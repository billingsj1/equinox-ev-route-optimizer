# AGENTS.md — Project Guide & Engineering Standards

Welcome to the **2025 Chevrolet Equinox EV Route Optimizer & Pricing Engine** repository. This document serves as the single source of truth for AI agents and human contributors to ensure continuity, architectural consistency, and quality across all development sessions.

---

## 1. System Overview & Technology Stack

The project is an EV route optimizer, physics simulation engine, and CPO pricing scraper custom-calibrated for the **2025 Chevrolet Equinox EV FWD (85.0 kWh usable battery pack)**. It evaluates multi-objective Pareto frontiers (Fastest, Cheapest, Balanced) considering road-load dynamics, elevation profiles, weather conditions, charging tapers, and turnpike tolls.

### Core Optimization Principles: Performance vs. Fidelity Hierarchy

When evaluating algorithms, route pruning, caching, or simulation performance, adhere strictly to this priority order:

1. **Ground-Truth Fidelity & Accuracy (Non-Negotiable Priority):**
   - Physics accuracy must never be sacrificed for runtime speed.
   - Calculations must preserve: realistic road-load dynamics (aero drag, rolling resistance, mass, elevation differentials), full Ultium battery charging taper profiles, ambient temperature/weather impacts, and exact toll/discount rates.
   - The optimizer must discover the TRUE Pareto frontier (Fastest, Cheapest, Balanced). Never introduce heuristics that risk pruning optimal stop combinations.

2. **Latency & Compute Optimization (Achieve Without Sacrificing Fidelity):**
   - Optimize via algorithmic efficiency: vectorized NumPy operations, early geometric pruning of unreachable stations/routes, and spatial polygon indexing.
   - Maximize precomputed offline caching: utilize and maintain precomputed corridor elevations, bottleneck speeds, and highway caches (`data/*.json`) for primary routes.
   - Never 'optimize' by lowering spatial sampling resolution, dropping weather/elevation vectors, or flattening the charging curve.

### Core Stack

| Layer | Technologies | Role / Notes |
|---|---|---|
| **Runtime** | Python 3.12+ (tested up to Python 3.14) | Core backend, physics engine, scraping pipelines |
| **Backend API** | FastAPI, Uvicorn, Pydantic v2 | High-performance ASGI REST API and data provider |
| **HTTP & Async** | HTTPX, AsyncIO, WebSockets | Asynchronous network scraping and CDP automation |
| **Numerical & Geo** | NumPy, Shapely, GeoPy | Geodesic math, polygon bounds, spatial station matching |
| **Data Persistence** | SQLite (`prices.db`), JSON data caches | Local relational store and precomputed highway caches |
| **Serverless Host** | Vercel ASGI (`vercel.json`, `api/index.py`) | Serverless deployment for web endpoints |
| **Frontend UI** | Standalone Single-Page Application (SPA) | Pure client-side execution capability (`index.html`) |
| **CSS Framework** | Tailwind CSS (CDN loaded) | Utility-first responsive dark slate theme |
| **Map & Visuals** | Leaflet.js (v1.9.4 CDN), Lucide Icons | Interactive route rendering, station markers, layers |
| **External APIs** | TomTom, HERE Maps, Google Maps / Elevation | Real-time speeds, historical traffic, elevations, tolls |

---

## 2. Package Manager & Environment Setup

The Python environment is managed using **`uv`** (preferred) or standard **`pip`**. The project does **not** use Node.js or `package.json`; frontend dependencies are loaded via CDNs directly in the HTML.

### Virtual Environment & Dependencies

```bash
# Create virtual environment with uv (recommended)
uv venv

# Activate on Windows (PowerShell / Command Prompt)
.venv\Scripts\activate

# Install project dependencies
uv pip install -r requirements.txt
# Alternatively: pip install -r requirements.txt
```

### Dependency Manifest (`requirements.txt`)

