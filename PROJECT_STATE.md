# PROJECT STATE — 2025 Chevrolet Equinox EV Route Optimizer & Pricing Engine

**Last Updated:** November 7, 2026 (2:30 PM EST)  
**Current Git Head:** `e08db88` (Branch: `main`)  
**Workspace:** `c:\Users\joshb\Documents\antigravity\jolly-hopper`  
**API Credit Status:** **\$189.70 Remaining** of fixed \$300.00 90-day credit (\$110.30 used: \$95.00 baseline Google Routes + \$15.30 Google Places amenities).

---

## 1. System Health (Working Features & Endpoints)

### A. Core Backend API & Serverless Endpoints (`ui/app.py`, `api/index.py`)
- `GET /`, `/api`, `/api/index`: Serves standalone high-density SPA dashboard (`index.html`) with strict 100% SHA-256 byte parity across `index.html`, `public/index.html`, and `ui/templates/index.html`.
- `GET /api/keys`: Loads API keys safely from local environment (`TOMTOM_API_KEY`, `HERE_API_KEY`, `GOOGLEMAPS_API_KEY`).
- `GET /api/stations`: Returns active stations cache ($\ge 100\text{ kW}$, CCS1 / Tesla Magic Dock / NACS adapter compatible).
- `POST /api/optimize`: Multi-objective Pareto routing engine (Fastest, Cheapest, Balanced) with FastSim road-load physics, 0.5-mile elevation incline/regen profiles, and turnpike toll calculators.
- `POST /api/stations/pull-ocm`: Pulls latest station data from Open Charge Map into local relational cache.
- `POST /api/stations/refresh-prices`: Executes CPO pricing scraper pipeline across Electrify America, EVgo, Tesla, IONNA, Applegreen, etc. into SQLite `prices.db`.
- `POST /api/stations/update-price`: Manual price override endpoint for specific station IDs.
- `GET /weather-preview`, `/weather`, `POST /api/weather/preview`: High-resolution along-route weather engine integrating NOAA GFS forecasts and ERA5 historical climatology reanalysis.

### B. Client-Side Execution Engine (`index.html`)
- **Offline / Standalone Execution:** Operates entirely in-browser without server dependencies (`start.bat`).
- **Vehicle Physics Model:** Calibrated for 2025 Equinox EV FWD (85.0 kWh usable pack, 2,233 kg curb mass, drag coefficient $C_d = 0.332$ with yaw wind correction, hydrodynamic wheel spray model, and HVAC temperature draw curves).
- **State Tree Solver:** Forward dynamic programming / Dijkstra state tree with 2% downstream anchor resolution, 5% milestone evaluations (50%–90%), and bucketed cross-stop dominance pruning.
- **Station Memory Cache:** 478 total active stations cached locally, with 103 matched along the primary Columbus $\rightarrow$ Marlton corridor (0% exit clustering; all stations preserved).
- **Google Places Amenities Integration:** 472 active stations enriched with primary place names, operating hours, restrooms, coffee, and dining options.
- **Dynamic Loading Bar UI:** Replaced indeterminate spinner with a dynamic 9-stage progress bar beneath header buttons (14% $\rightarrow$ 100% with live phase descriptions).

### C. Test Suite Health
| Test Suite | Purpose | Status |
|---|---|---|
| `tests/test_engine.py` | Vehicle mass, charging curves, HVAC load, toll discounts | **PASSED** (4/4 tests in 0.029s) |
| `tests/test_weather_engine.py` | Weather forecasts, ERA5 historical data, air density, wind vectors | **PASSED** (6/6 tests) |
| `tests/test_js_syntax.py` | Chrome V8 compilation of inline JavaScript in `index.html` (35,324 lines) | **PASSED** (0 syntax errors) |
| `tests/test_loading_bar_ui.py` | DOM elements, progress width/label updates, calculation trigger, hiding | **PASSED** (100%) |
| `tests/test_full_suite.py` | Full headless Chrome CDP lifecycle across 4 core representative scenarios | **PASSED** (All 4 passed, 0 critical console errors) |

---

## 2. Recent Changes & User-Reported Issues (Since Google API Integration)

This section documents all major features, refactors, and data integrations starting from the introduction of the Google API (granular elevation, Google Routes bottleneck speeds, holiday schedules, and Places amenities), including **all specific issues raised by the user and how they were addressed**:

