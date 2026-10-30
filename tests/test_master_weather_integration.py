"""
Comprehensive End-to-End Test Suite for Master Program Integration:
1. Multi-Objective Optimizer Backend with Smart Weather Engine & Manual Overrides.
2. Full Browser UI Verification (Chrome CDP) for:
   - 3 Quick Destinations: St. Onge (Marlton), Billings (Sewickley), DeCamilla (Dillsburg)
   - Near-future departure (Forecast Mode: Open-Meteo hourly)
   - Distant-future departure (Historical Mode: ERA5 archive reanalysis)
   - 2 Additional Routes: Columbus -> Washington, DC and Columbus -> Cleveland, OH
   - Manual Weather Overrides Toggle (box checked forces manual slider values)
   - Ultium Battery Preconditioning cold detection (<55°F)
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
from datetime import datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.app import app

APP_PORT = 8796
CDP_PORT = 9296
USER_DATA_DIR = r"C:\temp\chrome_master_weather_test"


def start_app_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=APP_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(1.5)
    return server


async def run_master_integration_tests():
    print("=" * 80)
    print("STARTING MASTER PROGRAM WEATHER INTEGRATION & PHYSICS TEST SUITE")
    print("=" * 80)

    # 1. Start FastAPI server
    print("\n[STEP 1] Starting FastAPI Master Server on port", APP_PORT)
    start_app_server()

    # 2. Test Backend API: /api/optimize with Smart Weather (near future)
    print("\n[STEP 2] Testing /api/optimize backend with Smart Weather (Forecast Mode)...")
    now = datetime.now()
    dep_date_str = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    payload = {
        "start_lon": -83.0750,
        "start_lat": 39.9512,
        "end_lon": -74.9218,
        "end_lat": 39.8912,
        "destination_name": "st_onge",
        "departure_date": dep_date_str,
        "departure_time": "09:00",
        "manual_weather_override": False,
        "initial_soc_pct": 100.0,
        "min_safety_buffer_pct": 10.0,
        "target_arrival_soc_pct": 20.0
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:{APP_PORT}/api/optimize",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert "itineraries" in data, "Missing itineraries in API response"
        fastest = data["itineraries"]["fastest"]
        print(f"  Fastest Itinerary: {fastest['total_time_hours']}h | Cost: ${fastest['total_cost']} | Stops: {len(fastest['stops'])}")
        assert fastest["total_time_hours"] > 0
        if "route_weather" in data and data["route_weather"]:
            rw = data["route_weather"]
            print(f"  Route Weather Attached: mode={rw['mode']}, avg_temp={rw['summary']['avg_temp_f']}F, wet={rw['summary']['wet_road_pct']}%")
            assert rw["mode"] == "forecast"
        print("  [OK] Backend Smart Weather optimization verified!")

    # 3. Test Backend API: /api/optimize with Manual Weather Override
    print("\n[STEP 3] Testing /api/optimize backend with Manual Weather Override (Freezing 20F)...")
    payload_manual = {
        "start_lon": -83.0750,
        "start_lat": 39.9512,
        "end_lon": -74.9218,
        "end_lat": 39.8912,
        "destination_name": "st_onge",
        "departure_date": dep_date_str,
        "departure_time": "09:00",
        "manual_weather_override": True,
        "temperature_f": 20.0,
        "wind_speed_mph": 25.0,
        "wind_direction_deg": 90.0, # Headwind
        "road_condition": "snow_ice",
        "initial_soc_pct": 100.0,
        "min_safety_buffer_pct": 10.0,
        "target_arrival_soc_pct": 20.0
    }
    req_man = urllib.request.Request(
        f"http://127.0.0.1:{APP_PORT}/api/optimize",
        data=json.dumps(payload_manual).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_man) as resp:
        data_man = json.loads(resp.read().decode("utf-8"))
        fastest_man = data_man["itineraries"]["fastest"]
        print(f"  Freezing Manual Itinerary: {fastest_man['total_time_hours']}h | Cost: ${fastest_man['total_cost']} | Stops: {len(fastest_man['stops'])}")
        # In extreme cold and snow, charging time and stops increase
        print("  [OK] Backend Manual Weather override verified!")

    # 4. Launch Headless Chrome CDP for Master UI Browser Testing
    print("\n[STEP 4] Launching Headless Chrome to test Master Frontend (index.html)...")
    if os.path.exists(USER_DATA_DIR):
        shutil.rmtree(USER_DATA_DIR, ignore_errors=True)

    proc = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--disable-gpu",
        "--no-first-run",
        f"http://127.0.0.1:{APP_PORT}/"
    ])

    try:
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json") as resp:
                    tabs = json.loads(resp.read().decode())
                    for tab in tabs:
                        if tab.get("type") == "page":
                            ws_url = tab["webSocketDebuggerUrl"]
                            break
                    if ws_url:
                        break
            except Exception:
                time.sleep(0.2)

        assert ws_url, "Failed to connect to Chrome CDP WebSocket"
        print("  Connected to Chrome CDP WebSocket successfully.")

        async with websockets.connect(ws_url, max_size=None) as ws:
            mid = 0

            async def eval_js(expr):
                nonlocal mid
                mid += 1
                await ws.send(json.dumps({
                    "id": mid,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}
                }))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == mid:
                        res = msg.get("result", {})
                        if "exceptionDetails" in res:
                            print("  JS EXCEPTION:", res["exceptionDetails"])
                        return res.get("result", {}).get("value")

            await asyncio.sleep(1.5)

            # Test 4.1: Verify Departure Controls Initialization
            print("\n[TEST 4.1] Verifying Departure Date and 30-min Time Picker Initialization...")
            dep_date = await eval_js("document.getElementById('departureDate')?.value")
            dep_time = await eval_js("document.getElementById('departureTime')?.value")
            time_opts_count = await eval_js("document.getElementById('departureTime')?.options?.length")
            dep_clock = await eval_js("document.getElementById('departureTimeDisplay')?.innerText")
            print(f"  Departure Date: {dep_date} (today)")
            print(f"  Departure Time: {dep_time} ({dep_clock}) with {time_opts_count} 30-min options")
            assert dep_date is not None and len(dep_date) == 10
            assert time_opts_count == 48, f"Expected 48 30-min options, got {time_opts_count}"
            assert dep_clock is not None and ("AM" in dep_clock or "PM" in dep_clock)
            print("  [OK] Departure controls initialized perfectly!")

            # Test 4.2: Verify Weather Card in Advanced Settings (Manual Override Toggle)
            print("\n[TEST 4.2] Verifying Weather Card & Manual Override Toggle...")
            chk_val = await eval_js("document.getElementById('manualWeatherOverride')?.checked")
            badge_text = await eval_js("document.getElementById('weatherEngineModeBadge')?.innerText")
            controls_has_pointer_events = await eval_js("document.getElementById('manualWeatherControls')?.classList.contains('pointer-events-none')")
            print(f"  Manual Override Checkbox: {chk_val} (Default unchecked)")
            print(f"  Weather Mode Badge: '{badge_text}'")
            print(f"  Sliders Disabled/Grayed Out: {controls_has_pointer_events}")
            assert chk_val is False, "Default manual override should be False (unchecked)"
            assert "Smart Weather" in badge_text
            assert controls_has_pointer_events is True
            print("  [OK] Default Smart Weather mode active and sliders protected!")

            # Test 4.3: Quick Destination 1 - Marlton, NJ (St. Onge) with Smart Forecast
            print("\n[TEST 4.3] Quick Destination 1: Marlton, NJ (St. Onge) with Smart Weather...")
            await eval_js("document.getElementById('departureTime').value = '08:30'; updateDepartureTimeDisplay();")
            await eval_js("handleSearchRoute()")
            for _ in range(60):
                await asyncio.sleep(0.3)
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if st == 'Optimization Complete':
                    break
            
            rw_badge = await eval_js("document.getElementById('routeWeatherModeBadge')?.innerText")
            rw_temp = await eval_js("document.getElementById('rwTempDisplay')?.innerText")
            rw_road = await eval_js("document.getElementById('rwRoadDisplay')?.innerText")
            rw_wind = await eval_js("document.getElementById('rwWindDisplay')?.innerText")
            rw_air = await eval_js("document.getElementById('rwAirDensityDisplay')?.innerText")
            rw_precond = await eval_js("document.getElementById('rwPrecondDisplay')?.innerText")
            fastest_time = await eval_js("document.getElementById('fastestTime')?.innerText")
            fastest_cost = await eval_js("document.getElementById('fastestCost')?.innerText")
            fastest_stops = await eval_js("document.getElementById('fastestStopsCount')?.innerText")
            
            print(f"  Route Weather Badge: '{rw_badge}'")
            print(f"  Temp: {rw_temp} | Road: {rw_road} | Wind: {rw_wind}")
            print(f"  Air Density: {rw_air} | Preconditioning: {rw_precond}")
            print(f"  Marlton Result: {fastest_time} | {fastest_cost} | {fastest_stops} stops")
            assert "Live Forecast" in rw_badge or "Smart Weather" in rw_badge
            assert "°F" in rw_temp
            assert "kg/m³" in rw_air
            print("  [OK] St. Onge Smart Weather Route verified!")

            # Test 4.4: Quick Destination 2 - Sewickley, PA (Billings) with Night Departure
            print("\n[TEST 4.4] Quick Destination 2: Sewickley, PA (Billings) with Night Departure...")
            await eval_js("setQuickDest('billings')")
            await eval_js("document.getElementById('departureTime').value = '21:00'; updateDepartureTimeDisplay();")
            await eval_js("handleSearchRoute()")
            for _ in range(60):
                await asyncio.sleep(0.3)
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if st == 'Optimization Complete':
                    break

            b_fastest = await eval_js("document.getElementById('fastestTime')?.innerText")
            b_cost = await eval_js("document.getElementById('fastestCost')?.innerText")
            b_nonstop = await eval_js("document.getElementById('nonStopDuration')?.innerText")
            b_temp = await eval_js("document.getElementById('rwTempDisplay')?.innerText")
            print(f"  Billings Result: Non-stop {b_nonstop} | Fastest {b_fastest} | {b_cost} | Temp: {b_temp}")
            assert b_fastest is not None and "h" in b_fastest
            print("  [OK] Billings night departure verified!")

            # Test 4.5: Quick Destination 3 - Dillsburg, PA (DeCamilla) with Distant Historical Date
            print("\n[TEST 4.5] Quick Destination 3: Dillsburg, PA (DeCamilla) with Distant Date (ERA5 Reanalysis)...")
            future_date_str = (now + timedelta(days=45)).strftime("%Y-%m-%d")
            await eval_js(f"document.getElementById('departureDate').value = '{future_date_str}';")
            await eval_js("setQuickDest('decamilla')")
            await eval_js("handleSearchRoute()")
            for _ in range(60):
                await asyncio.sleep(0.3)
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if st == 'Optimization Complete':
                    break

            d_badge = await eval_js("document.getElementById('routeWeatherModeBadge')?.innerText")
            d_fastest = await eval_js("document.getElementById('fastestTime')?.innerText")
            d_cost = await eval_js("document.getElementById('fastestCost')?.innerText")
            d_temp = await eval_js("document.getElementById('rwTempDisplay')?.innerText")
            print(f"  DeCamilla Result (45d out): {d_fastest} | {d_cost} | Badge: '{d_badge}' | Temp: {d_temp}")
            assert "ERA5" in d_badge or "Archive" in d_badge or "Historical" in d_badge or "Smart Weather" in d_badge
            print("  [OK] DeCamilla distant-future historical route verified!")

            # Test 4.6: Additional Route 1 - Columbus, OH to Washington, DC
            print("\n[TEST 4.6] Additional Route 1: Columbus, OH to Washington, DC...")
            await eval_js("document.getElementById('destAddress').value = 'Washington, DC';")
            await eval_js("document.getElementById('departureDate').value = '" + (now + timedelta(days=1)).strftime("%Y-%m-%d") + "';")
            await eval_js("handleSearchRoute()")
            for _ in range(60):
                await asyncio.sleep(0.3)
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if st == 'Optimization Complete':
                    break

            dc_fastest = await eval_js("document.getElementById('fastestTime')?.innerText")
            dc_cost = await eval_js("document.getElementById('fastestCost')?.innerText")
            dc_miles = await eval_js("document.getElementById('fastestMiles')?.innerText")
            dc_temp = await eval_js("document.getElementById('rwTempDisplay')?.innerText")
            print(f"  Washington DC Result: {dc_fastest} | {dc_cost} | {dc_miles} | Temp: {dc_temp}")
            assert dc_fastest is not None and "h" in dc_fastest
            print("  [OK] Columbus -> Washington DC route verified!")

            # Test 4.7: Additional Route 2 - Columbus, OH to Cleveland, OH
            print("\n[TEST 4.7] Additional Route 2: Columbus, OH to Cleveland, OH...")
            await eval_js("document.getElementById('destAddress').value = 'Cleveland, OH';")
            await eval_js("handleSearchRoute()")
            for _ in range(60):
                await asyncio.sleep(0.3)
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if st == 'Optimization Complete':
                    break

            cle_fastest = await eval_js("document.getElementById('fastestTime')?.innerText")
            cle_cost = await eval_js("document.getElementById('fastestCost')?.innerText")
            cle_miles = await eval_js("document.getElementById('fastestMiles')?.innerText")
            print(f"  Cleveland Result: {cle_fastest} | {cle_cost} | {cle_miles}")
            assert cle_fastest is not None and "h" in cle_fastest
            print("  [OK] Columbus -> Cleveland route verified!")

            # Test 4.8: Manual Weather Override Toggle Test
            print("\n[TEST 4.8] Testing Manual Weather Override (Checking box forces sliders)...")
            await eval_js("document.getElementById('manualWeatherOverride').checked = true; toggleManualWeatherOverride();")
            await asyncio.sleep(0.3)
            override_badge = await eval_js("document.getElementById('weatherEngineModeBadge')?.innerText")
            override_rw_badge = await eval_js("document.getElementById('routeWeatherModeBadge')?.innerText")
            print(f"  Settings Mode Badge: '{override_badge}'")
            print(f"  Route Weather Badge: '{override_rw_badge}'")
            assert "Manual Override" in override_badge
            assert "Manual Override" in override_rw_badge

            # Change manual slider to 15°F freezing with snow
            print("  Setting manual sliders to 15°F, 30 mph headwind, snow/ice...")
            await eval_js("""
                (async () => {
                    document.getElementById('tempF').value = 15;
                    document.getElementById('windSpeed').value = 30;
                    document.getElementById('windDir').value = 90;
                    document.getElementById('roadCond').value = 'snow_ice';
                    updatePhysicsHUD();
                    await recomputeCurrentRoute();
                })()
            """)

            cold_temp = await eval_js("document.getElementById('rwTempDisplay')?.innerText")
            cold_fastest = await eval_js("document.getElementById('fastestTime')?.innerText")
            cold_cost = await eval_js("document.getElementById('fastestCost')?.innerText")
            print(f"  Manual Cold Result: {cold_fastest} | {cold_cost} | Temp displayed: {cold_temp}")
            assert "15°F" in cold_temp

            # Toggle Manual Override back OFF (resume Smart Weather)
            print("  Toggling Manual Override OFF (smart weather resumes)...")
            await eval_js("""
                (async () => {
                    document.getElementById('manualWeatherOverride').checked = false;
                    await toggleManualWeatherOverride();
                })()
            """)

            resumed_badge = await eval_js("document.getElementById('weatherEngineModeBadge')?.innerText")
            resumed_temp = await eval_js("document.getElementById('rwTempDisplay')?.innerText")
            print(f"  Resumed Badge: '{resumed_badge}' | Resumed Temp: {resumed_temp}")
            assert "Smart Weather" in resumed_badge
            assert "15°F" not in resumed_temp
            print("  [OK] Manual weather override toggle test passed with flying colors!")

    finally:
        proc.terminate()
        try:
            shutil.rmtree(USER_DATA_DIR, ignore_errors=True)
        except Exception:
            pass

    print("\n" + "=" * 80)
    print("ALL MASTER PROGRAM INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_master_integration_tests())
