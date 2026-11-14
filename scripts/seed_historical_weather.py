"""
Seed static ERA5 historical weather reanalysis cache for all quick destinations
across realistic travel seasons (Winter Holidays, Thanksgiving, Summer Peak, Spring/Easter).
Saves identical copies to data/historical_weather_cache.json and public/data/historical_weather_cache.json.
"""

import json
import math
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
import httpx

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.weather_engine import WeatherEngine


def get_realistic_date_ranges():
    """Returns list of (month, day) tuples for realistic travel windows."""
    dates = set()
    # 1. Winter Holidays: Dec 20 - Jan 5
    start = datetime(2025, 12, 20)
    for d in range(17):
        dt = start + timedelta(days=d)
        dates.add((dt.month, dt.day))

    # 2. Thanksgiving: Nov 20 - Nov 30
    start = datetime(2025, 11, 20)
    for d in range(11):
        dt = start + timedelta(days=d)
        dates.add((dt.month, dt.day))

    # 3. Summer Peak: Jul 1 - Jul 10
    start = datetime(2025, 7, 1)
    for d in range(10):
        dt = start + timedelta(days=d)
        dates.add((dt.month, dt.day))

    # 4. Spring / Easter: Mar 25 - Apr 10
    start = datetime(2025, 3, 25)
    for d in range(17):
        dt = start + timedelta(days=d)
        dates.add((dt.month, dt.day))

    return sorted(list(dates))


def collect_unique_waypoints():
    """Collects all unique (lat, lon) coordinates across all quick destination corridors."""
    corridors = WeatherEngine.get_precomputed_corridors()
    coords = {}
    for key, cfg in corridors.items():
        for wp in cfg["waypoints"]:
            _, lat, lon, _, _ = wp
            coord_key = f"{lat:.3f},{lon:.3f}"
            coords[coord_key] = (lat, lon)
    return coords


def fetch_batch_archive(coords_list, start_date, end_date):
    lats = ",".join(f"{lat:.4f}" for lat, _ in coords_list)
    lons = ",".join(f"{lon:.4f}" for _, lon in coords_list)
    url = (
        f"https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lats}&longitude={lons}&"
        f"start_date={start_date}&end_date={end_date}&"
        f"hourly=temperature_2m,relative_humidity_2m,precipitation,weather_code,"
        f"wind_speed_10m,wind_direction_10m,surface_pressure&"
        f"temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
    )
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else [data]


def main():
    coords_map = collect_unique_waypoints()
    coord_keys = list(coords_map.keys())
    coords_list = [coords_map[k] for k in coord_keys]
    print(f"Collected {len(coord_keys)} unique waypoints across all quick destinations.")

    # Use past 3 complete years (2023, 2024, 2025)
    target_years = [2025, 2024, 2023]
    windows = [
        ("12-20", "12-31"),
        ("01-01", "01-05"),
        ("11-20", "11-30"),
        ("07-01", "07-10"),
        ("03-25", "04-10"),
    ]

    # Raw accumulator: raw[coord_key][mm-dd][hour] = list of dicts per year
    raw = {ck: {} for ck in coord_keys}

    for yr in target_years:
        for w_start, w_end in windows:
            s_date = f"{yr}-{w_start}"
            e_date = f"{yr}-{w_end}"
            print(f"Fetching {s_date} to {e_date} for {len(coords_list)} waypoints...")
            series_list = fetch_batch_archive(coords_list, s_date, e_date)
            for c_idx, ck in enumerate(coord_keys):
                if c_idx >= len(series_list):
                    continue
                hourly = series_list[c_idx].get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("temperature_2m", [])
                hums = hourly.get("relative_humidity_2m", [])
                press = hourly.get("surface_pressure", [])
                winds = hourly.get("wind_speed_10m", [])
                wdirs = hourly.get("wind_direction_10m", [])
                precs = hourly.get("precipitation", [])
                codes = hourly.get("weather_code", [])

                for t_idx, t_str in enumerate(times):
                    # t_str format: "2025-12-23T08:00"
                    mm_dd = t_str[5:10]
                    hr = int(t_str[11:13])
                    if mm_dd not in raw[ck]:
                        raw[ck][mm_dd] = [[] for _ in range(24)]
                    if temps[t_idx] is None:
                        continue
                    raw[ck][mm_dd][hr].append({
                        "t": float(temps[t_idx]),
                        "h": float(hums[t_idx] if hums[t_idx] is not None else 50.0),
                        "p": float(press[t_idx] if press[t_idx] is not None else 1013.25),
                        "w": float(winds[t_idx] if winds[t_idx] is not None else 5.0),
                        "wd": float(wdirs[t_idx] if wdirs[t_idx] is not None else 270.0),
                        "pr": float(precs[t_idx] if precs[t_idx] is not None else 0.0),
                        "c": int(codes[t_idx] if codes[t_idx] is not None else 0),
                    })
            time.sleep(0.4)

    # Aggregate 3-year averages cleanly
    cache = {}
    for ck in coord_keys:
        cache[ck] = {}
        for mm_dd, hours_list in raw[ck].items():
            t_arr, h_arr, p_arr, w_arr, wd_arr, pr_arr, c_arr = [], [], [], [], [], [], []
            for hr in range(24):
                samples = hours_list[hr]
                if not samples:
                    t_arr.append(55.0)
                    h_arr.append(50.0)
                    p_arr.append(1013.25)
                    w_arr.append(7.0)
                    wd_arr.append(270.0)
                    pr_arr.append(0.0)
                    c_arr.append(0)
                else:
                    n = len(samples)
                    t_arr.append(round(sum(s["t"] for s in samples) / n, 1))
                    h_arr.append(round(sum(s["h"] for s in samples) / n, 1))
                    p_arr.append(round(sum(s["p"] for s in samples) / n, 1))
                    w_arr.append(round(sum(s["w"] for s in samples) / n, 1))
                    u_sum = sum(-math.sin(math.radians(s["wd"])) for s in samples)
                    v_sum = sum(-math.cos(math.radians(s["wd"])) for s in samples)
                    avg_wd = (math.degrees(math.atan2(-u_sum, -v_sum)) + 360) % 360
                    wd_arr.append(round(avg_wd, 1))
                    pr_arr.append(round(sum(s["pr"] for s in samples) / n, 3))
                    c_arr.append(samples[0]["c"])
            cache[ck][mm_dd] = {
                "t": t_arr,
                "h": h_arr,
                "p": p_arr,
                "w": w_arr,
                "wd": wd_arr,
                "pr": pr_arr,
                "c": c_arr,
            }

    out_data = Path("data/historical_weather_cache.json")
    out_pub = Path("public/data/historical_weather_cache.json")
    out_data.parent.mkdir(parents=True, exist_ok=True)
    out_pub.parent.mkdir(parents=True, exist_ok=True)

    with open(out_data, "w", encoding="utf-8") as f:
        json.dump(cache, f, separators=(",", ":"))
    shutil.copy2(out_data, out_pub)
    print(f"Successfully wrote {out_data} and {out_pub} ({out_data.stat().st_size / 1024:.1f} KB).")


if __name__ == "__main__":
    main()