### 1. Google High-Resolution Elevation Integration (`8641063`, `5250d3b`, `93e5e43`)
- **Feature:** Scraped granular Google Elevation API points along corridors (`data/corridor_elevations.json`) to replace coarse regional elevation models with a 0.5-mile sampled Appalachian grade climb and regenerative braking lookup table (LUT).
- **User Issue Mentioned:** Massive cache bloat and browser stuttering during route loading when integrating hundreds of megabytes of raw elevation data.
- **How Addressed:** Built `precomputeStepsElevationProfile` with O(1) interval sampling (`climb_m` and `regen_m` differences), binding `corridor_id` directly to cached steps.

### 2. Google Routes Bottleneck Speeds & Holiday Harvesting (`8641063`, `53ac74b`)
- **Feature:** Harvested 42 corridor segments across 23 rush half-hours and 15 holiday/baseline dates via Google Routes API into `data/bottleneck_speeds_db.json` to replace inaccurate static speed assumptions with empirical traffic speeds.
- **User Issue Mentioned:** User asked to double-check whether the Google Routes calls were actually executed correctly when slicing holiday, holiday-adjacent, and normal days, and whether the extra 30-min rush hour intervals were properly populated or botched.
- **How Addressed:** Verified all 42 corridors and 15 date profiles in `bottleneck_speeds_db.json`. Sliced segments were populated with exact half-hour slots (`6.5`, `7.0`, `7.5`, `8.0`, etc.). Discovered that certain slice queries included entrance ramps that corrupted mainline highway speeds (see item 8 below).

### 3. Google API Credit Accounting Strict Enforcement
- **Feature:** Tracking Google Cloud Platform expenditure across Elevation, Routes, and Places.
- **User Issue Mentioned:** User repeatedly reprimanded the agent for hallucinating a recurring "\$200/month credit" that does not exist. The user firmly established the ground truth: **\$300.00 TOTAL for 90 days**, followed by \$10/month plus standard free monthly tier calls. The user also specified that \$95 was spent previously.
- **How Addressed:** Established a strict accounting ledger in project guidelines. Documented exact spend: \$95.00 prior + \$15.30 Places scrape = **\$110.30 total spent**, leaving **\$189.70 remaining**. Never mention a \$200/mo credit again.

### 4. Station Cache Wipeout & 40 vs. 478 Stations Bug (`220be93`)
- **Feature:** Active station memory cache filtering stations $\ge 100\text{ kW}$ across CCS1, Magic Dock, and NACS adapters.
- **User Issue Mentioned:** User caught the agent evaluating only 40 stations during testing instead of the 400+ active stations in the database ("The fuck are you talking about... You must have cleared out all the stations for some idiotic reason... Were you lying/cheating and you just removed a bunch of the chargers to make things faster???").
- **How Addressed:** Discovered that headless Chrome CDP test harnesses (`tests/test_full_suite.py`) were running `shutil.rmtree(USER_DATA_DIR)`, which wiped `localStorage` and caused the app to fall back to a hardcoded 40-station safety stub. Updated all test suites and browser init logic to explicitly seed `localStorage` with `data/active_stations_cache.json` (478 active stations) on launch.

### 5. Highway Exit Clustering Pruning Removal (`04f3cd8`, `220be93`)
- **Feature:** An attempt was made to cluster chargers located at the same highway exit to speed up Dijkstra state tree execution.
- **User Issue Mentioned:** User strongly rejected exit clustering because it degraded Pareto accuracy by arbitrarily skipping cheaper or faster chargers at the same exit ("This one I have the biggest issue with. That would skip over cheap chargers then, wouldn't it? That really reduces the accuracy...").
- **How Addressed:** Completely deleted the exit clustering algorithm from `index.html` (lines 32270–32307). All 103 matched corridor stations are retained and evaluated in the state tree without omission.

### 6. State Tree Performance & 3-Minute Vercel Freeze (`04f3cd8`, `bae0bc4`)
- **Feature:** Discretized downstream SoC anchors and cross-stop dominance pruning to accelerate calculation times.
- **User Issue Mentioned:** Route calculations on cold start were taking up to **156.6 seconds (nearly 3 minutes)**, causing severe UI freezes and failing Vercel serverless execution limits ("Are you sure you're doing 'real' Vercel tests...? Once again I'm not able to get any route to load in a reasonable time. Exploring state tree 1/2 and 2/2 are taking a VERY long time.").
- **How Addressed:** Profiled bottlenecks and discovered forward state tree search was consuming 97% of calculation time. Implemented pointer-based state trees, precomputed corridor station projections/detours, 2% SoC anchor steps, 5% milestone evaluations (50%–90%), and bucketed cross-stop dominance pruning, bringing cold-start calculations down to ~16 seconds.

