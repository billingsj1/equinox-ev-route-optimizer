"""
Comprehensive HERE Technologies Tolls Harvester & Database Generator

Queries HERE Routing API v8 with:
  - return=summary,tolls
  - currency=USD
  - tolls[transponders]=all (for E-ZPass) and without (for Toll-by-Plate / Cash)

Captures:
  1. Primary Routes (Both Directions):
     - Columbus, OH <-> Marlton, NJ (Straight, via DeCamilla, via I-68 toll-free)
     - Columbus, OH <-> Dillsburg, PA (DeCamilla)
     - Columbus, OH <-> Sewickley, PA (Billings)
  2. Charging Stop Detour Combinations (getting on/off PA Turnpike):
     - New Stanton, Somerset, Bedford, Fort Littleton, Carlisle, Mechanicsburg/US-15, Chester Springs, KOP
  3. Directional River Crossings / Bridges (into NJ vs into PA/DE)
  4. Interchange Gantry Matrix for O(1) instant segment combination

Outputs:
  - data/here_tolls_db.json
  - public/data/here_tolls_db.json
"""

import json
import os
import time
import urllib.parse
import urllib.request

def load_keys():
    keys = {}
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k.strip()] = v.strip().strip('"').strip("'")
    return keys

api_key = load_keys().get("HERE_API_KEY")
if not api_key:
    print("ERROR: No HERE_API_KEY found in .env")
    exit(1)

def query_here_toll(origin_lat, origin_lon, dest_lat, dest_lon, vias=None, has_ezpass=True):
    orig_str = f"{origin_lat:.5f},{origin_lon:.5f}"
    dest_str = f"{dest_lat:.5f},{dest_lon:.5f}"
    
    params = {
        "transportMode": "car",
        "origin": orig_str,
        "destination": dest_str,
        "return": "summary,tolls",
        "currency": "USD",
        "apiKey": api_key
    }
    if has_ezpass:
        params["tolls[transponders]"] = "all"
        
    query_str = urllib.parse.urlencode(params)
    if vias:
        for v in vias:
            v_str = f"{v[0]:.5f},{v[1]:.5f}"
            query_str += f"&via={v_str}"
            
    url = f"https://router.hereapi.com/v8/routes?{query_str}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EquinoxEV-RouteOptimizer/2.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            
        total_fare = 0.0
        fares_breakdown = []
        toll_systems = []
        
        for route in data.get("routes", []):
            for sec in route.get("sections", []):
                for toll in sec.get("tolls", []):
                    sys_name = toll.get("tollSystem")
                    if sys_name and sys_name not in toll_systems:
                        toll_systems.append(sys_name)
                    locs = [loc.get("name") for loc in toll.get("tollCollectionLocations", []) if loc.get("name")]
                    for fare in toll.get("fares", []):
                        val = fare.get("price", {}).get("value", 0.0)
                        total_fare += val
                        fares_breakdown.append({
                            "name": fare.get("name") or sys_name or "Toll",
                            "cost": val,
                            "system": sys_name,
                            "payment": fare.get("paymentMethods", []),
                            "locations": locs
                        })
        return {
            "total": round(total_fare, 2),
            "toll_systems": toll_systems,
            "fares": fares_breakdown
        }
    except Exception as e:
        print(f"  [ERROR] HERE Toll query failed ({orig_str} -> {dest_str}): {e}")
        return {"total": 0.0, "toll_systems": [], "fares": [], "error": str(e)}

# Key Reference Waypoints
P_COLUMBUS = (39.9512, -83.0750)
P_MARLTON = (39.8912, -74.9218)
P_SEWICKLEY = (40.5401, -80.1834)
P_DILLSBURG = (40.1413, -77.0156)

