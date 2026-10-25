"""
Open Charge Map (OCM) station discovery client.
Filters strictly for CCS1 connectors (ConnectionTypeID 32) and power >= 100 kW.
Targets: IONNA, Mercedes-Benz HPC, Electrify America, Applegreen, ChargePoint, Francis Energy, EVgo.
"""
from typing import List, Dict, Any, Optional
import httpx
import logging

logger = logging.getLogger("ocm_client")

# Operator IDs in OCM
TARGET_OPERATOR_IDS = [
    3831, # IONNA
    3827, # Mercedes-Benz High-Power Charging
    3318, # Electrify America
    3516, # Applegreen Fast Charge
    5,    # ChargePoint
    3733, # Francis Energy
    15,   # EVgo
    3252  # NRG EVgo
]

# Blacklisted stations (e.g. fake OCM entries or permanently/temporarily closed locations)
BLOCKED_OCM_IDS = {307653, 285227, 307817} # 307653 = Fake IONNA Huber Heights; 285227 = Menlo Park Mall closed EVgo; 307817 = Myerstown EVgo GM Energy

def is_blocked_poi(poi: Dict[str, Any]) -> bool:
    poi_id = poi.get("ID")
    if poi_id in BLOCKED_OCM_IDS:
        return True
    addr = poi.get("AddressInfo", {})
    title = (addr.get("Title") or "").lower()
    town = (addr.get("Town") or "").lower()
    line1 = (addr.get("AddressLine1") or "").lower()
    op_title = (poi.get("OperatorInfo", {}).get("Title") or "").lower()
    all_text = f"{title} {town} {line1} {op_title}"
    
    # Huber Heights fake IONNA station
    if "huber heights" in all_text and "ionna" in all_text:
        return True
    # Menlo Park Mall closed EVgo station
    if "menlo park" in all_text:
        return True
    # Myerstown EVgo GM Energy station
    if "myerstown" in all_text:
        return True
    return False

TARGET_STATE_CONFIGS = {
    "OH": {"lat": 40.4173, "lon": -82.9071, "dist": 180, "aliases": ["OH", "OHIO"]},
    "PA": {"lat": 40.9699, "lon": -77.7278, "dist": 200, "aliases": ["PA", "PENNSYLVANIA"]},
    "NJ": {"lat": 40.0583, "lon": -74.4057, "dist": 110, "aliases": ["NJ", "NEW JERSEY"]},
    "WV": {"lat": 38.5976, "lon": -80.4549, "dist": 160, "aliases": ["WV", "WEST VIRGINIA"]},
    "MD": {"lat": 39.0458, "lon": -76.6413, "dist": 130, "aliases": ["MD", "MARYLAND"]},
}

class OpenChargeMapClient:
    BASE_URL = "https://api.openchargemap.io/v3/poi/"
    DEFAULT_API_KEY = "3e165280-87eb-4a3d-8741-7d80903bb87b"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 12.0):
        self.api_key = api_key or self.DEFAULT_API_KEY
        self.timeout = timeout

    async def discover_chargers_for_states(
        self,
        states: Optional[List[str]] = None,
        min_power_kw: float = 100.0
    ) -> List[Dict[str, Any]]:
        """
        Queries OCM POI API across target states with CCS1 (ID 32) and >= 100 kW.
        Uses geographic radius queries to reliably discover all chargers in each state.
        """
        states = states or list(TARGET_STATE_CONFIGS.keys())
        op_str = ",".join(str(op_id) for op_id in TARGET_OPERATOR_IDS)
        all_results = []
        seen_ids = set()

        headers = {
            "User-Agent": "Equinox-Route-Optimizer/1.0",
            "X-API-Key": self.api_key
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for state in states:
                cfg = TARGET_STATE_CONFIGS.get(state)
                if not cfg:
                    continue
                params = {
                    "output": "json",
                    "latitude": cfg["lat"],
                    "longitude": cfg["lon"],
                    "distance": cfg["dist"],
                    "distanceunit": "Miles",
                    "operatorid": op_str,
                    "connectiontypeid": "32", # CCS1
                    "minpowerkw": min_power_kw,
                    "maxresults": 250,
                    "compact": "true",
                    "verbose": "false"
                }
                try:
                    resp = await client.get(self.BASE_URL, params=params, headers=headers)
                    if resp.status_code == 200:
                        pois = resp.json()
                        for poi in pois:
                            if is_blocked_poi(poi):
                                continue
                            poi_id = poi.get("ID")
                            addr = poi.get("AddressInfo", {})
                            st_code = addr.get("StateOrProvince", "").strip().upper()
                            matches = any(
                                st_code == a or st_code.startswith(a + " ") or st_code == f"{a}."
                                for a in cfg["aliases"]
                            )
                            if poi_id not in seen_ids and matches:
                                seen_ids.add(poi_id)
                                all_results.append(poi)
                except Exception as e:
                    logger.warning(f"Error fetching OCM chargers for {state}: {e}")

        logger.info(f"Discovered {len(all_results)} stations via OCM across {states}")
        return all_results
