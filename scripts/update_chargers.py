"""Uppdaterar listan över snabbladdare (minst 150 kW) i Sverige.

    python scripts/update_chargers.py --ocm-dir ocm-export/data/SE

Källor:
- Open Charge Map, deras öppna export på GitHub (github.com/openchargemap/ocm-export), en JSON-fil per plats
- supercharge.info (Teslas Superchargers som är öppna för andra bilar)

Skriver data/chargers.json och data/chargers_meta.json. Om en källa inte går att nå behålls den
senast hämtade datan, så att bygget aldrig går sönder av ett tillfälligt fel.
"""
import argparse, collections, datetime, glob, json, math, os, sys, urllib.request

S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument('--ocm-dir', default=None, help='mapp med OCM-exportens filer för Sverige (data/SE)')
ap.add_argument('--ocm-date', default=None, help='datum för OCM-exporten (ÅÅÅÅ-MM-DD), t.ex. från git log')
ap.add_argument('--no-tesla', action='store_true', help='hämta inte om Tesla-datan')
args = ap.parse_args()
today = datetime.date.today().isoformat()
meta_path = f'{S}/data/chargers_meta.json'
meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}

# operatörer: OCM:s operatörs-id först, annars nyckelord i namnet
OPID = {3534: 'Tesla', 23: 'Tesla', 3299: 'Ionity', 198: 'Recharge', 3510: 'Circle K', 3403: 'E.ON', 3343: 'InCharge',
        3492: 'Mer', 103: 'Allego', 3529: 'Jolt', 3763: 'OKQ8', 136: 'Virta', 73: 'EVBox'}
KW = [('supercharger', 'Tesla'), ('tesla', 'Tesla'), ('ionity', 'Ionity'), ('recharge', 'Recharge'), ('circle k', 'Circle K'),
      ('ingo', 'Circle K'), ('e.on', 'E.ON'), ('eon ', 'E.ON'), ('incharge', 'InCharge'), ('vattenfall', 'InCharge'),
      (' mer', 'Mer'), ('mer ', 'Mer'), ('allego', 'Allego'), ('jolt', 'Jolt'), ('okq8', 'OKQ8'), ('virta', 'Virta'),
      ('eways', 'Eways'), ('spirii', 'Spirii'), ('fastned', 'Fastned'), ('kwatt', 'kWatt'), ('clever', 'Clever'),
      ('chargenode', 'ChargeNode'), ('plugit', 'Övriga'), ('emobility', 'Övriga'), ('preem', 'Recharge'), ('st1', 'St1'),
      ('qstar', 'Qstar'), ('evbox', 'EVBox'), ('monta', 'Monta'), ('ellevio', 'Ellevio'), ('kempower', 'Övriga'),
      ('zaptec', 'Övriga'), ('juicebar', 'Övriga')]
def op_of(p, name):
    o = OPID.get(p.get('OperatorID'))
    if o: return o
    n = ' ' + (name or '').lower() + ' '
    for k, v in KW:
        if k in n: return v
    return 'Övriga'
def km(a, b, c, d):
    la1, lo1, la2, lo2 = map(math.radians, (a, b, c, d))
    return 6371 * 2 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))

old = json.load(open(f'{S}/data/chargers.json')) if os.path.exists(f'{S}/data/chargers.json') else []

# --- Open Charge Map ---
ocm = []
files = glob.glob(os.path.join(args.ocm_dir, '*.json')) if args.ocm_dir else []
for f in files:
    try: p = json.load(open(f))
    except Exception: continue
    if p.get('StatusTypeID') in (100, 150, 200): continue   # ur drift / planerad / borttagen
    if p.get('UsageTypeID') in (2, 3, 6): continue          # privat / bara för boende eller anställda
    fast = [c for c in (p.get('Connections') or []) if (c.get('PowerKW') or 0) >= 150]
    if not fast: continue
    a = p.get('AddressInfo') or {}; name = (a.get('Title') or '').strip()
    if a.get('Latitude') is None: continue
    op = op_of(p, name)
    if op == 'Tesla': continue                              # Tesla tas från supercharge.info
    ocm.append(dict(name=name, town=(a.get('Town') or '').strip().title(), lat=round(a['Latitude'], 5),
                    lon=round(a['Longitude'], 5), kw=int(max(c['PowerKW'] for c in fast)),
                    n=int(sum((c.get('Quantity') or 1) for c in fast)), op=op, src='OCM',
                    upd=(p.get('DateLastStatusUpdate') or p.get('DateLastVerified') or '')[:10]))
if len(ocm) < 100:
    print(f'OCM: bara {len(ocm)} platser hittade, behåller tidigare OCM-data', file=sys.stderr)
    ocm = [c for c in old if c['src'] == 'OCM']
else:
    meta['ocm'] = args.ocm_date or today
ded = []
for c in sorted(ocm, key=lambda c: -c['kw']):  # samma plats med flera poster inom 120 m
    if any(km(c['lat'], c['lon'], d['lat'], d['lon']) < 0.12 and (c['op'] == d['op'] or 'Övriga' in (c['op'], d['op'])) for d in ded): continue
    ded.append(c)

# --- Tesla från supercharge.info ---
tesla = json.load(open(f'{S}/data/tesla_se.json'))
if not args.no_tesla:
    try:
        req = urllib.request.Request('https://supercharge.info/service/supercharge/allSites',
                                     headers={'User-Agent': 'Laddresan (github.com; ruttplanerare for elbil)'})
        sites = json.load(urllib.request.urlopen(req, timeout=60))
        t2 = []
        for s in sites:
            ad = s.get('address') or {}
            if (ad.get('country') or '') != 'Sweden': continue
            gps = s.get('gps') or {}
            if gps.get('latitude') is None: continue
            t2.append([s.get('name') or ad.get('city') or '', s.get('status') or '', round(gps['latitude'], 5), round(gps['longitude'], 5),
                       int(s.get('stallCount') or 0), int(s.get('powerKilowatt') or 0), 1 if s.get('otherEVs') else 0,
                       (s.get('dateOpened') or '')[:10]])
        if len(t2) >= 50:
            tesla = t2; meta['tesla'] = today
            json.dump(tesla, open(f'{S}/data/tesla_se.json', 'w'), ensure_ascii=False)
        else:
            print(f'supercharge.info: bara {len(t2)} svenska platser, behåller tidigare data', file=sys.stderr)
    except Exception as e:
        print('supercharge.info gick inte att nå, behåller tidigare data:', e, file=sys.stderr)
for name, status, lat, lon, stalls, kw, other, dt in tesla:
    if status not in ('OPEN', 'EXPANDING') or not other or kw < 150: continue
    nm = name.replace(', Sweden', '').replace(' Sweden', '').strip(' -,')
    ded.append(dict(name='Tesla Supercharger ' + nm, town=nm.split(',')[0].split(' - ')[0], lat=lat, lon=lon, kw=kw,
                    n=stalls, op='Tesla', src='supercharge.info', upd=dt))

json.dump(ded, open(f'{S}/data/chargers.json', 'w'), ensure_ascii=False)
json.dump(meta, open(meta_path, 'w'), ensure_ascii=False)
print(f'{len(ded)} laddplatser (OCM {sum(c["src"] == "OCM" for c in ded)}, Tesla {sum(c["op"] == "Tesla" for c in ded)})')
print(collections.Counter(c['op'] for c in ded).most_common())
