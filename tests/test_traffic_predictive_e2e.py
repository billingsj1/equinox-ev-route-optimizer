import asyncio
import http.server
import json
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

            print("\n*** ALL TRAFFIC PREDICTIVE TESTS PASSED SUCCESSFULLY! ***")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_traffic_flow())
