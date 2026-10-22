# 2025 Chevrolet Equinox EV Route Optimizer & Pricing Engine

A decoupled, multi-objective EV route optimizer and automated CPO pricing pipeline designed specifically for the **2025 Chevrolet Equinox EV FWD (85.0 kWh usable pack)**.

---

## ⚡ System Architecture

The project is decoupled into two independent systems:

```
┌────────────────────────────────────────────────────────┐
│     Automated Pricing Pipeline (GitHub Actions)        │
│  - Scheduled 6-hr cron or manual workflow dispatch     │
│  - Intercepts backend JSON APIs for:                   │
│    IONNA, Mercedes-Benz, Electrify America, Applegreen,│
│    Francis Energy, ChargePoint, Tesla MagicDock        │
│  - Discovers stations via Open Charge Map (OCM)        │
│  - Filters: CCS1 / MagicDock, Speed >= 100 kW          │
│  - Persists static data/prices.json and SQLite db      │
└──────────────────────────┬─────────────────────────────┘
                           │ (Static Data Feed)
┌──────────────────────────▼─────────────────────────────┐
│          Routing, Physics & Optimization Engine        │
│  - Routing: OpenRouteService (ORS) alternatives + elev │
│  - Weather: OpenWeatherMap (Live, Historical, Manual)  │
│  - Physics: NREL FASTSim & road-load dynamics          │
│  - Tolls: PA Turnpike, NJ Turnpike (EV Green Pass), WV │
│  - Multi-Objective Pareto Frontier (Fastest, Cheapest, │
│    and Balanced via Utopia Point / Knee detection)     │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│               Interactive Dashboard                    │
│  - Fast, responsive UI (Tailwind CSS + Leaflet.js)     │
│  - Passenger & cargo sliders (Josh, Courtney, Asher,   │
│    Arno the Dog, Gear slider)                          │
│  - Speed offset & hard max cap controls                │
│  - Electrify America Pass+ net benefit calculator      │
└────────────────────────────────────────────────────────┘
```

---

## 🚗 Vehicle Specifications & Physics Parameters

* **Usable Battery Capacity:** `85.0 kWh` (gross `89.0 kWh`)
* **Nominal Pack Architecture:** `~288V` low-voltage Ultium platform (requires high-amperage 500A stalls for full 150 kW peak)
* **Curb Weight:** `2,233 kg` (~4,923 lbs)
* **Drag Area ($C_d \times A$):** $0.332 \times 2.60\,\text{m}^2 = 0.8632\,\text{m}^2$
* **Rolling Resistance ($C_{rr}$):**
  * Dry Asphalt: `0.0095`
  * Wet / Rainy: `0.0125` (+30% water displacement drag)
  * Slush / Snow / Ice: `0.0185` (+95%)
* **Drivetrain & Regen:** 91% traction efficiency, 85% regenerative braking round-trip recovery up to 70 kW max regen power.
* **Empirical DC Fast Charge Curve:**
  * `0% - 32% SoC`: **150 kW** peak
  * `32% - 58% SoC`: Tapers **150 kW $\to$ 100 kW**
  * `58% - 70% SoC`: Tapers **100 kW $\to$ 75 kW**
  * `70% - 80% SoC`: Tapers **75 kW $\to$ 52 kW** (10-80% averages **~97 kW**, ~38 minutes)
  * `80% - 90% SoC`: Tapers to **32 kW**
  * `90% - 100% SoC`: Tapers to **12 kW**
  * *Station Power Clamping:* Automatically clamped by $\min(P_{\text{station}}, P_{\text{car}}(\text{SoC}))$.

---

## 👥 Dynamic Payload Configuration

Real-time weight toggles modify the simulated mass:
* **Josh:** `150 lbs`
* **Courtney:** `130 lbs`
* **Asher:** `20 lbs`
* **Arno (Dog):** `50 lbs`
* **Gear:** Slider from `0 to 100 lbs`

---

## 🛣️ Toll Corridors & EV Discounts

1. **Pennsylvania Turnpike (I-76 / I-70):** E-ZPass discount (~50% lower than Toll-By-Plate).
2. **New Jersey Turnpike (I-95):** Peak vs. off-peak E-ZPass rates, plus the **NJ Turnpike EV Green Pass** (10% additional discount during off-peak hours for zero-emission vehicles).
3. **West Virginia Turnpike (I-77):** Mainline toll plazas with E-ZPass passenger rates.

---

## 🏷️ CPO Pricing, Memberships & OEM Perks

* **GM EV Perks:**
  * `10% discount` at **IONNA** rechargeries.
  * `10% discount` + `$0 session fees` at **EVgo**.
* **Electrify America Pass+ Analysis:** Automatically evaluates if the `$7.00/month` fee is offset by charging savings on the selected trip.
* **Time-of-Use (TOU) Pricing:** Off-peak (`10:00 PM - 10:00 AM`) vs. On-peak (`10:00 AM - 10:00 PM`) supported per station.

---

## 🚀 Quickstart & Usage

### 1. Install Dependencies
```bash
uv venv
uv pip install -r requirements.txt
```

### 2. Launch the Interactive Dashboard
```bash
python run.py
```
Open **http://127.0.0.1:8000** in your browser to adjust sliders, inspect alternative routes, and view the 3 Pareto itineraries on the interactive map.

### 3. Run Optimization in Terminal (CLI)
```bash
python run.py --cli
```

### 4. Run the Pricing Scraper Pipeline Locally
```bash
python run.py --scrape
```
Updates `data/prices.json` and `data/prices.db`. In production, this runs automatically via `.github/workflows/update_prices.yml`.
