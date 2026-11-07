#!/usr/bin/env python3
"""
Scrapes Google Places API (New) for walking-distance amenities around each charging station.
Idempotent and resumable: writes progress to data/station_amenities_db.json and
public/data/station_amenities_db.json every 25 stations.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error

DB_PATH = "data/station_amenities_db.json"
PUBLIC_DB_PATH = "public/data/station_amenities_db.json"
CACHE_PATH = "data/active_stations_cache.json"

def get_api_key():
    key = os.environ.get("GOOGLEMAPS_API_KEY")
    if not key and os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GOOGLEMAPS_API_KEY="):
                    key = line.strip().split("=", 1)[1].strip()
                    break
    if not key:
        raise ValueError("GOOGLEMAPS_API_KEY not found in environment or .env")
    return key

def parse_amenities_from_places(places):
    """Parses Google Places (New) response into structured amenity flags."""
    if not places:
        return {
            "host": None,
            "is_24_7": False,
            "has_restrooms": False,
            "has_coffee": False,
            "has_food": False,
            "rating": None,
            "user_ratings_total": None,
            "top_dining": [],
            "coffee_brands": []
        }

    host = None
    is_24_7 = False
    has_restrooms = False
    has_coffee = False
    has_food = False
    top_dining = []
    coffee_brands = []
    best_rating = None
    best_reviews = 0

    KNOWN_HOST_KEYWORDS = [
        "Sheetz", "Wawa", "Pilot Travel Center", "Flying J", "Love's Travel Stop",
        "Buc-ee's", "Target", "Walmart", "Meijer", "Giant Eagle", "GetGo",
        "Kroger", "Royal Farms", "Turnpike Service Plaza", "CVS", "Walgreens"
    ]

    for p in places:
        name = p.get("displayName", {}).get("text", "")
        ptype = p.get("primaryType", "")
        types = set(p.get("types", []))
        rating = p.get("rating")
        reviews = p.get("userRatingCount", 0)

        if rating and reviews and reviews > best_reviews:
            best_rating = rating
            best_reviews = reviews

        # 24/7 check
        hours = p.get("regularOpeningHours", {})
        periods = hours.get("periods", [])
        if len(periods) == 1 and periods[0].get("open", {}).get("day") == 0 and periods[0].get("open", {}).get("hour") == 0 and "close" not in periods[0]:
            is_24_7 = True
        weekday_desc = hours.get("weekdayDescriptions", [])
        if any("Open 24 hours" in desc for desc in weekday_desc):
            is_24_7 = True

        # Host detection
        if not host:
            for kw in KNOWN_HOST_KEYWORDS:
                if kw.lower() in name.lower():
                    host = kw
                    break

        # Restrooms: present in convenience stores, gas stations, plazas, large retail, sit-down restaurants
        if any(t in types for t in ["convenience_store", "gas_station", "rest_stop", "department_store", "supermarket", "shopping_mall", "restaurant", "fast_food_restaurant"]):
            has_restrooms = True

        # Coffee
        if any(t in types for t in ["cafe", "coffee_shop", "bakery"]) or any(c in name.lower() for c in ["starbucks", "dunkin", "coffee", "tim hortons", "sheetz", "wawa"]):
            has_coffee = True
            if any(c in name.lower() for c in ["starbucks", "dunkin", "tim hortons", "panera", "caribou"]):
                clean_name = name.split("-")[0].strip()
                if clean_name not in coffee_brands and len(coffee_brands) < 2:
                    coffee_brands.append(clean_name)

        # Food & dining
        if any(t in types for t in ["restaurant", "fast_food_restaurant", "cafe", "meal_takeaway", "pizza_delivery", "sandwich_shop"]):
            has_food = True
            clean_name = name.split("-")[0].strip()
            # Avoid duplicate generic names
            if clean_name not in top_dining and len(top_dining) < 3:
                top_dining.append(clean_name)
        elif any(t in types for t in ["convenience_store"]):
            has_food = True # e.g. Sheetz, Wawa, Buc-ees have food

    # Fallback host if not found from keywords
    if not host and places:
        # Check if first place is convenience store or supermarket
        p0 = places[0]
        p0_name = p0.get("displayName", {}).get("text", "")
        p0_types = set(p0.get("types", []))
        if any(t in p0_types for t in ["convenience_store", "gas_station", "supermarket", "shopping_mall", "department_store"]):
            host = p0_name.split("-")[0].strip()

    if not coffee_brands and has_coffee:
        if host in ["Sheetz", "Wawa", "Buc-ee's", "GetGo"]:
            coffee_brands.append(f"{host} Coffee Bar")

    return {
        "host": host,
        "is_24_7": is_24_7,
        "has_restrooms": has_restrooms,
        "has_coffee": has_coffee,
        "has_food": has_food,
        "rating": best_rating,
        "user_ratings_total": best_reviews if best_reviews > 0 else None,
        "top_dining": top_dining,
        "coffee_brands": coffee_brands
    }

def scrape_station_amenities(api_key, lat, lon):
    """Performs 1 Google Places Nearby Search request within 175m."""
    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.primaryType,places.types,places.rating,places.userRatingCount,places.regularOpeningHours"
    }
    payload = {
        "includedTypes": [
            "restaurant", "cafe", "fast_food_restaurant", "convenience_store",
            "gas_station", "supermarket", "bakery", "coffee_shop", "shopping_mall"
        ],
        "maxResultCount": 10,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": 175.0
            }
        }
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("places", [])
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"  HTTP error {e.code}: {err_body[:200]}")
        return []
    except Exception as e:
        print(f"  Request error: {e}")
        return []

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    api_key = get_api_key()

    if not os.path.exists(CACHE_PATH):
        print(f"Error: {CACHE_PATH} not found. Run discovery first.")
        sys.exit(1)

    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        stations = json.load(f)

    print(f"Loaded {len(stations)} stations from {CACHE_PATH}.")

    # Load existing amenities DB if present
    amenities_db = {}
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                amenities_db = json.load(f)
            print(f"Loaded existing database with {len(amenities_db)} entries.")
        except Exception as e:
            print(f"Warning: could not read {DB_PATH}: {e}")

    # Process all stations
    scraped_this_run = 0
    total = len(stations)

    start_time = time.time()
    for idx, st in enumerate(stations):
        st_id = st.get("id")
        lat = st.get("lat")
        lon = st.get("lon")
        name = st.get("name", "Unknown")

        if not st_id or lat is None or lon is None:
            continue

        if st_id in amenities_db:
            continue

        # Scrape
        places = scrape_station_amenities(api_key, lat, lon)
        parsed = parse_amenities_from_places(places)
        parsed["station_id"] = st_id
        parsed["station_name"] = name
        parsed["lat"] = lat
        parsed["lon"] = lon
        parsed["scraped_timestamp"] = int(time.time())

        amenities_db[st_id] = parsed
        scraped_this_run += 1

        print(f"[{idx+1}/{total}] {name[:45]} -> Host: {parsed.get('host') or 'None'} | Food: {parsed.get('has_food')} | 24/7: {parsed.get('is_24_7')} | Rating: {parsed.get('rating')}")

        # Save checkpoint every 25 stations
        if scraped_this_run % 25 == 0:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            with open(DB_PATH, "w", encoding="utf-8") as f:
                json.dump(amenities_db, f, indent=2)
            os.makedirs(os.path.dirname(PUBLIC_DB_PATH), exist_ok=True)
            with open(PUBLIC_DB_PATH, "w", encoding="utf-8") as f:
                json.dump(amenities_db, f, indent=2)
            print(f"  >> Checkpoint saved ({len(amenities_db)} total records in DB).")

        # Rate-limiting: gentle pause (0.12s ~ 8 req/sec)
        time.sleep(0.12)

    # Final write
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(amenities_db, f, indent=2)
    os.makedirs(os.path.dirname(PUBLIC_DB_PATH), exist_ok=True)
    with open(PUBLIC_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(amenities_db, f, indent=2)

    elapsed = time.time() - start_time
    cost = scraped_this_run * 0.032
    print("\n" + "="*60)
    print(f"Amenity Scrape Complete!")
    print(f"New Calls Made: {scraped_this_run}")
    print(f"Total Database Entries: {len(amenities_db)}")
    print(f"Elapsed Time: {elapsed:.1f} seconds")
    print(f"Estimated Cost: ${cost:.2f}")
    print(f"Saved to: {DB_PATH} and {PUBLIC_DB_PATH}")
    print("="*60)

if __name__ == "__main__":
    main()
