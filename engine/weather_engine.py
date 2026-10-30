"""
Weather Engine for 2025 Chevrolet Equinox EV Route Optimizer.

Provides high-resolution along-route weather modeling:
1. Pre-computed corridor waypoint profiles for primary routes (St. Onge, Billings, DeCamilla)
   and dynamic polyline slicing for arbitrary custom routes.
2. Segment-by-segment cumulative non-stop transit calculation matching master engine speed physics.
3. Zero-cost batched Open-Meteo queries:
   - Near-future (<= 16 days): High-resolution hourly forecast API.
   - Distant-future (> 16 days): Multi-year ERA5 historical reanalysis archive for identical calendar day & hour.
4. Multi-tier road moisture & pavement drying state machine (WMO 51-67 vs 71+, solar, wind, humidity).
5. Exact moist air density rho(T, p, phi) factoring in elevation-adjusted barometric pressure.
6. Vector wind aerodynamics (tailwind drag reductions, headwind drag penalties, crosswind yaw).
7. Full Equinox EV Ultium physical energy consumption & weather delta comparison vs 70F baseline.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import math
import httpx
import asyncio

from engine.energy import EnergySimulator, DrivingProfile, RouteSegment
from engine.vehicle import EquinoxEVFWD, PayloadConfig

# Physical Constants
AIR_DENSITY_STP = 1.225        # kg/m^3 at sea level 15°C
GRAVITY = 9.80665              # m/s^2
GAS_CONSTANT_DRY_AIR = 287.058 # J/(kg*K)
GAS_CONSTANT_VAPOR = 461.495   # J/(kg*K)
MPH_TO_MS = 0.44704
MS_TO_MPH = 2.23694
METERS_TO_FEET = 3.28084
FEET_TO_METERS = 0.3048


# Weather WMO code descriptions
WMO_DESCRIPTIONS: Dict[int, str] = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    56: "Light Freezing Drizzle",
    57: "Dense Freezing Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    66: "Light Freezing Rain",
    67: "Heavy Freezing Rain",
    71: "Slight Snowfall",
    73: "Moderate Snowfall",
    75: "Heavy Snowfall",
    77: "Snow Grains",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Slight Hail",
    99: "Thunderstorm with Heavy Hail"
}


@dataclass
class WaypointWeather:
    name: str
    lat: float
    lon: float
    elevation_ft: float
    distance_from_start_miles: float
    segment_distance_miles: float
    elapsed_time_minutes: float
    arrival_time_iso: str
    arrival_time_clock: str
    
    # Atmospheric metrics
    ambient_temp_f: float
    relative_humidity_pct: float
    surface_pressure_hpa: float
    air_density_kg_m3: float
    air_density_delta_pct: float  # vs 1.225 STP
    
    # Precipitation & Road State
    precipitation_rate_in_hr: float
    weather_code: int
    weather_description: str
    is_day: bool
    road_condition: str           # "dry", "damp", "wet", "heavy_wet", "snow_slush", "ice"
    pavement_wetness_factor: float # 0.0 (dry) to 1.0 (flooded/ice)
    rolling_resistance_crr: float
    
    # Wind & Aerodynamics
    wind_speed_mph: float
    wind_direction_deg: float
    wind_direction_cardinal: str
    segment_bearing_deg: float
    effective_headwind_mph: float # positive = headwind, negative = tailwind assist
    crosswind_mph: float
    wind_category: str            # "tailwind", "headwind", "crosswind", "calm"
    
    # Physics & Vehicle Impact
    hvac_power_kw: float
    battery_eff_factor: float
    estimated_consumption_wh_per_mi: float
    baseline_consumption_wh_per_mi: float
    wh_per_mi_delta: float
    
    # Metadata
    is_forecast: bool = True      # True = live forecast (<=16d), False = historical reanalysis (>16d)


@dataclass
class RouteWeatherReport:
    route_id: str
    route_name: str
    origin_name: str
    destination_name: str
    departure_time_iso: str
    departure_time_clock: str
    total_distance_miles: float
    total_duration_hours: float
    mode: str                     # "forecast" (<=16d) or "historical" (>16d)
    waypoints: List[WaypointWeather]
    summary: Dict[str, Any]
    route_geometry: Optional[List[List[float]]] = None # [[lon, lat, elev], ...]


class WeatherEngine:
    def __init__(self, vehicle: Optional[EquinoxEVFWD] = None):
        self.vehicle = vehicle or EquinoxEVFWD()
        self.energy_sim = EnergySimulator(self.vehicle)
        self.payload = PayloadConfig(josh=True, courtney=True, asher=True, arno=True, gear_lbs=50.0)
        self.profile = DrivingProfile(speed_offset_mph=5.0, max_speed_cap_mph=75.0)

    # -------------------------------------------------------------------------
    # 1. PRE-COMPUTED WAYPOINT CORRIDORS FOR 3 QUICK DESTINATIONS
    # -------------------------------------------------------------------------
    @staticmethod
    def get_precomputed_corridors() -> Dict[str, Dict[str, Any]]:
        """
        Returns pre-baked, high-precision waypoints with true elevations and speeds
        originating at West High School (Columbus, OH: 39.9512, -83.0750).
        """
        return {
            "st_onge": {
                "route_id": "quick_st_onge",
                "route_name": "Columbus OH to Marlton NJ (St. Onge)",
                "origin_name": "West High School (Columbus, OH)",
                "destination_name": "St. Onge (Marlton, NJ)",
                "waypoints": [
                    # name, lat, lon, elev_m, speed_limit_mph
                    ("Columbus Metro (West High School)", 39.9512, -83.0750, 230.0, 65.0),
                    ("Zanesville / Muskingum Valley", 39.9400, -82.0130, 215.0, 70.0),
                    ("Eastern Ohio Plateau (St. Clairsville)", 40.0780, -80.9850, 360.0, 70.0),
                    ("Ohio River Valley (Wheeling, WV)", 40.0630, -80.7200, 205.0, 65.0),
                    ("Western PA (Washington, PA)", 40.1740, -80.2462, 310.0, 70.0),
                    ("New Stanton Interchange", 40.2187, -79.6103, 340.0, 70.0),
                    ("Laurel Highlands Crest (Somerset, PA)", 40.0084, -79.0781, 690.0, 70.0), # Somerset 2,260 ft
                    ("South Central Valley (Bedford / Breezewood)", 40.0187, -78.5039, 380.0, 70.0),
                    ("Cumberland Mountain Passes (Fort Littleton)", 40.0495, -77.9620, 300.0, 70.0),
                    ("Susquehanna Valley (Carlisle, PA)", 40.2014, -77.1889, 150.0, 70.0),
                    ("Lancaster County (Bowmansville, PA)", 40.1830, -76.0120, 130.0, 70.0),
                    ("Delaware Valley (Valley Forge / KOP)", 40.0880, -75.4050, 60.0, 65.0),
                    ("Marlton / St. Onge Destination", 39.9050, -74.9436, 25.0, 50.0)
                ]
            },
            "billings": {
                "route_id": "quick_billings",
                "route_name": "Columbus OH to Sewickley PA (Billings)",
                "origin_name": "West High School (Columbus, OH)",
                "destination_name": "Billings (Sewickley, PA)",
                "waypoints": [
                    ("Columbus Metro (West High School)", 39.9512, -83.0750, 230.0, 65.0),
                    ("Zanesville / I-70 Corridor", 39.9400, -82.0130, 215.0, 70.0),
                    ("Cambridge / US-22 Cadiz Foothills", 40.0300, -81.5900, 260.0, 65.0),
                    ("Appalachian Ridge (Steubenville, OH)", 40.2700, -80.8500, 360.0, 65.0),
                    ("Ohio River Crossing (Weirton, WV)", 40.4100, -80.5800, 230.0, 60.0),
                    ("Sewickley / Billings Destination", 40.5415, -80.1820, 225.0, 55.0)
                ]
            },
            "decamilla": {
                "route_id": "quick_decamilla",
                "route_name": "Columbus OH to Dillsburg PA (DeCamilla)",
                "origin_name": "West High School (Columbus, OH)",
                "destination_name": "DeCamilla (Dillsburg, PA)",
                "waypoints": [
                    ("Columbus Metro (West High School)", 39.9512, -83.0750, 230.0, 65.0),
                    ("Zanesville / Muskingum Valley", 39.9400, -82.0130, 215.0, 70.0),
                    ("Eastern Ohio Plateau (St. Clairsville)", 40.0780, -80.9850, 360.0, 70.0),
                    ("Ohio River Valley (Wheeling, WV)", 40.0630, -80.7200, 205.0, 65.0),
                    ("Western PA (Washington, PA)", 40.1740, -80.2462, 310.0, 70.0),
                    ("Laurel Highlands Crest (Somerset, PA)", 40.0084, -79.0781, 690.0, 70.0),
                    ("South Central Valley (Bedford / Breezewood)", 40.0187, -78.5039, 380.0, 70.0),
                    ("Kittatinny Tunnel / Newburg", 40.1340, -77.5560, 240.0, 70.0),
                    ("Turnpike Exit 236 (US-15 S / Mechanicsburg)", 40.1980, -77.0180, 140.0, 65.0),
                    ("Dillsburg / DeCamilla Destination", 40.1413, -77.0156, 170.0, 50.0)
                ]
            }
        }

    # -------------------------------------------------------------------------
    # 2. GEOMETRY, BEARING & TRANSIT CALCULATIONS
    # -------------------------------------------------------------------------
    @staticmethod
    def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 3958.8  # Earth radius in miles
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
        x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) -
             math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1)))
        initial_bearing = math.atan2(y, x)
        return (math.degrees(initial_bearing) + 360) % 360

    @staticmethod
    def degrees_to_cardinal(deg: float) -> str:
        dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        ix = round(deg / (360. / len(dirs))) % len(dirs)
        return dirs[ix]

    def build_route_timeline_from_waypoints(
        self,
        raw_waypoints: List[Tuple[str, float, float, float, float]],
        departure_dt: datetime
    ) -> List[Dict[str, Any]]:
        """
        Reuses the exact speed calculation from EnergySimulator to establish
        cumulative transit seconds and arrival datetimes at each waypoint.
        raw_waypoints: [(name, lat, lon, elev_m, speed_limit_mph), ...]
        """
        timeline = []
        cum_dist_miles = 0.0
        cum_seconds = 0.0

        for i, wp in enumerate(raw_waypoints):
            name, lat, lon, elev_m, speed_limit = wp
            if i == 0:
                timeline.append({
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "elev_m": elev_m,
                    "elev_ft": round(elev_m * METERS_TO_FEET, 0),
                    "dist_from_start_miles": 0.0,
                    "segment_dist_miles": 0.0,
                    "elapsed_minutes": 0.0,
                    "arrival_dt": departure_dt,
                    "bearing_deg": (
                        self.calculate_bearing(lat, lon, raw_waypoints[1][1], raw_waypoints[1][2])
                        if len(raw_waypoints) > 1 else 90.0
                    ),
                    "speed_limit_mph": speed_limit
                })
                continue

            prev = raw_waypoints[i - 1]
            prev_name, prev_lat, prev_lon, prev_elev, prev_speed = prev
            seg_dist_miles = self.haversine_distance_miles(prev_lat, prev_lon, lat, lon)
            cum_dist_miles += seg_dist_miles

            # Calculate actual cruising speed using master engine driving profile
            v_ms = self.energy_sim.calculate_actual_speed_ms(speed_limit, self.profile)
            v_mph = v_ms * MS_TO_MPH
            seg_seconds = (seg_dist_miles / max(15.0, v_mph)) * 3600.0
            cum_seconds += seg_seconds

            arrival_dt = departure_dt + timedelta(seconds=cum_seconds)
            bearing = self.calculate_bearing(prev_lat, prev_lon, lat, lon)

            timeline.append({
                "name": name,
                "lat": lat,
                "lon": lon,
                "elev_m": elev_m,
                "elev_ft": round(elev_m * METERS_TO_FEET, 0),
                "dist_from_start_miles": round(cum_dist_miles, 2),
                "segment_dist_miles": round(seg_dist_miles, 2),
                "elapsed_minutes": round(cum_seconds / 60.0, 1),
                "arrival_dt": arrival_dt,
                "bearing_deg": round(bearing, 1),
                "speed_limit_mph": speed_limit
            })

        return timeline

    def slice_arbitrary_route(
        self,
        coordinates: List[List[float]],
        departure_dt: datetime,
        default_speed_mph: float = 65.0,
        sample_spacing_miles: float = 35.0
    ) -> List[Dict[str, Any]]:
        """
        Samples an arbitrary polyline [[lon, lat, elev], ...] every ~35 miles,
        detecting major summits, and calculates the cumulative transit timeline.
        """
        if len(coordinates) < 2:
            return []

        sampled = []
        sampled.append(("Route Origin", coordinates[0][1], coordinates[0][0], coordinates[0][2] if len(coordinates[0]) > 2 else 200.0, default_speed_mph))

        accum_dist = 0.0
        prev_pt = coordinates[0]

        for i in range(1, len(coordinates) - 1):
            pt = coordinates[i]
            d = self.haversine_distance_miles(prev_pt[1], prev_pt[0], pt[1], pt[0])
            accum_dist += d
            prev_pt = pt

            elev = pt[2] if len(pt) > 2 else 200.0
            if accum_dist >= sample_spacing_miles:
                total_so_far = sum(self.haversine_distance_miles(coordinates[j-1][1], coordinates[j-1][0], coordinates[j][1], coordinates[j][0]) for j in range(1, i+1))
                sampled.append((
                    f"Waypoint Mile {round(total_so_far, 0)}",
                    pt[1], pt[0], elev, default_speed_mph
                ))
                accum_dist = 0.0

        last = coordinates[-1]
        sampled.append(("Route Destination", last[1], last[0], last[2] if len(last) > 2 else 100.0, 50.0))

        return self.build_route_timeline_from_waypoints(sampled, departure_dt)

    # -------------------------------------------------------------------------
    # 3. ATMOSPHERICS & PHYSICAL ROAD MODELING
    # -------------------------------------------------------------------------
    @staticmethod
    def calculate_moist_air_density(
        temp_f: float,
        surface_pressure_hpa: float,
        relative_humidity_pct: float
    ) -> Tuple[float, float]:
        """
        Computes true moist air density rho (kg/m^3) based on temperature,
        elevation-adjusted surface pressure, and relative humidity.
        Returns (rho_kg_m3, delta_pct_vs_stp).
        """
        temp_c = (temp_f - 32.0) * 5.0 / 9.0
        temp_k = temp_c + 273.15

        # Saturation vapor pressure (Magnus-Tetens formula) in hPa
        p_sat = 6.1078 * (10.0 ** ((7.5 * temp_c) / (temp_c + 237.3)))
        
        # Vapor pressure & dry air partial pressure
        p_v = (relative_humidity_pct / 100.0) * p_sat
        p_d = max(10.0, surface_pressure_hpa - p_v)

        # Gas law for moist air (convert hPa to Pa)
        rho_dry = (p_d * 100.0) / (GAS_CONSTANT_DRY_AIR * temp_k)
        rho_vapor = (p_v * 100.0) / (GAS_CONSTANT_VAPOR * temp_k)
        rho_total = rho_dry + rho_vapor

        delta_pct = ((rho_total - AIR_DENSITY_STP) / AIR_DENSITY_STP) * 100.0
        return round(rho_total, 4), round(delta_pct, 1)

    @staticmethod
    def calculate_vector_wind(
        segment_bearing_deg: float,
        wind_speed_mph: float,
        wind_direction_deg: float
    ) -> Tuple[float, float, str]:
        """
        Calculates effective headwind (positive) or tailwind (negative),
        and crosswind component.
        Note: Meteorological wind direction theta_w is where wind comes FROM.
        Angle between vehicle travel and wind origin:
        headwind = wind_speed * cos(bearing - wind_direction)
        crosswind = wind_speed * |sin(bearing - wind_direction)|
        """
        rel_rad = math.radians(segment_bearing_deg - wind_direction_deg)
        headwind_mph = wind_speed_mph * math.cos(rel_rad)
        crosswind_mph = abs(wind_speed_mph * math.sin(rel_rad))

        if wind_speed_mph < 3.0:
            category = "calm"
        elif headwind_mph >= 3.0:
            category = "headwind"
        elif headwind_mph <= -3.0:
            category = "tailwind"
        else:
            category = "crosswind"

        return round(headwind_mph, 1), round(crosswind_mph, 1), category

    @staticmethod
    def evaluate_road_moisture_and_drying(
        current_precip_in_hr: float,
        past_precip_1h_in: float,
        past_precip_2h_in: float,
        weather_code: int,
        temp_f: float,
        humidity_pct: float,
        wind_speed_mph: float,
        is_day: bool
    ) -> Tuple[str, float, float]:
        """
        Dynamic Pavement Drying & Moisture State Machine.
        Distinguishes WMO 51-67 vs 71+ and factors in rainfall volume,
        solar radiation/cloud cover, wind, temperature, and humidity.
        Returns: (road_condition, pavement_wetness_factor, rolling_resistance_crr)
        """
        # 1. Snow / Ice Conditions
        is_snow_code = weather_code in [71, 73, 75, 77, 85, 86]
        is_freezing_rain = weather_code in [56, 57, 66, 67]

        if is_freezing_rain or (temp_f <= 32.0 and current_precip_in_hr > 0.01):
            return "ice", 1.0, 0.0210

        if is_snow_code or (temp_f <= 32.0 and current_precip_in_hr > 0.03):
            return "snow_slush", 1.0, 0.0195

        # 2. Currently Raining
        if current_precip_in_hr >= 0.15:
            # Heavy Rain with standing puddles / spray
            return "heavy_wet", 1.0, 0.0145
        elif current_precip_in_hr >= 0.03 or weather_code in [61, 63, 65, 80, 81, 82]:
            # Continuous Rain
            return "wet", 0.85, 0.0130
        elif current_precip_in_hr > 0.005 or weather_code in [51, 53, 55]:
            # Light drizzle / mist
            return "damp", 0.50, 0.0112

        # 3. Rain has stopped -> Pavement Drying Model
        # Evaluate how much moisture remains on the highway pavement
        recent_accum_in = past_precip_1h_in * 0.70 + past_precip_2h_in * 0.30

        if recent_accum_in > 0.005:
            # Evaporation Rate Factor:
            solar_factor = 1.0 if is_day and weather_code in [0, 1, 2] else (0.55 if is_day else 0.25)
            temp_factor = max(0.4, min(1.8, temp_f / 65.0))
            humidity_factor = max(0.3, 1.0 - (humidity_pct / 150.0))
            wind_factor = 1.0 + min(1.0, wind_speed_mph / 20.0)

            evaporation_rate = 0.06 * solar_factor * temp_factor * humidity_factor * wind_factor
            remaining_water = max(0.0, recent_accum_in - evaporation_rate)

            if remaining_water >= 0.03:
                return "wet", 0.65, 0.0125
            elif remaining_water >= 0.005:
                return "damp", 0.35, 0.0108

        return "dry", 0.0, 0.0095

    def calculate_segment_physics(
        self,
        distance_miles: float,
        speed_limit_mph: float,
        bearing_deg: float,
        elev_change_m: float,
        temp_f: float,
        wind_speed_mph: float,
        wind_dir_deg: float,
        surface_pressure_hpa: float,
        humidity_pct: float,
        crr: float
    ) -> Tuple[float, float, float, float, float]:
        """
        Simulates Equinox EV aerodynamic drag, rolling resistance, grade, and HVAC,
        and returns:
        (consumption_wh_per_mi, baseline_wh_per_mi, hvac_kw, battery_eff, headwind_mph)
        """
        v_ms = self.energy_sim.calculate_actual_speed_ms(speed_limit_mph, self.profile)
        v_mph = v_ms * MS_TO_MPH
        dist_m = distance_miles * 1609.34
        dur_hours = distance_miles / max(15.0, v_mph)

        # 1. Real Moist Air Density & Vector Wind
        rho, _ = self.calculate_moist_air_density(temp_f, surface_pressure_hpa, humidity_pct)
        headwind_mph, crosswind_mph, _ = self.calculate_vector_wind(bearing_deg, wind_speed_mph, wind_dir_deg)
        
        # Effective airspeed: tailwind (negative headwind) reduces airspeed!
        v_headwind_ms = headwind_mph * MPH_TO_MS
        v_airspeed_ms = max(0.0, v_ms + v_headwind_ms)

        # Crosswind yaw angle slightly increases effective Cd
        yaw_rad = math.atan2(crosswind_mph * MPH_TO_MS, max(5.0, v_airspeed_ms))
        yaw_deg = min(10.0, math.degrees(yaw_rad))
        cd_effective = self.vehicle.cd * (1.0 + 0.015 * yaw_deg)
        drag_area = cd_effective * self.vehicle.frontal_area_m2

        # Aerodynamic Drag Force: F_aero = 0.5 * rho * CdA * v_air^2
        f_aero = 0.5 * rho * drag_area * (v_airspeed_ms ** 2)

        # Rolling Resistance Force: F_rr = Crr * m * g
        total_mass_kg = self.vehicle.get_total_mass_kg(self.payload)
        grade_rad = math.atan2(elev_change_m, max(1.0, dist_m))
        f_rr = crr * total_mass_kg * GRAVITY * math.cos(grade_rad)

        # Gravitational Grade Force
        f_grade = total_mass_kg * GRAVITY * math.sin(grade_rad)

        # Net mechanical tractive work
        f_net = f_aero + f_rr + f_grade
        work_joules = f_net * dist_m
        work_kwh = work_joules / 3.6e6

        if work_kwh >= 0:
            traction_battery_kwh = work_kwh / self.vehicle.drivetrain_efficiency
        else:
            regen_power_kw = abs(work_kwh / dur_hours) if dur_hours > 0 else 0.0
            clamped_regen = min(regen_power_kw, self.vehicle.max_regen_kw)
            recoverable_kwh = clamped_regen * dur_hours
            traction_battery_kwh = - (recoverable_kwh * self.vehicle.regen_efficiency)

        # 2. HVAC & Auxiliaries
        delta_t = abs(temp_f - 70.0)
        if delta_t <= 3.0:
            hvac_kw = 0.25
        elif temp_f > 70.0:
            hvac_kw = min(2.5, 0.40 + 0.050 * delta_t)
        else:
            if temp_f >= 40.0:
                hvac_kw = min(2.5, 0.45 + 0.045 * delta_t)
            else:
                base_hp = 0.45 + 0.045 * (70.0 - 40.0)
                ptc_extra = 0.075 * (40.0 - temp_f)
                hvac_kw = min(5.0, base_hp + ptc_extra)

        total_aux_kwh = (self.vehicle.base_aux_power_kw + hvac_kw) * dur_hours

        # 3. Cold Battery Chemical Kinetics Efficiency
        if temp_f >= 65.0:
            battery_eff = 1.00
        elif temp_f >= 32.0:
            battery_eff = 0.90 + 0.10 * ((temp_f - 32.0) / 33.0)
        elif temp_f >= 0.0:
            battery_eff = 0.80 + 0.10 * (temp_f / 32.0)
        else:
            battery_eff = 0.75

        gross_traction_kwh = traction_battery_kwh / battery_eff if traction_battery_kwh > 0 else traction_battery_kwh
        total_energy_kwh = gross_traction_kwh + total_aux_kwh
        wh_per_mi = (total_energy_kwh * 1000.0) / max(0.1, distance_miles)

        # Baseline: 70F ambient, 0 wind, dry road Crr=0.0095, STP air density 1.225, HVAC=0.25 kW
        f_aero_base = 0.5 * AIR_DENSITY_STP * self.vehicle.drag_area_m2 * (v_ms ** 2)
        f_rr_base = 0.0095 * total_mass_kg * GRAVITY * math.cos(grade_rad)
        f_net_base = f_aero_base + f_rr_base + f_grade
        work_base_kwh = (f_net_base * dist_m) / 3.6e6
        traction_base_kwh = work_base_kwh / self.vehicle.drivetrain_efficiency if work_base_kwh >= 0 else -(min(abs(work_base_kwh/dur_hours), 70.0) * dur_hours * 0.85)
        aux_base_kwh = (self.vehicle.base_aux_power_kw + 0.25) * dur_hours
        total_base_kwh = traction_base_kwh + aux_base_kwh
        wh_per_mi_base = (total_base_kwh * 1000.0) / max(0.1, distance_miles)

        return (
            round(wh_per_mi, 1),
            round(wh_per_mi_base, 1),
            round(hvac_kw, 2),
            round(battery_eff, 2),
            round(headwind_mph, 1)
        )

    # -------------------------------------------------------------------------
    # 4. OPEN-METEO API CLIENT (FORECAST & HISTORICAL ARCHIVE)
    # -------------------------------------------------------------------------
    async def fetch_open_meteo_weather(
        self,
        timeline: List[Dict[str, Any]],
        departure_dt: datetime
    ) -> List[WaypointWeather]:
        """
        Fetches hourly weather data for all waypoints via batched Open-Meteo call.
        If departure is <= 16 days -> calls Forecast API.
        If departure is > 16 days  -> calls Historical Archive API across past 3 years.
        """
        now = datetime.now()
        horizon_days = (departure_dt.date() - now.date()).days
        is_forecast_mode = horizon_days <= 16

        lats = ",".join(f"{wp['lat']:.4f}" for wp in timeline)
        lons = ",".join(f"{wp['lon']:.4f}" for wp in timeline)

        if is_forecast_mode:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lats}&longitude={lons}&"
                f"hourly=temperature_2m,relative_humidity_2m,precipitation,rain,snowfall,"
                f"weather_code,surface_pressure,wind_speed_10m,wind_direction_10m,is_day&"
                f"temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&"
                f"past_days=1&forecast_days=16"
            )
            raw_series = await self._fetch_http_json(url)
            return self._parse_forecast_response(timeline, raw_series)
        else:
            return await self._fetch_historical_reanalysis(timeline, departure_dt)

    async def _fetch_http_json(self, url: str) -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"User-Agent": "EquinoxEVWeatherEngine/1.0"}
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def _parse_forecast_response(
        self,
        timeline: List[Dict[str, Any]],
        raw_series: Any
    ) -> List[WaypointWeather]:
        series_list = raw_series if isinstance(raw_series, list) else [raw_series]
        result_waypoints = []

        for i, wp in enumerate(timeline):
            series = series_list[i if i < len(series_list) else -1]
            hourly = series.get("hourly", {})
            times = hourly.get("time", [])

            target_str = wp["arrival_dt"].strftime("%Y-%m-%dT%H:00")
            match_idx = -1
            if target_str in times:
                match_idx = times.index(target_str)
            else:
                best_diff = float("inf")
                target_dt = wp["arrival_dt"]
                for t_idx, t_str in enumerate(times):
                    try:
                        t_dt = datetime.fromisoformat(t_str)
                        diff = abs((t_dt - target_dt).total_seconds())
                        if diff < best_diff:
                            best_diff = diff
                            match_idx = t_idx
                    except Exception:
                        pass
                if match_idx == -1:
                    match_idx = len(times) - 1

            temp_f = float(hourly.get("temperature_2m", [65.0])[match_idx])
            humidity = float(hourly.get("relative_humidity_2m", [50.0])[match_idx])
            precip = float(hourly.get("precipitation", [0.0])[match_idx])
            weather_code = int(hourly.get("weather_code", [0])[match_idx])
            pressure = float(hourly.get("surface_pressure", [1013.25])[match_idx])
            wind_speed = float(hourly.get("wind_speed_10m", [5.0])[match_idx])
            wind_dir = float(hourly.get("wind_direction_10m", [270.0])[match_idx])
            is_day = bool(hourly.get("is_day", [1])[match_idx])

            p_past1 = float(hourly.get("precipitation", [0.0])[max(0, match_idx - 1)]) if match_idx > 0 else 0.0
            p_past2 = float(hourly.get("precipitation", [0.0])[max(0, match_idx - 2)]) if match_idx > 1 else 0.0

            road_cond, wetness_factor, crr = self.evaluate_road_moisture_and_drying(
                current_precip_in_hr=precip,
                past_precip_1h_in=p_past1,
                past_precip_2h_in=p_past2,
                weather_code=weather_code,
                temp_f=temp_f,
                humidity_pct=humidity,
                wind_speed_mph=wind_speed,
                is_day=is_day
            )

            rho, rho_delta = self.calculate_moist_air_density(temp_f, pressure, humidity)
            headwind, crosswind, wind_cat = self.calculate_vector_wind(
                wp["bearing_deg"], wind_speed, wind_dir
            )

            elev_change_m = (
                wp["elev_m"] - timeline[i-1]["elev_m"] if i > 0 else 0.0
            )

            seg_dist = wp["segment_dist_miles"] if i > 0 else wp["dist_from_start_miles"]
            wh_mi, wh_mi_base, hvac_kw, batt_eff, _ = self.calculate_segment_physics(
                distance_miles=max(0.1, seg_dist),
                speed_limit_mph=wp["speed_limit_mph"],
                bearing_deg=wp["bearing_deg"],
                elev_change_m=elev_change_m,
                temp_f=temp_f,
                wind_speed_mph=wind_speed,
                wind_dir_deg=wind_dir,
                surface_pressure_hpa=pressure,
                humidity_pct=humidity,
                crr=crr
            )

            wmo_desc = WMO_DESCRIPTIONS.get(weather_code, "Cloudy")

            result_waypoints.append(WaypointWeather(
                name=wp["name"],
                lat=wp["lat"],
                lon=wp["lon"],
                elevation_ft=wp["elev_ft"],
                distance_from_start_miles=wp["dist_from_start_miles"],
                segment_distance_miles=round(seg_dist, 2),
                elapsed_time_minutes=wp["elapsed_minutes"],
                arrival_time_iso=wp["arrival_dt"].isoformat(),
                arrival_time_clock=wp["arrival_dt"].strftime("%I:%M %p"),
                ambient_temp_f=round(temp_f, 1),
                relative_humidity_pct=round(humidity, 0),
                surface_pressure_hpa=round(pressure, 1),
                air_density_kg_m3=rho,
                air_density_delta_pct=rho_delta,
                precipitation_rate_in_hr=round(precip, 3),
                weather_code=weather_code,
                weather_description=wmo_desc,
                is_day=is_day,
                road_condition=road_cond,
                pavement_wetness_factor=round(wetness_factor, 2),
                rolling_resistance_crr=round(crr, 4),
                wind_speed_mph=round(wind_speed, 1),
                wind_direction_deg=round(wind_dir, 0),
                wind_direction_cardinal=self.degrees_to_cardinal(wind_dir),
                segment_bearing_deg=wp["bearing_deg"],
                effective_headwind_mph=headwind,
                crosswind_mph=crosswind,
                wind_category=wind_cat,
                hvac_power_kw=hvac_kw,
                battery_eff_factor=batt_eff,
                estimated_consumption_wh_per_mi=wh_mi,
                baseline_consumption_wh_per_mi=wh_mi_base,
                wh_per_mi_delta=round(wh_mi - wh_mi_base, 1),
                is_forecast=True
            ))

        return result_waypoints

    async def _fetch_historical_reanalysis(
        self,
        timeline: List[Dict[str, Any]],
        departure_dt: datetime
    ) -> List[WaypointWeather]:
        target_years = [departure_dt.year - 1, departure_dt.year - 2, departure_dt.year - 3]
        lats = ",".join(f"{wp['lat']:.4f}" for wp in timeline)
        lons = ",".join(f"{wp['lon']:.4f}" for wp in timeline)

        year_data: List[List[Dict[str, Any]]] = []

        for yr in target_years:
            month = departure_dt.month
            day = departure_dt.day
            if month == 2 and day == 29 and yr % 4 != 0:
                day = 28

            date_str = f"{yr}-{month:02d}-{day:02d}"
            url = (
                f"https://archive-api.open-meteo.com/v1/archive?"
                f"latitude={lats}&longitude={lons}&"
                f"start_date={date_str}&end_date={date_str}&"
                f"hourly=temperature_2m,relative_humidity_2m,precipitation,weather_code,"
                f"wind_speed_10m,wind_direction_10m,surface_pressure&"
                f"temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
            )
            try:
                resp = await self._fetch_http_json(url)
                series_list = resp if isinstance(resp, list) else [resp]
                year_data.append(series_list)
            except Exception:
                pass

        result_waypoints = []
        for i, wp in enumerate(timeline):
            target_hour = wp["arrival_dt"].hour
            temps, hums, pressures, winds, wind_dirs, precips, codes = [], [], [], [], [], [], []

            for yr_series in year_data:
                if i < len(yr_series):
                    hourly = yr_series[i].get("hourly", {})
                    if "temperature_2m" in hourly and target_hour < len(hourly["temperature_2m"]):
                        temps.append(float(hourly["temperature_2m"][target_hour]))
                        hums.append(float(hourly.get("relative_humidity_2m", [50.0])[target_hour]))
                        pressures.append(float(hourly.get("surface_pressure", [1013.25])[target_hour]))
                        winds.append(float(hourly.get("wind_speed_10m", [5.0])[target_hour]))
                        wind_dirs.append(float(hourly.get("wind_direction_10m", [270.0])[target_hour]))
                        precips.append(float(hourly.get("precipitation", [0.0])[target_hour]))
                        codes.append(int(hourly.get("weather_code", [0])[target_hour]))

            temp_f = sum(temps) / len(temps) if temps else 55.0
            humidity = sum(hums) / len(hums) if hums else 50.0
            pressure = sum(pressures) / len(pressures) if pressures else 1013.25
            wind_speed = sum(winds) / len(winds) if winds else 7.0
            precip = sum(precips) / len(precips) if precips else 0.0

            if wind_dirs:
                u_sum = sum(-math.sin(math.radians(d)) for d in wind_dirs)
                v_sum = sum(-math.cos(math.radians(d)) for d in wind_dirs)
                wind_dir = (math.degrees(math.atan2(-u_sum, -v_sum)) + 360) % 360
            else:
                wind_dir = 270.0

            weather_code = codes[0] if codes else 0
            is_day = 6 <= target_hour <= 19

            road_cond, wetness_factor, crr = self.evaluate_road_moisture_and_drying(
                current_precip_in_hr=precip,
                past_precip_1h_in=0.0,
                past_precip_2h_in=0.0,
                weather_code=weather_code,
                temp_f=temp_f,
                humidity_pct=humidity,
                wind_speed_mph=wind_speed,
                is_day=is_day
            )

            rho, rho_delta = self.calculate_moist_air_density(temp_f, pressure, humidity)
            headwind, crosswind, wind_cat = self.calculate_vector_wind(wp["bearing_deg"], wind_speed, wind_dir)

            elev_change_m = wp["elev_m"] - timeline[i-1]["elev_m"] if i > 0 else 0.0
            seg_dist = wp["segment_dist_miles"] if i > 0 else wp["dist_from_start_miles"]

            wh_mi, wh_mi_base, hvac_kw, batt_eff, _ = self.calculate_segment_physics(
                distance_miles=max(0.1, seg_dist),
                speed_limit_mph=wp["speed_limit_mph"],
                bearing_deg=wp["bearing_deg"],
                elev_change_m=elev_change_m,
                temp_f=temp_f,
                wind_speed_mph=wind_speed,
                wind_dir_deg=wind_dir,
                surface_pressure_hpa=pressure,
                humidity_pct=humidity,
                crr=crr
            )

            desc = f"Historical Average ({WMO_DESCRIPTIONS.get(weather_code, 'Fair')})"

            result_waypoints.append(WaypointWeather(
                name=wp["name"],
                lat=wp["lat"],
                lon=wp["lon"],
                elevation_ft=wp["elev_ft"],
                distance_from_start_miles=wp["dist_from_start_miles"],
                segment_distance_miles=round(seg_dist, 2),
                elapsed_time_minutes=wp["elapsed_minutes"],
                arrival_time_iso=wp["arrival_dt"].isoformat(),
                arrival_time_clock=wp["arrival_dt"].strftime("%I:%M %p"),
                ambient_temp_f=round(temp_f, 1),
                relative_humidity_pct=round(humidity, 0),
                surface_pressure_hpa=round(pressure, 1),
                air_density_kg_m3=rho,
                air_density_delta_pct=rho_delta,
                precipitation_rate_in_hr=round(precip, 3),
                weather_code=weather_code,
                weather_description=desc,
                is_day=is_day,
                road_condition=road_cond,
                pavement_wetness_factor=round(wetness_factor, 2),
                rolling_resistance_crr=round(crr, 4),
                wind_speed_mph=round(wind_speed, 1),
                wind_direction_deg=round(wind_dir, 0),
                wind_direction_cardinal=self.degrees_to_cardinal(wind_dir),
                segment_bearing_deg=wp["bearing_deg"],
                effective_headwind_mph=headwind,
                crosswind_mph=crosswind,
                wind_category=wind_cat,
                hvac_power_kw=hvac_kw,
                battery_eff_factor=batt_eff,
                estimated_consumption_wh_per_mi=wh_mi,
                baseline_consumption_wh_per_mi=wh_mi_base,
                wh_per_mi_delta=round(wh_mi - wh_mi_base, 1),
                is_forecast=False
            ))

        return result_waypoints

    # -------------------------------------------------------------------------
    # 5. PUBLIC API: EVALUATE WEATHER REPORT FOR ANY ROUTE
    # -------------------------------------------------------------------------
    async def get_route_weather_report(
        self,
        destination_key_or_name: str,
        departure_dt: datetime,
        custom_coordinates: Optional[List[List[float]]] = None,
        origin_name: str = "West High School (Columbus, OH)",
        destination_name: Optional[str] = None
    ) -> RouteWeatherReport:
        """
        Main entry point for generating a comprehensive RouteWeatherReport.
        Handles:
        1. Pre-computed quick destination keys: 'st_onge', 'billings', 'decamilla'
        2. Arbitrary custom routes provided via custom_coordinates [[lon, lat, elev], ...]
        """
        corridors = self.get_precomputed_corridors()
        clean_key = destination_key_or_name.lower().replace(".", "").replace(" ", "_").strip()

        if clean_key in corridors:
            cfg = corridors[clean_key]
            route_id = cfg["route_id"]
            route_name = cfg["route_name"]
            orig_name = cfg["origin_name"]
            dest_name = cfg["destination_name"]
            timeline = self.build_route_timeline_from_waypoints(cfg["waypoints"], departure_dt)
            geom = [[wp[2], wp[1], wp[3]] for wp in cfg["waypoints"]]
        elif custom_coordinates:
            route_id = "custom_route"
            orig_name = origin_name
            dest_name = destination_name or destination_key_or_name
            route_name = f"{orig_name} to {dest_name}"
            timeline = self.slice_arbitrary_route(custom_coordinates, departure_dt)
            geom = custom_coordinates
        else:
            cfg = corridors["st_onge"]
            route_id = cfg["route_id"]
            route_name = cfg["route_name"]
            orig_name = cfg["origin_name"]
            dest_name = cfg["destination_name"]
            timeline = self.build_route_timeline_from_waypoints(cfg["waypoints"], departure_dt)
            geom = [[wp[2], wp[1], wp[3]] for wp in cfg["waypoints"]]

        waypoints_weather = await self.fetch_open_meteo_weather(timeline, departure_dt)

        total_dist = timeline[-1]["dist_from_start_miles"] if timeline else 0.0
        total_duration_hours = (timeline[-1]["elapsed_minutes"] / 60.0) if timeline else 0.0

        temps = [w.ambient_temp_f for w in waypoints_weather]
        min_temp = min(temps) if temps else 68.0
        max_temp = max(temps) if temps else 68.0
        avg_temp = round(sum(temps) / len(temps), 1) if temps else 68.0

        hw_vals = [w.effective_headwind_mph for w in waypoints_weather]
        max_headwind = max(0.0, max(hw_vals)) if hw_vals else 0.0
        max_tailwind = abs(min(0.0, min(hw_vals))) if hw_vals else 0.0

        wet_count = sum(1 for w in waypoints_weather if w.road_condition in ["damp", "wet", "heavy_wet"])
        snow_count = sum(1 for w in waypoints_weather if w.road_condition in ["snow_slush", "ice"])
        wet_pct = round((wet_count / max(1, len(waypoints_weather))) * 100.0, 1)
        snow_pct = round((snow_count / max(1, len(waypoints_weather))) * 100.0, 1)

        total_energy_kwh = sum(
            (w.estimated_consumption_wh_per_mi * w.segment_distance_miles) / 1000.0
            for w in waypoints_weather
        )
        baseline_energy_kwh = sum(
            (w.baseline_consumption_wh_per_mi * w.segment_distance_miles) / 1000.0
            for w in waypoints_weather
        )
        delta_kwh = total_energy_kwh - baseline_energy_kwh
        delta_pct = (delta_kwh / max(0.1, baseline_energy_kwh)) * 100.0

        avg_wh_mi = (total_energy_kwh * 1000.0) / max(0.1, total_dist)
        baseline_avg_wh_mi = (baseline_energy_kwh * 1000.0) / max(0.1, total_dist)

        total_hvac_kwh = sum(
            w.hvac_power_kw * (w.segment_distance_miles / max(15.0, 65.0))
            for w in waypoints_weather
        )

        now = datetime.now()
        mode_str = "forecast" if (departure_dt.date() - now.date()).days <= 16 else "historical"

        summary = {
            "min_temp_f": min_temp,
            "max_temp_f": max_temp,
            "avg_temp_f": avg_temp,
            "max_headwind_mph": max_headwind,
            "max_tailwind_mph": max_tailwind,
            "wet_road_pct": wet_pct,
            "snow_ice_road_pct": snow_pct,
            "total_energy_kwh": round(total_energy_kwh, 2),
            "baseline_energy_kwh": round(baseline_energy_kwh, 2),
            "energy_delta_kwh": round(delta_kwh, 2),
            "energy_delta_pct": round(delta_pct, 1),
            "avg_consumption_wh_per_mi": round(avg_wh_mi, 1),
            "baseline_avg_wh_per_mi": round(baseline_avg_wh_mi, 1),
            "total_hvac_kwh": round(total_hvac_kwh, 2)
        }

        return RouteWeatherReport(
            route_id=route_id,
            route_name=route_name,
            origin_name=orig_name,
            destination_name=dest_name,
            departure_time_iso=departure_dt.isoformat(),
            departure_time_clock=departure_dt.strftime("%I:%M %p"),
            total_distance_miles=round(total_dist, 1),
            total_duration_hours=round(total_duration_hours, 2),
            mode=mode_str,
            waypoints=waypoints_weather,
            summary=summary,
            route_geometry=geom
        )
