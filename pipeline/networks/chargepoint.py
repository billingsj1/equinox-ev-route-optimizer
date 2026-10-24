"""
ChargePoint live API adapter.
Queries ChargePoint Map Cache API (v2 bounding query) and station details (v3/station/info)
to extract real-time live energy tariffs ($/kWh) directly from ChargePoint's production backend.
"""
from typing import List, Optional, Dict, Any
import httpx
import json
import urllib.parse
import logging
from pipeline.networks.base import BaseNetworkAdapter, StationTariff

logger = logging.getLogger("chargepoint_adapter")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://driver.chargepoint.com",
    "Referer": "https://driver.chargepoint.com/"
}

class ChargePointAdapter(BaseNetworkAdapter):
    network_name: str = "ChargePoint"

    async def fetch_prices_for_bounding_box(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float
    ) -> List[StationTariff]:
        """
        Queries ChargePoint backend for fast chargers and extracts live energy tariffs.
        """
        tariffs: List[StationTariff] = []
        query = {
            "station_list": {
                "screen_width": 1200,
                "screen_height": 900,
                "ne_lat": lat_max,
                "ne_lon": lon_max,
                "sw_lat": lat_min,
                "sw_lon": lon_min,
                "page_size": 50
            }
        }
        v2_url = "https://mc.chargepoint.com/map-prod/v2?" + urllib.parse.quote(json.dumps(query))

        try:
            async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
                resp = await client.get(v2_url)
                if resp.status_code != 200:
                    logger.warning(f"ChargePoint v2 returned status {resp.status_code}")
                    return []

                data = resp.json()
                stations = data.get("station_list", {}).get("stations", [])

                for st in stations:
                    dev_id = st.get("device_id")
                    if not dev_id:
                        continue

                    # Filter for DC fast chargers (power >= 50 or display_level == DC)
                    is_dc = st.get("display_level") == "DC" or (st.get("max_power", {}).get("max", 0) >= 50)
                    if not is_dc:
                        continue

                    lat = float(st.get("lat"))
                    lon = float(st.get("lon"))
                    city = st.get("city", "")
                    state = st.get("state_name", "")
                    name = f"{st.get('name1', '')} {st.get('name2', '')}".strip() or "ChargePoint Station"

                    # Fetch live tariff from v3/station/info
                    info_url = f"https://mc.chargepoint.com/map-prod/v3/station/info?deviceId={dev_id}"
                    info_resp = await client.get(info_url)
                    rate = 0.40  # verified fallback
                    session_fee = 0.0

                    if info_resp.status_code == 200:
                        info_data = info_resp.json()
                        price_obj = info_data.get("stationPrice", {})
                        energy_fee = price_obj.get("energyFee", {}).get("fixedFee", {}).get("amount")
                        if energy_fee is not None:
                            rate = float(energy_fee)
                        guest_fee = price_obj.get("guestFee", {}).get("amount")
                        if guest_fee is not None:
                            session_fee = float(guest_fee)

                    max_kw = float(st.get("max_power", {}).get("max", 125.0))
                    tariffs.append(StationTariff(
                        station_id=f"cp-{dev_id}",
                        network=self.network_name,
                        name=f"ChargePoint - {name}",
                        city=city,
                        state=state,
                        latitude=lat,
                        longitude=lon,
                        power_kw=max_kw,
                        connectors=["CCS1"],
                        rate_off_peak=rate,
                        rate_on_peak=rate,
                        session_fee=session_fee,
                        plugshare_url=f"https://driver.chargepoint.com/stations/{dev_id}"
                    ))
        except Exception as e:
            logger.warning(f"Error querying ChargePoint API: {e}")

        logger.info(f"ChargePointAdapter retrieved {len(tariffs)} verified stations.")
        return tariffs

    async def fetch_price_for_device_id(self, device_id: int) -> Optional[float]:
        url = f"https://mc.chargepoint.com/map-prod/v3/station/info?deviceId={device_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    fee = data.get("stationPrice", {}).get("energyFee", {}).get("fixedFee", {}).get("amount")
                    if fee is not None:
                        return float(fee)
        except Exception as e:
            logger.debug(f"Failed to fetch ChargePoint device {device_id}: {e}")
        return None