- `fastapi>=0.110.0`
- `uvicorn>=0.28.0`
- `pydantic>=2.0.0`
- `httpx>=0.27.0`
- `numpy>=1.26.0`
- `shapely>=2.0.0`
- `geopy>=2.4.0`

### Environment Variables (`.env`)

API keys are loaded in `ui/app.py` from system environment variables or a local `.env` file at the project root:

| Key | Purpose | Required For |
|---|---|---|
| `GEMINI_API_KEY` | Automated headless plan architecture review | `scripts/review_plan.py` |
| `TOMTOM_API_KEY` | Turn-by-turn predictive speeds & corridor traffic | Precision speed sync, traffic profiling |
| `HERE_API_KEY` | Highway speed limits & toll plaza rate lookups | Speed validation, toll calculations |
| `GOOGLEMAPS_API_KEY` | Google Elevation API & Google Places amenities | Elevation profiles, charger amenities |

> [!WARNING]
> Never commit `.env` or sensitive API keys. `.env*` and `*.key` are strictly ignored by `.gitignore`.

---

## 3. Styling & UI Conventions

The frontend employs a unified, cohesive dark aesthetic designed for high-density telemetry and route inspection.

### Color Palette (Tailwind CSS)

- **Canvas & Backgrounds:**
  - Deep canvas: `bg-slate-950`
  - Cards & Navigation bars: `bg-slate-900`
  - Elevated containers / Modals: `bg-slate-800` or `bg-slate-900/90` with backdrop blur
  - Borders: `border-slate-800` and `border-slate-700`
- **Text & Hierarchy:**
  - Primary text: `text-white` or `text-slate-100`
  - Secondary / labels: `text-slate-400`
  - Badges / subtle text: `text-slate-300`
- **Semantic Accents:**
  - **Emerald (`emerald-500`, `text-emerald-400`):** Optimal metrics, charging power, primary action buttons, success badges.
  - **Amber (`amber-500`, `text-amber-400`):** Precision sync, live traffic warnings, bottleneck speeds, active loading badges.
  - **Cyan / Blue / Violet:** Distinct itinerary comparative variants (Fastest vs. Cheapest vs. Balanced).

### Typography

- **UI & Controls:** Standard sans-serif (`font-sans`).
- **Telemetry & Numbers:** Monospace (`font-mono`) for SoC percentages, kW rates, duration, currency, GPS coordinates, and vehicle mass.

### Map Elements & Leaflet Components

- Custom circular CSS icons are defined for Leaflet pins:
  - `.custom-stop-icon`: Emerald badge with white border and drop shadow for charging stops.
  - `.custom-endpoint-icon`: Origin/destination markers.
- Interactive tooltips display station brand, kW rating, stall counts, and walking amenities.

---

## 4. Testing Setup & Quality Assurance

The repository includes a multi-layered test suite spanning Python unit logic, weather physics, and headless browser V8 JavaScript verification.

### Test Directory (`tests/`)

| Test File | Scope | Method |
|---|---|---|
| `tests/test_engine.py` | Vehicle mass, charging curve taper, HVAC draw, toll discounts | Python `unittest` |
| `tests/test_weather_engine.py` | Weather forecasts, ERA5 historical data, air density, wind, drying | Python `asyncio` test runner |
| `tests/test_js_syntax.py` | Extracts inline `<script>` from `index.html` and checks syntax | Headless Chrome via CDP (`Runtime.compileScript`) |
| `tests/test_full_suite.py` | Full browser lifecycle, DOM assertions, console error monitoring | Headless Chrome CDP over WebSockets |
| `tests/test_benchmark_reproduce.py` | Benchmark optimization execution times and station filters | Headless Chrome CDP |

### Running Tests

```bash
# 1. Run Python unit tests
python -m unittest tests/test_engine.py

# 2. Run weather engine test suite
python tests/test_weather_engine.py

# 3. Validate frontend JavaScript syntax (Chrome V8)
python tests/test_js_syntax.py

# 4. Run browser end-to-end suite
python tests/test_full_suite.py
```

