"""
Google Maps Routes API Mainline Corridor Harvest (22 Directional Segments).

Replaces off-highway/ramp-polluted TomTom segments with strictly on-highway
mainline endpoints extracted from data/corridor_routes_cache.json.

Features:
  1. 22-call pre-flight sanity check (--preflight-only) verifying free-flow
     speed >= min_mph before spending full quota.
  2. 16 date profiles: 5 baseline days (Mon, Wed, Fri, Sat, Sun) + 11 holiday
     and adjacent travel dates.
  3. 23 time slots/day: 03:00, 06:00-20:00 hourly, 23:00, plus 6 rush-hour
     half-hours (06:30, 07:30, 08:30, 15:30, 16:30, 17:30).
  4. Interpolates baseline 5-day data into 7x24 matrices in
     data/tomtom_corridors_168h.json (+ public/data/) and stores full date
     profiles in data/bottleneck_speeds_db.json (+ public/data/).
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

def load_key():
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GOOGLEMAPS_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("GOOGLEMAPS_API_KEY")

CORRIDORS = [
    # 1. Columbus I-70 East Freeway (between downtown split & I-270)
    {"id": "columbus_i70_east", "name": "I-70 East (Columbus East Freeway to I-270)", "start": (39.932653, -82.932283), "end": (39.932645, -82.830438), "min_ff": 55.0},
    {"id": "columbus_i70_west", "name": "I-70 West (I-270 to Columbus East Freeway)", "start": (39.932895, -82.829824), "end": (39.932792, -82.932071), "min_ff": 55.0},
    # 2. Zanesville <-> Cambridge I-70
    {"id": "zanesville_to_cambridge_east", "name": "I-70 East (Zanesville to Cambridge)", "start": (39.960181, -81.923207), "end": (40.002367, -81.662978), "min_ff": 55.0},
    {"id": "zanesville_to_cambridge_west", "name": "I-70 West (Cambridge to Zanesville)", "start": (40.002605, -81.663295), "end": (39.960426, -81.923524), "min_ff": 55.0},
    # 3. Cambridge <-> Belmont I-70
    {"id": "cambridge_to_belmont_east", "name": "I-70 East (Cambridge to Belmont)", "start": (40.003241, -81.511330), "end": (40.061904, -81.046740), "min_ff": 55.0},
    {"id": "cambridge_to_belmont_west", "name": "I-70 West (Belmont to Cambridge)", "start": (40.062210, -81.046564), "end": (40.003501, -81.511831), "min_ff": 55.0},
    # 4. Belmont <-> Wheeling I-70
    {"id": "belmont_to_wheeling_east", "name": "I-70 East (Belmont to Wheeling)", "start": (40.075518, -80.964478), "end": (40.070084, -80.856564), "min_ff": 55.0},
    {"id": "belmont_to_wheeling_west", "name": "I-70 West (Wheeling to Belmont)", "start": (40.070163, -80.856338), "end": (40.075694, -80.964651), "min_ff": 55.0},
    # 5. I-79 Washington <-> Canonsburg
    {"id": "i79_washington_to_canonsburg_north", "name": "I-79 North (Washington PA to Canonsburg)", "start": (40.211035, -80.233707), "end": (40.260927, -80.172611), "min_ff": 55.0},
    {"id": "i79_washington_to_canonsburg_south", "name": "I-79 South (Canonsburg to Washington PA)", "start": (40.261103, -80.172858), "end": (40.211284, -80.233701), "min_ff": 55.0},
    # 6. I-79 Canonsburg <-> Bridgeville
    {"id": "i79_canonsburg_to_bridgeville_north", "name": "I-79 North (Canonsburg to Bridgeville)", "start": (40.287295, -80.168557), "end": (40.349957, -80.117143), "min_ff": 55.0},
    {"id": "i79_canonsburg_to_bridgeville_south", "name": "I-79 South (Bridgeville to Canonsburg)", "start": (40.349977, -80.117511), "end": (40.287176, -80.168848), "min_ff": 55.0},
    # 7. US-22 Weirton
    {"id": "us22_weirton_east", "name": "US-22 East (Weirton Freeway)", "start": (40.381750, -80.642290), "end": (40.397620, -80.544940), "min_ff": 50.0},
    {"id": "us22_weirton_west", "name": "US-22 West (Weirton Freeway)", "start": (40.397759, -80.545061), "end": (40.381872, -80.642509), "min_ff": 50.0},
    # 8. PA-576 Southern Beltway
    {"id": "pa576_beltway_north", "name": "PA-576 Northbound (Southern Beltway)", "start": (40.437440, -80.316420), "end": (40.465380, -80.291010), "min_ff": 55.0},
    {"id": "pa576_beltway_south", "name": "PA-576 Southbound (Southern Beltway)", "start": (40.465663, -80.291061), "end": (40.437619, -80.316608), "min_ff": 55.0},
    # 9. MD I-68 Cumberland
    {"id": "i68_cumberland_east", "name": "I-68 East (Cumberland)", "start": (39.641090, -78.816010), "end": (39.678670, -78.682830), "min_ff": 50.0},
    {"id": "i68_cumberland_west", "name": "I-68 West (Cumberland)", "start": (39.678812, -78.682920), "end": (39.641155, -78.816064), "min_ff": 50.0},
    # 10. MD I-70 Hagerstown
    {"id": "i70_hagerstown_east", "name": "I-70 East (Hagerstown)", "start": (39.641330, -77.829110), "end": (39.587060, -77.642770), "min_ff": 55.0},
    {"id": "i70_hagerstown_west", "name": "I-70 West (Hagerstown)", "start": (39.587330, -77.642653), "end": (39.641458, -77.828823), "min_ff": 55.0},
    # 11. MD I-70 Frederick
    {"id": "i70_frederick_east", "name": "I-70 East (Frederick)", "start": (39.407690, -77.470470), "end": (39.398110, -77.331670), "min_ff": 55.0},
    {"id": "i70_frederick_west", "name": "I-70 West (Frederick)", "start": (39.398244, -77.331422), "end": (39.407872, -77.470201), "min_ff": 55.0},
]

DATES = [
    {"key": "baseline_mon", "date": "2026-11-16", "type": "baseline"},
    {"key": "baseline_wed", "date": "2026-11-18", "type": "baseline"},
    {"key": "baseline_fri", "date": "2026-11-20", "type": "baseline"},
    {"key": "baseline_sat", "date": "2026-11-21", "type": "baseline"},
    {"key": "baseline_sun", "date": "2026-11-22", "type": "baseline"},
    {"key": "thanksgiving_eve", "date": "2026-11-25", "type": "holiday"},
    {"key": "thanksgiving_day", "date": "2026-11-26", "type": "holiday"},
    {"key": "black_friday", "date": "2026-11-27", "type": "holiday"},
    {"key": "thanksgiving_sun_return", "date": "2026-11-29", "type": "holiday"},
    {"key": "pre_xmas_getaway", "date": "2026-12-23", "type": "holiday"},
    {"key": "xmas_eve", "date": "2026-12-24", "type": "holiday"},
    {"key": "xmas_day", "date": "2026-12-25", "type": "holiday"},
    {"key": "day_after_xmas", "date": "2026-12-26", "type": "holiday"},
    {"key": "new_years_eve", "date": "2026-12-31", "type": "holiday"},
    {"key": "new_years_day", "date": "2027-01-01", "type": "holiday"},
    {"key": "post_holiday_sun_return", "date": "2027-01-03", "type": "holiday"},
]

STANDARD_HOURS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 23, 3]
HALF_HOURS = [6.5, 7.5, 8.5, 15.5, 16.5, 17.5]
ALL_HOURS = sorted(STANDARD_HOURS + HALF_HOURS)


def query_google_route(api_key, start_lat, start_lon, end_lat, end_lon, dt_iso):
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    payload = {
        "origin": {"location": {"latLng": {"latitude": start_lat, "longitude": start_lon}}},
        "destination": {"location": {"latLng": {"latitude": end_lat, "longitude": end_lon}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "departureTime": dt_iso,
        "computeAlternativeRoutes": False,
        "units": "IMPERIAL",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters",
    }
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                routes = res.get("routes", [])
                if not routes:
                    return None
                r = routes[0]
                dist_m = float(r.get("distanceMeters", 0))
                dur_s = float(r.get("duration", "0s").rstrip("s"))
                static_s = float(r.get("staticDuration", "0s").rstrip("s"))
                dist_mi = dist_m * 0.000621371
                ff_mph = dist_mi / max(0.0001, static_s / 3600.0)
                tr_mph = dist_mi / max(0.0001, dur_s / 3600.0)
                return {
                    "distance_miles": round(dist_mi, 2),
                    "duration_seconds": round(dur_s, 1),
                    "static_seconds": round(static_s, 1),
                    "free_flow_mph": round(ff_mph, 1),
                    "traffic_mph": round(tr_mph, 1),
                    "delay_minutes": round(max(0.0, (dur_s - static_s) / 60.0), 1),
                    "delay_ratio": round(dur_s / static_s if static_s > 0 else 1.0, 3),
                }
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(1.0 * (attempt + 1))
            else:
                body = e.read().decode("utf-8", errors="ignore")
                print(f"  HTTP {e.code}: {body[:200]}")
                time.sleep(0.5)
        except Exception as exc:
            print(f"  ERR: {exc}")
            time.sleep(0.5)
    return None


def run_preflight(api_key):
    print("=== PRE-FLIGHT SANITY CHECK (22 CALLS, Wed 11:00 AM) ===")
    failures = []
    results_by_id = {}
    for c in CORRIDORS:
        res = query_google_route(api_key, c["start"][0], c["start"][1], c["end"][0], c["end"][1], "2026-11-18T11:00:00-05:00")
        if not res:
            failures.append((c["id"], "NO_RESPONSE"))
            print(f"  FAIL {c['id']:40s}: NO RESPONSE")
            continue
        ok = res["free_flow_mph"] >= c["min_ff"]
        status = "OK  " if ok else "FAIL"
        if not ok:
            failures.append((c["id"], f"ff={res['free_flow_mph']} < {c['min_ff']}"))
        print(f"  {status} {c['id']:40s}: {res['distance_miles']:5.1f} mi | ff={res['free_flow_mph']:5.1f} mph | traffic={res['traffic_mph']:5.1f} mph")
        results_by_id[c["id"]] = res

    # Verify directional distance symmetry (catches U-turn / wrong-carriageway snaps)
    for i in range(0, len(CORRIDORS), 2):
        fwd = CORRIDORS[i]
        rev = CORRIDORS[i + 1]
        if fwd["id"] in results_by_id and rev["id"] in results_by_id:
            d_fwd = results_by_id[fwd["id"]]["distance_miles"]
            d_rev = results_by_id[rev["id"]]["distance_miles"]
            if abs(d_rev - d_fwd) > 1.0:
                failures.append((rev["id"], f"distance asymmetry: fwd={d_fwd} mi vs rev={d_rev} mi"))

    if failures:
        print(f"\nPRE-FLIGHT FAILED ({len(failures)} corridors): {failures}")
        return False
    print("\nALL 22 CORRIDORS PASSED PRE-FLIGHT!")
    return True


def interpolate_day_24h(hours_dict):
    # Fill 24 hourly slots from sampled hours (3, 6..20, 23) via circular linear interpolation
    sampled = sorted([(int(float(k)), v["traffic_mph"]) for k, v in hours_dict.items() if float(k) == int(float(k))])
    if not sampled:
        return [65.0] * 24
    by_hr = dict(sampled)
    out = []
    for h in range(24):
        if h in by_hr:
            out.append(round(by_hr[h], 1))
        else:
            prev_h = max([k for k in by_hr if k < h], default=max(by_hr.keys()) - 24)
            next_h = min([k for k in by_hr if k > h], default=min(by_hr.keys()) + 24)
            v0 = by_hr[prev_h % 24]
            v1 = by_hr[next_h % 24]
            frac = (h - prev_h) / max(1, next_h - prev_h)
            out.append(round(v0 + frac * (v1 - v0), 1))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true", help="Run only the 22-call pre-flight check")
    parser.add_argument("--run", action="store_true", help="Execute full 8,096-call harvest after pre-flight")
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
    database = json.load(open(db_path, "r", encoding="utf-8")) if os.path.exists(db_path) else {"metadata": {}, "corridors": {}}
    all_failures = []

    for idx, c in enumerate(CORRIDORS):
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
            print(f"[{idx+1}/{len(CORRIDORS)}] Skipping {cid} (already complete)")
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
            print(f"[{idx+1}/{len(CORRIDORS)}] Saved partial {cid} ({len(pending) - len(corridor_failures)}/{len(pending)} succeeded, {len(corridor_failures)} FAILED)")
        else:
            print(f"[{idx+1}/{len(CORRIDORS)}] Saved {cid} ({len(pending)} calls)")

    def _is_complete(cid):
        dates = database.get("corridors", {}).get(cid, {}).get("dates", {})
        return len(dates) == len(DATES) and all(
            len(dates.get(d["key"], {}).get("hours", {})) == len(ALL_HOURS) for d in DATES
        )

    incomplete_corridors = [c["id"] for c in CORRIDORS if not _is_complete(c["id"])]

    # Update data/tomtom_corridors_168h.json (+ public/data/) only for complete corridors
    tt_path = "data/tomtom_corridors_168h.json"
    pub_tt_path = "public/data/tomtom_corridors_168h.json"
    tt = json.load(open(tt_path, "r", encoding="utf-8"))
    for c in CORRIDORS:
        cid = c["id"]
        if cid in incomplete_corridors:
            print(f"SKIP publishing {cid} to tomtom_corridors_168h.json (incomplete harvest)")
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
    print("Updated tomtom_corridors_168h.json & public/data/tomtom_corridors_168h.json!")

    # Update data/holiday_congestion_offsets.json (+ public/data/) only for complete corridors
    hol_path = "data/holiday_congestion_offsets.json"
    pub_hol_path = "public/data/holiday_congestion_offsets.json"
    hol_db = json.load(open(hol_path, "r", encoding="utf-8"))
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
    for c in CORRIDORS:
        cid = c["id"]
        if cid in incomplete_corridors:
            print(f"SKIP publishing {cid} to holiday_congestion_offsets.json (incomplete harvest)")
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
            hol_entry["holidays"][hkey] = {
                "holiday_desc": hdesc,
                "baseline_compared": bkey,
                "hours": hours_out,
            }
        hol_db["corridors"][cid] = hol_entry
    for p in (hol_path, pub_hol_path):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(hol_db, f)
    print("Updated holiday_congestion_offsets.json & public/data/holiday_congestion_offsets.json!")

    if all_failures or incomplete_corridors:
        print(f"ERROR: Harvest incomplete ({len(all_failures)} failed calls, {len(incomplete_corridors)} incomplete corridors): {all_failures[:10]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
