import asyncio
import http.server
import json
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets

PORT, CDP = 8799, 9298
USER_DATA_DIR = r"C:\temp\chrome_decamilla_e2e"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def test_decamilla_flow():
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

            # Wait for initial load
            await asyncio.sleep(2.0)

            # 1. Verify decamillaOptionBox is visible on default Marlton destination
            box_hidden = await eval_js("document.getElementById('decamillaOptionBox').classList.contains('hidden')")
            print(f"DeCamilla box hidden: {box_hidden} (expected False)")
            assert not box_hidden, "decamillaOptionBox should be visible for Marlton"

            # Check initial calculation state
            init_results = await eval_js("typeof calculatedResults !== 'undefined' && calculatedResults !== null")
            print(f"Initial results calculated on page load: {init_results}")

            # 2. Test user selecting 2.0 hr stop at DeCamilla WITHOUT pressing Calculate Route
            # Clear calculatedResults to verify no auto-calculation fires
            await eval_js("window.testCalcRan = false; calculatedResults = null;")
            
            # Change decamillaStopDuration
            await eval_js("""(() => {
                const sel = document.getElementById('decamillaStopDuration');
                sel.value = "2.0";
                sel.dispatchEvent(new Event('change'));
            })()""")

            # Wait 1.5 seconds to see if any calculation triggered
            await asyncio.sleep(1.5)
            calc_after_dropdown = await eval_js("calculatedResults !== null")
            print(f"Calculated results after dropdown change: {calc_after_dropdown} (expected False - NO auto-calc)")
            assert not calc_after_dropdown, "Dropdown change should NOT automatically calculate routes!"

            # Change departure time to 07:30
            await eval_js("""(() => {
                const el = document.getElementById('departureTime');
                el.value = "07:30";
                el.dispatchEvent(new Event('change'));
            })()""")

            await asyncio.sleep(1.0)
            time_badge = await eval_js("document.getElementById('departureTimeDisplay').innerText")
            print(f"Departure time display badge: '{time_badge}'")
            assert "7:30" in time_badge, "Departure time badge should be updated"

            calc_after_time = await eval_js("calculatedResults !== null")
            print(f"Calculated results after departure time change: {calc_after_time} (expected False - NO auto-calc)")
            assert not calc_after_time, "Departure time change should NOT automatically calculate routes!"

            # 3. Now explicitly click the 'Calculate Route' button
            print("Clicking 'Calculate Route' button...")
            await eval_js("document.getElementById('searchBtn').click()")

            # Wait for optimization to complete
            for _ in range(120):
                await asyncio.sleep(0.5)
                status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if status in ("Optimization Complete", "No Routes Found"):
                    print(f"Status: {status}")
                    break

            # 4. Check calculated results
            res = await eval_js("""(() => {
                if (typeof calculatedResults === 'undefined' || !calculatedResults) return null;
                const r = calculatedResults;
                const f = r.fastest;
                const c = r.cheapest;
                const b = r.balanced;
                const ns = r.nonStop;
                return {
                    fastest: {
                        total_hours: f.total_hours,
                        total_cost: f.total_cost,
                        toll_cost: f.toll_cost,
                        stops: f.stops.map(s => ({
                            name: s.station.name,
                            arr_soc: s.arr_soc,
                            tgt_soc: s.tgt_soc,
                            mins: s.mins,
                            cost: s.cost,
                            is_decamilla: s.is_decamilla,
                            detour_miles: s.detour_miles
                        }))
                    },
                    cheapest: {
                        total_hours: c.total_hours,
                        total_cost: c.total_cost,
                        toll_cost: c.toll_cost,
                        stops: c.stops.map(s => ({
                            name: s.station.name,
                            arr_soc: s.arr_soc,
                            tgt_soc: s.tgt_soc,
                            mins: s.mins,
                            cost: s.cost,
                            is_decamilla: s.is_decamilla,
                            detour_miles: s.detour_miles
                        }))
                    },
                    nonStop: ns
                };
            })()""")

            assert res is not None, "Results should be computed after pressing Calculate Route"
            print(f"Fastest total hours: {res['fastest']['total_hours']:.2f}h | Total cost: ${res['fastest']['total_cost']:.2f}")
            print(f"Fastest highway toll: ${res['fastest']['toll_cost']:.2f} (expected $37.59)")
            assert abs(res['fastest']['toll_cost'] - 37.59) < 0.01, f"Toll cost should be $37.59, got {res['fastest']['toll_cost']}"

            print("Fastest stops:")
            found_decamilla = False
            for s in res['fastest']['stops']:
                print(f"  - {s['name']}: {s['arr_soc']}% -> {s['tgt_soc']}%, {s['mins']} mins, ${s['cost']:.2f}, is_decamilla={s.get('is_decamilla')}, detour={s.get('detour_miles')} mi")
                if s.get('is_decamilla'):
                    found_decamilla = True
                    assert s['mins'] == 120, "DeCamilla stop should be 120 mins"
                    assert s['cost'] == 0.0, "DeCamilla stop should be free ($0.00)"
                    assert s['detour_miles'] == 12.8, f"DeCamilla detour should be 12.8 mi, got {s['detour_miles']}"
            assert found_decamilla, "Fastest itinerary must include DeCamilla stop"

            # Check Non-Stop driving baseline
            ns = res['nonStop']
            print(f"Non-stop baseline: {ns['hours']:.2f}h, decamilla stop hours: {ns.get('decamilla_stop_hours')}h")
            assert ns.get('decamilla_stop_hours') == 2.0, "Non-stop baseline should include 2h DeCamilla stop"

            # Check table HTML rendering for detour badge and 2026 toll label
            tbody_html = await eval_js("document.getElementById('stopsTableBody').innerHTML")
            assert "+12.8 mi" in tbody_html, "Table must show +12.8 mi detour badge for DeCamilla"
            assert "Exit 236" in tbody_html, "Table must show Exit 236 for DeCamilla"

            tfoot_html = await eval_js("document.getElementById('stopsTableFoot').innerHTML")
            assert "2026 PA Turnpike E-ZPass" in tfoot_html, "Table footer must label 2026 PA Turnpike E-ZPass"
            assert "$37.59" in tfoot_html, "Table footer must show $37.59 toll"

            print("\n*** ALL E2E TESTS PASSED SUCCESSFULLY! ***")

    finally:
        proc.terminate()

if __name__ == '__main__':
    asyncio.run(test_decamilla_flow())
