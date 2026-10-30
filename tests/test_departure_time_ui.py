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
USER_DATA_DIR = r"C:\temp\chrome_dep_test"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def test_departure_and_tou():
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

            async def eval_js(expr):
                m = await send("Runtime.evaluate", {"expression": expr, "awaitPromise": True})
                while True:
                    raw = json.loads(await ws.recv())
                    if raw.get("id") == m:
                        res = raw.get("result", {})
                        if "exceptionDetails" in res:
                            print("JS EXCEPTION:", res["exceptionDetails"])
                        return res.get("result", {}).get("value")

            await send("Page.enable")
            await asyncio.sleep(1.0)
            await eval_js("handleSearchRoute()")

            # Wait for route computation to finish on default Marlton
            for _ in range(100):
                status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if status == "Optimization Complete":
                    break
                await asyncio.sleep(0.2)

            # 1. Check default departure time and display
            dep_info = await eval_js("""
            (() => {
                const input = document.getElementById('departureTime');
                const disp = document.getElementById('departureTimeDisplay');
                return JSON.stringify({
                    val: input ? input.value : null,
                    disp: disp ? disp.innerText : null
                });
            })()
            """)
            print("Default Departure Time Info:", dep_info)
            parsed_dep = json.loads(dep_info)
            assert parsed_dep["val"] == "08:00"
            assert ("08:00 AM" in parsed_dep["disp"] or "8:00 AM" in parsed_dep["disp"])

            # 2. Check table stop rows and destination row for clock times
            table_info = await eval_js("""
            (() => {
                const tbody = document.getElementById('stopsTableBody');
                const rows = Array.from(tbody.querySelectorAll('tr')).map(r => r.innerText);
                const fastest = calculatedResults['fastest'];
                return JSON.stringify({
                    rowCount: rows.length,
                    sampleRow: rows[0],
                    destRow: rows[rows.length - 1],
                    destArrClock: fastest ? fastest.dest_arr_clock : null,
                    stops: fastest ? fastest.stops.map(s => ({
                        name: s.station.name,
                        arr: s.arr_clock,
                        dep: s.dep_clock,
                        rate: s.rate,
                        badge: s.badge
                    })) : []
                });
            })()
            """)
            print("\nTable Clock Times & Stops Info:")
            parsed_table = json.loads(table_info)
            print(f"Total rows: {parsed_table['rowCount']}")
            print(f"Destination ETA: {parsed_table['destArrClock']}")
            for st in parsed_table["stops"]:
                print(f"  {st['name']}: {st['arr']} -> {st['dep']} | ${st['rate']}/kWh [{st['badge']}]")

            assert parsed_table["destArrClock"] is not None
            assert len(parsed_table["stops"]) > 0
            assert parsed_table["stops"][0]["arr"] is not None

            # 3. Test changing departure time to 23:00 (11:00 PM)
            await eval_js("""
            (async () => {
                document.getElementById('departureTime').value = '23:00';
                updateDepartureTimeDisplay();
                await recomputeCurrentRoute();
            })()
            """)
            await asyncio.sleep(4.0)

            dep_night = await eval_js("""
            (() => {
                const input = document.getElementById('departureTime');
                const disp = document.getElementById('departureTimeDisplay');
                const fastest = calculatedResults['fastest'];
                return JSON.stringify({
                    val: input.value,
                    disp: disp.innerText,
                    destArrClock: fastest ? fastest.dest_arr_clock : null,
                    firstStopArr: fastest && fastest.stops.length > 0 ? fastest.stops[0].arr_clock : null
                });
            })()
            """)
            print("\nNight Departure Info (23:00):", dep_night)
            parsed_night = json.loads(dep_night)
            assert parsed_night["val"] == "23:00"
            assert "11:00 PM" in parsed_night["disp"]
            print("First stop arrives at:", parsed_night["firstStopArr"])
            print("Destination arrives at:", parsed_night["destArrClock"])

            print("\nALL UI DEPARTURE TIME & TIMELINE CLOCK TESTS PASSED SUCCESSFULLY!")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_departure_and_tou())
