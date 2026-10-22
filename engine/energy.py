"""
Physical energy simulation engine implementing NREL FASTSim equations,
aerodynamic drag, rolling resistance, elevation gain/loss, wind vector effects,
cabin HVAC heating/cooling draw, and regenerative braking recovery.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import math
import numpy as np

from engine.vehicle import EquinoxEVFWD, PayloadConfig
from engine.weather import WeatherConditions

MPH_TO_MS = 0.44704
MS_TO_MPH = 2.23694
AIR_DENSITY_STP = 1.225  # kg/m^3
GRAVITY = 9.80665        # m/s^2

@dataclass
class DrivingProfile:
    speed_offset_mph: float = 5.0     # e.g., +5 mph over posted limit
    max_speed_cap_mph: float = 75.0   # Hard ceiling speed cap
    min_safety_buffer_soc: float = 0.10 # e.g., 10% min battery remaining
    ideal_time_between_stops_min: float = 120.0 # 2 hours default
    ideal_time_min_bound: float = 90.0
    ideal_time_max_bound: float = 150.0

@dataclass
class RouteSegment:
    distance_meters: float
    start_elevation_m: float
    end_elevation_m: float
    speed_limit_mph: float
    bearing_deg: float           # 0-360 compass direction
    road_class: str = "motorway" # motorway, trunk, primary, secondary, city

class EnergySimulator:
    def __init__(self, vehicle: Optional[EquinoxEVFWD] = None):
        self.vehicle = vehicle or EquinoxEVFWD()

    def calculate_actual_speed_ms(self, speed_limit_mph: float, profile: DrivingProfile) -> float:
        """
        Determines cruising speed based on speed limit, user delta offset, and hard max cap.
        """
        target_mph = speed_limit_mph + profile.speed_offset_mph
        actual_mph = min(target_mph, profile.max_speed_cap_mph)
        actual_mph = max(15.0, actual_mph)  # minimum sane highway/urban speed
        return actual_mph * MPH_TO_MS

    def get_rolling_resistance_coef(self, road_condition: str) -> float:
        if road_condition == "wet":
            return self.vehicle.crr_wet
        elif road_condition == "snow_ice":
            return self.vehicle.crr_snow_ice
        return self.vehicle.crr_dry

    def simulate_segment(
        self,
        segment: RouteSegment,
        weather: WeatherConditions,
        payload: PayloadConfig,
        profile: DrivingProfile
    ) -> Dict[str, Any]:
        """
        Simulates energy consumption (kWh) and duration (seconds) over a single route segment.
        """
        total_mass_kg = self.vehicle.get_total_mass_kg(payload)
        v_ground_ms = self.calculate_actual_speed_ms(segment.speed_limit_mph, profile)
        
        # Duration over segment
        duration_sec = segment.distance_meters / v_ground_ms
        duration_hours = duration_sec / 3600.0

        # Grade
        delta_elev_m = segment.end_elevation_m - segment.start_elevation_m
        grade_fraction = (delta_elev_m / segment.distance_meters) if segment.distance_meters > 0 else 0.0

        # Wind & Aerodynamics
        # Weather headwind component (m/s)
        headwind_mph = weather.get_effective_headwind_mph(segment.bearing_deg)
        v_headwind_ms = headwind_mph * MPH_TO_MS
        v_airspeed_ms = max(0.0, v_ground_ms + v_headwind_ms)

        # Temperature adjusted air density: rho = rho_0 * (273.15 / (T_c + 273.15))
        temp_c = (weather.temperature_f - 32.0) * 5.0 / 9.0
        air_density = AIR_DENSITY_STP * (288.15 / max(240.0, temp_c + 273.15))

        # Aero drag force: F_drag = 0.5 * rho * Cd * A * v_air^2
        f_aero = 0.5 * air_density * self.vehicle.drag_area_m2 * (v_airspeed_ms ** 2)

        # Rolling resistance: F_rr = Crr * m * g * cos(theta)
        crr = self.get_rolling_resistance_coef(weather.road_condition)
        f_rr = crr * total_mass_kg * GRAVITY * math.cos(math.atan(grade_fraction))

        # Gravitational grade force: F_grade = m * g * sin(theta)
        f_grade = total_mass_kg * GRAVITY * math.sin(math.atan(grade_fraction))

        # Net tractive mechanical force required at wheels
        f_wheel_net = f_aero + f_rr + f_grade

        # Mechanical work required (Joules = Force * distance)
        work_wheel_joules = f_wheel_net * segment.distance_meters
        work_wheel_kwh = work_wheel_joules / 3.6e6

        # Traction vs Regenerative Braking
        if work_wheel_kwh >= 0:
            # Consuming battery energy through motor inverter
            traction_battery_kwh = work_wheel_kwh / self.vehicle.drivetrain_efficiency
        else:
            # Descending hill / coasting -> Regen recovery
            # Max regen power constraint
            regen_power_kw = abs(work_wheel_kwh / duration_hours) if duration_hours > 0 else 0.0
            clamped_regen_kw = min(regen_power_kw, self.vehicle.max_regen_kw)
            recoverable_kwh = clamped_regen_kw * duration_hours
            traction_battery_kwh = - (recoverable_kwh * self.vehicle.regen_efficiency)

        # Auxiliary & HVAC energy
        base_aux_kw = self.vehicle.base_aux_power_kw
        hvac_kw = weather.get_hvac_power_kw()
        total_aux_kwh = (base_aux_kw + hvac_kw) * duration_hours

        # Cold temperature battery internal efficiency penalty
        battery_eff_factor = weather.get_battery_temp_efficiency_factor()
        gross_traction_kwh = traction_battery_kwh / battery_eff_factor if traction_battery_kwh > 0 else traction_battery_kwh

        total_energy_kwh = gross_traction_kwh + total_aux_kwh

        return {
            "distance_miles": round(segment.distance_meters * 0.000621371, 2),
            "duration_minutes": round(duration_sec / 60.0, 1),
            "average_speed_mph": round(v_ground_ms * MS_TO_MPH, 1),
            "elevation_change_feet": round(delta_elev_m * 3.28084, 1),
            "aero_kwh": round((f_aero * segment.distance_meters / 3.6e6), 3),
            "rolling_kwh": round((f_rr * segment.distance_meters / 3.6e6), 3),
            "grade_kwh": round((f_grade * segment.distance_meters / 3.6e6), 3),
            "aux_and_hvac_kwh": round(total_aux_kwh, 3),
            "total_energy_kwh": round(total_energy_kwh, 3)
        }

    def simulate_full_route(
        self,
        segments: List[RouteSegment],
        weather: WeatherConditions,
        payload: PayloadConfig,
        profile: DrivingProfile,
        initial_soc: float = 1.00
    ) -> Dict[str, Any]:
        """
        Simulates an entire sequence of segments without charging stops,
        tracking SoC along every waypoint.
        """
        current_battery_kwh = initial_soc * self.vehicle.usable_battery_kwh
        total_dist_miles = 0.0
        total_time_min = 0.0
        total_energy_used_kwh = 0.0

        soc_profile = [initial_soc]
        segment_results = []

        for seg in segments:
            res = self.simulate_segment(seg, weather, payload, profile)
            segment_results.append(res)
            
            total_dist_miles += res["distance_miles"]
            total_time_min += res["duration_minutes"]
            total_energy_used_kwh += res["total_energy_kwh"]

            current_battery_kwh -= res["total_energy_kwh"]
            current_soc = current_battery_kwh / self.vehicle.usable_battery_kwh
            soc_profile.append(round(current_soc, 4))

        return {
            "total_distance_miles": round(total_dist_miles, 1),
            "total_driving_time_hours": round(total_time_min / 60.0, 2),
            "total_energy_kwh": round(total_energy_used_kwh, 2),
            "average_consumption_mi_per_kwh": round(total_dist_miles / max(0.1, total_energy_used_kwh), 2),
            "average_consumption_wh_per_mi": round((total_energy_used_kwh * 1000.0) / max(0.1, total_dist_miles), 1),
            "final_soc": round(current_battery_kwh / self.vehicle.usable_battery_kwh, 4),
            "soc_profile": soc_profile,
            "segments": segment_results
        }
