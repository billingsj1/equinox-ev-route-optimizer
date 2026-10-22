"""
Open Charge Map (OCM) station discovery client.
Filters strictly for CCS1 connectors and power >= 100 kW.
"""
from typing import List, Dict, Any, Optional
import httpx
import logging

logger = logging.getLogger("ocm_client")

class OpenChargeMapClient:
    BASE_URL = "https://api.openchargemap.io/v3/poi/"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 8.0):
        self.api_key = api_key
        self.timeout = timeout

    async def discover_chargers_in_bbox(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        min_power_kw: float = 100.0
    ) -> List[Dict[str, Any]]:
        """
        Queries OCM POI API with CCS1 (ID 33/32) and >= 100 kW.
        """
        params = {
            "output": "json",
            "boundingbox": f"({lat_min},{lon_min}),({lat_max},{lon_max})",
            "connectiontypeid": "33,32", # CCS1
            "minpowerkw": min_power_kw,
            "maxresults": 100,
            "compact": "true",
            "verbose": "false"
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {"User-Agent": "Equinox-Route-Optimizer/1.0"}
                resp = await client.get(self.BASE_URL, params=params, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.debug(f"OCM query fallback: {e}")
        return []
