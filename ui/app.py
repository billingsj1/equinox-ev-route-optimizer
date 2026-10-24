"""
FastAPI application serving the EV Route Optimizer dashboard,
REST endpoints for physics simulation and multi-objective Pareto optimization.
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os

from engine.vehicle import EquinoxEVFWD, PayloadConfig
from engine.weather import WeatherConditions, WeatherService
from engine.energy import EnergySimulator, DrivingProfile
from engine.router import ORSRouter, RoutePath
from engine.station_manager import StationManager
from engine.tolls import TollCalculator, TollPassConfig
from engine.optimizer import MultiObjectiveOptimizer, Itinerary

app = FastAPI(title="2025 Equinox EV Route Optimizer")

# Serve static files if directory exists
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

vehicle = EquinoxEVFWD()
station_manager = StationManager()
toll_calculator = TollCalculator()
router = ORSRouter()
weather_service = WeatherService()
optimizer = MultiObjectiveOptimizer(vehicle, station_manager, toll_calculator)

class OptimizationRequest(BaseModel):
    # Origin & Destination (default Washington PA to Chester Springs / Philly)
    start_lon: float = -80.2462
    start_lat: float = 40.1740
    end_lon: float = -75.6268
    end_lat: float = 40.0934
    
    # Payload toggles
    payload_josh: bool = True
    payload_courtney: bool = True
    payload_asher: bool = True
    payload_arno: bool = True
    payload_gear_lbs: float = 50.0
    
    # Driving & Speed
    speed_offset_mph: float = 5.0
    max_speed_cap_mph: float = 75.0
    initial_soc_pct: float = 100.0
    min_safety_buffer_pct: float = 10.0
    target_arrival_soc_pct: float = 20.0 # Ideal ending charge state (default 20%)
    ideal_time_min_minutes: float = 90.0
    ideal_time_max_minutes: float = 150.0

    # Weather
    weather_mode: str = "manual" # "manual", "historical", "live"
    temperature_f: float = 68.0
    wind_speed_mph: float = 7.0
    wind_direction_deg: float = 270.0 # From West
    road_condition: str = "dry"       # "dry", "wet", "snow_ice"
    cabin_temp_f: float = 70.0
    historical_month: int = 10

    # Tolls & Passes
    has_ezpass: bool = True
    has_nj_green_pass: bool = True
    time_of_day_hour: int = 14
    has_ea_pass: bool = False

@app.get("/", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
@app.get("/api/index", response_class=HTMLResponse)
async def serve_index():
    root_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html")
    if os.path.exists(root_path):
        with open(root_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/stations")
async def get_stations():
    """
    Returns all verified chargers currently loaded in the database.
    """
    return [
        {
            "id": s.id,
            "name": s.name,
            "network": s.network,
            "city": s.city,
            "state": s.state,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "power_kw": s.power_kw,
            "rate_off_peak": s.rate_off_peak,
            "rate_on_peak": s.rate_on_peak,
            "gm_discount_eligible": s.gm_discount_eligible,
            "ea_pass_eligible": s.ea_pass_eligible,
            "membership_rate_off_peak": s.membership_rate_off_peak,
            "membership_rate_on_peak": s.membership_rate_on_peak,
            "session_fee": s.session_fee,
            "plugshare_url": s.plugshare_url
        }
        for s in station_manager.stations
    ]

@app.post("/api/optimize")
async def run_optimization(req: OptimizationRequest):
    # 1. Payload
    payload = PayloadConfig(
        josh=req.payload_josh,
        courtney=req.payload_courtney,
        asher=req.payload_asher,
        arno=req.payload_arno,
        gear_lbs=req.payload_gear_lbs
    )

    # 2. Driving Profile
    profile = DrivingProfile(
        speed_offset_mph=req.speed_offset_mph,
        max_speed_cap_mph=req.max_speed_cap_mph,
        min_safety_buffer_soc=req.min_safety_buffer_pct / 100.0,
        target_arrival_soc=req.target_arrival_soc_pct / 100.0,
        ideal_time_min_bound=req.ideal_time_min_minutes,
        ideal_time_max_bound=req.ideal_time_max_minutes
    )

    # 3. Weather
    if req.weather_mode == "live":
        weather = await weather_service.get_live_weather(
            lat=req.start_lat,
            lon=req.start_lon,
            cabin_temp_f=req.cabin_temp_f
        )
    elif req.weather_mode == "historical":
        weather = weather_service.get_historical_weather(
            month=req.historical_month,
            cabin_temp_f=req.cabin_temp_f
        )
    else:
        weather = WeatherConditions(
            temperature_f=req.temperature_f,
            wind_speed_mph=req.wind_speed_mph,
            wind_direction_deg=req.wind_direction_deg,
            road_condition=req.road_condition,
            cabin_temp_f=req.cabin_temp_f,
            mode="manual"
        )

    # 4. Tolls
    toll_config = TollPassConfig(
        has_ezpass=req.has_ezpass,
        has_nj_green_pass=req.has_nj_green_pass,
        time_of_day_hour=req.time_of_day_hour
    )

    # 5. Fetch alternative routes
    routes = await router.get_routes([req.start_lon, req.start_lat], [req.end_lon, req.end_lat], target_count=3)

    # 6. Run Pareto optimization
    initial_soc = req.initial_soc_pct / 100.0
    results = optimizer.optimize(
        routes=routes,
        weather=weather,
        payload=payload,
        profile=profile,
        toll_config=toll_config,
        initial_soc=initial_soc
    )

    def serialize_itin(itin: Itinerary) -> Dict[str, Any]:
        return {
            "itinerary_type": itin.itinerary_type,
            "route_name": itin.route_name,
            "route_id": itin.route_id,
            "total_distance_miles": itin.total_distance_miles,
            "driving_time_hours": itin.driving_time_hours,
            "charging_time_hours": itin.charging_time_hours,
            "total_time_hours": itin.total_time_hours,
            "charging_cost": itin.charging_cost,
            "toll_cost": itin.toll_cost,
            "total_cost": itin.total_cost,
            "pareto_score": itin.pareto_score,
            "final_arrival_soc": itin.final_arrival_soc,
            "membership_recommendations": itin.membership_recommendations,
            "stops": [
                {
                    "station_id": s.station.id,
                    "name": s.station.name,
                    "network": s.network,
                    "power_kw": s.station.power_kw,
                    "arrival_soc": s.arrival_soc,
                    "target_soc": s.target_soc,
                    "energy_added_kwh": s.energy_added_kwh,
                    "charge_duration_minutes": s.charge_duration_minutes,
                    "charging_cost": s.charging_cost,
                    "rate_per_kwh": s.rate_per_kwh,
                    "plugshare_url": s.plugshare_url,
                    "latitude": s.station.latitude,
                    "longitude": s.station.longitude
                }
                for s in itin.stops
            ],
            "soc_waypoints": itin.soc_waypoint_profile
        }

    routes_geojson = [
        {
            "route_id": r.route_id,
            "name": r.name,
            "summary": r.summary,
            "distance_miles": r.total_distance_miles,
            "coordinates": r.coordinates
        }
        for r in routes
    ]

    return {
        "vehicle_total_mass_lbs": round(vehicle.get_total_mass_kg(payload) * 2.20462, 1),
        "vehicle_total_mass_kg": round(vehicle.get_total_mass_kg(payload), 1),
        "weather_summary": {
            "temp_f": weather.temperature_f,
            "wind_speed_mph": weather.wind_speed_mph,
            "wind_direction_deg": weather.wind_direction_deg,
            "road_condition": weather.road_condition,
            "hvac_kw": round(weather.get_hvac_power_kw(), 2),
            "battery_eff_factor": round(weather.get_battery_temp_efficiency_factor(), 2)
        },
        "itineraries": {
            "fastest": serialize_itin(results["fastest"]),
            "cheapest": serialize_itin(results["cheapest"]),
            "balanced": serialize_itin(results["balanced"])
        },
        "routes": routes_geojson
    }


from pipeline.scraper import PricingScraperPipeline

class UpdatePriceRequest(BaseModel):
    station_id: str
    price: float

class PullOcmRequest(BaseModel):
    api_key: Optional[str] = "3e165280-87eb-4a3d-8741-7d80903bb87b"
    states: Optional[List[str]] = ["OH", "PA", "NJ", "WV", "MD"]

@app.post("/api/stations/pull-ocm")
async def pull_ocm_stations(req: PullOcmRequest):
    pipeline = PricingScraperPipeline(ocm_key=req.api_key)
    updated = await pipeline.pull_ocm_stations(states=req.states)
    station_manager.load_stations()
    return {"status": "ok", "count": len(updated), "stations": updated}

@app.post("/api/stations/refresh-prices")
async def refresh_prices():
    pipeline = PricingScraperPipeline()
    updated = await pipeline.refresh_prices()
    station_manager.load_stations()
    return {"status": "ok", "count": len(updated), "stations": updated}

@app.post("/api/stations/reset")
@app.post("/api/stations/clear")
async def reset_stations():
    pipeline = PricingScraperPipeline()
    baseline = pipeline.reset_to_baseline()
    station_manager.load_stations()
    return {"status": "ok", "count": len(baseline), "stations": baseline}

@app.post("/api/stations/update-price")
async def update_single_price(req: UpdatePriceRequest):
    pipeline = PricingScraperPipeline()
    st = pipeline.update_single_station_price(req.station_id, req.price)
    if st:
        station_manager.load_stations()
        return {"status": "ok", "station": st}
    return JSONResponse(status_code=404, content={"status": "error", "message": "Station not found"})
