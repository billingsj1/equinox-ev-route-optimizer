"""
Immediate Quota Exhaustion Harvester (Day 2 Remaining Quota: 420 Calls):
Backfills the 3 most critical PA Turnpike Mainline Inter-Exit Slices:
  1. Carlisle <-> Blue Mountain (mountain grade & Kittatinny/Blue Mtn tunnel approach)
  2. Blue Mountain <-> Breezewood (mountain grade & Tuscarora tunnel approach)
  3. Valley Forge <-> Bowmansville (Schuylkill/KOP commuter interface)

Fetches the missing 14 timestamps across 5 days (Sun, Mon, Wed, Fri, Sat):
  - Missing Daytime Hours: 10, 12, 14, 19
  - Missing Night Anchors: 22, 0, 2, 4
  - Missing Rush Half-Hours: 6.5 (6:30a), 7.5 (7:30a), 8.5 (8:30a), 15.5 (3:30p), 16.5 (4:30p), 17.5 (5:30p)

Total: 6 directed corridors * 5 days * 14 timestamps = 420 calls.
Leaves a 64-call buffer to strictly protect the 2,500 daily allowance.
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
    # 1. Carlisle <-> Blue Mountain
    {"id": "patp_mainline_carlisle_to_bluemtn_west", "start": (40.221, -77.130), "end": (40.225, -77.620), "fallback": 55.0},
    {"id": "patp_mainline_carlisle_to_bluemtn_east", "start": (40.225, -77.620), "end": (40.221, -77.130), "fallback": 55.0},

    # 2. Blue Mountain <-> Breezewood
    {"id": "patp_mainline_bluemtn_to_breezewood_west", "start": (40.225, -77.620), "end": (39.998, -78.243), "fallback": 55.0},
    {"id": "patp_mainline_bluemtn_to_breezewood_east", "start": (39.998, -78.243), "end": (40.225, -77.620), "fallback": 55.0},

    # 3. Valley Forge <-> Bowmansville
    {"id": "patp_mainline_vf_to_bowmansville_west", "start": (40.088, -75.405), "end": (40.178, -75.980), "fallback": 65.0},
    {"id": "patp_mainline_vf_to_bowmansville_east", "start": (40.178, -75.980), "end": (40.088, -75.405), "fallback": 65.0},
]

# 5 Days (Reference week)
DAYS_MAP = {
    0: "2026-11-15", # Sun
    1: "2026-11-16", # Mon
    3: "2026-11-18", # Wed (midweek for Tue/Wed/Thu)
    5: "2026-11-20", # Fri
    6: "2026-11-21"  # Sat
}

# The 14 missing timestamps
MISSING_HOURS = [
    10.0, 12.0, 14.0, 19.0, # Daytime
    22.0, 0.0, 2.0, 4.0,    # Night anchors
    6.5, 7.5, 8.5,          # AM peak half-hours
    15.5, 16.5, 17.5        # PM peak half-hours
]

def query_tomtom(start_lat, start_lon, end_lat, end_lon, dt_iso, fallback=60.0):
    base_url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lon}:{end_lat},{end_lon}/json"
    params = {
        "key": api_key,
        "departAt": dt_iso,
        "traffic": "true",
        "routeType": "fastest",
        "travelMode": "car"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Backfill/1.0"})

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
            time.sleep(0.3 * (attempt + 1))
    return fallback

def run_backfill():
    db_file = "data/tomtom_corridors_168h.json"
    public_db_file = "public/data/tomtom_corridors_168h.json"

    with open(db_file, "r", encoding="utf-8") as f:
        database = json.load(f)

    # Build tasks: 6 corridors * 5 days * 14 timestamps = 420 tasks
    tasks = []
    for c in CORRIDORS:
        cid = c["id"]
        start_lat, start_lon = c["start"]
        end_lat, end_lon = c["end"]
        fb = c["fallback"]
        for dow, d_str in DAYS_MAP.items():
            for h in MISSING_HOURS:
                int_part = int(h)
                min_part = int(round((h - int_part) * 60))
                dt_iso = f"{d_str}T{int_part:02d}:{min_part:02d}:00"
                tasks.append({
                    "cid": cid,
                    "dow": dow,
                    "h": h,
                    "start": (start_lat, start_lon),
                    "end": (end_lat, end_lon),
                    "dt_iso": dt_iso,
                    "fallback": fb
                })

    print(f"Executing immediate backfill: {len(tasks)} queries across {len(CORRIDORS)} corridors...")
    start_time = time.time()
    results = {}
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {
            executor.submit(
                query_tomtom,
                t["start"][0], t["start"][1],
                t["end"][0], t["end"][1],
                t["dt_iso"], t["fallback"]
            ): t for t in tasks
        }
        for f in concurrent.futures.as_completed(future_map):
            t = future_map[f]
            spd = f.result()
            cid = t["cid"]
            dow = t["dow"]
            h = t["h"]
            results.setdefault(cid, {}).setdefault(dow, {})[h] = spd
            completed += 1
            if completed % 50 == 0 or completed == len(tasks):
                elapsed = time.time() - start_time
                print(f"  Progress: {completed}/{len(tasks)} queries completed ({elapsed:.1f}s)")

    print(f"\nAll {len(tasks)} queries completed in {time.time() - start_time:.1f}s.")

    # Now assemble 48-slot half-hour array for each corridor
    # 48 slots: 0.0, 0.5, 1.0, 1.5, ..., 23.5
    for c in CORRIDORS:
        cid = c["id"]
        fb = c["fallback"]
        old_7x24 = database.get(cid, [[fb]*24 for _ in range(7)])
        new_7x48 = []

        for dow in range(7):
            mapped_dow = dow
            if dow in (2, 4): # Tue and Thu use Wed
                mapped_dow = 3

            # Build full dictionary of all measured points for mapped_dow
            # 1. Existing 24h entries
            h_dict = {}
            for h in range(24):
                if h < len(old_7x24[mapped_dow]):
                    h_dict[float(h)] = old_7x24[mapped_dow][h]

            # 2. Overwrite / insert newly fetched missing hours
            if cid in results and mapped_dow in results[cid]:
                for h_val, spd in results[cid][mapped_dow].items():
                    h_dict[h_val] = spd

            # 3. Create 48-slot array by linear interpolation across measured timestamps
            known_times = sorted(h_dict.keys())
            slots_48 = [fb] * 48
            for slot_idx in range(48):
                t_val = slot_idx / 2.0
                if t_val in h_dict:
                    slots_48[slot_idx] = h_dict[t_val]
                else:
                    # Interpolate between surrounding known timestamps
                    prev_t = max([kt for kt in known_times if kt <= t_val], default=min(known_times))
                    next_t = min([kt for kt in known_times if kt >= t_val], default=max(known_times))
                    if prev_t == next_t:
                        slots_48[slot_idx] = h_dict[prev_t]
                    else:
                        frac = (t_val - prev_t) / (next_t - prev_t)
                        slots_48[slot_idx] = round(h_dict[prev_t] + frac * (h_dict[next_t] - h_dict[prev_t]), 1)

            new_7x48.append(slots_48)

        database[cid] = new_7x48

    # Save to both locations
    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print(f"Updated: {db_file}")

    with open(public_db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print(f"Updated: {public_db_file}")

    # Print verification samples
    print("\nVerification of 48-slot Backfilled Speeds:")
    for c in CORRIDORS:
        cid = c["id"]
        # Wed (3) at 7:00, 7:30, 8:00, 8:30 AM (indices 14, 15, 16, 17)
        wed_700 = database[cid][3][14]
        wed_730 = database[cid][3][15]
        wed_800 = database[cid][3][16]
        wed_830 = database[cid][3][17]
        wed_1000 = database[cid][3][20]
        wed_1200 = database[cid][3][24]
        print(f"  {cid}: 7a={wed_700} | 7:30a={wed_730} | 8a={wed_800} | 8:30a={wed_830} | 10a={wed_1000} | 12p={wed_1200}")

if __name__ == "__main__":
    run_backfill()
