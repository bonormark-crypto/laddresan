"""Mäter hur mycket hårdvarudata NOBIL har för svenska snabbladdare.

    NOBIL_API_KEY=... python scripts/nobil_check.py [--out rapport.md] [--json nobil_se.json]

Hämtar NOBIL:s datadump för Sverige och räknar, per effektklass och operatör, hur många DC-uttag
som har spänning, ström och tillverkare ifyllt. Attributen hittas både på ID (12 spänning,
31 ström, 23 tillverkare enligt nobil.no/admin/attributes.php) och på namn, eftersom
dokumentationen inte listar dem. Nyckeln läses bara från miljövariabeln och skrivs aldrig ut.

NOBIL:s villkor: API:t får inte anropas direkt från slutanvändare. Data ska hämtas och
bearbetas i ett mellansteg, här i GitHub Actions.
"""
import argparse, collections, json, os, re, sys, urllib.parse, urllib.request

URL = 'https://nobil.no/api/server/datadump.php'
IDS = {'volt': {'12'}, 'amp': {'31'}, 'manu': {'23'}}
NAMES = {'volt': re.compile(r'volt|spænn|spänn', re.I),
         'amp': re.compile(r'amp|strøm|ström|current', re.I),
         'manu': re.compile(r'manufact|produsent|tillverk|fabrikat|model', re.I)}
LABEL = {'volt': 'Spänning', 'amp': 'Ström', 'manu': 'Tillverkare'}


def fetch(key):
    q = urllib.parse.urlencode(dict(apikey=key, countrycode='SWE', format='json', file='false'))
    with urllib.request.urlopen(f'{URL}?{q}', timeout=180) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def val(a):
    t, v = (a.get('trans') or '').strip(), str(a.get('attrval') or '').strip()
    v = v if (v and (not t or t == (a.get('attrname') or '').strip())) else (t or v)
    return '' if v.lower() in ('', '-', 'unknown', 'ukjent', 'okänd', 'n/a') else v


def kind(a):
    tid = str(a.get('attrtypeid', ''))
    for k in IDS:
        if tid in IDS[k]:
            return k
    return None


def num(v):
    m = re.search(r'\d+(?:[.,]\d+)?', v or '')
    return float(m.group(0).replace(',', '.')) if m else None


def dc_kw(conn):
    t = (conn.get('5') or {}).get('trans', '') or ''
    m = re.search(r'(\d+)\s*kW', t)
    if 'DC' not in t.upper() or not m:
        return None
    return int(m.group(1))


