import re
import sys

def apply_phase1():
    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update queue initialization and helper getRouteStops
    target_queue_init = """        profiler.startStage("Forward State Tree (Dijkstra/DP)");
        const queue = [{
          stationIdx: -1,
          mile: 0.0,
          soc: start_soc,
          pack_temp_f: initialPackTemp,
          drive_hrs: 0.0,
          ch_hrs: 0.0,
          ch_cost: 0.0,
          stops: [],
          has_decamilla: false
        }];
        let queueHead = 0;
        let queueIterCount = 0;
        const paretoFrontier = new Map();"""

    replacement_queue_init = """        profiler.startStage("Forward State Tree (Dijkstra/DP)");
        function getRouteStops(state) {
          const stops = [];
          let s = state;
          while (s && s.lastStop) {
            stops.push(s.lastStop);
            s = s.parent;
          }
          stops.reverse();
          return stops;
        }

        const queue = [{
          stationIdx: -1,
          mile: 0.0,
          soc: start_soc,
          pack_temp_f: initialPackTemp,
          drive_hrs: 0.0,
          ch_hrs: 0.0,
          ch_cost: 0.0,
          stopsCount: 0,
          lastStop: null,
          parent: null,
          has_decamilla: false
        }];
        let queueHead = 0;
        let queueIterCount = 0;
        const paretoFrontier = new Map();"""

    assert target_queue_init in content, "target_queue_init not found in index.html"
    content = content.replace(target_queue_init, replacement_queue_init, 1)
    print(" [OK] 1. Replaced queue initialization with pointer-based state")

    # 2. Update destination reachability check to reconstruct stops lazily
    target_dest_reach = """          if (canReachDest && final_soc >= (target_arrival_soc - 0.015) && leg_to_dest_mins <= max_mins) {
            if (curr.stops.length === 0 || leg_to_dest_mins >= 30.0) {
              const has_ea_preowned = document.getElementById('hasEaPass') ? document.getElementById('hasEaPass').checked : false;
              const has_tesla_preowned = document.getElementById('hasTeslaMember') ? document.getElementById('hasTeslaMember').checked : false;

              let ea_kwh = 0, ea_gross_savings = 0;
              let tesla_kwh = 0, tesla_gross_savings = 0;

              let cum_time_s1 = 0.0;
              curr.stops.forEach(sp => {
                cum_time_s1 += sp.leg_drive_hrs;
                const arr_clock_dec = departure_hours + cum_time_s1;
                if (sp.station.ea_pass) {
                  ea_kwh += sp.added_kwh;
                  ea_gross_savings += (sp.added_kwh * (sp.station.on * 0.25));
                }
                if (isTeslaNetwork(sp.station.network)) {
                  const non_mem = resolveStationTariff(sp.station, arr_clock_dec, false);
                  const mem = resolveStationTariff(sp.station, arr_clock_dec, true);
                  if (non_mem.rate > mem.rate) {
                    tesla_kwh += sp.added_kwh;
                    tesla_gross_savings += (sp.added_kwh * (non_mem.rate - mem.rate));
                  }
                }
                cum_time_s1 += (sp.mins / 60.0);
              });

              const ea_active = has_ea_preowned || (ea_gross_savings >= 3.50);
              const ea_fee = has_ea_preowned ? 0.0 : (ea_active ? 3.50 : 0.0);
              const ea_net = ea_gross_savings - ea_fee;

              const tesla_active = has_tesla_preowned || (tesla_gross_savings >= 6.50);
              const tesla_fee = has_tesla_preowned ? 0.0 : (tesla_active ? 6.50 : 0.0);
              const tesla_net = tesla_gross_savings - tesla_fee;

              let discounted_ch_cost = 0;
              let cum_time_stops = 0.0;
              const finalStops = curr.stops.map(sp => {"""

    replacement_dest_reach = """          if (canReachDest && final_soc >= (target_arrival_soc - 0.015) && leg_to_dest_mins <= max_mins) {
            if (curr.stopsCount === 0 || leg_to_dest_mins >= 30.0) {
              const currStops = getRouteStops(curr);
              const has_ea_preowned = document.getElementById('hasEaPass') ? document.getElementById('hasEaPass').checked : false;
              const has_tesla_preowned = document.getElementById('hasTeslaMember') ? document.getElementById('hasTeslaMember').checked : false;

              let ea_kwh = 0, ea_gross_savings = 0;
              let tesla_kwh = 0, tesla_gross_savings = 0;

              let cum_time_s1 = 0.0;
              currStops.forEach(sp => {
                cum_time_s1 += sp.leg_drive_hrs;
                const arr_clock_dec = departure_hours + cum_time_s1;
                if (sp.station.ea_pass) {
                  ea_kwh += sp.added_kwh;
                  ea_gross_savings += (sp.added_kwh * (sp.station.on * 0.25));
                }
                if (isTeslaNetwork(sp.station.network)) {
                  const non_mem = resolveStationTariff(sp.station, arr_clock_dec, false);
                  const mem = resolveStationTariff(sp.station, arr_clock_dec, true);
                  if (non_mem.rate > mem.rate) {
                    tesla_kwh += sp.added_kwh;
                    tesla_gross_savings += (sp.added_kwh * (non_mem.rate - mem.rate));
                  }
                }
                cum_time_s1 += (sp.mins / 60.0);
              });

              const ea_active = has_ea_preowned || (ea_gross_savings >= 3.50);
              const ea_fee = has_ea_preowned ? 0.0 : (ea_active ? 3.50 : 0.0);
              const ea_net = ea_gross_savings - ea_fee;

              const tesla_active = has_tesla_preowned || (tesla_gross_savings >= 6.50);
              const tesla_fee = has_tesla_preowned ? 0.0 : (tesla_active ? 6.50 : 0.0);
              const tesla_net = tesla_gross_savings - tesla_fee;

              let discounted_ch_cost = 0;
              let cum_time_stops = 0.0;
              const finalStops = currStops.map(sp => {"""

    assert target_dest_reach in content, "target_dest_reach not found in index.html"
    content = content.replace(target_dest_reach, replacement_dest_reach, 1)
    print(" [OK] 2. Replaced destination reachability stop reconstruction")

    # 3. Update candidate stopTollObj and final_leg_miles
    target_cand_toll = """              const stopTollObj = resolveCandidateToll(route.origin, route.destination, route, curr.stops, null);
              const stopToll = (stopTollObj && stopTollObj.total != null) ? stopTollObj.total : route.toll;
              const total_time = total_drive_hrs + curr.ch_hrs;
              const total_cost = Math.round((discounted_ch_cost + membership_fees + stopToll) * 100) / 100;

              const final_leg_miles = curr.stops.length === 0 ? total_miles : Math.round((total_miles - curr.stops[curr.stops.length - 1].mile) * 10) / 10;"""

    replacement_cand_toll = """              const stopTollObj = resolveCandidateToll(route.origin, route.destination, route, currStops, null);
              const stopToll = (stopTollObj && stopTollObj.total != null) ? stopTollObj.total : route.toll;
              const total_time = total_drive_hrs + curr.ch_hrs;
              const total_cost = Math.round((discounted_ch_cost + membership_fees + stopToll) * 100) / 100;

              const final_leg_miles = curr.stopsCount === 0 ? total_miles : Math.round((total_miles - curr.lastStop.mile) * 10) / 10;"""

    assert target_cand_toll in content, "target_cand_toll not found in index.html"
    content = content.replace(target_cand_toll, replacement_cand_toll, 1)
    print(" [OK] 3. Replaced candidate toll and final leg miles using currStops & curr.lastStop")

    # 4. Update max_stops_budget check
    target_budget = """          if (leg_to_dest_mins < 30.0) continue;
          const max_stops_budget = Math.max(5, Math.ceil(total_miles / 85.0));
          if (curr.stops.length >= max_stops_budget) continue;"""

    replacement_budget = """          if (leg_to_dest_mins < 30.0) continue;
          const max_stops_budget = Math.max(5, Math.ceil(total_miles / 85.0));
          if (curr.stopsCount >= max_stops_budget) continue;"""

          
    assert target_budget in content, "target_budget not found in index.html"
    content = content.replace(target_budget, replacement_budget, 1)
    print(" [OK] 4. Replaced max_stops_budget check with curr.stopsCount")

    # 5. Precompute Station Anchors and Station Ambient Temps in Station Leg Physics Matrix
    target_matrix_precomp = """        for (let i = 0; i < routeStations.length; i++) {
          stationToStationLegs[i] = new Array(routeStations.length);
          for (let j = i + 1; j < routeStations.length; j++) {
            const isToOrFromDecamilla = routeStations[i].is_decamilla || routeStations[j].is_decamilla;
            const minGapMiles = isToOrFromDecamilla ? 0.1 : 5.0;
            if (routeStations[j].mile > routeStations[i].mile + minGapMiles) {
              stationToStationLegs[i][j] = simulateLegFromSteps(route.steps, routeStations[i].mile, routeStations[j].mile, payload_lbs, temp_f, wind_speed, wind_dir, road_cond, sOffset, sCap, route.speed_mph);
            }
          }
        }"""

    replacement_matrix_precomp = """        for (let i = 0; i < routeStations.length; i++) {
          stationToStationLegs[i] = new Array(routeStations.length);
          for (let j = i + 1; j < routeStations.length; j++) {
            const isToOrFromDecamilla = routeStations[i].is_decamilla || routeStations[j].is_decamilla;
            const minGapMiles = isToOrFromDecamilla ? 0.1 : 5.0;
            if (routeStations[j].mile > routeStations[i].mile + minGapMiles) {
              stationToStationLegs[i][j] = simulateLegFromSteps(route.steps, routeStations[i].mile, routeStations[j].mile, payload_lbs, temp_f, wind_speed, wind_dir, road_cond, sOffset, sCap, route.speed_mph);
            }
          }
        }

        // Precompute downstream anchors and ambient temperatures per station (Zero-loss accuracy)
        const stationTargetAnchors = new Array(routeStations.length);
        const stationAmbientTemps = new Array(routeStations.length);
        const isManualWeather = (typeof document !== 'undefined' && document.getElementById('manualWeatherOverride')?.checked);

        for (let j = 0; j < routeStations.length; j++) {
          const st = routeStations[j];
          let arrTemp = temp_f;
          if (window.activeWeatherReport && !isManualWeather) {
            const wpSt = getRouteWeatherAtMile(st.mile);
            if (wpSt && wpSt.ambient_temp_f != null) arrTemp = wpSt.ambient_temp_f;
          }
          stationAmbientTemps[j] = arrTemp;

          const legToDestFromSt = destLegPerStation[j];
          const dest_mins_from_st = legToDestFromSt.hours * 60.0;
          const dest_needed_soc = (legToDestFromSt.kwh / 85.0) + target_arrival_soc;
          let finishTarget = null;
          if (dest_mins_from_st <= max_mins && dest_needed_soc <= 0.90) {
            finishTarget = Math.ceil(dest_needed_soc * 100 - 1e-9) / 100.0;
          }

          const downstreamAnchors = [];
          for (let k = j + 1; k < routeStations.length; k++) {
            const nextLegSim = stationToStationLegs[j][k];
            if (!nextLegSim) continue;
            const nextLegMins = nextLegSim.hours * 60.0;
            const isToOrFromDecamillaK = st.is_decamilla || routeStations[k].is_decamilla;
            const satisfiesMinMins = isToOrFromDecamillaK || (nextLegMins >= min_mins);
            if (satisfiesMinMins && nextLegMins <= max_mins) {
              const nextDetour = stationDetours[k];
              const totalEnergyToK = nextLegSim.kwh + (nextDetour.kwh / 2.0);
              const exactTgtK = Math.ceil(((totalEnergyToK / 85.0) + min_buffer_soc) * 100 - 1e-9) / 100.0;
              if (exactTgtK <= 0.90) {
                downstreamAnchors.push(exactTgtK);
              }
            }
          }

          stationTargetAnchors[j] = {
            finishTarget: finishTarget,
            downstreamAnchors: downstreamAnchors
          };
        }"""

    assert target_matrix_precomp in content, "target_matrix_precomp not found in index.html"
    content = content.replace(target_matrix_precomp, replacement_matrix_precomp, 1)
    print(" [OK] 5. Added precomputation of stationTargetAnchors and stationAmbientTemps")

    # 6. Update DeCamilla stopPlan from_label and queue.push
    target_decamilla_push = """                from_label: curr.stops.length === 0 ? "from Start" : `from Stop ${curr.stops.length}`,
                is_plaza: true,
                detour_mi: 0,
                detour_miles: 0,
                detour_mins: 0,
                arr_soc: Math.round(arr_soc * 100),
                tgt_soc: Math.round(target_soc * 100),
                added_kwh: added_kwh,
                charge_mins: stop_mins,
                setup_mins: 0,
                has_plug_and_go: false,
                mins: stop_mins,
                cost: 0.0,
                rate: 0.0,
                badge: "Free (Private L2)",
                is_decamilla: true
              };

              const postDeCamillaPackTemp = Math.max(arrTemp, Math.min(75.0, arrPackTemp + 5.0));
              queue.push({
                stationIdx: j,
                mile: st.mile,
                soc: target_soc,
                pack_temp_f: postDeCamillaPackTemp,
                drive_hrs: leg_drive_hrs,
                ch_hrs: leg_ch_hrs,
                ch_cost: leg_total_cost,
                stops: [...curr.stops, stopPlan],
                has_decamilla: true
              });"""

    replacement_decamilla_push = """                from_label: curr.stopsCount === 0 ? "from Start" : `from Stop ${curr.stopsCount}`,
                is_plaza: true,
                detour_mi: 0,
                detour_miles: 0,
                detour_mins: 0,
                arr_soc: Math.round(arr_soc * 100),
                tgt_soc: Math.round(target_soc * 100),
                added_kwh: added_kwh,
                charge_mins: stop_mins,
                setup_mins: 0,
                has_plug_and_go: false,
                mins: stop_mins,
                cost: 0.0,
                rate: 0.0,
                badge: "Free (Private L2)",
                is_decamilla: true
              };

              const postDeCamillaPackTemp = Math.max(arrTemp, Math.min(75.0, arrPackTemp + 5.0));
              queue.push({
                stationIdx: j,
                mile: st.mile,
                soc: target_soc,
                pack_temp_f: postDeCamillaPackTemp,
                drive_hrs: leg_drive_hrs,
                ch_hrs: leg_ch_hrs,
                ch_cost: leg_total_cost,
                stopsCount: curr.stopsCount + 1,
                lastStop: stopPlan,
                parent: curr,
                has_decamilla: true
              });"""

    assert target_decamilla_push in content, "target_decamilla_push not found in index.html"
    content = content.replace(target_decamilla_push, replacement_decamilla_push, 1)
    print(" [OK] 6. Updated DeCamilla from_label and pointer-based queue.push")

    # 7. Use precomputed stationAmbientTemps in loop
    target_arr_temp = """            // Ultium Battery Thermal & Dynamic Preconditioning for DC Fast Chargers
            let precond_kwh = 0.0;
            let arrTemp = temp_f;
            if (window.activeWeatherReport && !document.getElementById('manualWeatherOverride')?.checked) {
              const wpSt = getRouteWeatherAtMile(st.mile);
              if (wpSt && wpSt.ambient_temp_f != null) arrTemp = wpSt.ambient_temp_f;
            }"""

    replacement_arr_temp = """            // Ultium Battery Thermal & Dynamic Preconditioning for DC Fast Chargers
            let precond_kwh = 0.0;
            const arrTemp = stationAmbientTemps[j];"""

    assert target_arr_temp in content, "target_arr_temp not found in index.html"
    content = content.replace(target_arr_temp, replacement_arr_temp, 1)
    print(" [OK] 7. Replaced repeated weather lookup with O(1) stationAmbientTemps[j]")

    # 8. Fast target generation using precomputed anchors + deduplication
    target_targets_gen = """            const targetSet = new Set();
            // 1. Strict floor target (1% precision)
            targetSet.add(min_target_allowed);

            // 2. Exact finish target to destination (ensuring it satisfies the minimum charge floor)
            if (dest_mins_from_st <= max_mins && dest_needed_soc <= 0.90) {
              const tgtFinish = Math.ceil(Math.max(min_target_allowed, dest_needed_soc) * 100 - 1e-9) / 100.0;
              if (tgtFinish <= 0.90) targetSet.add(tgtFinish);
            }

            // 3. Exact reach-next anchors to downstream reachable stations along this corridor (Tier 1 Smart Anchors)
            for (let k = j + 1; k < routeStations.length; k++) {
              const nextLegSim = stationToStationLegs[j][k];
              if (!nextLegSim) continue;
              const nextLegMins = nextLegSim.hours * 60.0;
              const isToOrFromDecamillaK = st.is_decamilla || routeStations[k].is_decamilla;
              const satisfiesMinMins = isToOrFromDecamillaK || (nextLegMins >= min_mins);
              if (satisfiesMinMins && nextLegMins <= max_mins) {
                const nextDetour = stationDetours[k];
                const totalEnergyToK = nextLegSim.kwh + (nextDetour.kwh / 2.0);
                // Round UP (ceil): arriving at k at >= buffer. Raise to the min-charge floor if needed.
                const exactTgtK = Math.max(min_target_allowed, Math.ceil(((totalEnergyToK / 85.0) + min_buffer_soc) * 100 - 1e-9) / 100.0);
                if (exactTgtK <= 0.90) targetSet.add(exactTgtK);
              }
            }

            // 4. Strategic standard SoC milestones above the floor (up to 90%)
            const startStep = Math.ceil(min_target_allowed * 20.0) / 20.0;
            for (let t = startStep; t <= 0.901; t += 0.05) {
              targetSet.add(Math.round(t * 100) / 100.0);
            }

            const has_plug_and_go = (st.gm || st.network === "IONNA" || st.network === "EVgo" || st.network === "ChargePoint");
            const setup_mins = has_plug_and_go ? 1.0 : 3.0;
            const arrival_clock_decimal = departure_hours + curr.drive_hrs + curr.ch_hrs + total_leg_hrs;
            const stage1Tariff = resolveStationTariff(st, timeAgnosticBaseline ? 12.0 : arrival_clock_decimal, false);
            const rate = timeAgnosticBaseline ? (st.on || stage1Tariff.rate) : stage1Tariff.rate;

            const targetList = Array.from(targetSet).sort((a, b) => a - b);"""

    replacement_targets_gen = """            // Fast target generation using precomputed anchors + deduplication (Zero-loss accuracy)
            const targets = [min_target_allowed];
            const anchors = stationTargetAnchors[j];
            if (anchors.finishTarget != null) {
              const tgtFinish = Math.max(min_target_allowed, anchors.finishTarget);
              if (tgtFinish <= 0.90) targets.push(tgtFinish);
            }
            for (let aIdx = 0; aIdx < anchors.downstreamAnchors.length; aIdx++) {
              const exactTgtK = Math.max(min_target_allowed, anchors.downstreamAnchors[aIdx]);
              if (exactTgtK <= 0.90) targets.push(exactTgtK);
            }
            const startStep = Math.ceil(min_target_allowed * 20.0) / 20.0;
            for (let t = startStep; t <= 0.901; t += 0.05) {
              targets.push(Math.round(t * 100) / 100.0);
            }
            targets.sort((a, b) => a - b);
            const targetList = [];
            for (let tIdx = 0; tIdx < targets.length; tIdx++) {
              if (tIdx === 0 || targets[tIdx] !== targets[tIdx - 1]) {
                targetList.push(targets[tIdx]);
              }
            }

            const has_plug_and_go = (st.gm || st.network === "IONNA" || st.network === "EVgo" || st.network === "ChargePoint");
            const setup_mins = has_plug_and_go ? 1.0 : 3.0;
            const arrival_clock_decimal = departure_hours + curr.drive_hrs + curr.ch_hrs + total_leg_hrs;
            const stage1Tariff = resolveStationTariff(st, timeAgnosticBaseline ? 12.0 : arrival_clock_decimal, false);
            const rate = timeAgnosticBaseline ? (st.on || stage1Tariff.rate) : stage1Tariff.rate;"""

    assert target_targets_gen in content, "target_targets_gen not found in index.html"
    content = content.replace(target_targets_gen, replacement_targets_gen, 1)
    print(" [OK] 8. Replaced O(N) downstream loop with precomputed anchors and array deduplication")

    # 9. Fast numeric Pareto key, in-place frontier mutation, from_label, and pointer queue.push
    target_pareto_and_push = """              // Pareto State Dominance Pruning (scoped to exact station and 5% target SoC)
              const stateKey = `${st.id || st.name}_${curr.stops.length + 1}_${Math.round(target_soc * 100)}_${curr.has_decamilla ? 1 : 0}`;
              if (!paretoFrontier.has(stateKey)) {
                paretoFrontier.set(stateKey, []);
              }
              const frontier = paretoFrontier.get(stateKey);
              let dominated = false;
              for (let fIdx = 0; fIdx < frontier.length; fIdx++) {
                const prev = frontier[fIdx];
                if (prev.t <= (leg_total_hrs + 0.01) && prev.c <= (leg_total_cost + 0.05)) {
                  dominated = true;
                  break;
                }
              }
              if (dominated) continue;

              const filtered = frontier.filter(p => !(leg_total_hrs <= p.t && leg_total_cost <= p.c));
              filtered.push({ t: leg_total_hrs, c: leg_total_cost });
              paretoFrontier.set(stateKey, filtered);

              const stopPlan = {
                station: st,
                mile: st.mile,
                arr_clock_dec: arrival_clock_decimal,
                leg_drive_hrs: total_leg_hrs,
                leg_drive_mins: Math.round(total_leg_hrs * 60.0),
                leg_miles: (curr.stationIdx === -1) ? Math.round(st.mile * 10) / 10 : Math.round((st.mile - routeStations[curr.stationIdx].mile) * 10) / 10,
                from_label: curr.stops.length === 0 ? "from Start" : `from Stop ${curr.stops.length}`,
                is_plaza: isPlaza,
                detour_mi: st.detour_mi || 0,
                detour_miles: detour_miles,
                detour_mins: detour_mins,
                arr_soc: Math.round(arr_soc * 100),
                tgt_soc: Math.round(target_soc * 100),
                added_kwh: Math.round(ch.added_kwh * 10) / 10,
                charge_mins: Math.round(ch.mins),
                setup_mins: setup_mins,
                has_plug_and_go: has_plug_and_go,
                mins: total_stop_mins,
                cost: Math.round(ch.cost * 100) / 100,
                rate: rate
              };

              const postChargePackTemp = Math.max(95.0, arrTemp);
              queue.push({
                stationIdx: j,
                mile: st.mile,
                soc: target_soc,
                pack_temp_f: postChargePackTemp,
                drive_hrs: leg_drive_hrs,
                ch_hrs: leg_ch_hrs,
                ch_cost: leg_total_cost,
                stops: [...curr.stops, stopPlan],
                has_decamilla: curr.has_decamilla
              });"""

    replacement_pareto_and_push = """              // Pareto State Dominance Pruning (Fast 32-bit numeric key + in-place mutation)
              const stateKey = (j * 100000) + ((curr.stopsCount + 1) * 10000) + (Math.round(target_soc * 100) * 10) + (curr.has_decamilla ? 1 : 0);
              if (!paretoFrontier.has(stateKey)) {
                paretoFrontier.set(stateKey, []);
              }
              const frontier = paretoFrontier.get(stateKey);
              let dominated = false;
              for (let fIdx = 0; fIdx < frontier.length; fIdx++) {
                const prev = frontier[fIdx];
                if (prev.t <= (leg_total_hrs + 0.01) && prev.c <= (leg_total_cost + 0.05)) {
                  dominated = true;
                  break;
                }
              }
              if (dominated) continue;

              let writeIdx = 0;
              for (let fIdx = 0; fIdx < frontier.length; fIdx++) {
                const p = frontier[fIdx];
                if (!(leg_total_hrs <= p.t && leg_total_cost <= p.c)) {
                  frontier[writeIdx++] = p;
                }
              }
              frontier.length = writeIdx;
              frontier.push({ t: leg_total_hrs, c: leg_total_cost });

              const stopPlan = {
                station: st,
                mile: st.mile,
                arr_clock_dec: arrival_clock_decimal,
                leg_drive_hrs: total_leg_hrs,
                leg_drive_mins: Math.round(total_leg_hrs * 60.0),
                leg_miles: (curr.stationIdx === -1) ? Math.round(st.mile * 10) / 10 : Math.round((st.mile - routeStations[curr.stationIdx].mile) * 10) / 10,
                from_label: curr.stopsCount === 0 ? "from Start" : `from Stop ${curr.stopsCount}`,
                is_plaza: isPlaza,
                detour_mi: st.detour_mi || 0,
                detour_miles: detour_miles,
                detour_mins: detour_mins,
                arr_soc: Math.round(arr_soc * 100),
                tgt_soc: Math.round(target_soc * 100),
                added_kwh: Math.round(ch.added_kwh * 10) / 10,
                charge_mins: Math.round(ch.mins),
                setup_mins: setup_mins,
                has_plug_and_go: has_plug_and_go,
                mins: total_stop_mins,
                cost: Math.round(ch.cost * 100) / 100,
                rate: rate
              };

              const postChargePackTemp = Math.max(95.0, arrTemp);
              queue.push({
                stationIdx: j,
                mile: st.mile,
                soc: target_soc,
                pack_temp_f: postChargePackTemp,
                drive_hrs: leg_drive_hrs,
                ch_hrs: leg_ch_hrs,
                ch_cost: leg_total_cost,
                stopsCount: curr.stopsCount + 1,
                lastStop: stopPlan,
                parent: curr,
                has_decamilla: curr.has_decamilla
              });"""

    assert target_pareto_and_push in content, "target_pareto_and_push not found in index.html"
    content = content.replace(target_pareto_and_push, replacement_pareto_and_push, 1)
    print(" [OK] 9. Replaced numeric Pareto key, in-place mutation, and pointer-based queue.push")

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully wrote updated index.html!")

if __name__ == "__main__":
    apply_phase1()
