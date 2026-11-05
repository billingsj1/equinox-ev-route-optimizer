"""
Compute Normalized Holiday Congestion Offsets
Processes data/bottleneck_speeds_db.json to generate:
  - speed_multiplier: traffic_mph_holiday / traffic_mph_baseline
  - speed_offset_mph: traffic_mph_holiday - traffic_mph_baseline
  - delay_delta_minutes: delay_min_holiday - delay_min_baseline
"""

import json
import os

BASELINE_MAPPING = {
    "thanksgiving_eve": "baseline_wed",
    "thanksgiving_day": "baseline_wed", # compare against typical midweek commuter day
    "black_friday": "baseline_fri",
    "thanksgiving_sun_return": "baseline_sun",
    "pre_xmas_getaway": "baseline_wed",
    "xmas_eve": "baseline_wed",
    "xmas_day": "baseline_fri",
    "day_after_xmas": "baseline_sun", # compare against weekend
    "new_years_eve": "baseline_wed",
    "new_years_day": "baseline_fri",
    "post_holiday_sun_return": "baseline_sun"
}

def main():
    in_file = "data/bottleneck_speeds_db.json"
    out_file = "data/holiday_congestion_offsets.json"
    public_out = "public/data/holiday_congestion_offsets.json"
    
    with open(in_file, "r", encoding="utf-8") as f:
        db = json.load(f)
        
    offsets_db = {
        "metadata": {
            "source": "Google Maps Routes API (TRAFFIC_AWARE_OPTIMAL)",
            "description": "Normalized speed multipliers and delay deltas relative to baseline day-of-week profiles",
            "holiday_keys": list(BASELINE_MAPPING.keys())
        },
        "corridors": {}
    }
    
    for cid, cdata in db["corridors"].items():
        offsets_db["corridors"][cid] = {
            "id": cid,
            "name": cdata["name"],
            "holidays": {}
        }
        
        dates_data = cdata.get("dates", {})
        
        for hkey, base_key in BASELINE_MAPPING.items():
            if hkey not in dates_data or base_key not in dates_data:
                continue
                
            h_hours = dates_data[hkey].get("hours", {})
            base_hours = dates_data[base_key].get("hours", {})
            
            offsets_db["corridors"][cid]["holidays"][hkey] = {
                "holiday_desc": dates_data[hkey].get("desc"),
                "baseline_compared": base_key,
                "hours": {}
            }
            
            for h_str, h_vals in h_hours.items():
                if h_str not in base_hours:
                    continue
                b_vals = base_hours[h_str]
                
                h_spd = h_vals["traffic_mph"]
                b_spd = b_vals["traffic_mph"]
                h_delay = h_vals["delay_minutes"]
                b_delay = b_vals["delay_minutes"]
                
                multiplier = round(h_spd / max(1.0, b_spd), 3)
                spd_diff = round(h_spd - b_spd, 1)
                delay_diff = round(h_delay - b_delay, 1)
                
                offsets_db["corridors"][cid]["holidays"][hkey]["hours"][h_str] = {
                    "holiday_spd": h_spd,
                    "baseline_spd": b_spd,
                    "speed_multiplier": multiplier,
                    "speed_offset_mph": spd_diff,
                    "delay_delta_min": delay_diff
                }
                
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(offsets_db, f, indent=2)
    print(f"Saved: {out_file}")
    
    with open(public_out, "w", encoding="utf-8") as f:
        json.dump(offsets_db, f, indent=2)
    print(f"Saved: {public_out}")

if __name__ == "__main__":
    main()
