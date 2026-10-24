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

TARGET_STATES = ["OH", "PA", "NJ", "WV", "MD"]

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
        """
        states = states or TARGET_STATES
        op_str = ",".join(str(op_id) for op_id in TARGET_OPERATOR_IDS)
        all_results = []
        seen_ids = set()

        headers = {
            "User-Agent": "Equinox-Route-Optimizer/1.0",
            "X-API-Key": self.api_key
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for state in states:
                params = {
                    "output": "json",
                    "countrycode": "US",
                    "statename": state,
                    "operatorid": op_str,
                    "connectiontypeid": "32", # CCS1
                    "minpowerkw": min_power_kw,
                    "maxresults": 100,
                    "compact": "true",
                    "verbose": "false"
                }
                try:
                    resp = await client.get(self.BASE_URL, params=params, headers=headers)
                    if resp.status_code == 200:
                        pois = resp.json()
                        for poi in pois:
                            poi_id = poi.get("ID")
                            addr = poi.get("AddressInfo", {})
                            st_code = addr.get("StateOrProvince", "").strip().upper()
                            # Ensure state matches exactly or abbreviation
                            if poi_id not in seen_ids and st_code in [state, f"{state}."]:
                                seen_ids.add(poi_id)
                                all_results.append(poi)
                except Exception as e:
                    logger.warning(f"Error fetching OCM chargers for {state}: {e}")

        logger.info(f"Discovered {len(all_results)} stations via OCM across {states}")
        return all_results
