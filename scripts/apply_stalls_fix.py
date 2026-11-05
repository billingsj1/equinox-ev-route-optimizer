"""
Script to apply stall display and retention fixes to index.html, public/index.html, and ui/templates/index.html.
Ensures SHA-256 byte parity across all three files.
"""
import hashlib
import os
import re

FILES = [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "index.html"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "templates", "index.html"),
]

def update_html(content: str) -> str:
    # 1. Update initMap() popup to include stalls
    target_1 = """            <b>${s.name}</b><br>
            <span style="color:#64748b;">Network:</span> <b>${s.network}</b> (${s.kw} kW)<br>"""
    replacement_1 = """            <b>${s.name}</b><br>
            <span style="color:#64748b;">Network:</span> <b>${s.network}</b> (${s.kw} kW${s.stalls ? ` &bull; ${s.stalls} stalls` : ''})<br>"""
    if target_1 in content:
        content = content.replace(target_1, replacement_1, 1)
        print(" [OK] Updated initMap() popup with stalls")
    else:
        print(" [SKIP] initMap() popup already updated or target not found")

    # 2. Update renderTable(itin) / Timeline stops table
    target_2 = """              <div class="text-[10px] text-slate-400 font-mono font-normal">
                Trip Mile ${Math.round(s.mile)} &bull; ${s.station.stalls ? `${s.station.stalls} Stalls &bull; ` : ''}${s.station.network || ''}
              </div>"""
    replacement_2 = """              <div class="text-[10px] text-slate-400 font-mono font-normal flex items-center gap-1.5 flex-wrap mt-0.5">
                <span>Trip Mile ${Math.round(s.mile)}</span>
                <span>&bull;</span>
                <span class="inline-flex items-center gap-1 text-cyan-300 font-semibold bg-cyan-950/70 border border-cyan-700/40 px-1.5 py-0.5 rounded text-[10px]">
                  <i data-lucide="zap" class="w-2.5 h-2.5 text-cyan-400"></i> ${s.station.stalls ? `${s.station.stalls} Stalls` : '4 Stalls'}
                </span>
                <span>&bull;</span>
                <span>${s.station.kw} kW</span>
                <span>&bull;</span>
                <span>${s.station.network || ''}</span>
              </div>"""
    if target_2 in content:
        content = content.replace(target_2, replacement_2, 1)
        print(" [OK] Updated Timeline table stop card with prominent stalls badge")
    else:
        print(" [SKIP] Timeline table stop card already updated or target not found")

    # 3. Update MANUALLY_VERIFIED_OVERRIDES to include stalls
    target_3 = """    const MANUALLY_VERIFIED_OVERRIDES = {
      'cp-hancock-md': { on: 0.40, off: 0.40, url: 'https://driver.chargepoint.com/stations/13210691', verified: true },
      'ag-waterfall-pa': { on: 0.55, off: 0.55, url: 'https://dcfctracker.com/stations/451875', verified: true },
      'ea-belle-vernon-pa': { on: 0.60, off: 0.40, url: 'https://dcfctracker.com/stations/237974', verified: true },
      'ionna-cambridge-oh': { on: 0.39, off: 0.39, url: 'https://www.ionna.com/ev-charging-stations/oh/cambridge/61600-southgate-rd-43725/', verified: true },
      'ionna-chester-springs-pa': { on: 0.35, off: 0.35, url: 'https://www.ionna.com/ev-charging-stations/pa/chester-springs/1800-ticonderoga-blvd-19425/', verified: true },
      'ionna-frederick-md': { on: 0.39, off: 0.39, url: 'https://www.ionna.com/ev-charging-stations/md/frederick/1390-w-patrick-st-21703/', verified: true },
      'ionna-elkton-md': { on: 0.39, off: 0.39, url: 'https://www.ionna.com/ev-charging-stations/md/elkton/1657-elkton-rd-21921/', verified: true },
      'evgo-pilot-belmont-oh': { on: 0.53, off: 0.53, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/306630', verified: true },
      'ocm-306630': { on: 0.53, off: 0.53, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/306630', verified: true },
      'mb-washington-pa': { on: 0.44, off: 0.44, url: 'https://mercedesbenzhpc.com/charging-station/pa-washington-the-old-mill/', verified: true },
      'tesla-somerset-pa': { on: 0.56, off: 0.56, mem_on: 0.41, mem_off: 0.41, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/somersetsupercharger', verified: true },
      'tesla-fort-littleton-pa': { on: 0.56, off: 0.56, mem_on: 0.41, mem_off: 0.41, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/26674', verified: true },
      'tesla-mt-laurel-nj': { on: 0.51, off: 0.35, mem_on: 0.38, mem_off: 0.26, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/406608', verified: true },
      'tesla-woodlyn-pa': { on: 0.62, off: 0.32, mem_on: 0.44, mem_off: 0.23, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/59209', verified: true },
      'tesla-cherry-hill-nj': { on: 0.72, off: 0.72, mem_on: 0.48, mem_off: 0.34, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/cherryhillnjhaddonfieldroadsupercharger', verified: true },
      'tesla-maple-shade-nj': { on: 0.72, off: 0.72, mem_on: 0.48, mem_off: 0.34, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/26769', verified: true },
      'tesla-pittsburgh-freeport-pa': { on: 0.59, off: 0.3, mem_on: 0.44, mem_off: 0.22, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/20506', verified: true },
      'tesla-summerdale-pa': { on: 0.55, off: 0.28, mem_on: 0.4, mem_off: 0.21, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/33951', verified: true },
      'tesla-lawnside-nj': { on: 0.49, off: 0.34, mem_on: 0.36, mem_off: 0.25, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/402407', verified: true },
      'tesla-aston-pa': { on: 0.56, off: 0.28, mem_on: 0.4, mem_off: 0.2, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/35027', verified: true },
      'tesla-shrewsbury-pa': { on: 0.68, off: 0.3, mem_on: 0.49, mem_off: 0.22, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/36287', verified: true },
      'tesla-timonium-md': { on: 0.6, off: 0.38, mem_on: 0.43, mem_off: 0.27, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/33688', verified: true },
      'tesla-waynesburg-pa': { on: 0.57, off: 0.57, mem_on: 0.41, mem_off: 0.41, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/401410', verified: true },
      'tesla-medford-nj': { on: 0.72, off: 0.72, mem_on: 0.48, mem_off: 0.34, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/19516', verified: true },
      'tesla-hamilton-nj': { on: 0.72, off: 0.72, mem_on: 0.48, mem_off: 0.34, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/424861', verified: true },
      'tesla-blackwood-nj': { on: 0.73, off: 0.38, mem_on: 0.52, mem_off: 0.27, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/59126', verified: true },
      'tesla-34183': { on: 0.56, off: 0.56, mem_on: 0.41, mem_off: 0.41, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/34183', verified: true, tou_rates: [] },
      'evgo-pilot-marengo-oh': { on: 0.69, off: 0.69, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/347668', verified: true },
      'ocm-306512': { on: 0.69, off: 0.69, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/347668', verified: true },
      'ocm-351529': { on: 0.69, off: 0.69, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/347668', verified: true },
      'ocm-306563': { on: 0.58, off: 0.58, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/349766', verified: true },
      'evgo-farley-nj': { on: 0.66, off: 0.66, gm: true, gm_pct: 0.10, url: 'https://dcfctracker.com/stations/228536', verified: true },
      'ocm-225139': { on: 0.66, off: 0.66, gm: true, gm_pct: 0.10, url: 'https://dcfctracker.com/stations/228536', verified: true },
      'evgo-hollinswood-md': { on: 0.61, off: 0.61, gm: true, gm_pct: 0.10, url: 'https://dcfctracker.com/stations/322293', verified: true },
      'ocm-294317': { on: 0.61, off: 0.61, gm: true, gm_pct: 0.10, url: 'https://dcfctracker.com/stations/322293', verified: true },
      'cp-potomac-edison-canal-md': { on: 0.34, off: 0.34, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/300557', verified: true },
      'ocm-282416': { on: 0.34, off: 0.34, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/300557', verified: true }
    };"""

    replacement_3 = """    const MANUALLY_VERIFIED_OVERRIDES = {
      'cp-hancock-md': { on: 0.40, off: 0.40, stalls: 2, url: 'https://driver.chargepoint.com/stations/13210691', verified: true },
      'ag-waterfall-pa': { on: 0.55, off: 0.55, stalls: 4, url: 'https://dcfctracker.com/stations/451875', verified: true },
      'ea-belle-vernon-pa': { on: 0.60, off: 0.40, stalls: 4, url: 'https://dcfctracker.com/stations/237974', verified: true },
      'ionna-cambridge-oh': { on: 0.39, off: 0.39, stalls: 8, url: 'https://www.ionna.com/ev-charging-stations/oh/cambridge/61600-southgate-rd-43725/', verified: true },
      'ionna-chester-springs-pa': { on: 0.35, off: 0.35, stalls: 8, url: 'https://www.ionna.com/ev-charging-stations/pa/chester-springs/1800-ticonderoga-blvd-19425/', verified: true },
      'ionna-frederick-md': { on: 0.39, off: 0.39, stalls: 8, url: 'https://www.ionna.com/ev-charging-stations/md/frederick/1390-w-patrick-st-21703/', verified: true },
      'ionna-elkton-md': { on: 0.39, off: 0.39, stalls: 8, url: 'https://www.ionna.com/ev-charging-stations/md/elkton/1657-elkton-rd-21921/', verified: true },
      'evgo-pilot-belmont-oh': { on: 0.53, off: 0.53, stalls: 4, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/306630', verified: true },
      'ocm-306630': { on: 0.53, off: 0.53, stalls: 4, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/306630', verified: true },
      'mb-washington-pa': { on: 0.44, off: 0.44, stalls: 4, url: 'https://mercedesbenzhpc.com/charging-station/pa-washington-the-old-mill/', verified: true },
      'tesla-somerset-pa': { on: 0.56, off: 0.56, mem_on: 0.41, mem_off: 0.41, stalls: 10, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/somersetsupercharger', verified: true },
      'tesla-fort-littleton-pa': { on: 0.56, off: 0.56, mem_on: 0.41, mem_off: 0.41, stalls: 8, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/26674', verified: true },
      'tesla-mt-laurel-nj': { on: 0.51, off: 0.35, mem_on: 0.38, mem_off: 0.26, stalls: 40, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/406608', verified: true },
      'tesla-woodlyn-pa': { on: 0.62, off: 0.32, mem_on: 0.44, mem_off: 0.23, stalls: 12, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/59209', verified: true },
      'tesla-cherry-hill-nj': { on: 0.72, off: 0.72, mem_on: 0.48, mem_off: 0.34, stalls: 8, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/cherryhillnjhaddonfieldroadsupercharger', verified: true },
      'tesla-maple-shade-nj': { on: 0.72, off: 0.72, mem_on: 0.48, mem_off: 0.34, stalls: 12, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/26769', verified: true },
      'tesla-pittsburgh-freeport-pa': { on: 0.59, off: 0.3, mem_on: 0.44, mem_off: 0.22, stalls: 16, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/20506', verified: true },
      'tesla-summerdale-pa': { on: 0.55, off: 0.28, mem_on: 0.4, mem_off: 0.21, stalls: 8, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/33951', verified: true },
      'tesla-lawnside-nj': { on: 0.49, off: 0.34, mem_on: 0.36, mem_off: 0.25, stalls: 32, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/402407', verified: true },
      'tesla-aston-pa': { on: 0.56, off: 0.28, mem_on: 0.4, mem_off: 0.2, stalls: 8, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/35027', verified: true },
      'tesla-shrewsbury-pa': { on: 0.68, off: 0.3, mem_on: 0.49, mem_off: 0.22, stalls: 12, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/36287', verified: true },
      'tesla-timonium-md': { on: 0.6, off: 0.38, mem_on: 0.43, mem_off: 0.27, stalls: 12, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/33688', verified: true },
      'tesla-waynesburg-pa': { on: 0.57, off: 0.57, mem_on: 0.41, mem_off: 0.41, stalls: 12, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/401410', verified: true },
      'tesla-medford-nj': { on: 0.72, off: 0.72, mem_on: 0.48, mem_off: 0.34, stalls: 12, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/19516', verified: true },
      'tesla-hamilton-nj': { on: 0.72, off: 0.72, mem_on: 0.48, mem_off: 0.34, stalls: 12, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/424861', verified: true },
      'tesla-blackwood-nj': { on: 0.73, off: 0.38, mem_on: 0.52, mem_off: 0.27, stalls: 16, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/59126', verified: true },
      'tesla-34183': { on: 0.56, off: 0.56, mem_on: 0.41, mem_off: 0.41, stalls: 8, gm: false, gm_pct: 0.0, url: 'https://www.tesla.com/findus/location/supercharger/34183', verified: true, tou_rates: [] },
      'evgo-pilot-marengo-oh': { on: 0.69, off: 0.69, stalls: 6, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/347668', verified: true },
      'ocm-306512': { on: 0.69, off: 0.69, stalls: 6, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/347668', verified: true },
      'ocm-351529': { on: 0.69, off: 0.69, stalls: 6, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/347668', verified: true },
      'ocm-306563': { on: 0.58, off: 0.58, stalls: 4, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/349766', verified: true },
      'evgo-farley-nj': { on: 0.66, off: 0.66, stalls: 4, gm: true, gm_pct: 0.10, url: 'https://dcfctracker.com/stations/228536', verified: true },
      'ocm-225139': { on: 0.66, off: 0.66, stalls: 4, gm: true, gm_pct: 0.10, url: 'https://dcfctracker.com/stations/228536', verified: true },
      'evgo-hollinswood-md': { on: 0.61, off: 0.61, stalls: 6, gm: true, gm_pct: 0.10, url: 'https://dcfctracker.com/stations/322293', verified: true },
      'ocm-294317': { on: 0.61, off: 0.61, stalls: 6, gm: true, gm_pct: 0.10, url: 'https://dcfctracker.com/stations/322293', verified: true },
      'cp-potomac-edison-canal-md': { on: 0.34, off: 0.34, stalls: 1, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/300557', verified: true },
      'ocm-282416': { on: 0.34, off: 0.34, stalls: 1, gm: false, gm_pct: 0.0, url: 'https://dcfctracker.com/stations/300557', verified: true }
    };"""
    if target_3 in content:
        content = content.replace(target_3, replacement_3, 1)
        print(" [OK] Updated MANUALLY_VERIFIED_OVERRIDES with stalls")
    else:
        print(" [SKIP] MANUALLY_VERIFIED_OVERRIDES already updated or target not found")

    # 4. Update matchStationToScrapedData return blocks
    # 4a. Overrides block:
    target_4a = """        return {
          on: ov.on,
          off: ov.off,
          mem_on: ov.mem_on,
          mem_off: ov.mem_off,
          tou_rates: ov.tou_rates || [],
          gm: canGm,
          gm_pct: canGm ? (ov.gm_pct || 0.10) : 0.0,
          url: ov.url,
          verified: true
        };"""
    replacement_4a = """        return {
          on: ov.on,
          off: ov.off,
          mem_on: ov.mem_on,
          mem_off: ov.mem_off,
          tou_rates: ov.tou_rates || [],
          gm: canGm,
          gm_pct: canGm ? (ov.gm_pct || 0.10) : 0.0,
          stalls: ov.stalls || station.stalls,
          url: ov.url,
          verified: true
        };"""
    if target_4a in content:
        content = content.replace(target_4a, replacement_4a, 1)
        print(" [OK] Updated matchStationToScrapedData overrides block with stalls")

    # 4b. Tesla block:
    target_4b = """            if (idMatch || slugMatch || distMatch) {
              return {
                on: t.rate_on,
                off: t.rate_off,
                mem_on: t.mem_on,
                mem_off: t.mem_off,
                tou_rates: t.tou_rates || [],
                url: t.url || `https://www.tesla.com/findus/location/supercharger/${t.slug}`,
                verified: true
              };
            }"""
    replacement_4b = """            if (idMatch || slugMatch || distMatch) {
              return {
                on: t.rate_on,
                off: t.rate_off,
                mem_on: t.mem_on,
                mem_off: t.mem_off,
                tou_rates: t.tou_rates || [],
                stalls: t.stalls || 8,
                url: t.url || `https://www.tesla.com/findus/location/supercharger/${t.slug}`,
                verified: true
              };
            }"""
    if target_4b in content:
        content = content.replace(target_4b, replacement_4b, 1)
        print(" [OK] Updated matchStationToScrapedData Tesla block with stalls")

    # 5. Update initStations() matching loop:
    target_5 = """          if (!s.price_verified || s.on == null || s.on <= 0 || hasOverride || isTesla) {
            const res = matchStationToScrapedData(s, db);
            if (res.verified) {
              s.on = res.on;
              s.off = res.off;
              if (res.mem_on) s.mem_on = res.mem_on;
              if (res.mem_off) s.mem_off = res.mem_off;
              s.tou_rates = res.tou_rates || [];
              if (res.gm !== undefined) s.gm = res.gm;
              if (res.gm_pct !== undefined) s.gm_pct = res.gm_pct;
              if (res.url) s.plug = res.url;
              s.price_verified = true;
              s.manually_verified = false;"""

    replacement_5 = """          if (!s.price_verified || s.on == null || s.on <= 0 || hasOverride || isTesla) {
            const res = matchStationToScrapedData(s, db);
            if (res.verified) {
              s.on = res.on;
              s.off = res.off;
              if (res.mem_on) s.mem_on = res.mem_on;
              if (res.mem_off) s.mem_off = res.mem_off;
              s.tou_rates = res.tou_rates || [];
              if (res.gm !== undefined) s.gm = res.gm;
              if (res.gm_pct !== undefined) s.gm_pct = res.gm_pct;
              if (res.stalls) s.stalls = res.stalls;
              if (res.url) s.plug = res.url;
              s.price_verified = true;
              s.manually_verified = false;"""
    if target_5 in content:
        content = content.replace(target_5, replacement_5, 1)
        print(" [OK] Updated initStations() price match loop with stalls")

    # 5b. In initStations(), also ensure any station lacking stalls matches db:
    target_5b = """          if (!s.price_verified || s.on == null || s.on <= 0 || hasOverride || isTesla) {"""
    replacement_5b = """          if (!s.stalls) {
            const sRes = matchStationToScrapedData(s, db);
            if (sRes && sRes.stalls) s.stalls = sRes.stalls;
          }
          if (!s.price_verified || s.on == null || s.on <= 0 || hasOverride || isTesla) {"""
    if target_5b in content:
        content = content.replace(target_5b, replacement_5b, 1)
        print(" [OK] Added fallback stall matching for all stations in initStations()")

    # 6. Update fetchChargers() - OCM existing station stall backfill
    target_6a = """                  const exists = ALL_STATIONS.some(s =>
                    (s.ocm_id && poi.ID && String(s.ocm_id) === String(poi.ID)) ||
                    (s.network === network && haversineMiles(s.lat, s.lon, lat, lon) < (network === 'IONNA' ? 3.5 : 0.5)) ||
                    haversineMiles(s.lat, s.lon, lat, lon) < 0.35
                  );

                  if (!exists) {"""

    replacement_6a = """                  const existingSt = ALL_STATIONS.find(s =>
                    (s.ocm_id && poi.ID && String(s.ocm_id) === String(poi.ID)) ||
                    (s.network === network && haversineMiles(s.lat, s.lon, lat, lon) < (network === 'IONNA' ? 3.5 : 0.5)) ||
                    haversineMiles(s.lat, s.lon, lat, lon) < 0.35
                  );
                  if (existingSt) {
                    let curStalls = poi.NumberOfPoints || null;
                    if (!curStalls && Array.isArray(poi.Connections)) {
                      const sumQ = poi.Connections.reduce((acc, c) => acc + (c.Quantity || 0), 0);
                      if (sumQ > 0) curStalls = sumQ;
                    }
                    if (curStalls && (!existingSt.stalls || existingSt.stalls < curStalls)) {
                      existingSt.stalls = curStalls;
                    }
                    return;
                  }

                  if (!existingSt) {"""
    if target_6a in content:
        content = content.replace(target_6a, replacement_6a, 1)
        print(" [OK] Updated fetchChargers() OCM station stall backfill")

    # 6b. Update fetchChargers() - Tesla Supercharger stall retention
    target_6b = """              const slug = String(s.locationId || s.id);
              const exists = ALL_STATIONS.some(ex =>
                (isTeslaNetwork(ex.network) && (ex.tesla_slug === slug || (ex.id && ex.id.toLowerCase().includes(slug.toLowerCase())))) ||
                haversineMiles(ex.lat, ex.lon, lat, lon) < 0.35
              );

              if (!exists) {
                const stId = `tesla-${slug.toLowerCase()}`;
                const rawTitle = (s.name || (s.address && s.address.city) || 'Station').trim();
                const stState = (s.address && s.address.state) || '';
                let cleanTitle = rawTitle;
                if (stState) {
                  const stateRegex = new RegExp(`,\\\\s*${stState}\\\\.?$`, 'i');
                  cleanTitle = cleanTitle.replace(stateRegex, '').trim();
                }
                const name = hasMagicDock
                  ? `Tesla Supercharger (+CCS1) - ${cleanTitle}, ${stState}`
                  : `Tesla Supercharger (NACS Adapter) - ${cleanTitle}, ${stState}`;
                const kw = s.powerKilowatt || 250;

                const res = matchStationToScrapedData({
                  id: stId,
                  network: netName,
                  state: stState,
                  city: (s.address && s.address.city) || "",
                  name: name,
                  lat: lat,
                  lon: lon,
                  tesla_slug: slug,
                  plug: `https://www.tesla.com/findus/location/supercharger/${slug}`
                }, db);

                const newSt = {
                  id: stId,
                  name: name,
                  network: netName,
                  lat: Math.round(lat * 10000) / 10000,
                  lon: Math.round(lon * 10000) / 10000,
                  city: (s.address && s.address.city) || "",
                  state: stState,
                  kw: kw,
                  off: res.off,
                  on: res.on,
                  gm: false,
                  gm_pct: 0.0,
                  ea_pass: false,
                  mem_off: res.mem_off,
                  mem_on: res.mem_on,
                  plug: res.url || `https://www.tesla.com/findus/location/supercharger/${slug}`,
                  price_verified: res.verified,
                  tesla_slug: slug
                };"""

    replacement_6b = """              const slug = String(s.locationId || s.id);
              const stallCount = s.stallCount || (res && res.stalls) || 8;
              const existingSt = ALL_STATIONS.find(ex =>
                (isTeslaNetwork(ex.network) && (ex.tesla_slug === slug || (ex.id && ex.id.toLowerCase().includes(slug.toLowerCase())))) ||
                haversineMiles(ex.lat, ex.lon, lat, lon) < 0.35
              );
              if (existingSt) {
                if (!existingSt.stalls && stallCount) {
                  existingSt.stalls = stallCount;
                }
                return;
              }

              if (!existingSt) {
                const stId = `tesla-${slug.toLowerCase()}`;
                const rawTitle = (s.name || (s.address && s.address.city) || 'Station').trim();
                const stState = (s.address && s.address.state) || '';
                let cleanTitle = rawTitle;
                if (stState) {
                  const stateRegex = new RegExp(`,\\\\s*${stState}\\\\.?$`, 'i');
                  cleanTitle = cleanTitle.replace(stateRegex, '').trim();
                }
                const name = hasMagicDock
                  ? `Tesla Supercharger (+CCS1) - ${cleanTitle}, ${stState}`
                  : `Tesla Supercharger (NACS Adapter) - ${cleanTitle}, ${stState}`;
                const kw = s.powerKilowatt || 250;

                const res = matchStationToScrapedData({
                  id: stId,
                  network: netName,
                  state: stState,
                  city: (s.address && s.address.city) || "",
                  name: name,
                  lat: lat,
                  lon: lon,
                  tesla_slug: slug,
                  plug: `https://www.tesla.com/findus/location/supercharger/${slug}`
                }, db);

                const newSt = {
                  id: stId,
                  name: name,
                  network: netName,
                  lat: Math.round(lat * 10000) / 10000,
                  lon: Math.round(lon * 10000) / 10000,
                  city: (s.address && s.address.city) || "",
                  state: stState,
                  kw: kw,
                  stalls: s.stallCount || (res && res.stalls) || 8,
                  off: res.off,
                  on: res.on,
                  gm: false,
                  gm_pct: 0.0,
                  ea_pass: false,
                  mem_off: res.mem_off,
                  mem_on: res.mem_on,
                  plug: res.url || `https://www.tesla.com/findus/location/supercharger/${slug}`,
                  price_verified: res.verified,
                  tesla_slug: slug
                };"""
    if target_6b in content:
        content = content.replace(target_6b, replacement_6b, 1)
        print(" [OK] Updated fetchChargers() Tesla stall count assignment and backfill")

    return content

def main():
    print("Applying stall fixes across all three HTML files...")
    with open(FILES[0], "r", encoding="utf-8") as f:
        original = f.read()

    updated = update_html(original)

    for path in FILES:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        h = hashlib.sha256(updated.encode("utf-8")).hexdigest()
        print(f"Written {path} -> SHA256: {h}")

if __name__ == "__main__":
    main()
