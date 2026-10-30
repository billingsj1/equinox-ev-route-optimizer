"""
Comprehensive Test Suite for Weather Engine (Phase 1).
Tests quick destinations (St. Onge, Billings, DeCamilla), custom non-quick routes
(Columbus to Washington DC, Columbus to Cleveland), near-future forecasts,
distant-future ERA5 historical reanalysis, air density elevation effects,
wind aerodynamics, and pavement drying state machine.
"""

import asyncio
from datetime import datetime, timedelta
import sys
import os

# Configure UTF-8 safe output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.weather_engine import WeatherEngine, WaypointWeather, RouteWeatherReport


async def test_all_scenarios():
    print("=" * 70)
    print("STARTING WEATHER ENGINE PHASE 1 TEST SUITE")
    print("=" * 70)

    engine = WeatherEngine()

    # -------------------------------------------------------------------------
    # TEST 1: Quick Destination 1 - St. Onge (Marlton, NJ) - Near Future
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Testing St. Onge (Marlton, NJ) - Departure Tomorrow at 08:30 AM...")
    tomorrow = datetime.now() + timedelta(days=1)
    dep_t1 = tomorrow.replace(hour=8, minute=30, second=0, microsecond=0)

    rep1 = await engine.get_route_weather_report("st_onge", dep_t1)

    print(f"  Route: {rep1.route_name}")
    print(f"  Mode: {rep1.mode.upper()} | Distance: {rep1.total_distance_miles} mi | Duration: {rep1.total_duration_hours} hrs")
    print(f"  Waypoints: {len(rep1.waypoints)} checkpoints")
    print(f"  Temps: min={rep1.summary['min_temp_f']} F, max={rep1.summary['max_temp_f']} F, avg={rep1.summary['avg_temp_f']} F")
    print(f"  Wind: max headwind={rep1.summary['max_headwind_mph']} mph, max tailwind={rep1.summary['max_tailwind_mph']} mph")
    print(f"  Road Conditions: wet={rep1.summary['wet_road_pct']}%, snow/ice={rep1.summary['snow_ice_road_pct']}%")
    print(f"  Energy Consumption: {rep1.summary['avg_consumption_wh_per_mi']} Wh/mi vs {rep1.summary['baseline_avg_wh_per_mi']} Wh/mi (70 F dry base)")
    print(f"  Trip Energy Delta: {rep1.summary['energy_delta_kwh']} kWh ({rep1.summary['energy_delta_pct']}%)")

    assert len(rep1.waypoints) >= 12, "St. Onge should have at least 12 waypoints"
    assert rep1.total_distance_miles > 400.0, "St. Onge distance should be >400 miles"
    assert rep1.mode == "forecast", "Tomorrow should be in forecast mode"

    # Verify Somerset crest elevation & pressure
    somerset_wp = next((w for w in rep1.waypoints if "Somerset" in w.name), None)
    assert somerset_wp is not None, "Somerset waypoint must be present"
    print(f"  Somerset Crest Check: elev={somerset_wp.elevation_ft}ft, pressure={somerset_wp.surface_pressure_hpa}hPa, rho={somerset_wp.air_density_kg_m3}kg/m3")
    assert somerset_wp.elevation_ft > 2000.0, "Somerset elevation should be >2000 ft"
    assert somerset_wp.surface_pressure_hpa < 970.0, "Somerset surface pressure must be lower than sea level (<970 hPa)"

    # -------------------------------------------------------------------------
    # TEST 2: Quick Destination 2 - Billings (Sewickley, PA) - Near Future
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Testing Billings (Sewickley, PA) - Departure in 3 days at 02:00 PM...")
    dep_t2 = (datetime.now() + timedelta(days=3)).replace(hour=14, minute=0, second=0, microsecond=0)

    rep2 = await engine.get_route_weather_report("billings", dep_t2)

    print(f"  Route: {rep2.route_name}")
    print(f"  Mode: {rep2.mode.upper()} | Distance: {rep2.total_distance_miles} mi | Duration: {rep2.total_duration_hours} hrs")
    print(f"  Avg Temp: {rep2.summary['avg_temp_f']} F | Consumption: {rep2.summary['avg_consumption_wh_per_mi']} Wh/mi")
    assert rep2.total_distance_miles > 160.0 and rep2.total_distance_miles < 210.0, "Billings distance should be ~180 miles"
    assert rep2.mode == "forecast"

    # -------------------------------------------------------------------------
    # TEST 3: Quick Destination 3 - DeCamilla (Dillsburg, PA) - Distant Future (>16 Days)
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Testing DeCamilla (Dillsburg, PA) - Departure in 60 days (Historical Mode)...")
    dep_t3 = (datetime.now() + timedelta(days=60)).replace(hour=9, minute=0, second=0, microsecond=0)

    rep3 = await engine.get_route_weather_report("decamilla", dep_t3)

    print(f"  Route: {rep3.route_name}")
    print(f"  Mode: {rep3.mode.upper()} (ERA5 Climatology) | Distance: {rep3.total_distance_miles} mi")
    print(f"  Avg Temp: {rep3.summary['avg_temp_f']} F | Max Headwind: {rep3.summary['max_headwind_mph']} mph")
    print(f"  Historical Reanalysis Description Sample: {rep3.waypoints[3].weather_description}")
    assert rep3.mode == "historical", "Departure > 16 days out must trigger historical reanalysis mode"
    assert len(rep3.waypoints) >= 9, "DeCamilla should have at least 9 waypoints"

    # -------------------------------------------------------------------------
    # TEST 4: Custom Non-Quick Route 1 - Columbus, OH to Washington, DC
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Testing Custom Non-Quick Route 1: Columbus OH to Washington DC (via I-70/I-270)...")
    coords_dc = [
        [-83.0750, 39.9512, 230.0], # Columbus West High
        [-82.0130, 39.9400, 215.0], # Zanesville
        [-80.7200, 40.0630, 205.0], # Wheeling WV
        [-79.9559, 39.6295, 290.0], # Morgantown WV
        [-78.9284, 39.6582, 640.0], # Frostburg MD (Big Savage Mtn, 2100 ft)
        [-78.7625, 39.6529, 210.0], # Cumberland MD
        [-77.7200, 39.6418, 170.0], # Hagerstown MD
        [-77.4105, 39.4143, 90.0],  # Frederick MD
        [-77.0369, 38.9072, 20.0]   # Washington DC
    ]
    rep4 = await engine.get_route_weather_report(
        destination_key_or_name="Washington DC",
        departure_dt=dep_t1,
        custom_coordinates=coords_dc,
        origin_name="West High School (Columbus, OH)",
        destination_name="Washington, DC"
    )

    print(f"  Route: {rep4.route_name}")
    print(f"  Distance: {rep4.total_distance_miles} mi | Duration: {rep4.total_duration_hours} hrs")
    print(f"  Waypoints sliced: {len(rep4.waypoints)} checkpoints")
    assert rep4.total_distance_miles > 350.0, "Columbus to DC should be >350 miles"
    assert rep4.route_id == "custom_route"

    # -------------------------------------------------------------------------
    # TEST 5: Custom Non-Quick Route 2 - Columbus, OH to Cleveland, OH (Lake-Effect Corridor)
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Testing Custom Non-Quick Route 2: Columbus OH to Cleveland OH (via I-71 N)...")
    coords_cle = [
        [-83.0750, 39.9512, 230.0], # Columbus West High
        [-82.8000, 40.3500, 340.0], # Delaware / Mount Gilead
        [-82.5180, 40.7580, 380.0], # Mansfield
        [-82.0000, 41.0800, 320.0], # Medina
        [-81.6944, 41.4993, 200.0]  # Cleveland Public Square
    ]
    rep5 = await engine.get_route_weather_report(
        destination_key_or_name="Cleveland",
        departure_dt=dep_t1,
        custom_coordinates=coords_cle,
        origin_name="West High School (Columbus, OH)",
        destination_name="Cleveland, OH"
    )

    print(f"  Route: {rep5.route_name}")
    print(f"  Distance: {rep5.total_distance_miles} mi | Duration: {rep5.total_duration_hours} hrs")
    print(f"  Waypoints sliced: {len(rep5.waypoints)} checkpoints")
    assert rep5.total_distance_miles > 120.0 and rep5.total_distance_miles < 160.0

    # -------------------------------------------------------------------------
    # TEST 6: Physical Mechanics & Aerodynamic Logic Verifications
    # -------------------------------------------------------------------------
    print("\n[TEST 6] Validating Physical Mechanics...")
    
    # 6a. Tailwind vs Headwind
    hw_15, _, cat_hw = engine.calculate_vector_wind(segment_bearing_deg=90.0, wind_speed_mph=15.0, wind_direction_deg=90.0)
    tw_15, _, cat_tw = engine.calculate_vector_wind(segment_bearing_deg=90.0, wind_speed_mph=15.0, wind_direction_deg=270.0)
    print(f"  Wind Heading East (90 deg): Wind from East -> headwind={hw_15} mph ({cat_hw})")
    print(f"  Wind Heading East (90 deg): Wind from West -> headwind={tw_15} mph ({cat_tw})")
    assert hw_15 == 15.0 and cat_hw == "headwind", "East wind while driving East must be headwind"
    assert tw_15 == -15.0 and cat_tw == "tailwind", "West wind while driving East must be tailwind"

    # Energy with tailwind vs headwind
    wh_hw, _, _, _, _ = engine.calculate_segment_physics(
        distance_miles=30.0, speed_limit_mph=70.0, bearing_deg=90.0, elev_change_m=0.0,
        temp_f=70.0, wind_speed_mph=15.0, wind_dir_deg=90.0, surface_pressure_hpa=1013.25, humidity_pct=50.0, crr=0.0095
    )
    wh_tw, _, _, _, _ = engine.calculate_segment_physics(
        distance_miles=30.0, speed_limit_mph=70.0, bearing_deg=90.0, elev_change_m=0.0,
        temp_f=70.0, wind_speed_mph=15.0, wind_dir_deg=270.0, surface_pressure_hpa=1013.25, humidity_pct=50.0, crr=0.0095
    )
    print(f"  Consumption with 15mph Headwind: {wh_hw} Wh/mi | with 15mph Tailwind: {wh_tw} Wh/mi")
    assert wh_hw > wh_tw, "Headwind must consume more energy than tailwind"
    tailwind_saving_pct = round(((wh_hw - wh_tw) / wh_hw) * 100.0, 1)
    print(f"  Tailwind savings: {tailwind_saving_pct}% less energy!")
    assert tailwind_saving_pct > 15.0, "Tailwind must reduce consumption significantly"

    # 6b. Elevation Air Density Effect at identical temperature
    rho_sealevel, _ = engine.calculate_moist_air_density(temp_f=60.0, surface_pressure_hpa=1013.25, relative_humidity_pct=50.0)
    rho_mountain, _ = engine.calculate_moist_air_density(temp_f=60.0, surface_pressure_hpa=935.0, relative_humidity_pct=50.0)
    print(f"  Air Density at Sea Level (1013 hPa): {rho_sealevel} kg/m3 | Mountain (935 hPa): {rho_mountain} kg/m3")
    assert rho_mountain < rho_sealevel, "Mountain air density must be thinner than sea level"

    # 6c. Pavement Drying State Machine
    # Case 1: Actively raining moderate
    cond1, wet1, crr1 = engine.evaluate_road_moisture_and_drying(
        current_precip_in_hr=0.10, past_precip_1h_in=0.10, past_precip_2h_in=0.05,
        weather_code=63, temp_f=65.0, humidity_pct=80.0, wind_speed_mph=10.0, is_day=True
    )
    assert cond1 == "wet" and crr1 >= 0.0125, "Active rain must be wet"

    # Case 2: Rain stopped 1h ago, sunny day, warm
    cond2, wet2, crr2 = engine.evaluate_road_moisture_and_drying(
        current_precip_in_hr=0.0, past_precip_1h_in=0.02, past_precip_2h_in=0.01,
        weather_code=1, temp_f=75.0, humidity_pct=40.0, wind_speed_mph=15.0, is_day=True
    )
    print(f"  Rain stopped (sunny/warm/breezy): condition={cond2}, wetness={wet2}, crr={crr2}")
    assert cond2 in ["dry", "damp"], "Light rain with sunny breeze must dry quickly"

    # Case 3: Freezing rain
    cond3, wet3, crr3 = engine.evaluate_road_moisture_and_drying(
        current_precip_in_hr=0.04, past_precip_1h_in=0.0, past_precip_2h_in=0.0,
        weather_code=66, temp_f=30.0, humidity_pct=90.0, wind_speed_mph=8.0, is_day=False
    )
    print(f"  Freezing Rain at 30 F: condition={cond3}, wetness={wet3}, crr={crr3}")
    assert cond3 == "ice" and crr3 >= 0.0210, "Freezing rain must register as ice"

    print("\n" + "=" * 70)
    print("SUCCESS: ALL TESTS PASSED! PHASE 1 IS VERIFIED AND FLAWLESS.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_all_scenarios())
