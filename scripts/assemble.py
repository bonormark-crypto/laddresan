"""Bygger Laddresan till en enda HTML-fil.

    python scripts/assemble.py                    # webbplatsen -> dist/index.html
    python scripts/assemble.py --target claude    # artifact-versionen för claude.ai

Data läses från data/: vägnät (graph_stage1b.json), höjd (elev_b.json), laddare (chargers.json,
chargers_meta.json), orter (se_cities.json) och baskarta (basemap.json).
"""
import argparse, json, os, datetime
import numpy as np
from scipy.spatial import cKDTree
from pyproj import Transformer

S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # projektets rot
ap = argparse.ArgumentParser()
ap.add_argument('--target', choices=['site', 'claude'], default='site')
ap.add_argument('--out', default=None)
ap.add_argument('--saved', default=None,
                help='JSON-fil med sparade platser [[namn, lat, lon, ort], ...] (bara för --target claude)')
args = ap.parse_args()
out_path = args.out or os.path.join(S, 'dist', 'index.html' if args.target == 'site' else 'laddresan.html')

T = Transformer.from_crs(4326, 3006, always_xy=True)  # WGS84 -> SWEREF 99 TM
g = json.load(open(f'{S}/data/graph_stage1b.json'))['edges']
elev = json.load(open(f'{S}/data/elev_b.json'))  # {osm-nod: meter}
jn = {}
def nid(o):
    if o not in jn: jn[o] = len(jn)
    return jn[o]
E = []; allpts = []; owner = []
for ei, e in enumerate(g):
    a = nid(e['a']); b = nid(e['b'])
    P = []; Z = []
    for k, (x, y) in enumerate(e['pts']):
        P += [round(x, 2), round(y, 2)]
        Z.append(int(round(elev.get(str(e['ids'][k]), 0))))
        allpts.append((x, y)); owner.append((ei, k))
    E.append([a, b, P, Z, [round(l, 3) for l in e['L']], [round(v, 1) for v in e['V']]])
tree = cKDTree(np.array(allpts))
def snap(x, y):
    d, i = tree.query([x, y]); ei, k = owner[i]; return ei, k, d

places = []
# Sparade platser byggs bara in i den privata claude.ai-versionen. På webbplatsen sparar var och en
# sina egna platser i webbläsaren.
if args.target == 'claude' and args.saved:
    for n, (name, la, lo, sub) in enumerate(json.load(open(args.saved)), start=1):
        x, y = [v / 1000 for v in T.transform(lo, la)]; ei, k, d = snap(x, y)
        places.append([name, '', 0, round(x, 2), round(y, 2), la, lo, ei, k, n, name, sub])
nsaved = len(places)
far = []
for name, pop, la, lo, adm, fc in json.load(open(f'{S}/data/se_cities.json')):
    if adm == '05' or fc in ('PPLX', 'PPLH', 'PPLQ', 'PPLW'): continue
    x, y = [v / 1000 for v in T.transform(lo, la)]; ei, k, d = snap(x, y)
    if d > 30: far.append((name, round(d))); continue
    places.append([name, adm, pop, round(x, 2), round(y, 2), round(la, 5), round(lo, 5), ei, k, 0])

C = []
for c in json.load(open(f'{S}/data/chargers.json')):
    x, y = [v / 1000 for v in T.transform(c['lon'], c['lat'])]
    C.append([c['name'], c['op'], c['kw'], c['n'], round(x, 2), round(y, 2), c['lat'], c['lon'], c['town'],
              c['src'] == 'OCM' and 'Open Charge Map' or 'supercharge.info', c['upd']])
# laddplatser som saknas i de öppna källorna
EXTRA = [('Klevshult E4 (Plugit, tidigare GreenStop/ChargeNode)', 'Övriga', 400, 8, 57.3552, 14.1014, 'Klevshult', 'pressmeddelanden ChargeNode/Plugit', '2026-03'),
         ('ChargeNode Rasta Ödeshög, Lievägen 2', 'ChargeNode', 400, 24, 58.23317, 14.67172, 'Ödeshög', 'uppgift från användare', '2026-10')]
for name, op, kw, n, la, lo, town, srcn, upd in EXTRA:
    x, y = [v / 1000 for v in T.transform(lo, la)]
    C.append([name, op, kw, n, round(x, 2), round(y, 2), la, lo, town, srcn, upd])

MON = ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti', 'september', 'oktober', 'november', 'december']
def sv_date(iso, day=True):
    try:
        d = datetime.date.fromisoformat(iso[:10])
        return (f'{d.day} ' if day else '') + f'{MON[d.month - 1]} {d.year}'
    except Exception:
        return iso
cm = {}
if os.path.exists(f'{S}/data/chargers_meta.json'):
    cm = json.load(open(f'{S}/data/chargers_meta.json'))
roadkm = round(sum(sum(e[4]) for e in E))
meta = {'roadkm': f'{roadkm:,}'.replace(',', ' '), 'places': len(places) - nsaved, 'nsaved': nsaved,
        'ocm': sv_date(cm['ocm'], False) if cm.get('ocm') else 'april 2026',
        'tesla': sv_date(cm['tesla']) if cm.get('tesla') else '20 oktober 2026', 'nch': len(C),
        'built': datetime.date.today().isoformat()}
graph = {'n': len(jn), 'e': E}
sep = (',', ':')
src = open(f'{S}/src/index.src.html').read()
out = (src.replace('__GRAPH__', json.dumps(graph, separators=sep))
          .replace('__PLACES__', json.dumps(places, separators=sep, ensure_ascii=False))
          .replace('__CHARGERS__', json.dumps(C, separators=sep, ensure_ascii=False))
          .replace('__BASE__', open(f'{S}/data/basemap.json').read())
          .replace('__META__', json.dumps(meta, ensure_ascii=False))
          .replace('__CARS_EXTRA__', open(f'{S}/data/cars_extra.json').read())
          .replace('__CARS_OWN__', open(f'{S}/data/cars_own.json').read())
          .replace('__TARGET__', args.target))
if args.target == 'site':  # claude.ai lägger själv till dokumentramen; webbplatsen behöver en egen
    icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 34 34'%3E%3Crect width='34' height='34' rx='7' "
            "fill='%230a5ea6'/%3E%3Cpath d='M19 6 10 19h6l-2 9 9-13h-6z' fill='white'/%3E%3C/svg%3E")
    out = ('<!doctype html>\n<html lang="sv">\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
           '<meta name="description" content="Ruttplanerare för elbil i Sverige: laddstopp vid snabbladdare från 150 kW, förbrukning med höjd, väder och vind.">\n'
           '<meta name="theme-color" content="#0a5ea6">\n'
           f'<link rel="icon" href="{icon}">\n' + out + '\n</html>\n')
os.makedirs(os.path.dirname(out_path), exist_ok=True)
open(out_path, 'w').write(out)
print(f'{args.target}: {out_path} · {len(jn)} noder, {len(E)} kanter, {roadkm} km väg, {len(places) - nsaved} orter, '
      f'{nsaved} sparade, {len(C)} laddplatser, {round(len(out) / 1e6, 2)} MB')
if far: print('utelämnade orter (långt från vägnätet):', far)
