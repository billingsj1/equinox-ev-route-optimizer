"""
TomTom Day 1 Quota Harvester (Priority 3):
Harvests 12 key PA Turnpike Mainline Inter-Exit Slices and Top Arterial Charger Offshoots
across 7 Days of the Week (168 hours) using the 2,500 daily free allowance.

Corridors:
  1. Valley Forge <-> Bowmansville (patp_mainline_vf_to_bowmansville_east / west)
  2. Bowmansville <-> Harrisburg West (patp_mainline_bowmansville_to_harrisburg_east / west)
  3. Harrisburg West <-> Carlisle (patp_mainline_harrisburg_to_carlisle_east / west)
  4. Carlisle <-> Blue Mountain (patp_mainline_carlisle_to_bluemtn_east / west)
  5. Blue Mountain <-> Breezewood (patp_mainline_bluemtn_to_breezewood_east / west)
  6. Breezewood <-> Somerset (patp_mainline_breezewood_to_somerset_east / west)
  7. Somerset <-> New Stanton (patp_mainline_somerset_to_newstanton_east / west)
  8. Carlisle US-11 Sheetz Offshoot (carlisle_us11_offshoot_north / south)
  9. Breezewood US-30 EVgo Strip (breezewood_us30_offshoot_east / west)
 10. Irwin / North Huntingdon US-30 Offshoot (irwin_us30_offshoot_east / west)
 11. Mid-County I-276 / I-476 Interchange (midcounty_i276_i476_east / west)
 12. Mt. Laurel NJ-73 Arterial Offshoot (mt_laurel_nj73_arterial_north / south)

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
    # 1. Valley Forge <-> Bowmansville
    {"id": "patp_mainline_vf_to_bowmansville_west", "start": (40.088, -75.405), "end": (40.178, -75.980), "fallback": 65.0},
    {"id": "patp_mainline_vf_to_bowmansville_east", "start": (40.178, -75.980), "end": (40.088, -75.405), "fallback": 65.0},

    # 2. Bowmansville <-> Harrisburg West
    {"id": "patp_mainline_bowmansville_to_harrisburg_west", "start": (40.178, -75.980), "end": (40.222, -76.885), "fallback": 68.0},
    {"id": "patp_mainline_bowmansville_to_harrisburg_east", "start": (40.222, -76.885), "end": (40.178, -75.980), "fallback": 68.0},

    # 3. Harrisburg West <-> Carlisle
    {"id": "patp_mainline_harrisburg_to_carlisle_west", "start": (40.222, -76.885), "end": (40.221, -77.130), "fallback": 60.0},
    {"id": "patp_mainline_harrisburg_to_carlisle_east", "start": (40.221, -77.130), "end": (40.222, -76.885), "fallback": 60.0},

    # 4. Carlisle <-> Blue Mountain
    {"id": "patp_mainline_carlisle_to_bluemtn_west", "start": (40.221, -77.130), "end": (40.225, -77.620), "fallback": 55.0},
    {"id": "patp_mainline_carlisle_to_bluemtn_east", "start": (40.225, -77.620), "end": (40.221, -77.130), "fallback": 55.0},

    # 5. Blue Mountain <-> Breezewood
    {"id": "patp_mainline_bluemtn_to_breezewood_west", "start": (40.225, -77.620), "end": (40.005, -78.235), "fallback": 55.0},
    {"id": "patp_mainline_bluemtn_to_breezewood_east", "start": (40.005, -78.235), "end": (40.225, -77.620), "fallback": 55.0},

    # 6. Breezewood <-> Somerset
    {"id": "patp_mainline_breezewood_to_somerset_west", "start": (40.005, -78.235), "end": (40.015, -79.075), "fallback": 65.0},
    {"id": "patp_mainline_breezewood_to_somerset_east", "start": (40.015, -79.075), "end": (40.005, -78.235), "fallback": 65.0},

    # 7. Somerset <-> New Stanton
    {"id": "patp_mainline_somerset_to_newstanton_west", "start": (40.015, -79.075), "end": (40.220, -79.590), "fallback": 58.0},
    {"id": "patp_mainline_somerset_to_newstanton_east", "start": (40.220, -79.590), "end": (40.015, -79.075), "fallback": 58.0},

    # 8. Carlisle US-11 Sheetz Offshoot
    {"id": "carlisle_us11_offshoot_north", "start": (40.221, -77.134), "end": (40.237, -77.158), "fallback": 20.0},
    {"id": "carlisle_us11_offshoot_south", "start": (40.237, -77.158), "end": (40.221, -77.134), "fallback": 20.0},

    # 9. Breezewood US-30 EVgo Strip
    {"id": "breezewood_us30_offshoot_west", "start": (40.005, -78.236), "end": (39.998, -78.243), "fallback": 18.0},
    {"id": "breezewood_us30_offshoot_east", "start": (39.998, -78.243), "end": (40.005, -78.236), "fallback": 18.0},

    # 10. Irwin / North Huntingdon US-30 Offshoot
    {"id": "irwin_us30_offshoot_west", "start": (40.325, -79.715), "end": (40.328, -79.730), "fallback": 18.0},
    {"id": "irwin_us30_offshoot_east", "start": (40.328, -79.730), "end": (40.325, -79.715), "fallback": 18.0},

    # 11. Mid-County I-276 / I-476 Interchange
    {"id": "midcounty_i276_i476_west", "start": (40.115, -75.295), "end": (40.110, -75.335), "fallback": 30.0},
    {"id": "midcounty_i276_i476_east", "start": (40.110, -75.335), "end": (40.115, -75.295), "fallback": 30.0},

    # 12. Mt. Laurel NJ-73 Arterial Offshoot
    {"id": "mt_laurel_nj73_arterial_south", "start": (39.920, -74.960), "end": (39.932, -74.975), "fallback": 20.0},
    {"id": "mt_laurel_nj73_arterial_north", "start": (39.932, -74.975), "end": (39.920, -74.960), "fallback": 20.0},
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
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Day1Harvester/1.0"})

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

def interpolate_24h(hourly_dict, fallback=60.0):
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
    print(f"Targeting {len(CORRIDORS)} new corridors (2,016 queries) with 6 worker threads...\n")

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

    print("\nTomTom Day 1 harvest complete!")

if __name__ == "__main__":
    run_harvest()
