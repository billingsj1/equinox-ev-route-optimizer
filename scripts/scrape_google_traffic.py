"""
High-Impact 28-Corridor Traffic & Speed Scraper (Google Maps Routes API)
For Jolly Hopper EV Route Planner

Scrapes:
  - 28 Directional Corridor Links (Columbus, Zanesville, Wheeling, Washington PA,
    PA Turnpike Tunnels, Carlisle, Schuylkill, Ben Franklin/Vine, NJ-70,
    PA Turnpike I-276, NJ Turnpike Exits 6-4, NJ-73, Sewickley US-22 & I-79)
  - 17 Departure Hours:
      * Daytime hourly: 06:00 to 20:00 (15 hours)
      * Overnight: 23:00, 03:00 (2 hours)
  - 15 Calendar Date Profiles:
      * 4 Baseline Days: Mon (11/16), Wed (11/18), Fri (11/20), Sun (11/22)
      * 11 Holiday Dates:
          - Thanksgiving: 11/25 (Eve), 11/26 (Day), 11/27 (Black Fri), 11/29 (Sun Return)
          - Christmas: 12/23 (Pre-Xmas), 12/24 (Eve), 12/25 (Day), 12/26 (Post-Xmas)
          - New Year: 12/31 (Eve), 01/01 (New Year Day), 01/03 (Post-Holiday Sun Return)

Metrics Captured:
  - distanceMeters
  - staticDuration (pure free-flow baseline)
  - duration (predicted duration with traffic)
  - freeFlowSpeedMph
  - trafficSpeedMph
  - delayMinutes
  - delayRatio

Saves to:
  - data/bottleneck_speeds_db.json
  - public/data/bottleneck_speeds_db.json
Includes checkpointing after every corridor link.
"""

