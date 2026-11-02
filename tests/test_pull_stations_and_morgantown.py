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
USER_DATA_DIR = r"C:\temp\chrome_pull_stations_e2e"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def test_pull_stations_flow():
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

            # 1. First pull stations
            print("\n[TEST 1] Triggering 1st handlePullOcmStations()...")
            await eval_js("handlePullOcmStations();")

            first_status = ""
            for _ in range(60):
                await asyncio.sleep(1.0)
                status = await eval_js("document.getElementById('scraperStatusBox')?.innerText")
                if status and "Station Discovery Complete" in status:
                    lines = [line.strip() for line in status.splitlines() if line.strip()]
                    first_status = lines[0] if lines else status.strip()
                    print("1st Pull Status:", first_status)
                    break

            # 2. Check Morgantown, PA station details
            print("\n[TEST 2] Verifying Morgantown, PA station details...")
            morgantown = await eval_js("""(() => {
                const s = ALL_STATIONS.find(x => x.id === 'tesla-34183' || ((x.name || '').includes('Morgantown') && x.state === 'PA'));
                if (!s) return null;
                return {
                    id: s.id,
                    name: s.name,
                    network: s.network,
                    rate_on: s.on,
                    rate_off: s.off,
                    mem_on: s.mem_on,
                    mem_off: s.mem_off,
                    tou_rates: s.tou_rates,
                    price_verified: s.price_verified
                };
            })()""")

            print("Morgantown station data:", json.dumps(morgantown, indent=2))
            assert morgantown is not None, "Morgantown, PA station should be found in ALL_STATIONS!"
            assert "PA, PA" not in morgantown["name"], f"Double state found in name: {morgantown['name']}"
            assert morgantown["name"] == "Tesla Supercharger (NACS Adapter) - Morgantown, PA", f"Unexpected name: {morgantown['name']}"
            assert morgantown["mem_on"] == 0.41, f"Expected member rate $0.41, got {morgantown['mem_on']}"
            assert morgantown["rate_on"] == 0.56, f"Expected non-member rate $0.56, got {morgantown['rate_on']}"
            assert not morgantown.get("tou_rates") or len(morgantown.get("tou_rates")) == 0, f"Expected flat rate (no TOU), got {morgantown.get('tou_rates')}"
            print("Morgantown name and flat $0.41 member pricing verified successfully!")

            # 3. Trigger second pull stations immediately
            print("\n[TEST 3] Triggering 2nd handlePullOcmStations() (idempotency check)...")
            await eval_js("handlePullOcmStations();")

            second_status = ""
            for _ in range(60):
                await asyncio.sleep(1.0)
                status = await eval_js("document.getElementById('scraperStatusBox')?.innerText")
                if status and "Station Discovery Complete" in status:
                    lines = [line.strip() for line in status.splitlines() if line.strip()]
                    second_status = lines[0] if lines else status.strip()
                    print("2nd Pull Status:", second_status)
                    break

            assert "Added 34 stations" not in second_status, f"Bug reproduced! Still added 34 stations: {second_status}"
            assert "up to date" in second_status or "Added 0" in second_status, f"Unexpected 2nd pull status: {second_status}"
            print("Pull Stations idempotency confirmed: no duplicate 34 stations added!")

            print("\n*** ALL TESTS PASSED SUCCESSFULLY! ***")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_pull_stations_flow())
