import hashlib

def patch_simulate_detour():
    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()

    target = """          let arterial_spd = 26.0;
          if (station_id === 'ea-carlisle' || station_id === 'carlisle') {
            arterial_spd = getDirectionalTomTomSpeed('carlisle_us11_offshoot_north', 'carlisle_us11_offshoot_south', true, 3, 12, 18.1);
          } else if (station_id === 'evgo-breezewood' || station_id === 'breezewood') {
            arterial_spd = getDirectionalTomTomSpeed('breezewood_us30_offshoot_west', 'breezewood_us30_offshoot_east', true, 3, 12, 17.1);
          } else if (station_id && station_id.includes('irwin')) {
            arterial_spd = getDirectionalTomTomSpeed('irwin_us30_offshoot_west', 'irwin_us30_offshoot_east', true, 3, 12, 15.6);
          } else if (station_id && (station_id.includes('mt-laurel') || station_id.includes('target-mt-laurel'))) {
            arterial_spd = getDirectionalTomTomSpeed('mt_laurel_nj73_arterial_south', 'mt_laurel_nj73_arterial_north', true, 3, 12, 17.9);
          }"""

    replacement = """          let arterial_spd = 26.0;
          const cleanId = (station_id || '').toLowerCase().replace(/[^a-z0-9]/g, '_');
          const inKey = cleanId + '_inbound';
          const outKey = cleanId + '_outbound';
          const tomtomDb = (typeof TOMTOM_CORRIDOR_SPEEDS !== 'undefined') ? TOMTOM_CORRIDOR_SPEEDS : (window.TOMTOM_CORRIDOR_SPEEDS || {});
          if (tomtomDb[inKey] || tomtomDb[outKey]) {
            arterial_spd = getDirectionalTomTomSpeed(inKey, outKey, true, 3, 12, 22.0);
          } else if (station_id === 'ea-carlisle' || station_id === 'carlisle') {
            arterial_spd = getDirectionalTomTomSpeed('carlisle_us11_offshoot_north', 'carlisle_us11_offshoot_south', true, 3, 12, 18.1);
          } else if (station_id === 'evgo-breezewood' || station_id === 'breezewood') {
            arterial_spd = getDirectionalTomTomSpeed('breezewood_us30_offshoot_west', 'breezewood_us30_offshoot_east', true, 3, 12, 17.1);
          } else if (station_id && station_id.includes('irwin')) {
            arterial_spd = getDirectionalTomTomSpeed('irwin_us30_offshoot_west', 'irwin_us30_offshoot_east', true, 3, 12, 15.6);
          } else if (station_id && (station_id.includes('mt-laurel') || station_id.includes('target-mt-laurel'))) {
            arterial_spd = getDirectionalTomTomSpeed('mt_laurel_nj73_arterial_south', 'mt_laurel_nj73_arterial_north', true, 3, 12, 17.9);
          }"""

    assert target in content, "target string not found in index.html!"
    content = content.replace(target, replacement)

    files = ["index.html", "public/index.html", "ui/templates/index.html"]
    for p in files:
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    hashes = [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in files]
    assert len(set(hashes)) == 1, "SHA-256 hash mismatch!"
    print(f"Dynamic charger detour resolution patched! SHA-256: {hashes[0]}")

if __name__ == "__main__":
    patch_simulate_detour()
