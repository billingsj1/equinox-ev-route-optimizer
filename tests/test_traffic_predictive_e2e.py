import asyncio
import http.server
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets

PORT, CDP = 8798, 9297
USER_DATA_DIR = r"C:\temp\chrome_traffic_e2e"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def test_traffic_flow():
    run_server()
    shutil.rmtree(USER_DATA_DIR, ignore_errors=True)

    proc = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        f"--remote-debugging-port={CDP}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--disable-gpu",
        "--no-first-run",
        f"http://127.0.0.1:{PORT}/index.html"
    ])

    try:
        ws_url = None
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP}/json").read())
                ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page"), None)
                if ws_url: break
            except Exception:
                time.sleep(0.1)

        async with websockets.connect(ws_url, max_size=None) as ws:
            mid = 0
            async def send(method, params=None):
                nonlocal mid
                mid += 1
                await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
                return mid

            async def call(method, params=None):
                req_id = await send(method, params)
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == req_id:
                        return msg.get("result", {})

            async def eval_js(expr):
                res = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
                return res.get("result", {}).get("value")

            await asyncio.sleep(2.0)

            # Seed full active stations cache into localStorage
            with open("data/active_stations_cache.json", "r", encoding="utf-8") as f:
                cached_stations = json.load(f)
            await eval_js(f"localStorage.setItem('equinox_custom_stations', {json.dumps(json.dumps(cached_stations))});")
            await eval_js("initStationData();")
            total_stations = await eval_js("ALL_STATIONS.length")
            print(f"[INIT] Loaded {total_stations} active stations into browser memory from cache.")

            # Set Origin: DeCamilla (1185 Gettysburg Pike, Dillsburg, PA)
            # Set Destination: Marlton, NJ
            # Speed offset: +10 mph, Max cap: 80 mph
            print("\n[TEST 1] Setting origin: DeCamilla, destination: Marlton, +10mph offset, 80mph cap...")
            await eval_js("""(() => {
                document.getElementById('originAddress').value = "1185 Gettysburg Pike, Dillsburg, PA 17019";
                document.getElementById('destAddress').value = "270 Conestoga Dr, Marlton, NJ 08053";
                document.getElementById('speedOffset').value = "10";
                document.getElementById('maxSpeedCap').value = "80";
            })()""")

            # Test A: Off-peak free flow (Sunday 9:00 AM)
            print("Configuring Sunday 9:00 AM departure (Free Flow)...")
            await eval_js("""(() => {
                document.getElementById('departureDate').value = "2026-11-08"; // Sunday
                document.getElementById('departureTime').value = "09:00";
                document.getElementById('searchBtn').click();
            })()""")

            for _ in range(60):
                await asyncio.sleep(0.5)
                status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if status in ("Optimization Complete", "No Routes Found"):
                    break

            sunday_info = await eval_js("""(() => {
                if (!calculatedResults || !calculatedResults.fastest) return null;
                const f = calculatedResults.fastest;
                return {
                    route_name: f.route ? f.route.name : '',
                    total_hours: f.total_hours,
                    drive_hours: f.drive_hours,
                    routes_count: activeRoutesData.length,
                    routes: activeRoutesData.map(r => ({ id: r.id, name: r.name, dist: r.distance }))
                };
            })()""")
            print(f"Sunday Results: {json.dumps(sunday_info, indent=2)}")
            assert sunday_info is not None, "Calculation should succeed for Sunday"
            print(f"Sunday Total Driving Time: {int(sunday_info['drive_hours'])}h {int(round((sunday_info['drive_hours']%1)*60))}m")
            assert 2.0 <= sunday_info['drive_hours'] <= 2.35, f"Expected off-peak ~2h05m-2h20m, got {sunday_info['drive_hours']}h"

            # Test B: Friday PM Peak Commute (Friday 3:30 PM departure)
            print("\nConfiguring Friday 3:30 PM departure (Rush Hour Commute)...")
            await eval_js("""(() => {
                document.getElementById('departureDate').value = "2026-11-06"; // Friday
                document.getElementById('departureTime').value = "15:30";
                document.getElementById('searchBtn').click();
            })()""")

            for _ in range(60):
                await asyncio.sleep(0.5)
                status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if status in ("Optimization Complete", "No Routes Found"):
                    break

            friday_info = await eval_js("""(() => {
                if (!calculatedResults || !calculatedResults.fastest) return null;
                const f = calculatedResults.fastest;
                return {
                    route_name: f.route ? f.route.name : '',
                    total_hours: f.total_hours,
                    drive_hours: f.drive_hours,
                    routes_count: activeRoutesData.length,
                    routes: activeRoutesData.map(r => ({ id: r.id, name: r.name, dist: r.distance }))
                };
            })()""")
            print(f"Friday PM Results: {json.dumps(friday_info, indent=2)}")
            assert friday_info is not None, "Calculation should succeed for Friday"
            print(f"Friday PM Total Driving Time: {int(friday_info['drive_hours'])}h {int(round((friday_info['drive_hours']%1)*60))}m")
            assert friday_info['drive_hours'] > sunday_info['drive_hours'], "Friday rush hour should take longer than Sunday free flow"

            # Test C: On-Demand TomTom Precision Sync
            print("\n[TEST 2] Testing on-demand TomTom Precision Sync...")
            key_path = "scratch/tomtom_api_key.txt"
            api_key = ""
            if os.path.exists(key_path):
                with open(key_path, "r", encoding="utf-8") as f:
                    api_key = f.read().strip()
            if not api_key:
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.getenv("TOMTOM_API_KEY", "")

            assert api_key, "API key should be present in scratch/tomtom_api_key.txt or .env"

            # Inject TomTom API Key into window and localStorage
            await eval_js(f"""(() => {{
                window.TOMTOM_API_KEY = "{api_key}";
                localStorage.setItem("tomtom_api_key", "{api_key}");
                const inp = document.getElementById("tomtomApiKeyInput");
                if (inp) inp.value = "{api_key}";
            }})()""")

            # Click TomTom Precision button
            print("Clicking #precisionSyncBtn...")
            await eval_js("document.getElementById('precisionSyncBtn').click();")

            # Wait for sync to complete (max 30 seconds)
            precision_completed = False
            for _ in range(60):
                await asyncio.sleep(0.5)
                btn_text = await eval_js("document.getElementById('precisionSyncBtnText')?.innerText")
                badge_hidden = await eval_js("document.getElementById('precisionStatusBadge')?.classList.contains('hidden')")
                if "Precision Active" in (btn_text or "") and not badge_hidden:
                    precision_completed = True
                    break

            assert precision_completed, "TomTom Precision Sync should complete and activate badge"
            print("TomTom Precision Sync completed successfully!")

            # Verify that route cards and timeline have precision results
            precision_results = await eval_js("""(() => {
                const f = calculatedResults?.fastest_x;
                const tblRows = document.getElementById('stopsTableBody')?.children.length;
                return {
                    fastest_x_hours: f?.total_hours,
                    drive_hours: f?.drive_hours,
                    traffic_delay_mins: f?.total_traffic_delay_mins,
                    dest_arr_clock: f?.dest_arr_clock,
                    stops_count: f?.stops?.length,
                    table_rows: tblRows
                };
            })()""")

            print(f"Precision Route Details: {json.dumps(precision_results, indent=2)}")
            assert precision_results["fastest_x_hours"] > 0, "Precision sync should produce valid total hours"
            print(f"Precision Total Traffic Delay: +{precision_results['traffic_delay_mins']} mins")

            print("\n*** ALL TRAFFIC PREDICTIVE & PRECISION TESTS PASSED SUCCESSFULLY! ***")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_traffic_flow())
