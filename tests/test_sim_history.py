import asyncio
import http.server
import json
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets

PORT, CDP = 8792, 9292
USER_DATA_DIR = r"C:\temp\chrome_sim_history_test"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def test_sim_history_flow():
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
            await eval_js("localStorage.removeItem('ev_trip_sim_history')")

            # 1. Initial State: History should be empty
            hist0 = await eval_js("getSimHistory()")
            print("[TEST 1] Initial history count:", len(hist0))
            assert len(hist0) == 0, "History should be empty on first load"

            # 2. Run first simulation (Marlton, NJ)
            print("[TEST 2] Running 1st simulation...")
            await eval_js("document.getElementById('searchBtn').click()")
            for _ in range(120):
                await asyncio.sleep(0.5)
                status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if status and ("Optimization Complete" in status or "No Routes Found" in status):
                    break

            hist1 = await eval_js("getSimHistory()")
            print(f"  After 1st run, history count: {len(hist1)}")
            assert len(hist1) == 1, "History must contain 1 recorded run"
            run1 = hist1[0]
            print(f"  Run 1 Destination: {run1['inputs']['destination']}")
            print(f"  Run 1 Winner Duration: {run1['winners']['fastest_x']['total_hours']}h")
            assert "Marlton" in run1['inputs']['destination'], "Destination should be Marlton"

            # 3. Change destination to Sewickley, PA and run second simulation
            print("\n[TEST 3] Changing destination to Sewickley, PA and running 2nd simulation...")
            await eval_js("""(() => {
                document.getElementById('destAddress').value = "Sewickley, PA";
                document.getElementById('searchBtn').click();
            })()""")
            for _ in range(120):
                await asyncio.sleep(0.5)
                status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if status and ("Optimization Complete" in status or "No Routes Found" in status):
                    break

            hist2 = await eval_js("getSimHistory()")
            print(f"  After 2nd run, history count: {len(hist2)}")
            assert len(hist2) == 2, "History must contain 2 recorded runs"
            run2_latest = hist2[0]
            run2_prev = hist2[1]
            print(f"  Latest Run Destination: {run2_latest['inputs']['destination']} ({run2_latest['winners']['fastest_x']['total_hours']}h)")
            print(f"  Previous Run Destination: {run2_prev['inputs']['destination']} ({run2_prev['winners']['fastest_x']['total_hours']}h)")
            assert "Sewickley" in run2_latest['inputs']['destination']
            assert "Marlton" in run2_prev['inputs']['destination']

            # 4. Test formatDebugString output
            debug_str = await eval_js("formatDebugString(getSimHistory()[0])")
            print("\n[TEST 4] Formatted Debug String Preview:\n" + "="*50 + "\n" + debug_str + "\n" + "="*50)
            assert "[SIMULATION DEBUG RUN:" in debug_str
            assert "Sewickley" in debug_str
            assert "RESULTS (Fastest Route):" in debug_str

            # 5. Test UI Modal Rendering & Badge
            badgeText = await eval_js("document.getElementById('simHistoryCountBadge')?.innerText")
            badgeHidden = await eval_js("document.getElementById('simHistoryCountBadge')?.classList.contains('hidden')")
            print(f"\n[TEST 5] History Badge: '{badgeText}', Hidden: {badgeHidden}")
            assert badgeText == "2"
            assert not badgeHidden

            # Open modal
            await eval_js("openSimHistoryModal()")
            modalHidden = await eval_js("document.getElementById('simHistoryModal')?.classList.contains('hidden')")
            runsListHtml = await eval_js("document.getElementById('simRunsList')?.innerHTML")
            print(f"  Modal hidden: {modalHidden}, Rendered items contains 'Run #2': {'Run #2' in runsListHtml}")
            assert not modalHidden
            assert "Run #2" in runsListHtml
            assert "Run #1" in runsListHtml

            # Close modal
            await eval_js("closeSimHistoryModal()")
            modalClosed = await eval_js("document.getElementById('simHistoryModal')?.classList.contains('hidden')")
            assert modalClosed

            print("\n*** ALL SIMULATION HISTORY & DEBUG LOGGING TESTS PASSED! ***")
    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_sim_history_flow())
