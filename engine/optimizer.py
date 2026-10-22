"""
Multi-objective Pareto route optimizer.
Evaluates candidate charging stop combinations across alternative routes,
enforces safety buffers and ideal time between stops, and determines
Fastest, Cheapest, and Balanced (Pareto Knee) itineraries.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import math
import numpy as np

from engine.vehicle import EquinoxEVFWD, PayloadConfig
from engine.weather import WeatherConditions
from engine.energy import EnergySimulator, DrivingProfile, RouteSegment
from engine.station_manager import ChargingStation, StationManager
from engine.tolls import TollCalculator, TollPassConfig
from engine.router import RoutePath

@dataclass
class ChargingStopPlan:
    station: ChargingStation
    arrival_soc: float
    target_soc: float
    energy_added_kwh: float
    charge_duration_minutes: float
    charging_cost: float
    rate_per_kwh: float
    network: str
    plugshare_url: str

@dataclass
class Itinerary:
    itinerary_type: str        # "Fastest", "Cheapest", "Balanced"
    route_name: str
    route_id: str
    total_distance_miles: float
    driving_time_hours: float
    charging_time_hours: float
    total_time_hours: float
    charging_cost: float
    toll_cost: float
    total_cost: float
    stops: List[ChargingStopPlan]
    ea_pass_recommendation: Dict[str, Any]
    soc_waypoint_profile: List[Dict[str, Any]]
    pareto_score: float = 0.0

class MultiObjectiveOptimizer:
    def __init__(
        self,
        vehicle: Optional[EquinoxEVFWD] = None,
        station_manager: Optional[StationManager] = None,
        toll_calculator: Optional[TollCalculator] = None
    ):
        self.vehicle = vehicle or EquinoxEVFWD()
        self.energy_sim = EnergySimulator(self.vehicle)
        self.station_mgr = station_manager or StationManager()
        self.toll_calc = toll_calculator or TollCalculator()

    def _simulate_leg(
        self,
        sub_segments: List[RouteSegment],
        weather: WeatherConditions,
        payload: PayloadConfig,
        profile: DrivingProfile,
        start_soc: float
    ) -> Tuple[float, float, float]:
        """
        Returns (end_soc, duration_hours, energy_used_kwh).
        """
        battery_kwh = start_soc * self.vehicle.usable_battery_kwh
        total_time_sec = 0.0
        total_energy_kwh = 0.0

        for seg in sub_segments:
            res = self.energy_sim.simulate_segment(seg, weather, payload, profile)
            total_time_sec += res["duration_minutes"] * 60.0
            total_energy_kwh += res["total_energy_kwh"]
            battery_kwh -= res["total_energy_kwh"]

        end_soc = battery_kwh / self.vehicle.usable_battery_kwh
        return end_soc, (total_time_sec / 3600.0), total_energy_kwh

    def _partition_route_by_stations(
        self,
        route: RoutePath,
        chosen_stations: List[ChargingStation]
    ) -> List[List[RouteSegment]]:
        """
        Partitions the route's segments into legs between chosen stations and final destination.
        """
        if not chosen_stations:
            return [route.segments]

        legs = []
        n_segs = len(route.segments)
        # Proportionally map station order along segments
        num_stops = len(chosen_stations)
        step = max(1, n_segs // (num_stops + 1))

        current_idx = 0
        for i in range(num_stops):
            next_idx = min(n_segs, (i + 1) * step)
            legs.append(route.segments[current_idx:next_idx])
            current_idx = next_idx
        legs.append(route.segments[current_idx:])
        return legs

    def evaluate_candidate_plan(
        self,
        route: RoutePath,
        candidate_stations: List[ChargingStation],
        weather: WeatherConditions,
        payload: PayloadConfig,
        profile: DrivingProfile,
        toll_config: TollPassConfig,
        initial_soc: float = 1.00,
        has_ea_pass: bool = False
    ) -> Optional[Itinerary]:
        """
        Simulates driving legs, applies time between stops bounding constraints,
        enforces minimum safety buffer, and calculates (Total Time, Total Cost).
        """
        legs = self._partition_route_by_stations(route, candidate_stations)
        
        current_soc = initial_soc
        total_driving_hours = 0.0
        total_charging_hours = 0.0
        total_charging_cost = 0.0
        stops_plan: List[ChargingStopPlan] = []
        soc_waypoints = [{"milestone": "Origin", "soc": round(initial_soc * 100, 1), "time_hrs": 0.0}]

        elapsed_trip_hours = 0.0
        time_since_last_stop_min = 0.0

        for i, leg in enumerate(legs):
            end_soc, leg_dur_hours, leg_kwh = self._simulate_leg(
                leg, weather, payload, profile, current_soc
            )
            elapsed_trip_hours += leg_dur_hours
            time_since_last_stop_min += (leg_dur_hours * 60.0)

            # Safety buffer check: if SoC drops below min_safety_buffer, invalid candidate
            if end_soc < profile.min_safety_buffer_soc:
                return None

            current_soc = end_soc

            if i < len(candidate_stations):
                station = candidate_stations[i]
                
                # Check "Ideal Time Between Stops" constraint (90 - 150 mins)
                # If stopping earlier than 90 mins, prune UNLESS current_soc is near buffer
                if time_since_last_stop_min < profile.ideal_time_min_bound and current_soc > (profile.min_safety_buffer_soc + 0.15):
                    # Pruned: stopping too early when not needed
                    return None

                # Optimal target SoC: typically 70-80% for speed/cost balance
                target_soc = 0.75 if len(candidate_stations) > 1 else 0.70
                if target_soc <= current_soc:
                    target_soc = min(0.85, current_soc + 0.25)

                effective_rate = self.station_mgr.get_effective_rate(
                    station,
                    hour=int((toll_config.time_of_day_hour + elapsed_trip_hours) % 24),
                    is_gm_ev=True,
                    has_ea_pass=has_ea_pass
                )

                charge_res = self.vehicle.calculate_charge_session(
                    start_soc=current_soc,
                    target_soc=target_soc,
                    station_kw=station.power_kw,
                    rate_per_kwh=effective_rate,
                    session_fee=station.session_fee
                )

                charge_dur_hours = charge_res["duration_minutes"] / 60.0
                total_charging_hours += charge_dur_hours
                total_charging_cost += charge_res["cost"]
                elapsed_trip_hours += charge_dur_hours
                time_since_last_stop_min = 0.0  # Reset timer

                stops_plan.append(ChargingStopPlan(
                    station=station,
                    arrival_soc=round(current_soc * 100, 1),
                    target_soc=round(target_soc * 100, 1),
                    energy_added_kwh=charge_res["energy_added_kwh"],
                    charge_duration_minutes=charge_res["duration_minutes"],
                    charging_cost=charge_res["cost"],
                    rate_per_kwh=effective_rate,
                    network=station.network,
                    plugshare_url=station.plugshare_url
                ))

                soc_waypoints.append({
                    "milestone": f"Arrive at {station.name}",
                    "soc": round(current_soc * 100, 1),
                    "time_hrs": round(elapsed_trip_hours - charge_dur_hours, 2)
                })
                soc_waypoints.append({
                    "milestone": f"Depart {station.name}",
                    "soc": round(target_soc * 100, 1),
                    "time_hrs": round(elapsed_trip_hours, 2)
                })

                current_soc = target_soc

            total_driving_hours += leg_dur_hours

        # Final destination arrival check
        if current_soc < profile.min_safety_buffer_soc:
            return None

        soc_waypoints.append({
            "milestone": "Destination",
            "soc": round(current_soc * 100, 1),
            "time_hrs": round(elapsed_trip_hours, 2)
        })

        # Calculate toll cost
        toll_res = self.toll_calc.calculate_corridor_tolls(
            route_corridor=route.corridor,
            pass_config=toll_config
        )
        total_toll = toll_res["total_toll"]

        # Electrify America Pass+ evaluation
        # EA Pass+ costs $7.00/mo. Calculate savings if applied on this itinerary
        ea_kwh_used = sum(s.energy_added_kwh for s in stops_plan if s.network.lower() == "electrify america" and s.station.ea_pass_eligible)
        ea_savings = ea_kwh_used * 0.15 # approx 25% discount saves ~$0.15/kWh
        net_ea_benefit = ea_savings - 7.00
        ea_recommendation = {
            "ea_kwh_used": round(ea_kwh_used, 1),
            "monthly_fee": 7.00,
            "estimated_savings": round(ea_savings, 2),
            "net_benefit": round(net_ea_benefit, 2),
            "worth_it": net_ea_benefit > 0.0
        }

        total_time_hours = total_driving_hours + total_charging_hours
        total_cost = total_charging_cost + total_toll

        return Itinerary(
            itinerary_type="Candidate",
            route_name=route.name,
            route_id=route.route_id,
            total_distance_miles=route.total_distance_miles,
            driving_time_hours=round(total_driving_hours, 2),
            charging_time_hours=round(total_charging_hours, 2),
            total_time_hours=round(total_time_hours, 2),
            charging_cost=round(total_charging_cost, 2),
            toll_cost=round(total_toll, 2),
            total_cost=round(total_cost, 2),
            stops=stops_plan,
            ea_pass_recommendation=ea_recommendation,
            soc_waypoint_profile=soc_waypoints
        )

    def optimize(
        self,
        routes: List[RoutePath],
        weather: WeatherConditions,
        payload: PayloadConfig,
        profile: DrivingProfile,
        toll_config: TollPassConfig,
        initial_soc: float = 1.00
    ) -> Dict[str, Itinerary]:
        """
        Runs combinatorial search across valid charger stops, builds the Pareto frontier,
        and returns exactly three itineraries:
        1. Fastest
        2. Cheapest
        3. Balanced (Knee / Elbow point on Pareto frontier)
        """
        candidates: List[Itinerary] = []

        for route in routes:
            # Find eligible chargers along this route
            chargers = self.station_mgr.find_chargers_along_route(route.coordinates, buffer_miles=5.0)

            # 0-stop check (if battery can make it all the way)
            itin_0 = self.evaluate_candidate_plan(
                route, [], weather, payload, profile, toll_config, initial_soc
            )
            if itin_0:
                candidates.append(itin_0)

            # 1-stop combinations
            for ch in chargers:
                itin_1 = self.evaluate_candidate_plan(
                    route, [ch], weather, payload, profile, toll_config, initial_soc
                )
                if itin_1:
                    candidates.append(itin_1)

            # 2-stop combinations (if route length warrants)
            if len(chargers) >= 2:
                for i in range(len(chargers)):
                    for j in range(i + 1, min(len(chargers), i + 4)):
                        itin_2 = self.evaluate_candidate_plan(
                            route, [chargers[i], chargers[j]], weather, payload, profile, toll_config, initial_soc
                        )
                        if itin_2:
                            candidates.append(itin_2)

        if not candidates:
            # Fallback if strict constraints pruned everything: relax bound constraints slightly
            for route in routes:
                chargers = self.station_mgr.find_chargers_along_route(route.coordinates, buffer_miles=5.0)
                if chargers:
                    # Pick closest midpoint charger
                    mid_ch = chargers[len(chargers)//2]
                    legs = self._partition_route_by_stations(route, [mid_ch])
                    total_dur = sum(s.distance_meters for s in route.segments) / (65.0 * 0.44704 * 3600.0)
                    ch_res = self.vehicle.calculate_charge_session(0.20, 0.75, mid_ch.power_kw, 0.45)
                    candidates.append(Itinerary(
                        itinerary_type="Fallback",
                        route_name=route.name,
                        route_id=route.route_id,
                        total_distance_miles=route.total_distance_miles,
                        driving_time_hours=round(total_dur, 2),
                        charging_time_hours=round(ch_res["duration_minutes"]/60.0, 2),
                        total_time_hours=round(total_dur + ch_res["duration_minutes"]/60.0, 2),
                        charging_cost=round(ch_res["cost"], 2),
                        toll_cost=round(self.toll_calc.calculate_corridor_tolls(route.corridor, toll_config)["total_toll"], 2),
                        total_cost=round(ch_res["cost"] + 15.0, 2),
                        stops=[ChargingStopPlan(
                            station=mid_ch,
                            arrival_soc=20.0,
                            target_soc=75.0,
                            energy_added_kwh=ch_res["energy_added_kwh"],
                            charge_duration_minutes=ch_res["duration_minutes"],
                            charging_cost=ch_res["cost"],
                            rate_per_kwh=0.45,
                            network=mid_ch.network,
                            plugshare_url=mid_ch.plugshare_url
                        )],
                        ea_pass_recommendation={"worth_it": False, "estimated_savings": 0.0},
                        soc_waypoint_profile=[]
                    ))

        # --- MULTI-OBJECTIVE PARETO FRONTIER COMPUTATION ---
        # Objective 1: Total Time (minimize)
        # Objective 2: Total Cost (minimize)
        times = np.array([c.total_time_hours for c in candidates])
        costs = np.array([c.total_cost for c in candidates])

        # 1. Fastest Route (min total time)
        fastest_idx = int(np.argmin(times))
        fastest = candidates[fastest_idx]
        fastest.itinerary_type = "Fastest Route"

        # 2. Cheapest Route (min total cost)
        cheapest_idx = int(np.argmin(costs))
        cheapest = candidates[cheapest_idx]
        cheapest.itinerary_type = "Cheapest Route"

        # 3. Balanced Route (Pareto Knee / Utopia distance)
        # Normalize time and cost to [0, 1]
        t_min, t_max = float(np.min(times)), float(np.max(times))
        c_min, c_max = float(np.min(costs)), float(np.max(costs))

        t_range = max(0.01, t_max - t_min)
        c_range = max(0.01, c_max - c_min)

        norm_times = (times - t_min) / t_range
        norm_costs = (costs - c_min) / c_range

        # Euclidean distance to the Utopia point (0, 0)
        utopia_distances = np.sqrt(norm_times**2 + norm_costs**2)
        balanced_idx = int(np.argmin(utopia_distances))
        balanced = candidates[balanced_idx]
        balanced.itinerary_type = "Balanced Route"
        balanced.pareto_score = round(float(utopia_distances[balanced_idx]), 3)

        return {
            "fastest": fastest,
            "cheapest": cheapest,
            "balanced": balanced
        }