import datetime
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
                if line.startswith("GOOGLEMAPS_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

api_key = load_key()
if not api_key:
    print("ERROR: GOOGLEMAPS_API_KEY not found in .env")
    sys.exit(1)

# 28 Directional Corridors
CORRIDORS = [
    # --- Columbus Metro ---
    {"id": "columbus_i70_east", "name": "I-70 East (Downtown Columbus to Reynoldsburg / I-270)", "start": (39.9575, -82.9988), "end": (39.9540, -82.8150)},
    {"id": "columbus_i70_west", "name": "I-70 West (Reynoldsburg / I-270 to Downtown Columbus)", "start": (39.9540, -82.8150), "end": (39.9575, -82.9988)},
    
    # --- Central / Eastern Ohio ---
    {"id": "zanesville_i70_east", "name": "I-70 East through Zanesville & US-40", "start": (39.9500, -82.0500), "end": (39.9400, -81.9700)},
    {"id": "zanesville_i70_west", "name": "I-70 West through Zanesville & US-40", "start": (39.9400, -81.9700), "end": (39.9500, -82.0500)},
    
    # --- Wheeling, WV / Ohio River Gorge ---
    {"id": "wheeling_i70_east", "name": "I-70 East Fort Henry Bridge & Wheeling Tunnels", "start": (40.0710, -80.7300), "end": (40.0520, -80.6100)},
    {"id": "wheeling_i70_west", "name": "I-70 West Wheeling Tunnels to Fort Henry Bridge", "start": (40.0520, -80.6100), "end": (40.0710, -80.7300)},
    
    # --- Washington, PA (I-70 / I-79 Split) ---
    {"id": "washington_pa_i70_east", "name": "I-70 East through Washington, PA (I-79 Split)", "start": (40.1800, -80.2900), "end": (40.1700, -80.1900)},
    {"id": "washington_pa_i70_west", "name": "I-70 West through Washington, PA (I-79 Split)", "start": (40.1700, -80.1900), "end": (40.1800, -80.2900)},
    
    # --- PA Turnpike Mountain Pass & Tunnels ---
    {"id": "pa_turnpike_tunnels_east", "name": "PA Turnpike East: New Stanton to Breezewood (Allegheny Tunnel)", "start": (40.2150, -79.5850), "end": (40.0050, -78.2400)},
    {"id": "pa_turnpike_tunnels_west", "name": "PA Turnpike West: Breezewood to New Stanton (Allegheny Tunnel)", "start": (40.0050, -78.2400), "end": (40.2150, -79.5850)},
    {"id": "pa_turnpike_east_carlisle", "name": "PA Turnpike East: Breezewood to Carlisle (Tuscarora/Blue Mtn Tunnels)", "start": (40.0050, -78.2400), "end": (40.2185, -76.9982)},
    {"id": "pa_turnpike_west_carlisle", "name": "PA Turnpike West: Carlisle to Breezewood (Tuscarora/Blue Mtn Tunnels)", "start": (40.2185, -76.9982), "end": (40.0050, -78.2400)},
    
    # --- Philadelphia & South Jersey (Route 1) ---
    {"id": "schuylkill_east", "name": "I-76 Schuylkill Expressway East (KOP to Center City)", "start": (40.0903, -75.3881), "end": (39.9575, -75.1812)},
    {"id": "schuylkill_west", "name": "I-76 Schuylkill Expressway West (Center City to KOP)", "start": (39.9575, -75.1812), "end": (40.0903, -75.3881)},
    {"id": "vinest_benfranklin_east", "name": "I-676 Vine St & Ben Franklin Bridge East (Philly to Camden/NJ-70)", "start": (39.9575, -75.1812), "end": (39.9405, -75.0802)},
    {"id": "vinest_benfranklin_west", "name": "Ben Franklin Bridge & I-676 Vine St West (NJ-70 to Philly)", "start": (39.9405, -75.0802), "end": (39.9575, -75.1812)},
    {"id": "nj70_east", "name": "NJ-70 Marlton Pike East (Pennsauken to Marlton)", "start": (39.9405, -75.0802), "end": (39.8912, -74.9218)},
    {"id": "nj70_west", "name": "NJ-70 Marlton Pike West (Marlton to Pennsauken)", "start": (39.8912, -74.9218), "end": (39.9405, -75.0802)},
    
    # --- PA Turnpike to NJ Turnpike Bypass (Route 2) ---
    {"id": "i276_paturnpike_east", "name": "PA Turnpike East (I-276 Valley Forge to Delaware River Bridge)", "start": (40.0903, -75.3881), "end": (40.1195, -74.7431)},
    {"id": "i276_paturnpike_west", "name": "PA Turnpike West (I-276 Delaware River Bridge to Valley Forge)", "start": (40.1195, -74.7431), "end": (40.0903, -75.3881)},
    {"id": "njturnpike_south", "name": "NJ Turnpike South (Exit 6 PA Extension to Exit 4 Mount Laurel)", "start": (40.1195, -74.7431), "end": (39.9077, -74.9547)},
    {"id": "njturnpike_north", "name": "NJ Turnpike North (Exit 4 Mount Laurel to Exit 6 PA Extension)", "start": (39.9077, -74.9547), "end": (40.1195, -74.7431)},
    {"id": "nj73_south", "name": "NJ-73 South Connector (Exit 4 to Marlton Route 70)", "start": (39.9077, -74.9547), "end": (39.8912, -74.9218)},
    {"id": "nj73_north", "name": "NJ-73 North Connector (Marlton to Exit 4)", "start": (39.8912, -74.9218), "end": (39.9077, -74.9547)},
    
    # --- Sewickley Corridors (US-22 / PA-576 vs I-70 / I-79) ---
    {"id": "sewickley_us22_east", "name": "US-22 East / PA-576 Toll Highway into Sewickley", "start": (40.4150, -80.5750), "end": (40.5415, -80.1820)},
    {"id": "sewickley_us22_west", "name": "Sewickley to US-22 West via PA-576 Toll Highway", "start": (40.5415, -80.1820), "end": (40.4150, -80.5750)},
    {"id": "sewickley_i79_north", "name": "I-79 North from Washington, PA to Sewickley (Toll-Free)", "start": (40.1740, -80.2462), "end": (40.5415, -80.1820)},
    {"id": "sewickley_i79_south", "name": "Sewickley to I-79 South towards Washington, PA (Toll-Free)", "start": (40.5415, -80.1820), "end": (40.1740, -80.2462)},
]

# 15 Date Profiles
DATES = [
    # 4 Normal Baseline Days
    {"key": "baseline_mon", "date": "2026-11-16", "type": "baseline", "desc": "Normal Monday"},
    {"key": "baseline_wed", "date": "2026-11-18", "type": "baseline", "desc": "Normal Wednesday (Midweek)"},
    {"key": "baseline_fri", "date": "2026-11-20", "type": "baseline", "desc": "Normal Friday (Weekend Getaway)"},
    {"key": "baseline_sun", "date": "2026-11-22", "type": "baseline", "desc": "Normal Sunday (Return Travel)"},
    
    # 11 Holiday Dates
    {"key": "thanksgiving_eve", "date": "2026-11-25", "type": "holiday", "desc": "Thanksgiving Eve (Peak Outbound Getaway)"},
    {"key": "thanksgiving_day", "date": "2026-11-26", "type": "holiday", "desc": "Thanksgiving Day (Holiday Lull)"},
    {"key": "black_friday", "date": "2026-11-27", "type": "holiday", "desc": "Black Friday (Retail & Travel Surge)"},
    {"key": "thanksgiving_sun_return", "date": "2026-11-29", "type": "holiday", "desc": "Sunday after Thanksgiving (Peak Return Rush)"},
    
    {"key": "pre_xmas_getaway", "date": "2026-12-23", "type": "holiday", "desc": "Dec 23 Pre-Christmas Travel Rush"},
    {"key": "xmas_eve", "date": "2026-12-24", "type": "holiday", "desc": "Christmas Eve"},
    {"key": "xmas_day", "date": "2026-12-25", "type": "holiday", "desc": "Christmas Day"},
    {"key": "day_after_xmas", "date": "2026-12-26", "type": "holiday", "desc": "Dec 26 Return & Retail Travel"},
    
    {"key": "new_years_eve", "date": "2026-12-31", "type": "holiday", "desc": "New Year's Eve"},
    {"key": "new_years_day", "date": "2027-01-01", "type": "holiday", "desc": "New Year's Day"},
    {"key": "post_holiday_sun_return", "date": "2027-01-03", "type": "holiday", "desc": "Jan 3 Post-Holiday Sunday Return"}
]

# 17 Departure Hours (Local Eastern Time converted to UTC)
# Note: In Nov/Dec/Jan, US Eastern Time is EST = UTC-5
HOURS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 23, 3]

