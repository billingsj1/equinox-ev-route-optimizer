"""
TomTom Day 4 Quota Harvester (Backfill Wave 2 + Fast-Charger Offshoots Part 1):
Strictly follows the 5-Day x 25-Timestamp Protocol.

Part A: Backfill Remaining 7 Segments from Day 2 (490 calls):
  - I-81: Shippensburg -> Chambersburg Northbound
  - I-79: Washington PA <-> Canonsburg (North & South)
  - I-79: Canonsburg <-> Bridgeville (North & South)
  - I-79: Bridgeville <-> Neville Island / Sewickley (North & South)
  7 segments * 5 days * 14 timestamps = 490 calls.

Part B: First 8 Fast-Charger Arterial Offshoots (15 directed segments / 1,875 calls):
  1. Electrify America - Belle Vernon, PA (Tri-County Plaza / I-70 Exit 42)
  2. Sheetz - New Stanton, PA (I-70 / PA Turnpike Interchange)
  3. EVgo - Pilot Travel Center - Belmont, OH (I-70 Exit 208)
  4. IONNA - Cambridge, OH (I-70 Exit 178)
  5. Sheetz - Cambridge, OH (I-70 Exit 176)
  6. Tesla Supercharger - Somerset, PA (PA Turnpike Exit 110)
  7. Electrify America - Washington, PA (Washington Crown Center / I-70 Exit 19B)
  8. EVgo - Chartiers Valley / Bridgeville, PA (Inbound)
  15 segments * 5 days * 25 timestamps = 1,875 calls.

Total calls: 490 + 1,875 = 2,365 calls (135 buffer below 2,500 limit).
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

# PART A: 7 Backfill Segments
BACKFILL_CORRIDORS = [
    {"id": "i81_shippensburg_to_chambersburg_north", "start": (39.935, -77.660), "end": (40.050, -77.520), "fallback": 55.0},
    {"id": "i79_washington_to_canonsburg_north", "start": (40.180, -80.220), "end": (40.260, -80.190), "fallback": 60.0},
    {"id": "i79_washington_to_canonsburg_south", "start": (40.260, -80.190), "end": (40.180, -80.220), "fallback": 60.0},
    {"id": "i79_canonsburg_to_bridgeville_north", "start": (40.260, -80.190), "end": (40.350, -80.110), "fallback": 55.0},
    {"id": "i79_canonsburg_to_bridgeville_south", "start": (40.350, -80.110), "end": (40.260, -80.190), "fallback": 55.0},
    {"id": "i79_bridgeville_to_sewickley_north", "start": (40.350, -80.110), "end": (40.540, -80.180), "fallback": 50.0},
    {"id": "i79_bridgeville_to_sewickley_south", "start": (40.540, -80.180), "end": (40.350, -80.110), "fallback": 50.0},
]
assert len(BACKFILL_CORRIDORS) == 7

# PART B: 15 Charger Arterial Segments
CHARGER_CORRIDORS = [
    # 1. EA Belle Vernon (I-70 Exit 42 to plaza)
    {"id": "ea_belle_vernon_inbound", "start": (40.125, -79.865), "end": (40.138, -79.878), "fallback": 25.0},
    {"id": "ea_belle_vernon_outbound", "start": (40.138, -79.878), "end": (40.125, -79.865), "fallback": 25.0},

    # 2. Sheetz New Stanton (I-70/PA Turnpike to Sheetz)
    {"id": "sheetz_new_stanton_inbound", "start": (40.220, -79.590), "end": (40.215, -79.605), "fallback": 20.0},
    {"id": "sheetz_new_stanton_outbound", "start": (40.215, -79.605), "end": (40.220, -79.590), "fallback": 20.0},

    # 3. Pilot Travel Center / EVgo Belmont OH (I-70 Exit 208)
    {"id": "evgo_pilot_belmont_inbound", "start": (40.035, -81.010), "end": (40.040, -81.015), "fallback": 22.0},
    {"id": "evgo_pilot_belmont_outbound", "start": (40.040, -81.015), "end": (40.035, -81.010), "fallback": 22.0},

    # 4. IONNA Cambridge OH (I-70 Exit 178)
    {"id": "ionna_cambridge_inbound", "start": (40.035, -81.545), "end": (40.040, -81.542), "fallback": 22.0},
    {"id": "ionna_cambridge_outbound", "start": (40.040, -81.542), "end": (40.035, -81.545), "fallback": 22.0},

    # 5. Sheetz Cambridge OH (I-70 Exit 176)
    {"id": "sheetz_cambridge_inbound", "start": (40.030, -81.585), "end": (40.025, -81.580), "fallback": 20.0},
    {"id": "sheetz_cambridge_outbound", "start": (40.025, -81.580), "end": (40.030, -81.585), "fallback": 20.0},

    # 6. Tesla Supercharger Somerset PA (PA Turnpike Exit 110)
    {"id": "tesla_somerset_inbound", "start": (40.010, -79.075), "end": (40.018, -79.082), "fallback": 22.0},
    {"id": "tesla_somerset_outbound", "start": (40.018, -79.082), "end": (40.010, -79.075), "fallback": 22.0},

    # 7. EA Washington Crown Center PA (I-70 Exit 19B)
    {"id": "ea_washington_pa_inbound", "start": (40.165, -80.250), "end": (40.155, -80.265), "fallback": 20.0},
    {"id": "ea_washington_pa_outbound", "start": (40.155, -80.265), "end": (40.165, -80.250), "fallback": 20.0},

    # 8. EVgo Chartiers Valley / Bridgeville PA (Inbound)
    {"id": "evgo_bridgeville_inbound", "start": (40.355, -80.105), "end": (40.365, -80.095), "fallback": 22.0}
]
assert len(CHARGER_CORRIDORS) == 15

DAYS_MAP = {
    0: "2026-11-15", # Sun
    1: "2026-11-16", # Mon
    3: "2026-11-18", # Wed
    5: "2026-11-20", # Fri
    6: "2026-11-21"  # Sat
}

BACKFILL_HOURS = [
    10.0, 12.0, 14.0, 19.0, # Daytime
    22.0, 0.0, 2.0, 4.0,    # Night anchors
    6.5, 7.5, 8.5,          # AM peak half-hours
    15.5, 16.5, 17.5        # PM peak half-hours
]

FULL_25_HOURS = [
    6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, # 15 Daytime
    22.0, 0.0, 2.0, 4.0,                                                                     # 4 Night anchors
    6.5, 7.5, 8.5, 15.5, 16.5, 17.5                                                          # 6 Peak rush half-hours
]
assert len(FULL_25_HOURS) == 25

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
    # Part A tasks: 7 corridors * 5 days * 14 hours = 490 tasks
    for c in BACKFILL_CORRIDORS:
        cid = c["id"]
        for dow, d_str in DAYS_MAP.items():
            for h in BACKFILL_HOURS:
                int_part = int(h)
                min_part = int(round((h - int_part) * 60))
                tasks.append({
                    "cid": cid, "dow": dow, "h": h,
                    "start": c["start"], "end": c["end"],
                    "dt_iso": f"{d_str}T{int_part:02d}:{min_part:02d}:00",
                    "fallback": c["fallback"]
                })

    # Part B tasks: 15 corridors * 5 days * 25 hours = 1,875 tasks
    for c in CHARGER_CORRIDORS:
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

    print(f"Executing Day 4 Harvester: {len(tasks)} queries (490 backfill + 1,875 charger offshoots)...")
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

    # Process Backfill Corridors
    for c in BACKFILL_CORRIDORS:
        cid = c["id"]
        fb = c["fallback"]
        old_data = database.get(cid, [[fb]*24 for _ in range(7)])
        new_7x48 = []
        for dow in range(7):
            mapped_dow = 3 if dow in (2, 4) else dow
            h_dict = {}
            if len(old_data[mapped_dow]) == 48:
                for idx in range(48): h_dict[idx / 2.0] = old_data[mapped_dow][idx]
            else:
                for idx in range(min(24, len(old_data[mapped_dow]))): h_dict[float(idx)] = old_data[mapped_dow][idx]
            if cid in results and mapped_dow in results[cid]:
                for h_val, spd in results[cid][mapped_dow].items(): h_dict[h_val] = spd
            new_7x48.append(assemble_48_slots(h_dict, fb))
        database[cid] = new_7x48

    # Process New Charger Corridors
    for c in CHARGER_CORRIDORS:
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

    print(f"Updated database ({len(database)} corridors total). Day 4 harvest complete!")

if __name__ == "__main__":
    run_harvest()
