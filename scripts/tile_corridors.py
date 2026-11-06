import json
import time
import urllib.request
import xml.etree.ElementTree as ET

def fetch_osm_tiled(min_lon, min_lat, max_lon, max_lat, step=0.03):
    total_signals = 0
    total_stops = 0
    total_yields = 0
    total_roundabouts = 0
    
    seen_nodes = set()
    seen_ways = set()
    
    cur_lon = min_lon
    while cur_lon < max_lon:
        next_lon = min(max_lon, cur_lon + step)
        cur_lat = min_lat
        while cur_lat < max_lat:
            next_lat = min(max_lat, cur_lat + step)
            url = f"https://api.openstreetmap.org/api/0.6/map?bbox={cur_lon:.5f},{cur_lat:.5f},{next_lon:.5f},{next_lat:.5f}"
            headers = {"User-Agent": "EquinoxEV-RouteOptimizer/2.0"}
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    root = ET.fromstring(resp.read())
                    for node in root.findall('node'):
                        nid = node.attrib.get('id')
                        if nid in seen_nodes:
                            continue
                        seen_nodes.add(nid)
                        for tag in node.findall('tag'):
                            k = tag.attrib.get('k')
                            v = tag.attrib.get('v')
                            if k == 'highway' and v == 'traffic_signals':
                                total_signals += 1
                            elif k == 'highway' and v == 'stop':
                                total_stops += 1
                            elif k == 'highway' and v == 'give_way':
                                total_yields += 1
                    for way in root.findall('way'):
                        wid = way.attrib.get('id')
                        if wid in seen_ways:
                            continue
                        seen_ways.add(wid)
                        for tag in way.findall('tag'):
                            if tag.attrib.get('k') == 'junction' and tag.attrib.get('v') in ('roundabout', 'circular'):
                                total_roundabouts += 1
            except Exception as e:
                print(f"  tile error {cur_lat},{cur_lon}: {e}")
            time.sleep(0.4)
            cur_lat = next_lat
        cur_lon = next_lon
        
    return total_signals, total_stops, total_yields, total_roundabouts

# Load existing DB
with open("data/route_intersections_db.json", "r", encoding="utf-8") as f:
    db = json.load(f)

corridors_to_fix = {
    "schuylkill": {"name": "I-76 Schuylkill Expressway", "bbox": (-75.3881, 39.9575, -75.1812, 40.0903), "is_freeway": True},
    "vinest_benfranklin": {"name": "I-676 Vine St & Ben Franklin Bridge", "bbox": (-75.1812, 39.9405, -75.0802, 39.9575), "is_freeway": False},
    "nj70": {"name": "NJ-70 Marlton Pike", "bbox": (-75.0802, 39.8912, -74.9218, 39.9405), "is_freeway": False},
    "i276_paturnpike": {"name": "I-276 PA Turnpike", "bbox": (-75.3881, 40.0903, -74.7431, 40.1195), "is_freeway": True},
}

for ckey, cinfo in corridors_to_fix.items():
    print(f"Tiling corridor {ckey}...")
    min_lon, min_lat, max_lon, max_lat = cinfo["bbox"]
    sigs, stops, yields, rbs = fetch_osm_tiled(min_lon, min_lat, max_lon, max_lat, step=0.035)
    db["corridors"][ckey] = {
        "name": cinfo["name"],
        "is_freeway": cinfo["is_freeway"],
        "total_signals": sigs,
        "total_stops": stops,
        "total_yields": yields,
        "roundabouts": rbs
    }
    print(f"  -> {ckey}: signals={sigs}, stops={stops}, yields={yields}, roundabouts={rbs}")

with open("data/route_intersections_db.json", "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2)
with open("public/data/route_intersections_db.json", "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2)
print("Updated route_intersections_db.json successfully!")
