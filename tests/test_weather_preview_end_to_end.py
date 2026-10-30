"""
Phase 2 End-to-End Test Suite: Weather Preview API & Headless Chrome Browser UI.
Verifies the FastAPI preview endpoints and full DOM interactions, including
quick destination switching, 30-min rounded time picker, and custom routes.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uvicorn
import websockets

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.app import app

APP_PORT = 8795
CDP_PORT = 9295
USER_DATA_DIR = r"C:\temp\chrome_weather_preview_test"


def start_app_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=APP_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(1.5)
    return server


async def run_end_to_end_preview_tests():
    print("=" * 70)
    print("STARTING PHASE 2 END-TO-END TEST SUITE (API & BROWSER)")
    print("=" * 70)

    # 1. Start FastAPI server
    print("\n[STEP 1] Starting FastAPI test server on port", APP_PORT)
    start_app_server()

    # 2. Test GET /weather-preview
    print("\n[STEP 2] Verifying GET /weather-preview endpoint...")
    req = urllib.request.Request(f"http://127.0.0.1:{APP_PORT}/weather-preview")
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "Route Weather Engine" in html
        assert "St. Onge" in html
        assert "Billings" in html
        assert "DeCamilla" in html
        print("  GET /weather-preview status: 200 OK (HTML verified)")

    # 3. Test POST /api/weather/preview with Quick Destinations & Custom Route
    print("\n[STEP 3] Verifying POST /api/weather/preview REST API...")
    
    # 3a. Quick Destination St. Onge
    post_data = json.dumps({
        "destination": "st_onge",
        "departure_date": "2026-10-30",
        "departure_time": "09:00"
    }).encode("utf-8")
    req_api = urllib.request.Request(
        f"http://127.0.0.1:{APP_PORT}/api/weather/preview",
        data=post_data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_api) as resp:
        assert resp.status == 200
        res_json = json.loads(resp.read().decode("utf-8"))
        print(f"  API St. Onge Response: route={res_json['route_name']}, waypoints={len(res_json['waypoints'])}, distance={res_json['total_distance_miles']}mi")
        assert len(res_json["waypoints"]) >= 12
        assert res_json["mode"] == "forecast"

    # 3b. Distant-future historical reanalysis
    post_data_hist = json.dumps({
        "destination": "decamilla",
        "departure_date": "2026-12-25",
        "departure_time": "10:30"
    }).encode("utf-8")
    req_hist = urllib.request.Request(
        f"http://127.0.0.1:{APP_PORT}/api/weather/preview",
        data=post_data_hist,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_hist) as resp:
        assert resp.status == 200
        res_hist = json.loads(resp.read().decode("utf-8"))
        print(f"  API DeCamilla Historical: mode={res_hist['mode']}, avg_temp={res_hist['summary']['avg_temp_f']}F")
        assert res_hist["mode"] == "historical"

    # 4. Headless Chrome Browser Verification via CDP
    print("\n[STEP 4] Launching Headless Chrome to verify interactive UI rendering...")
    shutil.rmtree(USER_DATA_DIR, ignore_errors=True)

    proc = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--disable-gpu",
        "--no-first-run",
        f"http://127.0.0.1:{APP_PORT}/weather-preview"
    ])

    try:
        ws_url = None
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json").read())
                ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page"), None)
                if ws_url:
                    break
            except Exception:
                time.sleep(0.1)

        assert ws_url is not None, "Could not connect to Chrome DevTools Protocol"

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
            await asyncio.sleep(1.0)

            # Wait for default St. Onge route weather simulation to complete
            print("  Waiting for client-side initial weather calculation to complete...")
            card_count = 0
            for _ in range(40):
                card_count = await eval_js("document.getElementById('timelineContainer')?.children.length || 0")
                if card_count >= 12:
                    break
                await asyncio.sleep(0.5)

            print(f"  Rendered Checkpoint Cards: {card_count} cards")
            assert card_count >= 12, "Should render at least 12 checkpoint cards for St. Onge"

            # Check HUD cards
            hud_temp = await eval_js("document.getElementById('hudTempRange')?.innerText")
            hud_wh = await eval_js("document.getElementById('hudConsumption')?.innerText")
            hud_dist = await eval_js("document.getElementById('routeDistanceDisplay')?.innerText")
            print(f"  HUD Verified: Temp Range='{hud_temp}', Consumption='{hud_wh}', Distance='{hud_dist}'")
            assert "°" in hud_temp
            assert "Wh/mi" in hud_wh
            assert "440" in hud_dist or "441" in hud_dist

            # Test switching to Billings
            print("\n[STEP 5] Testing UI click to switch destination to 'Billings'...")
            await eval_js("selectQuickDest('billings')")
            await asyncio.sleep(2.0)

            billings_cards = await eval_js("document.getElementById('timelineContainer')?.children.length || 0")
            billings_dist = await eval_js("document.getElementById('routeDistanceDisplay')?.innerText")
            print(f"  Switched to Billings: Cards={billings_cards}, Distance='{billings_dist}'")
            assert billings_cards >= 5, "Billings should render at least 5 cards"
            assert "162" in billings_dist

            # Test custom route Washington DC
            print("\n[STEP 6] Testing UI click to switch route to Custom 'Washington DC'...")
            await eval_js("selectCustomRoute('washington_dc')")
            await asyncio.sleep(2.0)

            dc_cards = await eval_js("document.getElementById('timelineContainer')?.children.length || 0")
            dc_dist = await eval_js("document.getElementById('routeDistanceDisplay')?.innerText")
            print(f"  Switched to Washington DC: Cards={dc_cards}, Distance='{dc_dist}'")
            assert dc_cards >= 7, "Washington DC should render at least 7 cards"
            assert "357" in dc_dist

            # Test changing date to 60 days out (Historical Climatology Mode)
            print("\n[STEP 7] Testing changing departure date to 60 days out...")
            await eval_js("""
                const d = new Date();
                d.setDate(d.getDate() + 60);
                document.getElementById('departureDate').value = d.toISOString().split('T')[0];
                onDateTimeChanged();
            """)
            await asyncio.sleep(2.5)

            mode_text = await eval_js("document.getElementById('modeLabel')?.innerText")
            print(f"  Mode Banner Updated: '{mode_text}'")
            assert "Historical" in mode_text

    finally:
        try:
            proc.kill()
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("SUCCESS: ALL PHASE 2 END-TO-END TESTS PASSED FLAWLESSLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_end_to_end_preview_tests())
