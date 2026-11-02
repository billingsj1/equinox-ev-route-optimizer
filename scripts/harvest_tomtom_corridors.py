"""
TomTom Comprehensive Corridor Velocity Harvester & Rich Data Logger

Features:
  - 22 Bidirectional Corridors (Philadelphia, NJ Turnpike, Central PA/US-30, Pittsburgh/Sewickley, Columbus)
  - 5 Day Profiles:
      * Sunday
      * Monday (hybrid commute)
      * Wednesday (representative Midweek for Tue, Wed, Thu)
      * Friday (early escape rush & weekend getaway)
      * Saturday (midday shopping & leisure)
  - 20 Hours per day (1h daytime 5a-9p, 2h overnight with interpolation)
  - 22 corridors x 5 days x 20 hours = 2,200 total queries (comfortably under 2,500/day limit)
  - Rich Data Logging: Records speed, free-flow speed, travel time, delay seconds, congestion ratio,
    and traffic length in meters.
  - Outputs both:
      1. data/tomtom_corridors_rich_archive.json (complete historical analytics dataset)
      2. data/tomtom_corridors_168h.json (7x24 matrix for production web app)
  - Auto-compiles into index.html, public/index.html, and ui/templates/index.html
"""

import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

# 22 Bidirectional Key Corridors
CORRIDORS = {
    # --- Philadelphia & South Jersey (St. Onge Route) ---
    "schuylkill_east": {
        "name": "I-76 Schuylkill Expressway East (KOP to Center City)",
        "start": (40.0903, -75.3881), # King of Prussia
        "end": (39.9575, -75.1812),   # I-676 Center City
    },
    "schuylkill_west": {
        "name": "I-76 Schuylkill Expressway West (Center City to KOP)",
        "start": (39.9575, -75.1812), # Center City
        "end": (40.0903, -75.3881),   # King of Prussia
    },
    "vinest_east": {
        "name": "I-676 Vine St & Ben Franklin Bridge East (Philly to Camden/NJ-70)",
        "start": (39.9575, -75.1812), # Center City / Schuylkill
        "end": (39.9405, -75.0802),   # Pennsauken / Route 38/70 merge
    },
    "vinest_west": {
        "name": "Ben Franklin Bridge & I-676 Vine St West (NJ-70 to Philly)",
        "start": (39.9405, -75.0802), # Pennsauken
        "end": (39.9575, -75.1812),   # Center City
    },
    "nj70_east": {
        "name": "NJ-70 Marlton Pike East (Pennsauken to Marlton)",
        "start": (39.9405, -75.0802), # Pennsauken
        "end": (39.8912, -74.9218),   # Marlton / Conestoga Dr
    },
    "nj70_west": {
        "name": "NJ-70 Marlton Pike West (Marlton to Pennsauken)",
        "start": (39.8912, -74.9218), # Marlton
        "end": (39.9405, -75.0802),   # Pennsauken
    },
    "i276_east": {
        "name": "PA Turnpike East (I-276 KOP to Delaware River Bridge)",
        "start": (40.0903, -75.3881), # Valley Forge / KOP
        "end": (40.1195, -74.7431),   # Delaware River Bridge
    },
    "i276_west": {
        "name": "PA Turnpike West (I-276 Delaware River Bridge to KOP)",
        "start": (40.1195, -74.7431), # Delaware River Bridge
        "end": (40.0903, -75.3881),   # Valley Forge / KOP
    },
    "njturnpike_south": {
        "name": "NJ Turnpike South (Exit 6 to Exit 4 Mount Laurel)",
        "start": (40.1195, -74.7431), # Interchange 6 / PA Turnpike Connector
        "end": (39.9077, -74.9547),   # Interchange 4 / NJ-73 Mount Laurel
    },
    "njturnpike_north": {
        "name": "NJ Turnpike North (Exit 4 to Exit 6 PA Connector)",
        "start": (39.9077, -74.9547), # Interchange 4 / NJ-73 Mount Laurel
        "end": (40.1195, -74.7431),   # Interchange 6 / PA Turnpike Connector
    },
    "nj73_south": {
        "name": "NJ-73 South Connector (Exit 4 to Marlton Route 70)",
        "start": (39.9077, -74.9547), # NJ Turnpike Exit 4
        "end": (39.8912, -74.9218),   # Marlton / Route 70
    },
    "nj73_north": {
        "name": "NJ-73 North Connector (Marlton to NJ Turnpike Exit 4)",
        "start": (39.8912, -74.9218), # Marlton / Route 70
        "end": (39.9077, -74.9547),   # NJ Turnpike Exit 4
    },

    # --- Central PA & DeCamilla Corridors ---
    "us15_south": {
        "name": "US-15 South (PA Turnpike Exit 236 to DeCamilla)",
        "start": (40.2185, -76.9982), # PA Turnpike Exit 236
        "end": (40.1413, -77.0156),   # DeCamilla / Dillsburg
    },
    "us15_north": {
        "name": "US-15 North (DeCamilla to PA Turnpike Exit 236)",
        "start": (40.1413, -77.0156), # DeCamilla / Dillsburg
        "end": (40.2185, -76.9982),   # PA Turnpike Exit 236
    },
    "pa283_us30_east": {
        "name": "PA-283 / US-30 East (Harrisburg to Lancaster & Exton)",
        "start": (40.2312, -76.8142), # Harrisburg / Highspire
        "end": (40.0385, -75.6212),   # Exton / US-202
    },
    "us30_pa283_west": {
        "name": "US-30 / PA-283 West (Exton & Lancaster to Harrisburg)",
        "start": (40.0385, -75.6212), # Exton / US-202
        "end": (40.2312, -76.8142),   # Harrisburg / Highspire
    },

    # --- Pittsburgh Metro (Billings / Sewickley Route) ---
    "pittsburgh_parkway_inbound": {
        "name": "I-376 Parkway West Inbound (Airport/I-79 to Pittsburgh)",
        "start": (40.4520, -80.1850), # Airport / I-79
        "end": (40.4350, -80.0150),   # Fort Pitt Tunnel approach
    },
    "pittsburgh_parkway_outbound": {
        "name": "I-376 Parkway West Outbound (Pittsburgh to Airport/I-79)",
        "start": (40.4350, -80.0150), # Downtown Pittsburgh
        "end": (40.4520, -80.1850),   # Airport / I-79
    },
    "pa65_north": {
        "name": "PA-65 Ohio River Blvd North (Pittsburgh to Sewickley)",
        "start": (40.4650, -80.0400), # Bellevue / Avalon
        "end": (40.5415, -80.1820),   # Sewickley Beaver Rd
    },
    "pa65_south": {
        "name": "PA-65 Ohio River Blvd South (Sewickley to Pittsburgh)",
        "start": (40.5415, -80.1820), # Sewickley Beaver Rd
        "end": (40.4650, -80.0400),   # Bellevue / Avalon
    },

    # --- Columbus Metro ---
    "columbus_i70_east": {
        "name": "I-70 East Columbus Outbound (Downtown to I-270)",
        "start": (39.9570, -83.0030), # Downtown Columbus
        "end": (39.9320, -82.8250),   # Reynoldsburg / I-270
    },
    "columbus_i70_west": {
        "name": "I-70 West Columbus Inbound (I-270 to Downtown)",
        "start": (39.9320, -82.8250), # Reynoldsburg / I-270
        "end": (39.9570, -83.0030),   # Downtown Columbus
    }
}

