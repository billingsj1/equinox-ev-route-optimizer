import hashlib

def main():
    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Add window & var declarations right at the top of the script tag (line 1077)
    top_target = """  <script>
    // --- VERIFIED CHARGING NETWORK DATABASE (CCS1 / >= 100 kW) ---"""

    top_replacement = """  <script>
    // Global Databases for Elevation, Bottlenecks, and Holiday Offsets
    window.CORRIDOR_ELEVATIONS_DB = null;
    window.BOTTLENECK_SPEEDS_DB = null;
    window.HOLIDAY_OFFSETS_DB = null;
    var CORRIDOR_ELEVATIONS_DB = null;
    var BOTTLENECK_SPEEDS_DB = null;
    var HOLIDAY_OFFSETS_DB = null;

    // --- VERIFIED CHARGING NETWORK DATABASE (CCS1 / >= 100 kW) ---"""

    assert top_target in content, "top_target not found"
    content = content.replace(top_target, top_replacement, 1)

    # 2. Update declarations at line 19780 so they don't shadow with 'let'
    decl_target = """    let HERE_TOLLS_DB = null;
    const HERE_TOLL_CACHE = new Map();
    let CORRIDOR_ELEVATIONS_DB = null;
    let BOTTLENECK_SPEEDS_DB = null;
    let HOLIDAY_OFFSETS_DB = null;"""

    decl_replacement = """    let HERE_TOLLS_DB = null;
    const HERE_TOLL_CACHE = new Map();"""

    assert decl_target in content, "decl_target not found"
    content = content.replace(decl_target, decl_replacement, 1)

    # 3. Update loaders to assign to both window and local var
    old_loader = """        if (resp.ok) {
          CORRIDOR_ELEVATIONS_DB = await resp.json();
          console.log(`Loaded Google high-resolution elevation database (71,168 points across 5 corridors).`);
          return CORRIDOR_ELEVATIONS_DB;
        }"""
    new_loader = """        if (resp.ok) {
          const db = await resp.json();
          window.CORRIDOR_ELEVATIONS_DB = db;
          CORRIDOR_ELEVATIONS_DB = db;
          console.log(`Loaded Google high-resolution elevation database (71,168 points across 5 corridors).`);
          return db;
        }"""
    assert old_loader in content, "old_loader not found"
    content = content.replace(old_loader, new_loader, 1)

    old_b_loader = """        if (resp.ok) {
          BOTTLENECK_SPEEDS_DB = await resp.json();
          console.log(`Loaded Google Routes bottleneck speeds database (28 corridors x 17 hours).`);
          return BOTTLENECK_SPEEDS_DB;
        }"""
    new_b_loader = """        if (resp.ok) {
          const db = await resp.json();
          window.BOTTLENECK_SPEEDS_DB = db;
          BOTTLENECK_SPEEDS_DB = db;
          console.log(`Loaded Google Routes bottleneck speeds database (28 corridors x 17 hours).`);
          return db;
        }"""
    assert old_b_loader in content, "old_b_loader not found"
    content = content.replace(old_b_loader, new_b_loader, 1)

    old_h_loader = """        if (resp.ok) {
          HOLIDAY_OFFSETS_DB = await resp.json();
          console.log(`Loaded normalized holiday congestion offsets database.`);
          return HOLIDAY_OFFSETS_DB;
        }"""
    new_h_loader = """        if (resp.ok) {
          const db = await resp.json();
          window.HOLIDAY_OFFSETS_DB = db;
          HOLIDAY_OFFSETS_DB = db;
          console.log(`Loaded normalized holiday congestion offsets database.`);
          return db;
        }"""
    assert old_h_loader in content, "old_h_loader not found"
    content = content.replace(old_h_loader, new_h_loader, 1)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(content)
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(content)
    with open("ui/templates/index.html", "w", encoding="utf-8") as f:
        f.write(content)

    h1 = hashlib.sha256(open("index.html", "rb").read()).hexdigest()
    h2 = hashlib.sha256(open("public/index.html", "rb").read()).hexdigest()
    h3 = hashlib.sha256(open("ui/templates/index.html", "rb").read()).hexdigest()

    print("Fixed global scope in all 3 files!")
    print(f"SHA-256 index.html: {h1}")
    assert h1 == h2 == h3

if __name__ == "__main__":
    main()
