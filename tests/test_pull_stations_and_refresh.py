import asyncio
import http.server
import json
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets

PORT, CDP = 8796, 9297
USER_DATA_DIR = r"C:\temp\chrome_pull_test"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def test_pull_and_refresh():
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

            # 1. Check Button text
            btn_text = await eval_js("document.getElementById('btnPullOcm').innerText.trim()")
            print(f"Button text: '{btn_text}'")
            assert "Pull Stations" in btn_text, f"Expected 'Pull Stations', got '{btn_text}'"

            # 2. Test Refresh Prices
            print("Triggering handleRefreshPrices()...")
            await eval_js("handleRefreshPrices()")
            for _ in range(30):
                await asyncio.sleep(0.5)
                box_text = await eval_js("document.getElementById('scraperStatusBox').innerText")
                if "Price Refresh Complete!" in box_text:
                    print(f"Refresh Prices status: {box_text.strip()}")
                    break
            else:
                raise TimeoutError("handleRefreshPrices did not finish in time")

            # Verify that Cherry Hill has its TOU rates intact after refresh
            ch_data = await eval_js("(() => { const s = ALL_STATIONS.find(x => x.id === 'tesla-cherry-hill-nj'); return { id: s.id, on: s.on, off: s.off, mem_on: s.mem_on, mem_off: s.mem_off, tou_rates_count: s.tou_rates?.length }; })()")
            print(f"Cherry Hill after refresh: {ch_data}")
            assert ch_data["mem_off"] == 0.34, f"Expected mem_off 0.34, got {ch_data['mem_off']}"
            assert ch_data["tou_rates_count"] == 2, f"Expected 2 tou_rates, got {ch_data['tou_rates_count']}"

            # 3. Test Pull Stations
            print("Triggering handlePullOcmStations()...")
            await eval_js("handlePullOcmStations()")
            for _ in range(60):
                await asyncio.sleep(0.5)
                box_text = await eval_js("document.getElementById('scraperStatusBox').innerText")
                if "Station Discovery Complete" in box_text:
                    print(f"Pull Stations status: {box_text.strip()}")
                    break
            else:
                raise TimeoutError("handlePullOcmStations did not finish in time")

            print("\nALL PULL STATIONS & REFRESH PRICES INTEGRATION TESTS PASSED!")

    finally:
        proc.kill()

asyncio.run(test_pull_and_refresh())
