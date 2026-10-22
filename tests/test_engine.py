import unittest
from engine.vehicle import EquinoxEVFWD, PayloadConfig
from engine.weather import WeatherConditions
from engine.energy import EnergySimulator, DrivingProfile
from engine.station_manager import StationManager
from engine.tolls import TollCalculator, TollPassConfig
from engine.optimizer import MultiObjectiveOptimizer

class TestEquinoxOptimizer(unittest.TestCase):
    def setUp(self):
        self.vehicle = EquinoxEVFWD()
        self.station_mgr = StationManager()
        self.toll_calc = TollCalculator()
        self.optimizer = MultiObjectiveOptimizer(self.vehicle, self.station_mgr, self.toll_calc)

    def test_vehicle_mass(self):
        payload = PayloadConfig(josh=True, courtney=True, asher=True, arno=True, gear_lbs=50.0)
        mass_kg = self.vehicle.get_total_mass_kg(payload)
        mass_lbs = mass_kg * 2.20462
        self.assertAlmostEqual(mass_lbs, 5323.0, delta=15.0)

    def test_charging_curve(self):
        # 10% to 50%
        dur_10_50 = self.vehicle.calculate_charge_session(0.10, 0.50, station_kw=150.0, rate_per_kwh=0.45)
        # 50% to 90% (should take longer due to Ultium taper)
        dur_50_90 = self.vehicle.calculate_charge_session(0.50, 0.90, station_kw=150.0, rate_per_kwh=0.45)
        self.assertGreater(dur_50_90["duration_minutes"], dur_10_50["duration_minutes"])

    def test_cold_weather_hvac_draw(self):
        cold_weather = WeatherConditions(temperature_f=10.0)
        mild_weather = WeatherConditions(temperature_f=68.0)
        self.assertGreater(cold_weather.get_hvac_power_kw(), mild_weather.get_hvac_power_kw())

    def test_tolls_ezpass_discount(self):
        toll_ez = TollPassConfig(has_ezpass=True)
        toll_cash = TollPassConfig(has_ezpass=False)
        res_ez = self.toll_calc.calculate_corridor_tolls("PA_Turnpike", toll_ez)
        res_cash = self.toll_calc.calculate_corridor_tolls("PA_Turnpike", toll_cash)
        self.assertLess(res_ez["total_toll"], res_cash["total_toll"])

if __name__ == '__main__':
    unittest.main()
