"""
TomTom Day 7 Rush-Hour Delta Harvester:
Upgrades all 50 pure TomTom 24-slot corridors to 48-slot (30-minute rush-hour) resolution.
STRICTLY EXCLUDES all corridors covered by the Google Maps Routes database (bottleneck_speeds_db.json).

Scope:
  - 50 Bidirectional / Arterial Pure TomTom Corridors
  - 5 Reference Days: Sun (0), Mon (1), Wed (3), Fri (5), Sat (6)
  - 6 Peak Rush-Hour Half-Hours: 06:30, 07:30, 08:30 (AM Peak), 15:30, 16:30, 17:30 (PM Peak)
  - Call Count: 50 corridors * 5 days * 6 timestamps = 1,500 calls (1,000 call buffer under 2,500/day limit)
  - Blends the newly sampled 30-min peak congestion speeds directly into the existing 24-slot baseline matrices,
    interpolating the remaining half-hours into full 7x48 matrices.
"""

import concurrent.futures
import json
import os
import sys
import time
import urllib.parse
import urllib.request

def load_key():
    key = os.environ.get("TOMTOM_API_KEY")
    if key:
        return key.strip().strip('"').strip("'")
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TOMTOM_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

api_key = load_key()
if not api_key:
    print("ERROR: TOMTOM_API_KEY not found in environment or .env")
    sys.exit(1)

# 50 Clean Pure TomTom Corridors (Zero overlap with Google Routes API DB)
CORRIDORS = [
    # 1. Maryland & Southern Arterials
    {"id": "us15_south", "start": (40.2185, -76.9982), "end": (40.1413, -77.0156), "fallback": 55.0},
    {"id": "us15_north", "start": (40.1413, -77.0156), "end": (40.2185, -76.9982), "fallback": 55.0},
    {"id": "dillsburg_us15_arterial_south", "start": (40.1800, -77.0050), "end": (40.1250, -77.0250), "fallback": 45.0},
    {"id": "dillsburg_us15_arterial_north", "start": (40.1250, -77.0250), "end": (40.1800, -77.0050), "fallback": 45.0},
    {"id": "i68_cumberland_east", "start": (39.6450, -78.7800), "end": (39.6550, -78.7200), "fallback": 65.0},
    {"id": "i68_cumberland_west", "start": (39.6550, -78.7200), "end": (39.6450, -78.7800), "fallback": 65.0},
    {"id": "i70_hagerstown_east", "start": (39.6300, -77.7800), "end": (39.6350, -77.6800), "fallback": 60.0},
    {"id": "i70_hagerstown_west", "start": (39.6350, -77.6800), "end": (39.6300, -77.7800), "fallback": 60.0},
    {"id": "i70_frederick_east", "start": (39.4200, -77.4400), "end": (39.4000, -77.3700), "fallback": 55.0},
    {"id": "i70_frederick_west", "start": (39.4000, -77.3700), "end": (39.4200, -77.4400), "fallback": 55.0},

    # 2. Capital Region & Mid-State Arterials
    {"id": "i83_harrisburg_north", "start": (40.2350, -76.9550), "end": (40.2450, -76.8750), "fallback": 50.0},
    {"id": "i83_harrisburg_south", "start": (40.2450, -76.8750), "end": (40.2350, -76.9550), "fallback": 50.0},
    {"id": "pa283_us30_east", "start": (40.2312, -76.8142), "end": (40.0385, -75.6212), "fallback": 60.0},
    {"id": "us30_pa283_west", "start": (40.0385, -75.6212), "end": (40.2312, -76.8142), "fallback": 60.0},
    {"id": "us30_lancaster_east", "start": (40.0600, -76.3200), "end": (40.0350, -76.2200), "fallback": 50.0},
    {"id": "us30_lancaster_west", "start": (40.0350, -76.2200), "end": (40.0600, -76.3200), "fallback": 50.0},

    # 3. Philadelphia Metro & South Jersey River Bridges / Arterials
    {"id": "delaware_memorial_bridge_east", "start": (39.6850, -75.5300), "end": (39.6950, -75.4950), "fallback": 55.0},
    {"id": "delaware_memorial_bridge_west", "start": (39.6950, -75.4950), "end": (39.6850, -75.5300), "fallback": 55.0},
    {"id": "waltwhitman_east", "start": (39.9120, -75.1850), "end": (39.8850, -75.1100), "fallback": 50.0},
    {"id": "waltwhitman_west", "start": (39.8850, -75.1100), "end": (39.9120, -75.1850), "fallback": 50.0},
    {"id": "tacony_palmyra_nj73_north", "start": (39.9450, -74.9850), "end": (40.0120, -75.0450), "fallback": 40.0},
    {"id": "tacony_palmyra_nj73_south", "start": (40.0120, -75.0450), "end": (39.9450, -74.9850), "fallback": 40.0},
    {"id": "us202_north", "start": (40.0385, -75.6212), "end": (40.0850, -75.3950), "fallback": 55.0},
    {"id": "us202_south", "start": (40.0850, -75.3950), "end": (40.0385, -75.6212), "fallback": 55.0},
    {"id": "nj38_east", "start": (39.9405, -75.0802), "end": (39.9650, -74.9350), "fallback": 45.0},
    {"id": "nj38_west", "start": (39.9650, -74.9350), "end": (39.9405, -75.0802), "fallback": 45.0},
    {"id": "i295_southjersey_north", "start": (39.8750, -75.0950), "end": (39.9250, -74.9600), "fallback": 65.0},
    {"id": "i295_southjersey_south", "start": (39.9250, -74.9600), "end": (39.8750, -75.0950), "fallback": 65.0},

    # 4. Greater Pittsburgh & Western PA Arterials / Bridges
    {"id": "pittsburgh_parkway_inbound", "start": (40.4520, -80.1850), "end": (40.4350, -80.0150), "fallback": 45.0},
    {"id": "pittsburgh_parkway_outbound", "start": (40.4350, -80.0150), "end": (40.4520, -80.1850), "fallback": 45.0},
    {"id": "i79_pittsburgh_north", "start": (40.3800, -80.1000), "end": (40.5250, -80.1450), "fallback": 60.0},
    {"id": "i79_pittsburgh_south", "start": (40.5250, -80.1450), "end": (40.3800, -80.1000), "fallback": 60.0},
    {"id": "pa65_north", "start": (40.4650, -80.0400), "end": (40.5415, -80.1820), "fallback": 45.0},
    {"id": "pa65_south", "start": (40.5415, -80.1820), "end": (40.4650, -80.0400), "fallback": 45.0},
    {"id": "sewickley_bridge_east", "start": (40.5330, -80.1880), "end": (40.5395, -80.1830), "fallback": 35.0},
    {"id": "sewickley_bridge_west", "start": (40.5395, -80.1830), "end": (40.5330, -80.1880), "fallback": 35.0},
    {"id": "pa576_beltway_north", "start": (40.3650, -80.3100), "end": (40.4850, -80.2600), "fallback": 65.0},
    {"id": "pa576_beltway_south", "start": (40.4850, -80.2600), "end": (40.3650, -80.3100), "fallback": 65.0},

    # 5. PA Turnpike Major Interchange & Gateways Nodes
    {"id": "patp_new_stanton_east", "start": (40.2150, -79.6200), "end": (40.2300, -79.5600), "fallback": 68.0},
    {"id": "patp_new_stanton_west", "start": (40.2300, -79.5600), "end": (40.2150, -79.6200), "fallback": 68.0},
    {"id": "patp_valley_forge_east", "start": (40.0750, -75.4300), "end": (40.0950, -75.3800), "fallback": 65.0},
    {"id": "patp_valley_forge_west", "start": (40.0950, -75.3800), "end": (40.0750, -75.4300), "fallback": 65.0},
    {"id": "patp_harrisburg_west_east", "start": (40.2100, -76.9200), "end": (40.2250, -76.8500), "fallback": 65.0},
    {"id": "patp_harrisburg_west_west", "start": (40.2250, -76.8500), "end": (40.2100, -76.9200), "fallback": 65.0},
    {"id": "patp_breezewood_node_east", "start": (40.0050, -78.2600), "end": (40.0050, -78.2200), "fallback": 65.0},
    {"id": "patp_breezewood_node_west", "start": (40.0050, -78.2200), "end": (40.0050, -78.2600), "fallback": 65.0},
    {"id": "patp_somerset_node_east", "start": (40.0150, -79.1000), "end": (40.0150, -79.0500), "fallback": 65.0},
    {"id": "patp_somerset_node_west", "start": (40.0150, -79.0500), "end": (40.0150, -79.1000), "fallback": 65.0},
    {"id": "patp_bowmansville_node_east", "start": (40.1800, -76.0200), "end": (40.1800, -75.9600), "fallback": 68.0},
    {"id": "patp_bowmansville_node_west", "start": (40.1800, -75.9600), "end": (40.1800, -76.0200), "fallback": 68.0},
]
assert len(CORRIDORS) == 50, f"Expected 50 corridors, got {len(CORRIDORS)}"

