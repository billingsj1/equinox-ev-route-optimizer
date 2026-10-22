"""
Francis Energy backend API adapter.
"""
from typing import List
import httpx
import logging
from pipeline.networks.base import BaseNetworkAdapter, StationTariff

logger = logging.getLogger("francis_adapter")

class FrancisEnergyAdapter(BaseNetworkAdapter):
    network_name: str = "Francis Energy"

    async def fetch_prices_for_bounding_box(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float
    ) -> List[StationTariff]:
        """
        Queries Francis Energy CPO platform (EV Gateway / AmpUp backend).
        """
        url = "https://francis.evgateway.com/api/v2/locations"
        params = {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max}
        tariffs: List[StationTariff] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {"User-Agent": "FrancisEnergy/3.0 (Android)", "Accept": "application/json"}
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for loc in data.get("locations", []):
                        power = float(loc.get("power_kw", 150))
                        if power >= 100:
                            rate = float(loc.get("cost_per_kwh", 0.54))
                            tariffs.append(StationTariff(
                                station_id=f"fe-{loc.get('id')}",
                                network=self.network_name,
                                name=loc.get("name", "Francis Energy Station"),
                                city=loc.get("city", "Newburg"),
                                state=loc.get("state", "PA"),
                                latitude=float(loc.get("latitude")),
                                longitude=float(loc.get("longitude")),
                                power_kw=power,
                                connectors=["CCS1"],
                                rate_off_peak=rate,
                                rate_on_peak=rate,
                                session_fee=0.0
                            ))
                    return tariffs
        except Exception as e:
            logger.debug(f"Francis Energy live bypass: {e}")
        return []
