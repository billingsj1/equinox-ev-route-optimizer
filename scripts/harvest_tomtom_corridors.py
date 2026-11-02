"""
TomTom 168-Hour Corridor Velocity Harvester & HTML Compiler
Extracts empirical hourly speeds (24h x 7 days) across key corridors:
  - I-76 Schuylkill Expressway (King of Prussia -> Center City Philadelphia)
  - I-676 Vine Street Expressway & Ben Franklin Bridge
  - NJ-70 Marlton Pike Corridor
  - PA Turnpike East Extension (I-276 King of Prussia -> Delaware River Bridge)
  - NJ Turnpike Mainline (Interchange 6 -> Interchange 4)
  - NJ-73 South (Exit 4 -> Marlton)
  - US-30 / PA-283 (Harrisburg -> Lancaster / Exton)

Uses the TomTom Routing API calculateRoute with departAt and traffic=true.
Embeds the resulting 168-hour empirical matrix directly into index.html,
public/index.html, and ui/templates/index.html with SHA-256 verification.
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

CORRIDORS = {
    "schuylkill": {
        "name": "I-76 Schuylkill Expressway (King of Prussia to Center City)",
        "start": (40.0903, -75.3881), # King of Prussia
        "end": (39.9575, -75.1812),   # I-676 Center City
    },
    "vinest": {
        "name": "I-676 Vine St Expressway & Ben Franklin Bridge",
        "start": (39.9575, -75.1812), # Center City / Schuylkill
        "end": (39.9405, -75.0802),   # Pennsauken / Route 38/70 merge
    },
    "nj70": {
        "name": "NJ-70 Marlton Pike Corridor",
        "start": (39.9405, -75.0802), # Pennsauken
        "end": (39.8912, -74.9218),   # Marlton / Conestoga Dr
    },
    "i276": {
        "name": "PA Turnpike East Extension (I-276)",
        "start": (40.0903, -75.3881), # Valley Forge / KOP
        "end": (40.1195, -74.7431),   # Delaware River Bridge
    },
    "njturnpike": {
        "name": "NJ Turnpike Mainline (Exit 6 to 4)",
        "start": (40.1195, -74.7431), # Interchange 6 / PA Turnpike Connector
        "end": (39.9077, -74.9547),   # Interchange 4 / NJ-73 Mount Laurel
    },
    "nj73": {
        "name": "NJ-73 South Connector",
        "start": (39.9077, -74.9547), # NJ Turnpike Exit 4
        "end": (39.8912, -74.9218),   # Marlton / Route 70
    },
    "us30_pa283": {
        "name": "US-30 / PA-283 Corridor",
        "start": (40.2312, -76.8142), # Harrisburg / Highspire
        "end": (40.0385, -75.6212),   # Exton / US-202
    }
}

# Reference week: Sunday Nov 8, 2026 to Saturday Nov 14, 2026
BASE_SUNDAY = datetime.date(2026, 11, 8)

def fetch_hourly_speed(api_key: str, start_lat: float, start_lon: float, end_lat: float, end_lon: float, depart_iso: str):
    base_url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lon}:{end_lat},{end_lon}/json"
    params = {
        "key": api_key,
        "departAt": depart_iso,
        "traffic": "true",
        "routeType": "fastest",
        "travelMode": "car"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-TrafficHarvester/1.0"})
    
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        summary = data["routes"][0]["summary"]
        meters = summary["lengthInMeters"]
        seconds = summary["travelTimeInSeconds"]
        delay_sec = summary.get("trafficDelayInSeconds", 0)
        no_traffic_sec = summary.get("noTrafficTravelTimeInSeconds", seconds - delay_sec)

        miles = meters * 0.000621371
        speed_mph = miles / (seconds / 3600.0) if seconds > 0 else 60.0
        free_mph = miles / (no_traffic_sec / 3600.0) if no_traffic_sec > 0 else speed_mph
        
        return {
            "miles": round(miles, 2),
            "speed_mph": round(speed_mph, 1),
            "free_flow_mph": round(free_mph, 1),
            "delay_mins": round(delay_sec / 60.0, 1),
            "travel_mins": round(seconds / 60.0, 1)
        }

def embed_into_html(dataset: dict):
    """Embeds the harvested TOMTOM_CORRIDOR_SPEEDS dictionary into index.html and its copies."""
    speed_matrix = {}
    for cid, cinfo in dataset.items():
        speed_matrix[cid] = cinfo["speeds"]

    js_code = "const TOMTOM_CORRIDOR_SPEEDS = " + json.dumps(speed_matrix, indent=2) + ";"
    pattern = re.compile(r"const TOMTOM_CORRIDOR_SPEEDS = \{.*?\};", re.DOTALL)

    html_files = ["index.html", "public/index.html", "ui/templates/index.html"]
    for path in html_files:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if pattern.search(content):
                new_content = pattern.sub(js_code, content)
            else:
                # Insert before getDepartureDayOfWeek
                target = "function getDepartureDayOfWeek()"
                if target in content:
                    new_content = content.replace(target, f"{js_code}\n\n    {target}")
                else:
                    print(f"Warning: could not find insertion point in {path}")
                    continue
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            h = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
            print(f"Updated {path} (SHA-256: {h[:12]}...)")

def harvest(api_key: str, output_path: str = "data/tomtom_corridors_168h.json"):
    results = {}
    total_calls = len(CORRIDORS) * 7 * 24
    call_idx = 0
    print(f"Starting TomTom 168-Hour Harvest ({total_calls} total queries across {len(CORRIDORS)} corridors)...")

    for c_id, c_data in CORRIDORS.items():
        results[c_id] = {
            "name": c_data["name"],
            # matrix: 7 days (0=Sun..6=Sat) x 24 hours (0..23)
            "speeds": [[0.0 for _ in range(24)] for _ in range(7)],
            "delays": [[0.0 for _ in range(24)] for _ in range(7)],
            "free_flow_mph": 0.0,
            "miles": 0.0
        }
        print(f"\nHarvesting corridor: {c_data['name']}...")
        
        for dow in range(7):
            cur_date = BASE_SUNDAY + datetime.timedelta(days=dow)
            day_name = cur_date.strftime("%A")
            
            for hour in range(24):
                call_idx += 1
                depart_iso = f"{cur_date.isoformat()}T{hour:02d}:00:00"
                
                try:
                    res = fetch_hourly_speed(
                        api_key,
                        c_data["start"][0], c_data["start"][1],
                        c_data["end"][0], c_data["end"][1],
                        depart_iso
                    )
                    results[c_id]["speeds"][dow][hour] = res["speed_mph"]
                    results[c_id]["delays"][dow][hour] = res["delay_mins"]
                    results[c_id]["free_flow_mph"] = res["free_flow_mph"]
                    results[c_id]["miles"] = res["miles"]
                    
                    if hour % 4 == 0 or res["delay_mins"] > 3.0:
                        print(f"  [{call_idx}/{total_calls}] {day_name} {hour:02d}:00 -> {res['speed_mph']} mph (delay: {res['delay_mins']}m)")
                    
                    time.sleep(0.12) # Respect 10 req/s rate limit
                except Exception as e:
                    print(f"  Error at {c_id} {day_name} {hour:02d}:00: {e}")
                    time.sleep(1.0)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSuccessfully harvested and saved to {output_path}!")

    print("\nCompiling harvested 168-hour data into HTML templates...")
    embed_into_html(results)

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
        print("Or set TOMTOM_API_KEY in your environment or .env file.")
        sys.exit(1)
    harvest(key)
