import asyncio
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
import websockets

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

PORT = 8779
CDP_PORT = 9259
USER_DATA_DIR = r"C:\temp\chrome_quick_dest_test2"

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_http_server():
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd

async def run_test():
    if os.path.exists(USER_DATA_DIR):
        try: shutil.rmtree(USER_DATA_DIR)
        except Exception: pass

    proc = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"http://127.0.0.1:{PORT}/index.html"
    ])
    try:
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json") as resp:
                    tabs = json.loads(resp.read().decode())
                    for tab in tabs:
                        if tab.get("type") == "page":
                            ws_url = tab["webSocketDebuggerUrl"]
                            break
                    if ws_url: break
            except Exception: time.sleep(0.2)

        async with websockets.connect(ws_url) as ws:
            msg_id = 0
            async def eval_js(expr):
                nonlocal msg_id
                msg_id += 1
                await ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == msg_id:
                        if "exceptionDetails" in msg.get("result", {}):
                            print("JS Exception:", msg["result"]["exceptionDetails"])
                        return msg.get("result", {}).get("result", {}).get("value")

            await asyncio.sleep(2.0)

            # Destination 1: Marlton
            print("=== Testing Marlton, NJ (St. Onge) ===", flush=True)
            t0 = time.time()
            await eval_js("handleSearchRoute()")
            for _ in range(60):
                await asyncio.sleep(0.2)
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if st == 'Optimization Complete': break
            print(f"Marlton completed in {time.time()-t0:.2f}s", flush=True)
            fastest_time = await eval_js("document.getElementById('fastestTime')?.innerText")
            fastest_cost = await eval_js("document.getElementById('fastestCost')?.innerText")
            fastest_miles = await eval_js("document.getElementById('fastestMiles')?.innerText")
            nonstop_time = await eval_js("document.getElementById('nonStopDuration')?.innerText")
            audit_summary = await eval_js("document.getElementById('auditLogSummary')?.innerText")
            print(f"Marlton -> Non-stop: {nonstop_time}, Fastest: {fastest_time}, Cost: {fastest_cost}, Miles: {fastest_miles}", flush=True)
            print(f"Audit Summary:\n{audit_summary}", flush=True)

            # Destination 2: Sewickley
            print("\n=== Testing Sewickley, PA (Billings) ===", flush=True)
            t0 = time.time()
            await eval_js("setQuickDest('billings')")
            for _ in range(60):
                await asyncio.sleep(0.2)
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if st == 'Optimization Complete': break
            print(f"Sewickley completed in {time.time()-t0:.2f}s", flush=True)
            fastest_time = await eval_js("document.getElementById('fastestTime')?.innerText")
            fastest_cost = await eval_js("document.getElementById('fastestCost')?.innerText")
            fastest_miles = await eval_js("document.getElementById('fastestMiles')?.innerText")
            nonstop_time = await eval_js("document.getElementById('nonStopDuration')?.innerText")
            print(f"Sewickley -> Non-stop: {nonstop_time}, Fastest: {fastest_time}, Cost: {fastest_cost}, Miles: {fastest_miles}", flush=True)

            # Destination 3: Dillsburg
            print("\n=== Testing Dillsburg, PA (DeCamilla) ===", flush=True)
            t0 = time.time()
            await eval_js("setQuickDest('decamilla')")
            for _ in range(60):
                await asyncio.sleep(0.2)
                st = await eval_js("document.getElementById('auditStatusText')?.innerText")
                if st == 'Optimization Complete': break
            print(f"Dillsburg completed in {time.time()-t0:.2f}s", flush=True)
            fastest_time = await eval_js("document.getElementById('fastestTime')?.innerText")
            fastest_cost = await eval_js("document.getElementById('fastestCost')?.innerText")
            fastest_miles = await eval_js("document.getElementById('fastestMiles')?.innerText")
            nonstop_time = await eval_js("document.getElementById('nonStopDuration')?.innerText")
            print(f"Dillsburg -> Non-stop: {nonstop_time}, Fastest: {fastest_time}, Cost: {fastest_cost}, Miles: {fastest_miles}", flush=True)

    finally:
        proc.terminate()

if __name__ == "__main__":
    httpd = start_http_server()
    try:
        asyncio.run(run_test())
    finally:
        httpd.shutdown()
