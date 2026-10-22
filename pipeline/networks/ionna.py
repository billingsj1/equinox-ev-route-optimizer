"""
IONNA joint venture network backend adapter.
"""
from typing import List
import httpx
import logging
from pipeline.networks.base import BaseNetworkAdapter, StationTariff

logger = logging.getLogger("ionna_adapter")

class IONNAAdapter(BaseNetworkAdapter):
    network_name: str = "IONNA"

    async def fetch_prices_for_bounding_box(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float
    ) -> List[StationTariff]:
        """
        Queries IONNA network backend endpoint.
        IONNA offers a standard 10% discount for GM EV drivers.
        """
        url = "https://api.ionnacharging.com/v1/stations"
        params = {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max}
        tariffs: List[StationTariff] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {"User-Agent": "IONNA-Mobile/1.0", "Accept": "application/json"}
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for loc in data.get("stations", []):
                        power = float(loc.get("power_kw", 150))
                        if power >= 100:
                            rate = float(loc.get("price_kwh", 0.39))
                            tariffs.append(StationTariff(
                                station_id=f"ionna-{loc.get('id')}",
                                network=self.network_name,
                                name=loc.get("name", "IONNA Rechargery"),
                                city=loc.get("city", ""),
                                state=loc.get("state", "PA"),
                                latitude=float(loc.get("latitude")),
                                longitude=float(loc.get("longitude")),
                                power_kw=power,
                                connectors=["CCS1", "NACS"],
                                rate_off_peak=rate,
                                rate_on_peak=rate,
                                session_fee=0.0,
                                gm_discount_eligible=True,
                                gm_discount_pct=0.10,
                                membership_rate_off_peak=round(rate * 0.90, 2),
                                membership_rate_on_peak=round(rate * 0.90, 2)
                            ))
                    return tariffs
        except Exception as e:
            logger.debug(f"IONNA API bypass: {e}")
        return []
