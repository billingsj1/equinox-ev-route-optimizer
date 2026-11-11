"""
Full JavaScript Syntax and V8 Compilation Verification Test.
Extracts the inline JavaScript from index.html and compiles it directly
using Chrome's native V8 JavaScript engine via Chrome DevTools Protocol (CDP)
Runtime.compileScript. Catches any syntax errors, parsing issues, or malformed
tokens across all 11,000+ lines of application code.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import websockets

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

CDP_PORT = 9298
USER_DATA_DIR = r"C:\temp\chrome_js_syntax_test"


async def recv_response(ws, msg_id):
    """Skip CDP event notifications until the reply with the matching id arrives."""
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == msg_id:
            return msg


async def compile_script_v8(script_content: str, name: str = "inline.js"):
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
        "--disable-gpu",
        "about:blank"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ws_url = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json") as resp:
                targets = json.loads(resp.read().decode())
                if targets and len(targets) > 0:
                    ws_url = targets[0]["webSocketDebuggerUrl"]
                    break
        except Exception:
            time.sleep(0.1)

    if not ws_url:
        raise RuntimeError(f"Could not connect to Chrome CDP on port {CDP_PORT}")

    try:

        async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            await recv_response(ws, 1)

            compile_cmd = {
                "id": 2,
                "method": "Runtime.compileScript",
                "params": {
                    "expression": script_content,
                    "sourceURL": name,
                    "persistScript": False
                }
            }
            await ws.send(json.dumps(compile_cmd))
            res = await recv_response(ws, 2)

            result = res.get("result", {})
            exc = result.get("exceptionDetails")
            return exc
    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            chrome_proc.kill()
        try:
            shutil.rmtree(USER_DATA_DIR, ignore_errors=True)
        except Exception:
            pass


def test_index_html_javascript_syntax():
    index_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    pattern = re.compile(r'<script(?![^>]*src)[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
    scripts = pattern.findall(html)
    assert len(scripts) > 0, "No inline <script> tags found in index.html!"

    for i, s in enumerate(scripts):
        print(f"Compiling script block #{i+1} ({len(s)} chars, {s.count(chr(10))} lines) with Chrome V8...")
        exc = asyncio.run(compile_script_v8(s, f"inline_script_{i+1}.js"))
        if exc:
            line_no = exc.get("lineNumber")
            col_no = exc.get("columnNumber")
            text = exc.get("text")
            desc = exc.get("exception", {}).get("description")
            raise AssertionError(f"JavaScript Syntax Error in block #{i+1} at line {line_no}:{col_no}: {text} - {desc}")

    print("ALL JAVASCRIPT SYNTAX IN index.html VERIFIED 100% VALID BY CHROME V8!")


if __name__ == "__main__":
    test_index_html_javascript_syntax()
