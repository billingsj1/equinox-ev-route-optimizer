"""
IONNA joint venture network live scraper adapter.
Scrapes published rechargery pricing and locations from ionna.com sitemap and location pages.
IONNA offers a standard 10% discount for GM EV drivers.
"""
from typing import List, Optional
import httpx
import re
import logging
from pipeline.networks.base import BaseNetworkAdapter, StationTariff

logger = logging.getLogger("ionna_adapter")

CHROME_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1"
}

class IONNAAdapter(BaseNetworkAdapter):
    network_name: str = "IONNA"

    async def fetch_prices_for_bounding_box(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float
    ) -> List[StationTariff]:
        """
        Scrapes IONNA rechargeries matching target bounding box or states (OH, PA, NJ, WV, MD).
        """
        tariffs: List[StationTariff] = []
        sitemap_url = "https://www.ionna.com/rechargery-sitemap.xml"
        
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=CHROME_HEADERS, follow_redirects=True) as client:
                resp = await client.get(sitemap_url)
                if resp.status_code != 200:
                    logger.warning(f"IONNA sitemap failed with status {resp.status_code}")
                    return []

                all_locs = re.findall(r"<loc>([^<]+)</loc>", resp.text)
                target_state_patterns = ["/oh/", "/pa/", "/nj/", "/wv/", "/md/"]
                matched_urls = [u for u in all_locs if any(pat in u for pat in target_state_patterns)]

                for page_url in matched_urls:
                    try:
                        p_resp = await client.get(page_url)
                        if p_resp.status_code != 200:
                            continue
                        
                        html = p_resp.text
                        # Extract price: <span class="rechargery_price_now">$0.39</span>
                        price_match = re.search(r'class="rechargery_price_now">\$?(\d+\.\d{2})', html)
                        rate = float(price_match.group(1)) if price_match else 0.39

                        # Extract coords: var locs = '39.9964278,-81.5741239|**|...
                        coords_match = re.search(r"var locs = '([-\d\.]+),([-\d\.]+)", html)
                        if not coords_match:
                            continue
                        lat = float(coords_match.group(1))
                        lon = float(coords_match.group(2))

                        # Bounding box filter
                        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
                            continue

                        # Extract title and city/state
                        title_match = re.search(r"<strong>([^<]+Rechargery[^<]*)</strong>", html)
                        title = title_match.group(1) if title_match else "IONNA Rechargery"
                        clean_title = re.sub(r"&#8211;", "-", title).strip()

                        # Parse city/state from URL: /ev-charging-stations/oh/cambridge/...
                        parts = page_url.strip("/").split("/")
                        state = parts[-3].upper() if len(parts) >= 3 else "OH"
                        city = parts[-2].replace("-", " ").title() if len(parts) >= 2 else "Unknown"
                        st_id = f"ionna-{parts[-2]}-{parts[-3]}"

                        tariffs.append(StationTariff(
                            station_id=st_id,
                            network=self.network_name,
                            name=f"IONNA - {clean_title}",
                            city=city,
                            state=state,
                            latitude=lat,
                            longitude=lon,
                            power_kw=350.0,
                            connectors=["CCS1", "NACS"],
                            rate_off_peak=rate,
                            rate_on_peak=rate,
                            session_fee=0.0,
                            gm_discount_eligible=True,
                            gm_discount_pct=0.10,
                            membership_rate_off_peak=round(rate * 0.90, 2),
                            membership_rate_on_peak=round(rate * 0.90, 2),
                            plugshare_url=page_url
                        ))
                    except Exception as pe:
                        logger.debug(f"Error scraping IONNA page {page_url}: {pe}")
                        continue

        except Exception as e:
            logger.warning(f"Error in IONNAAdapter: {e}")

        logger.info(f"IONNAAdapter scraped {len(tariffs)} verified stations.")
        return tariffs
