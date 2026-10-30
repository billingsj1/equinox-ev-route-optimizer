"""
Waypoint Density Analysis & Sensitivity Testing
Compares route slicing resolutions (60mi, 35mi, 18mi, 10mi) across all 3 Quick Destinations
Evaluates:
- Predicted Energy Consumption (total kWh and Wh/mi)
- Temperature capture (min, max, weighted avg)
- Effective vector wind capture (mph)
- Road state detection (% wet / rain / snow)
- Open-Meteo batch latency and data resolution
"""
import sys
import os
import math
import time
import asyncio
from datetime import datetime
from typing import List, Tuple, Dict, Any

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.weather_engine import WeatherEngine

def interpolate_corridor(
    raw_waypoints: List[Tuple[str, float, float, float, float]],
    target_spacing_miles: float
) -> List[Tuple[str, float, float, float, float]]:
    """
    Subdivides waypoints along corridor so that segment distance <= target_spacing_miles.
    Linearly interpolates lat, lon, elevation, and preserves speed limit.
    """
    out = [raw_waypoints[0]]
    for i in range(len(raw_waypoints) - 1):
        p1 = raw_waypoints[i]
        p2 = raw_waypoints[i + 1]
        
        dist = WeatherEngine.haversine_distance_miles(p1[1], p1[2], p2[1], p2[2])
        num_sub = max(1, math.ceil(dist / target_spacing_miles))
        
        for k in range(1, num_sub + 1):
            t = k / float(num_sub)
            lat = p1[1] + t * (p2[1] - p1[1])
            lon = p1[2] + t * (p2[2] - p1[2])
            elev = p1[3] + t * (p2[3] - p1[3])
            speed = p2[4]
            name = p2[0] if k == num_sub else f"{p1[0]} (Mile {round(dist * t, 1)})"
            out.append((name, lat, lon, elev, speed))
    return out

async def evaluate_timeline(engine: WeatherEngine, wps: List[Tuple[str, float, float, float, float]], dep_dt: datetime) -> Dict[str, Any]:
    timeline = engine.build_route_timeline_from_waypoints(wps, dep_dt)
    t0 = time.time()
    waypoints_weather = await engine.fetch_open_meteo_weather(timeline, dep_dt)
    elapsed_ms = (time.time() - t0) * 1000.0

    total_dist = timeline[-1]["dist_from_start_miles"] if timeline else 0.0
    temps = [w.ambient_temp_f for w in waypoints_weather]
    hw_vals = [w.effective_headwind_mph for w in waypoints_weather]
    
    wet_count = sum(1 for w in waypoints_weather if w.road_condition in ["damp", "wet", "heavy_wet"])
    snow_count = sum(1 for w in waypoints_weather if w.road_condition in ["snow_slush", "ice"])
    wet_pct = round((wet_count / max(1, len(waypoints_weather))) * 100.0, 1)
    snow_pct = round((snow_count / max(1, len(waypoints_weather))) * 100.0, 1)

    total_energy_kwh = sum(
        (w.estimated_consumption_wh_per_mi * w.segment_distance_miles) / 1000.0
        for w in waypoints_weather
    )
    baseline_energy_kwh = sum(
        (w.baseline_consumption_wh_per_mi * w.segment_distance_miles) / 1000.0
        for w in waypoints_weather
    )
    avg_wh_per_mi = round((total_energy_kwh * 1000.0) / max(0.1, total_dist), 1)

    return {
        "pts": len(waypoints_weather),
        "latency_ms": elapsed_ms,
        "avg_temp": round(sum(temps)/len(temps), 1) if temps else 0.0,
        "min_temp": min(temps) if temps else 0.0,
        "max_temp": max(temps) if temps else 0.0,
        "max_hw": max(0.0, max(hw_vals)) if hw_vals else 0.0,
        "max_tw": abs(min(0.0, min(hw_vals))) if hw_vals else 0.0,
        "wet_pct": wet_pct,
        "snow_pct": snow_pct,
        "total_kwh": round(total_energy_kwh, 2),
        "baseline_kwh": round(baseline_energy_kwh, 2),
        "avg_wh_mi": avg_wh_per_mi
    }

