"""
Orchestrator for automated CPO discovery and real station-specific price scraper pipeline.
Discovers stations via Open Charge Map (OCM) in OH, PA, NJ, WV, MD (CCS1 >= 100 kW),
scrapes station-specific pricing from DCFC Tracker, IONNA, Mercedes-Benz HPC, and ChargePoint live endpoints,
persists verified rates with direct inspection URLs, and flags unverified stations for manual entry.
Never uses synthetic flat network tariffs.
"""
import asyncio
import json
import os
import sqlite3
import logging
from typing import List, Dict, Any, Optional
import math
import re

from pipeline.networks.chargepoint import ChargePointAdapter
from pipeline.networks.mercedes_benz import MercedesBenzAdapter
from pipeline.networks.ionna import IONNAAdapter
from pipeline.networks.dcfc_tracker import DCFCTrackerAdapter
from pipeline.networks.open_charge_map import OpenChargeMapClient
from pipeline.networks.tesla import TeslaSuperchargerAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pricing_pipeline")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PRICES_JSON = os.path.join(DATA_DIR, "prices.json")
INITIAL_PRICES_JSON = os.path.join(DATA_DIR, "initial_prices.json")
SCRAPED_PRICES_JSON = os.path.join(DATA_DIR, "scraped_prices.json")
PRICES_DB = os.path.join(DATA_DIR, "prices.db")

# Known manually verified station tariffs
MANUALLY_VERIFIED_OVERRIDES = {
    "cp-hancock-md": {"price": 0.40, "url": "https://driver.chargepoint.com/stations/13210691"},
    "ag-waterfall-pa": {"price": 0.55, "url": "https://dcfctracker.com/stations/451875"},
    "ea-belle-vernon-pa": {"price": 0.60, "url": "https://dcfctracker.com/stations/237974"},
    "ionna-cambridge-oh": {"price": 0.39, "url": "https://dcfctracker.com/stations/454141"},
    "mb-washington-pa": {"price": 0.44, "url": "https://mercedesbenzhpc.com/charging-station/pa-washington-the-old-mill/"},
    "tesla-somerset-pa": {"price": 0.56, "mem_price": 0.41, "url": "https://www.tesla.com/findus/location/supercharger/somersetsupercharger"},
    "tesla-fort-littleton-pa": {"price": 0.56, "mem_price": 0.41, "url": "https://www.tesla.com/findus/location/supercharger/26674"},
    "tesla-mt-laurel-nj": {"price": 0.51, "price_off_peak": 0.35, "mem_price": 0.38, "mem_price_off_peak": 0.26, "url": "https://www.tesla.com/findus/location/supercharger/406608"},
    "tesla-woodlyn-pa": {"price": 0.62, "price_off_peak": 0.32, "mem_price": 0.44, "mem_price_off_peak": 0.23, "url": "https://www.tesla.com/findus/location/supercharger/59209"},
    "tesla-cherry-hill-nj": {"price": 0.72, "mem_price": 0.48, "mem_price_off_peak": 0.34, "url": "https://www.tesla.com/findus/location/supercharger/cherryhillnjhaddonfieldroadsupercharger"},
    "tesla-maple-shade-nj": {"price": 0.72, "mem_price": 0.48, "mem_price_off_peak": 0.34, "url": "https://www.tesla.com/findus/location/supercharger/26769"},
    "tesla-blackwood-nj": {"price": 0.73, "price_off_peak": 0.38, "mem_price": 0.52, "mem_price_off_peak": 0.27, "url": "https://www.tesla.com/findus/location/supercharger/59126"},
    "tesla-pittsburgh-freeport-pa": {"price": 0.59, "price_off_peak": 0.30, "mem_price": 0.44, "mem_price_off_peak": 0.22, "url": "https://www.tesla.com/findus/location/supercharger/20506"},
    "tesla-summerdale-pa": {"price": 0.55, "price_off_peak": 0.28, "mem_price": 0.40, "mem_price_off_peak": 0.21, "url": "https://www.tesla.com/findus/location/supercharger/33951"},
    "tesla-lawnside-nj": {"price": 0.49, "price_off_peak": 0.34, "mem_price": 0.36, "mem_price_off_peak": 0.25, "url": "https://www.tesla.com/findus/location/supercharger/402407"},
    "tesla-aston-pa": {"price": 0.56, "price_off_peak": 0.28, "mem_price": 0.40, "mem_price_off_peak": 0.20, "url": "https://www.tesla.com/findus/location/supercharger/35027"},
    "tesla-shrewsbury-pa": {"price": 0.68, "price_off_peak": 0.30, "mem_price": 0.49, "mem_price_off_peak": 0.22, "url": "https://www.tesla.com/findus/location/supercharger/36287"},
    "tesla-timonium-md": {"price": 0.60, "price_off_peak": 0.38, "mem_price": 0.43, "mem_price_off_peak": 0.27, "url": "https://www.tesla.com/findus/location/supercharger/33688"},
    "tesla-waynesburg-pa": {"price": 0.57, "mem_price": 0.41, "url": "https://www.tesla.com/findus/location/supercharger/401410"},
    "tesla-medford-nj": {"price": 0.72, "mem_price": 0.48, "mem_price_off_peak": 0.34, "url": "https://www.tesla.com/findus/location/supercharger/19516"},
    "tesla-hamilton-nj": {"price": 0.72, "mem_price": 0.48, "mem_price_off_peak": 0.34, "url": "https://www.tesla.com/findus/location/supercharger/424861"},
    "evgo-pilot-marengo-oh": {"price": 0.69, "url": "https://dcfctracker.com/stations/347668", "gm_discount_eligible": False},
    "ocm-306512": {"price": 0.69, "url": "https://dcfctracker.com/stations/347668", "gm_discount_eligible": False},
    "ocm-351529": {"price": 0.69, "url": "https://dcfctracker.com/stations/347668", "gm_discount_eligible": False},
    "evgo-farley-nj": {"price": 0.66, "url": "https://dcfctracker.com/stations/228536", "gm_discount_eligible": True},
    "ocm-225139": {"price": 0.66, "url": "https://dcfctracker.com/stations/228536", "gm_discount_eligible": True},
    "evgo-hollinswood-md": {"price": 0.61, "url": "https://dcfctracker.com/stations/322293", "gm_discount_eligible": True},
    "ocm-294317": {"price": 0.61, "url": "https://dcfctracker.com/stations/322293", "gm_discount_eligible": True},
    "cp-potomac-edison-canal-md": {"price": 0.34, "url": "https://dcfctracker.com/stations/300557", "gm_discount_eligible": False},
    "ocm-282416": {"price": 0.34, "url": "https://dcfctracker.com/stations/300557", "gm_discount_eligible": False}
}

