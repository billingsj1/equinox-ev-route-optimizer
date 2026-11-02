"""
Recalculates true traffic delay and congestion ratio for all corridor entries
in data/tomtom_corridors_rich_archive.json relative to each corridor's true
uncongested free-flow baseline (minimum travel time across the 168-hour week).
"""

import json

with open("data/tomtom_corridors_rich_archive.json", "r") as f:
    archive = json.load(f)

for cid, cdata in archive.items():
    # Find absolute minimum travel time (true free-flow open road baseline)
    min_time = float("inf")
    best_free_flow_mph = 60.0
    for day_name, hours in cdata["profiles"].items():
        for h, sample in hours.items():
            t = sample["travel_time_seconds"]
            if t < min_time and t > 0:
                min_time = t
                best_free_flow_mph = sample["speed_mph"]

    cdata["baseline_free_flow_seconds"] = min_time
    cdata["baseline_free_flow_mph"] = best_free_flow_mph

    # Update each hour
    for day_name, hours in cdata["profiles"].items():
        for h, sample in hours.items():
            t = sample["travel_time_seconds"]
            delay_sec = max(0, t - min_time)
            delay_min = round(delay_sec / 60.0, 1)
            ratio = round(t / max(1, min_time), 3)

            sample["delay_seconds"] = delay_sec
            sample["delay_minutes"] = delay_min
            sample["free_flow_mph"] = best_free_flow_mph
            sample["congestion_ratio"] = ratio

with open("data/tomtom_corridors_rich_archive.json", "w") as f:
    json.dump(archive, f, indent=2)

print("Successfully updated data/tomtom_corridors_rich_archive.json with true free-flow delays!")
