"""
TomTom Batch 3 Corridor Velocity Harvester & Rich Data Logger

Features:
  - 22 New Bidirectional Highway Corridors covering our 3 quick destination routes:
      * PA Turnpike Gateways: New Stanton (Exit 75), Valley Forge (Exit 326), Harrisburg West (Exit 242)
      * Sewickley & Pittsburgh Alternates: US-22 Weirton Bridge, I-79 Bridgeville Corridor, PA-576 Southern Beltway
      * Maryland Toll-Free Route: I-68 Cumberland Pass, I-70 Hagerstown (I-81), I-70 Frederick (I-270)
      * South Jersey & Lancaster: Delaware Memorial Bridge (I-295), US-30 Lancaster Bypass
  - 5 Day Profiles (Sun, Mon, Midweek Wed, Fri, Sat)
  - 20 Hours per day (1h daytime 6a-10p, 2h overnight with cubic/linear interpolation)
  - 22 corridors x 5 days x 20 hours = 2,200 total queries (comfortably under 2,500/day limit)
  - Outputs:
      1. data/tomtom_corridors_rich_archive.json (complete historical analytics dataset)
      2. data/tomtom_corridors_168h.json (7x24 matrix for production web app)
  - Auto-compiles into index.html, public/index.html, and ui/templates/index.html
"""

