"""
Orchestrator for automated CPO discovery and live price scraping pipeline.
Discovers stations via Open Charge Map (OCM) in OH, PA, NJ, WV, MD (CCS1 >= 100 kW),
scrapes network pricing (IONNA, Mercedes-Benz HPC, ChargePoint live API, DCFC Tracker for EA/Applegreen/EVgo/Francis),
persists verified rates, and flags unverified stations (without assigning dummy prices) for manual inspection.
"""
import asyncio
import json
import os
import sqlite3
import logging
from typing import List, Dict, Any, Optional
import math

from pipeline.networks.chargepoint import ChargePointAdapter
from pipeline.networks.mercedes_benz import MercedesBenzAdapter
from pipeline.networks.ionna import IONNAAdapter
from pipeline.networks.dcfc_tracker import DCFCTrackerAdapter
from pipeline.networks.open_charge_map import OpenChargeMapClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pricing_pipeline")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PRICES_JSON = os.path.join(DATA_DIR, "prices.json")
INITIAL_PRICES_JSON = os.path.join(DATA_DIR, "initial_prices.json")
PRICES_DB = os.path.join(DATA_DIR, "prices.db")

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * r * math.asin(math.sqrt(max(0.0, min(1.0, a))))

class PricingScraperPipeline:
    def __init__(self, ocm_key: Optional[str] = None):
        self.ocm_client = OpenChargeMapClient(api_key=ocm_key)
        self.chargepoint_adapter = ChargePointAdapter()
        self.mercedes_adapter = MercedesBenzAdapter()
        self.ionna_adapter = IONNAAdapter()
        self.dcfc_adapter = DCFCTrackerAdapter()

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
            rate_reg = s.get("rate_regular") or {}
            rate_mem = s.get("membership_rate") or {}
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
                rate_reg.get("off_peak"), rate_reg.get("on_peak"),
                1 if s.get("gm_discount_eligible") else 0,
                1 if s.get("ea_pass_eligible") else 0,
                rate_mem.get("off_peak"), rate_mem.get("on_peak"),
                s.get("session_fee", 0.0), s.get("plugshare_url", ""),
                1 if s.get("price_verified", True) else 0
            ))
        conn.commit()
        conn.close()

    def load_baseline_stations(self) -> List[Dict[str, Any]]:
        if os.path.exists(INITIAL_PRICES_JSON):
            with open(INITIAL_PRICES_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def load_existing_stations(self) -> Dict[str, Dict[str, Any]]:
        stations = {}
        for path in [INITIAL_PRICES_JSON, PRICES_JSON]:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for item in json.load(f):
                        stations[item["id"]] = item
        return stations

    def reset_to_baseline(self) -> List[Dict[str, Any]]:
        """
        Clears all added stations and restores the database to the 20 verified baseline stations.
        """
        baseline = self.load_baseline_stations()
        for s in baseline:
            s["price_verified"] = True

        with open(PRICES_JSON, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2)

        # Reset SQLite table
        self._init_sqlite_db()
        conn = sqlite3.connect(PRICES_DB)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stations")
        conn.commit()
        conn.close()

        self._save_to_sqlite(baseline)
        logger.info(f"Database reset to baseline ({len(baseline)} stations).")
        return baseline

    async def pull_ocm_stations(self, states: List[str] = None) -> List[Dict[str, Any]]:
        """
        Pulls CCS1 >= 100 kW stations from OCM across target states,
        runs live pricing adapters to automatically find verified tariffs,
        and flags any remaining unverified stations with NULL prices (NO default 50c).
        """
        existing = self.load_existing_stations()
        ocm_items = await self.ocm_client.discover_chargers_for_states(states=states)
        added_count = 0

        # Pre-fetch live rates from adapters to cross-reference
        ionna_tariffs = await self.ionna_adapter.fetch_prices_for_bounding_box(37.0, -85.0, 42.5, -73.5)
        mercedes_tariffs = await self.mercedes_adapter.fetch_prices_for_bounding_box(37.0, -85.0, 42.5, -73.5)
        dcfc_records = await self.dcfc_adapter.fetch_prices_for_states(["pa", "oh", "md", "nj", "wv"])

        for item in ocm_items:
            addr = item.get("AddressInfo", {})
            lat = addr.get("Latitude")
            lon = addr.get("Longitude")
            if not lat or not lon:
                continue

            # Deduplicate by distance (< 0.5 miles)
            matched_id = None
            for ex_id, ex_st in existing.items():
                if haversine_miles(ex_st["latitude"], ex_st["longitude"], lat, lon) < 0.5:
                    matched_id = ex_id
                    break

            if matched_id:
                continue

            op_id = item.get("OperatorID")
            op_title = item.get("OperatorInfo", {}).get("Title", "").lower()
            network = "Other"
            gm_perk = False
            ea_pass = False

            if op_id == 3831 or "ionna" in op_title:
                network = "IONNA"
                gm_perk = True
            elif op_id == 3827 or "mercedes" in op_title:
                network = "Mercedes-Benz"
            elif op_id == 3318 or "electrify america" in op_title:
                network = "Electrify America"
                ea_pass = True
            elif op_id == 3516 or "applegreen" in op_title:
                network = "Applegreen"
            elif op_id == 5 or "chargepoint" in op_title:
                network = "ChargePoint"
            elif op_id == 3733 or "francis" in op_title:
                network = "Francis Energy"
            elif op_id in [15, 3252] or "evgo" in op_title:
                network = "EVgo"
                gm_perk = True

            # Max kW
            max_kw = 150.0
            for conn in item.get("Connections", []):
                p = conn.get("PowerKW")
                if p and p > max_kw:
                    max_kw = float(p)

            # AUTOMATIC PRICE DISCOVERY:
            verified_price: Optional[float] = None
            source_url = addr.get("RelatedURL") or f"https://openchargemap.org/site/poi/details/{item.get('ID')}"

            # 1. Match against IONNA scraped stations
            if network == "IONNA":
                for it in ionna_tariffs:
                    if haversine_miles(it.latitude, it.longitude, lat, lon) < 1.0:
                        verified_price = it.rate_on_peak
                        source_url = it.plugshare_url
                        break

            # 2. Match against Mercedes-Benz HPC scraped stations
            elif network == "Mercedes-Benz":
                for mb in mercedes_tariffs:
                    if haversine_miles(mb.latitude, mb.longitude, lat, lon) < 1.0:
                        verified_price = mb.rate_on_peak
                        source_url = mb.plugshare_url
                        break

            # 3. Match against ChargePoint live API
            elif network == "ChargePoint":
                try:
                    cp_results = await self.chargepoint_adapter.fetch_prices_for_bounding_box(
                        lat - 0.05, lon - 0.05, lat + 0.05, lon + 0.05
                    )
                    for cp in cp_results:
                        if haversine_miles(cp.latitude, cp.longitude, lat, lon) < 0.5:
                            verified_price = cp.rate_on_peak
                            source_url = cp.plugshare_url
                            break
                except Exception as cpe:
                    logger.debug(f"CP live lookup failed: {cpe}")

            # 4. Match against DCFC Tracker records (EA, Applegreen, EVgo, Francis)
            if verified_price is None and dcfc_records:
                city_clean = (addr.get("Town") or "").strip().lower()
                title_clean = (addr.get("Title") or "").strip().lower()
                for rec in dcfc_records:
                    if network.lower() in rec["network"].lower() or rec["network"].lower() in network.lower():
                        # Match city or title in DCFC record name/address
                        if city_clean and (city_clean in rec["name"].lower() or city_clean in rec["address"].lower()):
                            verified_price = rec["price"]
                            source_url = rec["url"]
                            break

            st_id = f"{network.lower().replace(' ', '-')}-{addr.get('ID', item.get('ID'))}"

            # If no price verified, DO NOT assign dummy 50c! Keep as None and flag unverified.
            is_verified = (verified_price is not None)
            rate_val = verified_price if is_verified else None

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
                    "off_peak": rate_val,
                    "on_peak": rate_val
                },
                "gm_discount_eligible": gm_perk,
                "gm_discount_pct": 0.10 if gm_perk else 0.0,
                "ea_pass_eligible": ea_pass,
                "membership_rate": {
                    "off_peak": round(rate_val * 0.75, 2) if (is_verified and ea_pass) else rate_val,
                    "on_peak": round(rate_val * 0.75, 2) if (is_verified and ea_pass) else rate_val
                },
                "session_fee": 0.0,
                "plugshare_url": source_url,
                "price_verified": is_verified,
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
        Refreshes pricing across all stations using live CPO adapters and DCFC Tracker.
        """
        existing = self.load_existing_stations()

        # 1. Fetch live IONNA tariffs
        ionna_tariffs = await self.ionna_adapter.fetch_prices_for_bounding_box(37.0, -85.0, 42.5, -73.5)
        for it in ionna_tariffs:
            for ex in existing.values():
                if ex.get("network") == "IONNA":
                    if haversine_miles(it.latitude, it.longitude, ex["latitude"], ex["longitude"]) < 1.0:
                        ex["rate_regular"]["off_peak"] = it.rate_off_peak
                        ex["rate_regular"]["on_peak"] = it.rate_on_peak
                        ex["price_verified"] = True
                        ex["plugshare_url"] = it.plugshare_url

        # 2. Fetch live Mercedes-Benz HPC tariffs
        mercedes_tariffs = await self.mercedes_adapter.fetch_prices_for_bounding_box(37.0, -85.0, 42.5, -73.5)
        for mb in mercedes_tariffs:
            for ex in existing.values():
                if ex.get("network") == "Mercedes-Benz":
                    if haversine_miles(mb.latitude, mb.longitude, ex["latitude"], ex["longitude"]) < 1.0:
                        ex["rate_regular"]["off_peak"] = mb.rate_off_peak
                        ex["rate_regular"]["on_peak"] = mb.rate_on_peak
                        ex["price_verified"] = True
                        ex["plugshare_url"] = mb.plugshare_url

        # 3. Fetch DCFC Tracker records
        dcfc_records = await self.dcfc_adapter.fetch_prices_for_states(["pa", "oh", "md", "nj", "wv"])
        for rec in dcfc_records:
            for ex in existing.values():
                if ex.get("network", "").lower() in rec["network"].lower():
                    city = (ex.get("city") or "").strip().lower()
                    if city and (city in rec["name"].lower() or city in rec["address"].lower()):
                        ex["rate_regular"]["off_peak"] = rec["price"]
                        ex["rate_regular"]["on_peak"] = rec["price"]
                        ex["price_verified"] = True
                        ex["plugshare_url"] = rec["url"]

        # 4. ChargePoint live queries for ChargePoint stations
        for ex in existing.values():
            if ex.get("network") == "ChargePoint" and not ex.get("price_verified"):
                try:
                    cp_list = await self.chargepoint_adapter.fetch_prices_for_bounding_box(
                        ex["latitude"] - 0.05, ex["longitude"] - 0.05,
                        ex["latitude"] + 0.05, ex["longitude"] + 0.05
                    )
                    for cp in cp_list:
                        if haversine_miles(cp.latitude, cp.longitude, ex["latitude"], ex["longitude"]) < 0.5:
                            ex["rate_regular"]["off_peak"] = cp.rate_off_peak
                            ex["rate_regular"]["on_peak"] = cp.rate_on_peak
                            ex["price_verified"] = True
                            ex["plugshare_url"] = cp.plugshare_url
                            break
                except Exception as e:
                    logger.debug(f"Failed to refresh CP station {ex['id']}: {e}")

        final_list = list(existing.values())
        with open(PRICES_JSON, "w", encoding="utf-8") as f:
            json.dump(final_list, f, indent=2)
        self._save_to_sqlite(final_list)
        logger.info(f"Refreshed pricing for {len(final_list)} stations.")
        return final_list

    def update_single_station_price(self, station_id: str, new_price: float) -> Optional[Dict[str, Any]]:
        existing = self.load_existing_stations()
        if station_id in existing:
            st = existing[station_id]
            st["rate_regular"]["off_peak"] = new_price
            st["rate_regular"]["on_peak"] = new_price
            st["price_verified"] = True
            if st.get("ea_pass_eligible"):
                st["membership_rate"]["off_peak"] = round(new_price * 0.75, 2)
                st["membership_rate"]["on_peak"] = round(new_price * 0.75, 2)
            elif st.get("gm_discount_eligible"):
                st["membership_rate"]["off_peak"] = round(new_price * 0.90, 2)
                st["membership_rate"]["on_peak"] = round(new_price * 0.90, 2)

            final_list = list(existing.values())
            with open(PRICES_JSON, "w", encoding="utf-8") as f:
                json.dump(final_list, f, indent=2)
            self._save_to_sqlite(final_list)
            return st
        return None
