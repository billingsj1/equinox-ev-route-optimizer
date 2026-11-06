import os
import hashlib

def update_file(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    # 1. Update engine counter 0/9 -> 0/10
    content = content.replace(
        '<span id="dbEngineCount" class="px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30">0/9</span>',
        '<span id="dbEngineCount" class="px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30">0/10</span>'
    )

    # 2. Add window.ROUTE_INTERSECTIONS_DB
    if "window.ROUTE_INTERSECTIONS_DB" not in content:
        content = content.replace(
            "window.HOLIDAY_OFFSETS_DB = null;\r\n",
            "window.HOLIDAY_OFFSETS_DB = null;\r\n    window.ROUTE_INTERSECTIONS_DB = null;\r\n"
        )

    # 3. Add var ROUTE_INTERSECTIONS_DB
    if "var ROUTE_INTERSECTIONS_DB" not in content:
        content = content.replace(
            "var HOLIDAY_OFFSETS_DB = null;\r\n",
            "var HOLIDAY_OFFSETS_DB = null;\r\n    var ROUTE_INTERSECTIONS_DB = null;\r\n"
        )

    # 4. Upgrade simulateDetourPhysics
    old_sim_str = """    function simulateDetourPhysics(detour_miles, is_plaza, payload_lbs, temp_f, road_cond) {
      const curb_kg = 2233.0;
      const total_mass_kg = curb_kg + (payload_lbs * 0.453592);
      const v_mph = is_plaza ? 20.0 : 28.0;
      const v_ms = v_mph * 0.44704;
      const hours = detour_miles / v_mph;
      const dist_m = detour_miles * 1609.34;

      // Local rolling resistance and aero at 20-28 mph
      let crr = 0.0105;
      if (road_cond === "wet") crr *= 1.40;
      else if (road_cond === "snow_ice") crr *= 2.20;
      const f_rr = crr * total_mass_kg * 9.80665;
      const f_spray = (road_cond === "wet") ? (0.5 * 0.35 * 1000.0 * (4 * 0.235) * 0.0005 * Math.pow(v_ms, 2)) : 0.0;

      const temp_c = (temp_f - 32) * 5 / 9;
      const rho = 1.225 * (288.15 / Math.max(240, temp_c + 273.15));
      const f_aero = 0.5 * rho * (0.332 * 2.60) * Math.pow(v_ms, 2);
      const steady_kwh = ((f_rr + f_spray + f_aero) * dist_m) / 3.6e6 / 0.91;

      // Stop-and-go intersection cycles (service plazas: 1 parking stop; off-highway exits: 2-3 intersection stops)
      const num_stops = is_plaza ? 1.0 : Math.max(2.0, detour_miles * 2.2);
      const delta_ke = 0.5 * total_mass_kg * Math.pow(v_ms, 2);
      const cycle_loss = delta_ke * ((1.0 / 0.91) - 0.78);
      const stops_kwh = (num_stops * cycle_loss) / 3.6e6;

      // On-ramp merge acceleration (re-accelerating 5,100 lbs from ramp to 70 mph highway)
      const v_hwy_ms = 70.0 * 0.44704;
      const ramp_ke = 0.5 * total_mass_kg * Math.max(0.0, Math.pow(v_hwy_ms, 2) - Math.pow(v_ms, 2));
      const ramp_accel_kwh = (ramp_ke / 0.91) / 3.6e6;

      // Idle delay (plazas: ~1.2 mins pedestrian/stall entry; off-highway: traffic lights + turns ~2.5 mins/mi)
      const idle_hours = is_plaza ? (1.2 / 60.0) : (Math.max(2.0, detour_miles * 2.4) / 60.0);
      const total_hours = hours + idle_hours;

      let hvac_kw = 0.35;
      if (temp_f < 45) hvac_kw = Math.min(5.2, 0.45 + (0.09 * (45 - temp_f)));
      else if (temp_f > 75) hvac_kw = Math.min(2.8, 0.40 + (0.06 * (temp_f - 75)));
      const aux_kwh = (0.35 + hvac_kw) * total_hours;

      let batt_eff = 1.0;
      if (temp_f < 32) batt_eff = Math.max(0.78, 0.90 - ((32 - temp_f) * 0.0045));
      else if (temp_f < 55) batt_eff = 0.90 + ((temp_f - 32) / 23) * 0.10;

      const total_kwh = ((steady_kwh + stops_kwh + ramp_accel_kwh) / batt_eff) + aux_kwh;
      return {
        kwh: total_kwh,
        hours: total_hours,
        mins: Math.round(total_hours * 60)
      };
    }"""

    new_sim_str = """    function simulateDetourPhysics(detour_miles, is_plaza, payload_lbs, temp_f, road_cond, station_id) {
      const curb_kg = 2233.0;
      const total_mass_kg = curb_kg + (payload_lbs * 0.453592);
      
      const st_db = (window.ROUTE_INTERSECTIONS_DB && window.ROUTE_INTERSECTIONS_DB.stations) ? window.ROUTE_INTERSECTIONS_DB.stations[station_id] : null;
      let v_mph, num_stops, idle_hours;

      if (st_db) {
        const access_type = st_db.access_type || (is_plaza ? 'plaza_standard' : 'off_pike_commercial');
        if (access_type.startsWith('plaza_')) {
          if (access_type === 'plaza_median_bidirectional') {
            v_mph = 22.0;
            num_stops = Math.max(2.0, (st_db.stop_signs_count || 1) + 1.0); // crossover ramp yield + stall stop
            idle_hours = (1.8 / 60.0);
          } else {
            v_mph = 20.0;
            num_stops = Math.max(1.0, st_db.stop_signs_count || 1.0);
            idle_hours = (1.2 / 60.0);
          }
        } else {
          v_mph = 26.0;
          const sig_count = st_db.traffic_signals_count || 0;
          const stop_count = Math.max(1.0, st_db.stop_signs_count || 1.0);
          const rbs_count = st_db.roundabouts_count || 0;

          // Physical signal stop probability ~40%, 32s red dwell; Stop sign 100% stop, 3s dwell; Roundabout 50% yield, 4s dwell
          num_stops = (sig_count * 0.40) + stop_count + (rbs_count * 0.50);
          idle_hours = ((sig_count * 0.40 * 32.0) + (stop_count * 3.0) + (rbs_count * 4.0)) / 3600.0;
        }
      } else {
        v_mph = is_plaza ? 20.0 : 28.0;
        num_stops = is_plaza ? 1.0 : Math.max(2.0, detour_miles * 2.2);
        idle_hours = is_plaza ? (1.2 / 60.0) : (Math.max(2.0, detour_miles * 2.4) / 60.0);
      }

      const v_ms = v_mph * 0.44704;
      const hours = detour_miles / v_mph;
      const dist_m = detour_miles * 1609.34;

      // Local rolling resistance and aero at 20-28 mph
      let crr = 0.0105;
      if (road_cond === "wet") crr *= 1.40;
      else if (road_cond === "snow_ice") crr *= 2.20;
      const f_rr = crr * total_mass_kg * 9.80665;
      const f_spray = (road_cond === "wet") ? (0.5 * 0.35 * 1000.0 * (4 * 0.235) * 0.0005 * Math.pow(v_ms, 2)) : 0.0;

      const temp_c = (temp_f - 32) * 5 / 9;
      const rho = 1.225 * (288.15 / Math.max(240, temp_c + 273.15));
      const f_aero = 0.5 * rho * (0.332 * 2.60) * Math.pow(v_ms, 2);
      const steady_kwh = ((f_rr + f_spray + f_aero) * dist_m) / 3.6e6 / 0.91;

      // Stop-and-go intersection cycles (with regenerative braking: ~78% recovery)
      const delta_ke = 0.5 * total_mass_kg * Math.pow(v_ms, 2);
      const cycle_loss = delta_ke * ((1.0 / 0.91) - 0.78);
      const stops_kwh = (num_stops * cycle_loss) / 3.6e6;

      // On-ramp merge acceleration (re-accelerating 5,100 lbs from ramp to 70 mph highway)
      const v_hwy_ms = 70.0 * 0.44704;
      const ramp_ke = 0.5 * total_mass_kg * Math.max(0.0, Math.pow(v_hwy_ms, 2) - Math.pow(v_ms, 2));
      const ramp_accel_kwh = (ramp_ke / 0.91) / 3.6e6;

      const total_hours = hours + idle_hours;

      let hvac_kw = 0.35;
      if (temp_f < 45) hvac_kw = Math.min(5.2, 0.45 + (0.09 * (45 - temp_f)));
      else if (temp_f > 75) hvac_kw = Math.min(2.8, 0.40 + (0.06 * (temp_f - 75)));
      const aux_kwh = (0.35 + hvac_kw) * total_hours;

      let batt_eff = 1.0;
      if (temp_f < 32) batt_eff = Math.max(0.78, 0.90 - ((32 - temp_f) * 0.0045));
      else if (temp_f < 55) batt_eff = 0.90 + ((temp_f - 32) / 23) * 0.10;

      const total_kwh = ((steady_kwh + stops_kwh + ramp_accel_kwh) / batt_eff) + aux_kwh;
      return {
        kwh: total_kwh,
        hours: total_hours,
        mins: Math.round(total_hours * 60)
      };
    }"""

    old_sim_crlf = old_sim_str.replace("\n", "\r\n")
    new_sim_crlf = new_sim_str.replace("\n", "\r\n")

    if old_sim_crlf in content:
        content = content.replace(old_sim_crlf, new_sim_crlf)
        print(f"Upgraded simulateDetourPhysics in {path}")
    else:
        print(f"Warning: old simulateDetourPhysics not found in {path}")

    # 5. Add loadRouteIntersectionsDatabase
    load_func = """    async function loadRouteIntersectionsDatabase() {
      if (ROUTE_INTERSECTIONS_DB) return ROUTE_INTERSECTIONS_DB;
      const ts = Date.now();
      try {
        const resp = await fetch(`data/route_intersections_db.json?t=${ts}`);
        if (resp.ok) {
          const db = await resp.json();
          window.ROUTE_INTERSECTIONS_DB = db;
          ROUTE_INTERSECTIONS_DB = db;
          console.log(`Loaded OSM route intersections database (${Object.keys(db.stations || {}).length} stations).`);
          return db;
        }
      } catch (e) {
        console.warn("Could not load local data/route_intersections_db.json, trying GitHub raw:", e);
      }
      try {
        const rawUrl = `https://raw.githubusercontent.com/billingsj1/equinox-ev-route-optimizer/main/data/route_intersections_db.json?t=${ts}`;
        const resp2 = await fetch(rawUrl);
        if (resp2.ok) {
          const db = await resp2.json();
          window.ROUTE_INTERSECTIONS_DB = db;
          ROUTE_INTERSECTIONS_DB = db;
          console.log("Loaded route intersections database from GitHub raw.");
          return db;
        }
      } catch (e2) {
        console.warn("Could not load route intersections database from GitHub:", e2);
      }
      return null;
    }
"""
    load_func_crlf = load_func.replace("\n", "\r\n")
    if "async function loadRouteIntersectionsDatabase" not in content:
        target_marker = "    async function loadHolidayOffsetsDatabase() {"
        content = content.replace(target_marker, load_func_crlf + "\r\n" + target_marker)
        print(f"Added loadRouteIntersectionsDatabase to {path}")

    # 6. Add to ENGINE_DATABASES
    old_eng_db = "      { id: 'holidays', name: 'Holiday Congestion', fn: () => loadHolidayOffsetsDatabase() },\r\n"
    new_eng_db = "      { id: 'holidays', name: 'Holiday Congestion', fn: () => loadHolidayOffsetsDatabase() },\r\n      { id: 'intersections', name: 'Intersections & Signals', fn: () => loadRouteIntersectionsDatabase() },\r\n"
    if new_eng_db not in content:
        content = content.replace(old_eng_db, new_eng_db)
        print(f"Added intersections to ENGINE_DATABASES in {path}")

    # 7. Update stationDetours caller in runStage1Search
    old_caller = """            const detourSim = simulateDetourPhysics(detour_miles, isPlaza, payload_lbs, temp_f, road_cond);
            const lastExitSim = simulateDetourPhysics(detour_miles / 2.0, isPlaza, payload_lbs, temp_f, road_cond);"""

    new_caller = """            const detourSim = simulateDetourPhysics(detour_miles, isPlaza, payload_lbs, temp_f, road_cond, st.id);
            const lastExitSim = simulateDetourPhysics(detour_miles / 2.0, isPlaza, payload_lbs, temp_f, road_cond, st.id);
            if (detourSim && detourSim.mins) {
              detour_mins = detourSim.mins;
            }"""

    old_caller_crlf = old_caller.replace("\n", "\r\n")
    new_caller_crlf = new_caller.replace("\n", "\r\n")
    if old_caller_crlf in content:
        content = content.replace(old_caller_crlf, new_caller_crlf)
        print(f"Updated detourSim caller with st.id in {path}")

    # 8. Fix Stage 1 departure time optimization argument
    content = content.replace(
        "runStage1Search(min_leg_mins, max_leg_mins, shouldOptimizeDep,",
        "runStage1Search(min_leg_mins, max_leg_mins, false,"
    )

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)

for p in ["index.html", "public/index.html", "ui/templates/index.html"]:
    if os.path.exists(p):
        update_file(p)

hashes = {}
for p in ["index.html", "public/index.html", "ui/templates/index.html"]:
    with open(p, "rb") as f:
        hashes[p] = hashlib.sha256(f.read()).hexdigest()

print("\nSHA-256 Check:")
for p, h in hashes.items():
    print(f"  {p}: {h}")

if len(set(hashes.values())) == 1:
    print("ALL 3 FILES ARE 100% IDENTICAL!")
else:
    print("MISMATCH DETECTED!")
