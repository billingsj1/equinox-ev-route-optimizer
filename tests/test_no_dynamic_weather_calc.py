import asyncio
import json
import subprocess
import time
import urllib.request
import websockets

CDP_PORT = 9260
USER_DATA_DIR = r"C:\temp\chrome_no_dynamic_test"

def test_no_dynamic_updates():
    print("=" * 80)
    print("VERIFYING ZERO DYNAMIC WEATHER/ROUTE UPDATES ON INPUT CHANGES")
    print("=" * 80)

    # Launch Chrome directly on index.html
    proc = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--disable-gpu",
        "--no-first-run",
        r"c:\Users\joshb\Documents\antigravity\jolly-hopper\index.html"
    ])

    try:
        ws_url = None
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json").read())
                page = next((t for t in tabs if "index.html" in t.get("url", "")), None)
                if page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.1)

        print("Connected to Chrome CDP WebSocket:", ws_url)
        assert ws_url is not None

        async def run_suite():
            async with websockets.connect(ws_url, max_size=None) as ws:
                mid = 0
                async def send(method, params=None):
                    nonlocal mid
                    mid += 1
                    await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
                    return mid

                async def eval_js(expr):
                    m = await send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
                    while True:
                        raw = json.loads(await ws.recv())
                        if raw.get("id") == m:
                            res = raw.get("result", {})
                            if "exceptionDetails" in res:
                                print("JS EXCEPTION:", res["exceptionDetails"])
                            return res.get("result", {}).get("value")

                await send("Page.enable")
                await asyncio.sleep(1.0)

                # 1. Initially calculate St. Onge route once so activeRoutesData and weather cards exist
                print("\n[STEP 1] Running initial calculation for St. Onge...")
                await eval_js("handleSearchRoute()")
                for _ in range(60):
                    await asyncio.sleep(0.3)
                    status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                    if status == "Optimization Complete":
                        break

                init_temp = await eval_js("document.getElementById('rwTempDisplay')?.innerText")
                init_fastest = await eval_js("document.getElementById('fastestTime')?.innerText")
                init_audit = await eval_js("document.getElementById('auditTimestamp')?.innerText")
                print(f"  Initial State: Temp={init_temp} | Time={init_fastest} | Audit={init_audit}")

                # 2. Attach a spy to detect if fetchRouteWeatherData or recomputeCurrentRoute get called
                await eval_js("""
                (() => {
                    window.fetchWeatherCalls = 0;
                    window.recomputeCalls = 0;

                    const origFetch = window.fetchRouteWeatherData;
                    window.fetchRouteWeatherData = async (...args) => {
                        window.fetchWeatherCalls++;
                        return origFetch(...args);
                    };

                    const origRecompute = window.recomputeCurrentRoute;
                    window.recomputeCurrentRoute = async (...args) => {
                        window.recomputeCalls++;
                        return origRecompute(...args);
                    };
                })()
                """)

                # 3. Change Departure Date
                print("\n[STEP 2] Changing Departure Date to a future date...")
                await eval_js("""
                (() => {
                    const dateInput = document.getElementById('departureDate');
                    dateInput.value = '2026-12-25';
                    onDepartureDateTimeChanged();
                })()
                """)
                await asyncio.sleep(0.5)

                calls_after_date = json.loads(await eval_js("""
                (() => {
                    return JSON.stringify({
                        fetchCalls: window.fetchWeatherCalls,
                        recomputeCalls: window.recomputeCalls,
                        tempText: document.getElementById('rwTempDisplay')?.innerText,
                        auditText: document.getElementById('auditTimestamp')?.innerText
                    });
                })()
                """))
                print("  State after date change:", calls_after_date)
                assert calls_after_date["fetchCalls"] == 0, f"Expected 0 fetch calls on date change, got {calls_after_date['fetchCalls']}"
                assert calls_after_date["recomputeCalls"] == 0, f"Expected 0 recompute calls on date change, got {calls_after_date['recomputeCalls']}"
                assert calls_after_date["tempText"] == init_temp, "Weather cards should NOT update on date change!"
                assert calls_after_date["auditText"] == init_audit, "Route optimizer should NOT recompute on date change!"
                print("  [OK] Date change produced ZERO dynamic network calls and ZERO recomputations!")

                # 4. Change Departure Time
                print("\n[STEP 3] Changing Departure Time to 23:30 (11:30 PM)...")
                await eval_js("""
                (() => {
                    const timeInput = document.getElementById('departureTime');
                    timeInput.value = '23:30';
                    updateDepartureTimeDisplay();
                    onDepartureDateTimeChanged();
                })()
                """)
                await asyncio.sleep(0.5)

                calls_after_time = json.loads(await eval_js("""
                (() => {
                    return JSON.stringify({
                        fetchCalls: window.fetchWeatherCalls,
                        recomputeCalls: window.recomputeCalls,
                        tempText: document.getElementById('rwTempDisplay')?.innerText,
                        timeBadge: document.getElementById('departureTimeDisplay')?.innerText
                    });
                })()
                """))
                print("  State after time change:", calls_after_time)
                assert calls_after_time["fetchCalls"] == 0, f"Expected 0 fetch calls on time change, got {calls_after_time['fetchCalls']}"
                assert calls_after_time["recomputeCalls"] == 0, f"Expected 0 recompute calls on time change, got {calls_after_time['recomputeCalls']}"
                assert "11:30 PM" in calls_after_time["timeBadge"], "Display badge should update without lag"
                assert calls_after_time["tempText"] == init_temp, "Weather cards should NOT update on time change!"
                print("  [OK] Time change produced ZERO dynamic network calls and ZERO recomputations!")

                # 5. Toggle Manual Weather Override Checkbox
                print("\n[STEP 4] Toggling Manual Weather Override checkbox...")
                await eval_js("""
                (() => {
                    const chk = document.getElementById('manualWeatherOverride');
                    chk.checked = true;
                    toggleManualWeatherOverride();
                })()
                """)
                await asyncio.sleep(0.5)

                calls_after_override = json.loads(await eval_js("""
                (() => {
                    return JSON.stringify({
                        fetchCalls: window.fetchWeatherCalls,
                        recomputeCalls: window.recomputeCalls,
                        settingsBadge: document.getElementById('weatherEngineModeBadge')?.innerText
                    });
                })()
                """))
                print("  State after override toggle:", calls_after_override)
                assert calls_after_override["fetchCalls"] == 0, "Expected 0 fetch calls on override toggle"
                assert calls_after_override["recomputeCalls"] == 0, "Expected 0 recompute calls on override toggle"
                assert "Manual Override Active" in calls_after_override["settingsBadge"]
                print("  [OK] Override toggle produced ZERO dynamic network calls and ZERO recomputations!")

                # 6. Click Calculate Route Button
                print("\n[STEP 5] Clicking 'Calculate Route' button (Should calculate now)...")
                await eval_js("handleSearchRoute()")
                for _ in range(60):
                    await asyncio.sleep(0.3)
                    status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                    if status == "Optimization Complete":
                        break

                calls_after_calc = json.loads(await eval_js("""
                (() => {
                    return JSON.stringify({
                        fetchCalls: window.fetchWeatherCalls,
                        recomputeCalls: window.recomputeCalls,
                        auditText: document.getElementById('auditTimestamp')?.innerText
                    });
                })()
                """))
                print("  State after Calculate Route clicked:", calls_after_calc)
                assert calls_after_calc["fetchCalls"] >= 1, "Should fetch weather when Calculate Route is clicked!"
                assert calls_after_calc["recomputeCalls"] >= 1, "Should recompute route when Calculate Route is clicked!"
                print("  [OK] Calculations properly executed ONLY upon clicking 'Calculate Route'!")

                print("\n" + "=" * 80)
                print("ALL NO-DYNAMIC-UPDATES TESTS PASSED SUCCESSFULLY!")
                print("=" * 80)

        asyncio.run(run_suite())

    finally:
        proc.terminate()

if __name__ == "__main__":
    test_no_dynamic_updates()