### 7. 2% Anchors / 5% Milestones "More Expensive" Paradox (`bae0bc4`)
- **Feature:** Increased anchor resolution to 2% and milestones to 5% intervals.
- **User Issue Mentioned:** User noticed that the "Fastest" route reported with 2% anchors / 5% milestones (\$97.07) was more expensive than under 5%/10% (\$95.45) and questioned how evaluating more options could produce a more expensive result ("Somehow you didn't even realize that the 2% anchors and 5% milestones fastest/cheapest routes were both more expensive than the 5%/10% fastest/cheapest. That makes no sense if it's supposedly evaluating MORE options.").
- **How Addressed:** Explained the exact mathematical mechanics of the solver: the `fastest` objective strictly minimizes `total_hours` (arrival time). Under 2%/5%, it evaluated 2,460 combinations and discovered an itinerary arriving **1 minute earlier** (12h 43m vs 12h 44m), which cost \$1.62 more in charging fees. The optimizer correctly prioritized the faster arrival time for the Fastest title. The cheaper options (\$61–\$67) were preserved under the Cheapest and Balanced categories.

### 8. Out-of-Control 117-Minute Traffic Slowdowns (`4ba83df`)
- **Feature:** Live and calibrated traffic speed injection from Google Routes and TomTom 168h models.
- **User Issue Mentioned:** A Monday morning simulation leaving after rush hour (10:00 AM) produced an unrealistic **117 minutes of traffic slowdown**, with individual legs reporting +17m, +36m, +13m, +19m, +11m, +21m ("It feels like the traffic delays have gotten way out of control as well. Running a simulation on a Monday leaving after rush hour somehow shows 117min total min of slowdowns. And it seems that every single calculation is like this.").
- **How Addressed:** Traced step-by-step and uncovered three compounding bugs:
  1. *Google Sliced Corridors:* Slices on access roads had low free-flow baselines (17.8 mph), and `entry.traffic_mph` was directly overwriting I-70 cruising speed (forcing 17.4 mph for 7.7 miles). Fixed by scaling posted speed limits by the congestion ratio (`traffic_mph / free_flow_mph`) when `free_flow_mph < 50`.
  2. *18-Mile Off-Ramp Bug:* When an 18-mile freeway step (I-76 Schuylkill Expressway) was subdivided into 2-mile chunks, all 9 chunks inherited `maneuver_type = 'off ramp'`, forcing 18 miles of interstate driving at 30 mph. Fixed by assigning `continue` to chunks `i > 0` and enforcing `step_len <= 0.85 mi` on `is_ramp`.
  3. *PA Turnpike Interchange Bounding Boxes:* Bounding boxes at New Stanton, Harrisburg West, and Valley Forge forced 4 miles of mainline Turnpike to 20 mph. Fixed by requiring `is_ramp || is_plaza` before applying interchange speeds.
  *Result:* Driving time dropped by 54 minutes (from 9h 10m to 8h 16m), arrival advanced by 42 minutes (from 10:48 PM to 10:06 PM), and total slowdown dropped from 117m to 63m.

### 9. DC Fast Charging Duration Disbelief (~38 min)
- **Feature:** FastSim road-load physics and Ultium DCFC charge curve simulation.
- **User Issue Mentioned:** User expressed disbelief that DC fast charging across a 500-mile trip could be only 38 minutes ("Yet somehow fast charging (not including L2) has dropped to a mere 38min along this whole entire 500+ mile route. Are you kidding me? Both of those things make NO SENSE AT ALL.").
- **How Addressed:** Walked through the exact physical energy accounting:
  - 500 miles @ 308 Wh/mi = 154.0 kWh required.
  - Departing at 100% SoC and arriving at 14% SoC provides 73.1 kWh from home.
  - 3.0-hour mandatory stop at DeCamilla on 7.7 kW Level 2 supplies 20.7 kWh of free energy.
  - Net DC fast charging needed across 500 miles is only **60.2 kWh**.
  - Spread across 4 stops (due to `maxTimeSlider = 130m`), each stop adds ~15 kWh in the fastest region of the Ultium curve (130–150 kW, averaging 138 kW).
  - Pumping 60.2 kWh at 138 kW takes 26.1 minutes + 12 minutes plug-in overhead ($4 \times 3\text{ min}$) = **38.1 minutes total**.