> [!IMPORTANT]
> **Mandatory Frontend Quality Gate:** Because the dashboard JavaScript is embedded directly within `index.html` (>11,000 lines), **always run `python tests/test_js_syntax.py`** after modifying the frontend scripts to confirm no syntax or parser errors were introduced.

---

## 4.1. Autonomous Execution & Verification Guardrails

1. **Strict HTML Synchronization:**
   - Any modification to frontend logic must be made to `index.html`, `public/index.html`, and `ui/templates/index.html`.
   - After updating the HTML files, you MUST run `python tests/test_js_syntax.py` before taking any other action. If syntax errors exist, resolve them immediately.

2. **The "Two-Failure" Circuit Breaker:**
   - If a test script (`test_engine.py`, `test_js_syntax.py`, etc.) fails twice in a row on the same task, halt execution. 
   - Revert changes to the last clean git status and clearly document the root cause rather than attempting repetitive micro-patches.

3. **Deployment Gates:**
   - Never commit or push code if `tests/test_engine.py` or `tests/test_js_syntax.py` fail.
   - Separate feature completion from remote deployment. Always present a `git status` and test summary before initiating a commit.

---

## 5. File Structure Rules & Parity Requirements

```
.
├── api/
│   └── index.py                # Serverless ASGI bridge for Vercel deployment
├── data/                       # Core persistent data caches
│   ├── active_stations_cache.json
│   ├── bottleneck_speeds_db.json
│   ├── charger_detours_cache.json
│   ├── corridor_elevations.json
│   ├── corridor_routes_cache.json
│   ├── here_speed_limits.json
│   ├── here_tolls_db.json
│   ├── holiday_congestion_offsets.json
│   ├── prices.db               # SQLite database for pricing history
│   ├── prices.json
│   ├── route_intersections_db.json
│   ├── station_amenities_db.json
│   ├── tomtom_corridors_168h.json
│   └── waypoint_sequences_cache.json
├── engine/                     # Physics, vehicle, routing, and optimization logic
│   ├── energy.py               # FastSim road-load physics, aero drag, regen, HVAC
│   ├── optimizer.py            # Multi-objective Pareto optimization (Fastest, Cheapest, Balanced)
│   ├── router.py               # Route polyline decoder, corridors, waypoints
│   ├── station_manager.py      # Station filtering (>=100 kW, CCS1/MagicDock), amenities
│   ├── tolls.py                # PA/NJ/WV Turnpike rates, E-ZPass and EV Green Pass
│   ├── vehicle.py              # 2025 Equinox EV specs, mass payloads, Ultium charging curve
│   ├── weather.py              # OpenWeatherMap live/manual models
│   └── weather_engine.py       # High-resolution multi-modal weather & road physics engine
├── pipeline/                   # CPO pricing scraper pipeline
│   ├── networks/               # Adapters for EA, Tesla, EVgo, IONNA, Mercedes, ChargePoint, etc.
│   └── scraper.py              # Scraper orchestrator and database updater
├── public/                     # Static deployment artifacts (Vercel & static hosting)
│   ├── index.html              # Mirror of root index.html
│   ├── weather_preview.html
│   └── data/                   # Mirror of active data caches for static web access
├── scripts/                    # Automation, cache harvesting, and maintenance utilities
│   └── review_plan.py          # Headless plan audit runner (Gemini API)
├── tests/                      # Python unit tests and Chrome CDP integration tests
├── ui/
│   ├── app.py                  # FastAPI server and REST endpoints
│   ├── static/                 # Static web assets (if needed)
│   └── templates/
│       └── index.html          # Mirror of root index.html
├── index.html                  # Primary standalone application dashboard
├── preview_weather.py          # Standalone CLI weather preview tool
├── requirements.txt            # Python dependencies
├── run.py                      # Master entry point (Web server, CLI optimizer, Scraper)
├── start.bat                   # Windows one-click local dashboard launcher
└── vercel.json                 # Vercel serverless routing configuration
```

