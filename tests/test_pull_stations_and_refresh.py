import asyncio
import http.server
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import websockets

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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

            # 2. Test Pull Stations
            print("\n--- Testing handlePullOcmStations() ---")
            await eval_js("handlePullOcmStations()")
            for _ in range(80):
                await asyncio.sleep(0.5)
                box_text = await eval_js("document.getElementById('scraperStatusBox').innerText")
                if "Station Discovery Complete" in box_text:
                    print(f"Pull Stations status: {box_text.strip()}")
                    break
            else:
                raise TimeoutError("handlePullOcmStations did not finish in time")

            # Verify NY stations are NOT present
            ny_tesla = await eval_js("ALL_STATIONS.filter(s => s.network === 'Tesla' && (s.state === 'NY' || (s.name && s.name.includes(', NY'))))")
            print(f"NY Tesla stations in database: {len(ny_tesla)}")
            assert len(ny_tesla) == 0, f"Expected 0 NY Tesla stations, but found {len(ny_tesla)}: {ny_tesla}"

            # Check specific unwanted sites mentioned by user
            unwanted_names = ["West Seneca", "North Hudson", "Staten Island", "Parish"]
            for bad in unwanted_names:
                match = await eval_js(f"ALL_STATIONS.find(s => s.name && s.name.toLowerCase().includes('{bad.lower()}'))")
                assert match is None, f"Found unwanted site '{bad}': {match}"
            print("Verified: West Seneca, North Hudson, Staten Island, and Parish are NOT in station list.")

            # Check corridor Tesla stations count
            corridor_tesla = await eval_js("ALL_STATIONS.filter(s => s.network === 'Tesla')")
            print(f"Corridor Tesla Magic Dock stations added: {len(corridor_tesla)}")
            assert len(corridor_tesla) > 0, "No Tesla stations were pulled!"

            # 3. Test Refresh Prices
            print("\n--- Testing handleRefreshPrices() ---")
            await eval_js("handleRefreshPrices()")
            for _ in range(40):
                await asyncio.sleep(0.5)
                box_text = await eval_js("document.getElementById('scraperStatusBox').innerText")
                if "Price Refresh Complete" in box_text:
                    print(f"Refresh Prices status: {box_text.strip()}")
                    break
            else:
                raise TimeoutError("handleRefreshPrices did not finish in time")

            # Check unverified Tesla stations
            unverified_tesla = await eval_js("ALL_STATIONS.filter(s => s.network === 'Tesla' && (s.price_verified === false || s.on == null || s.on <= 0))")
            print(f"Unverified Tesla stations: {len(unverified_tesla)}")
            if len(unverified_tesla) > 0:
                print(f"First 5 unverified: {unverified_tesla[:5]}")
            assert len(unverified_tesla) == 0, f"Found unverified Tesla stations: {len(unverified_tesla)}"

            # Check specific verified corridor stations
            bellmawr = await eval_js("ALL_STATIONS.find(s => s.name && s.name.includes('Bellmawr'))")
            print(f"Bellmawr verification: name='{bellmawr.get('name')}', on={bellmawr.get('on')}, off={bellmawr.get('off')}, mem_on={bellmawr.get('mem_on')}, mem_off={bellmawr.get('mem_off')}, verified={bellmawr.get('price_verified')}")
            assert bellmawr.get('price_verified') is True

            cherry_hill = await eval_js("ALL_STATIONS.find(s => s.name && s.name.includes('Cherry Hill'))")
            print(f"Cherry Hill verification: name='{cherry_hill.get('name')}', on={cherry_hill.get('on')}, off={cherry_hill.get('off')}, mem_on={cherry_hill.get('mem_on')}, mem_off={cherry_hill.get('mem_off')}, verified={cherry_hill.get('price_verified')}")
            assert cherry_hill.get('price_verified') is True
            assert cherry_hill.get('mem_off') == 0.34

            # 3b. Test second refresh (should report 0 station prices changed)
            print("\n--- Testing second handleRefreshPrices() (0 changes expected) ---")
            await eval_js("handleRefreshPrices()")
            for _ in range(40):
                await asyncio.sleep(0.5)
                box_text2 = await eval_js("document.getElementById('scraperStatusBox').innerText")
                if "Price Refresh Complete:" in box_text2:
                    print(f"Second Refresh status: {box_text2.strip()}")
                    break
            else:
                raise TimeoutError("Second handleRefreshPrices did not finish in time")
            assert "0 station prices changed" in box_text2, f"Expected '0 station prices changed', got: {box_text2}"

            # 4. Test purge of injected NY station
            print("\n--- Testing purgeBlockedStations() on legacy/injected NY stations ---")
            await eval_js("ALL_STATIONS.push({ id: 'tesla-west-seneca', network: 'Tesla', name: 'Tesla Supercharger - West Seneca, NY', state: 'NY', lat: 42.85, lon: -78.75 })")
            check_injected = await eval_js("ALL_STATIONS.some(s => s.id === 'tesla-west-seneca')")
            assert check_injected is True
            await eval_js("purgeBlockedStations()")
            check_purged = await eval_js("ALL_STATIONS.some(s => s.id === 'tesla-west-seneca')")
            assert check_purged is False
            print("Purge successfully removed injected West Seneca, NY station!")

            print("\n=======================================================")
            print("ALL PULL STATIONS & REFRESH PRICES INTEGRATION TESTS PASSED!")
            print("=======================================================")

    finally:
        proc.kill()

asyncio.run(test_pull_and_refresh())
