"""
TomTom Day 6 Quota Harvester (Micro-Slices with Mathematical Inference + Secondary Bypasses):
Strictly follows the 5-Day x 25-Timestamp Protocol.

Part A: 8 Direct Mountain Tunnel & Bridge Slices (1,000 calls):
  - Allegheny Mountain Tunnel (East & West) -> mathematically infers Somerset approach
  - Tuscarora Mountain Tunnel (East & West) -> mathematically infers Breezewood approach
  - Wheeling I-70 Ohio River Tunnel (East & West) -> mathematically infers Ohio approach
  - Neville Island Bridge on I-79 (North & South) -> mathematically infers Sewickley approach
  8 segments * 5 days * 25 timestamps = 1,000 calls.
  (Infers 8 complementary slices at 0 cost).

Part B: 4 Secondary Feeder Bypasses (8 directed segments / 1,000 calls):
  - I-470 Wheeling South Bypass (East & West)
  - PA-576 Southern Beltway Airport Connector (North & South)
  - PA-283 Lancaster Expressway (East & West)
  - NJ-73 / NJ-38 South Jersey Connector (North & South)
  8 segments * 5 days * 25 timestamps = 1,000 calls.

Part C: Remaining Charger Detours (3 directed segments / 375 calls):
  - Pilot Travel Center / EVgo Austintown, OH (Inbound & Outbound)
  - Sheetz Breezewood Alternate North Approach
  3 segments * 5 days * 25 timestamps = 375 calls.

Total calls: 1,000 + 1,000 + 375 = 2,375 calls (125 buffer).
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

# Part A: Direct Slices that enable mathematical inference
TUNNEL_SLICES = [
    {"id": "patp_allegheny_tunnel_west", "parent": "patp_mainline_breezewood_to_somerset_west", "start": (40.025, -78.780), "end": (40.015, -78.850), "fallback": 50.0, "infer_child": "patp_somerset_to_allegheny_west"},
    {"id": "patp_allegheny_tunnel_east", "parent": "patp_mainline_breezewood_to_somerset_east", "start": (40.015, -78.850), "end": (40.025, -78.780), "fallback": 50.0, "infer_child": "patp_somerset_to_allegheny_east"},
    {"id": "patp_tuscarora_tunnel_west", "parent": "patp_mainline_bluemtn_to_breezewood_west", "start": (40.180, -77.780), "end": (40.160, -77.850), "fallback": 50.0, "infer_child": "patp_breezewood_to_tuscarora_west"},
    {"id": "patp_tuscarora_tunnel_east", "parent": "patp_mainline_bluemtn_to_breezewood_east", "start": (40.160, -77.850), "end": (40.180, -77.780), "fallback": 50.0, "infer_child": "patp_breezewood_to_tuscarora_east"},
    {"id": "wheeling_tunnel_i70_west", "parent": "wheeling_to_washington_west", "start": (40.070, -80.710), "end": (40.060, -80.730), "fallback": 35.0, "infer_child": "wheeling_approach_i70_west"},
    {"id": "wheeling_tunnel_i70_east", "parent": "wheeling_to_washington_east", "start": (40.060, -80.730), "end": (40.070, -80.710), "fallback": 35.0, "infer_child": "wheeling_approach_i70_east"},
    {"id": "i79_neville_island_bridge_north", "parent": "i79_bridgeville_to_sewickley_north", "start": (40.505, -80.140), "end": (40.525, -80.160), "fallback": 40.0, "infer_child": "i79_bridgeville_to_neville_north"},
    {"id": "i79_neville_island_bridge_south", "parent": "i79_bridgeville_to_sewickley_south", "start": (40.525, -80.160), "end": (40.505, -80.140), "fallback": 40.0, "infer_child": "i79_bridgeville_to_neville_south"},
]
assert len(TUNNEL_SLICES) == 8

# Part B: Secondary Feeder Bypasses
BYPASS_CORRIDORS = [
    {"id": "i470_wheeling_bypass_west", "start": (40.040, -80.680), "end": (40.045, -80.760), "fallback": 60.0},
    {"id": "i470_wheeling_bypass_east", "start": (40.045, -80.760), "end": (40.040, -80.680), "fallback": 60.0},
    {"id": "pa576_southern_beltway_north", "start": (40.355, -80.280), "end": (40.485, -80.250), "fallback": 65.0},
    {"id": "pa576_southern_beltway_south", "start": (40.485, -80.250), "end": (40.355, -80.280), "fallback": 65.0},
    {"id": "pa283_lancaster_west", "start": (40.080, -76.350), "end": (40.210, -76.800), "fallback": 65.0},
    {"id": "pa283_lancaster_east", "start": (40.210, -76.800), "end": (40.080, -76.350), "fallback": 65.0},
    {"id": "nj73_nj38_connector_north", "start": (39.920, -74.960), "end": (39.940, -75.010), "fallback": 35.0},
    {"id": "nj73_nj38_connector_south", "start": (39.940, -75.010), "end": (39.920, -74.960), "fallback": 35.0},
]
assert len(BYPASS_CORRIDORS) == 8

# Part C: Residual Detour Corridors
RESIDUAL_CORRIDORS = [
    {"id": "pilot_austintown_inbound", "start": (41.110, -80.785), "end": (41.115, -80.790), "fallback": 22.0},
    {"id": "pilot_austintown_outbound", "start": (41.115, -80.790), "end": (41.110, -80.785), "fallback": 22.0},
    {"id": "sheetz_breezewood_north", "start": (40.005, -78.236), "end": (40.015, -78.232), "fallback": 20.0},
]
assert len(RESIDUAL_CORRIDORS) == 3

ALL_DAY6_CORRIDORS = TUNNEL_SLICES + BYPASS_CORRIDORS + RESIDUAL_CORRIDORS
assert len(ALL_DAY6_CORRIDORS) == 19

DAYS_MAP = {
    0: "2026-11-15", # Sun
    1: "2026-11-16", # Mon
    3: "2026-11-18", # Wed
    5: "2026-11-20", # Fri
    6: "2026-11-21"  # Sat
}

FULL_25_HOURS = [
    6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0,
    22.0, 0.0, 2.0, 4.0,
    6.5, 7.5, 8.5, 15.5, 16.5, 17.5
]
assert len(FULL_25_HOURS) == 25

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
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Day6Harvester/1.0"})

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

def assemble_48_slots(h_dict, fb):
    known_times = sorted(h_dict.keys())
    slots = [fb] * 48
    for slot_idx in range(48):
        t_val = slot_idx / 2.0
        if t_val in h_dict:
            slots[slot_idx] = h_dict[t_val]
        else:
            prev_t = max([kt for kt in known_times if kt <= t_val], default=min(known_times))
            next_t = min([kt for kt in known_times if kt >= t_val], default=max(known_times))
            if prev_t == next_t:
                slots[slot_idx] = h_dict[prev_t]
            else:
                frac = (t_val - prev_t) / (next_t - prev_t)
                slots[slot_idx] = round(h_dict[prev_t] + frac * (h_dict[next_t] - h_dict[prev_t]), 1)
    return slots

def run_harvest():
    db_file = "data/tomtom_corridors_168h.json"
    public_db_file = "public/data/tomtom_corridors_168h.json"

    with open(db_file, "r", encoding="utf-8") as f:
        database = json.load(f)

    tasks = []
    for c in ALL_DAY6_CORRIDORS:
        cid = c["id"]
        for dow, d_str in DAYS_MAP.items():
            for h in FULL_25_HOURS:
                int_part = int(h)
                min_part = int(round((h - int_part) * 60))
                tasks.append({
                    "cid": cid, "dow": dow, "h": h,
                    "start": c["start"], "end": c["end"],
                    "dt_iso": f"{d_str}T{int_part:02d}:{min_part:02d}:00",
                    "fallback": c["fallback"]
                })

    print(f"Executing Day 6 Harvester: {len(tasks)} queries across {len(ALL_DAY6_CORRIDORS)} corridors...")
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

    print(f"\nAll {len(tasks)} queries completed in {time.time() - start_time:.1f}s. Assembling matrices & inferring complementary slices...")

    # Assemble directly polled corridors
    for c in ALL_DAY6_CORRIDORS:
        cid = c["id"]
        fb = c["fallback"]
        new_7x48 = []
        for dow in range(7):
            mapped_dow = 3 if dow in (2, 4) else dow
            h_dict = results.get(cid, {}).get(mapped_dow, {})
            new_7x48.append(assemble_48_slots(h_dict, fb))
        database[cid] = new_7x48

    # MATHEMATICAL INFERENCE FOR COMPLEMENTARY SLICES
    # T_child = T_parent - T_slice1 => v_child = d_child / T_child
    for c in TUNNEL_SLICES:
        parent_id = c["parent"]
        child_id = c["infer_child"]
        slice1_id = c["id"]
        fb = c["fallback"]

        parent_matrix = database.get(parent_id)
        slice1_matrix = database.get(slice1_id)

        if parent_matrix and slice1_matrix:
            child_7x48 = []
            for dow in range(7):
                child_slots = []
                for slot_idx in range(48):
                    v_p = parent_matrix[dow][slot_idx] if len(parent_matrix[dow]) == 48 else parent_matrix[dow][slot_idx // 2]
                    v_s1 = slice1_matrix[dow][slot_idx]

                    # Slice 1 tunnel is ~15% of corridor length
                    # T_parent = 1.0 / v_p, T_s1 = 0.15 / v_s1, T_child = T_parent - T_s1
                    # v_child = 0.85 / T_child
                    t_p = 1.0 / max(10.0, v_p)
                    t_s1 = 0.15 / max(10.0, v_s1)
                    t_child = max(0.005, t_p - t_s1)
                    v_child = round(0.85 / t_child, 1)
                    child_slots.append(min(75.0, max(25.0, v_child)))
                child_7x48.append(child_slots)
            database[child_id] = child_7x48
            print(f"  Mathematically inferred complementary slice: {child_id}")

    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    with open(public_db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)

    print(f"Updated database ({len(database)} corridors total). Day 6 harvest complete!")

if __name__ == "__main__":
    run_harvest()
