"""
Weather module supporting Live OpenWeatherMap data, Historical averages,
and Manual user overrides, plus HVAC & battery temperature modifiers.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import math
import httpx

@dataclass
class WeatherConditions:
    temperature_f: float = 70.0
    wind_speed_mph: float = 0.0
    wind_direction_deg: float = 0.0  # Meteorological degrees (direction wind is coming FROM)
    road_condition: str = "dry"      # "dry", "wet", "snow_ice"
    cabin_temp_f: float = 70.0
    mode: str = "manual"             # "live", "historical", "manual"

    def get_hvac_power_kw(self) -> float:
        """
        Calculates HVAC draw for the Equinox EV Ultium Heat Pump system.
        """
        delta_t = abs(self.temperature_f - self.cabin_temp_f)
        
        if delta_t <= 3.0:
            # Gentle fan/ventilation
            return 0.25

        if self.temperature_f > self.cabin_temp_f:
            # A/C Cooling: Compressor + blower
            # 0.4 kW base + 0.05 kW per deg F difference, max 2.5 kW
            return min(2.5, 0.40 + 0.05 * delta_t)
        else:
            # Heating
            if self.temperature_f >= 40.0:
                # Heat pump operating in high efficiency zone
                return min(2.5, 0.45 + 0.045 * delta_t)
            else:
                # Heat pump + auxiliary PTC resistive heater kicks in
                base_hp = 0.45 + 0.045 * (self.cabin_temp_f - 40.0)
                ptc_extra = 0.075 * (40.0 - self.temperature_f)
                return min(5.0, base_hp + ptc_extra)

    def get_battery_temp_efficiency_factor(self) -> float:
        """
        Efficiency factor due to electrochemical kinetics / internal resistance.
        Optimal around 70F (1.0). In extreme cold, drops to ~0.82-0.85.
        """
        if self.temperature_f >= 65.0:
            return 1.0
        elif self.temperature_f >= 32.0:
            # Linear scale from 1.0 down to 0.90 at 32F
            t = (self.temperature_f - 32.0) / (65.0 - 32.0)
            return 0.90 + 0.10 * t
        elif self.temperature_f >= 0.0:
            # Linear scale from 0.90 down to 0.80 at 0F
            t = (self.temperature_f - 0.0) / (32.0 - 0.0)
            return 0.80 + 0.10 * t
        else:
            return 0.75

    def get_effective_headwind_mph(self, segment_bearing_deg: float) -> float:
        """
        Calculates the headwind component along the direction of travel.
        Positive = headwind (increases aerodynamic resistance).
        Negative = tailwind (assists vehicle).
        
        Note: Meteorological wind direction theta_w is where wind comes FROM.
        Angle between vehicle direction and wind origin:
        headwind = wind_speed * cos(segment_bearing - wind_direction)
        """
        rel_angle_rad = math.radians(segment_bearing_deg - self.wind_direction_deg)
        return self.wind_speed_mph * math.cos(rel_angle_rad)


class WeatherService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def get_live_weather(self, lat: float, lon: float, cabin_temp_f: float = 70.0) -> WeatherConditions:
        """
        Fetches live weather from OpenWeatherMap API.
        """
        if not self.api_key:
            return WeatherConditions(
                temperature_f=68.0,
                wind_speed_mph=5.0,
                wind_direction_deg=270.0,
                road_condition="dry",
                cabin_temp_f=cabin_temp_f,
                mode="live_fallback"
            )

        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key,
            "units": "imperial"
        }

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    temp_f = data.get("main", {}).get("temp", 70.0)
                    wind_speed = data.get("wind", {}).get("speed", 0.0)
                    wind_deg = data.get("wind", {}).get("deg", 0.0)
                    
                    weather_main = data.get("weather", [{}])[0].get("main", "").lower()
                    road_cond = "dry"
                    if any(w in weather_main for w in ["rain", "drizzle", "thunderstorm"]):
                        road_cond = "wet"
                    elif any(w in weather_main for w in ["snow", "sleet", "ice"]):
                        road_cond = "snow_ice"

                    return WeatherConditions(
                        temperature_f=float(temp_f),
                        wind_speed_mph=float(wind_speed),
                        wind_direction_deg=float(wind_deg),
                        road_condition=road_cond,
                        cabin_temp_f=cabin_temp_f,
                        mode="live"
                    )
        except Exception:
            pass

        return WeatherConditions(
            temperature_f=68.0,
            wind_speed_mph=5.0,
            wind_direction_deg=270.0,
            road_condition="dry",
            cabin_temp_f=cabin_temp_f,
            mode="live_fallback"
        )

    def get_historical_weather(self, month: int, state_or_region: str = "PA", cabin_temp_f: float = 70.0) -> WeatherConditions:
        """
        Provides climatological averages for the Mid-Atlantic / Ohio Valley corridor by month (1=Jan to 12=Dec).
        """
        # Monthly averages: (temp_f, wind_mph, wind_deg, typical_road_cond)
        climatology = {
            1: (28.0, 10.5, 280.0, "snow_ice"),
            2: (31.0, 10.0, 275.0, "snow_ice"),
            3: (40.0, 11.0, 270.0, "wet"),
            4: (51.0, 9.5, 260.0, "wet"),
            5: (62.0, 8.0, 250.0, "dry"),
            6: (71.0, 7.5, 240.0, "dry"),
            7: (76.0, 7.0, 240.0, "dry"),
            8: (74.0, 6.8, 240.0, "dry"),
            9: (67.0, 7.5, 250.0, "dry"),
            10: (54.0, 8.5, 260.0, "dry"),
            11: (44.0, 9.5, 270.0, "wet"),
            12: (34.0, 10.0, 280.0, "snow_ice"),
        }
        
        m_data = climatology.get(month, (65.0, 8.0, 270.0, "dry"))
        return WeatherConditions(
            temperature_f=m_data[0],
            wind_speed_mph=m_data[1],
            wind_direction_deg=m_data[2],
            road_condition=m_data[3],
            cabin_temp_f=cabin_temp_f,
            mode="historical"
        )
