"""
Unified Automated Runner for Scheduled Daily TomTom Campaigns
Executes harvest -> integration -> testing -> git commit -> git push -> status log.
"""

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time

STATE_FILE = "data/scheduled_runs_state.json"
LOG_FILE = "data/scheduled_runs.log"

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_days": [1], "next_day": 2, "last_run": "2026-11-06T00:55:00"}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def run_cmd(cmd_list, desc="Command"):
    log(f"Running {desc}: {' '.join(cmd_list)}")
    res = subprocess.run(cmd_list, capture_output=True, text=True)
    if res.returncode != 0:
        log(f"ERROR running {desc}:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
        return False, res.stdout + res.stderr
    return True, res.stdout

def sync_html_files():
    log("Synchronizing tomtom_corridors_168h.json into index.html, public/index.html, and ui/templates/index.html...")
    with open("data/tomtom_corridors_168h.json", "r", encoding="utf-8") as f:
        tomtom_db = json.load(f)

    json_str = json.dumps(tomtom_db, indent=2)

    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()

    idx_start = content.find("const TOMTOM_CORRIDOR_SPEEDS =")
    if idx_start == -1:
        log("ERROR: const TOMTOM_CORRIDOR_SPEEDS not found in index.html")
        return False
    idx_eq = content.find("=", idx_start)
    idx_end = content.find("};\n", idx_start) + 1

    content = content[:idx_eq + 2] + json_str + content[idx_end:]

    files = ["index.html", "public/index.html", "ui/templates/index.html"]
    for p in files:
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    hashes = [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in files]
    if len(set(hashes)) != 1:
        log("ERROR: SHA-256 parity mismatch across HTML files!")
        return False
    log(f"HTML sync successful! Byte-parity verified: {hashes[0]}")
    return True

def run_day(day_num):
    log(f"=== STARTING AUTOMATED TOMTOM CAMPAIGN: DAY {day_num} ===")

    script_path = f"scripts/harvest_tomtom_day{day_num}.py"
    if not os.path.exists(script_path):
        log(f"ERROR: Harvester script {script_path} does not exist!")
        return False

    # 1. Run Harvester
    ok, out = run_cmd([sys.executable, script_path], f"Day {day_num} Harvester")
    if not ok:
        log(f"Day {day_num} Harvester failed!")
        return False
    log(f"Day {day_num} Harvester succeeded.")

    # 2. Sync to HTML files
    if not sync_html_files():
        return False

    # 3. Run JS Syntax verification
    ok, out = run_cmd([sys.executable, "tests/test_js_syntax.py"], "Chrome V8 Syntax Test")
    if not ok:
        log("JS Syntax test failed!")
        return False

    # 4. Run Full Simulation Suite
    ok, out = run_cmd([sys.executable, "tests/test_full_suite.py"], "Full Engine Test Suite")
    if not ok:
        log("Full test suite failed!")
        return False

    # 5. Run Sim History Test
    ok, out = run_cmd([sys.executable, "tests/test_sim_history.py"], "Simulation History Test")
    if not ok:
        log("Sim history test failed!")
        return False

    # 6. Git commit & push
    run_cmd(["git", "add", "data/tomtom_corridors_168h.json", "public/data/tomtom_corridors_168h.json", "index.html", "public/index.html", "ui/templates/index.html", STATE_FILE, LOG_FILE], "Git Add")
    commit_msg = f"feat: automated TomTom Day {day_num} harvest and integration (100% test verified)"
    run_cmd(["git", "commit", "-m", commit_msg], "Git Commit")
    ok, out = run_cmd(["git", "push", "origin", "main"], "Git Push")
    if ok:
        log(f"Successfully pushed Day {day_num} deployment to origin/main.")
    else:
        log("WARNING: Git push encountered an issue, will retry next run.")

    # 7. Update state
    state = load_state()
    if day_num not in state.get("completed_days", []):
        state.setdefault("completed_days", []).append(day_num)
    state["next_day"] = day_num + 1 if day_num < 5 else 6
    state["last_run"] = datetime.datetime.now().isoformat()
    save_state(state)

    log(f"=== COMPLETED AUTOMATED TOMTOM CAMPAIGN: DAY {day_num} ===\n")
    return True

def main():
    parser = argparse.ArgumentParser(description="Run scheduled TomTom harvest & integration")
    parser.add_argument("--day", type=int, default=0, help="Day number (2..5). If 0, auto-detects next day.")
    args = parser.parse_args()

    state = load_state()
    day_to_run = args.day if args.day > 0 else state.get("next_day", 2)

    if day_to_run > 5:
        log("All 5 days of TomTom campaigns have already completed!")
        print("All 5 days completed.")
        return

    run_day(day_to_run)

if __name__ == "__main__":
    main()
