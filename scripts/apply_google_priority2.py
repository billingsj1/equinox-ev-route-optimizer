import hashlib

def update_content(content):
    # 1. Update getCalibratedSpeed & getSchuylkillHourlySpeed
    s1 = content.find('// Google Routes Speed Lookup with Normalized Holiday Congestion Offsets')
    e1 = content.find('    function getVineStHourlySpeed')
    assert s1 != -1 and e1 != -1, f"Sentinel 1 not found: s1={s1}, e1={e1}"

    new_block1 = '''// Google Routes Speed Lookup with 30-min rush intervals and normalized holiday congestion
    function getBestHourEntry(hoursObj, hour) {
      if (!hoursObj) return null;
      const clamped = Math.min(23, Math.max(0, hour));
      const halfHour = Math.round(clamped * 2) / 2;
      const halfStr = String(halfHour);
      if (hoursObj[halfStr] && hoursObj[halfStr].traffic_mph != null) {
        return hoursObj[halfStr];
      }
      const intStr = String(Math.round(clamped));
      if (hoursObj[intStr] && hoursObj[intStr].traffic_mph != null) {
        return hoursObj[intStr];
      }
      const floorStr = String(Math.floor(clamped));
      if (hoursObj[floorStr] && hoursObj[floorStr].traffic_mph != null) {
        return hoursObj[floorStr];
      }
      return null;
    }

    const CORRIDOR_KEY_ALIASES = {
      'vinest_east': 'vinest_benfranklin_east',
      'vinest_west': 'vinest_benfranklin_west',
      'columbus_i70_split_east': 'columbus_i70_east',
      'columbus_i70_split_west': 'columbus_i70_west',
      'i276_east': 'i276_paturnpike_east',
      'i276_west': 'i276_paturnpike_west',
      'patp_carlisle_node_east': 'pa_turnpike_east_carlisle',
      'patp_carlisle_node_west': 'pa_turnpike_west_carlisle',
      'patp_allegheny_tunnel_east': 'pa_turnpike_tunnels_east',
      'patp_allegheny_tunnel_west': 'pa_turnpike_tunnels_west',
      'patp_tuscarora_tunnel_east': 'pa_turnpike_tunnels_east',
      'patp_tuscarora_tunnel_west': 'pa_turnpike_tunnels_west',
      'patp_blue_mountain_tunnel_east': 'pa_turnpike_tunnels_east',
      'patp_blue_mountain_tunnel_west': 'pa_turnpike_tunnels_west',
      'i79_bridgeville_north': 'sewickley_i79_north',
      'i79_bridgeville_south': 'sewickley_i79_south',
      'us22_weirton_east': 'sewickley_us22_east',
      'us22_weirton_west': 'sewickley_us22_west'
    };

    function getCalibratedSpeed(key, dow, hour, fallback, dateStr) {
      const lookupKey = (BOTTLENECK_SPEEDS_DB && BOTTLENECK_SPEEDS_DB.corridors && BOTTLENECK_SPEEDS_DB.corridors[key])
        ? key
        : (CORRIDOR_KEY_ALIASES[key] || key);

      // 1. Check if Google Routes DB has this corridor
      if (BOTTLENECK_SPEEDS_DB && BOTTLENECK_SPEEDS_DB.corridors && BOTTLENECK_SPEEDS_DB.corridors[lookupKey]) {
        const cData = BOTTLENECK_SPEEDS_DB.corridors[lookupKey];
        const hKeyObj = dateStr ? getHolidayProfileKey(dateStr) : null;
        const hKey = hKeyObj ? hKeyObj.key : null;

        // A. If holiday date and direct Google holiday profile exists
        if (hKey && cData.dates && cData.dates[hKey]) {
          const directEntry = getBestHourEntry(cData.dates[hKey].hours, hour);
          if (directEntry && directEntry.traffic_mph != null) {
            return directEntry.traffic_mph;
          }
        }

        // B. If holiday date and offsets exist, apply normalized offset multiplier to baseline
        if (hKey && HOLIDAY_OFFSETS_DB && HOLIDAY_OFFSETS_DB.corridors && HOLIDAY_OFFSETS_DB.corridors[lookupKey]) {
          const clamped = Math.min(23, Math.max(0, hour));
          const hStr = String(Math.round(clamped));
          const hOffset = HOLIDAY_OFFSETS_DB.corridors[lookupKey].holidays?.[hKey]?.hours?.[hStr];
          if (hOffset && hOffset.speed_multiplier != null) {
            let bKey = 'baseline_wed';
            if (dow === 0) bKey = 'baseline_sun';
            else if (dow === 1) bKey = 'baseline_mon';
            else if (dow === 5 || dow === 6) bKey = 'baseline_fri';
            
            const baseEntry = getBestHourEntry(cData.dates?.[bKey]?.hours, hour);
            const baseSpd = (baseEntry && baseEntry.traffic_mph != null) ? baseEntry.traffic_mph : fallback;
            const adjustedSpd = Math.round(baseSpd * hOffset.speed_multiplier * 10) / 10;
            return Math.max(12.0, adjustedSpd);
          }
        }

        // C. Non-holiday or direct Google baseline lookup
        let baseProfileKey = 'baseline_wed';
        if (dow === 0) baseProfileKey = 'baseline_sun';
        else if (dow === 1) baseProfileKey = 'baseline_mon';
        else if (dow === 5 || dow === 6) baseProfileKey = 'baseline_fri';

        const gEntry = getBestHourEntry(cData.dates?.[baseProfileKey]?.hours, hour);
        if (gEntry && gEntry.traffic_mph != null) {
          return gEntry.traffic_mph;
        }
      }

      // 2. Fall back to TomTom 168h calibrated speeds
      return getTomTomSpeed(key, dow, hour, fallback);
    }

    function getDirectionalTomTomSpeed(eastOrNorthKey, westOrSouthKey, isEastOrNorth, dow, hour, fallback) {
      const key = isEastOrNorth ? eastOrNorthKey : westOrSouthKey;
      const depDateEl = document.getElementById('departureDate');
      const dateStr = depDateEl ? depDateEl.value : null;
      return getCalibratedSpeed(key, dow, hour, fallback, dateStr);
    }

    function getSchuylkillHourlySpeed(dow, hour, isEastbound, lon) {
      if (isEastbound != null) {
        let eastKey = 'schuylkill_east';
        let westKey = 'schuylkill_west';
        if (lon != null && lon !== 0.0) {
          if (isEastbound) {
            if (lon <= -75.305) eastKey = 'schuylkill_east_slice1';
            else if (lon <= -75.215) eastKey = 'schuylkill_east_slice2';
            else eastKey = 'schuylkill_east_slice3';
          } else {
            if (lon > -75.215) westKey = 'schuylkill_west_slice1';
            else if (lon > -75.305) westKey = 'schuylkill_west_slice2';
            else westKey = 'schuylkill_west_slice3';
          }
        }
        return getDirectionalTomTomSpeed(eastKey, westKey, isEastbound, dow, hour, 49.5);
      }
      return getTomTomSpeed('schuylkill', dow, hour, 49.5);
    }

'''

    content = content[:s1] + new_block1 + content[e1:]

    # 2. In precomputeStepsPhysicsLUT, update Schuylkill call to pass lon
    schuylkill_old = "base_mph = getSchuylkillHourlySpeed(localDayOfWeek, localHourInt, isEastbound);"
    schuylkill_new = "base_mph = getSchuylkillHourlySpeed(localDayOfWeek, localHourFloat, isEastbound, lon);"
    assert schuylkill_old in content, "schuylkill_old not found!"
    content = content.replace(schuylkill_old, schuylkill_new)

    # 3. Locate LUT block first
    lut_start = content.find("function precomputeStepsPhysicsLUT(")
    lut_end = content.find("return {", lut_start)
    assert lut_start != -1 and lut_end != -1, "LUT block not found!"

    # 4. Update Columbus I-70 to micro-slices and add Washington PA I-70 slices inside LUT block
    idx_col = content.find('columbus_i70_split_east', lut_start)
    assert idx_col != -1 and idx_col < lut_end, "columbus_i70_split_east not found inside LUT!"
    line_start = content.rfind('\n', 0, idx_col - 50) + 1
    line_end = content.find('free_flow_mph = 52.8;', idx_col) + len('free_flow_mph = 52.8;')
    columbus_new = """        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -83.10 && lon < -82.80 && lat > 39.92 && lat < 40.00) {\n          let eastKey = (lon < -82.855) ? 'columbus_i70_east_slice1' : 'columbus_i70_east_slice2';\n          let westKey = (lon >= -82.855) ? 'columbus_i70_west_slice1' : 'columbus_i70_west_slice2';\n          base_mph = getDirectionalTomTomSpeed(eastKey, westKey, isEastbound, localDayOfWeek, localHourFloat, posted_speed);\n          free_flow_mph = 52.8;\n        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -80.32 && lon < -80.16 && lat > 40.14 && lat < 40.21) {\n          let eastKey = (lon <= -80.240) ? 'washington_pa_i70_east_slice1' : 'washington_pa_i70_east_slice2';\n          let westKey = (lon > -80.240) ? 'washington_pa_i70_west_slice1' : 'washington_pa_i70_west_slice2';\n          base_mph = getDirectionalTomTomSpeed(eastKey, westKey, isEastbound, localDayOfWeek, localHourFloat, posted_speed);\n          free_flow_mph = 55.0;"""
    content = content[:line_start] + columbus_new + content[line_end:]

    # 5. In precomputeStepsPhysicsLUT, replace remaining 'localDayOfWeek, localHourInt' with 'localDayOfWeek, localHourFloat'
    lut_start = content.find("function precomputeStepsPhysicsLUT(")
    lut_end = content.find("return {", lut_start)
    assert lut_start != -1 and lut_end != -1, "LUT block re-lookup failed!"
    lut_sub = content[lut_start:lut_end]
    lut_sub = lut_sub.replace("localDayOfWeek, localHourInt", "localDayOfWeek, localHourFloat")
    content = content[:lut_start] + lut_sub + content[lut_end:]

    # 6. Update log message in loadBottleneckSpeedsDatabase
    log_old = "console.log(`Loaded Google Routes bottleneck speeds database (28 corridors x 17 hours).`);"
    log_new = "console.log(`Loaded Google Routes bottleneck speeds database (42 corridors/slices x 23 hours/half-hours x 15 dates).`);"
    assert log_old in content, "log_old not found!"
    content = content.replace(log_old, log_new)

    return content

def main():
    with open('index.html', 'r', encoding='utf-8', newline='') as f:
        original = f.read()

    updated = update_content(original)

    files = ['index.html', 'public/index.html', 'ui/templates/index.html']
    for p in files:
        with open(p, 'w', encoding='utf-8', newline='') as f:
            f.write(updated)
        print(f'Wrote {p}')

    # Verify sha256
    hashes = [hashlib.sha256(open(p, 'rb').read()).hexdigest() for p in files]
    print('All files byte-identical?', len(set(hashes)) == 1, hashes[0])

if __name__ == '__main__':
    main()
