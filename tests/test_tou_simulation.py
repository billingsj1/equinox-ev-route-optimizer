import json

def parse_time_to_decimal(time_str):
    parts = time_str.split(':')
    return int(parts[0]) + int(parts[1]) / 60.0

def resolve_station_tariff(st, arrival_hours_decimal, is_member):
    if not st:
        return {"rate": 0.50, "label": "", "is_tou": False}
    
    tou_rates = st.get("tou_rates")
    if tou_rates and len(tou_rates) > 0:
        hr = ((arrival_hours_decimal % 24) + 24) % 24
        for tier in tou_rates:
            s_hr = parse_time_to_decimal(tier.get("start", "00:00"))
            e_hr = parse_time_to_decimal(tier.get("end", "24:00"))
            if s_hr < e_hr:
                in_window = (s_hr <= hr < e_hr)
            else:
                in_window = (hr >= s_hr or hr < e_hr)
            
            if in_window:
                rate = tier.get("mem_on") if is_member and tier.get("mem_on") is not None else tier.get("on")
                base_label = tier.get("label") or ("Off-Peak" if tier.get("on") < (st.get("on", 0.60)) else "Peak")
                badge = f"Member {base_label}" if is_member else base_label
                return {"rate": rate, "label": badge, "is_tou": True}
    
    rate = st.get("on", 0.50)
    badge = ""
    if st.get("gm"):
        rate *= (1.0 - st.get("gm_pct", 0.10))
        badge = "10% GM"
    elif is_member and st.get("mem_on"):
        rate = st.get("mem_on")
        badge = "Member"
    return {"rate": rate, "label": badge, "is_tou": False}

# Test Mt Laurel station
mt_laurel = {
    "id": "tesla-mt-laurel-nj",
    "name": "Tesla Supercharger (+CCS1) - Mt Laurel, NJ",
    "on": 0.51,
    "off": 0.35,
    "mem_on": 0.38,
    "mem_off": 0.26,
    "tou_rates": [
        {"start": "00:00", "end": "10:00", "on": 0.35, "off": 0.35, "mem_on": 0.26, "mem_off": 0.26, "label": "Off-Peak"},
        {"start": "10:00", "end": "22:00", "on": 0.51, "off": 0.51, "mem_on": 0.38, "mem_off": 0.38, "label": "Peak"},
        {"start": "22:00", "end": "24:00", "on": 0.35, "off": 0.35, "mem_on": 0.26, "mem_off": 0.26, "label": "Off-Peak"}
    ]
}

# Test at 8:00 AM departure + 8.5 hr trip -> 16.5 hr (4:30 PM) -> Peak
res_day = resolve_station_tariff(mt_laurel, 16.5, is_member=False)
res_day_mem = resolve_station_tariff(mt_laurel, 16.5, is_member=True)
print("Day arrival (16:30):", res_day, "Member:", res_day_mem)

# Test at 23:00 (11:00 PM) departure + 8.5 hr trip -> 7.5 hr (7:30 AM) -> Off-Peak
res_night = resolve_station_tariff(mt_laurel, 7.5, is_member=False)
res_night_mem = resolve_station_tariff(mt_laurel, 7.5, is_member=True)
print("Night arrival (07:30):", res_night, "Member:", res_night_mem)

assert res_day["rate"] == 0.51 and res_day["label"] == "Peak"
assert res_day_mem["rate"] == 0.38 and res_day_mem["label"] == "Member Peak"
assert res_night["rate"] == 0.35 and res_night["label"] == "Off-Peak"
assert res_night_mem["rate"] == 0.26 and res_night_mem["label"] == "Member Off-Peak"
print("All assertions passed!")
