import urllib.request
import json
import math

req = urllib.request.Request(
    'https://supercharge.info/service/supercharge/allSites',
    headers={'User-Agent': 'Mozilla/5.0'}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))

ccs_sites = [
    s for s in data 
    if s.get('status') == 'OPEN' 
    and s.get('address', {}).get('country') == 'USA' 
    and s.get('plugs', {}).get('ccs1', 0) > 0
]

target_states = {'OH', 'PA', 'WV', 'MD', 'DE', 'NJ'}
regional_sites = [
    s for s in ccs_sites 
    if s.get('address', {}).get('state') in target_states
]

print(f"Total Magic Dock sites in OH, PA, WV, MD, DE, NJ: {len(regional_sites)}")

# Sort by state, then city
regional_sites.sort(key=lambda s: (s['address']['state'], s['address']['city']))

for s in regional_sites:
    loc_id = s.get('locationId')
    name = s.get('name')
    st = s['address']['state']
    city = s['address']['city']
    street = s['address']['street']
    lat = s['gps']['latitude']
    lon = s['gps']['longitude']
    kw = s.get('powerKilowatt', 250)
    stalls = s.get('stallCount', 8)
    print(f"[{st}] {name:35} | slug: {str(loc_id):20} | lat: {lat:.4f}, lon: {lon:.4f} | {kw} kW, {stalls} stalls | {street}")
