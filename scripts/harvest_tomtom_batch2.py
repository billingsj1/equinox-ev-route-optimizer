"""
Batch 2 TomTom Velocity Harvesting Script
Harvests 22 new bidirectional urban/arterial corridors across 5 day profiles
and merges them with Batch 1 into data/tomtom_corridors_rich_archive.json
and data/tomtom_corridors_168h.json, then auto-compiles into index.html.
"""

import datetime
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BATCH2_CORRIDORS = {
    # --- Greater Philadelphia & South Jersey Non-Highway / Bridge Alternates ---
    "us202_south": {
        "name": "US-202 Great Valley South (King of Prussia to Exton/US-30)",
        "start": (40.0850, -75.3950),
        "end": (40.0385, -75.6212),
    },
    "us202_north": {
        "name": "US-202 Great Valley North (Exton/US-30 to King of Prussia)",
        "start": (40.0385, -75.6212),
        "end": (40.0850, -75.3950),
    },
    "nj38_east": {
        "name": "NJ-38 Commercial Arterial East (Pennsauken to Moorestown/Mt Laurel)",
        "start": (39.9405, -75.0802),
        "end": (39.9650, -74.9350),
    },
    "nj38_west": {
        "name": "NJ-38 Commercial Arterial West (Moorestown/Mt Laurel to Pennsauken)",
        "start": (39.9650, -74.9350),
        "end": (39.9405, -75.0802),
    },
    "i295_southjersey_north": {
        "name": "I-295 North (Bellmawr/Rt 42 to Mount Laurel/Rt 70/73)",
        "start": (39.8750, -75.0950),
        "end": (39.9250, -74.9600),
    },
    "i295_southjersey_south": {
        "name": "I-295 South (Mount Laurel/Rt 70/73 to Bellmawr/Rt 42)",
        "start": (39.9250, -74.9600),
        "end": (39.8750, -75.0950),
    },
    "waltwhitman_east": {
        "name": "Walt Whitman Bridge & I-76 East (South Philly to I-295/Rt 42)",
        "start": (39.9120, -75.1850),
        "end": (39.8850, -75.1100),
    },
    "waltwhitman_west": {
        "name": "Walt Whitman Bridge & I-76 West (I-295/Rt 42 to South Philly)",
        "start": (39.8850, -75.1100),
        "end": (39.9120, -75.1850),
    },
    "tacony_palmyra_nj73_south": {
        "name": "Tacony-Palmyra Bridge & NJ-73 South (NE Philly/Palmyra to NJ-38)",
        "start": (40.0120, -75.0450),
        "end": (39.9450, -74.9850),
    },
    "tacony_palmyra_nj73_north": {
        "name": "NJ-73 North & Tacony-Palmyra Bridge (NJ-38 to Palmyra/NE Philly)",
        "start": (39.9450, -74.9850),
        "end": (40.0120, -75.0450),
    },

    # --- Pittsburgh & Sewickley Bottlenecks ---
    "i79_pittsburgh_north": {
        "name": "I-79 North (Bridgeville/I-376 to Neville Island/Sewickley Exit 66)",
        "start": (40.3800, -80.1000),
        "end": (40.5250, -80.1450),
    },
    "i79_pittsburgh_south": {
        "name": "I-79 South (Neville Island/Sewickley to Bridgeville/I-376)",
        "start": (40.5250, -80.1450),
        "end": (40.3800, -80.1000),
    },
    "sewickley_bridge_east": {
        "name": "Sewickley Bridge & PA-51 East (Coraopolis to Sewickley Beaver St)",
        "start": (40.5330, -80.1880),
        "end": (40.5395, -80.1830),
    },
    "sewickley_bridge_west": {
        "name": "Sewickley Bridge & PA-51 West (Sewickley Beaver St to Coraopolis)",
        "start": (40.5395, -80.1830),
        "end": (40.5330, -80.1880),
    },

    # --- Central PA & Dillsburg Arterials ---
    "i83_harrisburg_north": {
        "name": "I-83 South Bridge Northbound (Camp Hill/PA-581 to Harrisburg)",
        "start": (40.2350, -76.9550),
        "end": (40.2450, -76.8750),
    },
    "i83_harrisburg_south": {
        "name": "I-83 South Bridge Southbound (Harrisburg to Camp Hill/PA-581)",
        "start": (40.2450, -76.8750),
        "end": (40.2350, -76.9550),
    },
    "dillsburg_us15_arterial_south": {
        "name": "US-15 Dillsburg Signalized Commercial Arterial South",
        "start": (40.1800, -77.0050),
        "end": (40.1250, -77.0250),
    },
    "dillsburg_us15_arterial_north": {
        "name": "US-15 Dillsburg Signalized Commercial Arterial North",
        "start": (40.1250, -77.0250),
        "end": (40.1800, -77.0050),
    },

    # --- Columbus & Wheeling Metro Bottlenecks ---
    "columbus_i70_split_east": {
        "name": "I-70/I-71 Downtown Columbus Downtown Split East (SR-315 to I-70/I-71 E)",
        "start": (39.9535, -83.0080),
        "end": (39.9580, -82.9850),
    },
    "columbus_i70_split_west": {
        "name": "I-70/I-71 Downtown Columbus Downtown Split West (I-70/I-71 E to SR-315)",
        "start": (39.9580, -82.9850),
        "end": (39.9535, -83.0080),
    },
    "wheeling_i70_east": {
        "name": "I-70 Fort Henry Bridge & Wheeling Tunnels East (Ohio River to Wheeling)",
        "start": (40.0680, -80.7350),
        "end": (40.0550, -80.6900),
    },
    "wheeling_i70_west": {
        "name": "I-70 Wheeling Tunnels & Fort Henry Bridge West (Wheeling to Ohio River)",
        "start": (40.0550, -80.6900),
        "end": (40.0680, -80.7350),
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
    5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
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
    # Load existing archive to merge
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

    total_calls = len(BATCH2_CORRIDORS) * len(HARVEST_DAYS) * len(SAMPLE_HOURS)
    call_idx = 0

    print("=" * 75, flush=True)
    print("TOMTOM BATCH 2 CORRIDOR VELOCITY HARVEST", flush=True)
    print(f"New Corridors: {len(BATCH2_CORRIDORS)} (Bidirectional)", flush=True)
    print(f"Total Queries: {total_calls} (Daily limit: 2,500 | QPS: 4.0)", flush=True)
    print("=" * 75, flush=True)

    for c_id, c_data in BATCH2_CORRIDORS.items():
        print(f"\nHarvesting corridor: {c_data['name']}...", flush=True)
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

                    if call_idx % 10 == 0 or hour in [8, 17]:
                        print(
                            f"  [{call_idx:4d}/{total_calls}] {day_name[:3].upper()} {hour:02d}:00 | "
                            f"{res['speed_mph']:4.1f} mph | {res['travel_time_seconds']/60:4.1f} min",
                            flush=True
                        )
                    time.sleep(0.25)
                except Exception as e:
                    print(f"  Error at {c_id} {day_name} {hour:02d}:00: {e}", flush=True)
                    time.sleep(2.0)

            interp_24 = interpolate_24h(day_samples, key="speed_mph")
            for d in hday["applies_to"]:
                production_speeds[c_id][d] = interp_24

    # Recalibrate true free-flow baseline and delays for newly added corridors
    for c_id in BATCH2_CORRIDORS.keys():
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

    # Save merged datasets
    os.makedirs("data", exist_ok=True)
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(rich_archive, f, indent=2)
    print(f"\nSaved updated rich archive ({len(rich_archive)} corridors) to: {archive_path}", flush=True)

    with open(speeds_path, "w", encoding="utf-8") as f:
        json.dump(production_speeds, f, indent=2)
    print(f"Saved updated 7x24 production speed matrix to: {speeds_path}", flush=True)

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
        print(f"SHA-256 Parity Verified: {hashes[0][:16]}...", flush=True)

if __name__ == "__main__":
    key = None
    if len(sys.argv) > 1:
        key = sys.argv[1]
    elif os.environ.get("TOMTOM_API_KEY"):
        key = os.environ.get("TOMTOM_API_KEY")
    elif os.path.exists("scratch/tomtom_api_key.txt"):
        key = open("scratch/tomtom_api_key.txt").read().strip()

    if not key:
        print("ERROR: No TomTom API key provided. Pass via argument, TOMTOM_API_KEY env, or scratch/tomtom_api_key.txt")
        sys.exit(1)

    harvest(key)
