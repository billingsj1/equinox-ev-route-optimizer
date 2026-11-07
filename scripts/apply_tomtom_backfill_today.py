import hashlib
import json

def sync_and_patch():
    with open("data/tomtom_corridors_168h.json", "r", encoding="utf-8") as f:
        tomtom_db = json.load(f)

    json_str = json.dumps(tomtom_db, indent=2)

    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update const TOMTOM_CORRIDOR_SPEEDS
    idx_start = content.find("const TOMTOM_CORRIDOR_SPEEDS =")
    assert idx_start != -1
    idx_eq = content.find("=", idx_start)
    idx_end = content.find("};\n", idx_start) + 1
    assert idx_end != -1

    content = content[:idx_eq + 2] + json_str + content[idx_end:]

    # 2. Update getTomTomSpeed to handle 48-slot arrays (half-hour resolution)
    target_fn = """    function getTomTomSpeed(key, dow, hour, fallback) {
      if (!window.TOMTOM_CORRIDOR_SPEEDS && typeof TOMTOM_CORRIDOR_SPEEDS === 'undefined') return fallback;
      const speeds = (typeof TOMTOM_CORRIDOR_SPEEDS !== 'undefined') ? TOMTOM_CORRIDOR_SPEEDS : window.TOMTOM_CORRIDOR_SPEEDS;
      const c = speeds[key];
      if (!c) return fallback;
      const d = c[dow % 7];
      if (!d) return fallback;
      const spd = d[Math.min(23, Math.max(0, hour))];
      return (spd != null && !isNaN(spd)) ? spd : fallback;
    }"""

    replacement_fn = """    function getTomTomSpeed(key, dow, hour, fallback) {
      if (!window.TOMTOM_CORRIDOR_SPEEDS && typeof TOMTOM_CORRIDOR_SPEEDS === 'undefined') return fallback;
      const speeds = (typeof TOMTOM_CORRIDOR_SPEEDS !== 'undefined') ? TOMTOM_CORRIDOR_SPEEDS : window.TOMTOM_CORRIDOR_SPEEDS;
      const c = speeds[key];
      if (!c) return fallback;
      const d = c[dow % 7];
      if (!d) return fallback;
      if (d.length === 48) {
        const idx = Math.min(47, Math.max(0, Math.round(hour * 2)));
        const spd = d[idx];
        return (spd != null && !isNaN(spd)) ? spd : fallback;
      }
      const spd = d[Math.min(23, Math.max(0, Math.round(hour)))];
      return (spd != null && !isNaN(spd)) ? spd : fallback;
    }"""

    assert target_fn in content, "target_fn not found in index.html!"
    content = content.replace(target_fn, replacement_fn)

    files = ["index.html", "public/index.html", "ui/templates/index.html"]
    for p in files:
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    hashes = [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in files]
    assert len(set(hashes)) == 1, "SHA-256 hash mismatch!"
    print(f"Sync & patch successful! SHA-256: {hashes[0]}")

if __name__ == "__main__":
    sync_and_patch()
