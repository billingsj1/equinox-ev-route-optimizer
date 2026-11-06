"""
TomTom Day 5 Quota Harvester (Priority 3, Day 5):
Harvests 12 Secondary Feeder Corridors & Regional Bypasses across PA, NJ, OH, WV
across 7 Days of the Week (168 hours) using the 2,500 daily free allowance.

Corridors:
  1. US-22: Steubenville OH <-> Weirton WV / Ohio River (us22_steubenville_to_weirton_east / west)
  2. US-22: Weirton WV <-> PA Border / PA-576 merge (us22_weirton_to_paborder_east / west)
  3. PA-576: US-22 Interchange <-> Pittsburgh Airport / I-376 (pa576_us22_to_airport_north / south)
  4. PA-576: Pittsburgh Airport <-> I-79 Southern Beltway (pa576_airport_to_i79_north / south)
  5. US-30: Lancaster <-> York PA / Susquehanna River (us30_lancaster_to_york_east / west)
  6. US-30: York PA <-> Gettysburg (us30_york_to_gettysburg_east / west)
  7. I-83: York PA <-> Maryland Border (i83_york_to_mdborder_north / south)
  8. I-68: Cumberland MD <-> Sideling Hill Mountain (i68_cumberland_to_sideling_east / west)
  9. I-68: Sideling Hill <-> Hancock / I-70 merge (i68_sideling_to_hancock_east / west)
 10. Walt Whitman Bridge approach corridor (waltwhitman_approach_east / west)
 11. Tacony-Palmyra Bridge approach corridor (tacony_approach_north / south)
 12. Delaware Memorial Bridge approach corridor (delaware_approach_east / west)

Total calls: 24 directed corridors * 7 days * 12 sampled hours = 2,016 calls.
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
    # 1. US-22: Steubenville OH <-> Weirton WV
    {"id": "us22_steubenville_to_weirton_east", "start": (40.365, -80.620), "end": (40.380, -80.580), "fallback": 50.0},
    {"id": "us22_steubenville_to_weirton_west", "start": (40.380, -80.580), "end": (40.365, -80.620), "fallback": 50.0},

    # 2. US-22: Weirton WV <-> PA Border / PA-576
    {"id": "us22_weirton_to_paborder_east", "start": (40.380, -80.580), "end": (40.410, -80.460), "fallback": 55.0},
    {"id": "us22_weirton_to_paborder_west", "start": (40.410, -80.460), "end": (40.380, -80.580), "fallback": 55.0},

    # 3. PA-576: US-22 <-> Pittsburgh Airport
    {"id": "pa576_us22_to_airport_north", "start": (40.410, -80.460), "end": (40.490, -80.260), "fallback": 65.0},
    {"id": "pa576_us22_to_airport_south", "start": (40.490, -80.260), "end": (40.410, -80.460), "fallback": 65.0},

    # 4. PA-576: Airport <-> I-79 Southern Beltway
    {"id": "pa576_airport_to_i79_north", "start": (40.490, -80.260), "end": (40.315, -80.170), "fallback": 65.0},
    {"id": "pa576_airport_to_i79_south", "start": (40.315, -80.170), "end": (40.490, -80.260), "fallback": 65.0},

    # 5. US-30: Lancaster <-> York PA
    {"id": "us30_lancaster_to_york_west", "start": (40.040, -76.350), "end": (39.980, -76.720), "fallback": 55.0},
    {"id": "us30_lancaster_to_york_east", "start": (39.980, -76.720), "end": (40.040, -76.350), "fallback": 55.0},

    # 6. US-30: York PA <-> Gettysburg
    {"id": "us30_york_to_gettysburg_west", "start": (39.980, -76.720), "end": (39.830, -77.230), "fallback": 50.0},
    {"id": "us30_york_to_gettysburg_east", "start": (39.830, -77.230), "end": (39.980, -76.720), "fallback": 50.0},

    # 7. I-83: York PA <-> MD Border
    {"id": "i83_york_to_mdborder_south", "start": (39.950, -76.730), "end": (39.720, -76.650), "fallback": 65.0},
    {"id": "i83_york_to_mdborder_north", "start": (39.720, -76.650), "end": (39.950, -76.730), "fallback": 65.0},

    # 8. I-68: Cumberland MD <-> Sideling Hill
    {"id": "i68_cumberland_to_sideling_east", "start": (39.650, -78.760), "end": (39.715, -78.290), "fallback": 65.0},
    {"id": "i68_cumberland_to_sideling_west", "start": (39.715, -78.290), "end": (39.650, -78.760), "fallback": 65.0},

    # 9. I-68: Sideling Hill <-> Hancock I-70
    {"id": "i68_sideling_to_hancock_east", "start": (39.715, -78.290), "end": (39.700, -78.180), "fallback": 65.0},
    {"id": "i68_sideling_to_hancock_west", "start": (39.700, -78.180), "end": (39.715, -78.290), "fallback": 65.0},

    # 10. Walt Whitman approach corridor
    {"id": "waltwhitman_approach_east", "start": (39.905, -75.185), "end": (39.905, -75.125), "fallback": 40.0},
    {"id": "waltwhitman_approach_west", "start": (39.905, -75.125), "end": (39.905, -75.185), "fallback": 40.0},

    # 11. Tacony-Palmyra approach corridor
    {"id": "tacony_approach_north", "start": (40.010, -75.050), "end": (40.015, -75.025), "fallback": 35.0},
    {"id": "tacony_approach_south", "start": (40.015, -75.025), "end": (40.010, -75.050), "fallback": 35.0},

    # 12. Delaware Memorial approach corridor
    {"id": "delaware_approach_east", "start": (39.680, -75.550), "end": (39.695, -75.500), "fallback": 45.0},
    {"id": "delaware_approach_west", "start": (39.695, -75.500), "end": (39.680, -75.550), "fallback": 45.0},
]

SAMPLED_HOURS = [6, 7, 8, 9, 11, 13, 15, 16, 17, 18, 20, 23]

REF_DATES = [
    "2026-11-15", # Sun (0)
    "2026-11-16", # Mon (1)
    "2026-11-17", # Tue (2)
    "2026-11-18", # Wed (3)
    "2026-11-19", # Thu (4)
    "2026-11-20", # Fri (5)
    "2026-11-21"  # Sat (6)
]

def query_tomtom(start_lat, start_lon, end_lat, end_lon, dt_iso, fallback=55.0):
    base_url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lon}:{end_lat},{end_lon}/json"
    params = {
        "key": api_key,
        "departAt": dt_iso,
        "traffic": "true",
        "routeType": "fastest",
        "travelMode": "car"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Day5Harvester/1.0"})

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

def interpolate_24h(hourly_dict, fallback=55.0):
    full = [fallback] * 24
    known_hours = sorted(hourly_dict.keys())
    if not known_hours:
        return full
    for h in range(24):
        if h in hourly_dict:
            full[h] = hourly_dict[h]
        elif h < known_hours[0]:
            full[h] = hourly_dict[known_hours[0]]
        elif h > known_hours[-1]:
            full[h] = hourly_dict[known_hours[-1]]
        else:
            h_prev = max([k for k in known_hours if k < h])
            h_next = min([k for k in known_hours if k > h])
            frac = (h - h_prev) / (h_next - h_prev)
            full[h] = round(hourly_dict[h_prev] + frac * (hourly_dict[h_next] - hourly_dict[h_prev]), 1)
    return full

def run_harvest():
    db_file = "data/tomtom_corridors_168h.json"
    public_db_file = "public/data/tomtom_corridors_168h.json"

    with open(db_file, "r", encoding="utf-8") as f:
        database = json.load(f)

    print(f"Loaded existing database with {len(database)} corridors.")
    print(f"Targeting {len(CORRIDORS)} Day 5 corridors (2,016 queries) with 6 worker threads...\n")

    tasks = []
    for c in CORRIDORS:
        cid = c["id"]
        start_lat, start_lon = c["start"]
        end_lat, end_lon = c["end"]
        fb = c["fallback"]
        for dow in range(7):
            d_str = REF_DATES[dow]
            for h in SAMPLED_HOURS:
                dt_iso = f"{d_str}T{h:02d}:00:00"
                tasks.append({
                    "cid": cid,
                    "dow": dow,
                    "h": h,
                    "start": (start_lat, start_lon),
                    "end": (end_lat, end_lon),
                    "dt_iso": dt_iso,
                    "fallback": fb
                })

    results_map = {c["id"]: [{} for _ in range(7)] for c in CORRIDORS}

    def worker(task):
        spd = query_tomtom(task["start"][0], task["start"][1], task["end"][0], task["end"][1], task["dt_iso"], task["fallback"])
        return task["cid"], task["dow"], task["h"], spd

    start_time = time.time()
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(worker, t) for t in tasks]
        for f in concurrent.futures.as_completed(futures):
            cid, dow, h, spd = f.result()
            results_map[cid][dow][h] = spd
            completed += 1
            if completed % 200 == 0 or completed == len(tasks):
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                print(f"  Progress: {completed}/{len(tasks)} queries completed ({rate:.1f} q/s, {elapsed:.1f}s elapsed)")

    print(f"\nAll {len(tasks)} queries completed in {time.time() - start_time:.1f}s! Assembling 168h matrices...")

    for c in CORRIDORS:
        cid = c["id"]
        fb = c["fallback"]
        c_matrix = []
        for dow in range(7):
            hourly_dict = results_map[cid][dow]
            full_24h = interpolate_24h(hourly_dict, fb)
            c_matrix.append(full_24h)
        database[cid] = c_matrix

    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print(f"Saved: {db_file} (Now {len(database)} corridors)")

    with open(public_db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print(f"Saved: {public_db_file}")

    print("\nTomTom Day 5 harvest complete!")

if __name__ == "__main__":
    run_harvest()
