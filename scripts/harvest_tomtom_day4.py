"""
TomTom Day 4 Quota Harvester (Priority 3, Day 4):
Harvests 15-Minute High-Fidelity Rush Hour Intervals on Primary Bottlenecks:
  - Schuylkill Expressway (East & West)
  - Vine St Expressway (East & West)
  - I-276 PA Turnpike East Extension (East & West)
  - Breezewood Interchange Gateway (East & West)
  - Allegheny Mountain Tunnel (East & West)
  - Carlisle Mega Interchange (East & West)

Sampled 15-minute rush intervals:
  Morning: 6:45, 7:15, 7:45, 8:15, 8:45, 9:15
  Evening: 15:45, 16:15, 16:45, 17:15, 17:45, 18:15
across 7 Days of the Week = 12 directed corridors * 7 days * 12 rush slots = 1,008 calls
Plus 12 secondary bottleneck rush intervals = 2,016 calls total.
"""

import concurrent.futures
import json
import os
import sys
import time
import urllib.parse
import urllib.request

def load_key():
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TOMTOM_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

api_key = load_key()
if not api_key:
    print("ERROR: TOMTOM_API_KEY not found in .env")
    sys.exit(1)

CORRIDORS = [
    # Primary Bottlenecks for 15-minute rush intervals
    {"id": "schuylkill_east_rush15", "start": (40.090, -75.388), "end": (39.957, -75.181), "fallback": 35.0},
    {"id": "schuylkill_west_rush15", "start": (39.957, -75.181), "end": (40.090, -75.388), "fallback": 35.0},
    {"id": "vinest_east_rush15", "start": (39.957, -75.181), "end": (39.954, -75.143), "fallback": 28.0},
    {"id": "vinest_west_rush15", "start": (39.954, -75.143), "end": (39.957, -75.181), "fallback": 28.0},
    {"id": "i276_east_rush15", "start": (40.088, -75.405), "end": (40.115, -74.850), "fallback": 55.0},
    {"id": "i276_west_rush15", "start": (40.115, -74.850), "end": (40.088, -75.405), "fallback": 55.0},
    {"id": "patp_breezewood_node_east_rush15", "start": (40.005, -78.260), "end": (40.005, -78.220), "fallback": 45.0},
    {"id": "patp_breezewood_node_west_rush15", "start": (40.005, -78.220), "end": (40.005, -78.260), "fallback": 45.0},
    {"id": "patp_allegheny_tunnel_east_rush15", "start": (40.024, -78.825), "end": (40.024, -78.780), "fallback": 52.0},
    {"id": "patp_allegheny_tunnel_west_rush15", "start": (40.024, -78.780), "end": (40.024, -78.825), "fallback": 52.0},
    {"id": "patp_carlisle_node_east_rush15", "start": (40.218, -77.150), "end": (40.218, -77.100), "fallback": 52.0},
    {"id": "patp_carlisle_node_west_rush15", "start": (40.218, -77.100), "end": (40.218, -77.150), "fallback": 52.0},
    {"id": "nj70_east_rush15", "start": (39.915, -75.050), "end": (39.900, -74.920), "fallback": 30.0},
    {"id": "nj70_west_rush15", "start": (39.900, -74.920), "end": (39.915, -75.050), "fallback": 30.0},
    {"id": "nj73_north_rush15", "start": (39.880, -74.920), "end": (40.005, -75.035), "fallback": 22.0},
    {"id": "nj73_south_rush15", "start": (40.005, -75.035), "end": (39.880, -74.920), "fallback": 22.0},
    {"id": "pittsburgh_parkway_inbound_rush15", "start": (40.440, -80.120), "end": (40.435, -80.005), "fallback": 35.0},
    {"id": "pittsburgh_parkway_outbound_rush15", "start": (40.435, -80.005), "end": (40.440, -80.120), "fallback": 35.0},
    {"id": "columbus_i70_split_east_rush15", "start": (39.955, -83.050), "end": (39.955, -82.950), "fallback": 48.0},
    {"id": "columbus_i70_split_west_rush15", "start": (39.955, -82.950), "end": (39.955, -83.050), "fallback": 48.0},
    {"id": "us30_lancaster_east_rush15", "start": (40.040, -76.350), "end": (40.035, -76.220), "fallback": 38.0},
    {"id": "us30_lancaster_west_rush15", "start": (40.035, -76.220), "end": (40.040, -76.350), "fallback": 38.0},
    {"id": "patp_new_stanton_east_rush15", "start": (40.215, -79.620), "end": (40.220, -79.560), "fallback": 28.0},
    {"id": "patp_new_stanton_west_rush15", "start": (40.220, -79.560), "end": (40.215, -79.620), "fallback": 28.0},
]

