import hashlib
import json

def update_index_html():
    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update I-70 to cover all new empirical slices between Columbus and Washington PA
    target_i70 = """        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -83.10 && lon < -82.80 && lat > 39.92 && lat < 40.00) {
          let eastKey = (lon < -82.855) ? 'columbus_i70_east_slice1' : 'columbus_i70_east_slice2';
          let westKey = (lon >= -82.855) ? 'columbus_i70_west_slice1' : 'columbus_i70_west_slice2';
          base_mph = getDirectionalTomTomSpeed(eastKey, westKey, isEastbound, localDayOfWeek, localHourFloat, posted_speed);
          free_flow_mph = 52.8;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -80.32 && lon < -80.16 && lat > 40.14 && lat < 40.21) {
          let eastKey = (lon <= -80.240) ? 'washington_pa_i70_east_slice1' : 'washington_pa_i70_east_slice2';
          let westKey = (lon > -80.240) ? 'washington_pa_i70_west_slice1' : 'washington_pa_i70_west_slice2';
          base_mph = getDirectionalTomTomSpeed(eastKey, westKey, isEastbound, localDayOfWeek, localHourFloat, posted_speed);
          free_flow_mph = 55.0;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -80.76 && lon < -80.68 && lat > 40.05 && lat < 40.09) {
          base_mph = getDirectionalTomTomSpeed('wheeling_i70_east', 'wheeling_i70_west', isEastbound, localDayOfWeek, localHourFloat, 30.0);
          free_flow_mph = 33.2;"""

    replacement_i70 = """        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -83.10 && lon <= -82.855 && lat > 39.92 && lat < 40.05) {
          base_mph = getDirectionalTomTomSpeed('columbus_i70_east_slice1', 'columbus_i70_west_slice1', isEastbound, localDayOfWeek, localHourFloat, posted_speed);
          free_flow_mph = 52.8;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -82.855 && lon <= -82.012 && lat > 39.85 && lat < 40.10) {
          base_mph = getDirectionalTomTomSpeed('columbus_to_zanesville_east', 'columbus_to_zanesville_west', isEastbound, localDayOfWeek, localHourFloat, 65.0);
          free_flow_mph = posted_speed;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -82.012 && lon <= -81.588 && lat > 39.85 && lat < 40.10) {
          base_mph = getDirectionalTomTomSpeed('zanesville_to_cambridge_east', 'zanesville_to_cambridge_west', isEastbound, localDayOfWeek, localHourFloat, 65.0);
          free_flow_mph = posted_speed;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -81.588 && lon <= -81.010 && lat > 39.90 && lat < 40.10) {
          base_mph = getDirectionalTomTomSpeed('cambridge_to_belmont_east', 'cambridge_to_belmont_west', isEastbound, localDayOfWeek, localHourFloat, 65.0);
          free_flow_mph = posted_speed;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -81.010 && lon <= -80.760 && lat > 39.95 && lat < 40.10) {
          base_mph = getDirectionalTomTomSpeed('belmont_to_wheeling_east', 'belmont_to_wheeling_west', isEastbound, localDayOfWeek, localHourFloat, 60.0);
          free_flow_mph = posted_speed;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -80.760 && lon <= -80.680 && lat > 40.04 && lat < 40.10) {
          base_mph = getDirectionalTomTomSpeed('wheeling_i70_east', 'wheeling_i70_west', isEastbound, localDayOfWeek, localHourFloat, 30.0);
          free_flow_mph = 33.2;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -80.680 && lon <= -80.320 && lat > 40.04 && lat < 40.20) {
          base_mph = getDirectionalTomTomSpeed('wheeling_to_washington_east', 'wheeling_to_washington_west', isEastbound, localDayOfWeek, localHourFloat, 60.0);
          free_flow_mph = posted_speed;
        } else if ((sRef.includes('70') || sName.includes('i-70') || sName.includes('i 70')) && lon > -80.320 && lon < -80.160 && lat > 40.14 && lat < 40.21) {
          let eastKey = (lon <= -80.240) ? 'washington_pa_i70_east_slice1' : 'washington_pa_i70_east_slice2';
          let westKey = (lon > -80.240) ? 'washington_pa_i70_west_slice1' : 'washington_pa_i70_west_slice2';
          base_mph = getDirectionalTomTomSpeed(eastKey, westKey, isEastbound, localDayOfWeek, localHourFloat, posted_speed);
          free_flow_mph = 55.0;"""

    assert target_i70 in content, "target_i70 not found in index.html!"
    content = content.replace(target_i70, replacement_i70)

    # 2. Update I-79 to cover Washington PA to Bridgeville to Sewickley
    target_i79 = """        } else if ((sRef.includes('79') || sName.includes('i-79') || sName.includes('i 79')) && lon > -80.15 && lon < -80.08 && lat > 40.32 && lat < 40.42) {
          base_mph = getDirectionalTomTomSpeed('i79_bridgeville_north', 'i79_bridgeville_south', isNorthbound, localDayOfWeek, localHourFloat, 36.0);
          free_flow_mph = 41.1;"""

    replacement_i79 = """        } else if ((sRef.includes('79') || sName.includes('i-79') || sName.includes('i 79')) && lon > -80.30 && lon < -80.05 && lat >= 40.15 && lat < 40.26) {
          base_mph = getDirectionalTomTomSpeed('i79_washington_to_canonsburg_north', 'i79_washington_to_canonsburg_south', isNorthbound, localDayOfWeek, localHourFloat, 60.0);
          free_flow_mph = posted_speed;
        } else if ((sRef.includes('79') || sName.includes('i-79') || sName.includes('i 79')) && lon > -80.20 && lon < -80.05 && lat >= 40.26 && lat < 40.35) {
          base_mph = getDirectionalTomTomSpeed('i79_canonsburg_to_bridgeville_north', 'i79_canonsburg_to_bridgeville_south', isNorthbound, localDayOfWeek, localHourFloat, 55.0);
          free_flow_mph = posted_speed;
        } else if ((sRef.includes('79') || sName.includes('i-79') || sName.includes('i 79')) && lon > -80.20 && lon < -80.05 && lat >= 40.35 && lat <= 40.55) {
          base_mph = getDirectionalTomTomSpeed('i79_bridgeville_to_sewickley_north', 'i79_bridgeville_to_sewickley_south', isNorthbound, localDayOfWeek, localHourFloat, 50.0);
          free_flow_mph = posted_speed;"""

    assert target_i79 in content, "target_i79 not found in index.html!"
    content = content.replace(target_i79, replacement_i79)

    # 3. Update US-15 to cover Harrisburg to Dillsburg and Dillsburg to Gettysburg
    target_us15 = """        } else if ((sRef.includes('15') || sName.includes('us-15') || sName.includes('us 15')) && lon > -77.06 && lon < -76.90 && lat > 40.08 && lat < 40.24) {
          base_mph = getDirectionalTomTomSpeed('dillsburg_us15_arterial_north', 'dillsburg_us15_arterial_south', isNorthbound, localDayOfWeek, localHourFloat, 30.0);
          free_flow_mph = 31.7;"""

    replacement_us15 = """        } else if ((sRef.includes('15') || sName.includes('us-15') || sName.includes('us 15')) && lon > -77.10 && lon < -76.90 && lat >= 40.11 && lat <= 40.26) {
          base_mph = getDirectionalTomTomSpeed('us15_harrisburg_to_dillsburg_north', 'us15_harrisburg_to_dillsburg_south', isNorthbound, localDayOfWeek, localHourFloat, 50.0);
          free_flow_mph = posted_speed;
        } else if ((sRef.includes('15') || sName.includes('us-15') || sName.includes('us 15')) && lon > -77.25 && lon < -77.00 && lat >= 39.80 && lat < 40.11) {
          base_mph = getDirectionalTomTomSpeed('us15_dillsburg_to_gettysburg_north', 'us15_dillsburg_to_gettysburg_south', isNorthbound, localDayOfWeek, localHourFloat, 55.0);
          free_flow_mph = posted_speed;"""

    assert target_us15 in content, "target_us15 not found in index.html!"
    content = content.replace(target_us15, replacement_us15)

    # 4. Write back to all three HTML files
    files = ["index.html", "public/index.html", "ui/templates/index.html"]
    for p in files:
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    hashes = [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in files]
    assert len(set(hashes)) == 1, "Hash mismatch across HTML files!"
    print(f"Successfully updated and verified SHA-256 byte parity: {hashes[0]}")

if __name__ == "__main__":
    update_index_html()