def klass(kw):
    return '150 kW eller mer' if kw >= 150 else '50–149 kW' if kw >= 50 else 'under 50 kW'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out'); ap.add_argument('--json')
    a = ap.parse_args()
    key = os.environ.get('NOBIL_API_KEY', '').strip()
    if not key:
        sys.exit('NOBIL_API_KEY saknas')
    d = fetch(key)
    st = d.get('chargerstations') or []
    attrnames = collections.Counter()
    tot = collections.Counter(); have = collections.defaultdict(collections.Counter)
    sites = collections.defaultdict(set); sites_have = collections.defaultdict(lambda: collections.defaultdict(set))
    ops = collections.defaultdict(collections.Counter); values = collections.defaultdict(collections.Counter)
    rows = []; combos = collections.Counter(); opcombo = collections.defaultdict(collections.Counter); ratio = collections.Counter(); manuop = collections.Counter(); opratio = collections.defaultdict(collections.Counter)
    for s in st:
        md = s.get('csmd') or {}; at = s.get('attr') or {}
        sattr = at.get('st') or {}
        for x in sattr.values():
            attrnames[(str(x.get('attrtypeid')), x.get('attrname'), 'st')] += 1
        conns = at.get('conn') or {}
        for c in conns.values():
            for x in c.values():
                attrnames[(str(x.get('attrtypeid')), x.get('attrname'), 'conn')] += 1
            kw = dc_kw(c)
            if kw is None:
                continue
            k = klass(kw); op = (md.get('Owned_by') or 'okänd').strip()
            found = {}
            for x in list(c.values()) + list(sattr.values()):
                kk = kind(x)
                if kk and val(x) and kk not in found:
                    found[kk] = val(x)
            tot[k] += 1; sites[k].add(md.get('id'))
            for kk, v in found.items():
                have[k][kk] += 1; sites_have[k][kk].add(md.get('id')); values[kk][v] += 1
            V, A = num(found.get('volt')), num(found.get('amp'))
            if found.get('manu'):
                manuop[f"{op}, {kw} kW: {found['manu']}"] += 1
            if k == '150 kW eller mer':
                combos[(kw, V, A)] += 1; opcombo[op][(V, A)] += 1
                if V and A:
                    r = V * A / 1000 / kw
                    opratio[op]['tot'] += 1; opratio[op]['der' if 0.9 <= r <= 1.1 else 'hi' if r > 1.1 else 'lo'] += 1
                    ratio['V\u00d7A ungef\u00e4r lika med nominell effekt (0,9\u20131,1)' if 0.9 <= r <= 1.1 else 'V\u00d7A st\u00f6rre \u00e4n nominell effekt' if r > 1.1 else 'V\u00d7A mindre \u00e4n nominell effekt'] += 1
                ops[op]['n'] += 1
                for kk in found:
                    ops[op][kk] += 1
            rows.append(dict(id=md.get('id'), name=md.get('name'), owner=op, kw=kw,
                             pos=md.get('Position'), **found))
    pct = lambda n, t: f'{n} ({100 * n / t:.0f} %)' if t else '0'
    L = [f'# NOBIL: hårdvarudata för svenska DC-laddare', '',
         f'{len(st)} laddplatser i dumpen, {sum(tot.values())} DC-uttag.', '',
         '## Ifyllnadsgrad per effektklass (uttag)', '',
         '| Klass | DC-uttag | Platser | Spänning | Ström | Tillverkare |', '| --- | --- | --- | --- | --- | --- |']
    for k in ('150 kW eller mer', '50–149 kW', 'under 50 kW'):
        if tot[k]:
            L.append(f'| {k} | {tot[k]} | {len(sites[k])} | ' + ' | '.join(pct(have[k][x], tot[k]) for x in ('volt', 'amp', 'manu')) + ' |')
    L += ['', '## Operatörer, uttag på 150 kW eller mer', '',
          '| Operatör (Owned_by) | Uttag | Spänning | Ström | Tillverkare |', '| --- | --- | --- | --- | --- |']
    for op, c in sorted(ops.items(), key=lambda x: -x[1]['n'])[:25]:
        L.append(f'| {op} | {c["n"]} | ' + ' | '.join(pct(c[x], c['n']) for x in ('volt', 'amp', 'manu')) + ' |')
    for kk in ('manu', 'volt', 'amp'):
        L += ['', f'## Vanligaste värden: {LABEL[kk]} (alla DC-uttag)', '']
        L += [f'- {v}: {n}' for v, n in values[kk].most_common(20)] or ['- inga']
    L += ['', '## Uttag på 150 kW eller mer: V×A jämfört med nominell effekt', '']
    L += [f'- {k}: {n}' for k, n in ratio.most_common()]
    L += ['', '## Uttag på 150 kW eller mer: vanligaste kombinationer', '', '| Nominell kW | V | A | Uttag |', '| --- | --- | --- | --- |']
    L += [f'| {kw} | {V} | {A} | {n} |' for (kw, V, A), n in combos.most_common(30)]
    L += ['', '## Per operatör: vanligaste V/A-par (150 kW eller mer)', '', '| Operatör | V/A-par (antal uttag) |', '| --- | --- |']
    for op, c in sorted(ops.items(), key=lambda x: -x[1]['n'])[:25]:
        L.append(f'| {op} | ' + ', '.join(f'{V:g} V/{A:g} A ({n})' if V and A else f'saknas ({n})' for (V, A), n in opcombo[op].most_common(6)) + ' |')
    L += ['', '## Per operatör: V×A mot nominell effekt (150 kW eller mer)', '', '| Operatör | Med V och A | V×A ≈ nominell | V×A större | V×A mindre |', '| --- | --- | --- | --- | --- |']
    for op, c in sorted(opratio.items(), key=lambda x: -x[1]['tot'])[:30]:
        L.append(f"| {op} | {c['tot']} | {pct(c['der'], c['tot'])} | {pct(c['hi'], c['tot'])} | {pct(c['lo'], c['tot'])} |")
    L += ['', '## Tillverkare per operatör och effekt (alla DC-uttag)', '']
    L += [f'- {k}: {n}' for k, n in manuop.most_common(30)] or ['- inga']
    L += ['', '## Alla attribut i dumpen', '', '| ID | Namn | Nivå | Antal |', '| --- | --- | --- | --- |']
    L += [f'| {i} | {n} | {lv} | {c} |' for (i, n, lv), c in sorted(attrnames.items(), key=lambda x: (x[0][2], int(x[0][0]) if x[0][0].isdigit() else 999))]
    rep = '\n'.join(L) + '\n'
    print(rep)
    if a.out:
        open(a.out, 'w').write(rep)
    if a.json:
        json.dump(rows, open(a.json, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main()
