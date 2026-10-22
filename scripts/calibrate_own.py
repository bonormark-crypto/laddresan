"""Kalibrerar två bilar mot verklig körning (TeslaMate) och skriver data/cars_own.json.

    python scripts/calibrate_own.py

Mätvärdena är medianer avlästa ur diagrammen "Förbrukning mot fart – plan väg, utetemp ≥ 15 °C"
(200 m-bitar, lutning under ±1 %, jämn fart). De är effektbaserade, utan batteriförluster; bilens mätare
visar 5–10 % mer, så de räknas upp med METER = 1,07 till samma grund som modellen (energi ur batteriet).

Luftmotstånd (cda) och effektivt rullmotstånd (crr) anpassas med minsta kvadrat till modellens förbrukning
vid 20 °C och sommardäck. Model Y-datan är gles under 100 km/h och vägs därför lägre (vikt 1 mot 3), och
cda begränsas till ett fysikaliskt rimligt intervall.
"""
import json, os, itertools
S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METER = 1.07
SPEED = [75, 85, 95, 105, 115, 125, 135]
OWN = [
    dict(name='Tesla Model 3 Long Range 2019–2023 (egen körning, 12 479 km)', base='2021 Tesla Model 3 LR (82 kWh)',
         meas=[103, 115, 126, 137, 154, 172, 187], w=[1, 1, 1, 1, 1, 1, 1], kg=1850, b=75.0, start=0.17,
         src='TeslaMate, 80 körningar aug 2024–okt 2026'),
    dict(name='Tesla Model Y Long Range AWD 2025– (egen körning, 2 602 km)', base='Tesla Model Y Premium AWD 2026',
         meas=[150, 161, 153, 164, 165, 194, 208], w=[1, 1, 1, 3, 3, 3, 3], kg=1997, b=79.0, start=0.50,
         src='TeslaMate, 32 körningar jun–okt 2026'),
]
ETA = 0.90; LOAD = 100; T = 20

def cons(cda, crr, kg, v):  # samma formel som consumption() i src/index.src.html, plan väg, 20 °C, sommardäck
    rho = 101325 / (287.05 * (273.15 + T)); vs = v / 3.6
    cop = min(3.5, max(1, 2.3 + 0.09 * T)); aux = (0.5 + max(0, 21 - T) * 0.11 / cop) / v * 100
    trac = (0.5 * rho * cda * vs * vs + crr * (kg + LOAD) * 9.81) / 36 / ETA
    return (trac + aux) * 1.05 * 10  # Wh/km

extra = {c['name']: c for c in json.load(open(f'{S}/data/cars_extra.json'))}
out = []
for o in OWN:
    best = min(((sum(w * (cons(cda, crr, o['kg'], v) - m * METER) ** 2 for v, m, w in zip(SPEED, o['meas'], o['w'])), cda, crr)
                for cda in [x / 1000 for x in range(400 if o["w"][0] == o["w"][-1] else 500, 660, 2)] for crr in [x / 100000 for x in range(600, 1600, 5)]))
    _, cda, crr = best
    car = dict(name=o['name'], b=o['b'], kg=o['kg'], cda=round(cda, 3), crr=round(crr, 5), eta=ETA, pre=True, own=True,
               start=o['start'], src=o['src'], fit=[[v, round(m * METER), round(cons(cda, crr, o['kg'], v))] for v, m in zip(SPEED, o['meas'])])
    b = extra.get(o['base'])
    if b: car.update(kw=b['kw'], dc=b['dc'], curve=b['curve'])        # uppmätt laddkurva för modellen
    else: car.update(prof=3, dc=250, curve='Excelmodellens profil för Tesla Model Y')  # samma laddning som grundurvalets Model Y
    out.append(car)
    print(car['name'], 'cda', car['cda'], 'crr', car['crr'], 'mätt/modell', car['fit'])
json.dump(out, open(f'{S}/data/cars_own.json', 'w'), ensure_ascii=False, separators=(',', ':'))