### Critical File Parity Rules

1. **Dashboard HTML Synchronization:**
   - The primary UI lives in `index.html` at the project root.
   - Exact duplicate mirrors exist at `public/index.html` and `ui/templates/index.html`.
   - **Whenever modifying `index.html`**, you must synchronize the changes across all three locations (`index.html`, `public/index.html`, and `ui/templates/index.html`).

2. **Data Cache Parity:**
   - Static assets consumed directly by client-side browser logic are duplicated in `data/` and `public/data/`.
   - When generating or updating core offline database caches (e.g., `active_stations_cache.json`, `corridor_routes_cache.json`, `station_amenities_db.json`), ensure both `data/` and `public/data/` remain in sync.

3. **Scratch & Temporary Artifacts:**
   - Ad-hoc scripts, one-off test runs, or browser test profiles must be stored in `.scratch/` or `C:\temp\`.
   - `.scratch/` is ignored by Git and should not contain persistent production code.

---

## 6. Execution Modes & CLI Reference

The master runner is `run.py`:

```bash
# Launch interactive web dashboard ([http://127.0.0.1:8000](http://127.0.0.1:8000))
python run.py

# Launch simulation in terminal (CLI Pareto solver)
python run.py --cli

# Run pricing scraper across all CPO networks
python run.py --scrape

