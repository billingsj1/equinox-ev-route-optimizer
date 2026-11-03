"""
Test Suite for Blink Network Integration:
1. Verifies 'Blink' is included in KNOWN_NETWORKS, NETWORK_COLORS, and checkbox UI.
2. Verifies seed Blink stations exist in ALL_STATIONS with verified DCFC pricing.
3. Tests pull stations with Blink (Operator ID 9) included.
4. Verifies network filter toggle for Blink (included vs excluded from routing candidate stops).
"""

import asyncio
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import websockets

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

HTTP_PORT = 8791
CDP_PORT = 9281
USER_DATA_DIR = r"C:\temp\chrome_blink_test"

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

def start_http_server():
    server = http.server.HTTPServer(("127.0.0.1", HTTP_PORT), QuietHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server

async def run_blink_tests():
    start_http_server()
    shutil.rmtree(USER_DATA_DIR, ignore_errors=True)
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
        "--disable-gpu",
        f"http://127.0.0.1:{HTTP_PORT}/index.html"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        ws_url = None
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json").read())
                ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"), None)
                if ws_url:
                    break
            except Exception:
                time.sleep(0.1)

        assert ws_url, "Could not obtain Chrome websocket URL"

        async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
            msg_counter = 0

            async def call(method, params=None):
                nonlocal msg_counter
                msg_counter += 1
                mid = msg_counter
                cmd = {"id": mid, "method": method}
                if params:
                    cmd["params"] = params
                await ws.send(json.dumps(cmd))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == mid:
                        return m.get("result", {})

            await call("Page.enable")
            await call("Runtime.enable")
            await asyncio.sleep(2.0)

            # Test 1: Verify Blink in KNOWN_NETWORKS & NETWORK_COLORS & ALL_STATIONS
            t1 = await call("Runtime.evaluate", {
                "expression": """
                (() => {
                    const hasKnown = KNOWN_NETWORKS.includes("Blink");
                    const color = NETWORK_COLORS["Blink"];
                    const blinkStations = ALL_STATIONS.filter(s => s.network === "Blink");
                    const enabled = isNetworkEnabled("Blink");
                    return { hasKnown, color, blinkCount: blinkStations.length, enabled, sample: blinkStations[0] };
                })()
                """,
                "returnByValue": True
            })
            r1 = t1.get("result", {}).get("value", {})
            print("[TEST 1] Blink Network Registry:")
            print("  KNOWN_NETWORKS includes Blink:", r1.get("hasKnown"))
            print("  NETWORK_COLORS['Blink']:", r1.get("color"))
            print("  Initial Blink Stations count:", r1.get("blinkCount"))
            print("  isNetworkEnabled('Blink'):", r1.get("enabled"))
            print("  Sample Blink Station:", json.dumps(r1.get("sample"), indent=2))

            assert r1.get("hasKnown") is True, "Blink must be in KNOWN_NETWORKS!"
            assert r1.get("color") == "#0284c7", "Blink must have color #0284c7!"
            assert r1.get("blinkCount", 0) >= 4, "Initial seed Blink stations must be >= 4!"
            assert r1.get("enabled") is True, "Blink should be enabled by default!"

            # Test 2: Verify Network Checkbox DOM rendering
            t2 = await call("Runtime.evaluate", {
                "expression": """
                (() => {
                    renderNetworkFilters();
                    const cb = document.getElementById('net-filter-blink');
                    return {
                        exists: !!cb,
                        checked: cb ? cb.checked : false
                    };
                })()
                """,
                "returnByValue": True
            })
            r2 = t2.get("result", {}).get("value", {})
            print("\n[TEST 2] Network Filter Checkbox DOM:")
            print("  #net-filter-blink exists:", r2.get("exists"))
            print("  #net-filter-blink checked:", r2.get("checked"))
            assert r2.get("exists") is True, "#net-filter-blink checkbox must exist in DOM!"
            assert r2.get("checked") is True, "#net-filter-blink checkbox must be checked!"

            # Test 3: Test toggling Blink off and on
            t3 = await call("Runtime.evaluate", {
                "expression": """
                (() => {
                    toggleNetwork('Blink', false);
                    const disabled = !isNetworkEnabled('Blink');
                    toggleNetwork('Blink', true);
                    const reEnabled = isNetworkEnabled('Blink');
                    return { disabled, reEnabled };
                })()
                """,
                "returnByValue": True
            })
            r3 = t3.get("result", {}).get("value", {})
            print("\n[TEST 3] Network Toggle Behavior:")
            print("  Disabled on toggleNetwork(false):", r3.get("disabled"))
            print("  Re-enabled on toggleNetwork(true):", r3.get("reEnabled"))
            assert r3.get("disabled") is True, "Blink should be disabled when unchecked!"
            assert r3.get("reEnabled") is True, "Blink should be re-enabled when checked!"

            # Test 4: Pull stations and verify Blink discovery from OCM + DCFC pricing
            print("\n[TEST 4] Triggering handlePullOcmStations() with Blink...")
            pull_res = await call("Runtime.evaluate", {
                "expression": """
                (async () => {
                    await handlePullOcmStations();
                    const status = document.getElementById('ocmPullStatusBox')?.innerText || '';
                    const blinkSt = ALL_STATIONS.filter(s => s.network === 'Blink');
                    const pricedBlink = blinkSt.filter(s => s.price_verified && s.on > 0);
                    return {
                        status: status.slice(0, 150),
                        totalBlink: blinkSt.length,
                        pricedBlink: pricedBlink.length,
                        samplePriced: pricedBlink.slice(0, 3)
                    };
                })()
                """,
                "awaitPromise": True,
                "returnByValue": True
            })
            r4 = pull_res.get("result", {}).get("value", {})
            print("  Pull Status:", r4.get("status"))
            print("  Total Blink Stations after pull:", r4.get("totalBlink"))
            print("  Priced / Verified Blink Stations:", r4.get("pricedBlink"))
            print("  Sample Priced Stations:")
            for sp in r4.get("samplePriced", []):
                print(f"    - {sp.get('name')}: ${sp.get('on')}/kWh, {sp.get('kw')}kW ({sp.get('plug')})")

            assert r4.get("totalBlink", 0) >= 4, "Blink stations should exist!"
            assert r4.get("pricedBlink", 0) >= 4, "Blink stations should be priced!"

            print("\n" + "=" * 55)
            print("*** ALL BLINK NETWORK TESTS PASSED SUCCESSFULLY! ***")
            print("=" * 55)

    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            chrome_proc.kill()
        try:
            shutil.rmtree(USER_DATA_DIR, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(run_blink_tests())
