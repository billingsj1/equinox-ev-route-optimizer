"""
TomTom Day 3 Quota Harvester (Backfill Wave 1: 35 Directed Segments / 2,450 Calls):
Strictly follows the 5-Day x 25-Timestamp Protocol.
Backfills the 14 missing timestamps for 35 key PA Turnpike and I-70/US-15 segments:
  - 5 Days: Sun (0), Mon (1), Wed (3, covers Tue/Thu), Fri (5), Sat (6)
  - Missing Timestamps (14):
      * Daytime: 10:00, 12:00, 14:00, 19:00
      * Night Anchors: 22:00, 0:00, 2:00, 4:00
      * Peak Rush Half-Hours: 6:30, 7:30, 8:30, 15:30, 16:30, 17:30

Total calls: 35 directed segments * 5 days * 14 timestamps = 2,450 calls (50 buffer).
Assembles full 48-slot half-hour matrices (0.0 to 23.5) into data/tomtom_corridors_168h.json.
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
    # 1. Bowmansville <-> Harrisburg West
    {"id": "patp_mainline_bowmansville_to_harrisburg_west", "start": (40.178, -75.980), "end": (40.222, -76.885), "fallback": 68.0},
    {"id": "patp_mainline_bowmansville_to_harrisburg_east", "start": (40.222, -76.885), "end": (40.178, -75.980), "fallback": 68.0},

    # 2. Harrisburg West <-> Carlisle
    {"id": "patp_mainline_harrisburg_to_carlisle_west", "start": (40.222, -76.885), "end": (40.221, -77.130), "fallback": 60.0},
    {"id": "patp_mainline_harrisburg_to_carlisle_east", "start": (40.221, -77.130), "end": (40.222, -76.885), "fallback": 60.0},

    # 3. Breezewood <-> Somerset
    {"id": "patp_mainline_breezewood_to_somerset_west", "start": (39.998, -78.243), "end": (40.005, -79.075), "fallback": 65.0},
    {"id": "patp_mainline_breezewood_to_somerset_east", "start": (40.005, -79.075), "end": (39.998, -78.243), "fallback": 65.0},

    # 4. Somerset <-> New Stanton
    {"id": "patp_mainline_somerset_to_newstanton_west", "start": (40.005, -79.075), "end": (40.220, -79.590), "fallback": 58.0},
    {"id": "patp_mainline_somerset_to_newstanton_east", "start": (40.220, -79.590), "end": (40.005, -79.075), "fallback": 58.0},

    # 5. Carlisle US-11 Sheetz Offshoot
    {"id": "carlisle_us11_offshoot_north", "start": (40.221, -77.130), "end": (40.201, -77.189), "fallback": 18.0},
    {"id": "carlisle_us11_offshoot_south", "start": (40.201, -77.189), "end": (40.221, -77.130), "fallback": 18.0},

    # 6. Breezewood US-30 EVgo Strip
    {"id": "breezewood_us30_offshoot_west", "start": (40.005, -78.236), "end": (39.998, -78.243), "fallback": 18.0},
    {"id": "breezewood_us30_offshoot_east", "start": (39.998, -78.243), "end": (40.005, -78.236), "fallback": 18.0},

    # 7. Irwin / North Huntingdon US-30 Offshoot
    {"id": "irwin_us30_offshoot_west", "start": (40.325, -79.715), "end": (40.328, -79.730), "fallback": 18.0},
    {"id": "irwin_us30_offshoot_east", "start": (40.328, -79.730), "end": (40.325, -79.715), "fallback": 18.0},

    # 8. Mid-County I-276 / I-476 Interchange
    {"id": "midcounty_i276_i476_west", "start": (40.115, -75.295), "end": (40.110, -75.335), "fallback": 30.0},
    {"id": "midcounty_i276_i476_east", "start": (40.110, -75.335), "end": (40.115, -75.295), "fallback": 30.0},

    # 9. Mt. Laurel NJ-73 Arterial Offshoot
    {"id": "mt_laurel_nj73_arterial_south", "start": (39.920, -74.960), "end": (39.932, -74.975), "fallback": 20.0},
    {"id": "mt_laurel_nj73_arterial_north", "start": (39.932, -74.975), "end": (39.920, -74.960), "fallback": 20.0},

    # 10. Columbus Outerbelt <-> Zanesville
    {"id": "columbus_to_zanesville_east", "start": (39.955, -82.855), "end": (39.940, -82.012), "fallback": 65.0},
    {"id": "columbus_to_zanesville_west", "start": (39.940, -82.012), "end": (39.955, -82.855), "fallback": 65.0},

    # 11. Zanesville <-> Cambridge / I-77
    {"id": "zanesville_to_cambridge_east", "start": (39.940, -82.012), "end": (40.032, -81.588), "fallback": 65.0},
    {"id": "zanesville_to_cambridge_west", "start": (40.032, -81.588), "end": (39.940, -82.012), "fallback": 65.0},

    # 12. Cambridge <-> Belmont
    {"id": "cambridge_to_belmont_east", "start": (40.032, -81.588), "end": (40.031, -81.010), "fallback": 65.0},
    {"id": "cambridge_to_belmont_west", "start": (40.031, -81.010), "end": (40.032, -81.588), "fallback": 65.0},

    # 13. Belmont <-> Wheeling WV
    {"id": "belmont_to_wheeling_east", "start": (40.031, -81.010), "end": (40.065, -80.725), "fallback": 60.0},
    {"id": "belmont_to_wheeling_west", "start": (40.065, -80.725), "end": (40.031, -81.010), "fallback": 60.0},

    # 14. Wheeling <-> Washington PA
    {"id": "wheeling_to_washington_east", "start": (40.065, -80.725), "end": (40.170, -80.250), "fallback": 60.0},
    {"id": "wheeling_to_washington_west", "start": (40.170, -80.250), "end": (40.065, -80.725), "fallback": 60.0},

    # 15. US-15: Harrisburg West <-> Dillsburg
    {"id": "us15_harrisburg_to_dillsburg_south", "start": (40.222, -76.885), "end": (40.115, -77.030), "fallback": 50.0},
    {"id": "us15_harrisburg_to_dillsburg_north", "start": (40.115, -77.030), "end": (40.222, -76.885), "fallback": 50.0},

    # 16. US-15: Dillsburg <-> Gettysburg
    {"id": "us15_dillsburg_to_gettysburg_south", "start": (40.115, -77.030), "end": (39.830, -77.230), "fallback": 55.0},
    {"id": "us15_dillsburg_to_gettysburg_north", "start": (39.830, -77.230), "end": (40.115, -77.030), "fallback": 55.0},

    # 17. I-81: Carlisle <-> Shippensburg
    {"id": "i81_carlisle_to_shippensburg_south", "start": (40.200, -77.190), "end": (40.050, -77.520), "fallback": 55.0},
    {"id": "i81_carlisle_to_shippensburg_north", "start": (40.050, -77.520), "end": (40.200, -77.190), "fallback": 55.0},

    # 18. I-81: Shippensburg <-> Chambersburg (Southbound)
    {"id": "i81_shippensburg_to_chambersburg_south", "start": (40.050, -77.520), "end": (39.935, -77.660), "fallback": 55.0}
]

assert len(CORRIDORS) == 35, f"Expected exactly 35 corridors, got {len(CORRIDORS)}"

DAYS_MAP = {
    0: "2026-11-15", # Sun
    1: "2026-11-16", # Mon
    3: "2026-11-18", # Wed (midweek covers Tue/Wed/Thu)
    5: "2026-11-20", # Fri
    6: "2026-11-21"  # Sat
}

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
            time.sleep(0.3 * (attempt + 1))
    return fallback

def run_harvest():
    db_file = "data/tomtom_corridors_168h.json"
    public_db_file = "public/data/tomtom_corridors_168h.json"

    with open(db_file, "r", encoding="utf-8") as f:
        database = json.load(f)

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

    print(f"Executing Day 3 Harvester: {len(tasks)} queries across {len(CORRIDORS)} corridors...")
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
            if completed % 100 == 0 or completed == len(tasks):
                elapsed = time.time() - start_time
                print(f"  Progress: {completed}/{len(tasks)} queries completed ({elapsed:.1f}s)")

    print(f"\nAll {len(tasks)} queries completed in {time.time() - start_time:.1f}s. Assembling 48-slot matrices...")

    for c in CORRIDORS:
        cid = c["id"]
        fb = c["fallback"]
        old_data = database.get(cid, [[fb]*24 for _ in range(7)])
        new_7x48 = []

        for dow in range(7):
            mapped_dow = dow
            if dow in (2, 4):
                mapped_dow = 3

            h_dict = {}
            if len(old_data[mapped_dow]) == 48:
                for idx in range(48):
                    h_dict[idx / 2.0] = old_data[mapped_dow][idx]
            else:
                for idx in range(min(24, len(old_data[mapped_dow]))):
                    h_dict[float(idx)] = old_data[mapped_dow][idx]

            if cid in results and mapped_dow in results[cid]:
                for h_val, spd in results[cid][mapped_dow].items():
                    h_dict[h_val] = spd

            known_times = sorted(h_dict.keys())
            slots_48 = [fb] * 48
            for slot_idx in range(48):
                t_val = slot_idx / 2.0
                if t_val in h_dict:
                    slots_48[slot_idx] = h_dict[t_val]
                else:
                    prev_t = max([kt for kt in known_times if kt <= t_val], default=min(known_times))
                    next_t = min([kt for kt in known_times if kt >= t_val], default=max(known_times))
                    if prev_t == next_t:
                        slots_48[slot_idx] = h_dict[prev_t]
                    else:
                        frac = (t_val - prev_t) / (next_t - prev_t)
                        slots_48[slot_idx] = round(h_dict[prev_t] + frac * (h_dict[next_t] - h_dict[prev_t]), 1)

            new_7x48.append(slots_48)

        database[cid] = new_7x48

    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print(f"Updated: {db_file}")

    with open(public_db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print(f"Updated: {public_db_file}")

    print("\nTomTom Day 3 harvest complete!")

if __name__ == "__main__":
    run_harvest()
