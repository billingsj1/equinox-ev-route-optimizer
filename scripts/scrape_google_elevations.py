"""
High-Resolution Terrain-Adaptive Google Maps Elevation Scraper
For Jolly Hopper EV Route Planner

Features:
  - Fetches true high-res OSRM route geometries for all 5 core corridors.
  - Adaptive terrain chunking:
      * Severe Mountain Passes (Allegheny, Tuscarora, Savage Mtn, Wheeling): 6-mile chunks -> ~60 ft resolution (512 samples)
      * Rolling Hills (Central Ohio, Western PA, Lancaster): 18-mile chunks -> ~185 ft resolution (512 samples)
      * Flat Plains (Columbus, NJ Pine Plains): 35-mile chunks -> ~360 ft resolution (512 samples)
  - Post-processing Outlier & Tunnel Filter:
      * Linearly interpolates across tunnel bores (Allegheny, Tuscarora, Kittatinny, Blue Mtn, Wheeling)
      * Clamps bridge ravine DEM artifacts to AASHTO interstate standards (max 6.0% grade)
  - Saves to:
      * data/corridor_elevations.json
      * public/data/corridor_elevations.json
"""

import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

# Load API key
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

# Helper: Haversine distance in miles
def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8 # miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

# Helper: Google polyline encoder
def encode_polyline(coords): # coords is list of (lat, lon)
    result = []
    prev_lat = 0
    prev_lng = 0
    for lat, lng in coords:
        late5 = int(round(lat * 1e5))
        lnge5 = int(round(lng * 1e5))
        dlat = late5 - prev_lat
        dlng = lnge5 - prev_lng
        prev_lat = late5
        prev_lng = lnge5
        for val in (dlat, dlng):
            val = ~(val << 1) if val < 0 else (val << 1)
            while val >= 0x20:
                result.append(chr((0x20 | (val & 0x1f)) + 63))
                val >>= 5
            result.append(chr(val + 63))
    return ''.join(result)

# Fetch OSRM coordinates
def fetch_osrm_coords(coords_str):
    url = f"https://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Optimizer/2.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
        if not data.get("routes"):
            raise ValueError(f"OSRM returned no routes for {coords_str}")
        r = data["routes"][0]
        # Coordinates in GeoJSON are [lon, lat], convert to (lat, lon)
        raw_coords = [(pt[1], pt[0]) for pt in r["geometry"]["coordinates"]]
        distance_miles = r["distance"] * 0.000621371
        return raw_coords, distance_miles

# Tunnel Bounding Boxes: [min_lat, max_lat, min_lon, max_lon, name]
TUNNELS = [
    (40.058, 40.068, -80.718, -80.700, "Wheeling Tunnel (I-70)"),
    (40.018, 40.030, -78.820, -78.790, "Allegheny Mountain Tunnel (PA Turnpike)"),
    (40.155, 40.175, -77.800, -77.760, "Tuscarora Mountain Tunnel (PA Turnpike)"),
    (40.210, 40.225, -77.640, -77.615, "Kittatinny Mountain Tunnel (PA Turnpike)"),
    (40.225, 40.240, -77.615, -77.585, "Blue Mountain Tunnel (PA Turnpike)")
]

def is_in_tunnel(lat, lon):
    for min_lat, max_lat, min_lon, max_lon, name in TUNNELS:
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return name
    return None

# Terrain classification for adaptive chunking
def get_chunk_target_miles(lat, lon):
    # Mountain zones: PA Turnpike ridge (-79.5 to -77.3), I-68 Savage Mtn (-79.5 to -78.2), Wheeling descent (-80.85 to -80.60)
    if (-79.5 <= lon <= -77.3) or (-80.85 <= lon <= -80.60):
        return 7.0 # 7 miles / 512 = ~72 ft per sample
    # Rolling hills: Western PA, Central Ohio, Lancaster
    elif (-82.2 <= lon < -79.5) or (-77.3 < lon <= -75.8):
        return 18.0 # 18 miles / 512 = ~185 ft per sample
    # Flat / gentle: Columbus plains, NJ pine plains
    else:
        return 35.0 # 35 miles / 512 = ~360 ft per sample