async def run_density_experiment():
    print("=" * 100)
    print("WAYPOINT DENSITY SENSITIVITY EXPERIMENT - 2025 EQUINOX EV ROUTE WEATHER ENGINE")
    print("=" * 100)

    engine = WeatherEngine()
    corridors = WeatherEngine.get_precomputed_corridors()
    
    # Test departure: Tomorrow at 8:00 AM (Live forecast)
    now = datetime.now()
    dep_dt = datetime(now.year, now.month, now.day, 8, 0)
    
    # Resolutions to test
    resolutions = [
        ("Coarse (~60 mi)", 60.0),
        ("Current (~35 mi)", 35.0),
        ("Fine (~18 mi)", 18.0),
        ("Ultra-Fine (~10 mi)", 10.0),
    ]

    for dest_key, cfg in corridors.items():
        route_name = cfg["route_name"]
        raw_base_wps = cfg["waypoints"]
        print(f"\n" + "-" * 100)
        print(f"CORRIDOR: {route_name.upper()}")
        print("-" * 100)
        print(f"{'Resolution':<20} | {'Pts':<5} | {'Latency':<8} | {'Temp Range (°F)':<18} | {'Tail/Head':<12} | {'Wet Road %':<10} | {'Total kWh':<10} | {'Wh/mi':<8} | {'Delta vs 35m'}")
        print("-" * 100)

        results_by_res = {}

        for res_name, target_spacing in resolutions:
            if res_name == "Current (~35 mi)":
                wps = raw_base_wps
            elif target_spacing > 50.0:
                step = 2 if len(raw_base_wps) > 8 else 1
                wps = [raw_base_wps[i] for i in range(0, len(raw_base_wps), step)]
                if wps[-1] != raw_base_wps[-1]:
                    wps.append(raw_base_wps[-1])
            else:
                wps = interpolate_corridor(raw_base_wps, target_spacing)

            r = await evaluate_timeline(engine, wps, dep_dt)
            results_by_res[res_name] = r

        # Print comparison table with baseline delta
        base_kwh = results_by_res["Current (~35 mi)"]["total_kwh"]
        for res_name, r in results_by_res.items():
            delta_kwh = r["total_kwh"] - base_kwh
            delta_pct = (delta_kwh / base_kwh) * 100.0 if base_kwh > 0 else 0.0
            sign = "+" if delta_kwh >= 0 else ""
            delta_str = "Baseline" if res_name == "Current (~35 mi)" else f"{sign}{delta_kwh:.2f} kWh ({sign}{delta_pct:.1f}%)"
            
            wind_str = f"T+{r['max_tw']:.0f} / H+{r['max_hw']:.0f}"
            temp_range = f"{r['min_temp']:.0f}° - {r['max_temp']:.0f}°F (avg {r['avg_temp']:.0f})"
            print(f"{res_name:<20} | {r['pts']:<5} | {r['latency_ms']:>6.0f}ms | {temp_range:<18} | {wind_str:<12} | {r['wet_pct']:>8.1f}% | {r['total_kwh']:>8.2f} kWh | {r['avg_wh_mi']:>5} | {delta_str}")

    print("\n" + "=" * 100)
    print("HISTORICAL WINTER SENSITIVITY TEST (ERA5 Reanalysis - Dec 22 Winter Solstice)")
    print("=" * 100)

    # Test winter sub-freezing day (Dec 22, 2024) across Somerset PA Mountain Pass
    winter_dt = datetime(2024, 12, 22, 8, 0)
    for dest_key in ["st_onge", "decamilla"]:
        cfg = corridors[dest_key]
        raw_base_wps = cfg["waypoints"]
        print(f"\nWINTER CORRIDOR: {cfg['route_name']} (Date: 2024-12-22)")
        print(f"{'Resolution':<20} | {'Pts':<5} | {'Avg Temp':<10} | {'Min Temp (Summit)':<18} | {'Snow/Ice %':<12} | {'Total kWh':<10} | {'Wh/mi':<8} | {'Delta vs 35m'}")
        print("-" * 100)
        
        base_winter_kwh = None
        for res_name, target_spacing in resolutions:
            if res_name == "Current (~35 mi)":
                wps = raw_base_wps
            elif target_spacing > 50.0:
                step = 2 if len(raw_base_wps) > 8 else 1
                wps = [raw_base_wps[i] for i in range(0, len(raw_base_wps), step)]
                if wps[-1] != raw_base_wps[-1]:
                    wps.append(raw_base_wps[-1])
            else:
                wps = interpolate_corridor(raw_base_wps, target_spacing)

            r = await evaluate_timeline(engine, wps, winter_dt)
            if res_name == "Current (~35 mi)":
                base_winter_kwh = r["total_kwh"]

            delta_kwh = r["total_kwh"] - (base_winter_kwh or r["total_kwh"])
            delta_pct = (delta_kwh / base_winter_kwh) * 100.0 if base_winter_kwh else 0.0
            sign = "+" if delta_kwh >= 0 else ""
            delta_str = "Baseline" if res_name == "Current (~35 mi)" else f"{sign}{delta_kwh:.2f} kWh ({sign}{delta_pct:.1f}%)"

            print(f"{res_name:<20} | {r['pts']:<5} | {r['avg_temp']:>6.1f}°F   | {r['min_temp']:>6.1f}°F           | {r['snow_pct']:>8.1f}%    | {r['total_kwh']:>8.2f} kWh | {r['avg_wh_mi']:>5} | {delta_str}")

    print("\n" + "=" * 100)
    print("MULTI-DAY FORECAST WINDOW (Checking precipitation and front sensitivity)")
    print("=" * 100)
    cfg_st = corridors["st_onge"]
    base_wps = cfg_st["waypoints"]
    wps_18 = interpolate_corridor(base_wps, 18.0)

    for day_offset in [1, 2, 4, 7]:
        from datetime import timedelta
        f_dt = datetime(now.year, now.month, now.day, 12, 0) + timedelta(days=day_offset)
        r_base = await evaluate_timeline(engine, base_wps, f_dt)
        r_18 = await evaluate_timeline(engine, wps_18, f_dt)
        d_kwh = abs(r_base['total_kwh'] - r_18['total_kwh'])
        d_pct = (d_kwh / r_base['total_kwh']) * 100.0 if r_base['total_kwh'] > 0 else 0
        date_lbl = f_dt.strftime("%Y-%m-%d %I:%M %p")
        print(f"Departure {date_lbl} (Day +{day_offset}):")
        print(f"  Current (13 pts): {r_base['total_kwh']:>6.2f} kWh | {r_base['avg_wh_mi']:>5} Wh/mi | Wet: {r_base['wet_pct']:>4.1f}% | Temp: {r_base['avg_temp']:.1f}°F | Max Wind: T+{r_base['max_tw']:.0f} / H+{r_base['max_hw']:.0f}")
        print(f"  Fine    (31 pts): {r_18['total_kwh']:>6.2f} kWh | {r_18['avg_wh_mi']:>5} Wh/mi | Wet: {r_18['wet_pct']:>4.1f}% | Temp: {r_18['avg_temp']:.1f}°F | Max Wind: T+{r_18['max_tw']:.0f} / H+{r_18['max_hw']:.0f}")
        print(f"  Delta: {d_kwh:.2f} kWh ({d_pct:.2f}%)\n")

if __name__ == "__main__":
    asyncio.run(run_density_experiment())
