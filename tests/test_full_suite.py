import asyncio
import http.server
import json
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets
import sys

import sys
sys.stdout.reconfigure(line_buffering=True)

PORT = 8788
CDP = 9288
USER_DATA_DIR = r"C:\temp\chrome_full_suite_88"

class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), SilentHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def run_full_suite():
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

    test_results = {}
    console_errors = []

    try:
        ws_url = None
        for _ in range(60):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP}/json").read())
                ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page"), None)
                if ws_url: break
            except Exception:
                time.sleep(0.1)

        if not ws_url:
            raise RuntimeError("Could not connect to Chrome CDP.")

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
                    if msg.get("method") == "Runtime.consoleAPICalled":
                        p = msg.get("params", {})
                        if p.get("type") in ("error", "warning"):
                            txt = " ".join([str(arg.get("value", "")) for arg in p.get("args", [])])
                            if "error" in p.get("type"):
                                console_errors.append(txt)
                    if msg.get("id") == req_id:
                        return msg.get("result", {})

            async def eval_js(expr):
                res = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
                return res.get("result", {}).get("value")

            await send("Runtime.enable")
            await asyncio.sleep(2.5)

            # Check 1: Verify HERE database loaded and spatial grid ready
            here_db_len = await eval_js("HERE_SPEED_LIMITS_DB ? HERE_SPEED_LIMITS_DB.length : 0")
            print(f"[CHECK 1] HERE Legal Speed Limits Database: {here_db_len} segments loaded.")
            assert here_db_len >= 700, f"Expected >= 700 HERE segments, got {here_db_len}"

            # Test spatial grid matcher directly
            test_match = await eval_js("""(() => {
                // Test a point on PA Turnpike (around Allegheny Mountain Tunnel PA)
                const spd = matchHereSpeedLimit(39.96129, -78.85742, 'I 76', 'Pennsylvania Turnpike');
                return spd;
            })()""")
            print(f"[CHECK 1b] Spatial match test on PA Turnpike I-76: {test_match} mph.")
            assert test_match in (55, 65, 70), f"Expected 55, 65 or 70 mph on PA Turnpike, got {test_match}"

            # Helper to run a simulation and wait for completion
            async def run_sim_test(name, config_fn, max_timeout=35):
                print(f"\n--- Running: {name} ---")
                t0 = time.time()
                await eval_js(config_fn)
                await eval_js("document.getElementById('searchBtn').click()")
                done = False
                for _ in range(int(max_timeout * 2)):
                    await asyncio.sleep(0.5)
                    st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                    if st in ("Optimization Complete", "No Routes Found"):
                        done = True
                        break
                elapsed = time.time() - t0
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                res = await eval_js("calculatedResults")
                fx = res.get("fastest_x") if res else None
                cx = res.get("cheapest_x") if res else None
                bx = res.get("balanced_x") if res else None
                print(f"    Status: {st} in {elapsed:.2f}s")
                if fx:
                    print(f"    Fastest: {fx['total_hours']:.2f}h | ${fx['total_cost']:.2f} | {len(fx['stops'])} stops | {fx.get('departure_clock', 'N/A')} | +{fx.get('speed_offset')}mph cap {fx.get('max_speed_cap')}")
                assert done and st == "Optimization Complete", f"{name} failed to complete in {max_timeout}s"
                assert fx is not None, f"{name} produced no fastest_x route"
                assert cx is not None, f"{name} produced no cheapest_x route"
                assert bx is not None, f"{name} produced no balanced_x route"
                return {"elapsed": elapsed, "fastest": fx, "cheapest": cx, "balanced": bx}

            # =========================================================================
            # TEST 1: Standard Search (No Optimize)
            # =========================================================================
            r1 = await run_sim_test("Test 1: Standard Search (No Optimize)", """(() => {
                document.getElementById('optimizeDepartureTime').checked = false;
                document.getElementById('optimizeSpeedOffset').checked = false;
                document.getElementById('optimizeSpeedCap').checked = false;
                document.getElementById('departureDate').value = '2026-12-23';
                document.getElementById('departureTime').value = '07:30';
                document.getElementById('speedOffset').value = '10';
                document.getElementById('maxSpeedCap').value = '75';
                document.getElementById('startSocSlider').value = '100';
                document.getElementById('decamillaStopDuration').value = '3.0';
            })()""")
            test_results["standard_no_opt"] = r1
            assert r1["fastest"]["speed_offset"] == 10
            assert r1["fastest"]["max_speed_cap"] == 75

            # =========================================================================
            # TEST 2: Optimize Time Only (+/- 2 hours)
            # =========================================================================
            r2 = await run_sim_test("Test 2: Optimize Departure Time Only", """(() => {
                document.getElementById('optimizeDepartureTime').checked = true;
                document.getElementById('optimizeSpeedOffset').checked = false;
                document.getElementById('optimizeSpeedCap').checked = false;
            })()""")
            test_results["opt_time_only"] = r2
            # Time optimization must be <= or equal to fixed departure
            print(f"    Comparison: Fixed={r1['fastest']['total_hours']:.3f}h vs OptTime={r2['fastest']['total_hours']:.3f}h")
            assert r2["fastest"]["total_hours"] <= r1["fastest"]["total_hours"] + 0.01, "Opt Time must not be slower than fixed"

            # =========================================================================
            # TEST 3: Optimize Speed Offset Only (+5 vs +10 mph)
            # =========================================================================
            r3 = await run_sim_test("Test 3: Optimize Speed Offset Only", """(() => {
                document.getElementById('optimizeDepartureTime').checked = false;
                document.getElementById('optimizeSpeedOffset').checked = true;
                document.getElementById('optimizeSpeedCap').checked = false;
            })()""")
            test_results["opt_speed_only"] = r3
            assert r3["fastest"]["speed_offset"] in (5, 10)

            # =========================================================================
            # TEST 4: Optimize Max Speed Cap Only (75 vs 80 mph)
            # =========================================================================
            r4 = await run_sim_test("Test 4: Optimize Max Speed Cap Only", """(() => {
                document.getElementById('optimizeDepartureTime').checked = false;
                document.getElementById('optimizeSpeedOffset').checked = false;
                document.getElementById('optimizeSpeedCap').checked = true;
            })()""")
            test_results["opt_cap_only"] = r4
            assert r4["fastest"]["max_speed_cap"] in (75, 80)

            # =========================================================================
            # TEST 5: Optimize Speed Offset + Max Speed Cap (Cumulative 4 pairs)
            # =========================================================================
            r5 = await run_sim_test("Test 5: Optimize Speed Offset + Cap", """(() => {
                document.getElementById('optimizeDepartureTime').checked = false;
                document.getElementById('optimizeSpeedOffset').checked = true;
                document.getElementById('optimizeSpeedCap').checked = true;
            })()""")
            test_results["opt_speed_and_cap"] = r5
            assert r5["fastest"]["speed_offset"] in (5, 10)
            assert r5["fastest"]["max_speed_cap"] in (75, 80)

            # =========================================================================
            # TEST 6: All Three Optimized (Time + Offset + Cap)
            # =========================================================================
            r6 = await run_sim_test("Test 6: All Three Optimized (Full Matrix)", """(() => {
                document.getElementById('optimizeDepartureTime').checked = true;
                document.getElementById('optimizeSpeedOffset').checked = true;
                document.getElementById('optimizeSpeedCap').checked = true;
            })()""", max_timeout=40)
            test_results["opt_all_three"] = r6
            print(f"    Comparison: OptTimeOnly={r2['fastest']['total_hours']:.3f}h vs OptAll3={r6['fastest']['total_hours']:.3f}h")
            # All 3 optimized should find an equal or faster route than Opt Time only!
            assert r6["fastest"]["total_hours"] <= r2["fastest"]["total_hours"] + 0.01, "All 3 optimized must be <= Time only"

            # =========================================================================
            # TEST 7: Direct Columbus -> Marlton without DeCamilla stop (0 hrs dwell)
            # =========================================================================
            r7 = await run_sim_test("Test 7: Direct Trip (0.0h DeCamilla dwell)", """(() => {
                document.getElementById('optimizeDepartureTime').checked = false;
                document.getElementById('optimizeSpeedOffset').checked = false;
                document.getElementById('optimizeSpeedCap').checked = false;
                document.getElementById('decamillaStopDuration').value = '0';
            })()""")
            test_results["direct_no_decamilla"] = r7
            # Without 3h dwell, total hours should be significantly shorter than 12.7h (~10.5h with realistic corridor traffic)
            print(f"    Direct Trip Duration: {r7['fastest']['total_hours']:.2f}h")
            assert r7["fastest"]["total_hours"] < 11.0, "Direct trip without 3h stop should be under 11.0h"

            # Check for critical console errors
            fatal_errors = [e for e in console_errors if "favicon" not in e.lower() and "404" not in e]
            print(f"\n[CONSOLE ERRORS CHECK]: {len(fatal_errors)} critical errors detected.")
            if fatal_errors:
                for err in fatal_errors:
                    print("  ! " + err)
            assert len(fatal_errors) == 0, f"Encountered unexpected console errors: {fatal_errors}"

            print("\n=======================================================")
            print(">>> ALL 7 FULL SUITE VERIFICATION TESTS PASSED 100%! <<<")
            print("=======================================================")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(run_full_suite())
