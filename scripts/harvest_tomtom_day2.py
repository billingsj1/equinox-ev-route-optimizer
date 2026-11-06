"""
TomTom Day 2 Quota Harvester (Priority 3, Day 2):
Harvests 12 key Ohio & Western PA Highway Segments & Interchanges
across 7 Days of the Week (168 hours) using the 2,500 daily free allowance.

Corridors:
  1. I-70: Columbus Outerbelt <-> Zanesville (columbus_to_zanesville_east / west)
  2. I-70: Zanesville <-> Cambridge / I-77 (zanesville_to_cambridge_east / west)
  3. I-70: Cambridge <-> St. Clairsville / Belmont (cambridge_to_belmont_east / west)
  4. I-70: Belmont <-> Wheeling WV / Ohio River (belmont_to_wheeling_east / west)
  5. I-70: Wheeling <-> Washington PA / I-79 (wheeling_to_washington_east / west)
  6. I-79: Washington PA <-> Canonsburg / South Hills (i79_washington_to_canonsburg_north / south)
  7. I-79: Canonsburg <-> Bridgeville / I-376 Parkway West (i79_canonsburg_to_bridgeville_north / south)
  8. I-79: Bridgeville <-> Neville Island / Sewickley (i79_bridgeville_to_sewickley_north / south)
  9. I-81: Carlisle Interchange <-> Shippensburg (i81_carlisle_to_shippensburg_north / south)
 10. I-81: Shippensburg <-> Chambersburg / US-30 (i81_shippensburg_to_chambersburg_north / south)
 11. US-15: Harrisburg West <-> Dillsburg Bypass (us15_harrisburg_to_dillsburg_north / south)
 12. US-15: Dillsburg <-> Gettysburg / US-30 (us15_dillsburg_to_gettysburg_north / south)

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
    # 1. Columbus Outerbelt <-> Zanesville
    {"id": "columbus_to_zanesville_east", "start": (39.955, -82.855), "end": (39.940, -82.012), "fallback": 65.0},
    {"id": "columbus_to_zanesville_west", "start": (39.940, -82.012), "end": (39.955, -82.855), "fallback": 65.0},

    # 2. Zanesville <-> Cambridge / I-77
    {"id": "zanesville_to_cambridge_east", "start": (39.940, -82.012), "end": (40.032, -81.588), "fallback": 65.0},
    {"id": "zanesville_to_cambridge_west", "start": (40.032, -81.588), "end": (39.940, -82.012), "fallback": 65.0},

    # 3. Cambridge <-> Belmont
    {"id": "cambridge_to_belmont_east", "start": (40.032, -81.588), "end": (40.031, -81.010), "fallback": 65.0},
    {"id": "cambridge_to_belmont_west", "start": (40.031, -81.010), "end": (40.032, -81.588), "fallback": 65.0},

    # 4. Belmont <-> Wheeling WV
    {"id": "belmont_to_wheeling_east", "start": (40.031, -81.010), "end": (40.065, -80.725), "fallback": 60.0},
    {"id": "belmont_to_wheeling_west", "start": (40.065, -80.725), "end": (40.031, -81.010), "fallback": 60.0},

    # 5. Wheeling <-> Washington PA
    {"id": "wheeling_to_washington_east", "start": (40.065, -80.725), "end": (40.174, -80.246), "fallback": 60.0},
    {"id": "wheeling_to_washington_west", "start": (40.174, -80.246), "end": (40.065, -80.725), "fallback": 60.0},

    # 6. Washington PA <-> Canonsburg
    {"id": "i79_washington_to_canonsburg_north", "start": (40.174, -80.246), "end": (40.262, -80.188), "fallback": 62.0},
    {"id": "i79_washington_to_canonsburg_south", "start": (40.262, -80.188), "end": (40.174, -80.246), "fallback": 62.0},

    # 7. Canonsburg <-> Bridgeville
    {"id": "i79_canonsburg_to_bridgeville_north", "start": (40.262, -80.188), "end": (40.355, -80.108), "fallback": 60.0},
    {"id": "i79_canonsburg_to_bridgeville_south", "start": (40.355, -80.108), "end": (40.262, -80.188), "fallback": 60.0},

    # 8. Bridgeville <-> Sewickley
    {"id": "i79_bridgeville_to_sewickley_north", "start": (40.355, -80.108), "end": (40.540, -80.185), "fallback": 58.0},
    {"id": "i79_bridgeville_to_sewickley_south", "start": (40.540, -80.185), "end": (40.355, -80.108), "fallback": 58.0},

    # 9. Carlisle <-> Shippensburg
    {"id": "i81_carlisle_to_shippensburg_south", "start": (40.218, -77.130), "end": (40.050, -77.520), "fallback": 65.0},
    {"id": "i81_carlisle_to_shippensburg_north", "start": (40.050, -77.520), "end": (40.218, -77.130), "fallback": 65.0},

    # 10. Shippensburg <-> Chambersburg
    {"id": "i81_shippensburg_to_chambersburg_south", "start": (40.050, -77.520), "end": (39.935, -77.660), "fallback": 65.0},
    {"id": "i81_shippensburg_to_chambersburg_north", "start": (39.935, -77.660), "end": (40.050, -77.520), "fallback": 65.0},

    # 11. Harrisburg West <-> Dillsburg Bypass
    {"id": "us15_harrisburg_to_dillsburg_south", "start": (40.222, -76.885), "end": (40.110, -77.035), "fallback": 50.0},
    {"id": "us15_harrisburg_to_dillsburg_north", "start": (40.110, -77.035), "end": (40.222, -76.885), "fallback": 50.0},

    # 12. Dillsburg <-> Gettysburg
    {"id": "us15_dillsburg_to_gettysburg_south", "start": (40.110, -77.035), "end": (39.830, -77.230), "fallback": 55.0},
    {"id": "us15_dillsburg_to_gettysburg_north", "start": (39.830, -77.230), "end": (40.110, -77.035), "fallback": 55.0},
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
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Day2Harvester/1.0"})

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
    print(f"Targeting {len(CORRIDORS)} Day 2 corridors (2,016 queries) with 6 worker threads...\n")

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

    print("\nTomTom Day 2 harvest complete!")

if __name__ == "__main__":
    run_harvest()
