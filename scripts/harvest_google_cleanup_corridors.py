"""
Google Maps Routes API Cleanup Harvest (8 Legacy Corridors / 16 Directional Segments).

Fixes swapped-carriageway U-turn asymmetries, off-highway coordinates, and TomTom-only
corridors (I-276 PA Turnpike, NJ Turnpike, NJ-73, Tacony-Palmyra Bridge, Zanesville I-70,
Wheeling I-70, Washington PA I-70, and Sewickley I-79) using verified forward/reverse
OSRM mainline coordinates.
"""

import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request

from harvest_google_mainline_corridors import (
    ALL_HOURS,
    DATES,
    interpolate_day_24h,
    load_key,
    query_google_route,
)

CLEANUP_CORRIDORS = [
    # 1. I-276 PA Turnpike (Valley Forge <-> Delaware River Bridge)
    {"id": "i276_paturnpike_east", "name": "I-276 PA Turnpike East (Valley Forge to NJ Border)", "start": (40.090918, -75.380454), "end": (40.114271, -74.820749), "min_ff": 55.0},
    {"id": "i276_paturnpike_west", "name": "I-276 PA Turnpike West (NJ Border to Valley Forge)", "start": (40.114348, -74.820711), "end": (40.091105, -75.380677), "min_ff": 55.0},
    # 2. NJ Turnpike (Exit 4 NJ-73 <-> Exit 6 I-276)
    {"id": "njturnpike_north", "name": "NJ Turnpike Northbound (Exit 4 to Exit 6)", "start": (39.934725, -74.948539), "end": (40.091005, -74.735245), "min_ff": 55.0},
    {"id": "njturnpike_south", "name": "NJ Turnpike Southbound (Exit 6 to Exit 4)", "start": (40.096487, -74.731006), "end": (39.933123, -74.950798), "min_ff": 55.0},
    # 3. NJ-73 (Marlton <-> NJ Turnpike Exit 4)
    {"id": "nj73_north", "name": "NJ-73 Northbound (Marlton to NJTP Exit 4)", "start": (39.890670, -74.925375), "end": (39.913921, -74.942775), "min_ff": 30.0},
    {"id": "nj73_south", "name": "NJ-73 Southbound (NJTP Exit 4 to Marlton)", "start": (39.913953, -74.942983), "end": (39.890499, -74.925449), "min_ff": 30.0},
    # 4. Tacony-Palmyra Bridge / NJ-73
    {"id": "tacony_palmyra_nj73_north", "name": "Tacony-Palmyra Bridge Northbound (Palmyra to Bridge)", "start": (39.995331, -75.025057), "end": (40.009000, -75.040000), "min_ff": 22.0},
    {"id": "tacony_palmyra_nj73_south", "name": "Tacony-Palmyra Bridge Southbound (Bridge to Palmyra)", "start": (40.009000, -75.040000), "end": (39.995331, -75.025057), "min_ff": 22.0},
    # 5. Zanesville I-70
    {"id": "zanesville_i70_east", "name": "I-70 East (Zanesville Mainline)", "start": (39.944216, -81.997264), "end": (39.949480, -81.964670), "min_ff": 50.0},
    {"id": "zanesville_i70_west", "name": "I-70 West (Zanesville Mainline)", "start": (39.949773, -81.965942), "end": (39.944233, -81.996553), "min_ff": 50.0},
    # 6. Wheeling I-70
    {"id": "wheeling_i70_east", "name": "I-70 East (Wheeling Mainline & Tunnel)", "start": (40.072344, -80.722558), "end": (40.044431, -80.619862), "min_ff": 45.0},
    {"id": "wheeling_i70_west", "name": "I-70 West (Wheeling Mainline & Tunnel)", "start": (40.044593, -80.619799), "end": (40.071767, -80.729442), "min_ff": 45.0},
    # 7. Washington PA I-70
    {"id": "washington_pa_i70_east", "name": "I-70 East (Washington PA Mainline)", "start": (40.136321, -80.319870), "end": (40.187454, -80.251100), "min_ff": 55.0},
    {"id": "washington_pa_i70_west", "name": "I-70 West (Washington PA Mainline)", "start": (40.187613, -80.251295), "end": (40.136934, -80.319614), "min_ff": 55.0},
    # 8. Sewickley I-79
    {"id": "sewickley_i79_north", "name": "I-79 North (Washington PA to Sewickley)", "start": (40.234848, -80.209224), "end": (40.516801, -80.133402), "min_ff": 55.0},
    {"id": "sewickley_i79_south", "name": "I-79 South (Sewickley to Washington PA)", "start": (40.514880, -80.134210), "end": (40.234983, -80.209513), "min_ff": 55.0},
]

STALE_SLICE_KEYS = [
    "columbus_i70_east_slice1",
    "columbus_i70_east_slice2",
    "columbus_i70_west_slice1",
    "columbus_i70_west_slice2",
    "washington_pa_i70_east_slice1",
    "washington_pa_i70_east_slice2",
    "washington_pa_i70_west_slice1",
    "washington_pa_i70_west_slice2",
]