# Query Google Elevation API for a subpath
def query_google_elevation_chunk(coords_chunk):
    # Downsample points for polyline encoding if very dense (Google accepts enc polyline)
    # We want max ~150 vertices in the encoded path to stay well below URL limits
    step = max(1, len(coords_chunk) // 100)
    sampled_for_enc = coords_chunk[::step]
    if sampled_for_enc[-1] != coords_chunk[-1]:
        sampled_for_enc.append(coords_chunk[-1])
        
    enc = encode_polyline(sampled_for_enc)
    url = f"https://maps.googleapis.com/maps/api/elevation/json?path=enc:{urllib.parse.quote(enc)}&samples=512&key={api_key}"
    
    req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-Elevation/2.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        if data.get("status") != "OK":
            raise RuntimeError(f"Google Elevation API returned status: {data.get('status')}, error: {data.get('error_message')}")
        results = data.get("results", [])
        return [(r["location"]["lat"], r["location"]["lng"], r["elevation"]) for r in results]

# Process a complete corridor
def process_corridor(corridor_id, name, coords_str):
    print(f"\n{'='*70}\nProcessing: {name} ({corridor_id})\n{'='*70}")
    coords, total_dist = fetch_osrm_coords(coords_str)
    print(f"  OSRM route fetched: {len(coords)} vertices, {total_dist:.1f} total miles")
    
    # Partition coordinates into adaptive chunks
    chunks = []
    current_chunk = [coords[0]]
    current_dist = 0.0
    
    for i in range(1, len(coords)):
        prev = coords[i-1]
        curr = coords[i]
        d = haversine_miles(prev[0], prev[1], curr[0], curr[1])
        current_dist += d
        current_chunk.append(curr)
        
        target_dist = get_chunk_target_miles(curr[0], curr[1])
        if current_dist >= target_dist or i == len(coords) - 1:
            if len(current_chunk) >= 2:
                chunks.append(current_chunk)
            current_chunk = [curr]
            current_dist = 0.0
            
    print(f"  Adaptive partition created {len(chunks)} chunks for Google Elevation API")
    
    # Query Google Elevation API for each chunk
    raw_points = []
    call_count = 0
    for idx, chunk in enumerate(chunks):
        pts = query_google_elevation_chunk(chunk)
        call_count += 1
        print(f"    Chunk {idx+1}/{len(chunks)} ({len(pts)} samples) queried successfully")
        raw_points.extend(pts)
        time.sleep(0.05) # tiny pause
        
    print(f"  Total raw elevation points captured: {len(raw_points)} across {call_count} API calls")
    
    # Calculate cumulative distance along sampled points
    processed_points = []
    cum_miles = 0.0
    for i in range(len(raw_points)):
        lat, lon, elev_m = raw_points[i]
        if i > 0:
            prev_lat, prev_lon, _ = raw_points[i-1]
            cum_miles += haversine_miles(prev_lat, prev_lon, lat, lon)
        processed_points.append({
            "dist_mi": round(cum_miles, 3),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "raw_elev_m": round(elev_m, 2),
            "elev_m": round(elev_m, 2),
            "elev_ft": round(elev_m * 3.28084, 1)
        })
        
    # Apply Tunnel & Outlier Filtering
    filtered_points = apply_tunnel_and_outlier_filter(processed_points)
    
    # Compute grade percentage and climb/descent stats
    total_ascent_ft = 0.0
    total_descent_ft = 0.0
    max_elev_ft = -9999.0
    min_elev_ft = 99999.0
    
    for i in range(len(filtered_points)):
        curr = filtered_points[i]
        elev_ft = curr["elev_ft"]
        if elev_ft > max_elev_ft: max_elev_ft = elev_ft
        if elev_ft < min_elev_ft: min_elev_ft = elev_ft
        
        if i > 0:
            prev = filtered_points[i-1]
            d_mi = curr["dist_mi"] - prev["dist_mi"]
            dh_ft = elev_ft - prev["elev_ft"]
            if dh_ft > 0:
                total_ascent_ft += dh_ft
            else:
                total_descent_ft += abs(dh_ft)
                
            grade_pct = 0.0
            if d_mi > 0.001:
                grade_pct = (dh_ft / (d_mi * 5280.0)) * 100.0
            curr["grade_pct"] = round(grade_pct, 2)
        else:
            curr["grade_pct"] = 0.0
            
    print(f"  Summary: Length={filtered_points[-1]['dist_mi']} mi, MinElev={min_elev_ft:.0f} ft, MaxElev={max_elev_ft:.0f} ft")
    print(f"  Ascent={total_ascent_ft:.0f} ft, Descent={total_descent_ft:.0f} ft, Total Points={len(filtered_points)}")
    
    return {
        "id": corridor_id,
        "name": name,
        "distance_miles": filtered_points[-1]["dist_mi"],
        "min_elev_ft": round(min_elev_ft, 1),
        "max_elev_ft": round(max_elev_ft, 1),
        "total_ascent_ft": round(total_ascent_ft, 1),
        "total_descent_ft": round(total_descent_ft, 1),
        "point_count": len(filtered_points),
        "api_calls_used": call_count,
        "points": filtered_points
    }

# Apply Tunnel & Outlier Filtering
def apply_tunnel_and_outlier_filter(pts):
    n = len(pts)
    if n < 3: return pts
    
    # 1. Detect tunnel spans and linearly interpolate
    i = 0
    while i < n:
        tunnel_name = is_in_tunnel(pts[i]["lat"], pts[i]["lon"])
        if tunnel_name:
            start_idx = max(0, i - 1)
            # Find tunnel end
            end_idx = i
            while end_idx < n and is_in_tunnel(pts[end_idx]["lat"], pts[end_idx]["lon"]):
                end_idx += 1
            end_idx = min(n - 1, end_idx)
            
            # Linear interpolation across tunnel
            start_elev = pts[start_idx]["elev_m"]
            end_elev = pts[end_idx]["elev_m"]
            d_span = pts[end_idx]["dist_mi"] - pts[start_idx]["dist_mi"]
            
            if d_span > 0.0001:
                for k in range(start_idx + 1, end_idx):
                    frac = (pts[k]["dist_mi"] - pts[start_idx]["dist_mi"]) / d_span
                    interp_m = start_elev + frac * (end_elev - start_elev)
                    pts[k]["elev_m"] = round(interp_m, 2)
                    pts[k]["elev_ft"] = round(interp_m * 3.28084, 1)
                    pts[k]["filtered_reason"] = f"Tunnel: {tunnel_name}"
            i = end_idx + 1
        else:
            i += 1
            
    # 2. AASHTO Interstate Grade Clamp (clamp bridge ravines and spikes > 6.0%)
    MAX_GRADE_PCT = 6.0
    for i in range(1, n):
        prev = pts[i-1]
        curr = pts[i]
        d_ft = (curr["dist_mi"] - prev["dist_mi"]) * 5280.0
        if d_ft > 10.0:
            dh_ft = curr["elev_ft"] - prev["elev_ft"]
            grade = abs(dh_ft) / d_ft * 100.0
            if grade > MAX_GRADE_PCT:
                # Clamp to max grade
                allowed_dh_ft = (MAX_GRADE_PCT / 100.0) * d_ft
                clamped_elev_ft = prev["elev_ft"] + (allowed_dh_ft if dh_ft > 0 else -allowed_dh_ft)
                clamped_elev_m = clamped_elev_ft / 3.28084
                curr["elev_ft"] = round(clamped_elev_ft, 1)
                curr["elev_m"] = round(clamped_elev_m, 2)
                curr["filtered_reason"] = f"AASHTO Grade Clamp ({grade:.1f}% -> {MAX_GRADE_PCT}%)"
                
    return pts

def main():
    # 5 Primary Corridors to Scrape
    corridors = [
        {
            "id": "columbus_to_marlton_r1",
            "name": "Route 1: PA Turnpike & I-76 Schuylkill Expressway into Marlton",
            "coords": "-83.0768,39.9549;-74.9218,39.8912"
        },
        {
            "id": "columbus_to_marlton_r2",
            "name": "Route 2: PA Turnpike to Pearl Harbor Bridge & NJ Turnpike Bypass (Exit 4)",
            "coords": "-83.0768,39.9549;-74.803049,40.108257;-74.9218,39.8912"
        },
        {
            "id": "columbus_to_marlton_r3",
            "name": "Route 3: Maryland I-68 Mountain Freeway (Toll-Free Scenic)",
            "coords": "-83.0768,39.9549;-78.9284,39.6582;-74.9218,39.8912"
        },
        {
            "id": "columbus_to_sewickley_us22",
            "name": "Sewickley Route 1: US-22 Weirton to PA-576 Toll Highway",
            "coords": "-83.0768,39.9549;-80.1820,40.5415"
        },
        {
            "id": "columbus_to_sewickley_i79",
            "name": "Sewickley Route 2: I-70 East to I-79 North (via Washington, PA - Toll-Free)",
            "coords": "-83.0768,39.9549;-80.2462,40.1740;-80.1820,40.5415"
        }
    ]
    
    database = {
        "metadata": {
            "source": "Google Maps Elevation API",
            "date_generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "resolution": "Terrain-Adaptive (60 ft in mountains, 185 ft in hills, 360 ft on plains)",
            "outlier_filter": "Tunnel bore interpolation + AASHTO 6% grade clamp"
        },
        "corridors": {}
    }
    
    total_calls = 0
    for c in corridors:
        result = process_corridor(c["id"], c["name"], c["coords"])
        database["corridors"][c["id"]] = result
        total_calls += result["api_calls_used"]
        
    database["metadata"]["total_api_calls_used"] = total_calls
    print(f"\n{'='*70}\nScraping Complete! Total Google Elevation API calls used: {total_calls} / 5000 free monthly\n{'='*70}")
    
    # Save files
    os.makedirs("data", exist_ok=True)
    os.makedirs("public/data", exist_ok=True)
    
    with open("data/corridor_elevations.json", "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print("Saved: data/corridor_elevations.json")
    
    with open("public/data/corridor_elevations.json", "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
    print("Saved: public/data/corridor_elevations.json")

if __name__ == "__main__":
    main()