import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BATCH3_CORRIDORS = {
    # --- PA Turnpike Major Gateways (Marlton & Dillsburg Trips) ---
    "patp_new_stanton_east": {
        "name": "PA Turnpike New Stanton Eastbound (I-70/I-76 Interchange to MP 78)",
        "start": (40.2150, -79.6200),
        "end": (40.2300, -79.5600),
    },
    "patp_new_stanton_west": {
        "name": "PA Turnpike New Stanton Westbound (MP 78 to I-70/I-76 Interchange)",
        "start": (40.2300, -79.5600),
        "end": (40.2150, -79.6200),
    },
    "patp_valley_forge_east": {
        "name": "PA Turnpike Valley Forge Eastbound (MP 324 to Exit 326 / KOP)",
        "start": (40.0750, -75.4300),
        "end": (40.0950, -75.3800),
    },
    "patp_valley_forge_west": {
        "name": "PA Turnpike Valley Forge Westbound (Exit 326 / KOP to MP 324)",
        "start": (40.0950, -75.3800),
        "end": (40.0750, -75.4300),
    },
    "patp_harrisburg_west_east": {
        "name": "PA Turnpike Harrisburg West Eastbound (MP 241 to Exit 242 / US-15)",
        "start": (40.2100, -76.9200),
        "end": (40.2250, -76.8500),
    },
    "patp_harrisburg_west_west": {
        "name": "PA Turnpike Harrisburg West Westbound (Exit 242 / US-15 to MP 241)",
        "start": (40.2250, -76.8500),
        "end": (40.2100, -76.9200),
    },

    # --- Sewickley & Pittsburgh Bypass Alternates ---
    "us22_weirton_east": {
        "name": "US-22 Veterans Memorial Bridge Eastbound (Steubenville OH to Weirton WV)",
        "start": (40.3700, -80.6150),
        "end": (40.4050, -80.5700),
    },
    "us22_weirton_west": {
        "name": "US-22 Veterans Memorial Bridge Westbound (Weirton WV to Steubenville OH)",
        "start": (40.4050, -80.5700),
        "end": (40.3700, -80.6150),
    },
    "i79_bridgeville_north": {
        "name": "I-79 Bridgeville Corridor Northbound (Exit 54 to I-376 Parkway West)",
        "start": (40.3400, -80.1200),
        "end": (40.4000, -80.1000),
    },
    "i79_bridgeville_south": {
        "name": "I-79 Bridgeville Corridor Southbound (I-376 Parkway West to Exit 54)",
        "start": (40.4000, -80.1000),
        "end": (40.3400, -80.1200),
    },
    "pa576_beltway_north": {
        "name": "PA-576 Southern Beltway Northbound (US-22 to Pittsburgh Airport)",
        "start": (40.3650, -80.3100),
        "end": (40.4850, -80.2600),
    },
    "pa576_beltway_south": {
        "name": "PA-576 Southern Beltway Southbound (Pittsburgh Airport to US-22)",
        "start": (40.4850, -80.2600),
        "end": (40.3650, -80.3100),
    },

    # --- Maryland I-68 / I-70 Toll-Free Route to Marlton ---
    "i68_cumberland_east": {
        "name": "I-68 Cumberland Mountain Pass Eastbound (Exit 43 to Exit 46)",
        "start": (39.6450, -78.7800),
        "end": (39.6550, -78.7200),
    },
    "i68_cumberland_west": {
        "name": "I-68 Cumberland Mountain Pass Westbound (Exit 46 to Exit 43)",
        "start": (39.6550, -78.7200),
        "end": (39.6450, -78.7800),
    },
    "i70_hagerstown_east": {
        "name": "I-70 Hagerstown Freight Corridor Eastbound (I-81 to US-40)",
        "start": (39.6300, -77.7800),
        "end": (39.6350, -77.6800),
    },
    "i70_hagerstown_west": {
        "name": "I-70 Hagerstown Freight Corridor Westbound (US-40 to I-81)",
        "start": (39.6350, -77.6800),
        "end": (39.6300, -77.7800),
    },
    "i70_frederick_east": {
        "name": "I-70 Frederick Commuter Corridor Eastbound (US-15/US-40 to I-270)",
        "start": (39.4200, -77.4400),
        "end": (39.4000, -77.3700),
    },
    "i70_frederick_west": {
        "name": "I-70 Frederick Commuter Corridor Westbound (I-270 to US-15/US-40)",
        "start": (39.4000, -77.3700),
        "end": (39.4200, -77.4400),
    },
    "delaware_memorial_bridge_east": {
        "name": "Delaware Memorial Bridge I-295 Eastbound (DE Toll Plaza to NJ US-130)",
        "start": (39.6850, -75.5300),
        "end": (39.6950, -75.4950),
    },
    "delaware_memorial_bridge_west": {
        "name": "Delaware Memorial Bridge I-295 Westbound (NJ US-130 to DE Toll Plaza)",
        "start": (39.6950, -75.4950),
        "end": (39.6850, -75.5300),
    },

    # --- Central PA & Lancaster Commercial Arterials ---
    "us30_lancaster_east": {
        "name": "US-30 Lancaster Bypass Eastbound (Fruitville Pike to PA-896)",
        "start": (40.0600, -76.3200),
        "end": (40.0350, -76.2200),
    },
    "us30_lancaster_west": {
        "name": "US-30 Lancaster Bypass Westbound (PA-896 to Fruitville Pike)",
        "start": (40.0350, -76.2200),
        "end": (40.0600, -76.3200),
    },
}

HARVEST_DAYS = [
    {"name": "sunday", "sample_date": "2026-11-08", "applies_to": [0]},
    {"name": "monday", "sample_date": "2026-11-09", "applies_to": [1]},
    {"name": "midweek_wed", "sample_date": "2026-11-04", "applies_to": [2, 3, 4]},
    {"name": "friday", "sample_date": "2026-11-06", "applies_to": [5]},
    {"name": "saturday", "sample_date": "2026-11-07", "applies_to": [6]},
]

SAMPLE_HOURS = [
    0, 2, 4,
    6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
    22
]

