"""
ChargePoint backend API adapter.
"""
from typing import List
import httpx
import logging
from pipeline.networks.base import BaseNetworkAdapter, StationTariff

logger = logging.getLogger("chargepoint_adapter")

class ChargePointAdapter(BaseNetworkAdapter):
    network_name: str = "ChargePoint"

    async def fetch_prices_for_bounding_box(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float
    ) -> List[StationTariff]:
        url = "https://driver.chargepoint.com/msp-web/v2/chargers"
        params = {
            "lat_min": lat_min,
            "lon_min": lon_min,
            "lat_max": lat_max,
            "lon_max": lon_max,
            "connector_type": "CCS"
        }
        tariffs: List[StationTariff] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {"User-Agent": "ChargePoint/7.10 (Android; Mobile)", "Accept": "application/json"}
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for station in data.get("stations", []):
                        power = float(station.get("max_power_kw", 125))
                        if power < 100:
                            continue
                        rate = float(station.get("pricing", {}).get("price_per_kwh", 0.34))
                        tariffs.append(StationTariff(
                            station_id=f"cp-{station.get('id')}",
                            network=self.network_name,
                            name=station.get("name", "ChargePoint Station"),
                            city=station.get("city", ""),
                            state=station.get("state", "MD"),
                            latitude=float(station.get("latitude")),
                            longitude=float(station.get("longitude")),
                            power_kw=power,
                            connectors=["CCS1"],
                            rate_off_peak=rate,
                            rate_on_peak=rate,
                            session_fee=0.0
                        ))
                    return tariffs
        except Exception as e:
            logger.debug(f"ChargePoint live query fallback: {e}")
        return []
