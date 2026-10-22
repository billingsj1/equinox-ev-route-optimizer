"""
Orchestrator for automated CPO pricing pipeline.
Discovers stations via OCM and queries backend APIs for:
IONNA, Mercedes-Benz, Electrify America, Applegreen, Francis Energy, and ChargePoint.
Saves validated records to data/prices.json and data/prices.db.
"""
import asyncio
import json
import os
import sqlite3
import logging
from typing import List, Dict, Any

from pipeline.networks.electrify_america import ElectrifyAmericaAdapter
from pipeline.networks.chargepoint import ChargePointAdapter
from pipeline.networks.applegreen import ApplegreenAdapter
from pipeline.networks.francis_energy import FrancisEnergyAdapter
from pipeline.networks.mercedes_benz import MercedesBenzAdapter
from pipeline.networks.ionna import IONNAAdapter
from pipeline.networks.open_charge_map import OpenChargeMapClient
from pipeline.networks.base import StationTariff

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pricing_pipeline")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PRICES_JSON = os.path.join(DATA_DIR, "prices.json")
INITIAL_PRICES_JSON = os.path.join(DATA_DIR, "initial_prices.json")
PRICES_DB = os.path.join(DATA_DIR, "prices.db")

class PricingScraperPipeline:
    def __init__(self, ocm_key: str = None):
        self.ocm_client = OpenChargeMapClient(api_key=ocm_key)
        self.adapters = [
            ElectrifyAmericaAdapter(),
            ChargePointAdapter(),
            ApplegreenAdapter(),
            FrancisEnergyAdapter(),
            MercedesBenzAdapter(),
            IONNAAdapter(),
        ]

    def _init_sqlite_db(self):
        conn = sqlite3.connect(PRICES_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stations (
                id TEXT PRIMARY KEY,
                network TEXT,
                name TEXT,
                city TEXT,
                state TEXT,
                latitude REAL,
                longitude REAL,
                power_kw REAL,
                rate_off_peak REAL,
                rate_on_peak REAL,
                gm_discount_eligible INTEGER,
                ea_pass_eligible INTEGER,
                membership_rate_off_peak REAL,
                membership_rate_on_peak REAL,
                session_fee REAL,
                plugshare_url TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def _save_to_sqlite(self, stations: List[Dict[str, Any]]):
        self._init_sqlite_db()
        conn = sqlite3.connect(PRICES_DB)
        cursor = conn.cursor()
        for s in stations:
            rate_reg = s.get("rate_regular", {})
            rate_mem = s.get("membership_rate", {})
            cursor.execute("""
                INSERT OR REPLACE INTO stations (
                    id, network, name, city, state, latitude, longitude, power_kw,
                    rate_off_peak, rate_on_peak, gm_discount_eligible, ea_pass_eligible,
                    membership_rate_off_peak, membership_rate_on_peak, session_fee,
                    plugshare_url, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                s["id"], s["network"], s["name"], s.get("city", ""), s.get("state", ""),
                s["latitude"], s["longitude"], s["power_kw"],
                rate_reg.get("off_peak", 0.45), rate_reg.get("on_peak", 0.45),
                1 if s.get("gm_discount_eligible") else 0,
                1 if s.get("ea_pass_eligible") else 0,
                rate_mem.get("off_peak", 0.45), rate_mem.get("on_peak", 0.45),
                s.get("session_fee", 0.0), s.get("plugshare_url", "")
            ))
        conn.commit()
        conn.close()

    async def run(
        self,
        bbox: tuple = (38.5, -82.0, 41.5, -74.5) # Default Mid-Atlantic corridor (OH, PA, MD, NJ, WV)
    ):
        logger.info(f"Starting pricing pipeline scrape for corridor {bbox}...")
        lat_min, lon_min, lat_max, lon_max = bbox

        # 1. Load existing verified initial stations
        existing_stations: Dict[str, Dict[str, Any]] = {}
        if os.path.exists(INITIAL_PRICES_JSON):
            with open(INITIAL_PRICES_JSON, "r", encoding="utf-8") as f:
                for item in json.load(f):
                    existing_stations[item["id"]] = item

        # 2. Query CPO network backend APIs
        for adapter in self.adapters:
            logger.info(f"Querying backend API for network: {adapter.network_name}")
            try:
                results = await adapter.fetch_prices_for_bounding_box(lat_min, lon_min, lat_max, lon_max)
                logger.info(f"Retrieved {len(results)} stations from {adapter.network_name}")
                for r in results:
                    existing_stations[r.station_id] = {
                        "id": r.station_id,
                        "name": r.name,
                        "network": r.network,
                        "city": r.city,
                        "state": r.state,
                        "latitude": r.latitude,
                        "longitude": r.longitude,
                        "power_kw": r.power_kw,
                        "connectors": r.connectors,
                        "rate_regular": {
                            "off_peak": r.rate_off_peak,
                            "on_peak": r.rate_on_peak
                        },
                        "gm_discount_eligible": r.gm_discount_eligible,
                        "gm_discount_pct": r.gm_discount_pct,
                        "ea_pass_eligible": r.ea_pass_eligible,
                        "membership_rate": {
                            "off_peak": r.membership_rate_off_peak,
                            "on_peak": r.membership_rate_on_peak
                        },
                        "session_fee": r.session_fee,
                        "plugshare_url": r.plugshare_url
                    }
            except Exception as e:
                logger.warning(f"Error querying {adapter.network_name}: {e}")

        # 3. Export to prices.json
        final_list = list(existing_stations.values())
        with open(PRICES_JSON, "w", encoding="utf-8") as f:
            json.dump(final_list, f, indent=2)
        logger.info(f"Wrote {len(final_list)} stations to {PRICES_JSON}")

        # 4. Export to SQLite
        self._save_to_sqlite(final_list)
        logger.info(f"Indexed {len(final_list)} stations into {PRICES_DB}")

        return final_list

if __name__ == "__main__":
    pipeline = PricingScraperPipeline()
    asyncio.run(pipeline.run())