def run_preflight(api_key):
    print("=== PRE-FLIGHT SANITY CHECK (16 CALLS, Wed 11:00 AM) ===")
    failures = []
    results_by_id = {}
    for c in CLEANUP_CORRIDORS:
        res = query_google_route(api_key, c["start"][0], c["start"][1], c["end"][0], c["end"][1], "2026-11-18T11:00:00-05:00")
        if not res:
            failures.append((c["id"], "NO_RESPONSE"))
            print(f"  FAIL {c['id']:35s}: NO RESPONSE")
            continue
        ok = res["free_flow_mph"] >= c["min_ff"]
        status = "OK  " if ok else "FAIL"
        if not ok:
            failures.append((c["id"], f"ff={res['free_flow_mph']} < {c['min_ff']}"))
        print(f"  {status} {c['id']:35s}: {res['distance_miles']:5.1f} mi | ff={res['free_flow_mph']:5.1f} mph | traffic={res['traffic_mph']:5.1f} mph")
        results_by_id[c["id"]] = res

    for i in range(0, len(CLEANUP_CORRIDORS), 2):
        fwd = CLEANUP_CORRIDORS[i]
        rev = CLEANUP_CORRIDORS[i + 1]
        if fwd["id"] in results_by_id and rev["id"] in results_by_id:
            d_fwd = results_by_id[fwd["id"]]["distance_miles"]
            d_rev = results_by_id[rev["id"]]["distance_miles"]
            diff = abs(d_rev - d_fwd)
            pct = (diff / max(0.1, min(d_fwd, d_rev))) * 100
            if diff > 1.0 or pct > 15.0:
                failures.append((rev["id"], f"distance asymmetry: fwd={d_fwd} mi vs rev={d_rev} mi ({pct:.1f}%)"))

    if failures:
        print(f"\nPRE-FLIGHT FAILED ({len(failures)} issues): {failures}")
        return False
    print("\nALL 16 CLEANUP CORRIDORS PASSED PRE-FLIGHT!")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()

    api_key = load_key()
    if not api_key:
        print("ERROR: GOOGLEMAPS_API_KEY not found in .env")
        sys.exit(1)

    if not run_preflight(api_key):
        sys.exit(1)

    if args.preflight_only or not args.run:
        return

    db_path = "data/bottleneck_speeds_db.json"
    pub_db_path = "public/data/bottleneck_speeds_db.json"
    database = json.load(open(db_path, "r", encoding="utf-8"))
    for sk in STALE_SLICE_KEYS:
        database["corridors"].pop(sk, None)

    all_failures = []
    for idx, c in enumerate(CLEANUP_CORRIDORS):
        cid = c["id"]
        existing = database["corridors"].get(cid)
        coords_match = (
            existing is not None
            and len(existing.get("start", [])) == 2
            and len(existing.get("end", [])) == 2
            and abs(existing["start"][0] - c["start"][0]) < 1e-4
            and abs(existing["start"][1] - c["start"][1]) < 1e-4
            and abs(existing["end"][0] - c["end"][0]) < 1e-4
            and abs(existing["end"][1] - c["end"][1]) < 1e-4
        )
        if not coords_match:
            database["corridors"][cid] = {"id": cid, "name": c["name"], "start": list(c["start"]), "end": list(c["end"]), "dates": {}}
        elif len(existing.get("dates", {})) == len(DATES) and all(
            len(existing["dates"].get(d["key"], {}).get("hours", {})) == len(ALL_HOURS) for d in DATES
        ):
            print(f"[{idx+1}/{len(CLEANUP_CORRIDORS)}] Skipping {cid} (already complete)")
            continue

        entry = database["corridors"][cid]
        pending = []
        for d in DATES:
            dkey, dstr = d["key"], d["date"]
            d_entry = entry["dates"].setdefault(dkey, {"date": dstr, "type": d["type"], "hours": {}})
            for h in ALL_HOURS:
                h_key = str(int(h)) if float(h) == int(float(h)) else str(h)
                if h_key not in d_entry["hours"]:
                    hi = int(h)
                    mi = 30 if (h % 1.0 >= 0.4) else 0
                    dt_iso = f"{dstr}T{hi:02d}:{mi:02d}:00-05:00"
                    pending.append((dkey, h_key, dt_iso))

        def _fetch(task):
            dkey, h_key, dt_iso = task
            return dkey, h_key, query_google_route(api_key, c["start"][0], c["start"][1], c["end"][0], c["end"][1], dt_iso)

        corridor_failures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            for dkey, h_key, res in pool.map(_fetch, pending):
                if res:
                    entry["dates"][dkey]["hours"][h_key] = res
                else:
                    corridor_failures.append((cid, dkey, h_key))

        for p in (db_path, pub_db_path):
            with open(p, "w", encoding="utf-8") as f:
                json.dump(database, f)
        if corridor_failures:
            all_failures.extend(corridor_failures)
            print(f"[{idx+1}/{len(CLEANUP_CORRIDORS)}] Saved partial {cid} ({len(pending)-len(corridor_failures)}/{len(pending)} ok)")
        else:
            print(f"[{idx+1}/{len(CLEANUP_CORRIDORS)}] Saved {cid} ({len(pending)} calls)")

    for p in (db_path, pub_db_path):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(database, f)

    def _is_complete(cid):
        dates = database.get("corridors", {}).get(cid, {}).get("dates", {})
        return len(dates) == len(DATES) and all(
            len(dates.get(d["key"], {}).get("hours", {})) == len(ALL_HOURS) for d in DATES
        )

    incomplete = [c["id"] for c in CLEANUP_CORRIDORS if not _is_complete(c["id"])]

    tt_path = "data/tomtom_corridors_168h.json"
    pub_tt_path = "public/data/tomtom_corridors_168h.json"
    tt = json.load(open(tt_path, "r", encoding="utf-8"))
    for c in CLEANUP_CORRIDORS:
        cid = c["id"]
        if cid in incomplete:
            continue
        dates = database["corridors"][cid]["dates"]
        mon = interpolate_day_24h(dates["baseline_mon"]["hours"])
        wed = interpolate_day_24h(dates["baseline_wed"]["hours"])
        fri = interpolate_day_24h(dates["baseline_fri"]["hours"])
        sat = interpolate_day_24h(dates["baseline_sat"]["hours"])
        sun = interpolate_day_24h(dates["baseline_sun"]["hours"])
        tue = [round((mon[h] + wed[h]) / 2.0, 1) for h in range(24)]
        thu = [round((wed[h] + fri[h]) / 2.0, 1) for h in range(24)]
        tt[cid] = [sun, mon, tue, wed, thu, fri, sat]
    for p in (tt_path, pub_tt_path):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(tt, f)

    hol_path = "data/holiday_congestion_offsets.json"
    pub_hol_path = "public/data/holiday_congestion_offsets.json"
    hol_db = json.load(open(hol_path, "r", encoding="utf-8"))
    for sk in STALE_SLICE_KEYS:
        hol_db["corridors"].pop(sk, None)
    holiday_baseline_map = {
        "thanksgiving_eve": ("Thanksgiving Eve (Peak Outbound Getaway)", "baseline_wed"),
        "thanksgiving_day": ("Thanksgiving Day (Commuter Lull)", "baseline_wed"),
        "black_friday": ("Black Friday (Retail & Travel Surge)", "baseline_fri"),
        "thanksgiving_sun_return": ("Post-Thanksgiving Sunday Return", "baseline_sun"),
        "pre_xmas_getaway": ("Pre-Christmas Travel Surge", "baseline_wed"),
        "xmas_eve": ("Christmas Eve", "baseline_wed"),
        "xmas_day": ("Christmas Day (Holiday Free-Flow)", "baseline_fri"),
        "day_after_xmas": ("Dec 26 Post-Christmas Travel", "baseline_sat"),
        "new_years_eve": ("New Year's Eve", "baseline_wed"),
        "new_years_day": ("New Year's Day (Free-Flow)", "baseline_fri"),
        "post_holiday_sun_return": ("Post-Holiday Sunday Return", "baseline_sun"),
    }
    for c in CLEANUP_CORRIDORS:
        cid = c["id"]
        if cid in incomplete:
            continue
        dates = database["corridors"][cid]["dates"]
        hol_entry = {"id": cid, "name": c["name"], "holidays": {}}
        for hkey, (hdesc, bkey) in holiday_baseline_map.items():
            h_hours = dates.get(hkey, {}).get("hours", {})
            b_hours = dates.get(bkey, {}).get("hours", {})
            hours_out = {}
            for hr_str, hv in h_hours.items():
                bv = b_hours.get(hr_str)
                if not bv or not bv.get("traffic_mph") or not hv.get("traffic_mph"):
                    continue
                h_spd = hv["traffic_mph"]
                b_spd = bv["traffic_mph"]
                mult = round(h_spd / b_spd, 3) if b_spd > 0 else 1.0
                delay_delta = round((hv.get("duration_seconds", 0) - bv.get("duration_seconds", 0)) / 60.0, 1)
                hours_out[hr_str] = {
                    "holiday_spd": h_spd,
                    "baseline_spd": b_spd,
                    "speed_multiplier": mult,
                    "speed_offset_mph": round(h_spd - b_spd, 1),
                    "delay_delta_min": delay_delta,
                }
            hol_entry["holidays"][hkey] = {"holiday_desc": hdesc, "baseline_compared": bkey, "hours": hours_out}
        hol_db["corridors"][cid] = hol_entry
    for p in (hol_path, pub_hol_path):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(hol_db, f)

    if all_failures or incomplete:
        print(f"ERROR: Harvest incomplete ({len(all_failures)} failures, {len(incomplete)} incomplete)")
        sys.exit(1)
    print("ALL 16 CLEANUP CORRIDORS HARVESTED & PUBLISHED CLEANLY!")


if __name__ == "__main__":
    main()
