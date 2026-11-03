import asyncio
import http.server
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets

PORT = 8794
CDP_PORT = 9294
USER_DATA_DIR = r"C:\temp\chrome_blink_network_test"

class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

def start_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), SilentHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server

async def run_blink_and_kw_tests():
    start_server()
    shutil.rmtree(USER_DATA_DIR, ignore_errors=True)

    chrome_cmd = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"http://127.0.0.1:{PORT}/index.html"
    ]
    proc = subprocess.Popen(chrome_cmd)

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

            # Test 1: Verify Blink in KNOWN_NETWORKS & NETWORK_COLORS
            t1 = await call("Runtime.evaluate", {
                "expression": """
                (() => {
                    const hasKnown = KNOWN_NETWORKS.includes("Blink");
                    const color = NETWORK_COLORS["Blink"];
                    const enabled = isNetworkEnabled("Blink");
                    return { hasKnown, color, enabled };
                })()
                """,
                "returnByValue": True
            })
            r1 = t1.get("result", {}).get("value", {})
            print("[TEST 1] Blink Network Registry:")
            print("  KNOWN_NETWORKS includes Blink:", r1.get("hasKnown"))
            print("  NETWORK_COLORS['Blink']:", r1.get("color"))
            print("  isNetworkEnabled('Blink'):", r1.get("enabled"))

            assert r1.get("hasKnown") is True, "Blink must be in KNOWN_NETWORKS!"
            assert r1.get("color") == "#0284c7", "Blink must have color #0284c7!"
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

            # Test 4: Pull stations and verify 100 kW restriction (Zero < 100 kW public stations)
            print("\n[TEST 4] Triggering handlePullOcmStations() and verifying >= 100 kW restriction...")
            pull_res = await call("Runtime.evaluate", {
                "expression": """
                (async () => {
                    await handlePullOcmStations();
                    const status = document.getElementById('scraperStatusBox')?.innerText || '';
                    const sub100 = ALL_STATIONS.filter(s => !s.is_decamilla && s.network !== 'Private' && (s.kw || 0) < 100);
                    const cp50 = ALL_STATIONS.filter(s => s.network === 'ChargePoint' && (s.kw || 0) < 100);
                    const allPublic = ALL_STATIONS.filter(s => !s.is_decamilla && s.network !== 'Private');
                    const minPublicKw = Math.min(...allPublic.map(s => s.kw || 0));
                    return {
                        status: status.slice(0, 150),
                        totalStations: ALL_STATIONS.length,
                        sub100Count: sub100.length,
                        sub100Samples: sub100.slice(0, 5),
                        cp50Count: cp50.length,
                        minPublicKw: minPublicKw
                    };
                })()
                """,
                "awaitPromise": True,
                "returnByValue": True
            })
            r4 = pull_res.get("result", {}).get("value", {})
            print("  Pull Status:", r4.get("status"))
            print("  Total Stations in ALL_STATIONS:", r4.get("totalStations"))
            print("  Public Stations < 100 kW count:", r4.get("sub100Count"))
            print("  ChargePoint < 100 kW count:", r4.get("cp50Count"))
            print("  Minimum Public Station kW:", r4.get("minPublicKw"))

            assert r4.get("sub100Count") == 0, f"Found public stations under 100 kW: {r4.get('sub100Samples')}"
            assert r4.get("cp50Count") == 0, "Found 50 kW ChargePoint stations in database!"
            assert r4.get("minPublicKw", 0) >= 100, f"Minimum public charger kW should be >= 100, got {r4.get('minPublicKw')}"

            # Test 5: Test purge of legacy 50 kW station from localStorage
            print("\n[TEST 5] Testing purge of injected 50 kW station from localStorage...")
            purge_res = await call("Runtime.evaluate", {
                "expression": """
                (() => {
                    // Inject a fake 50 kW ChargePoint station into ALL_STATIONS and localStorage
                    const fake50 = { id: 'fake-cp-50', name: 'ChargePoint - Fake 50kW', network: 'ChargePoint', kw: 50, lat: 40.0, lon: -78.0, on: 0.5, off: 0.5 };
                    ALL_STATIONS.push(fake50);
                    localStorage.setItem('equinox_custom_stations', JSON.stringify([fake50]));

                    // Run purgeBlockedStations()
                    purgeBlockedStations();

                    const inMemory = ALL_STATIONS.find(s => s.id === 'fake-cp-50');
                    const inStorage = JSON.parse(localStorage.getItem('equinox_custom_stations') || '[]');
                    const inStorageFake = inStorage.find(s => s.id === 'fake-cp-50');

                    return {
                        inMemoryGone: !inMemory,
                        inStorageGone: !inStorageFake
                    };
                })()
                """,
                "returnByValue": True
            })
            r5 = purge_res.get("result", {}).get("value", {})
            print("  Fake 50kW purged from in-memory ALL_STATIONS:", r5.get("inMemoryGone"))
            print("  Fake 50kW purged from localStorage:", r5.get("inStorageGone"))

            assert r5.get("inMemoryGone") is True, "purgeBlockedStations() must remove 50 kW station from in-memory ALL_STATIONS!"
            assert r5.get("inStorageGone") is True, "purgeBlockedStations() must remove 50 kW station from localStorage!"

            print("\n" + "=" * 55)
            print("*** ALL BLINK & 100 KW RESTRICTION TESTS PASSED! ***")
            print("=" * 55)

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(run_blink_and_kw_tests())
