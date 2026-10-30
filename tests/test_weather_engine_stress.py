"""
Stress & Edge Case Testing for WeatherEngine.
Tests winter vs summer extremes, day vs night transitions, and input edge cases.
"""

import asyncio
from datetime import datetime, timedelta
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.weather_engine import WeatherEngine


async def run_stress_tests():
    print("=" * 70)
    print("RUNNING ADVANCED STRESS & EDGE CASE SCENARIOS")
    print("=" * 70)

    engine = WeatherEngine()

    # Scenario A: Mid-Winter Deep Freeze Departure (Jan 15 historical)
    print("\n[STRESS A] Mid-Winter Deep Freeze on St. Onge Corridor (Jan 15, 07:00 AM)...")
    winter_dt = datetime(2027, 1, 15, 7, 0)
    rep_winter = await engine.get_route_weather_report("st_onge", winter_dt)

    print(f"  Mode: {rep_winter.mode} | Avg Temp: {rep_winter.summary['avg_temp_f']} F (Min: {rep_winter.summary['min_temp_f']} F)")
    print(f"  Winter Avg Consumption: {rep_winter.summary['avg_consumption_wh_per_mi']} Wh/mi vs Baseline: {rep_winter.summary['baseline_avg_wh_per_mi']} Wh/mi")
    print(f"  Total HVAC Energy Used: {rep_winter.summary['total_hvac_kwh']} kWh")
    print(f"  Total Trip Energy: {rep_winter.summary['total_energy_kwh']} kWh (Delta: +{rep_winter.summary['energy_delta_kwh']} kWh, +{rep_winter.summary['energy_delta_pct']}%)")
    
    # In winter, consumption should be significantly higher due to PTC heater, cold air density, and battery kinetics
    assert rep_winter.summary['avg_temp_f'] < 45.0, "January should have cold average temperature"
    assert rep_winter.summary['avg_consumption_wh_per_mi'] > rep_winter.summary['baseline_avg_wh_per_mi'], "Winter consumption must exceed baseline"
    assert rep_winter.summary['total_hvac_kwh'] > 10.0, "Winter cabin heating should draw significant energy (>10 kWh over 6h)"

    # Scenario B: Mid-Summer Heatwave Departure (July 20 historical)
    print("\n[STRESS B] Mid-Summer Heatwave on St. Onge Corridor (July 20, 02:00 PM)...")
    summer_dt = datetime(2027, 7, 20, 14, 0)
    rep_summer = await engine.get_route_weather_report("st_onge", summer_dt)

    print(f"  Mode: {rep_summer.mode} | Avg Temp: {rep_summer.summary['avg_temp_f']} F (Max: {rep_summer.summary['max_temp_f']} F)")
    print(f"  Summer Avg Consumption: {rep_summer.summary['avg_consumption_wh_per_mi']} Wh/mi")
    print(f"  Total HVAC Energy (AC cooling): {rep_summer.summary['total_hvac_kwh']} kWh")
    
    assert rep_summer.summary['avg_temp_f'] > 70.0, "July should have warm average temperature"
    # Air density should be lower in summer (thinner warm air)
    somerset_summer = next(w for w in rep_summer.waypoints if "Somerset" in w.name)
    somerset_winter = next(w for w in rep_winter.waypoints if "Somerset" in w.name)
    print(f"  Somerset Air Density: Winter={somerset_winter.air_density_kg_m3} kg/m3 vs Summer={somerset_summer.air_density_kg_m3} kg/m3")
    assert somerset_winter.air_density_kg_m3 > somerset_summer.air_density_kg_m3, "Cold winter air must be denser than hot summer air"

    # Scenario C: Nighttime Departure (11:30 PM)
    print("\n[STRESS C] Nighttime Departure on Billings Corridor (Today at 11:30 PM)...")
    night_dt = datetime.now().replace(hour=23, minute=30, second=0, microsecond=0)
    rep_night = await engine.get_route_weather_report("billings", night_dt)
    print(f"  Night departure arrival time at destination: {rep_night.waypoints[-1].arrival_time_clock}")
    assert any(not w.is_day for w in rep_night.waypoints), "Night departure should have is_day=False for waypoints"

    # Scenario D: Custom non-quick route with high elevation variations (Pittsburgh to Frostburg / Cumberland)
    print("\n[STRESS D] Mountain Pass Custom Route: Washington PA to Cumberland MD via I-68...")
    coords_i68 = [
        [-80.2462, 40.1740, 310.0], # Washington PA
        [-79.9559, 39.6295, 290.0], # Morgantown WV
        [-78.9284, 39.6582, 640.0], # Frostburg MD (Big Savage Mountain 2,100 ft)
        [-78.7625, 39.6529, 210.0]  # Cumberland MD (Potomac Valley)
    ]
    rep_i68 = await engine.get_route_weather_report(
        destination_key_or_name="Cumberland",
        departure_dt=datetime.now() + timedelta(days=2),
        custom_coordinates=coords_i68,
        origin_name="Washington, PA",
        destination_name="Cumberland, MD"
    )
    print(f"  Route: {rep_i68.route_name} | Distance: {rep_i68.total_distance_miles} mi | Duration: {rep_i68.total_duration_hours} h")
    frostburg_wp = next(w for w in rep_i68.waypoints if "Frostburg" in w.name or w.elevation_ft > 2000.0)
    print(f"  Mountain Summit Check: elev={frostburg_wp.elevation_ft}ft, temp={frostburg_wp.ambient_temp_f}F, pressure={frostburg_wp.surface_pressure_hpa}hPa")
    assert frostburg_wp.elevation_ft > 2000.0

    print("\n" + "=" * 70)
    print("SUCCESS: ALL STRESS & EDGE CASE SCENARIOS PASSED WITH HIGH FIDELITY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_stress_tests())