def query_tomtom_corridor(api_key: str, start_coord, end_coord, depart_iso: str, retries: int = 5):
    s_lat, s_lon = start_coord
    e_lat, e_lon = end_coord
    coords = f"{s_lat},{s_lon}:{e_lat},{e_lon}"
    url = (
        f"https://api.tomtom.com/routing/1/calculateRoute/{coords}/json?"
        f"key={api_key}&traffic=true&departAt={urllib.parse.quote(depart_iso)}&routeType=fastest"
    )

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEVNavigator/1.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                summary = data["routes"][0]["summary"]
                miles = summary["lengthInMeters"] / 1609.34
                seconds = summary["travelTimeInSeconds"]
                no_traffic_sec = summary.get("noTrafficTravelTimeInSeconds", seconds)
                traffic_len_m = summary.get("trafficLengthInMeters", 0)

                speed_mph = miles / (seconds / 3600.0) if seconds > 0 else 60.0
                free_mph = miles / (no_traffic_sec / 3600.0) if no_traffic_sec > 0 else speed_mph

                return {
                    "miles": round(miles, 2),
                    "speed_mph": round(speed_mph, 1),
                    "free_flow_mph": round(free_mph, 1),
                    "travel_time_seconds": seconds,
                    "traffic_length_meters": traffic_len_m
                }
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_sec = 2.0 * (attempt + 1)
                print(f"    [Rate limit 429] Pausing {wait_sec}s before retry...", flush=True)
                time.sleep(wait_sec)
            else:
                if attempt == retries - 1:
                    raise
                time.sleep(1.0)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.0)

    raise RuntimeError("Failed after retries")

def interpolate_24h(sampled_dict: dict, key: str = "speed_mph"):
    vals_24 = [0.0] * 24
    for h in range(24):
        if h in sampled_dict:
            vals_24[h] = sampled_dict[h][key]
        else:
            prev_h = (h - 1) % 24
            next_h = (h + 1) % 24
            v_prev = sampled_dict.get(prev_h, {}).get(key, 60.0)
            v_next = sampled_dict.get(next_h, {}).get(key, 60.0)
            vals_24[h] = round((v_prev + v_next) / 2.0, 1)
    return vals_24

