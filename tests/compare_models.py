"""Compare model variants (html files in repo root / tests/tmp) on the quick destinations.
Usage: python tests/compare_models.py file1.html [file2.html ...]
"""
import asyncio, http.server, json, os, shutil, socketserver, subprocess, sys, threading, time, urllib.request, websockets

sys.stdout.reconfigure(encoding='utf-8')
PORT, CDP = 8795, 9295
DESTS = [("marlton", "270 Conestoga Dr, Marlton, NJ 08053"), ("billings", "billings"), ("decamilla", "decamilla")]

class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

SUMMARY_JS = """JSON.stringify(['fastest','cheapest','balanced'].map(k => {
  const r = calculatedResults[k];
  return {k, h: Math.round(r.total_hours*60), cost: +r.total_cost.toFixed(2), n: r.stops.length,
    stops: r.stops.map(s => s.station.name.replace(/Tesla Supercharger \\(\\+CCS1\\) - /,'Tesla ').slice(0,22)+' '+s.arr_soc+'>'+s.tgt_soc)};
}))"""

async def run(page):
    ud = r"C:\temp\chrome_cmp_" + str(abs(hash(page)))
    shutil.rmtree(ud, ignore_errors=True)
    proc = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new",
        f"--remote-debugging-port={CDP}", f"--user-data-dir={ud}", "--disable-gpu", "--no-first-run",
        f"http://127.0.0.1:{PORT}/{page}"])
    try:
        ws_url = None
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP}/json").read())
                ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page"), None)
                if ws_url: break
            except Exception: pass
            time.sleep(0.2)
        async with websockets.connect(ws_url, max_size=None) as ws:
            mid = 0
            async def ev(expr):
                nonlocal mid; mid += 1
                await ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate", "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == mid: return m["result"].get("result", {}).get("value")
            await asyncio.sleep(2)
            print(f"\n##### {page}")
            for name, addr in DESTS:
                await ev("document.getElementById('auditStatusText').innerText='RESET'")
                await ev(f"document.getElementById('destAddress').value={json.dumps(addr)}")
                t0 = time.time(); await ev("handleSearchRoute()")
                for _ in range(300):
                    await asyncio.sleep(0.2)
                    if await ev("document.getElementById('auditStatusText').innerText") in ("Optimization Complete", "No Routes Found"): break
                el = time.time() - t0
                cnt = await ev("[auditSequencesCount,auditGeneratedCount,auditAnalyzedCount,auditOsrmCount].map(e=>e.innerText).join(' / ')")
                dest = await ev("activeRoutesData[0].destination.name")
                print(f"-- {name} ({dest}) {el:.1f}s  seq/soc/analyzed/osrm: {cnt}")
                for r in json.loads(await ev(SUMMARY_JS)):
                    print(f"   {r['k']:9s} {r['h']//60}h{r['h']%60:02d}m ${r['cost']:.2f} {r['n']} stops | " + ' | '.join(r['stops']))
    finally:
        proc.terminate()

if __name__ == "__main__":
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), Q)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    for p in sys.argv[1:]:
        asyncio.run(run(p))
    httpd.shutdown()