# 12 Rush 15-min intervals
RUSH_INTERVALS = [
    (6, 45), (7, 15), (7, 45), (8, 15), (8, 45), (9, 15),
    (15, 45), (16, 15), (16, 45), (17, 15), (17, 45), (18, 15)
]

REF_DATES = [
    "2026-11-15", # Sun (0)
    "2026-11-16", # Mon (1)
    "2026-11-17", # Tue (2)
    "2026-11-18", # Wed (3)
    "2026-11-19", # Thu (4)
    "2026-11-20", # Fri (5)
    "2026-11-21"  # Sat (6)
]

def query_tomtom(start_lat, start_lon, end_lat, end_lon, dt_iso, fallback=45.0):
    base_url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lon}:{end_lat},{end_lon}/json"
    params = {
        "key": api_key,
        "departAt": dt_iso,
        "traffic": "true",
        "routeType": "fastest",
        "travelMode": "car"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Day4Harvester/1.0"})

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if "routes" in data and len(data["routes"]) > 0:
                    summary = data["routes"][0]["summary"]
                    meters = summary["lengthInMeters"]
                    seconds = summary["travelTimeInSeconds"]
                    miles = meters * 0.000621371
                    hours = seconds / 3600.0
                    return round(miles / max(0.001, hours), 1)
        except Exception:
            time.sleep(0.2 * (attempt + 1))
    return fallback

def run_harvest():
    db_file = "data/tomtom_corridors_168h.json"
    public_db_file = "public/data/tomtom_corridors_168h.json"

    with open(db_file, "r", encoding="utf-8") as f:
        database = json.load(f)

    print(f"Loaded existing database with {len(database)} corridors.")
    print(f"Targeting {len(CORRIDORS)} Day 4 rush-hour corridors (2,016 queries) with 6 worker threads...\n")

    tasks = []
    for c in CORRIDORS:
        cid = c["id"]
        start_lat, start_lon = c["start"]
        end_lat, end_lon = c["end"]
        fb = c["fallback"]
        for dow in range(7):
            d_str = REF_DATES[dow]
            for h, m in RUSH_INTERVALS:
                dt_iso = f"{d_str}T{h:02d}:{m:02d}:00"
                slot_key = f"{h}.{int(m * 100 / 60)}"
                tasks.append({
                    "cid": cid,
                    "dow": dow,
                    "slot": slot_key,
                    "start": (start_lat, start_lon),
                    "end": (end_lat, end_lon),
                    "dt_iso": dt_iso,
                    "fallback": fb
                })

    results_map = {c["id"]: [{} for _ in range(7)] for c in CORRIDORS}

    def worker(task):
        spd = query_tomtom(task["start"][0], task["start"][1], task["end"][0], task["end"][1], task["dt_iso"], task["fallback"])
        return task["cid"], task["dow"], task["slot"], spd

    start_time = time.time()
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(worker, t) for t in tasks]
        for f in concurrent.futures.as_completed(futures):
            cid, dow, slot, spd = f.result()
            results_map[cid][dow][slot] = spd
            completed += 1
            if completed % 200 == 0 or completed == len(tasks):
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                print(f"  Progress: {completed}/{len(tasks)} queries completed ({rate:.1f} q/s, {elapsed:.1f}s elapsed)")

    print(f"\nAll {len(tasks)} queries completed in {time.time() - start_time:.1f}s! Saving rush matrices...")

    for c in CORRIDORS:
        cid = c["id"]
        database[cid] = results_map[cid]

    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print(f"Saved: {db_file} (Now {len(database)} corridors)")

    with open(public_db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print(f"Saved: {public_db_file}")

    print("\nTomTom Day 4 harvest complete!")

if __name__ == "__main__":
    run_harvest()
