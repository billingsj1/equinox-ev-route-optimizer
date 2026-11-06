import hashlib
import json

def update_content(content):
    # 1. Update embedded TOMTOM_CORRIDOR_SPEEDS from data/tomtom_corridors_168h.json
    with open('data/tomtom_corridors_168h.json', 'r', encoding='utf-8') as f:
        tomtom_db = json.load(f)

    json_str = json.dumps(tomtom_db, indent=2)

    idx_start = content.find('const TOMTOM_CORRIDOR_SPEEDS =')
    assert idx_start != -1, "const TOMTOM_CORRIDOR_SPEEDS not found!"
    idx_eq = content.find('=', idx_start)
    idx_end = content.find('};\n', idx_start) + 1
    assert idx_end != -1, "End of TOMTOM_CORRIDOR_SPEEDS not found!"

    content = content[:idx_eq + 2] + json_str + content[idx_end:]

    # 2. Update PA Turnpike Mainline cruising in precomputeStepsPhysicsLUT
    target_mainline = """          } else {
            base_mph = posted_speed; // Mainline PA Turnpike cruising
            free_flow_mph = posted_speed;
          }"""

    replacement_mainline = """          } else if (lon <= -75.40 && lon > -75.98) {
            base_mph = getDirectionalTomTomSpeed('patp_mainline_vf_to_bowmansville_east', 'patp_mainline_vf_to_bowmansville_west', isEastbound, localDayOfWeek, localHourFloat, 65.0);
            free_flow_mph = posted_speed;
          } else if (lon <= -75.98 && lon > -76.885) {
            base_mph = getDirectionalTomTomSpeed('patp_mainline_bowmansville_to_harrisburg_east', 'patp_mainline_bowmansville_to_harrisburg_west', isEastbound, localDayOfWeek, localHourFloat, 68.0);
            free_flow_mph = posted_speed;
          } else if (lon <= -76.885 && lon > -77.130) {
            base_mph = getDirectionalTomTomSpeed('patp_mainline_harrisburg_to_carlisle_east', 'patp_mainline_harrisburg_to_carlisle_west', isEastbound, localDayOfWeek, localHourFloat, 60.0);
            free_flow_mph = posted_speed;
          } else if (lon <= -77.130 && lon > -77.620) {
            base_mph = getDirectionalTomTomSpeed('patp_mainline_carlisle_to_bluemtn_east', 'patp_mainline_carlisle_to_bluemtn_west', isEastbound, localDayOfWeek, localHourFloat, 55.0);
            free_flow_mph = posted_speed;
          } else if (lon <= -77.620 && lon > -78.235) {
            base_mph = getDirectionalTomTomSpeed('patp_mainline_bluemtn_to_breezewood_east', 'patp_mainline_bluemtn_to_breezewood_west', isEastbound, localDayOfWeek, localHourFloat, 55.0);
            free_flow_mph = posted_speed;
          } else if (lon <= -78.235 && lon > -79.075) {
            base_mph = getDirectionalTomTomSpeed('patp_mainline_breezewood_to_somerset_east', 'patp_mainline_breezewood_to_somerset_west', isEastbound, localDayOfWeek, localHourFloat, 65.0);
            free_flow_mph = posted_speed;
          } else if (lon <= -79.075 && lon > -79.590) {
            base_mph = getDirectionalTomTomSpeed('patp_mainline_somerset_to_newstanton_east', 'patp_mainline_somerset_to_newstanton_west', isEastbound, localDayOfWeek, localHourFloat, 58.0);
            free_flow_mph = posted_speed;
          } else {
            base_mph = posted_speed; // Mainline PA Turnpike cruising
            free_flow_mph = posted_speed;
          }"""

    assert target_mainline in content, "target_mainline not found!"
    content = content.replace(target_mainline, replacement_mainline)

    # 3. Update Mid-County Interchange in precomputeStepsPhysicsLUT
    target_midcounty = """          } else if (sRef.includes('276') || sName.includes('delaware river') || (lon > -75.40 && lon < -74.74 && lat > 40.05 && lat < 40.20)) {
            base_mph = getI276HourlySpeed(localDayOfWeek, localHourFloat, isEastbound); // PA Turnpike East Extension
            free_flow_mph = 64.0;"""

    replacement_midcounty = """          } else if (sRef.includes('276') || sName.includes('delaware river') || (lon > -75.40 && lon < -74.74 && lat > 40.05 && lat < 40.20)) {
            if (lon > -75.34 && lon < -75.28) {
              base_mph = getDirectionalTomTomSpeed('midcounty_i276_i476_east', 'midcounty_i276_i476_west', isEastbound, localDayOfWeek, localHourFloat, 30.0);
            } else {
              base_mph = getI276HourlySpeed(localDayOfWeek, localHourFloat, isEastbound); // PA Turnpike East Extension
            }
            free_flow_mph = 64.0;"""

    assert target_midcounty in content, "target_midcounty not found!"
    content = content.replace(target_midcounty, replacement_midcounty)

    # 4. Update simulateDetourPhysics with empirical offshoot speeds
    target_detour = """          v_mph = 26.0;
          const sig_count = st_db.traffic_signals_count || 0;"""

    replacement_detour = """          let arterial_spd = 26.0;
          if (station_id === 'ea-carlisle' || station_id === 'carlisle') {
            arterial_spd = getDirectionalTomTomSpeed('carlisle_us11_offshoot_north', 'carlisle_us11_offshoot_south', true, 3, 12, 18.1);
          } else if (station_id === 'evgo-breezewood' || station_id === 'breezewood') {
            arterial_spd = getDirectionalTomTomSpeed('breezewood_us30_offshoot_west', 'breezewood_us30_offshoot_east', true, 3, 12, 17.1);
          } else if (station_id && station_id.includes('irwin')) {
            arterial_spd = getDirectionalTomTomSpeed('irwin_us30_offshoot_west', 'irwin_us30_offshoot_east', true, 3, 12, 15.6);
          } else if (station_id && (station_id.includes('mt-laurel') || station_id.includes('target-mt-laurel'))) {
            arterial_spd = getDirectionalTomTomSpeed('mt_laurel_nj73_arterial_south', 'mt_laurel_nj73_arterial_north', true, 3, 12, 17.9);
          }
          v_mph = arterial_spd;
          const sig_count = st_db.traffic_signals_count || 0;"""

    assert target_detour in content, "target_detour not found!"
    content = content.replace(target_detour, replacement_detour)

    return content

def main():
    with open('index.html', 'r', encoding='utf-8') as f:
        original = f.read()

    updated = update_content(original)

    files = ['index.html', 'public/index.html', 'ui/templates/index.html']
    for p in files:
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(updated)
        print(f'Wrote {p}')

    hashes = [hashlib.sha256(open(p, 'rb').read()).hexdigest() for p in files]
    print('All files byte-identical?', len(set(hashes)) == 1, hashes[0])

if __name__ == '__main__':
    main()
