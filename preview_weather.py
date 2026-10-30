"""
Standalone Weather Engine Preview Tool (Phase 2 CLI).
Executes high-resolution weather predictions for primary and custom routes,
calculates physical vehicle impacts, and renders formatted tables.
"""

import argparse
import asyncio
from datetime import datetime, timedelta
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.weather_engine import WeatherEngine


def round_to_next_30m(dt: datetime) -> datetime:
    minutes = dt.minute
    if minutes == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt
    if minutes < 30:
        return dt.replace(minute=30, second=0, microsecond=0)
    else:
        return (dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)


def print_report_table(rep):
    print("\n" + "=" * 90)
    print(f"2025 EQUINOX EV ROUTE WEATHER & PHYSICS ENGINE REPORT")
    print(f"Route: {rep.route_name}")
    print(f"Origin: {rep.origin_name} -> Destination: {rep.destination_name}")
    print(f"Departure: {rep.departure_time_clock} on {rep.departure_time_iso[:10]} | Mode: {rep.mode.upper()}")
    print(f"Total Distance: {rep.total_distance_miles} mi | Est. Driving Time: {rep.total_duration_hours} hrs")
    print("=" * 90)

    # Waypoints table
    headers = [
        "Time", "Mile", "Elev", "Checkpoint", "Temp", "Weather", "Wind (Dir)", "Vector", "Road", "Air Rho", "Wh/mi"
    ]
    fmt = "{:<9} {:<6} {:<7} {:<32} {:<6} {:<15} {:<11} {:<10} {:<9} {:<9} {:<7}"
    print(fmt.format(*headers))
    print("-" * 125)

    for w in rep.waypoints:
        wind_str = f"{w.wind_speed_mph}m {w.wind_direction_cardinal}"
        if w.effective_headwind_mph <= -2.0:
            vec_str = f"Tail {abs(w.effective_headwind_mph):.0f}m"
        elif w.effective_headwind_mph >= 2.0:
            vec_str = f"Head +{w.effective_headwind_mph:.0f}m"
        else:
            vec_str = f"Cross {w.crosswind_mph:.0f}m"

        elev_str = f"{int(w.elevation_ft)}ft"
        mile_str = f"{w.distance_from_start_miles:.1f}"

        print(fmt.format(
            w.arrival_time_clock,
            mile_str,
            elev_str,
            w.name[:31],
            f"{w.ambient_temp_f:.0f}F",
            w.weather_description[:14],
            wind_str,
            vec_str,
            w.road_condition[:8],
            f"{w.air_density_kg_m3:.3f}",
            f"{w.estimated_consumption_wh_per_mi:.0f}"
        ))

    print("-" * 125)
    s = rep.summary
    print("\nTRIP WEATHER & PHYSICAL CONSUMPTION IMPACT SUMMARY:")
    print(f"  * Temperature Range: {s['min_temp_f']} F to {s['max_temp_f']} F (Avg: {s['avg_temp_f']} F)")
    print(f"  * Peak Headwind: {s['max_headwind_mph']} mph | Peak Tailwind: {s['max_tailwind_mph']} mph")
    print(f"  * Road Conditions: {s['wet_road_pct']}% Wet, {s['snow_ice_road_pct']}% Snow/Ice")
    print(f"  * Weather Consumption: {s['avg_consumption_wh_per_mi']} Wh/mi vs Baseline: {s['baseline_avg_wh_per_mi']} Wh/mi (70 F dry base)")
    print(f"  * Total Energy: {s['total_energy_kwh']} kWh vs Baseline: {s['baseline_energy_kwh']} kWh")
    sign = "+" if s['energy_delta_kwh'] >= 0 else ""
    print(f"  * Net Weather Impact: {sign}{s['energy_delta_kwh']} kWh ({sign}{s['energy_delta_pct']}%)")
    print(f"  * Total HVAC Draw: {s['total_hvac_kwh']} kWh (Cabin heat/cool)")
    print("=" * 90 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="Equinox EV Route Weather Preview")
    parser.add_argument("--dest", default="st_onge", help="Destination: st_onge, billings, decamilla, or custom city")
    parser.add_argument("--date", default="", help="Departure date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--time", default="", help="Departure time HH:MM (defaults to now + 30m)")
    parser.add_argument("--serve", action="store_true", help="Launch interactive web preview dashboard on port 8000")
    parser.add_argument("--port", type=int, default=8000, help="Web server port")

    args = parser.parse_args()

    if args.serve:
        import uvicorn
        print(f"\nLaunching Weather Engine Preview Dashboard at http://127.0.0.1:{args.port}/weather-preview\n")
        uvicorn.run("ui.app:app", host="127.0.0.1", port=args.port, reload=False)
        return

    now = datetime.now()
    dep_date = now.date()
    if args.date:
        try:
            dep_date = datetime.strptime(args.date.strip(), "%Y-%m-%d").date()
        except Exception:
            pass

    if args.time:
        try:
            t = datetime.strptime(args.time.strip(), "%H:%M").time()
            dep_dt = datetime.combine(dep_date, t)
        except Exception:
            dep_dt = round_to_next_30m(datetime.combine(dep_date, now.time()))
    else:
        dep_dt = round_to_next_30m(datetime.combine(dep_date, now.time()))

    engine = WeatherEngine()
    rep = await engine.get_route_weather_report(args.dest, dep_dt)
    print_report_table(rep)


if __name__ == "__main__":
    asyncio.run(main())