def query_google_route(start_lat, start_lon, end_lat, end_lon, dt_iso_utc):
    routes_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    payload = {
        "origin": {"location": {"latLng": {"latitude": start_lat, "longitude": start_lon}}},
        "destination": {"location": {"latLng": {"latitude": end_lat, "longitude": end_lon}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "departureTime": dt_iso_utc,
        "trafficModel": "BEST_GUESS"
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters"
    }
    req = urllib.request.Request(routes_url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
                if "routes" in data and len(data["routes"]) > 0:
                    r = data["routes"][0]
                    dist_m = r.get("distanceMeters", 0)
                    dur_s = int(r.get("duration", "0s").rstrip("s"))
                    static_s = int(r.get("staticDuration", "0s").rstrip("s"))
                    
                    dist_mi = dist_m * 0.000621371
                    static_h = max(0.001, static_s / 3600.0)
                    traffic_h = max(0.001, dur_s / 3600.0)
                    
                    free_flow_mph = dist_mi / static_h
                    traffic_mph = dist_mi / traffic_h
                    delay_min = max(0.0, (dur_s - static_s) / 60.0)
                    delay_ratio = dur_s / static_s if static_s > 0 else 1.0
                    
                    return {
                        "distance_miles": round(dist_mi, 2),
                        "duration_seconds": dur_s,
                        "static_seconds": static_s,
                        "free_flow_mph": round(free_flow_mph, 1),
                        "traffic_mph": round(traffic_mph, 1),
                        "delay_minutes": round(delay_min, 1),
                        "delay_ratio": round(delay_ratio, 3)
                    }
                else:
                    return None
        except urllib.error.HTTPError as e:
            if e.code == 429: # Rate limit
                time.sleep(1.0 * (attempt + 1))
            else:
                time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    return None

def main():
    db_path = "data/bottleneck_speeds_db.json"
    public_db_path = "public/data/bottleneck_speeds_db.json"
    
    database = {
        "metadata": {
            "source": "Google Maps Routes API (TRAFFIC_AWARE_OPTIMAL, BEST_GUESS)",
            "date_generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "corridor_count": len(CORRIDORS),
            "dates_profiled": [d["key"] for d in DATES],
            "hours_profiled": HOURS
        },
        "corridors": {}
    }
    
    # Load existing if available for checkpointing
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if "corridors" in existing:
                    database["corridors"] = existing["corridors"]
                    print(f"Loaded existing checkpoint with {len(database['corridors'])} corridors.")
        except Exception as e:
            print("Could not load checkpoint, starting fresh:", e)

    total_queries = 0
    total_planned = len(CORRIDORS) * len(DATES) * len(HOURS)
    print(f"\n{'='*70}\nStarting Google Maps Routes Traffic Scrape ({total_planned} planned calls across {len(CORRIDORS)} corridors)\n{'='*70}\n")
    
    start_time = time.time()
    
    for c_idx, corridor in enumerate(CORRIDORS):
        cid = corridor["id"]
        cname = corridor["name"]
        
        # Check if already completed
        if cid in database["corridors"] and len(database["corridors"][cid].get("dates", {})) == len(DATES):
            print(f"[{c_idx+1}/{len(CORRIDORS)}] Skipping {cid} (already fully captured).")
            continue
            
        print(f"\n[{c_idx+1}/{len(CORRIDORS)}] Scraping: {cname} ({cid})")
        if cid not in database["corridors"]:
            database["corridors"][cid] = {
                "id": cid,
                "name": cname,
                "start": corridor["start"],
                "end": corridor["end"],
                "dates": {}
            }
            
        for d_idx, date_obj in enumerate(DATES):
            dkey = date_obj["key"]
            dstr = date_obj["date"]
            
            if dkey not in database["corridors"][cid]["dates"]:
                database["corridors"][cid]["dates"][dkey] = {
                    "date": dstr,
                    "desc": date_obj["desc"],
                    "type": date_obj["type"],
                    "hours": {}
                }
                
            for h in HOURS:
                h_str = str(h)
                if h_str in database["corridors"][cid]["dates"][dkey]["hours"]:
                    continue # already captured
                    
                # Convert Eastern Time hour to UTC: EST is UTC-5, so UTC hour = (h + 5) % 24
                # If h + 5 >= 24, it rolls over to next UTC calendar day
                utc_hour = (h + 5) % 24
                rollover_days = (h + 5) // 24
                
                dt = datetime.date.fromisoformat(dstr) + datetime.timedelta(days=rollover_days)
                dt_iso_utc = f"{dt.isoformat()}T{utc_hour:02d}:00:00Z"
                
                res = query_google_route(corridor["start"][0], corridor["start"][1], corridor["end"][0], corridor["end"][1], dt_iso_utc)
                total_queries += 1
                
                if res:
                    database["corridors"][cid]["dates"][dkey]["hours"][h_str] = res
                    
                # Moderate throttle: ~8 to 10 queries/sec (stay comfortably below 600 req/min)
                time.sleep(0.08)
                
            print(f"    - {date_obj['desc']} ({dstr}): 17 hours captured.")
            
        # Checkpoint to disk after every corridor
        os.makedirs("data", exist_ok=True)
        os.makedirs("public/data", exist_ok=True)
        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(database, f, indent=2)
        with open(public_db_path, "w", encoding="utf-8") as f:
            json.dump(database, f, indent=2)
            
        elapsed = time.time() - start_time
        print(f"  -> Checkpointed {cid} to disk. Total queries so far: {total_queries} (Elapsed: {elapsed/60:.1f}m)")
        
    print(f"\n{'='*70}\nScraping Complete! Total queries made: {total_queries}\n{'='*70}\n")
    print(f"Final databases saved to:\n  - {db_path}\n  - {public_db_path}")

if __name__ == "__main__":
    main()
