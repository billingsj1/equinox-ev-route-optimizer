import hashlib

def patch_columbus_slice2():
    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()

    target = """        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -83.10 && lon <= -82.855 && lat > 39.92 && lat < 40.05) {
          base_mph = getDirectionalTomTomSpeed('columbus_i70_east_slice1', 'columbus_i70_west_slice1', isEastbound, localDayOfWeek, localHourFloat, posted_speed);
          free_flow_mph = 52.8;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -82.855 && lon <= -82.012 && lat > 39.85 && lat < 40.10) {
          base_mph = getDirectionalTomTomSpeed('columbus_to_zanesville_east', 'columbus_to_zanesville_west', isEastbound, localDayOfWeek, localHourFloat, 65.0);
          free_flow_mph = posted_speed;"""

    replacement = """        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -83.10 && lon <= -82.855 && lat > 39.92 && lat < 40.05) {
          base_mph = getDirectionalTomTomSpeed('columbus_i70_east_slice1', 'columbus_i70_west_slice1', isEastbound, localDayOfWeek, localHourFloat, posted_speed);
          free_flow_mph = 52.8;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -82.855 && lon <= -82.815 && lat > 39.85 && lat < 40.10) {
          base_mph = getDirectionalTomTomSpeed('columbus_i70_east_slice2', 'columbus_i70_west_slice2', isEastbound, localDayOfWeek, localHourFloat, posted_speed);
          free_flow_mph = 52.8;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -82.815 && lon <= -82.012 && lat > 39.85 && lat < 40.10) {
          base_mph = getDirectionalTomTomSpeed('columbus_to_zanesville_east', 'columbus_to_zanesville_west', isEastbound, localDayOfWeek, localHourFloat, 65.0);
          free_flow_mph = posted_speed;"""

    assert target in content, "Target string not found in index.html!"
    content = content.replace(target, replacement)

    files = ["index.html", "public/index.html", "ui/templates/index.html"]
    for p in files:
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    hashes = [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in files]
    assert len(set(hashes)) == 1, "Hash mismatch!"
    print(f"Successfully wired Columbus Slice 2! SHA-256: {hashes[0]}")

if __name__ == "__main__":
    patch_columbus_slice2()