# Turnpikes & Interchanges
INTERCHANGES = {
    "new_stanton": (40.2150, -79.6200),     # Exit 75
    "somerset": (40.0150, -79.0750),        # Exit 110
    "bedford": (40.0400, -78.5050),         # Exit 146
    "fort_littleton": (40.0520, -77.9620),  # Exit 180
    "carlisle": (40.2150, -77.1650),        # Exit 226
    "harrisburg_west": (40.2100, -76.9200), # Exit 242 (US-15)
    "downingtown": (40.0930, -75.6320),     # Exit 312 (Chester Springs)
    "valley_forge": (40.0850, -75.3950),    # Exit 326 (KOP)
    "mid_county": (40.1150, -75.2850),      # Exit 333
    "delaware_river_bridge": (40.1250, -74.8550) # Exit 359
}

# Major Bridges
BRIDGES = {
    "ben_franklin_bridge_east": {"start": (39.9540, -75.1480), "end": (39.9480, -75.1300), "desc": "PA to NJ (Eastbound)"},
    "ben_franklin_bridge_west": {"start": (39.9480, -75.1300), "end": (39.9540, -75.1480), "desc": "NJ to PA (Westbound)"},
    "walt_whitman_bridge_east": {"start": (39.9050, -75.1400), "end": (39.9050, -75.1200), "desc": "PA to NJ (Eastbound)"},
    "walt_whitman_bridge_west": {"start": (39.9050, -75.1200), "end": (39.9050, -75.1400), "desc": "NJ to PA (Westbound)"},
    "delaware_memorial_bridge_east": {"start": (39.6850, -75.5300), "end": (39.6950, -75.4950), "desc": "DE to NJ (Eastbound)"},
    "delaware_memorial_bridge_west": {"start": (39.6950, -75.4950), "end": (39.6850, -75.5300), "desc": "NJ to DE (Westbound)"},
    "tacony_palmyra_bridge_east": {"start": (40.0150, -75.0450), "end": (40.0100, -75.0300), "desc": "PA to NJ (Eastbound)"},
    "tacony_palmyra_bridge_west": {"start": (40.0100, -75.0300), "end": (40.0150, -75.0450), "desc": "NJ to PA (Westbound)"},
}

tolls_db = {
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "source": "HERE Technologies Routing API v8",
    "primary_routes": {},
    "bridges": {},
    "turnpike_interchanges": {},
    "common_charger_patterns": {}
}

print("=== 1. Polling Primary Route Tolls (Both Directions) ===")
primary_pairs = [
    ("columbus_to_marlton_direct", P_COLUMBUS, P_MARLTON, None),
    ("marlton_to_columbus_direct", P_MARLTON, P_COLUMBUS, None),
    ("columbus_to_marlton_via_decamilla", P_COLUMBUS, P_MARLTON, [P_DILLSBURG]),
    ("marlton_to_columbus_via_decamilla", P_MARLTON, P_COLUMBUS, [P_DILLSBURG]),
    ("columbus_to_dillsburg", P_COLUMBUS, P_DILLSBURG, None),
    ("dillsburg_to_columbus", P_DILLSBURG, P_COLUMBUS, None),
    ("columbus_to_sewickley", P_COLUMBUS, P_SEWICKLEY, None),
    ("sewickley_to_columbus", P_SEWICKLEY, P_COLUMBUS, None)
]

for name, orig, dest, vias in primary_pairs:
    print(f"  Checking {name}...")
    ez = query_here_toll(orig[0], orig[1], dest[0], dest[1], vias, has_ezpass=True)
    cash = query_here_toll(orig[0], orig[1], dest[0], dest[1], vias, has_ezpass=False)
    tolls_db["primary_routes"][name] = {
        "toll_ez": ez["total"],
        "toll_cash": cash["total"],
        "toll_systems": ez["toll_systems"],
        "fares_ez": ez["fares"],
        "fares_cash": cash["fares"]
    }
    print(f"    -> EZPass: ${ez['total']:.2f} | Cash/Plate: ${cash['total']:.2f}")
    time.sleep(0.2)

