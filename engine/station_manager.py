"""
Station discovery and spatial filtering engine.
Filters chargers by CCS1 / MagicDock, power >= 100 kW, and a 5-mile buffer
around the route linestring using Shapely.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json
import os
from shapely.geometry import Point, LineString
import httpx

MILES_TO_DEGREES_APPROX = 1.0 / 69.0  # Approx 1 degree lat = 69 miles

@dataclass
class ChargingStation:
    id: str
    name: str
    network: str
    city: str
    state: str
    latitude: float
    longitude: float
    power_kw: float
    connectors: List[str]
    rate_off_peak: float
    rate_on_peak: float
    gm_discount_eligible: bool
    gm_discount_pct: float
    ea_pass_eligible: bool
    membership_rate_off_peak: float
    membership_rate_on_peak: float
    session_fee: float
    plugshare_url: str
    distance_to_route_miles: float = 0.0

class StationManager:
    def __init__(self, data_file_path: Optional[str] = None):
        self.data_file_path = data_file_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "initial_prices.json"
        )
        self.stations: List[ChargingStation] = []
        self.load_stations()

    def load_stations(self):
        if not os.path.exists(self.data_file_path):
            self.stations = []
            return

        with open(self.data_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.stations = []
        for item in data:
            # Enforce hardware constraints: >= 100 kW and CCS1 / NACS MagicDock
            power_kw = float(item.get("power_kw", 0))
            connectors = item.get("connectors", [])
            has_ccs1 = any("ccs" in c.lower() for c in connectors)

            if power_kw >= 100 and has_ccs1:
                rate_reg = item.get("rate_regular", {})
                rate_mem = item.get("membership_rate", {})
                self.stations.append(ChargingStation(
                    id=item.get("id"),
                    name=item.get("name"),
                    network=item.get("network"),
                    city=item.get("city"),
                    state=item.get("state"),
                    latitude=float(item.get("latitude")),
                    longitude=float(item.get("longitude")),
                    power_kw=power_kw,
                    connectors=connectors,
                    rate_off_peak=float(rate_reg.get("off_peak", 0.45)),
                    rate_on_peak=float(rate_reg.get("on_peak", 0.45)),
                    gm_discount_eligible=bool(item.get("gm_discount_eligible", False)),
                    gm_discount_pct=float(item.get("gm_discount_pct", 0.0)),
                    ea_pass_eligible=bool(item.get("ea_pass_eligible", False)),
                    membership_rate_off_peak=float(rate_mem.get("off_peak", 0.45)),
                    membership_rate_on_peak=float(rate_mem.get("on_peak", 0.45)),
                    session_fee=float(item.get("session_fee", 0.0)),
                    plugshare_url=item.get("plugshare_url", "")
                ))

    def get_effective_rate(
        self,
        station: ChargingStation,
        hour: int = 14,
        is_gm_ev: bool = True,
        has_ea_pass: bool = False,
        has_tesla_membership: bool = False
    ) -> float:
        """
        Calculates exact per-kWh cost considering Time of Use, GM OEM perks, and network memberships.
        """
        is_off_peak = (hour < 10 or hour >= 22)
        base_rate = station.rate_off_peak if is_off_peak else station.rate_on_peak

        # 1. GM EV perks: 10% discount at IONNA and EVgo
        if is_gm_ev and station.gm_discount_eligible:
            return round(base_rate * (1.0 - station.gm_discount_pct), 2)

        # 2. Electrify America Pass+ (25% off) if eligible at that specific station
        if has_ea_pass and station.network.lower() == "electrify america" and station.ea_pass_eligible:
            mem_rate = station.membership_rate_off_peak if is_off_peak else station.membership_rate_on_peak
            return round(mem_rate, 2)

        # 3. Tesla Supercharger membership
        if has_tesla_membership and station.network.lower() == "tesla":
            mem_rate = station.membership_rate_off_peak if is_off_peak else station.membership_rate_on_peak
            return round(mem_rate, 2)

        return round(base_rate, 2)

    def find_chargers_along_route(
        self,
        route_coords: List[List[float]], # [[lon, lat], ...]
        buffer_miles: float = 5.0
    ) -> List[ChargingStation]:
        """
        Finds all qualifying stations within a 5-mile buffer of the route polyline.
        """
        if len(route_coords) < 2:
            return []

        # Build 2D line string in (lon, lat)
        line = LineString([(pt[0], pt[1]) for pt in route_coords])

        matching = []
        buffer_degrees = buffer_miles * MILES_TO_DEGREES_APPROX

        for station in self.stations:
            pt = Point(station.longitude, station.latitude)
            dist_deg = line.distance(pt)
            dist_miles = dist_deg * 69.0

            if dist_miles <= buffer_miles:
                station.distance_to_route_miles = round(dist_miles, 2)
                matching.append(station)

        # Sort matching stations according to their projection along the route polyline
        matching.sort(key=lambda s: line.project(Point(s.longitude, s.latitude)))
        return matching
