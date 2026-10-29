"""
Base CPO Network adapter for intercepting backend pricing APIs.
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import httpx
import logging

logger = logging.getLogger("cpo_adapter")

@dataclass
class StationTariff:
    station_id: str
    network: str
    name: str
    city: str
    state: str
    latitude: float
    longitude: float
    power_kw: float
    connectors: List[str]
    rate_off_peak: float
    rate_on_peak: float
    session_fee: float
    gm_discount_eligible: bool = False
    gm_discount_pct: float = 0.0
    ea_pass_eligible: bool = False
    membership_rate_off_peak: float = 0.45
    membership_rate_on_peak: float = 0.45
    plugshare_url: str = ""
    tou_rates: Optional[List[Dict[str, Any]]] = None

class BaseNetworkAdapter:
    network_name: str = "Base"

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    async def fetch_prices_for_bounding_box(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float
    ) -> List[StationTariff]:
        """
        Queries the network's backend API. Subclasses must implement this.
        """
        raise NotImplementedError
