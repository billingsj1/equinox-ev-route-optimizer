"""
Main entry point for 2025 Chevrolet Equinox EV Route Optimizer & Pricing Scraper.
Supports Web UI, CLI route simulation, and automated CPO pricing scraping.
"""
import sys
import argparse
import uvicorn
import asyncio

def run_server(host="127.0.0.1", port=8000):
    print(f"\n=======================================================")
    print(f"🚀 Equinox EV Multi-Objective Optimizer & Pricing Engine")
    print(f"📡 Web Dashboard: http://{host}:{port}")
    print(f"=======================================================\n")
    uvicorn.run("ui.app:app", host=host, port=port, reload=False)

def run_cli():
    from engine.optimizer import MultiObjectiveOptimizer
    from engine.router import ORSRouter
    from engine.weather import WeatherConditions
    from engine.vehicle import PayloadConfig
    from engine.energy import DrivingProfile
    from engine.tolls import TollPassConfig

    print("Running Pareto route optimization across corridor alternatives...")
    opt = MultiObjectiveOptimizer()
    router = ORSRouter()
    routes = router._get_default_corridor_alternatives()

    weather = WeatherConditions(temperature_f=68.0, road_condition="dry")
    payload = PayloadConfig(josh=True, courtney=True, asher=True, arno=True, gear_lbs=50.0)
    profile = DrivingProfile(speed_offset_mph=5.0, max_speed_cap_mph=75.0, min_safety_buffer_soc=0.10, target_arrival_soc=0.20)
    toll_config = TollPassConfig(has_ezpass=True, has_nj_green_pass=True)

    results = opt.optimize(routes, weather, payload, profile, toll_config, initial_soc=1.00)

    print("\n--- OPTIMIZATION RESULTS ---")
    for key, itin in results.items():
        print(f"\n[{itin.itinerary_type.upper()}] - {itin.route_name}")
        print(f"  Total Distance : {itin.total_distance_miles} miles")
        print(f"  Total Time     : {itin.total_time_hours} hrs (Driving: {itin.driving_time_hours}h, Charging: {itin.charging_time_hours}h)")
        print(f"  Total Cost     : ${itin.total_cost:.2f} (Charging: ${itin.charging_cost:.2f}, Tolls: ${itin.toll_cost:.2f})")
        print(f"  Final Arrival  : {itin.final_arrival_soc}% SoC")
        print(f"  Charging Stops : {len(itin.stops)}")
        for idx, s in enumerate(itin.stops):
            print(f"    Stop {idx+1}: {s.station.name} ({s.network}, {s.station.power_kw}kW)")
            print(f"           Arrival SoC: {s.arrival_soc}%, Target: {s.target_soc}% | Added: {s.energy_added_kwh} kWh | Duration: {s.charge_duration_minutes} min | Cost: ${s.charging_cost:.2f}")
        recs = itin.membership_recommendations or {}
        ea_rec = recs.get("electrify_america", {})
        if ea_rec and ea_rec.get("kwh_used", 0) > 0:
            print(f"  EA Pass+ Rec   : {'YES' if ea_rec['worth_it'] else 'NO'} (Net: ${ea_rec['net_benefit']:.2f} savings after $3.50 one-way fee)")
        tesla_rec = recs.get("tesla", {})
        if tesla_rec and tesla_rec.get("kwh_used", 0) > 0:
            print(f"  Tesla Mem Rec  : {'YES' if tesla_rec['worth_it'] else 'NO'} (Net: ${tesla_rec['net_benefit']:.2f} savings after $6.50 one-way fee)")

def run_scraper():
    from pipeline.scraper import PricingScraperPipeline
    pipeline = PricingScraperPipeline()
    asyncio.run(pipeline.run())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="2025 Equinox EV Route Optimizer & Pricing Engine")
    parser.add_argument("--cli", action="store_true", help="Run optimization in terminal")
    parser.add_argument("--scrape", action="store_true", help="Trigger CPO price scrapers")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")

    args = parser.parse_args()

    if args.cli:
        run_cli()
    elif args.scrape:
        run_scraper()
    else:
        run_server(host=args.host, port=args.port)
