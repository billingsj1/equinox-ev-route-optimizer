"""
DCFC Tracker live scraper adapter.
Scrapes real-world verified tariffs and locations across PA, OH, MD, NJ, WV
for Electrify America, Applegreen Fast Charge, EVgo, and Francis Energy.
"""
from typing import List, Dict, Any, Optional
import httpx
import re
import logging
from pipeline.networks.base import BaseNetworkAdapter, StationTariff

logger = logging.getLogger("dcfc_tracker_adapter")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}

class DCFCTrackerAdapter(BaseNetworkAdapter):
    network_name: str = "DCFC Tracker"

    async def fetch_prices_for_states(self, states: List[str] = None) -> List[Dict[str, Any]]:
        """
        Scrapes DCFC Tracker state pages (pa, oh, md, nj, wv) to retrieve
        station ID, network, name, address, and verified price $/kWh.
        """
        states = states or ["pa", "oh", "md", "nj", "wv"]
        records = []

        async with httpx.AsyncClient(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
            for st in states:
                url = f"https://dcfctracker.com/states/{st.lower()}"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    
                    html = resp.text
                    matches = re.findall(r'href="/stations/(\d+)"[^>]*>(.*?)</a>', html, re.DOTALL)
                    for sid, card in matches:
                        price_match = re.search(r'\$(\d+\.\d{2})/kWh', card)
                        if not price_match:
                            continue
                        
                        price = float(price_match.group(1))
                        net_match = re.search(r'rounded-full[^>]*>([^<]+)</span>', card)
                        name_match = re.search(r'font-medium text-foreground[^>]*>([^<]+)</p>', card)
                        addr_match = re.search(r'text-muted-foreground line-clamp-1[^>]*>([^<]+)</p>', card)
                        kw_match = re.search(r'(\d+)\s*kW', card)

                        network = net_match.group(1).strip() if net_match else "Other"
                        name = name_match.group(1).strip() if name_match else "DCFC Station"
                        addr = addr_match.group(1).strip() if addr_match else ""

                        # Never scrape IONNA from DCFC Tracker (approximate centroids & stale rates).
                        # IONNA is scraped directly via IONNAAdapter from ionna.com.
                        if network.upper() == "IONNA" or "IONNA" in name.upper() or "IONNA" in addr.upper():
                            continue

                        # Never scrape Tesla from DCFC Tracker (flat synthetic rates & missing TOU).
                        # Tesla Superchargers are scraped directly via TeslaSuperchargerAdapter with live TOU & Magic Dock.
                        if network.upper() == "TESLA" or "TESLA" in name.upper():
                            continue

                        power = float(kw_match.group(1)) if kw_match else 150.0

                        stalls_match = re.search(r'>Stalls</p>\s*<p[^>]*>(\d+)</p>', card) or re.search(r'(\d+)\s*(?:DC\s+fast\s+)?stalls', card, re.I)
                        stalls = int(stalls_match.group(1)) if stalls_match else 4

                        # Outlier rates (< $0.15 parking/valet fees or > $0.95 extreme fees)
                        # are flagged as unverified so user can inspect and verify manually.
                        is_outlier = (price < 0.15 or price > 0.95)
                        record_price = None if is_outlier else price
                        verified = not is_outlier

                        record = {
                            "dcfc_id": sid,
                            "network": network,
                            "name": name,
                            "address": addr,
                            "state": st.upper(),
                            "price": record_price,
                            "verified": verified,
                            "power_kw": power,
                            "stalls": stalls,
                            "url": f"https://dcfctracker.com/stations/{sid}"
                        }
                        if is_outlier:
                            record["raw_outlier_price"] = price

                        records.append(record)
                except Exception as e:
                    logger.warning(f"Error scraping DCFC Tracker for state {st}: {e}")

        logger.info(f"DCFCTrackerAdapter gathered {len(records)} priced stations across {states}.")
        return records

    async def fetch_station_coords(self, dcfc_id: str) -> Optional[tuple]:
        """
        Fetches latitude & longitude for a specific station page on DCFC Tracker.
        """
        url = f"https://dcfctracker.com/stations/{dcfc_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=HEADERS, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    coords = re.search(r'"latitude":\s*([-\d\.]+).*?"longitude":\s*([-\d\.]+)', resp.text)
                    if coords:
                        return float(coords.group(1)), float(coords.group(2))
        except Exception as e:
            logger.debug(f"Failed to fetch coords for DCFC {dcfc_id}: {e}")
        return None
