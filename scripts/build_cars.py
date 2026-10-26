"""Bygger data/cars_extra.json: bilar med normaliserad förbrukning och uppmätt laddkurva.

    python scripts/build_cars.py Rackvidd_normaliserad.xlsx Charging_curves.xlsx

- Rackvidd_normaliserad.xlsx, bladet "Sammanfattning per bil": normaliserad Wh/km vid 90 och 120 km/h
  (20 °C, torr väg, genomsnittligt sommardäck, standardfälg), använd kapacitet och vikt.
- Charging_curves.xlsx, bladet "Charging curve": uppmätt laddeffekt (kW) per % laddnivå.
Vilken laddkurva som hör till vilken bil står i scripts/car_mapping.py.
"""
import json, sys, os, openpyxl
S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from car_mapping import M, EXTRA_CURVES, FIXES, SMOOTH, PATCH
ws = openpyxl.load_workbook(sys.argv[1], data_only=True)['Sammanfattning per bil']
cars = {r[0]: dict(name=r[0], n=r[1], cap=r[2], kg=r[3], w90=r[13], w120=r[15])
        for r in ws.iter_rows(min_row=5, values_only=True) if r[0]}
ws = openpyxl.load_workbook(sys.argv[2], data_only=True)['Charging curve']
hdr = [c.value for c in ws[1]]; cols = list(ws.iter_cols(min_row=2, max_row=200, values_only=True))
curves = {h: [(cols[0][i], v) for i, v in enumerate(cols[j]) if isinstance(v, (int, float)) and isinstance(cols[0][i], (int, float))]
          for j, h in enumerate(hdr) if j and h}
curves.update(EXTRA_CURVES)
EXCL = {'BMW iX3 50 xDrive', 'Volvo EX60 Twin Ultra P10', 'VW ID4 GTX 82 kWh', 'Tesla Model Y LR Juniper', 'Jaguar I-Pace EV320', 'Jaguar I-Pace 90 kWh'}
# samma konstanter som Laddresans förbrukningsmodell (K i index.src.html)
T = 20; cabin = 21; base = 0.5; heatPerC = 0.11; cop = min(3.5, max(1, 2.3 + 0.09 * T)); markup = 0.05
rho = 101325 / (287.05 * (273.15 + T)); CRR = 0.0076; LOAD = 80  # referensdäck och förare+packning enligt normaliseringen
aux_kw = base + max(0, cabin - T) * heatPerC / cop
ETA = 0.88  # drivlinans verkningsgrad enligt normaliseringsmodellen
def fit(c):
    """Luftmotstånd (cda) och effektivt rullmotstånd (crr) så att modellen ger den normaliserade förbrukningen
    vid 90 och 120 km/h (20 °C, sommardäck, förare + packning 80 kg). Med bara en mätpunkt: crr = referensdäcket."""
    m = float(c['kg']) + LOAD
    pts = [(v, float(c[k]) / 10) for v, k in ((90, 'w90'), (120, 'w120')) if c.get(k) not in (None, '')]  # kWh/100 km
    rows = []
    for v, y in pts:
        vs = v / 3.6
        lhs = (y / (1 + markup) - aux_kw / v * 100) * 36 * ETA   # = 0.5ρ v²·cda + m g·crr
        rows.append((0.5 * rho * vs * vs, m * 9.81, lhs))
    crr = None
    if len(rows) == 2:
        (a1, b1, y1), (a2, b2, y2) = rows; det = a1 * b2 - a2 * b1
        cda = (y1 * b2 - y2 * b1) / det; crr = (a1 * y2 - a2 * y1) / det
        how = 'exakt'
        if not (0.005 <= crr <= 0.016) or not (0.35 <= cda <= 1.5):
            crr = min(0.016, max(0.005, crr))  # orimligt rullmotstånd: närmaste rimliga värde, cda anpassas
            cda = sum(a * (y - b * crr) for a, b, y in rows) / sum(a * a for a, b, y in rows); how = 'anpassad'
    if crr is None:  # bara en mätpunkt: referensdäckets rullmotstånd
        crr = CRR; cda = sum(a * (y - b * crr) for a, b, y in rows) / sum(a * a for a, b, y in rows); how = 'en punkt'
    return round(cda, 3), ETA, how, m, round(crr, 5)
def curve101(pts):
    pts = sorted(pts); socs = [p[0] for p in pts]; kws = [float(p[1]) for p in pts]
    out = []
    for s in range(101):
        if s <= socs[0]: out.append(kws[0])
        elif s >= socs[-1]:
            # efter sista mätpunkten: linjärt ned mot 30 % av sista värdet vid 100 %
            if socs[-1] >= 100: out.append(kws[-1])
            else: f = (s - socs[-1]) / (100 - socs[-1]); out.append(kws[-1] * (1 - 0.7 * f))
        else:
            i = max(j for j in range(len(socs)) if socs[j] <= s); k = min(i + 1, len(socs) - 1)
            t = 0 if socs[k] == socs[i] else (s - socs[i]) / (socs[k] - socs[i]); out.append(kws[i] + t * (kws[k] - kws[i]))
    return [round(x, 1) for x in out]
out = []; how_n = {}
for name, (cv, note) in M.items():
    if name in EXCL: continue
    c = cars[name]
    if c.get('w90') in (None, '') and c.get('w120') in (None, ''): continue
    cda, eta, how, m, crr = fit(c); how_n[how] = how_n.get(how, 0) + 1
    kw = curve101(curves[cv])
    for a0, a1 in SMOOTH.get(name, []):   # mätfel: rak linje mellan punkterna strax utanför intervallet
        lo, hi = a0 - 1, a1 + 1
        for x in range(a0, a1 + 1): kw[x] = round(kw[lo] + (x - lo) / (hi - lo) * (kw[hi] - kw[lo]), 1)
    pp = PATCH.get(name, [])
    for (s0, k0), (s1, k1) in zip(pp, pp[1:]):
        for x in range(s0, s1 + 1): kw[x] = round(k0 + (x - s0) / (s1 - s0) * (k1 - k0), 1) if s1 > s0 else k1
    wl = c.get('wltp') if False else None
    out.append(dict(name=name, b=round(float(c['cap']), 1), kg=round(float(c['kg'])), cda=cda, eta=eta, crr=crr, dc=round(max(kw)),
                    kw=kw, pre=max(kw) >= 120, curve=cv, cnote=note, n=int(c['n']), w90=round(float(c['w90'])) if c.get('w90') not in (None, '') else None,
                    w120=round(float(c['w120'])) if c.get('w120') not in (None, '') else None))
for d in out: d.update(FIXES.get(d['name'], {}))
out.sort(key=lambda d: d['name'].lower().lstrip('0123456789 '))
json.dump(out, open(f'{S}/data/cars_extra.json', 'w'), ensure_ascii=False, separators=(',', ':'))
print(len(out), how_n)
import statistics
print('crr range', min(d['crr'] for d in out), max(d['crr'] for d in out), 'cda range', min(d['cda'] for d in out), max(d['cda'] for d in out))
print([(d['name'],d['cda'],d['crr']) for d in out if d['cda']<0.45 or d['cda']>1.1 or d['crr']<0.006 or d['crr']>0.014])