# 5 Day Profiles (Reference week dates):
# Sunday Nov 8, Monday Nov 9, Wednesday Nov 11 (Midweek), Friday Nov 13, Saturday Nov 14
HARVEST_DAYS = [
    {"target_dow": 0, "name": "Sunday",    "date": datetime.date(2026, 11, 8),  "applies_to": [0]},
    {"target_dow": 1, "name": "Monday",    "date": datetime.date(2026, 11, 9),  "applies_to": [1]},
    {"target_dow": 3, "name": "Wednesday", "date": datetime.date(2026, 11, 11), "applies_to": [2, 3, 4]}, # Midweek covers Tue, Wed, Thu
    {"target_dow": 5, "name": "Friday",    "date": datetime.date(2026, 11, 13), "applies_to": [5]},
    {"target_dow": 6, "name": "Saturday",  "date": datetime.date(2026, 11, 14), "applies_to": [6]}
]

# 20 hours sampled: Daytime 5..21 (every 1h) + Nighttime 0, 2, 4, 22 (every 2h)
SAMPLE_HOURS = [0, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]

def fetch_hourly_data(api_key: str, start_lat: float, start_lon: float, end_lat: float, end_lon: float, depart_iso: str, retries: int = 3):
    base_url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lon}:{end_lat},{end_lon}/json"
    params = {
        "key": api_key,
        "departAt": depart_iso,
        "traffic": "true",
        "routeType": "fastest",
        "travelMode": "car"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-TrafficHarvester/2.0"})
    
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                summary = data["routes"][0]["summary"]
                meters = summary["lengthInMeters"]
                seconds = summary["travelTimeInSeconds"]
                delay_sec = summary.get("trafficDelayInSeconds", 0)
                no_traffic_sec = summary.get("noTrafficTravelTimeInSeconds", max(1, seconds - delay_sec))
                traffic_len_m = summary.get("trafficLengthInMeters", 0)

                miles = meters * 0.000621371
                speed_mph = miles / (seconds / 3600.0) if seconds > 0 else 60.0
                free_mph = miles / (no_traffic_sec / 3600.0) if no_traffic_sec > 0 else speed_mph
                congestion_ratio = round(seconds / max(1.0, no_traffic_sec), 3)

                return {
                    "miles": round(miles, 2),
                    "speed_mph": round(speed_mph, 1),
                    "free_flow_mph": round(free_mph, 1),
                    "travel_time_seconds": seconds,
                    "delay_seconds": delay_sec,
                    "delay_minutes": round(delay_sec / 60.0, 1),
                    "congestion_ratio": congestion_ratio,
                    "traffic_length_meters": traffic_len_m
                }
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_sec = 2.0 * (attempt + 1)
                print(f"    [Rate limit 429] Pausing {wait_sec}s before retry {attempt + 1}/{retries}...", flush=True)
                time.sleep(wait_sec)
            else:
                if attempt == retries - 1:
                    raise
                time.sleep(1.0)
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(1.0)
    
    raise RuntimeError(f"Failed to fetch data after {retries} retries")

def interpolate_24h(sampled_dict: dict, key: str = "speed_mph"):
    """Interpolates unsampled hours (e.g. 1, 3, 23) using neighboring hours."""
    vals_24 = [0.0] * 24
    for h in range(24):
        if h in sampled_dict:
            vals_24[h] = sampled_dict[h][key]
        else:
            prev_h = (h - 1) % 24
            next_h = (h + 1) % 24
            v_prev = sampled_dict.get(prev_h, {}).get(key, 60.0)
            v_next = sampled_dict.get(next_h, {}).get(key, 60.0)
            vals_24[h] = round((v_prev + v_next) / 2.0, 1)
    return vals_24

def harvest(api_key: str):
    rich_archive = {}
    production_speeds = {}
    total_calls = len(CORRIDORS) * len(HARVEST_DAYS) * len(SAMPLE_HOURS)
    call_idx = 0

    print("=" * 70, flush=True)
    print("TOMTOM COMPREHENSIVE CORRIDOR VELOCITY HARVEST", flush=True)
    print(f"Corridors:     {len(CORRIDORS)} (Bidirectional)", flush=True)
    print(f"Day Profiles:  {len(HARVEST_DAYS)} (Sun, Mon, Wed [Midweek], Fri, Sat)", flush=True)
    print(f"Hours/Day:     {len(SAMPLE_HOURS)} (1h daytime, 2h overnight with interpolation)", flush=True)
    print(f"Total Queries: {total_calls} (Daily limit: 2,500 | QPS: 4.0 [Limit: 5.0])", flush=True)
    print("=" * 70, flush=True)

    for c_id, c_data in CORRIDORS.items():
        print(f"\nHarvesting corridor: {c_data['name']}...", flush=True)
        rich_archive[c_id] = {
            "name": c_data["name"],
            "start": c_data["start"],
            "end": c_data["end"],
            "profiles": {}
        }
        production_speeds[c_id] = [[0.0 for _ in range(24)] for _ in range(7)]
        
        for hday in HARVEST_DAYS:
            day_name = hday["name"]
            cur_date = hday["date"]
            rich_archive[c_id]["profiles"][day_name] = {}
            day_samples = {}
            
            for hour in SAMPLE_HOURS:
                call_idx += 1
                depart_iso = f"{cur_date.isoformat()}T{hour:02d}:00:00"
                
                try:
                    res = fetch_hourly_data(
                        api_key,
                        c_data["start"][0], c_data["start"][1],
                        c_data["end"][0], c_data["end"][1],
                        depart_iso
                    )
                    day_samples[hour] = res
                    rich_archive[c_id]["profiles"][day_name][hour] = res
                    
                    if hour % 4 == 0 or res["delay_minutes"] >= 1.5:
                        print(f"  [{call_idx}/{total_calls}] {day_name} {hour:02d}:00 -> {res['speed_mph']} mph (Delay: +{res['delay_minutes']}m | Congestion: {res['congestion_ratio']}x)", flush=True)
                    
                    time.sleep(0.25) # 4 QPS max (TomTom Routing API free tier is 5 QPS)
                except Exception as e:
                    print(f"  Error at {c_id} {day_name} {hour:02d}:00: {e}", flush=True)
                    time.sleep(2.0)
            
            # Interpolate 24 hours of speed values
            interp_24 = interpolate_24h(day_samples, key="speed_mph")
            # Apply to all days this profile represents (e.g. Wed -> Tue, Wed, Thu)
            for d in hday["applies_to"]:
                production_speeds[c_id][d] = interp_24

    # Generate convenient base aliases for single-corridor lookups
    production_speeds["schuylkill"] = production_speeds.get("schuylkill_east")
    production_speeds["vinest"] = production_speeds.get("vinest_east")
    production_speeds["nj70"] = production_speeds.get("nj70_east")
    production_speeds["i276"] = production_speeds.get("i276_east")
    production_speeds["njturnpike"] = production_speeds.get("njturnpike_south")
    production_speeds["nj73"] = production_speeds.get("nj73_south")
    production_speeds["us30_pa283"] = production_speeds.get("pa283_us30_east")

    # Save rich archive
    os.makedirs("data", exist_ok=True)
    with open("data/tomtom_corridors_rich_archive.json", "w") as f:
        json.dump(rich_archive, f, indent=2)
    print("\nSaved full rich archive to: data/tomtom_corridors_rich_archive.json", flush=True)

    # Save production speed matrix
    with open("data/tomtom_corridors_168h.json", "w") as f:
        json.dump(production_speeds, f, indent=2)
    print("Saved 7x24 production speed matrix to: data/tomtom_corridors_168h.json", flush=True)

    # Save production speed matrix
    with open("data/tomtom_corridors_168h.json", "w") as f:
        json.dump(production_speeds, f, indent=2)
    print("Saved 7x24 production speed matrix to: data/tomtom_corridors_168h.json")

    # Auto-compile into HTML
    embed_into_html(production_speeds)

def embed_into_html(speed_matrix: dict):
    js_code = "const TOMTOM_CORRIDOR_SPEEDS = " + json.dumps(speed_matrix, indent=2) + ";"
    start_marker = "const TOMTOM_CORRIDOR_SPEEDS = {"
    end_marker = "function getDepartureDayOfWeek()"

    html_files = ["index.html", "public/index.html", "ui/templates/index.html"]
    for path in html_files:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if start_marker in content and end_marker in content:
                idx_start = content.find(start_marker)
                idx_end = content.find(end_marker)
                new_content = content[:idx_start] + js_code + "\n\n    " + content[idx_end:]
            elif end_marker in content:
                new_content = content.replace(end_marker, f"{js_code}\n\n    {end_marker}")
            else:
                print(f"Warning: could not find insertion point in {path}")
                continue
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            h = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
            print(f"Updated {path} (SHA-256: {h[:12]}...)")

if __name__ == "__main__":
    key = None
    if len(sys.argv) >= 2:
        key = sys.argv[1]
    elif os.environ.get("TOMTOM_API_KEY"):
        key = os.environ.get("TOMTOM_API_KEY")
    elif os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                if line.startswith("TOMTOM_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    
    if not key:
        print("Usage: python scripts/harvest_tomtom_corridors.py <TOMTOM_API_KEY>")
        sys.exit(1)
    harvest(key)
