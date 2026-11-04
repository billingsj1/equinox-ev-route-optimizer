import os
import requests
import json
import flexpolyline
import math

def load_keys():
    keys = {}
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    keys[k.strip()] = v.strip()
    return keys

here_key = load_keys().get('HERE_API_KEY')
if not here_key:
    print("ERROR: No HERE_API_KEY found")
    exit(1)

# Primary Waypoint Definitions for the 3 routes and corridors:
# Coordinates in lat,lon
WEST_HIGH_SCHOOL = "39.9537,-83.0560" # Columbus OH
MARLTON_NJ = "39.8912,-74.9205"       # Marlton NJ
SEWICKLEY_PA = "40.5401,-80.1834"     # Sewickley PA
DILLSBURG_PA = "40.1413,-77.0156"     # DeCamilla (Dillsburg PA)

# Corridors to query:
# 1. Columbus -> Marlton via PA Turnpike & Schuylkill (I-70 -> I-76 PA -> Schuylkill I-76)
# 2. Columbus -> Marlton via PA Turnpike & NJ Turnpike Bypass (I-70 -> I-76 PA -> NJ Turnpike Ex 6 to 4 -> NJ 73)
# 3. Columbus -> Marlton via Maryland I-68 / I-70 (I-70 -> I-68 MD -> I-70 MD -> US-40/I-95/NJ-73)
# 4. Columbus -> Dillsburg via PA Turnpike (I-70 -> I-76 -> US-15 -> Dillsburg)
# 5. Dillsburg -> Marlton via PA-283 / US-30 / Chester Springs / NJ-73
# 6. Columbus -> Sewickley via I-70 -> US-22 / PA-65
# 7. Columbus -> Sewickley via I-70 -> I-79 / Neville Island

corridors = [
    {
        "id": "pa_turnpike_schuylkill",
        "name": "I-70 to PA Turnpike via Philadelphia Schuylkill I-76",
        "origin": WEST_HIGH_SCHOOL,
        "destination": MARLTON_NJ,
        "via": ["40.1740,-80.2462", "40.1000,-78.5000", "40.0890,-75.3900", "39.9500,-75.1800"] # Washington PA, Bedford PA, King of Prussia, Schuylkill
    },
    {
        "id": "pa_turnpike_njtpk",
        "name": "I-70 to PA Turnpike via NJ Turnpike Bypass",
        "origin": WEST_HIGH_SCHOOL,
        "destination": MARLTON_NJ,
        "via": ["40.1740,-80.2462", "40.1000,-78.5000", "40.1300,-74.7500"] # Washington PA, Bedford PA, PA Turnpike Delaware River Ext
    },
    {
        "id": "maryland_i68_toll_free",
        "name": "I-70 to Maryland I-68 / I-70 Toll-Free Corridor",
        "origin": WEST_HIGH_SCHOOL,
        "destination": MARLTON_NJ,
        "via": ["39.6295,-79.9559", "39.6450,-78.7600", "39.6400,-77.7200"] # Morgantown WV, Cumberland MD, Hagerstown MD
    },
    {
        "id": "columbus_to_dillsburg",
        "name": "Columbus to Dillsburg (DeCamilla) via PA Turnpike & US-15",
        "origin": WEST_HIGH_SCHOOL,
        "destination": DILLSBURG_PA,
        "via": ["40.1740,-80.2462", "40.0300,-77.5000"] # Washington PA, Blue Mtn
    },
    {
        "id": "dillsburg_to_marlton",
        "name": "Dillsburg (DeCamilla) to Marlton via PA-283 / US-30 / Chester Springs",
        "origin": DILLSBURG_PA,
        "destination": MARLTON_NJ,
        "via": ["40.1800,-76.6000", "40.0500,-75.7000"] # PA-283 near Elizabethtown, Exton / Chester Springs US-30
    },
    {
        "id": "columbus_to_sewickley_us22",
        "name": "Columbus to Sewickley via I-70 & US-22 / PA-65",
        "origin": WEST_HIGH_SCHOOL,
        "destination": SEWICKLEY_PA,
        "via": ["40.0345,-81.5833", "40.3600,-80.6000"] # Cambridge OH, Steubenville / Weirton US-22
    },
    {
        "id": "columbus_to_sewickley_i79",
        "name": "Columbus to Sewickley via I-70 & I-79 North",
        "origin": WEST_HIGH_SCHOOL,
        "destination": SEWICKLEY_PA,
        "via": ["40.1740,-80.2462", "40.3500,-80.1200"] # Washington PA, I-79 Neville Island
    }
]

print(f"Ready to scrape {len(corridors)} corridors from HERE API...")
all_segments = []

for c in corridors:
    print(f"\nQuerying: {c['name']}...")
    url = "https://router.hereapi.com/v8/routes"
    params = {
        "transportMode": "car",
        "origin": c["origin"],
        "destination": c["destination"],
        "return": "polyline,summary",
        "spans": "maxSpeed,names",
        "apiKey": here_key
    }
    if c.get("via"):
        # HERE API supports 'via' parameter for waypoints
        params["via"] = c["via"]

    res = requests.get(url, params=params)
    if res.status_code != 200:
        print(f"  FAILED: HTTP {res.status_code}: {res.text[:300]}")
        continue

    data = res.json()
    routes = data.get("routes", [])
    if not routes:
        print("  No routes returned!")
        continue

    sec_count = 0
    span_count = 0
    for section in routes[0].get("sections", []):
        sec_count += 1
        poly_str = section.get("polyline")
        if not poly_str:
            continue
        coords = flexpolyline.decode(poly_str)
        spans = section.get("spans", [])
        span_count += len(spans)

        # Process each span into a continuous segment with start/end coordinate and speed limit
        for s_idx, sp in enumerate(spans):
            start_offset = sp["offset"]
            end_offset = spans[s_idx + 1]["offset"] if s_idx + 1 < len(spans) else len(coords) - 1
            if start_offset >= len(coords):
                continue
            
            speed_ms = sp.get("maxSpeed")
            speed_mph = round(speed_ms * 2.23694) if speed_ms else None
            names = [n["value"] for n in sp.get("names", [])]
            
            # Extract sample coordinates along this span
            span_coords = coords[start_offset:end_offset + 1]
            if not span_coords:
                span_coords = [coords[start_offset]]
            
            start_pt = span_coords[0]
            end_pt = span_coords[-1]
            mid_pt = span_coords[len(span_coords) // 2]
            
            all_segments.append({
                "corridor": c["id"],
                "speed_mph": speed_mph,
                "names": names,
                "start": [round(start_pt[0], 5), round(start_pt[1], 5)],
                "end": [round(end_pt[0], 5), round(end_pt[1], 5)],
                "mid": [round(mid_pt[0], 5), round(mid_pt[1], 5)],
                "points_count": len(span_coords)
            })

    print(f"  Success: {sec_count} sections, {span_count} spans parsed.")

print(f"\n==================================================")
print(f"Total speed limit segments collected across all corridors: {len(all_segments)}")
os.makedirs('data', exist_ok=True)
os.makedirs('public/data', exist_ok=True)

with open('data/here_speed_limits.json', 'w', encoding='utf-8') as f:
    json.dump(all_segments, f, indent=2)

with open('public/data/here_speed_limits.json', 'w', encoding='utf-8') as f:
    json.dump(all_segments, f, indent=2)

print(f"Saved database to data/here_speed_limits.json and public/data/here_speed_limits.json")
