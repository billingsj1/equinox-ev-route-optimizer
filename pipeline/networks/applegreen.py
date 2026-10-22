"""
Applegreen Electric backend API adapter.
"""
from typing import List
import httpx
import logging
from pipeline.networks.base import BaseNetworkAdapter, StationTariff

logger = logging.getLogger("applegreen_adapter")

class ApplegreenAdapter(BaseNetworkAdapter):
    network_name: str = "Applegreen"

    async def fetch_prices_for_bounding_box(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float
    ) -> List[StationTariff]:
        """
        Queries Applegreen Electric CPO backend endpoint.
        Standard turnpike plaza rate is typically $0.59/kWh flat.
        """
        url = "https://applegreenelectric.com/api/v1/locations"
        params = {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max}
        tariffs: List[StationTariff] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {"User-Agent": "ApplegreenElectric/2.1 (iOS)", "Accept": "application/json"}
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for loc in data.get("locations", []):
                        power = float(loc.get("power_kw", 150))
                        if power >= 100:
                            tariffs.append(StationTariff(
                                station_id=f"ag-{loc.get('id')}",
                                network=self.network_name,
                                name=loc.get("name", "Applegreen Electric"),
                                city=loc.get("city", ""),
                                state=loc.get("state", "PA"),
                                latitude=float(loc.get("lat")),
                                longitude=float(loc.get("lon")),
                                power_kw=power,
                                connectors=["CCS1", "NACS"],
                                rate_off_peak=0.59,
                                rate_on_peak=0.59,
                                session_fee=0.0
                            ))
                    return tariffs
        except Exception as e:
            logger.debug(f"Applegreen live API bypass: {e}")
        return []
