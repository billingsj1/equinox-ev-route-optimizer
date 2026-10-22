"""
Mercedes-Benz HPC / MN8 Energy backend adapter.
"""
from typing import List
import httpx
import logging
from pipeline.networks.base import BaseNetworkAdapter, StationTariff

logger = logging.getLogger("mercedes_adapter")

class MercedesBenzAdapter(BaseNetworkAdapter):
    network_name: str = "Mercedes-Benz"

    async def fetch_prices_for_bounding_box(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float
    ) -> List[StationTariff]:
        """
        Queries Mercedes-Benz High-Power Charging (HPC) Network API.
        """
        url = "https://api.mercedes-benz-charging.com/v1/stations"
        params = {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max}
        tariffs: List[StationTariff] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {"User-Agent": "MercedesMeCharge/4.2", "Accept": "application/json"}
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for loc in data.get("stations", []):
                        power = float(loc.get("power_kw", 150))
                        if power >= 100:
                            rate = float(loc.get("price_kwh", 0.44))
                            tariffs.append(StationTariff(
                                station_id=f"mb-{loc.get('id')}",
                                network=self.network_name,
                                name=loc.get("name", "Mercedes-Benz Charging Hub"),
                                city=loc.get("city", "Washington"),
                                state=loc.get("state", "PA"),
                                latitude=float(loc.get("latitude")),
                                longitude=float(loc.get("longitude")),
                                power_kw=power,
                                connectors=["CCS1", "NACS"],
                                rate_off_peak=rate,
                                rate_on_peak=rate,
                                session_fee=0.0
                            ))
                    return tariffs
        except Exception as e:
            logger.debug(f"Mercedes-Benz API bypass: {e}")
        return []
