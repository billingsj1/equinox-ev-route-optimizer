"""
Vehicle model and payload configuration for the 2025 Chevrolet Equinox EV FWD.
"""
from dataclasses import dataclass
from typing import Dict, Any, Tuple

LBS_TO_KG = 0.45359237

@dataclass
class PayloadConfig:
    josh: bool = True          # 150 lbs
    courtney: bool = True      # 130 lbs
    asher: bool = True         # 20 lbs
    arno: bool = True          # 50 lbs (Dog)
    gear_lbs: float = 50.0     # 0 to 100 lbs slider

    def total_payload_kg(self) -> float:
        total_lbs = 0.0
        if self.josh:
            total_lbs += 150.0
        if self.courtney:
            total_lbs += 130.0
        if self.asher:
            total_lbs += 20.0
        if self.arno:
            total_lbs += 50.0
        total_lbs += max(0.0, min(100.0, self.gear_lbs))
        return total_lbs * LBS_TO_KG

    def total_payload_lbs(self) -> float:
        total_lbs = 0.0
        if self.josh:
            total_lbs += 150.0
        if self.courtney:
            total_lbs += 130.0
        if self.asher:
            total_lbs += 20.0
        if self.arno:
            total_lbs += 50.0
        total_lbs += max(0.0, min(100.0, self.gear_lbs))
        return total_lbs


@dataclass
class EquinoxEVFWD:
    # Physical Specs
    usable_battery_kwh: float = 85.0
    curb_weight_kg: float = 2233.0
    cd: float = 0.332
    frontal_area_m2: float = 2.60
    drag_area_m2: float = 0.332 * 2.60  # 0.8632 m^2
    
    # Drivetrain & Electrical Specs
    nominal_voltage: float = 288.0      # Ultium low-voltage 288V pack
    drivetrain_efficiency: float = 0.91 # Traction efficiency
    regen_efficiency: float = 0.85      # Regen round-trip efficiency
    max_regen_kw: float = 70.0          # Max regenerative braking power
    base_aux_power_kw: float = 0.350    # Base computers, screens, lights
    max_dcfc_kw: float = 150.0          # Hard platform peak DCFC rate
    
    # Rolling resistance baseline
    crr_dry: float = 0.0095
    crr_wet: float = 0.0125
    crr_snow_ice: float = 0.0185

    def get_total_mass_kg(self, payload: PayloadConfig) -> float:
        return self.curb_weight_kg + payload.total_payload_kg()

    def get_max_charge_power_kw(self, soc: float, station_kw: float = 150.0) -> float:
        """
        Calculates the maximum charging power (kW) at a given State of Charge (0.0 to 1.0).
        Empirical curve based on 2025 Equinox EV FWD (85 kWh usable, 288V pack):
        - 0% to 32%: 150 kW peak
        - 32% to 58%: linear drop 150 -> 100 kW
        - 58% to 70%: linear drop 100 -> 75 kW
        - 70% to 80%: linear drop 75 -> 52 kW
        - 80% to 90%: linear drop 52 -> 32 kW
        - 90% to 100%: linear drop 32 -> 12 kW
        Clamped by the station's max power rating.
        """
        soc = max(0.0, min(1.0, soc))

        if soc <= 0.32:
            car_power = 150.0
        elif soc <= 0.58:
            # 0.32 -> 150, 0.58 -> 100
            t = (soc - 0.32) / (0.58 - 0.32)
            car_power = 150.0 - t * (150.0 - 100.0)
        elif soc <= 0.70:
            # 0.58 -> 100, 0.70 -> 75
            t = (soc - 0.58) / (0.70 - 0.58)
            car_power = 100.0 - t * (100.0 - 75.0)
        elif soc <= 0.80:
            # 0.70 -> 75, 0.80 -> 52
            t = (soc - 0.70) / (0.80 - 0.70)
            car_power = 75.0 - t * (75.0 - 52.0)
        elif soc <= 0.90:
            # 0.80 -> 52, 0.90 -> 32
            t = (soc - 0.80) / (0.90 - 0.80)
            car_power = 52.0 - t * (52.0 - 32.0)
        else:
            # 0.90 -> 32, 1.00 -> 12
            t = (soc - 0.90) / (1.00 - 0.90)
            car_power = 32.0 - t * (32.0 - 12.0)

        return min(car_power, float(station_kw))

    def calculate_charge_session(
        self,
        start_soc: float,
        target_soc: float,
        station_kw: float,
        rate_per_kwh: float,
        session_fee: float = 0.0,
        preconditioned: bool = True
    ) -> Dict[str, Any]:
        """
        Integrates along the charging curve to determine exact minutes and cost.
        """
        if target_soc <= start_soc:
            return {
                "energy_added_kwh": 0.0,
                "duration_minutes": 0.0,
                "cost": 0.0,
                "average_kw": 0.0
            }

        start_soc = max(0.01, min(0.99, start_soc))
        target_soc = max(start_soc, min(1.0, target_soc))

        energy_needed_kwh = (target_soc - start_soc) * self.usable_battery_kwh

        # Numerical integration across 100 slices
        steps = 100
        delta_soc = (target_soc - start_soc) / steps
        total_hours = 0.0

        for i in range(steps):
            current_soc = start_soc + (i + 0.5) * delta_soc
            power_kw = self.get_max_charge_power_kw(current_soc, station_kw)
            step_energy_kwh = delta_soc * self.usable_battery_kwh
            total_hours += step_energy_kwh / max(1.0, power_kw)

        duration_minutes = total_hours * 60.0
        
        # Add 3 minutes plug-in / handshake / payment overhead
        duration_minutes += 3.0

        total_cost = (energy_needed_kwh * rate_per_kwh) + session_fee
        avg_power = energy_needed_kwh / (total_hours) if total_hours > 0 else 0.0

        return {
            "energy_added_kwh": round(energy_needed_kwh, 2),
            "duration_minutes": round(duration_minutes, 1),
            "cost": round(total_cost, 2),
            "average_kw": round(avg_power, 1)
        }
