#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""桃園機場現在從哪一邊降落？（GitHub Actions 每 10 分鐘跑一次，輸出 public/status.json）

判斷方式：抓桃園機場附近的即時航機位置（adsb.lol，備援 adsb.fi），
找跑道延長線上低空、正在下降或爬升的飛機，看牠往東北還是往西南飛。
  往東北（05 方向）→ 降落從西南邊進來 → 去西南側：華興池、第三航廈機場咖啡
  往西南（23 方向）→ 降落從東北邊進來 → 去東北側：復興航棧
這一輪剛好沒有低空飛機時，沿用 60 分鐘內最近一次的判斷；再沒有，才用機場風向推估。
"""
import json, math, os, sys, time, urllib.request
from datetime import datetime, timezone

UA = {'User-Agent': 'kafutw-tpe-landing/1.0 (+https://kafutw.github.io/tpe-landing/)'}
ARP = (25.0777, 121.2328)
RWY = {'north': ((25.0729, 121.2160), (25.0945, 121.2434)),   # 05L → 23R（OurAirports）
       'south': ((25.0608, 121.2235), (25.0833, 121.2520))}   # 05R → 23L
RWY_NAME = {'north': '北跑道', 'south': '南跑道'}
K = 111.2
OUT = os.path.join(os.path.dirname(__file__), '..', 'public', 'status.json')
PREV_URL = 'https://kafutw.github.io/tpe-landing/status.json'


def get_json(url):
    r = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(r, timeout=30))


def xy(a, b):
    return (b[1] - a[1]) * K * math.cos(math.radians(25.07)), (b[0] - a[0]) * K


def angdiff(a, b):
    return abs(((a - b) + 180) % 360 - 180)


def side_of_airport(lat, lon):
    """飛機在機場的哪一邊（給人看的）"""
    dx, dy = xy(ARP, (lat, lon))
    d = math.hypot(dx, dy)
    b = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    names = ['北邊', '東北邊', '東邊', '東南邊', '南邊', '西南邊', '西邊', '西北邊']
    return names[int(((b + 22.5) % 360) // 45)], d


def fetch_aircraft():
    srcs = [('adsb.lol', 'https://api.adsb.lol/v2/lat/%s/lon/%s/dist/25' % ARP),
            ('adsb.fi', 'https://opendata.adsb.fi/api/v2/lat/%s/lon/%s/dist/25' % ARP)]
    for name, url in srcs:
        try:
            d = get_json(url)
            return name, d.get('ac') or d.get('aircraft') or []
        except Exception as e:
            print('fetch fail', name, e, file=sys.stderr)
    return None, []


def classify(ac):
    out = []
    for a in ac:
        lat, lon, trk = a.get('lat'), a.get('lon'), a.get('track')
        alt = a.get('alt_baro')
        rate = a.get('baro_rate', a.get('geom_rate'))
        if None in (lat, lon, trk, rate) or not isinstance(alt, (int, float)):
            continue
        if alt > 5000 or (a.get('seen_pos') or 0) > 60:
            continue
        best = None
        for key, (A, B) in RWY.items():
            ux, uy = xy(A, B); L = math.hypot(ux, uy); ux /= L; uy /= L
            px, py = xy(A, (lat, lon))
            along, cross = px * ux + py * uy, px * uy - py * ux
            if abs(cross) < 3 and -25 < along < L + 25 and (best is None or abs(cross) < abs(best[2])):
                best = (key, along, cross, L)
        if not best:
            continue
        key, along, cross, L = best
        ne, sw = angdiff(trk, 50) < 35, angdiff(trk, 230) < 35
        if not (ne or sw):
            continue
        if rate < -200:
            phase = 'land'
            if ne and along > L + 2 or sw and along < -2:   # 已經飛過跑道頭還在下降，不合理就跳過
                continue
        elif rate > 200:
            phase = 'takeoff'
        else:
            continue
        where, dist = side_of_airport(lat, lon)
        out.append({'flight': (a.get('flight') or a.get('r') or '').strip(), 'type': a.get('t') or '',
                    'runway': '05' if ne else '23', 'phase': phase, 'rwy': RWY_NAME[key],
                    'alt_ft': int(alt), 'where': where, 'dist_km': round(dist, 1)})
    return out


def fetch_metar():
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            'https://aviationweather.gov/api/data/metar?ids=RCTP&hours=1&format=raw', headers=UA), timeout=30)
        line = r.read().decode().strip().splitlines()[0]
    except Exception as e:
        print('metar fail', e, file=sys.stderr)
        return None
    import re
    m = re.search(r'\b(\d{3}|VRB)(\d{2,3})(?:G\d{2,3})?KT\b', line)
    wind = None
    if m:
        wind = {'dir': None if m.group(1) == 'VRB' else int(m.group(1)), 'kt': int(m.group(2))}
    return {'raw': line, 'wind': wind}


def main():
    now = datetime.now(timezone.utc)
    src, ac = fetch_aircraft()
    ev = classify(ac)
    metar = fetch_metar()
    try:
        prev = get_json(PREV_URL + '?t=%d' % time.time())
    except Exception:
        prev = {}
    hist = prev.get('history', [])

    votes = {'05': sum(1 for e in ev if e['runway'] == '05'), '23': sum(1 for e in ev if e['runway'] == '23')}
    runway, basis = None, None
    if votes['05'] or votes['23']:
        if votes['05'] and votes['23']:
            runway = '05' if votes['05'] > votes['23'] else ('23' if votes['23'] > votes['05'] else None)
            basis = 'mixed'
        else:
            runway = '05' if votes['05'] else '23'
            basis = 'live'
    if runway is None:   # 沿用 60 分鐘內最近一次的實際判斷
        for h in reversed(hist):
            t = datetime.fromisoformat(h['t'])
            if h.get('basis') == 'live' and (now - t).total_seconds() < 3600:
                runway, basis = h['runway'], 'recent'
                break
    if runway is None and metar and metar['wind'] and metar['wind']['dir'] is not None and metar['wind']['kt'] >= 5:
        w = metar['wind']['dir']
        if angdiff(w, 50) < 70:
            runway, basis = '05', 'wind'
        elif angdiff(w, 230) < 70:
            runway, basis = '23', 'wind'

    rec = {'t': now.isoformat(timespec='seconds'), 'runway': runway, 'basis': basis, 'n': len(ev)}
    hist = (hist + [rec])[-48:]
    last_live = next((h for h in reversed(hist) if h.get('basis') == 'live'), None)
    status = {'updated': rec['t'], 'runway': runway, 'basis': basis, 'source': src,
              'evidence': ev[:8], 'metar': metar, 'last_live': last_live, 'history': hist}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(status, open(OUT, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: status[k] for k in ('updated', 'runway', 'basis', 'source')}, ensure_ascii=False), len(ev), 'evidence')


if __name__ == '__main__':
    main()
