import asyncio
import json
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from pipeline.scraper import PricingScraperPipeline

async def main():
    p = PricingScraperPipeline()
    # Test loading scraped database
    db = p.load_scraped_database()
    print("Scraped DB keys:", list(db.keys()))
    print("Tesla count in scraped DB:", len(db.get("tesla", [])))
    print("Sample Tesla item:", json.dumps(db.get("tesla", [])[0], indent=2) if db.get("tesla") else "None")
    
    # Test match_station_price
    price, url, gm = p.match_station_price(
        st_id="tesla-406608",
        network="Tesla",
        state="NJ",
        city="Mt Laurel",
        title="Mt Laurel Supercharger",
        address="NJ-73",
        lat=39.957,
        lon=-74.925,
        usage_cost=None,
        scraped_db=db
    )
    print(f"Match test for Mt Laurel NJ: price=${price}, url={url}")
    assert price is not None, "Failed to match Mt Laurel NJ Tesla station!"

    # Test Cherry Hill match
    price, url, gm = p.match_station_price(
        st_id="tesla-cherryhillnjhaddonfieldroadsupercharger",
        network="Tesla",
        state="NJ",
        city="Cherry Hill",
        title="Cherry Hill Supercharger",
        address="Haddonfield Rd",
        lat=39.939,
        lon=-75.025,
        usage_cost=None,
        scraped_db=db
    )
    print(f"Match test for Cherry Hill NJ: price=${price}, url={url}")
    assert price is not None, "Failed to match Cherry Hill NJ Tesla station!"
    
    # Test that an unknown Tesla station does NOT match DCFC
    price, url, gm = p.match_station_price(
        st_id="tesla-unknown-random-12345",
        network="Tesla",
        state="NJ",
        city="SomeTown",
        title="Random Supercharger",
        address="123 Main St",
        lat=39.0,
        lon=-74.0,
        usage_cost=None,
        scraped_db=db
    )
    print(f"Match test for unknown Tesla station: price={price}")
    assert price is None, "Unknown Tesla station should NOT match DCFC or synthesize rates!"
    
    print("\nALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
