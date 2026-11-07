import asyncio
import http.server
import json
import shutil
import subprocess
import threading
import time
import urllib.request
import websockets

PORT, CDP = 8793, 9293
USER_DATA_DIR = r"C:\temp\chrome_loading_bar_test"

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def test_loading_bar():
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

        assert ws_url, "Chrome CDP debugger url not found"

        async with websockets.connect(ws_url, max_size=None) as ws:
            mid = 0
            async def send(method, params=None):
                nonlocal mid; mid += 1
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

            # Wait for page to finish initial load
            await asyncio.sleep(3.0)

            # Wait for engine caches to finish loading if not ready
            engine_ready = await eval_js("""(async () => {
                if (window.ENGINE_READY_PROMISE) {
                    try { await window.ENGINE_READY_PROMISE; } catch(e){}
                }
                return !!window.isEngineReady;
            })()""")
            print("[INIT] Engine ready:", engine_ready)

            # Test 1: Verify header placement & initial state
            container_info = await eval_js("""(() => {
                const c = document.getElementById('calcProgressContainer');
                const btn = document.getElementById('searchBtn');
                if (!c || !btn) return null;
                const header = btn.closest('header');
                const isUnderHeader = header && header.contains(c);
                return {
                    exists: true,
                    isHidden: c.classList.contains('hidden'),
                    isUnderHeader: isUnderHeader,
                    btnHtml: btn.innerHTML,
                    hasSpinner: btn.innerHTML.includes('animate-spin')
                };
            })()""")
            print("[TEST 1] Initial header & container state:", container_info)
            assert container_info["exists"], "calcProgressContainer must exist in DOM"
            assert container_info["isUnderHeader"], "calcProgressContainer must be located inside the header"
            assert container_info["isHidden"], "calcProgressContainer must initially be hidden"
            assert not container_info["hasSpinner"], "searchBtn must not have a spinner initially"

            # Test 2: Unit test updateCalcProgress & hideCalcProgress
            unit_test_res = await eval_js("""(() => {
                const btn = document.getElementById('searchBtn');
                btn.disabled = true;
                updateCalcProgress(42, "Simulating State Tree Corridor 2/3...");
                const c = document.getElementById('calcProgressContainer');
                const bar = document.getElementById('calcProgressBar');
                const pct = document.getElementById('calcProgressPct');
                const label = document.getElementById('calcProgressStageLabel');
                return {
                    containerHidden: c.classList.contains('hidden'),
                    barWidth: bar.style.width,
                    pctText: pct.innerText,
                    labelText: label.innerText,
                    btnHtml: btn.innerHTML,
                    btnHasSpinner: btn.innerHTML.includes('animate-spin'),
                    btnHasCpu: btn.innerHTML.includes('data-lucide="cpu"') || btn.innerHTML.includes('Calculating (42%)')
                };
            })()""")
            print("[TEST 2] updateCalcProgress result:", unit_test_res)
            assert not unit_test_res["containerHidden"], "Container should be unhidden during update"
            assert unit_test_res["barWidth"] == "42%", f"Bar width should be 42%, got {unit_test_res['barWidth']}"
            assert unit_test_res["pctText"] == "42%", f"Pct text should be 42%, got {unit_test_res['pctText']}"
            assert "Corridor 2/3" in unit_test_res["labelText"], "Label text should match stage"
            assert not unit_test_res["btnHasSpinner"], "searchBtn should NOT have animate-spin spinner"
            assert unit_test_res["btnHasCpu"], "searchBtn should display Calculating (42%)"

            # Test 3: hideCalcProgress test
            await eval_js("hideCalcProgress(50);")
            await asyncio.sleep(0.15)
            hidden_after = await eval_js("document.getElementById('calcProgressContainer').classList.contains('hidden')")
            print("[TEST 3] Hidden after hideCalcProgress:", hidden_after)
            assert hidden_after, "calcProgressContainer should be hidden after hideCalcProgress delay"

            # Reset button state after unit test
            await eval_js("""(() => {
                const btn = document.getElementById('searchBtn');
                btn.disabled = false;
                btn.innerHTML = '<i data-lucide="search" class="w-4 h-4"></i><span>Calculate Route</span>';
            })()""")

            # Test 4: Full calculation integration run
            print("[TEST 4] Triggering real calculation run via clicking #searchBtn...")
            await eval_js("""(() => {
                document.getElementById('destAddress').value = 'Marlton, NJ';
                document.getElementById('optimizeDepartureTime').checked = false;
                document.getElementById('optimizeSpeedOffset').checked = false;
                document.getElementById('optimizeSpeedCap').checked = false;
                document.getElementById('searchBtn').click();
            })()""")

            observed_pcts = []
            observed_spinners = []
            observed_stages = []
            done = False
            for step in range(300): # up to 60s (sampling every 0.2s)
                sample = await eval_js("""(() => {
                    const c = document.getElementById('calcProgressContainer');
                    const bar = document.getElementById('calcProgressBar');
                    const pct = document.getElementById('calcProgressPct');
                    const label = document.getElementById('calcProgressStageLabel');
                    const btn = document.getElementById('searchBtn');
                    const st = document.getElementById('auditStatusText')?.innerText;
                    return {
                        hidden: c ? c.classList.contains('hidden') : true,
                        pctText: pct ? pct.innerText : null,
                        barWidth: bar ? bar.style.width : null,
                        stage: label ? label.innerText : null,
                        btnSpinner: btn ? btn.innerHTML.includes('animate-spin') : false,
                        btnText: btn ? btn.innerText.trim() : '',
                        auditStatus: st
                    };
                })()""")
                if sample["pctText"] and (not observed_pcts or sample["pctText"] != observed_pcts[-1]):
                    observed_pcts.append(sample["pctText"])
                    observed_stages.append(sample["stage"])
                    print(f"    [PROGRESS TICK] {sample['pctText']} - {sample['stage']} | Button: '{sample['btnText']}' (Spinner: {sample['btnSpinner']})")
                observed_spinners.append(sample["btnSpinner"])
                if sample["auditStatus"] in ("Optimization Complete", "No Routes Found"):
                    done = True
                    break
                await asyncio.sleep(0.2)

            print(f"[TEST 4] Observed progress samples ({len(observed_pcts)}): {observed_pcts}")
            assert done, "Calculation must reach Optimization Complete"
            assert not any(observed_spinners), "At NO POINT during calculation should searchBtn contain animate-spin!"
            assert len(observed_pcts) >= 2, f"Progress bar must transition through stages, got {observed_pcts}"

            # Verify final route state
            results_ready = await eval_js("""(() => {
                const res = (typeof calculatedResults !== 'undefined') ? calculatedResults : null;
                const btn = document.getElementById('searchBtn');
                return {
                    hasResults: !!(res && res.fastest_x),
                    btnDisabled: btn.disabled,
                    btnText: btn.innerText.trim(),
                    btnHasSpinner: btn.innerHTML.includes('animate-spin')
                };
            })()""")
            print("[TEST 4] Final calculation state:", results_ready)
            assert results_ready["hasResults"], "Calculation must have generated Pareto routes"
            assert not results_ready["btnDisabled"], "searchBtn must be re-enabled after calculation"
            assert "Calculate Route" in results_ready["btnText"], "searchBtn must restore to 'Calculate Route'"
            assert not results_ready["btnHasSpinner"], "searchBtn must not have a spinner"

            # Wait for fade timer (1500ms)
            await asyncio.sleep(1.8)
            final_hidden = await eval_js("document.getElementById('calcProgressContainer').classList.contains('hidden')")
            print("[TEST 4] Container hidden after completion:", final_hidden)
            assert final_hidden, "calcProgressContainer must smoothly hide after calculation finishes"

            print("\n>>> ALL DYNAMIC LOADING BAR TESTS PASSED 100%! <<<\n")

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(test_loading_bar())
