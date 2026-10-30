import asyncio
import base64
import json
import subprocess
import time
import urllib.request
import websockets

CDP_PORT = 9256

def test_preview_ui():
    print("=" * 80)
    print("TESTING WEATHER PREVIEW UI - MAP VISIBILITY, ANIMATIONS & MANUAL TRIGGER")
    print("=" * 80)

    proc = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        "--window-size=1280,1024",
        "--disable-gpu",
        "--no-first-run",
        r"c:\Users\joshb\Documents\antigravity\jolly-hopper\weather_preview.html"
    ])

    try:
        ws_url = None
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json").read())
                page = next((t for t in tabs if "weather_preview.html" in t.get("url", "")), None)
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
                    m = await send("Runtime.evaluate", {"expression": expr, "awaitPromise": True})
                    while True:
                        raw = json.loads(await ws.recv())
                        if raw.get("id") == m:
                            res = raw.get("result", {})
                            if "exceptionDetails" in res:
                                print("JS EXCEPTION:", res["exceptionDetails"])
                            return res.get("result", {}).get("value")

                await send("Page.enable")
                await asyncio.sleep(2.0)

                # ============================================================
                # TEST 1: Initial Page Load State
                # ============================================================
                print("\n[TEST 1] Verifying Initial Page Load...")
                init_state = json.loads(await eval_js("""
                (() => {
                    const mapEl = document.getElementById('routeMap');
                    const tiles = Array.from(document.querySelectorAll('.leaflet-tile')).map(t => t.src);
                    const btn = document.getElementById('btnCalculate');
                    const btnText = document.getElementById('btnCalcText')?.innerText;
                    const isSpinning = document.getElementById('btnCalcIcon')?.classList.contains('animate-spin');
                    const hudTemp = document.getElementById('hudTempRange')?.innerText;
                    const timelineText = document.getElementById('timelineContainer')?.innerText;
                    const distanceText = document.getElementById('routeDistanceDisplay')?.innerText;
                    const polylines = Array.from(document.querySelectorAll('.leaflet-overlay-pane path')).length;
                    const markerLayersCount = typeof markerLayers !== 'undefined' ? markerLayers.length : 0;

                    return JSON.stringify({
                        mapExists: !!mapEl,
                        mapRect: mapEl ? {w: mapEl.offsetWidth, h: mapEl.offsetHeight} : null,
                        tilesCount: tiles.length,
                        sampleTile: tiles[0] || null,
                        btnDisabled: btn ? btn.disabled : null,
                        btnText,
                        isSpinning,
                        hudTemp,
                        distanceText,
                        polylines,
                        markerLayersCount,
                        hasPrompt: timelineText && timelineText.includes("Calculate Route Weather")
                    });
                })()
                """))
                print("Initial State:", init_state)

                # 1. Map is visible and sized properly
                assert init_state["mapExists"] is True, "Map element missing"
                assert init_state["mapRect"]["h"] >= 400, f"Map height too small: {init_state['mapRect']}"
                assert init_state["mapRect"]["w"] > 500, f"Map width too small: {init_state['mapRect']}"
                assert init_state["tilesCount"] > 0, "No tiles rendered on map"
                assert "tile.openstreetmap.org" in init_state["sampleTile"], f"Expected OpenStreetMap tile, got: {init_state['sampleTile']}"
                assert init_state["polylines"] > 0, "Route corridor polyline should be rendered on map initially"
                assert init_state["markerLayersCount"] > 0, "Milestone markers should be rendered on map initially"
                print("  [OK] Map is fully visible with OpenStreetMap tiles, route line, and milestone markers!")

                # 2. Button is NOT animating or spinning before being pressed
                assert init_state["btnText"] == "Calculate Route Weather", f"Unexpected button text: {init_state['btnText']}"
                assert init_state["isSpinning"] is False, "Calculate button should NOT be spinning before being pressed!"
                assert init_state["btnDisabled"] is False, "Calculate button should NOT be disabled initially"
                print("  [OK] Calculate button is idle and NOT animating before being pressed!")

                # 3. No auto-recalculation has run
                assert init_state["hudTemp"] == "--°F", f"HUD temp should be placeholder --°F, got: {init_state['hudTemp']}"
                assert init_state["hasPrompt"] is True, "Timeline should display instruction prompt"
                print("  [OK] Initial state has NOT auto-recalculated!")

                # Capture initial screenshot
                shot1 = await send("Page.captureScreenshot")
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == shot1:
                        with open("preview_loaded_idle.png", "wb") as f:
                            f.write(base64.b64decode(m["result"]["data"]))
                        print("  [Saved] preview_loaded_idle.png")
                        break

                # ============================================================
                # TEST 2: Changing Departure Date Does NOT Auto-Recalculate
                # ============================================================
                print("\n[TEST 2] Testing Departure Date Change (Date: 2026-12-15)...")
                await eval_js("""
                (() => {
                    const dateEl = document.getElementById('departureDate');
                    dateEl.value = '2026-12-15';
                    onDateTimeChanged();
                })()
                """)
                await asyncio.sleep(0.5)

                date_change_state = json.loads(await eval_js("""
                (() => {
                    const badgeText = document.getElementById('modeBadge')?.innerText;
                    const isSpinning = document.getElementById('btnCalcIcon')?.classList.contains('animate-spin');
                    const hudTemp = document.getElementById('hudTempRange')?.innerText;
                    return JSON.stringify({ badgeText, isSpinning, hudTemp });
                })()
                """))
                print("Date Change State:", date_change_state)
                assert "ERA5" in date_change_state["badgeText"], "Mode badge should update to ERA5"
                assert date_change_state["isSpinning"] is False, "Button must NOT spin on date change"
                assert date_change_state["hudTemp"] == "--°F", "Must NOT auto-recalculate on date change"
                print("  [OK] Date change updated mode horizon without auto-recalculating!")

                # ============================================================
                # TEST 3: Switching Destination Corridors Does NOT Auto-Recalculate
                # ============================================================
                print("\n[TEST 3] Testing Quick Destination Selection (Billings & DeCamilla)...")
                await eval_js("selectQuickDest('billings')")
                await asyncio.sleep(0.5)

                billings_state = json.loads(await eval_js("""
                (() => {
                    const distanceText = document.getElementById('routeDistanceDisplay')?.innerText;
                    const isSpinning = document.getElementById('btnCalcIcon')?.classList.contains('animate-spin');
                    const hudTemp = document.getElementById('hudTempRange')?.innerText;
                    return JSON.stringify({ distanceText, isSpinning, hudTemp });
                })()
                """))
                print("Billings Preview State:", billings_state)
                assert "162 miles" in billings_state["distanceText"], "Distance should update to 162 miles"
                assert billings_state["isSpinning"] is False, "Button must NOT spin on destination selection"
                assert billings_state["hudTemp"] == "--°F", "Must NOT auto-recalculate on destination selection"
                print("  [OK] Billings selected, map updated, NO auto-recalculation!")

                await eval_js("selectQuickDest('decamilla')")
                await asyncio.sleep(0.5)

                decamilla_state = json.loads(await eval_js("""
                (() => {
                    const distanceText = document.getElementById('routeDistanceDisplay')?.innerText;
                    const isSpinning = document.getElementById('btnCalcIcon')?.classList.contains('animate-spin');
                    const hudTemp = document.getElementById('hudTempRange')?.innerText;
                    return JSON.stringify({ distanceText, isSpinning, hudTemp });
                })()
                """))
                print("DeCamilla Preview State:", decamilla_state)
                assert "328 miles" in decamilla_state["distanceText"], "Distance should update to 328 miles"
                assert decamilla_state["isSpinning"] is False, "Button must NOT spin on destination selection"
                assert decamilla_state["hudTemp"] == "--°F", "Must NOT auto-recalculate on destination selection"
                print("  [OK] DeCamilla selected, map updated, NO auto-recalculation!")

                # ============================================================
                # TEST 4: Clicking 'Calculate Route Weather' Runs Calculation
                # ============================================================
                print("\n[TEST 4] Clicking 'Calculate Route Weather' Button...")
                # Reset to today and St. Onge for standard simulation
                await eval_js("""
                (() => {
                    const now = new Date();
                    const yyyy = now.getFullYear();
                    const mm = String(now.getMonth() + 1).padStart(2, '0');
                    const dd = String(now.getDate()).padStart(2, '0');
                    document.getElementById('departureDate').value = `${yyyy}-${mm}-${dd}`;
                    onDateTimeChanged();
                    selectQuickDest('st_onge');
                })()
                """)
                await asyncio.sleep(0.3)

                # Trigger calculation via clicking the button
                calc_task = asyncio.create_task(eval_js("document.getElementById('btnCalculate').click()"))
                await asyncio.sleep(0.15)

                # Check that button IS animating now that it was pressed
                active_calc_state = json.loads(await eval_js("""
                (() => {
                    const btn = document.getElementById('btnCalculate');
                    const btnText = document.getElementById('btnCalcText')?.innerText;
                    const isSpinning = document.getElementById('btnCalcIcon')?.classList.contains('animate-spin');
                    return JSON.stringify({
                        btnDisabled: btn ? btn.disabled : null,
                        btnText,
                        isSpinning
                    });
                })()
                """))
                print("Active Calculating State:", active_calc_state)
                assert active_calc_state["isSpinning"] is True, "Button MUST animate with spin AFTER being pressed!"
                assert active_calc_state["btnDisabled"] is True, "Button should be disabled during calculation"
                print("  [OK] Calculate button successfully entered animated calculation state!")

                # Wait for calculation to finish
                await calc_task
                await asyncio.sleep(2.0)

                # Verify completion state
                completed_state = json.loads(await eval_js("""
                (() => {
                    const btn = document.getElementById('btnCalculate');
                    const btnText = document.getElementById('btnCalcText')?.innerText;
                    const isSpinning = document.getElementById('btnCalcIcon')?.classList.contains('animate-spin');
                    const hudTemp = document.getElementById('hudTempRange')?.innerText;
                    const hudWh = document.getElementById('hudConsumption')?.innerText;
                    const cardCount = document.querySelectorAll('#timelineContainer > div').length;
                    return JSON.stringify({
                        btnDisabled: btn ? btn.disabled : null,
                        btnText,
                        isSpinning,
                        hudTemp,
                        hudWh,
                        cardCount
                    });
                })()
                """))
                print("Completed State:", completed_state)
                assert completed_state["isSpinning"] is False, "Button must stop spinning after completion"
                assert completed_state["btnDisabled"] is False, "Button must be re-enabled after completion"
                assert completed_state["hudTemp"] != "--°F", f"HUD temp should now have real weather, got: {completed_state['hudTemp']}"
                assert "Wh/mi" in completed_state["hudWh"], f"HUD consumption should be displayed, got: {completed_state['hudWh']}"
                assert completed_state["cardCount"] == 13, f"Expected 13 checkpoint cards for St. Onge, got {completed_state['cardCount']}"
                print("  [OK] Calculation completed successfully with 13 regional weather checkpoints!")

                # Capture completed screenshot
                shot2 = await send("Page.captureScreenshot")
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == shot2:
                        with open("preview_calculated.png", "wb") as f:
                            f.write(base64.b64decode(m["result"]["data"]))
                        print("  [Saved] preview_calculated.png")
                        break

                print("\n" + "=" * 80)
                print("ALL WEATHER PREVIEW UI TESTS PASSED SUCCESSFULLY!")
                print("=" * 80)

        asyncio.run(run_suite())

    finally:
        proc.terminate()

if __name__ == "__main__":
    test_preview_ui()