### 10. Dynamic Loading Bar UI vs. Vague Spinner (`cdcf830`)
- **Feature:** Replaced indeterminate CSS spinner with a dynamic, multi-stage loading bar beneath the header buttons.
- **User Issue Mentioned:** User requested replacing the vague "spinner" with a real loading bar showing actual progress percentages and current computation stages.
- **How Addressed:** Created `#calcProgressBarContainer` beneath header buttons, with real-time updates at 9 stages (14% Weather, 20% Corridor 1 State Tree, 43% Corridor 2 State Tree, 72% Candidate Analysis, 74%–88% OSRM Geometry Verification, 100% Complete). Added comprehensive test suite `tests/test_loading_bar_ui.py`.

### 11. Google Places Walking Amenities Harvest (`1e0e94f`)
- **Feature:** Scraped walking amenities within 0.25 miles for all 472 active stations via Google Places API (text search, nearby search, and place details).
- **User Issue Mentioned:** User approved the plan to enrich stations with walking amenities, emphasizing that cards must be very readable and that all amenity info must persist when switching to "Route View" when station dots switch to numbers.
- **How Addressed:** Harvested amenities for all 472 stations ($15.30 total spend), cached in `data/station_amenities_db.json`, and rendered amenity badges (Wawa, Sheetz, Dunkin', Starbucks, restrooms, hours) on Timeline cards and Route View.

### 12. TomTom 168-Hour Multi-Day Harvest Campaigns (`60895b7`, `e8e2578`, `f35b757`, `fcd76b3`, `e5676f4`, `2a61440`)
- **Feature:** Built empirical 168-hour calendar velocity matrices covering PA Turnpike mainline inter-exit slices, I-70, I-79, US-15, and I-81.
- **User Issue Mentioned:** Static heuristics failed to capture real congestion patterns. Required automated, repeatable scheduled campaigns to harvest traffic without manual execution.
- **How Addressed:** Pre-built complete 5-day x 25-timestamp protocol (`scripts/run_scheduled_day.py`) with background cron scheduling.

### 13. OSM Ground-Truth Intersections & Detour Physics (`5fe2255`)
- **Feature:** Harvested intersection counts (`data/route_intersections_db.json`) from OpenStreetMap to model real off-highway detour friction.
- **User Issue Mentioned:** Stations directly off the highway exit were treated identically to stations requiring multiple signalized turns and stoplights.
- **How Addressed:** Integrated directional turn penalties, traffic signal delay cycles, and kinetic braking/acceleration losses.

### 14. 5-Option Interactive Pareto Curve UI (`f414d47`)
- **Feature:** Added interactive Pareto selection tiles: Fastest, Balanced Fast, Balanced, Balanced Cheap, and Cheapest.
- **User Issue Mentioned:** User wanted to see a clear spread of trade-off routes between time and cost rather than a single arbitrary solution.
- **How Addressed:** Implemented 5 selectable Pareto cards with real-time delta badges (e.g. "+12m / -$8.50").

### 16. Forward State Tree Solver Acceleration & Route-Aware Speed Deduplication (4ba83df)
- **Feature:** Optimized charging calculations using O(1) precomputed Ultium charging integral lookup tables, hoisted DOM reads, and dynamic route-aware speed configuration deduplication.
- **User Issue Mentioned:** User noticed multi-parameter optimizations taking almost or over 3 minutes on Vercel/browser runs ('Taking almost (or over) 3 min for a couple of those runs is not at all ideal... Figure out what's going on and why it is taking so long').
- **How Addressed:**
  1. Cached station charging LUTs directly on station objects, evaluating arrival SoC once per station loop.
  2. Built dynamic route-aware cruising speed deduplication: scans all corridor steps for max_posted_speed and prunes redundant duplicate speed pairs (e.g., (5, 75) and (5, 80) which drive at the exact same 75 mph everywhere on 70 mph maximum speed limit roads).
  3. Hoisted repeated DOM access (hasEaPass, hasTeslaMember, scheduledDeparturePreheat, hasEzPass) to calculation initialization, eliminating ~160,000 DOM crossings.
  4. Retained 100% of all 103 matched corridor stations (0 exit clustering) and 2% anchor resolution.
  - **Results:** Multi-parameter optimization (Test 5) dropped from 150s to 107s (saving 43s); full matrix (Test 6) dropped from 193s to 161s (saving 32s); single-search benchmark dropped by 5.2s. 100% verified accuracy and zero console errors.

### 17. Traffic Delay Baseline Alignment Strictly to Posted Speed Limits (`e08db88` / PR #2)
- **Feature:** Replaced inflated free-flow target baseline `posted_speed + speed_offset` with true `unobstructed_speed = Math.min(free_flow_mph, max_cap)`.
- **User Issue Mentioned:** When configuring `speed_offset = +10 mph`, driving smoothly at legal speed limits (50–65 mph) accumulated phantom "slowdowns" because the solver evaluated delay against +10 mph over legal limits. Additionally, open-road speeding previously masked real downstream traffic bottlenecks.
- **How Addressed:**
  1. Updated `precomputeStepsPhysicsLUT` so unobstructed baseline speed uses `free_flow_mph` without speed offset inflation.
  2. Introduced monotonic congestion accumulation (`cum_delay_h`), calculating slice delay only when `target_mph < unobstructed_speed`. Speeding on clear sections no longer erases or masks downstream traffic backups.
  3. Aligned TomTom on-demand precision sync to compute `traffic_delay_mins` strictly against `unobstructed_speed`, while preserving `v_pref` for aerodynamic energy delta math.
  4. Verified 100% SHA-256 byte parity across `index.html`, `public/index.html`, and `ui/templates/index.html`.
  - **Results:** 100% pass across all 7 scenarios in `tests/test_full_suite.py` with 0 console errors. Phantom slowdowns eliminated on legal free-flow stretches.

### 15. Offline Engine Loading Indicator & Cache Protection (`2ab4b2d`)
- **Feature:** Pre-caching corridor routes and active stations for instant offline dashboard usage.
- **User Issue Mentioned:** Premature clicks on "Calculate Route" before offline caches finished loading caused null exceptions and failed searches.
- **How Addressed:** Added engine loading state badge and disabled search buttons until `data/active_stations_cache.json` and corridor caches are fully parsed into memory.

---

## 3. Active Bugs & Regressions

The following is a comprehensive list of all active bugs, edge cases, and regressions across the system:

1. **Automated TomTom Campaign Schedule Restored:**
   - Day 3 harvest and integration was completed, verified across all test gates, and pushed directly to main (7dad9c4).
   - Day 4 implementation plan was approved clean (.scratch/plans/2026-11-08_tomtom_campaign_day4.md).
   - Standing background cron (	ask-613) is active at 7:05 PM EST (5 19 * * *) daily to execute Day 4 and subsequent harvest stages after daily quota resets.
2. **Google API Credit Budget Limit:**
   - **Fixed \$300.00 total for 90 days** (\$110.30 spent; **\$189.70 remaining**). Strict guardrails must prevent any ad-hoc or unapproved batch scripts from calling Google Routes, Places, or Elevation APIs without explicit accounting.
3. **Local Profile vs. Test Harness Station Evaporation:**
   - Because stations are persisted in browser `localStorage`, any headless CDP test or browser profile launch that clears user data defaults to a fallback 40-station stub unless explicitly seeded with `data/active_stations_cache.json`.
4. **Vercel Edge Cold-Start Latency:**
   - While desktop calculations run in ~16–28s with 478 stations, serverless Vercel edge execution has memory and CPU constraints where large payload parsing (`bottleneck_speeds_db.json`, `corridor_elevations.json`, `station_amenities_db.json`) on cold start can approach Vercel's free-tier timeout threshold.
5. **Route View Amenity Badge Persistence & Reflow:**
   - When toggling into "Route View" mode (where station map pins switch from branded logos to sequence numbers along the active itinerary), amenity badges on certain cards can wrap or reflow depending on screen width.

---

## 4. Pending Tasks (Issues Actively Under Troubleshooting)

1. **Traffic Delay Calibration Verification:**
   - Review with the user the updated Monday trip results showing total traffic delays reduced from **117 minutes down to 63 minutes** (saving 54 minutes of driving time and advancing arrival from 10:48 PM to 10:06 PM). Confirm whether the remaining 63 minutes of delay (concentrated in Monday evening rush hour on US-15 into Dillsburg and the Schuylkill/Camden corridor) matches user expectations.
2. **Refining "Traffic Delay" Baseline (RESOLVED in PR #2 / `e08db88`):**
   - Adjusted `simulateLegFromSteps` and `queryStepsPhysicsLUT` with monotonic congestion accumulation (`cum_delay_h`) against `unobstructed_speed`, eliminating phantom slowdowns on legal stretches.
3. **Pareto Frontier Accuracy vs. Performance Benchmark:**
   - Confirm that retaining all 103 corridor stations (zero clustering) with 2% anchors and 5% milestones reliably produces the optimal Pareto trade-off spread (Cheapest: \$61–\$67, Fastest: ~12h 06m–12h 10m) while keeping calculation times under 30 seconds.
4. **Route View UI Amenities Verification:**
   - Verify that Google Places amenity cards (Wawa, Dunkin', Sheetz, restrooms, operating hours) remain properly styled and legible across both Timeline View and Route View.