# Run weather preview engine CLI
python preview_weather.py --dest st_onge --tomorrow
```

Windows users can also double-click `start.bat` to immediately launch `index.html` in their default browser for offline/direct usage.

---

## 7. Planning, Review Relay & Git Workflow

### 7.1. Autonomous Single-Session Plan Review Pipeline

**Trigger:** Any request containing *"create an implementation plan"*, *"plan [feature]"*, *"create a reviewed implementation plan"*, or equivalent planning intent.

Whenever a plan is requested, execute this automated review sequence within your session before writing application code:

1. **Author & Archive the Plan:**
   - Generate the detailed implementation plan adhering to the Fidelity Hierarchy and File Parity rules.
   - Write a permanent timestamped copy to `.scratch/plans/YYYY-MM-DD_<feature_name>.md`.
   - Overwrite `.scratch/plan.md` with the exact same content.
2. **Execute Headless Review:**
   - Run the automated reviewer script in the terminal:
     ```bash
     python scripts/review_plan.py
     ```
   - Inspect the terminal output and `.scratch/plan_review.md`.
3. **Handle Review Verdicts & Output Impact Summary:**
   - **If exit code is non-zero or contains `Status: CHANGES REQUESTED`:**
     - Address each flagged blocker or fidelity concern.
     - Update both `.scratch/plan.md` and `.scratch/plans/YYYY-MM-DD_<feature_name>.md`.
     - Re-run `python scripts/review_plan.py` until it exits 0 (`Status: APPROVED`).
   - **If exit code is 0 and contains `Status: APPROVED`:**
     - **Mandatory Review Impact Summary:** Include an explicit summary in your response:
       ```markdown
       ### Plan Review Impact Summary
       - **Reviewer Feedback:** (Key observations, edge cases, or blockers flagged)
       - **Adjustments Made:** (Concrete changes made to the plan based on the review)
       ```
       *(If approved on the first pass with zero changes required, explicitly state: "Approved on initial pass with zero architectural modifications required.")*
     - Delete `.scratch/plan.md` and `.scratch/plan_review.md`.
     - Proceed directly to code implementation and local testing gates.

---

### 7.2. Git Execution Modes & CodeRabbit Integration

#### Mode 0: Fast-Track / Super Quick Mode (Bypass All Reviews)
* **Trigger:** Explicit keywords such as *"super quick"*, *"quick fix"*, *"fast-track"*, *"skip reviews"*, or *"quick tweak"*.
* **Scope:** CSS tweaks, UI wording, quick typo fixes, minor styling, or simple isolated script tweaks where full planning and PR audits add unnecessary friction.
* **Execution Rules:**
  1. **Skip all reviews:** Do NOT generate `.scratch/plan.md` or run `review_plan.py`. Do NOT open a PR for CodeRabbit.
  2. **Synchronize File Parity:** If touching UI, still update all three files: `index.html`, `public/index.html`, and `ui/templates/index.html`.
  3. **Targeted Essential Test Only:** Run ONLY the minimal gate required for the affected layer:
     - **UI / Frontend edits:** Run only `python tests/test_js_syntax.py`.
     - **Backend / Math edits:** Run only `python -m unittest tests/test_engine.py`.
     - **Docs / Comments / Static assets:** Skip test runners entirely.
  4. Commit and push directly to `main`:
     ```bash
     git add -A && git commit -m "quick: <brief summary>" && git push
     ```

#### Mode A: Direct Mode (Fast / Standard)
* **Scope:** Routine, low-risk changes (single-file fixes, standard feature work, non-core refactors).
* **Execution:**
  1. Make edits ensuring the 3-file HTML synchronization rule is respected.
  2. Run local test gates: `python -m unittest tests/test_engine.py` and `python tests/test_js_syntax.py`.
  3. Verify exit code 0.
  4. Commit and push directly to `main`.

#### Mode B: PR Review Mode (Automated CodeRabbit Review)
* **Triggers:**
  - **Explicit prompt phrases:** *"Use PR mode"*, *"Open a PR for review"*, *"With reviews"*, *"Double check"*, *"External reviews"*, or similar requests.
  - **Automatic triggers:** Any modification to core physics/routing logic (`engine/**`), database schema changes (`prices.db`), or edits exceeding 300 lines in `index.html`.
* **Execution Workflow:**
  1. Create and checkout a feature branch:
     ```bash
     git checkout -b feature/<descriptive-name>
     ```
  2. Implement changes and synchronize HTML mirrors (`index.html`, `public/index.html`, `ui/templates/index.html`).
  3. Run local test suites (`tests/test_engine.py`, `tests/test_js_syntax.py`). Ensure 100% pass rate.
  4. Commit and push the branch:
     ```bash
     git push -u origin feature/<descriptive-name>
     ```
  5. Open a Pull Request using GitHub CLI:
     ```bash
     gh pr create --title "<Descriptive Title>" --body "<Summary and changes of passes test verified>"
     ```
  6. **Monitor CodeRabbit Review:**
     - Poll review status: `gh pr view --comments` or `gh pr checks`.
     - CodeRabbit automatically runs and comments inline on the PR.
  7. **Resolve Review Feedback & Output Impact Summary:**
     - **Actionable Bugs / Edge Cases:** Immediately fix the code locally, rerun test gates, and push the follow-up commit (`git push`).
     - **Stylistic / Irrelevant Comments:** Disregard minor comments that violate established project patterns (e.g., CDN loading, single-file SPA).
  8. **Merge & Report:**
     - Merge the PR:
       ```bash
       gh pr merge --squash --delete-branch
       ```
     - Return to `main` (`git checkout main && git pull`).
     - **Mandatory Review Impact Summary:** In your final response, provide a summary:
       ```markdown
       ### CodeRabbit Review Impact Summary
       - **Issues Flagged:** (Specific bugs, unhandled exceptions, or regressions noted by CodeRabbit)
       - **Fixes Applied:** (Exact commits/changes made in response before merging)
       ```
       *(If no actionable issues were raised, state: "CodeRabbit approved clean with no functional blockers flagged.")*

#### Mode C: Full Pipeline Mode (Plan Review + CodeRabbit PR)
* **Trigger:** Requests matching *"Full pipeline for [feature]"*, *"Plan and build [feature] with PR review"*, or *"End-to-end review mode"*.
* **Workflow:**
  1. Automatically execute Section 7.1 (`scripts/review_plan.py`) until approved and document plan impact.
  2. Transition directly into Section 7.2 Mode B (feature branch, local test gates, PR creation, CodeRabbit comment resolution, squash-merge, and code review impact report).