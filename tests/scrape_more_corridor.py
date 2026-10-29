import asyncio
import json
import subprocess
import time
import urllib.request
import websockets

CDP_PORT = 9292
USER_DATA_DIR = r"C:\temp\chrome_corridor_scrapers"

SLUGS_TO_SCRAPE = [
    "33951", # Summerdale, PA (near Harrisburg / Dillsburg)
    "19516", # Medford, NJ (right next to Marlton)
    "402407", # Lawnside, NJ (I-295 outside Philly / Marlton, 32 stalls)
    "20506", # Pittsburgh, PA - Freeport Rd
    "401410", # Waynesburg, PA (I-79)
    "33688", # Timonium, MD (I-83 / north of Baltimore)
    "424861", # Hamilton Township, NJ
    "35027", # Aston, PA (I-95 / US-322)
    "59145", # Bellmawr, NJ
    "36287", # Shrewsbury, PA (I-83)
]

async def scrape():
    proc = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank"
    ])
    try:
        ws_url = None
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json") as resp:
                    tabs = json.loads(resp.read().decode())
                    for tab in tabs:
                        if tab.get("type") == "page":
                            ws_url = tab["webSocketDebuggerUrl"]
                            break
                    if ws_url:
                        break
            except Exception:
                time.sleep(0.2)

        async with websockets.connect(ws_url, max_size=None) as ws:
            mid = 0
            async def send(method, params=None):
                nonlocal mid
                mid += 1
                await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
                return mid

            await send("Page.enable")
            results = {}

            for slug in SLUGS_TO_SCRAPE:
                url = f"https://www.tesla.com/findus/location/supercharger/{slug}"
                await send("Page.navigate", {"url": url})
                await asyncio.sleep(2.5)

                id_eval = await send("Runtime.evaluate", {
                    "expression": """
                    (() => {
                        const script = document.getElementById('__NEXT_DATA__');
                        if (!script) return JSON.stringify({error: 'no script', url: window.location.href});
                        try {
                            const data = JSON.parse(script.innerText);
                            const props = data.props && data.props.pageProps ? data.props.pageProps : {};
                            const fd = props.formattedData || {};
                            const details = fd.chargerDetails || {};
                            const notice = fd.additionalNotice || {};
                            return JSON.stringify({
                                name: details.name,
                                address: details.address,
                                maxPowerKw: details.maxPowerKw,
                                openToNonTeslas: details.openToNonTeslas,
                                noticeChip: notice.chipLabel,
                                effectivePricebooks: details.effectivePricebooks || [],
                                chargerPricing: fd.chargerPricing || [],
                                chargerHistogramData: fd.chargerHistogramData || []
                            });
                        } catch(e) {
                            return JSON.stringify({error: e.message});
                        }
                    })()
                    """
                })

                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == id_eval:
                        res = msg.get("result", {}).get("result", {}).get("value", "{}")
                        try:
                            parsed = json.loads(res)
                            results[slug] = parsed
                            print(f"\n=== {slug}: {parsed.get('name')} ===")
                            print("Notice Chip:", parsed.get("noticeChip"))
                            tou = [pb for pb in parsed.get("effectivePricebooks", []) if pb.get("isTou")]
                            print(f"TOU pricebooks count: {len(tou)}")
                            if tou:
                                for pb in tou:
                                    print(f"  TOU: make={pb.get('vehicleMakeType')} member={pb.get('isMemberPricebook')} start={pb.get('startTime')} end={pb.get('endTime')} rate={pb.get('rateBase')}")
                            else:
                                for pb in parsed.get("effectivePricebooks", []):
                                    if pb.get("feeType") == "CHARGING":
                                        print(f"  Flat/Congestion: make={pb.get('vehicleMakeType')} member={pb.get('isMemberPricebook')} rate={pb.get('rateBase')} occ={pb.get('minSiteOccupancy')}-{pb.get('maxSiteOccupancy')}")
                        except Exception as e:
                            print(f"Error parsing {slug}: {e}")
                        break

            with open("tests/scraped_corridor_tesla.json", "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(scrape())
