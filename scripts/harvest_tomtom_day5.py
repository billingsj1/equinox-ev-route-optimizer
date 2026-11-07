"""
TomTom Day 5 Quota Harvester (Fast-Charger Offshoots Part 2: 19 Directed Segments / 2,375 Calls):
Strictly follows the 5-Day x 25-Timestamp Protocol.

Segments:
  1. EVgo - Chartiers Valley / Bridgeville, PA (Outbound)
  2. Sheetz - Carlisle, PA (I-81 Exit 44 / Allen Rd) Inbound & Outbound
  3. Electrify America - Target / Mount Laurel, NJ (NJ Turnpike Exit 4) Inbound & Outbound
  4. Tesla / EA - Cherry Hill Mall, NJ (NJ-38) Inbound & Outbound
  5. Tesla Supercharger - Woodlyn, PA (I-95) Inbound & Outbound
  6. ChargePoint Flex - DeCamilla / Dillsburg, PA (US-15) Inbound & Outbound
  7. Sheetz - Zanesville, OH (I-70 Exit 155 / Underwood St) Inbound & Outbound
  8. EVgo - Ohio Valley Mall / St. Clairsville, OH (I-70 Exit 218) Inbound & Outbound
  9. Sheetz - Greensburg, PA (PA-66 / US-30) Inbound & Outbound
 10. Electrify America - Bedford, PA (PA Turnpike Exit 146 / US-220) Inbound & Outbound

Total calls: 19 directed segments * 5 days * 25 timestamps = 2,375 calls (125 buffer).
Assembles 48-slot half-hour matrices into data/tomtom_corridors_168h.json.
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
    # 1. EVgo Bridgeville Outbound
    {"id": "evgo_bridgeville_outbound", "start": (40.365, -80.095), "end": (40.355, -80.105), "fallback": 22.0},

    # 2. Sheetz Carlisle I-81 Exit 44
    {"id": "sheetz_carlisle_i81_inbound", "start": (40.185, -77.165), "end": (40.190, -77.175), "fallback": 20.0},
    {"id": "sheetz_carlisle_i81_outbound", "start": (40.190, -77.175), "end": (40.185, -77.165), "fallback": 20.0},

    # 3. Target Mount Laurel NJ
    {"id": "target_mt_laurel_inbound", "start": (39.945, -74.960), "end": (39.952, -74.968), "fallback": 20.0},
    {"id": "target_mt_laurel_outbound", "start": (39.952, -74.968), "end": (39.945, -74.960), "fallback": 20.0},

    # 4. Cherry Hill Mall NJ-38
    {"id": "cherry_hill_mall_inbound", "start": (39.938, -75.025), "end": (39.943, -75.018), "fallback": 22.0},
    {"id": "cherry_hill_mall_outbound", "start": (39.943, -75.018), "end": (39.938, -75.025), "fallback": 22.0},

    # 5. Woodlyn PA I-95
    {"id": "woodlyn_pa_inbound", "start": (39.875, -75.335), "end": (39.882, -75.340), "fallback": 25.0},
    {"id": "woodlyn_pa_outbound", "start": (39.882, -75.340), "end": (39.875, -75.335), "fallback": 25.0},

    # 6. DeCamilla Dillsburg US-15
    {"id": "decamilla_dillsburg_inbound", "start": (40.140, -77.015), "end": (40.145, -77.020), "fallback": 25.0},
    {"id": "decamilla_dillsburg_outbound", "start": (40.145, -77.020), "end": (40.140, -77.015), "fallback": 25.0},

    # 7. Sheetz Zanesville I-70 Exit 155
    {"id": "sheetz_zanesville_inbound", "start": (39.945, -82.005), "end": (39.950, -82.000), "fallback": 20.0},
    {"id": "sheetz_zanesville_outbound", "start": (39.950, -82.000), "end": (39.945, -82.005), "fallback": 20.0},

    # 8. EVgo St. Clairsville Ohio Valley Mall
    {"id": "evgo_st_clairsville_inbound", "start": (40.065, -80.855), "end": (40.070, -80.860), "fallback": 22.0},
    {"id": "evgo_st_clairsville_outbound", "start": (40.070, -80.860), "end": (40.065, -80.855), "fallback": 22.0},

    # 9. Sheetz Greensburg PA-66
    {"id": "sheetz_greensburg_inbound", "start": (40.315, -79.560), "end": (40.320, -79.555), "fallback": 22.0},
    {"id": "sheetz_greensburg_outbound", "start": (40.320, -79.555), "end": (40.315, -79.560), "fallback": 22.0},

    # 10. EA Bedford PA Turnpike Exit 146
    {"id": "ea_bedford_inbound", "start": (40.040, -78.505), "end": (40.048, -78.512), "fallback": 22.0},
    {"id": "ea_bedford_outbound", "start": (40.048, -78.512), "end": (40.040, -78.505), "fallback": 22.0}
]
assert len(CORRIDORS) == 19, f"Expected 19 corridors, got {len(CORRIDORS)}"

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

def query_tomtom(start_lat, start_lon, end_lat, end_lon, dt_iso, fallback=22.0):
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
    for c in CORRIDORS:
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

    print(f"Executing Day 5 Harvester: {len(tasks)} queries across {len(CORRIDORS)} corridors...")
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

    print(f"\nAll {len(tasks)} queries completed in {time.time() - start_time:.1f}s. Assembling matrices...")

    for c in CORRIDORS:
        cid = c["id"]
        fb = c["fallback"]
        new_7x48 = []
        for dow in range(7):
            mapped_dow = 3 if dow in (2, 4) else dow
            h_dict = results.get(cid, {}).get(mapped_dow, {})
            new_7x48.append(assemble_48_slots(h_dict, fb))
        database[cid] = new_7x48

    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    with open(public_db_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)

    print(f"Updated database ({len(database)} corridors total). Day 5 harvest complete!")

if __name__ == "__main__":
    run_harvest()
