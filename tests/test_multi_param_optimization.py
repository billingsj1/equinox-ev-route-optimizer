import asyncio
import http.server
import json
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets

PORT, CDP = 8793, 9293
USER_DATA_DIR = r"C:\temp\chrome_multi_opt_test"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def test_multi_param_opt():
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

            # Check presence of all 3 checkboxes
            hasDepOpt = await eval_js("document.getElementById('optimizeDepartureTime') != null")
            hasSpdOpt = await eval_js("document.getElementById('optimizeSpeedOffset') != null")
            hasCapOpt = await eval_js("document.getElementById('optimizeSpeedCap') != null")
            print(f"[CHECK] Checkboxes present: dep={hasDepOpt}, spd={hasSpdOpt}, cap={hasCapOpt}")
            assert hasDepOpt and hasSpdOpt and hasCapOpt, "All 3 optimize checkboxes must exist"

            # Check that optimizeDepartureTime is BELOW departureTime in DOM order
            isBelow = await eval_js("""(() => {
                const depTime = document.getElementById('departureTime');
                const optDep = document.getElementById('optimizeDepartureTime');
                return (depTime.compareDocumentPosition(optDep) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
            })()""")
            print(f"[CHECK] optimizeDepartureTime is placed below departureTime: {isBelow}")
            assert isBelow, "optimizeDepartureTime must be placed below departureTime in the DOM"

            # Enable all 3 optimize checkboxes
            print("\n[TEST] Enabling all 3 optimize checkboxes (Time, Speed Offset, Max Speed Cap)...")
            await eval_js("""(() => {
                document.getElementById('optimizeDepartureTime').checked = true;
                document.getElementById('optimizeSpeedOffset').checked = true;
                document.getElementById('optimizeSpeedCap').checked = true;
            })()""")

            # Run simulation
            await eval_js("document.getElementById('searchBtn').click()")
            for _ in range(120):
                await asyncio.sleep(0.5)
                status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if status in ("Optimization Complete", "No Routes Found"):
                    break

            # Verify winner results
            fx = await eval_js("calculatedResults.fastest_x")
            assert fx is not None, "Fastest route must exist"
            print(f"  Fastest Duration: {fx['total_hours']}h")
            print(f"  Departure Clock: {fx.get('departure_clock')}")
            print(f"  Speed Offset: {fx.get('speed_offset')} mph")
            print(f"  Max Speed Cap: {fx.get('max_speed_cap')} mph")

            assert fx.get('speed_offset') in (5, 10), "Speed offset should be one of [5, 10]"
            assert fx.get('max_speed_cap') in (75, 80), "Speed cap should be one of [75, 80]"

            # Check card UI elements
            speedText = await eval_js("document.getElementById('fastestSpeed_x')?.innerText")
            print(f"  Card Speed Text: {speedText}")
            assert "mph" in speedText and "cap" in speedText

            # Check debug string formatting
            debug_str = await eval_js("formatDebugString(getSimHistory()[0])")
            print("\n[DEBUG STRING PREVIEW]:\n" + debug_str)
            assert "[Opt +/-2h]" in debug_str
            assert "[Opt +5/+10]" in debug_str
            assert "[Opt 75/80]" in debug_str
            assert "Selected Plan: Depart" in debug_str

            print("\n*** ALL MULTI-PARAMETER OPTIMIZATION TESTS PASSED! ***")
    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_multi_param_opt())