def harvest(api_key: str):
    archive_path = "data/tomtom_corridors_rich_archive.json"
    speeds_path = "data/tomtom_corridors_168h.json"

    rich_archive = {}
    production_speeds = {}

    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            rich_archive = json.load(f)

    if os.path.exists(speeds_path):
        with open(speeds_path, "r", encoding="utf-8") as f:
            production_speeds = json.load(f)

    total_calls = len(BATCH3_CORRIDORS) * len(HARVEST_DAYS) * len(SAMPLE_HOURS)
    call_idx = 0

    print("=" * 75, flush=True)
    print("TOMTOM BATCH 3 CORRIDOR VELOCITY HARVEST", flush=True)
    print(f"New Corridors: {len(BATCH3_CORRIDORS)} (Bidirectional)", flush=True)
    print(f"Total Queries: {total_calls} (Daily limit: 2,500 | QPS: ~4.0)", flush=True)
    print("=" * 75, flush=True)

    t0_all = time.time()

    for c_id, c_data in BATCH3_CORRIDORS.items():
        print(f"\n[{len(rich_archive) + 1}] Harvesting: {c_data['name']} ({c_id})...", flush=True)
        rich_archive[c_id] = {
            "name": c_data["name"],
            "start": c_data["start"],
            "end": c_data["end"],
            "profiles": {}
        }
        production_speeds[c_id] = [None] * 7

        for hday in HARVEST_DAYS:
            day_name = hday["name"]
            rich_archive[c_id]["profiles"][day_name] = {}
            day_samples = {}

            for hour in SAMPLE_HOURS:
                call_idx += 1
                depart_iso = f"{hday['sample_date']}T{hour:02d}:00:00"
                try:
                    res = query_tomtom_corridor(
                        api_key,
                        c_data["start"],
                        c_data["end"],
                        depart_iso
                    )
                    rich_archive[c_id]["profiles"][day_name][str(hour)] = res
                    day_samples[hour] = res

                    if call_idx % 20 == 0 or hour in [8, 17]:
                        elapsed = time.time() - t0_all
                        qps = call_idx / max(1.0, elapsed)
                        print(
                            f"  [{call_idx:4d}/{total_calls} | {qps:.1f} qps] {day_name[:3].upper()} {hour:02d}:00 | "
                            f"{res['speed_mph']:4.1f} mph | {res['travel_time_seconds']/60:4.1f} min",
                            flush=True
                        )
                    time.sleep(0.24)
                except Exception as e:
                    print(f"  Error at {c_id} {day_name} {hour:02d}:00: {e}", flush=True)
                    time.sleep(2.0)

            interp_24 = interpolate_24h(day_samples, key="speed_mph")
            for d in hday["applies_to"]:
                production_speeds[c_id][d] = interp_24

        # Recalibrate true free-flow baseline and delays for newly added corridor
        cdata = rich_archive[c_id]
        min_time = float("inf")
        best_free_flow_mph = 60.0
        for day_name, hours in cdata["profiles"].items():
            for h, sample in hours.items():
                t = sample["travel_time_seconds"]
                if 0 < t < min_time:
                    min_time = t
                    best_free_flow_mph = sample["speed_mph"]

        cdata["baseline_free_flow_seconds"] = min_time
        cdata["baseline_free_flow_mph"] = best_free_flow_mph

        for day_name, hours in cdata["profiles"].items():
            for h, sample in hours.items():
                t = sample["travel_time_seconds"]
                delay_sec = max(0, t - min_time)
                sample["delay_seconds"] = delay_sec
                sample["delay_minutes"] = round(delay_sec / 60.0, 1)
                sample["free_flow_mph"] = best_free_flow_mph
                sample["congestion_ratio"] = round(t / max(1, min_time), 3)

        # Intermediate save every corridor so progress is never lost
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(rich_archive, f, indent=2)
        with open(speeds_path, "w", encoding="utf-8") as f:
            json.dump(production_speeds, f, indent=2)

    total_time_min = (time.time() - t0_all) / 60.0
    print("\n" + "=" * 75, flush=True)
    print(f"HARVEST COMPLETE in {total_time_min:.1f} minutes!", flush=True)
    print(f"Total Corridors in Archive: {len(rich_archive)}", flush=True)
    print(f"Total Corridors in Production: {len(production_speeds)}", flush=True)
    print("=" * 75, flush=True)

    # Embed updated dictionary into HTML
    embed_into_html(production_speeds)

def embed_into_html(speed_matrix: dict):
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    js_matrix = "const TOMTOM_CORRIDOR_SPEEDS = " + json.dumps(speed_matrix, indent=2) + ";\n"

    start_token = "const TOMTOM_CORRIDOR_SPEEDS = {"
    end_token = "function getDepartureDayOfWeek()"

    idx_start = html.find(start_token)
    idx_end = html.find(end_token)

    if idx_start == -1 or idx_end == -1:
        print("ERROR: Could not locate TOMTOM_CORRIDOR_SPEEDS markers in index.html", flush=True)
        return

    updated_html = html[:idx_start] + js_matrix + "\n    " + html[idx_end:]

    for path in ["index.html", "public/index.html", "ui/templates/index.html"]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated_html)
        print(f"Updated: {path}", flush=True)

    hashes = [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in ["index.html", "public/index.html", "ui/templates/index.html"]]
    if len(set(hashes)) == 1:
        print(f"SHA-256 Parity Verified across all 3 files: {hashes[0][:16]}...", flush=True)
    else:
        print("WARNING: SHA-256 mismatch across HTML files!", flush=True)

if __name__ == "__main__":
    key = None
    if len(sys.argv) > 1:
        key = sys.argv[1]
    elif os.environ.get("TOMTOM_API_KEY"):
        key = os.environ.get("TOMTOM_API_KEY")
    elif os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                if line.startswith("TOMTOM_API_KEY="):
                    key = line.strip().split("=", 1)[1].strip()

    if not key:
        print("ERROR: No TomTom API key found.")
        sys.exit(1)

    harvest(key)