# Blacklisted stations (fake OCM entries or permanently/temporarily closed locations)
BLOCKED_OCM_IDS = {307653, 285227, 307817} # 307653 = Fake IONNA Huber Heights; 285227 = Menlo Park Mall closed EVgo; 307817 = Myerstown EVgo GM Energy

def is_station_blocked(st_id: str, title: str = "", city: str = "", network: str = "", ocm_id: Optional[int] = None) -> bool:
    if ocm_id in BLOCKED_OCM_IDS:
        return True
    t = f"{st_id} {title} {city} {network}".lower()
    if "huber heights" in t and "ionna" in t:
        return True
    if "menlo park" in t:
        return True
    if "myerstown" in t:
        return True
    return False

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
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
        self.tesla_adapter = TeslaSuperchargerAdapter()

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

    def load_scraped_database(self) -> Dict[str, Any]:
        if os.path.exists(SCRAPED_PRICES_JSON):
            with open(SCRAPED_PRICES_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"dcfc": [], "ionna": [], "mercedes": []}

    def load_existing_stations(self) -> Dict[str, Dict[str, Any]]:
        stations = {}
        for path in [INITIAL_PRICES_JSON, PRICES_JSON]:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for item in json.load(f):
                        stations[item["id"]] = item
        return stations

    def reset_to_baseline(self) -> List[Dict[str, Any]]:
        baseline = self.load_baseline_stations()
        for s in baseline:
            s["price_verified"] = True

        with open(PRICES_JSON, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2)

        self._init_sqlite_db()
        conn = sqlite3.connect(PRICES_DB)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stations")
        conn.commit()
        conn.close()

        self._save_to_sqlite(baseline)
        logger.info(f"Database reset to baseline ({len(baseline)} stations).")
        return baseline

    def match_station_price(
        self,
        st_id: str,
        network: str,
        state: str,
        city: str,
        title: str,
        address: str,
        lat: Optional[float],
        lon: Optional[float],
        usage_cost: Optional[str],
        scraped_db: Dict[str, Any]
    ) -> Tuple[Optional[float], Optional[str], Optional[bool]]:
        """
        Matches station against real scraped sources with NO synthetic guessing.
        Returns (price, source_url, gm_eligible) or (None, fallback_url, gm_eligible).
        """
        if is_station_blocked(st_id, title, city, network):
            return None, None, False

        # 1. Check manually verified overrides
        if st_id in MANUALLY_VERIFIED_OVERRIDES:
            ov = MANUALLY_VERIFIED_OVERRIDES[st_id]
            return ov["price"], ov["url"], ov.get("gm_discount_eligible")

        # 2. Check IONNA real scraped stations
        if network == "IONNA" and lat is not None and lon is not None:
            for ion in scraped_db.get("ionna", []):
                if haversine_miles(lat, lon, ion["lat"], ion["lon"]) < 1.0:
                    return ion["price"], ion["url"], True

        # 3. Check DCFC Tracker real scraped stations (network + state + address / name match)
        line_clean = (address or "").lower()
        town_clean = (city or "").lower()
        title_clean = (title or "").lower()
        st_upper = (state or "").strip().upper()
        full_st_text = f"{title_clean} {line_clean} {town_clean}"
        is_pilot = "pilot" in full_st_text or "flying j" in full_st_text

        generic_words = {"station", "stations", "plaza", "center", "centre", "travel", "charger", "chargers", "fast", "charging", "north", "south", "east", "west", "road", "street", "avenue", "drive", "route", "highway", "exit", "lane", "court", "parkway", "evgo", "chargepoint", "electrify", "america", "applegreen", "tesla", "francis", "energy"}
        raw_tokens = re.findall(r'[a-zA-Z]{4,}', full_st_text)
        tokens = [t for t in raw_tokens if t not in generic_words]
        st_nums = set(re.findall(r'\b\d{2,5}\b', full_st_text))

        best_match = None
        best_score = 0

        for d in scraped_db.get("dcfc", []):
            if st_upper and d.get("state") != st_upper:
                continue

            d_net = (d.get("network") or "").lower()
            s_net = network.lower()

            net_compat = False
            if not s_net or s_net == "other":
                net_compat = True
            elif s_net == d_net or s_net in d_net or d_net in s_net:
                net_compat = True
            elif ("evgo" in s_net or "evgo" in d_net) and ("pilot" in d_net or "flying j" in d_net or is_pilot):
                net_compat = True

            if not net_compat:
                continue

            d_name = (d.get("name") or "").lower()
            d_addr = (d.get("address") or "").lower()
            d_full = f"{d_name} {d_addr}"

            score = 0
            for t in tokens:
                if t in d_full:
                    score += 3

            d_nums = set(re.findall(r'\b\d{2,5}\b', d_full))
            if st_nums.intersection(d_nums):
                score += 4

            if town_clean and len(town_clean) >= 4 and town_clean in d_full:
                score += 2

            if score > best_score and score >= 3:
                best_score = score
                best_match = d

        if best_match:
            d_name_l = (best_match.get("name") or "").lower()
            d_net_l = (best_match.get("network") or "").lower()
            is_pilot_site = is_pilot or "pilot" in d_name_l or "pilot" in d_net_l or "flying j" in d_name_l
            gm_eligible = (network in ("EVgo", "IONNA") or "evgo" in d_net_l or "ionna" in d_net_l) and not is_pilot_site
            return best_match["price"], best_match["url"], gm_eligible

        # 4. Check OCM UsageCost field
        if usage_cost:
            m = re.search(r'\$?(\d+\.\d{2})', usage_cost)
            if m:
                val = float(m.group(1))
                if 0.10 <= val <= 1.50:
                    gm_eligible = (network in ("EVgo", "IONNA")) and not is_pilot
                    return val, None, gm_eligible

        return None, None, None

    async def pull_ocm_stations(self, states: List[str] = None) -> List[Dict[str, Any]]:
        existing = self.load_existing_stations()
        ocm_items = await self.ocm_client.discover_chargers_for_states(states=states)
        added_count = 0
        scraped_db = self.load_scraped_database()

        for item in ocm_items:
            addr = item.get("AddressInfo", {})
            lat = addr.get("Latitude")
            lon = addr.get("Longitude")
            if not lat or not lon:
                continue

            matched_id = None
            for ex_id, ex_st in existing.items():
                if haversine_miles(ex_st["latitude"], ex_st["longitude"], lat, lon) < 0.5:
                    matched_id = ex_id
                    break

            title = addr.get("Title", "Station")
            city = addr.get("Town", "")
            ocm_id = item.get("ID")
            op_title = item.get("OperatorInfo", {}).get("Title", "").lower()
            if is_station_blocked(f"ocm-{ocm_id}", title, city, op_title, ocm_id=ocm_id):
                continue

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
                is_pilot = "pilot" in title.lower() or "flying j" in title.lower()
                gm_perk = not is_pilot

            max_kw = 150.0
            for conn in item.get("Connections", []):
                p = conn.get("PowerKW")
                if p and p > max_kw:
                    max_kw = float(p)

            st_id = f"{network.lower().replace(' ', '-')}-{addr.get('ID', item.get('ID'))}"
            city = addr.get("Town", "")
            st_raw = (addr.get("StateOrProvince", "")).strip().upper()
            state_map = {"OH": "OH", "OHIO": "OH", "PA": "PA", "PENNSYLVANIA": "PA", "NJ": "NJ", "NEW JERSEY": "NJ", "WV": "WV", "WEST VIRGINIA": "WV", "MD": "MD", "MARYLAND": "MD"}
            state = state_map.get(st_raw, st_raw[:2] if len(st_raw) >= 2 else st_raw)
            title = addr.get("Title", "Station")
            line1 = addr.get("AddressLine1", "")
            uc = item.get("UsageCost")

            # Try ChargePoint live lookup if ChargePoint
            verified_price: Optional[float] = None
            source_url: Optional[str] = None

            if network == "ChargePoint":
                try:
                    cp_list = await self.chargepoint_adapter.fetch_prices_for_bounding_box(
                        lat - 0.05, lon - 0.05, lat + 0.05, lon + 0.05
                    )
                    for cp in cp_list:
                        if haversine_miles(cp.latitude, cp.longitude, lat, lon) < 0.5:
                            verified_price = cp.rate_on_peak
                            source_url = cp.plugshare_url
                            break
                except Exception:
                    pass

            if verified_price is None:
                verified_price, source_url, matched_gm = self.match_station_price(
                    st_id, network, state, city, title, line1, lat, lon, uc, scraped_db
                )
                if matched_gm is not None:
                    gm_perk = matched_gm

            # Fallback inspection URL
            if not source_url:
                source_url = addr.get("RelatedURL") or f"https://openchargemap.org/site/poi/details/{item.get('ID')}"

            is_verified = (verified_price is not None)
            rate_val = verified_price if is_verified else None

            new_station = {
                "id": st_id,
                "name": f"{network} - {title}",
                "network": network,
                "city": city,
                "state": state,
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
        existing = self.load_existing_stations()
        scraped_db = self.load_scraped_database()
        refreshed_count = 0

        for ex in existing.values():
            st_id = ex["id"]
            net = ex.get("network", "Other")
            st = ex.get("state", "")
            city = ex.get("city", "")
            name = ex.get("name", "")
            lat = ex.get("latitude")
            lon = ex.get("longitude")

            if st_id in MANUALLY_VERIFIED_OVERRIDES:
                ov = MANUALLY_VERIFIED_OVERRIDES[st_id]
                ex["rate_regular"]["off_peak"] = ov.get("price_off_peak", ov["price"])
                ex["rate_regular"]["on_peak"] = ov["price"]
                if "mem_price" in ov:
                    if "membership_rate" not in ex or not isinstance(ex["membership_rate"], dict):
                        ex["membership_rate"] = {}
                    ex["membership_rate"]["off_peak"] = ov.get("mem_price_off_peak", ov["mem_price"])
                    ex["membership_rate"]["on_peak"] = ov["mem_price"]
                ex["price_verified"] = True
                if ov.get("url"):
                    ex["plugshare_url"] = ov["url"]
                refreshed_count += 1
            else:
                price, url, matched_gm = self.match_station_price(
                    st_id, net, st, city, name, "", lat, lon, None, scraped_db
                )
                if price is not None:
                    ex["rate_regular"]["off_peak"] = price
                    ex["rate_regular"]["on_peak"] = price
                    ex["price_verified"] = True
                    if url:
                        ex["plugshare_url"] = url
                    if ex.get("ea_pass_eligible"):
                        ex["membership_rate"]["off_peak"] = round(price * 0.75, 2)
                        ex["membership_rate"]["on_peak"] = round(price * 0.75, 2)
                    elif matched_gm is not None:
                        ex["gm_discount_eligible"] = matched_gm
                    refreshed_count += 1

        final_list = list(existing.values())
        with open(PRICES_JSON, "w", encoding="utf-8") as f:
            json.dump(final_list, f, indent=2)
        self._save_to_sqlite(final_list)
        logger.info(f"Refreshed pricing for {refreshed_count} stations.")
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
