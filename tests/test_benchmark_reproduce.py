import asyncio
import http.server
import json
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets

PORT, CDP = 8794, 9294
USER_DATA_DIR = r"C:\temp\chrome_benchmark_profile"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def benchmark_current_code():
    run_server()
    shutil.rmtree(USER_DATA_DIR, ignore_errors=True)

    # Read active stations cache
    with open("data/active_stations_cache.json", "r", encoding="utf-8") as f:
        stations_data = json.load(f)
    print(f"Loaded {len(stations_data)} active stations from cache.")

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
                nonlocal mid; mid += 1
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

            # Seed localStorage with all 472+ stations from active_stations_cache.json
            stations_json_str = json.dumps(stations_data)
            await eval_js(f"localStorage.setItem('equinox_custom_stations', {json.dumps(stations_json_str)});")
            # Also re-initialize station data
            await eval_js("initStationData();")
            station_count = await eval_js("ALL_STATIONS.length")
            print(f"ALL_STATIONS in browser memory: {station_count}")

            # Apply user's exact inputs
            await eval_js("""(() => {
                document.getElementById('originAddress').value = '179 S Powell Ave, Columbus, OH 43204 (West High School)';
                document.getElementById('destAddress').value = '270 Conestoga Dr, Marlton, NJ 08053';
                document.getElementById('optimizeDepartureTime').checked = true;
                document.getElementById('optimizeSpeedOffset').checked = false;
                document.getElementById('optimizeSpeedCap').checked = false;
                document.getElementById('departureDate').value = '2026-11-07';
                document.getElementById('departureTime').value = '08:00';
                document.getElementById('startSocSlider').value = '100';
                document.getElementById('bufferSlider').value = '10';
                document.getElementById('targetArrivalSlider').value = '15';
                document.getElementById('speedOffset').value = '10';
                document.getElementById('maxSpeedCap').value = '75';
                document.getElementById('minTimeSlider').value = '70';
                document.getElementById('maxTimeSlider').value = '130';
                document.getElementById('decamillaStopDuration').value = '3.0';
                document.getElementById('tempF').value = '68';
                document.getElementById('windSpeed').value = '8';
                document.getElementById('windDir').value = '270';
                document.getElementById('roadCond').value = 'dry';
            })()""")

            # Count how many stations matched the corridor
            matched_count = await eval_js("""(() => {
                const r = activeRoutesData[0] || (CORRIDOR_ROUTES_CACHE && CORRIDOR_ROUTES_CACHE['marlton_decamilla'] && CORRIDOR_ROUTES_CACHE['marlton_decamilla'][0]);
                if (r && r.coordinates) {
                    const m = matchStationsToPolyline(r.coordinates);
                    return m.matched.length;
                }
                return 0;
            })()""")
            print(f"Matched stations along corridor: {matched_count}")

            t0 = time.time()
            print("Triggering search...")
            await eval_js("handleSearchRoute();")

            for sec in range(180):
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                label = await eval_js("document.getElementById('calcProgressStageLabel')?.innerText")
                pct = await eval_js("document.getElementById('calcProgressPct')?.innerText")
                if sec % 5 == 0 or st == "Error":
                    err_msg = await eval_js("document.getElementById('auditLogSummary')?.innerText")
                    print(f"[{sec}s] Status: {st} | Progress: {pct} - {label} | Err: {err_msg}")
                if st in ("Optimization Complete", "No Routes Found"):
                    break
                await asyncio.sleep(1.0)

            elapsed = time.time() - t0
            timings = await eval_js("window.lastCalculationTimings")
            print(f"\nCompleted in {elapsed:.2f}s!")
            print("Profiling Timings:", json.dumps(timings, indent=2))

            curve_summary = await eval_js("""(() => {
                const res = (typeof calculatedResults !== 'undefined') ? calculatedResults : null;
                if (!res) return null;
                return {
                    curve_len: res.pareto_curve_x ? res.pareto_curve_x.length : 0,
                    fastest: res.fastest_x ? {
                        time_str: `${Math.floor(res.fastest_x.total_hours)}h ${Math.round((res.fastest_x.total_hours * 60) % 60)}m`,
                        cost: res.fastest_x.total_cost,
                        stops: res.fastest_x.stops.map(s => s.station ? s.station.name : s.name)
                    } : null,
                    cheapest: res.cheapest_x ? {
                        time_str: `${Math.floor(res.cheapest_x.total_hours)}h ${Math.round((res.cheapest_x.total_hours * 60) % 60)}m`,
                        cost: res.cheapest_x.total_cost,
                        stops: res.cheapest_x.stops.map(s => s.station ? s.station.name : s.name)
                    } : null,
                    pareto_samples: (res.pareto_curve_x || []).slice(0, 10).map(c => ({
                        time_str: `${Math.floor(c.total_hours)}h ${Math.round((c.total_hours * 60) % 60)}m`,
                        cost: Math.round(c.total_cost * 100) / 100,
                        stops_count: c.stops.length
                    }))
                };
            })()""")
            print("\nPARETO TRIO & CURVE SUMMARY:", json.dumps(curve_summary, indent=2))

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(benchmark_current_code())