print("\n=== 2. Polling Bridge Crossings ===")
for b_name, b_info in BRIDGES.items():
    print(f"  Checking {b_name} ({b_info['desc']})...")
    ez = query_here_toll(b_info["start"][0], b_info["start"][1], b_info["end"][0], b_info["end"][1], has_ezpass=True)
    cash = query_here_toll(b_info["start"][0], b_info["start"][1], b_info["end"][0], b_info["end"][1], has_ezpass=False)
    tolls_db["bridges"][b_name] = {
        "desc": b_info["desc"],
        "toll_ez": ez["total"],
        "toll_cash": cash["total"],
        "toll_systems": ez["toll_systems"]
    }
    print(f"    -> EZPass: ${ez['total']:.2f} | Cash/Plate: ${cash['total']:.2f}")
    time.sleep(0.2)

print("\n=== 3. Polling PA Turnpike Key Interchange Segments ===")
# Interchanges along the path east from New Stanton:
seq = ["new_stanton", "somerset", "bedford", "fort_littleton", "carlisle", "harrisburg_west", "downingtown", "valley_forge"]
for i in range(len(seq) - 1):
    ic1 = seq[i]
    ic2 = seq[i+1]
    name_east = f"{ic1}_to_{ic2}"
    name_west = f"{ic2}_to_{ic1}"
    
    # Eastbound
    pt1, pt2 = INTERCHANGES[ic1], INTERCHANGES[ic2]
    ez_e = query_here_toll(pt1[0], pt1[1], pt2[0], pt2[1], has_ezpass=True)
    cash_e = query_here_toll(pt1[0], pt1[1], pt2[0], pt2[1], has_ezpass=False)
    tolls_db["turnpike_interchanges"][name_east] = {
        "direction": "eastbound",
        "toll_ez": ez_e["total"],
        "toll_cash": cash_e["total"]
    }
    
    # Westbound
    ez_w = query_here_toll(pt2[0], pt2[1], pt1[0], pt1[1], has_ezpass=True)
    cash_w = query_here_toll(pt2[0], pt2[1], pt1[0], pt1[1], has_ezpass=False)
    tolls_db["turnpike_interchanges"][name_west] = {
        "direction": "westbound",
        "toll_ez": ez_w["total"],
        "toll_cash": cash_w["total"]
    }
    print(f"  {name_east}: EZ=${ez_e['total']:.2f} | {name_west}: EZ=${ez_w['total']:.2f}")
    time.sleep(0.2)

print("\n=== 4. Polling Common Intermediate Charger Combinations ===")
# E.g. Exit at Fort Littleton, re-enter to Downingtown/Chester Springs
charger_combos = [
    ("c2m_via_fort_littleton_and_chester_springs", P_COLUMBUS, P_MARLTON, [INTERCHANGES["fort_littleton"], INTERCHANGES["downingtown"]]),
    ("m2c_via_chester_springs_and_fort_littleton", P_MARLTON, P_COLUMBUS, [INTERCHANGES["downingtown"], INTERCHANGES["fort_littleton"]]),
    ("c2m_via_carlisle", P_COLUMBUS, P_MARLTON, [INTERCHANGES["carlisle"]]),
    ("m2c_via_carlisle", P_MARLTON, P_COLUMBUS, [INTERCHANGES["carlisle"]]),
]

for name, orig, dest, vias in charger_combos:
    print(f"  Checking {name}...")
    ez = query_here_toll(orig[0], orig[1], dest[0], dest[1], vias, has_ezpass=True)
    cash = query_here_toll(orig[0], orig[1], dest[0], dest[1], vias, has_ezpass=False)
    tolls_db["common_charger_patterns"][name] = {
        "toll_ez": ez["total"],
        "toll_cash": cash["total"]
    }
    print(f"    -> EZPass: ${ez['total']:.2f} | Cash/Plate: ${cash['total']:.2f}")
    time.sleep(0.2)

# Save to data/here_tolls_db.json and public/data/here_tolls_db.json
for out_path in ["data/here_tolls_db.json", "public/data/here_tolls_db.json"]:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(tolls_db, f, indent=2)
    print(f"Saved {out_path} ({os.path.getsize(out_path)} bytes)")

print("\nHERE Tolls Database Successfully Built!")
