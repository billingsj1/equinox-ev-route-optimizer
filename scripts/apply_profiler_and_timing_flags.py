"""
Implements calculation timing profiler with granular checkpoints and flags,
and embeds timing data into simulation history, debug logs, the history modal, and console.
Maintains 100% SHA-256 byte parity across index.html, public/index.html, and ui/templates/index.html.
"""
import hashlib
import os
import re

FILES = [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "index.html"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "templates", "index.html"),
]

def update_html(content: str) -> str:
    # 1. Define CalculationProfiler class near global databases definition (around line 1080)
    profiler_class_def = """    // Global Databases for Elevation, Bottlenecks, and Holiday Offsets
    window.CORRIDOR_ELEVATIONS_DB = null;
    window.BOTTLENECK_SPEEDS_DB = null;
    window.HOLIDAY_OFFSETS_DB = null;
    window.currentCalculationProfiler = null;
    window.lastCalculationTimings = null;

    // HIGH-PRECISION CALCULATION PROFILER & TIMING FLAGS
    class CalculationProfiler {
      constructor(name = "RouteCalculation") {
        this.name = name;
        this.startTime = performance.now();
        this.currentStage = null;
        this.stageStart = this.startTime;
        this.stages = {};
        this.checkpoints = [];
        console.log(`⏱️ [PERF START] Starting ${name} session`);
      }

      startStage(stageName) {
        const now = performance.now();
        if (this.currentStage) {
          this.endStage();
        }
        this.currentStage = stageName;
        this.stageStart = now;
        const totalSoFar = ((now - this.startTime) / 1000).toFixed(3);
        console.log(`⏱️ [PERF STAGE START] ${stageName} (T+${totalSoFar}s)`);
      }

      endStage(stageName) {
        const now = performance.now();
        const name = stageName || this.currentStage;
        if (!name) return;
        const elapsedMs = now - this.stageStart;
        this.stages[name] = (this.stages[name] || 0) + elapsedMs;
        const totalSoFar = ((now - this.startTime) / 1000).toFixed(3);
        this.checkpoints.push({
          stage: name,
          elapsed_ms: Math.round(elapsedMs * 10) / 10,
          elapsed_sec: Math.round(elapsedMs / 10) / 100,
          t_offset_ms: Math.round((now - this.startTime) * 10) / 10
        });
        console.log(`⏱️ [PERF CHECKPOINT] ${name}: ${(elapsedMs / 1000).toFixed(3)}s (Total T+${totalSoFar}s)`);
        this.currentStage = null;
        this.stageStart = now;
      }

      mark(label, meta = {}) {
        const now = performance.now();
        const elapsedFromStart = now - this.startTime;
        console.log(`⏱️ [PERF MARK] ${label}: ${(elapsedFromStart / 1000).toFixed(3)}s`, meta);
        this.checkpoints.push({
          label,
          ...meta,
          t_offset_ms: Math.round(elapsedFromStart * 10) / 10
        });
      }

      finish() {
        if (this.currentStage) {
          this.endStage();
        }
        const totalMs = performance.now() - this.startTime;
        this.totalMs = totalMs;
        this.totalSec = Math.round(totalMs / 10) / 100;

        const summary = {};
        for (const [k, v] of Object.entries(this.stages)) {
          summary[k] = {
            ms: Math.round(v * 10) / 10,
            sec: Math.round(v / 10) / 100,
            pct: totalMs > 0 ? Math.round((v / totalMs) * 1000) / 10 : 0
          };
        }

        console.log(`=======================================================`);
        console.log(`⏱️ [PERF COMPLETE] Total Calculation Time: ${(totalMs / 1000).toFixed(3)}s`);
        for (const [k, s] of Object.entries(summary)) {
          console.log(`   • ${k}: ${s.sec}s (${s.pct}%)`);
        }
        console.log(`=======================================================`);

        const result = {
          total_ms: Math.round(totalMs * 10) / 10,
          total_sec: this.totalSec,
          stages: summary,
          checkpoints: this.checkpoints
        };
        window.lastCalculationTimings = result;
        return result;
      }
    }"""

    target_init = """    // Global Databases for Elevation, Bottlenecks, and Holiday Offsets
    window.CORRIDOR_ELEVATIONS_DB = null;
    window.BOTTLENECK_SPEEDS_DB = null;
    window.HOLIDAY_OFFSETS_DB = null;"""

    if target_init in content:
        content = content.replace(target_init, profiler_class_def, 1)
        print(" [OK] Added CalculationProfiler class definition")
    else:
        print(" [SKIP] CalculationProfiler already present or target not found")

    # 2. Instrument handleSearchRoute()
    target_search = """async function handleSearchRoute() {
      const destText = document.getElementById('destAddress').value.trim();
      const originText = document.getElementById('originAddress').value.trim();
      if (!destText) return;

      const searchBtn = document.getElementById('searchBtn');
      searchBtn.disabled = true;
      searchBtn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i><span>Finding Routes...</span>`;
      lucide.createIcons();

      const auditStatusText = document.getElementById('auditStatusText');
      if (auditStatusText) auditStatusText.innerText = "Finding Corridors...";

      try {
        // Resolve Origin & Destination
        const originGeo = await geocodeAddress(originText || "Columbus, OH");
        const destGeo = await geocodeAddress(destText);"""

    replacement_search = """async function handleSearchRoute() {
      const destText = document.getElementById('destAddress').value.trim();
      const originText = document.getElementById('originAddress').value.trim();
      if (!destText) return;

      const profiler = new CalculationProfiler(`RouteCalculation_${destText}`);
      window.currentCalculationProfiler = profiler;

      const searchBtn = document.getElementById('searchBtn');
      searchBtn.disabled = true;
      searchBtn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i><span>Finding Routes...</span>`;
      lucide.createIcons();

      const auditStatusText = document.getElementById('auditStatusText');
      if (auditStatusText) auditStatusText.innerText = "Finding Corridors...";

      try {
        profiler.startStage("Geocoding & Setup");
        // Resolve Origin & Destination
        const originGeo = await geocodeAddress(originText || "Columbus, OH");
        const destGeo = await geocodeAddress(destText);"""

    if target_search in content:
        content = content.replace(target_search, replacement_search, 1)
        print(" [OK] Instrumented handleSearchRoute() start")
    else:
        print(" [SKIP] handleSearchRoute() start already instrumented")

    # Instrument OSRM stage start:
    target_osrm_start = """        // Fetch Live Road Route via OSRM with full steps & speed metadata
        let routesFound = false;"""
    replacement_osrm_start = """        // Fetch Live Road Route via OSRM with full steps & speed metadata
        profiler.startStage("OSRM Corridors Fetch");
        let routesFound = false;"""
    if target_osrm_start in content:
        content = content.replace(target_osrm_start, replacement_osrm_start, 1)
        print(" [OK] Instrumented OSRM Corridors Fetch stage")

    # Instrument Weather stage start:
    target_weather_start = """        // Pull smart along-route weather (or apply manual override)
        await fetchRouteWeatherData(destText, activeRoutesData[0]);

        await recomputeCurrentRoute();"""
    replacement_weather_start = """        // Pull smart along-route weather (or apply manual override)
        profiler.startStage("Along-Route Weather Engine");
        await fetchRouteWeatherData(destText, activeRoutesData[0]);

        await recomputeCurrentRoute(profiler);"""
    if target_weather_start in content:
        content = content.replace(target_weather_start, replacement_weather_start, 1)
        print(" [OK] Instrumented Along-Route Weather Engine stage")

    # 3. Instrument recomputeCurrentRoute(activeProfiler)
    target_recompute_start = """    async function recomputeCurrentRoute() {
      try {
      if (!activeRoutesData || activeRoutesData.length === 0) {"""
    replacement_recompute_start = """    async function recomputeCurrentRoute(activeProfiler) {
      const profiler = activeProfiler || window.currentCalculationProfiler || new CalculationProfiler("RecalculateRoute");
      window.currentCalculationProfiler = profiler;
      try {
      if (!activeRoutesData || activeRoutesData.length === 0) {"""
    if target_recompute_start in content:
        content = content.replace(target_recompute_start, replacement_recompute_start, 1)
        print(" [OK] Instrumented recomputeCurrentRoute() parameter and profiler attachment")

    # Instrument Non-Stop baseline:
    target_nonstop = """      // Compute Quickest Non-Stop Driving Baseline across active highway corridors
      let fastestNonStop = null;"""
    replacement_nonstop = """      // Compute Quickest Non-Stop Driving Baseline across active highway corridors
      profiler.startStage("Elevation & Baseline Physics");
      let fastestNonStop = null;"""
    if target_nonstop in content:
        content = content.replace(target_nonstop, replacement_nonstop, 1)
        print(" [OK] Instrumented Elevation & Baseline Physics stage")

    # Instrument Station Projection & Detours:
    target_detours = """        const projection = matchStationsToPolyline(route.coordinates);
        let routeStations = projection.matched.slice();"""
    replacement_detours = """        profiler.startStage("Station Projection & Detours");
        const projection = matchStationsToPolyline(route.coordinates);
        let routeStations = projection.matched.slice();"""
    if target_detours in content:
        content = content.replace(target_detours, replacement_detours, 1)
        print(" [OK] Instrumented Station Projection & Detours stage")

    # Instrument Station Leg Physics Matrix:
    target_legs_matrix = """        // Precompute start-to-dest leg
        const startToDestLeg = simulateLegFromSteps(route.steps, 0.0, total_miles, payload_lbs, temp_f, wind_speed, wind_dir, road_cond, sOffset, sCap, route.speed_mph);

        // Precompute station-to-destination legs and detour physics for all corridor stations
        const destLegPerStation = new Array(routeStations.length);"""
    replacement_legs_matrix = """        profiler.startStage("Station Leg Physics Matrix");
        // Precompute start-to-dest leg
        const startToDestLeg = simulateLegFromSteps(route.steps, 0.0, total_miles, payload_lbs, temp_f, wind_speed, wind_dir, road_cond, sOffset, sCap, route.speed_mph);

        // Precompute station-to-destination legs and detour physics for all corridor stations
        const destLegPerStation = new Array(routeStations.length);"""
    if target_legs_matrix in content:
        content = content.replace(target_legs_matrix, replacement_legs_matrix, 1)
        print(" [OK] Instrumented Station Leg Physics Matrix stage")

    # Instrument Forward State Tree search:
    target_forward_tree = """        const queue = [{
          stationIdx: -1,"""
    replacement_forward_tree = """        profiler.startStage("Forward State Tree (Dijkstra/DP)");
        const queue = [{
          stationIdx: -1,"""
    if target_forward_tree in content:
        content = content.replace(target_forward_tree, replacement_forward_tree, 1)
        print(" [OK] Instrumented Forward State Tree stage")

    # Instrument Multi-Param Matrix if applicable:
    target_multiparam = """      // =========================================================================
      // STAGE 2.5: FAST MULTI-PARAM RE-EVALUATION MATRIX"""
    replacement_multiparam = """      // =========================================================================
      // STAGE 2.5: FAST MULTI-PARAM RE-EVALUATION MATRIX
      profiler.startStage("Multi-Param Optimization Matrix");"""
    if target_multiparam in content:
        content = content.replace(target_multiparam, replacement_multiparam, 1)
        print(" [OK] Instrumented Multi-Param Optimization Matrix stage")

    # Instrument UI & Map Rendering:
    target_render = """      // Select fastest, cheapest, balanced according to duration cap and checkbox settings
      applyRouteSelectionFromPool(finalPool, fastestNonStop);
      lastCalculatedInputSignature = getCurrentInputSignature();

      // Automatically record simulation run in persistent session history
      recordSimulationRun(finalPool, fastestNonStop);"""
    replacement_render = """      profiler.startStage("UI & Map Rendering");
      // Select fastest, cheapest, balanced according to duration cap and checkbox settings
      applyRouteSelectionFromPool(finalPool, fastestNonStop);
      lastCalculatedInputSignature = getCurrentInputSignature();

      const timingResult = profiler.finish();
      window.lastCalculationTimings = timingResult;

      // Automatically record simulation run in persistent session history
      recordSimulationRun(finalPool, fastestNonStop, timingResult);"""
    if target_render in content:
        content = content.replace(target_render, replacement_render, 1)
        print(" [OK] Instrumented UI & Map Rendering stage and profiler finish")

    # Instrument Audit Status Bar and Quick Summary to show elapsed time and top stage:
    target_audit_bar = """      // Persistent Audit Bar Completion Update
      if (auditStatusText) auditStatusText.innerText = "Optimization Complete";
      const qSummary = document.getElementById("telemetryQuickSummary");
      if (qSummary) qSummary.innerText = `${uniqueSequencesCount} routes · ${totalItinerariesCount.toLocaleString()} combinations evaluated (${uniqueSequencesMap.size} verified via OSRM)`;"""
    replacement_audit_bar = """      // Persistent Audit Bar Completion Update
      if (auditStatusText) auditStatusText.innerText = "Optimization Complete";
      const topStage = (timingResult && timingResult.stages)
        ? Object.entries(timingResult.stages).sort((a,b) => b[1].ms - a[1].ms)[0]
        : null;
      const topText = topStage ? ` (Top: ${topStage[0]} ${topStage[1].sec}s)` : '';
      const perfSummary = timingResult ? `⏱️ ${timingResult.total_sec}s${topText} · ` : '';
      const qSummary = document.getElementById("telemetryQuickSummary");
      if (qSummary) qSummary.innerText = `${perfSummary}${uniqueSequencesCount} routes · ${totalItinerariesCount.toLocaleString()} combinations evaluated (${uniqueSequencesMap.size} verified via OSRM)`;"""
    if target_audit_bar in content:
        content = content.replace(target_audit_bar, replacement_audit_bar, 1)
        print(" [OK] Instrumented Audit Bar with elapsed timing and top bottleneck stage")

    # 4. Update recordSimulationRun to store timing
    target_record_fn = """    function recordSimulationRun(finalPool, fastestNonStop) {
      try {
        const history = getSimHistory();
        const runId = "sim_" + Date.now();
        const timestamp = new Date().toISOString();"""
    replacement_record_fn = """    function recordSimulationRun(finalPool, fastestNonStop, timingResult) {
      try {
        const history = getSimHistory();
        const runId = "sim_" + Date.now();
        const timestamp = new Date().toISOString();
        const timing = timingResult || window.lastCalculationTimings || null;"""
    if target_record_fn in content:
        content = content.replace(target_record_fn, replacement_record_fn, 1)
        print(" [OK] Updated recordSimulationRun signature for timing")

    target_new_entry = """          summary: {
            total_evaluated_combos: finalPool ? finalPool.length : 0,
            x_stops: calculatedResults?.x_stops,
            y_stops: calculatedResults?.y_stops,
            has_y: calculatedResults?.has_y,
            non_stop_hours: fastestNonStop ? Math.round(fastestNonStop.hours * 100) / 100 : null,
            non_stop_miles: fastestNonStop ? Math.round(fastestNonStop.distance * 10) / 10 : null
          },"""
    replacement_new_entry = """          summary: {
            total_evaluated_combos: finalPool ? finalPool.length : 0,
            x_stops: calculatedResults?.x_stops,
            y_stops: calculatedResults?.y_stops,
            has_y: calculatedResults?.has_y,
            non_stop_hours: fastestNonStop ? Math.round(fastestNonStop.hours * 100) / 100 : null,
            non_stop_miles: fastestNonStop ? Math.round(fastestNonStop.distance * 10) / 10 : null
          },
          timing: timing,"""
    if target_new_entry in content:
        content = content.replace(target_new_entry, replacement_new_entry, 1)
        print(" [OK] Stored timing in newEntry object")

    # 5. Update formatDebugString(entry) to output profiling timings
    target_format_debug = """RESULTS (Fastest Route):
${planLine}  Total Time: ${win.total_hours ? formatHours(win.total_hours) : '--'} (Driving: ${win.drive_hours ? formatHours(win.drive_hours) : '--'}, Charging: ${win.ch_hours ? formatHours(win.ch_hours) : '--'})
  Total Cost: $${win.total_cost ? win.total_cost.toFixed(2) : '--'} (Charging: $${win.ch_cost ? win.ch_cost.toFixed(2) : '0.00'}, Tolls: $${win.toll_cost ? win.toll_cost.toFixed(2) : '0.00'})
  Total Miles: ${win.miles || '--'} mi
  Stops (${(win.stops || []).length}):
${stopsList || '  (None - Non-stop)'}
  All Evaluated Combinations: ${entry.summary?.total_evaluated_combos || '--'}`;"""

    replacement_format_debug = """RESULTS (Fastest Route):
${planLine}  Total Time: ${win.total_hours ? formatHours(win.total_hours) : '--'} (Driving: ${win.drive_hours ? formatHours(win.drive_hours) : '--'}, Charging: ${win.ch_hours ? formatHours(win.ch_hours) : '--'})
  Total Cost: $${win.total_cost ? win.total_cost.toFixed(2) : '--'} (Charging: $${win.ch_cost ? win.ch_cost.toFixed(2) : '0.00'}, Tolls: $${win.toll_cost ? win.toll_cost.toFixed(2) : '0.00'})
  Total Miles: ${win.miles || '--'} mi
  Stops (${(win.stops || []).length}):
${stopsList || '  (None - Non-stop)'}
  All Evaluated Combinations: ${entry.summary?.total_evaluated_combos || '--'}

EXECUTION TIMINGS & BOTTLENECK PROFILING:
  Total Elapsed Calculation Time: ${entry.timing?.total_sec != null ? `${entry.timing.total_sec}s (${entry.timing.total_ms} ms)` : 'N/A'}${entry.timing?.stages ? Object.entries(entry.timing.stages).map(([name, s]) => `\\n  • ${name}: ${s.sec}s (${s.pct}%)`).join('') : ''}`;"""

    if target_format_debug in content:
        content = content.replace(target_format_debug, replacement_format_debug, 1)
        print(" [OK] Updated formatDebugString with execution timings and profiling breakdown")

    # 6. Update renderSimHistoryList to show timing badges and stage grid in modal cards
    target_modal_card = """          <div class="flex items-center gap-2">
            <span class="text-xs font-bold text-white">${destTitle}</span>
            <span class="text-[10px] text-slate-500 font-mono">(${run.inputs.origin} &rarr; ${destSub})</span>
          </div>"""

    replacement_modal_card = """          <div class="flex items-center gap-2">
            <span class="text-xs font-bold text-white">${destTitle}</span>
            <span class="text-[10px] text-slate-500 font-mono">(${run.inputs.origin} &rarr; ${destSub})</span>
            ${run.timing ? `<span class="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded ${run.timing.total_sec > 10 ? 'bg-amber-500/10 text-amber-300 border border-amber-500/30' : 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/30'}"><i data-lucide="clock" class="w-2.5 h-2.5"></i> ${run.timing.total_sec}s</span>` : ''}
          </div>"""

    if target_modal_card in content:
        content = content.replace(target_modal_card, replacement_modal_card, 1)
        print(" [OK] Added timing badge to history modal card header")

    # Also add the stage breakdown grid in the history card:
    target_card_footer = """        <div class="mt-2 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400 font-mono">
          <span>Evaluated Combos: <b class="text-slate-200">${run.summary?.total_evaluated_combos || '--'}</b></span>
          <div class="flex items-center gap-2">"""

    replacement_card_footer = """        ${run.timing && run.timing.stages ? `
          <div class="mt-2 p-2 bg-slate-950/70 rounded border border-slate-800 text-[10px] font-mono text-slate-400">
            <div class="text-slate-300 font-semibold mb-1 flex items-center justify-between">
              <span>⏱️ Calculation Stages Breakdown</span>
              <span class="text-emerald-400 font-bold">${run.timing.total_sec}s Total</span>
            </div>
            <div class="grid grid-cols-2 gap-x-4 gap-y-0.5">
              ${Object.entries(run.timing.stages).map(([name, s]) => `
                <div class="flex justify-between">
                  <span class="truncate">${name}:</span>
                  <span class="text-slate-200 ml-1 font-semibold">${s.sec}s <span class="text-slate-500">(${s.pct}%)</span></span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <div class="mt-2 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400 font-mono">
          <span>Evaluated Combos: <b class="text-slate-200">${run.summary?.total_evaluated_combos || '--'}</b></span>
          <div class="flex items-center gap-2">"""

    if target_card_footer in content:
        content = content.replace(target_card_footer, replacement_card_footer, 1)
        print(" [OK] Added stage profiling grid to history modal card footer")

    return content

def main():
    print("Applying CalculationProfiler and timing instrumentation across all 3 HTML files...")
    with open(FILES[0], "r", encoding="utf-8") as f:
        original = f.read()

    updated = update_html(original)

    for path in FILES:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        h = hashlib.sha256(updated.encode("utf-8")).hexdigest()
        print(f"Written {path} -> SHA256: {h}")

if __name__ == "__main__":
    main()
