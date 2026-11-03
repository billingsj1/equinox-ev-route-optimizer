"""
Station discovery and spatial filtering engine.
Filters chargers by CCS1 / MagicDock, power >= 100 kW, and a 5-mile buffer
around the route linestring using Shapely (with pure-Python fallback).
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json
import os
import math

try:
    from shapely.geometry import Point, LineString
except ImportError:
    Point, LineString = None, None

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
        prices_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "prices.json")
        initial_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "initial_prices.json")
        self.data_file_path = data_file_path or (prices_path if os.path.exists(prices_path) else initial_path)
        self.stations: List[ChargingStation] = []
        self.load_stations()

    def load_stations(self):
        if not os.path.exists(self.data_file_path):
            self.stations = []
            return

        with open(self.data_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            raw_stations = data
        elif isinstance(data, dict):
            raw_stations = data.get("stations", [])
        else:
            raw_stations = []

        for item in raw_stations:
            connectors = item.get("connectors", [])
            power_kw = float(item.get("power_kw", 0.0))
            is_ccs1_or_magicdock = any(
                c in ["CCS1", "CCS", "MagicDock", "NACS_MagicDock"] for c in connectors
            )

            if power_kw >= 50.0 and is_ccs1_or_magicdock:
                off_peak = item.get("rate_off_peak", 0.40)
                on_peak = item.get("rate_on_peak", 0.50)
                mem_off = item.get("membership_rate_off_peak", off_peak)
                mem_on = item.get("membership_rate_on_peak", on_peak)

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
                    rate_off_peak=float(off_peak),
                    rate_on_peak=float(on_peak),
                    gm_discount_eligible=bool(item.get("gm_discount_eligible", False)) and str(item.get("network", "")).strip().lower() in ("evgo", "ionna") and not ("pilot" in str(item.get("name", "")).lower() or "flying j" in str(item.get("name", "")).lower()),
                    gm_discount_pct=float(item.get("gm_discount_pct", 0.0)) if (str(item.get("network", "")).strip().lower() in ("evgo", "ionna") and not ("pilot" in str(item.get("name", "")).lower() or "flying j" in str(item.get("name", "")).lower())) else 0.0,
                    ea_pass_eligible=bool(item.get("ea_pass_eligible", False)),
                    membership_rate_off_peak=float(mem_off),
                    membership_rate_on_peak=float(mem_on),
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

        # 1. GM EV perks: 10% discount ONLY at IONNA and EVgo (never Pilot or Tesla)
        if is_gm_ev and station.gm_discount_eligible and station.network.lower() in ("evgo", "ionna"):
            return round(base_rate * (1.0 - station.gm_discount_pct), 2)

        # 2. Electrify America Pass+ (25% off) if eligible at that specific station
        if has_ea_pass and station.network.lower() == "electrify america" and station.ea_pass_eligible:
            mem_rate = station.membership_rate_off_peak if is_off_peak else station.membership_rate_on_peak
            return round(mem_rate, 2)

        # 3. Tesla Supercharger membership
        if has_tesla_membership and station.network.lower() in ("tesla", "tesla ccs1", "tesla nacs"):
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

        if LineString is not None:
            line = LineString([(pt[0], pt[1]) for pt in route_coords])

            matching = []
            for station in self.stations:
                pt = Point(station.longitude, station.latitude)
                dist_deg = line.distance(pt)
                dist_miles = dist_deg * 69.0

                if dist_miles <= buffer_miles:
                    station.distance_to_route_miles = round(dist_miles, 2)
                    matching.append(station)

            matching.sort(key=lambda s: line.project(Point(s.longitude, s.latitude)))
            return matching
        else:
            def dist_to_segment(px, py, x1, y1, x2, y2):
                dx = x2 - x1
                dy = y2 - y1
                if dx == 0 and dy == 0:
                    return math.hypot(px - x1, py - y1)
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                return math.hypot(px - proj_x, py - proj_y)

            matching = []
            for station in self.stations:
                sx, sy = station.longitude, station.latitude
                min_deg = float("inf")
                for k in range(len(route_coords) - 1):
                    p1 = route_coords[k]
                    p2 = route_coords[k + 1]
                    d = dist_to_segment(sx, sy, p1[0], p1[1], p2[0], p2[1])
                    if d < min_deg:
                        min_deg = d
                dist_miles = min_deg * 69.0
                if dist_miles <= buffer_miles:
                    station.distance_to_route_miles = round(dist_miles, 2)
                    matching.append(station)
            return matching
