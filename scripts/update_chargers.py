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

# --- NOBIL: laddarens spänning och ström (AFIR-data via Energimyndigheten, CC BY 3.0) ---
# NOBIL anger spänning och ström för nästan alla uttag, men oftast framräknade ur effekten med en fast
# spänning (t.ex. 1000 V/150 A för 150 kW). Bara när spänning × ström är minst 10 % större än effekten
# räknas värdena som laddarens verkliga gränser. Sammanställningen sparas i data/nobil_se.json så att
# den kan användas även om NOBIL inte går att nå. API:t anropas bara här, aldrig från webbläsaren.
NOBIL = f'{S}/data/nobil_se.json'
def nobil_fetch(key):
    import re, urllib.parse
    q = urllib.parse.urlencode(dict(apikey=key, countrycode='SWE', format='json', file='false'))
    d = json.loads(urllib.request.urlopen(f'https://nobil.no/api/server/datadump.php?{q}', timeout=180).read().decode('utf-8', 'replace'))
    def num(a):
        if not a: return None
        t, v = (a.get('trans') or '').strip(), str(a.get('attrval') or '').strip()
        v = v if v and (not t or t == (a.get('attrname') or '').strip()) else (t or v)
        m = re.search(r'\d+(?:[.,]\d+)?', v)
        return float(m.group(0).replace(',', '.')) if m else None
    out = []
    for s in d.get('chargerstations') or []:
        md = s.get('csmd') or {}
        pos = re.findall(r'-?\d+\.\d+', md.get('Position') or '')
        if len(pos) < 2: continue
        best = None
        for c in ((s.get('attr') or {}).get('conn') or {}).values():
            t = (c.get('5') or {}).get('trans') or ''
            m = re.search(r'(\d+)\s*kW', t)
            if 'DC' not in t.upper() or not m: continue
            kw, V, A = int(m.group(1)), num(c.get('12')), num(c.get('31'))
            real = bool(V and A and V * A / 1000 >= 1.1 * kw and V <= 1500 and A <= 1500)
            k = (kw, real, V or 0, A or 0)
            if best is None or k > best: best = k
        if best and best[0] >= 150:
            out.append(dict(lat=round(float(pos[0]), 5), lon=round(float(pos[1]), 5), kw=best[0], owner=(md.get('Owned_by') or '').strip(),
                            v=int(best[2]) if best[1] else 0, a=int(best[3]) if best[1] else 0))
    return out
nob = json.load(open(NOBIL)) if os.path.exists(NOBIL) else []
if os.environ.get('NOBIL_API_KEY'):
    try:
        n2 = nobil_fetch(os.environ['NOBIL_API_KEY'].strip())
        if len(n2) >= 500:
            nob = n2; meta['nobil'] = today
            json.dump(nob, open(NOBIL, 'w'), ensure_ascii=False, separators=(',', ':'))
        else:
            print(f'NOBIL: bara {len(n2)} platser, behåller tidigare data', file=sys.stderr)
    except Exception as e:
        print('NOBIL gick inte att nå, behåller tidigare data:', type(e).__name__, file=sys.stderr)
matched = 0
for c in ded:
    c.pop('vmax', None); c.pop('amax', None)
    near = [(km(c['lat'], c['lon'], n['lat'], n['lon']), n) for n in nob if abs(n['lat'] - c['lat']) < 0.005]
    near = [x for x in near if x[0] < 0.15 and ('tesla' in x[1]['owner'].lower()) == (c['op'] == 'Tesla')]  # Tesla och andra kan stå granne
    if not near: continue
    matched += 1
    n = min(near, key=lambda x: x[0])[1]
    if n['v'] and n['a']:
        c['vmax'], c['amax'] = n['v'], n['a']
print(f'NOBIL: {len(nob)} platser, {matched} matchade, {sum("vmax" in c for c in ded)} med verklig spänning och ström')

json.dump(ded, open(f'{S}/data/chargers.json', 'w'), ensure_ascii=False)
json.dump(meta, open(meta_path, 'w'), ensure_ascii=False)
print(f'{len(ded)} laddplatser (OCM {sum(c["src"] == "OCM" for c in ded)}, Tesla {sum(c["op"] == "Tesla" for c in ded)})')
print(collections.Counter(c['op'] for c in ded).most_common())