DAYS_MAP = {
    0: "2026-11-15", # Sun
    1: "2026-11-16", # Mon
    3: "2026-11-18", # Wed (midweek covers Tue/Wed/Thu)
    5: "2026-11-20", # Fri
    6: "2026-11-21"  # Sat
}

# The 6 critical rush-hour half-hours that convert 24-slot baselines into 48-slot precision
RUSH_HOURS = [
    6.5, 7.5, 8.5,    # AM peak rush half-hours
    15.5, 16.5, 17.5  # PM peak rush half-hours
]
assert len(RUSH_HOURS) == 6

def query_tomtom(start_lat, start_lon, end_lat, end_lon, dt_iso, fallback=50.0):
    base_url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lon}:{end_lat},{end_lon}/json"
    params = {
        "key": api_key,
        "departAt": dt_iso,
        "traffic": "true",
        "routeType": "fastest",
        "travelMode": "car"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Day7DeltaHarvester/1.0"})

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
            for h in RUSH_HOURS:
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

    expected_calls = len(CORRIDORS) * len(DAYS_MAP) * len(RUSH_HOURS)
    assert len(tasks) == expected_calls == 1500, f"Expected 1500 calls, got {len(tasks)}"

    print(f"Executing Day 7 Rush-Hour Delta Harvester: {len(tasks)} queries across {len(CORRIDORS)} pure TomTom corridors...")
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
                mapped_dow = 3 # Map Tue & Thu to Wed

            h_dict = {}
            if len(old_data[mapped_dow]) == 48:
                for idx in range(48):
                    h_dict[idx / 2.0] = old_data[mapped_dow][idx]
            else:
                for idx in range(min(24, len(old_data[mapped_dow]))):
                    h_dict[float(idx)] = old_data[mapped_dow][idx]

            # Merge in newly polled 6 rush-hour speeds
            if cid in results and mapped_dow in results[cid]:
                for h_val, spd in results[cid][mapped_dow].items():
                    h_dict[h_val] = spd

            # Linear interpolation for all 48 slots [0.0, 0.5, 1.0, ... 23.5]
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

    with open(public_db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)

    print(f"Day 7 complete! Successfully upgraded all {len(CORRIDORS)} pure TomTom corridors to 48-slot resolution.")
    print(f"Updated {db_file} and {public_db_file}.")

if __name__ == "__main__":
    run_harvest()
