import asyncio
import http.server
import json
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets

PORT, CDP = 8799, 9298
USER_DATA_DIR = r"C:\temp\chrome_decamilla_e2e"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def test_decamilla_flow():
    run_server()
    shutil.rmtree(USER_DATA_DIR, ignore_errors=True)

    proc = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        f"--remote-debugging-port={CDP}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--disable-gpu",
        "--no-first-run",
        f"http://127.0.0.1:{PORT}/index.html"
    ])

    try:
        ws_url = None
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP}/json").read())
                ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page"), None)
                if ws_url: break
            except Exception:
                time.sleep(0.1)

        async with websockets.connect(ws_url, max_size=None) as ws:
            mid = 0
            async def send(method, params=None):
                nonlocal mid
                mid += 1
                await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
                return mid

            async def call(method, params=None):
                req_id = await send(method, params)
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == req_id:
                        return msg.get("result", {})

            async def eval_js(expr):
                res = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
                return res.get("result", {}).get("value")

            await asyncio.sleep(2.5)

            # 1. Verify decamillaOptionBox is visible on default Marlton destination
            box_hidden = await eval_js("document.getElementById('decamillaOptionBox').classList.contains('hidden')")
            print(f"DeCamilla box hidden on default Marlton: {box_hidden} (expected False)")
            assert not box_hidden, "decamillaOptionBox should be visible for Marlton"

            # 2. Select 2.0 hr stop at DeCamilla
            await eval_js("""(() => {
                const sel = document.getElementById('decamillaStopDuration');
                sel.value = "2.0";
                handleDecamillaStopChange();
            })()""")

            # 3. Wait for optimization to complete
            for _ in range(120):
                await asyncio.sleep(0.5)
                status = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if status in ("Optimization Complete", "No Routes Found"):
                    print(f"Status: {status}")
                    break

            # 4. Check calculated results
            res = await eval_js("""(() => {
                if (typeof calculatedResults === 'undefined' || !calculatedResults) return null;
                const r = calculatedResults;
                const f = r.fastest;
                const c = r.cheapest;
                const b = r.balanced;
                const ns = r.nonStop;
                return {
                    fastest: {
                        total_hours: f.total_hours,
                        total_cost: f.total_cost,
                        stops: f.stops.map(s => ({
                            name: s.station.name,
                            arr_soc: s.arr_soc,
                            tgt_soc: s.tgt_soc,
                            mins: s.mins,
                            cost: s.cost,
                            is_decamilla: !!s.is_decamilla,
                            mile: s.mile
                        }))
                    },
                    cheapest: {
                        total_hours: c.total_hours,
                        total_cost: c.total_cost,
                        stops: c.stops.map(s => ({
                            name: s.station.name,
                            arr_soc: s.arr_soc,
                            tgt_soc: s.tgt_soc,
                            mins: s.mins,
                            cost: s.cost,
                            is_decamilla: !!s.is_decamilla
                        }))
                    },
                    balanced: {
                        total_hours: b.total_hours,
                        total_cost: b.total_cost,
                        stops: b.stops.map(s => ({
                            name: s.station.name,
                            arr_soc: s.arr_soc,
                            tgt_soc: s.tgt_soc,
                            mins: s.mins,
                            cost: s.cost,
                            is_decamilla: !!s.is_decamilla
                        }))
                    },
                    nonStop: {
                        hours: ns.hours,
                        pure_driving_hours: ns.pure_driving_hours,
                        decamilla_stop_hours: ns.decamilla_stop_hours,
                        distance: ns.distance
                    },
                    nonStopSpeedText: document.getElementById('nonStopSpeed')?.innerText
                };
            })()""")

            print("\n=== RESULTS WITH 2.0 HR DECAMILLA STOP ===")
            print(json.dumps(res, indent=2))

            # Validations
            assert res is not None, "Calculated results should not be null"
            ns = res["nonStop"]
            assert ns["decamilla_stop_hours"] == 2.0, "Non-stop baseline should include 2.0 hr DeCamilla stop"
            assert "+2h stop" in res["nonStopSpeedText"], f"Expected '+2h stop' in nonStopSpeedText, got: {res['nonStopSpeedText']}"

            for key in ["fastest", "cheapest", "balanced"]:
                itin = res[key]
                decamilla_stops = [s for s in itin["stops"] if s["is_decamilla"]]
                assert len(decamilla_stops) == 1, f"{key} route should have exactly 1 DeCamilla stop"
                ds = decamilla_stops[0]
                assert ds["cost"] == 0.0, f"{key} DeCamilla stop should be free ($0.00)"
                assert ds["mins"] == 120, f"{key} DeCamilla stop should be 120 mins (2.0 hrs)"
                assert "DeCamilla" in ds["name"]

            # 5. Verify switching to Billings hides option box and resets duration
            await eval_js("setQuickDest('301 Beaver Rd, Sewickley, PA 15143')")
            hidden_billings = await eval_js("document.getElementById('decamillaOptionBox').classList.contains('hidden')")
            dur_billings = await eval_js("document.getElementById('decamillaStopDuration').value")
            assert hidden_billings, "DeCamilla option box should be hidden for Billings"
            assert dur_billings == "0", f"DeCamilla duration should reset to 0, got {dur_billings}"

            # 6. Verify switching back to Marlton reveals option box
            await eval_js("setQuickDest('270 Conestoga Dr, Marlton, NJ 08053')")
            hidden_marlton = await eval_js("document.getElementById('decamillaOptionBox').classList.contains('hidden')")
            assert not hidden_marlton, "DeCamilla option box should be visible for Marlton"

            print("\nALL VERIFICATIONS (INCLUDING DESTINATION SWITCHING) PASSED SUCCESSFULLY!")

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(test_decamilla_flow())
