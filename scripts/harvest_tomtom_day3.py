"""
TomTom Day 3 Quota Harvester (Priority 3, Day 3):
Harvests 12 key Fast Charger Arterials & Interchanges across PA, OH, NJ, MD
across 7 Days of the Week (168 hours) using the 2,500 daily free allowance.

Corridors:
  1. Somerset Plaza / PA-601 Sheetz offshoot (somerset_sheetz_offshoot_north / south)
  2. Bedford Interchange / US-220 Sheetz & EVgo offshoot (bedford_sheetz_offshoot_north / south)
  3. Donegal Interchange / PA-31 Sheetz offshoot (donegal_sheetz_offshoot_east / west)
  4. Bowmansville MP 289 Service Plaza approach offshoot (bowmansville_plaza_offshoot_east / west)
  5. New Stanton Interchange / PA-66 bypass offshoot (new_stanton_offshoot_east / west)
  6. Washington PA Mercedes-Benz HPC / Beau St arterial (washington_pa_beau_st_east / west)
  7. Belmont OH Pilot Travel Center arterial offshoot (belmont_pilot_offshoot_north / south)
  8. Cambridge OH Southgate Rd / Sheetz arterial offshoot (cambridge_sheetz_offshoot_north / south)
  9. Zanesville OH Maysville Pike / Sheetz offshoot (zanesville_sheetz_offshoot_north / south)
 10. Hagerstown MD / I-70 US-40 Dual Hwy arterial (hagerstown_us40_arterial_east / west)
 11. Frederick MD / I-70 MD-85 Buckeystown Pike arterial (frederick_md85_arterial_north / south)
 12. Cherry Hill NJ / NJ-38 & Haddonfield Rd arterial (cherry_hill_nj38_arterial_east / west)

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
    # 1. Somerset PA-601 Sheetz offshoot
    {"id": "somerset_sheetz_offshoot_north", "start": (40.015, -79.075), "end": (40.030, -79.080), "fallback": 22.0},
    {"id": "somerset_sheetz_offshoot_south", "start": (40.030, -79.080), "end": (40.015, -79.075), "fallback": 22.0},

    # 2. Bedford US-220 Sheetz offshoot
    {"id": "bedford_sheetz_offshoot_north", "start": (40.035, -78.510), "end": (40.050, -78.515), "fallback": 25.0},
    {"id": "bedford_sheetz_offshoot_south", "start": (40.050, -78.515), "end": (40.035, -78.510), "fallback": 25.0},

    # 3. Donegal PA-31 Sheetz offshoot
    {"id": "donegal_sheetz_offshoot_east", "start": (40.110, -79.375), "end": (40.115, -79.385), "fallback": 22.0},
    {"id": "donegal_sheetz_offshoot_west", "start": (40.115, -79.385), "end": (40.110, -79.375), "fallback": 22.0},

    # 4. Bowmansville MP 289 approach offshoot
    {"id": "bowmansville_plaza_offshoot_east", "start": (40.178, -75.980), "end": (40.182, -75.965), "fallback": 25.0},
    {"id": "bowmansville_plaza_offshoot_west", "start": (40.182, -75.965), "end": (40.178, -75.980), "fallback": 25.0},

    # 5. New Stanton PA-66 bypass offshoot
    {"id": "new_stanton_offshoot_east", "start": (40.220, -79.590), "end": (40.228, -79.605), "fallback": 25.0},
    {"id": "new_stanton_offshoot_west", "start": (40.228, -79.605), "end": (40.220, -79.590), "fallback": 25.0},

    # 6. Washington PA Beau St arterial
    {"id": "washington_pa_beau_st_east", "start": (40.174, -80.246), "end": (40.170, -80.220), "fallback": 24.0},
    {"id": "washington_pa_beau_st_west", "start": (40.170, -80.220), "end": (40.174, -80.246), "fallback": 24.0},

    # 7. Belmont Pilot Travel Center arterial offshoot
    {"id": "belmont_pilot_offshoot_north", "start": (40.031, -81.010), "end": (40.040, -81.015), "fallback": 25.0},
    {"id": "belmont_pilot_offshoot_south", "start": (40.040, -81.015), "end": (40.031, -81.010), "fallback": 25.0},

    # 8. Cambridge Southgate Rd Sheetz arterial offshoot
    {"id": "cambridge_sheetz_offshoot_north", "start": (40.032, -81.588), "end": (40.020, -81.590), "fallback": 25.0},
    {"id": "cambridge_sheetz_offshoot_south", "start": (40.020, -81.590), "end": (40.032, -81.588), "fallback": 25.0},

    # 9. Zanesville Maysville Pike Sheetz offshoot
    {"id": "zanesville_sheetz_offshoot_north", "start": (39.940, -82.012), "end": (39.925, -82.015), "fallback": 24.0},
    {"id": "zanesville_sheetz_offshoot_south", "start": (39.925, -82.015), "end": (39.940, -82.012), "fallback": 24.0},

    # 10. Hagerstown US-40 Dual Hwy arterial
    {"id": "hagerstown_us40_arterial_east", "start": (39.635, -77.720), "end": (39.630, -77.670), "fallback": 30.0},
    {"id": "hagerstown_us40_arterial_west", "start": (39.630, -77.670), "end": (39.635, -77.720), "fallback": 30.0},

    # 11. Frederick MD-85 Buckeystown Pike arterial
    {"id": "frederick_md85_arterial_south", "start": (39.400, -77.410), "end": (39.380, -77.415), "fallback": 28.0},
    {"id": "frederick_md85_arterial_north", "start": (39.380, -77.415), "end": (39.400, -77.410), "fallback": 28.0},

    # 12. Cherry Hill NJ-38 & Haddonfield Rd arterial
    {"id": "cherry_hill_nj38_arterial_east", "start": (39.940, -75.040), "end": (39.945, -75.000), "fallback": 28.0},
    {"id": "cherry_hill_nj38_arterial_west", "start": (39.945, -75.000), "end": (39.940, -75.040), "fallback": 28.0},
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

def query_tomtom(start_lat, start_lon, end_lat, end_lon, dt_iso, fallback=25.0):
    base_url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lon}:{end_lat},{end_lon}/json"
    params = {
        "key": api_key,
        "departAt": dt_iso,
        "traffic": "true",
        "routeType": "fastest",
        "travelMode": "car"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Day3Harvester/1.0"})

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

def interpolate_24h(hourly_dict, fallback=25.0):
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
    print(f"Targeting {len(CORRIDORS)} Day 3 corridors (2,016 queries) with 6 worker threads...\n")

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

    print("\nTomTom Day 3 harvest complete!")

if __name__ == "__main__":
    run_harvest()
