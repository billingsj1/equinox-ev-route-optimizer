"""
Orchestrator for automated CPO pricing pipeline.
Discovers stations via Open Charge Map (OCM) in OH, PA, NJ, WV, MD (CCS1 >= 100 kW),
scrapes network pricing (DCFC Tracker, IONNA, Mercedes-Benz, Applegreen, ChargePoint, Francis Energy),
flags unverified stations for manual entry with source links, and persists data.
"""
import asyncio
import json
import os
import sqlite3
import logging
from typing import List, Dict, Any, Optional

from pipeline.networks.electrify_america import ElectrifyAmericaAdapter
from pipeline.networks.chargepoint import ChargePointAdapter
from pipeline.networks.applegreen import ApplegreenAdapter
from pipeline.networks.francis_energy import FrancisEnergyAdapter
from pipeline.networks.mercedes_benz import MercedesBenzAdapter
from pipeline.networks.ionna import IONNAAdapter
from pipeline.networks.open_charge_map import OpenChargeMapClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pricing_pipeline")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PRICES_JSON = os.path.join(DATA_DIR, "prices.json")
INITIAL_PRICES_JSON = os.path.join(DATA_DIR, "initial_prices.json")
PRICES_DB = os.path.join(DATA_DIR, "prices.db")

class PricingScraperPipeline:
    def __init__(self, ocm_key: Optional[str] = None):
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
                price_verified INTEGER DEFAULT 1,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Check if price_verified column exists
        cursor.execute("PRAGMA table_info(stations)")
        columns = [col[1] for col in cursor.fetchall()]
        if "price_verified" not in columns:
            cursor.execute("ALTER TABLE stations ADD COLUMN price_verified INTEGER DEFAULT 1")
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
                    plugshare_url, price_verified, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                s["id"], s["network"], s["name"], s.get("city", ""), s.get("state", ""),
                s["latitude"], s["longitude"], s["power_kw"],
                rate_reg.get("off_peak", 0.50), rate_reg.get("on_peak", 0.50),
                1 if s.get("gm_discount_eligible") else 0,
                1 if s.get("ea_pass_eligible") else 0,
                rate_mem.get("off_peak", 0.45), rate_mem.get("on_peak", 0.45),
                s.get("session_fee", 0.0), s.get("plugshare_url", ""),
                1 if s.get("price_verified", True) else 0
            ))
        conn.commit()
        conn.close()

    def load_existing_stations(self) -> Dict[str, Dict[str, Any]]:
        stations = {}
        for path in [INITIAL_PRICES_JSON, PRICES_JSON]:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for item in json.load(f):
                        stations[item["id"]] = item
        return stations

    async def pull_ocm_stations(self, states: List[str] = None) -> List[Dict[str, Any]]:
        """
        Pulls CCS1 >= 100 kW stations from OCM across target states,
        merges with existing stations, and flags new unverified additions.
        """
        existing = self.load_existing_stations()
        ocm_items = await self.ocm_client.discover_chargers_for_states(states=states)
        added_count = 0

        for item in ocm_items:
            addr = item.get("AddressInfo", {})
            lat = addr.get("Latitude")
            lon = addr.get("Longitude")
            if not lat or not lon:
                continue

            # Check if this station already exists (by lat/lon distance ~400m)
            matched_id = None
            for ex_id, ex_st in existing.items():
                d_lat = abs(ex_st["latitude"] - lat)
                d_lon = abs(ex_st["longitude"] - lon)
                if d_lat < 0.005 and d_lon < 0.005:
                    matched_id = ex_id
                    break

            if matched_id:
                # Already exists, preserve verified pricing
                continue

            # Determine network from OperatorID
            op_id = item.get("OperatorID")
            op_title = item.get("OperatorInfo", {}).get("Title", "")
            network = "Other"
            gm_perk = False
            ea_pass = False

            if op_id == 3831 or "ionna" in op_title.lower():
                network = "IONNA"
                gm_perk = True
            elif op_id == 3827 or "mercedes" in op_title.lower():
                network = "Mercedes-Benz"
            elif op_id == 3318 or "electrify america" in op_title.lower():
                network = "Electrify America"
                ea_pass = True
            elif op_id == 3516 or "applegreen" in op_title.lower():
                network = "Applegreen"
            elif op_id == 5 or "chargepoint" in op_title.lower():
                network = "ChargePoint"
            elif op_id == 3733 or "francis" in op_title.lower():
                network = "Francis Energy"
            elif op_id in [15, 3252] or "evgo" in op_title.lower():
                network = "EVgo"
                gm_perk = True

            # Determine max kW power
            max_kw = 150
            for conn in item.get("Connections", []):
                p = conn.get("PowerKW")
                if p and p > max_kw:
                    max_kw = int(p)

            st_id = f"{network.lower().replace(' ', '-')}-{addr.get('ID', item.get('ID'))}"
            new_station = {
                "id": st_id,
                "name": f"{network} - {addr.get('Title', 'Station')}",
                "network": network,
                "city": addr.get("Town", ""),
                "state": addr.get("StateOrProvince", "").strip().upper(),
                "latitude": round(lat, 5),
                "longitude": round(lon, 5),
                "power_kw": max_kw,
                "connectors": ["CCS1"],
                "rate_regular": {
                    "off_peak": 0.50,
                    "on_peak": 0.50
                },
                "gm_discount_eligible": gm_perk,
                "gm_discount_pct": 0.10 if gm_perk else 0.0,
                "ea_pass_eligible": ea_pass,
                "membership_rate": {
                    "off_peak": 0.45 if ea_pass else 0.50,
                    "on_peak": 0.45 if ea_pass else 0.50
                },
                "session_fee": 0.0,
                "plugshare_url": addr.get("RelatedURL") or f"https://openchargemap.org/site/poi/details/{item.get('ID')}",
                "price_verified": False,
                "ocm_id": item.get("ID")
            }
            existing[st_id] = new_station
            added_count += 1

        final_list = list(existing.values())
        with open(PRICES_JSON, "w", encoding="utf-8") as f:
            json.dump(final_list, f, indent=2)
        self._save_to_sqlite(final_list)

        logger.info(f"Added {added_count} new stations. Total database: {len(final_list)}")
        return final_list

    async def refresh_prices(self) -> List[Dict[str, Any]]:
        """
        Scrapes pricing across active stations using network adapters and verified heuristics.
        """
        existing = self.load_existing_stations()

        # Update verified prices from network adapters
        for adapter in self.adapters:
            try:
                results = await adapter.fetch_prices_for_bounding_box(37.0, -85.0, 42.5, -73.5)
                for r in results:
                    if r.station_id in existing:
                        st = existing[r.station_id]
                        st["rate_regular"]["off_peak"] = r.rate_off_peak
                        st["rate_regular"]["on_peak"] = r.rate_on_peak
                        st["price_verified"] = True
                        if r.plugshare_url:
                            st["plugshare_url"] = r.plugshare_url
            except Exception as e:
                logger.warning(f"Error refreshing {adapter.network_name}: {e}")

        final_list = list(existing.values())
        with open(PRICES_JSON, "w", encoding="utf-8") as f:
            json.dump(final_list, f, indent=2)
        self._save_to_sqlite(final_list)
        return final_list

    def update_single_station_price(self, station_id: str, new_price: float) -> Optional[Dict[str, Any]]:
        existing = self.load_existing_stations()
        if station_id in existing:
            st = existing[station_id]
            st["rate_regular"]["off_peak"] = new_price
            st["rate_regular"]["on_peak"] = new_price
            st["price_verified"] = True
            final_list = list(existing.values())
            with open(PRICES_JSON, "w", encoding="utf-8") as f:
                json.dump(final_list, f, indent=2)
            self._save_to_sqlite(final_list)
            return st
        return None

if __name__ == "__main__":
    pipeline = PricingScraperPipeline()
    asyncio.run(pipeline.pull_ocm_stations())
    asyncio.run(pipeline.refresh_prices())
