"""
Toll estimation engine with E-ZPass and EV-specific discount models
for PA Turnpike, NJ Turnpike, and WV Turnpike.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

@dataclass
class TollPassConfig:
    has_ezpass: bool = True
    has_nj_green_pass: bool = True  # 10% discount off-peak on NJ Turnpike for qualifying EVs
    time_of_day_hour: int = 14      # 24-hr format (e.g. 14 = 2 PM)

class TollCalculator:
    """
    Calculates toll expenses along major highway corridors.
    """
    
    # PA Turnpike: Typical mainline segment toll rates between exits (E-ZPass vs Toll-By-Plate)
    # E-ZPass offers ~50% savings over Toll-By-Plate
    PA_TURNPIKE_PLAZAS = {
        ("Warrendale", "New Stanton"): {"ezpass": 4.10, "toll_by_plate": 8.30},
        ("New Stanton", "Somerset"): {"ezpass": 4.90, "toll_by_plate": 9.90},
        ("Somerset", "Bedford"): {"ezpass": 4.60, "toll_by_plate": 9.40},
        ("Bedford", "Breezewood"): {"ezpass": 2.80, "toll_by_plate": 5.60},
        ("Breezewood", "Fort Littleton"): {"ezpass": 3.20, "toll_by_plate": 6.50},
        ("Fort Littleton", "Carlisle"): {"ezpass": 6.80, "toll_by_plate": 13.80},
        ("Carlisle", "Harrisburg East"): {"ezpass": 3.70, "toll_by_plate": 7.50},
        ("Harrisburg East", "Valley Forge"): {"ezpass": 11.20, "toll_by_plate": 22.80},
    }

    # NJ Turnpike: Exit to exit toll table
    # Off-peak hours: 9:00 PM to 7:00 AM weekdays, and all weekend
    NJ_TURNPIKE_SEGMENTS = {
        ("Exit 1 (Delaware Memorial)", "Exit 4 (Mount Laurel)"): {"peak_ezpass": 4.75, "offpeak_ezpass": 3.65, "toll_by_plate": 7.30},
        ("Exit 4 (Mount Laurel)", "Exit 7A (Trenton/I-195)"): {"peak_ezpass": 3.85, "offpeak_ezpass": 2.95, "toll_by_plate": 5.95},
        ("Exit 7A (Trenton/I-195)", "Exit 11 (Garden State Pkwy)"): {"peak_ezpass": 4.90, "offpeak_ezpass": 3.75, "toll_by_plate": 7.50},
        ("Exit 11 (Garden State Pkwy)", "Exit 14 (Newark Airport)"): {"peak_ezpass": 3.20, "offpeak_ezpass": 2.45, "toll_by_plate": 4.95},
        ("Exit 14 (Newark Airport)", "Exit 18W (GWB)"): {"peak_ezpass": 3.85, "offpeak_ezpass": 2.95, "toll_by_plate": 5.95},
    }

    # WV Turnpike (I-77): 3 mainline toll plazas (Chelyan, Pax, Ghent)
    WV_TURNPIKE_PLAZAS = [
        {"name": "Plaza A (Ghent)", "ezpass": 2.20, "cash_plate": 4.25},
        {"name": "Plaza B (Pax)", "ezpass": 2.20, "cash_plate": 4.25},
        {"name": "Plaza C (Chelyan)", "ezpass": 2.20, "cash_plate": 4.25},
    ]

    def is_nj_offpeak(self, hour: int, is_weekend: bool = False) -> bool:
        if is_weekend:
            return True
        return (hour < 7 or hour >= 21)

    def calculate_corridor_tolls(
        self,
        route_corridor: str,  # "PA_Turnpike", "NJ_Turnpike", "WV_Turnpike", or "combined"
        pass_config: TollPassConfig,
        entry_exit_pairs: List[Tuple[str, str]] = None
    ) -> Dict[str, Any]:
        total_toll = 0.0
        details = []

        if route_corridor in ["PA_Turnpike", "combined"]:
            pairs = entry_exit_pairs or [
                ("New Stanton", "Somerset"),
                ("Somerset", "Bedford"),
                ("Bedford", "Breezewood"),
                ("Breezewood", "Fort Littleton"),
                ("Fort Littleton", "Carlisle")
            ]
            for pair in pairs:
                rate_info = self.PA_TURNPIKE_PLAZAS.get(pair)
                if rate_info:
                    cost = rate_info["ezpass"] if pass_config.has_ezpass else rate_info["toll_by_plate"]
                    total_toll += cost
                    details.append({
                        "facility": "PA Turnpike",
                        "segment": f"{pair[0]} -> {pair[1]}",
                        "cost": cost,
                        "discount_applied": "E-ZPass" if pass_config.has_ezpass else "None (Toll-by-Plate)"
                    })

        if route_corridor in ["NJ_Turnpike", "combined"]:
            pairs = entry_exit_pairs or [
                ("Exit 1 (Delaware Memorial)", "Exit 4 (Mount Laurel)"),
                ("Exit 4 (Mount Laurel)", "Exit 7A (Trenton/I-195)"),
                ("Exit 7A (Trenton/I-195)", "Exit 11 (Garden State Pkwy)")
            ]
            offpeak = self.is_nj_offpeak(pass_config.time_of_day_hour)
            for pair in pairs:
                rate_info = self.NJ_TURNPIKE_SEGMENTS.get(pair)
                if rate_info:
                    if pass_config.has_ezpass:
                        base = rate_info["offpeak_ezpass"] if offpeak else rate_info["peak_ezpass"]
                        disc_name = "E-ZPass Off-Peak" if offpeak else "E-ZPass Peak"
                        if offpeak and pass_config.has_nj_green_pass:
                            base *= 0.90  # 10% Green Pass EV discount
                            disc_name += " + 10% NJ Green Pass EV"
                        cost = round(base, 2)
                    else:
                        cost = rate_info["toll_by_plate"]
                        disc_name = "None (Toll-by-Plate)"
                    
                    total_toll += cost
                    details.append({
                        "facility": "NJ Turnpike",
                        "segment": f"{pair[0]} -> {pair[1]}",
                        "cost": cost,
                        "discount_applied": disc_name
                    })

        if route_corridor in ["WV_Turnpike", "combined"]:
            for plaza in self.WV_TURNPIKE_PLAZAS:
                cost = plaza["ezpass"] if pass_config.has_ezpass else plaza["cash_plate"]
                total_toll += cost
                details.append({
                    "facility": "WV Turnpike (I-77)",
                    "segment": plaza["name"],
                    "cost": cost,
                    "discount_applied": "E-ZPass" if pass_config.has_ezpass else "Cash / Plate"
                })

        return {
            "total_toll": round(total_toll, 2),
            "breakdown": details
        }
