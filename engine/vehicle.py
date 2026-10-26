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
    gear_lbs: float = 100.0    # 0 to 250 lbs slider

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
        total_lbs += max(0.0, min(250.0, self.gear_lbs))
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
        total_lbs += max(0.0, min(250.0, self.gear_lbs))
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
        Calculates maximum DC fast charging power (kW) at a given State of Charge (0.0 to 1.0).
        Empirically calibrated for 2024/2025 Chevrolet Equinox EV (Ultium 85 kWh usable, 288V nominal pack):
        - 0% to 10%: Rapid thermal/voltage ramp 70 -> 150 kW
        - 10% to 22%: Peak 150 kW plateau (~500A limit on high-power stalls)
        - 22% to 45%: Initial step-down taper 150 -> 110 kW
        - 45% to 65%: Mid-pack thermal taper 110 -> 75 kW
        - 65% to 80%: High-voltage taper 75 -> 45 kW
        - 80% to 90%: Protection taper 45 -> 25 kW
        - 90% to 100%: CV finish taper 25 -> 12 kW
        Yields an empirical 10% to 80% duration of ~37-39 minutes (~97 kW average), matching
        real-world tests from InsideEVs (Tom Moloughney / State of Charge) and EVKX.net.
        """
        soc = max(0.0, min(1.0, soc))

        if soc <= 0.10:
            car_power = 70.0 + (soc / 0.10) * 80.0
        elif soc <= 0.22:
            car_power = 150.0
        elif soc <= 0.45:
            t = (soc - 0.22) / (0.45 - 0.22)
            car_power = 150.0 - t * 40.0
        elif soc <= 0.65:
            t = (soc - 0.45) / (0.65 - 0.45)
            car_power = 110.0 - t * 35.0
        elif soc <= 0.80:
            t = (soc - 0.65) / (0.80 - 0.65)
            car_power = 75.0 - t * 30.0
        elif soc <= 0.90:
            t = (soc - 0.80) / (0.90 - 0.80)
            car_power = 45.0 - t * 20.0
        else:
            t = (soc - 0.90) / (1.00 - 0.90)
            car_power = 25.0 - t * 13.0

        return min(car_power, station_kw)

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
