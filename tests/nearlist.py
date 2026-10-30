# «Маршруты рядом со мной» in «Трассы»: OpenStreetMap MTB / bike routes (Israel Hiking base) + my saved routes, nearest
# first, at most 15, radius 5 / 15 / 30 km; «Смотреть» previews on the map, «Поехали» starts navigation, a failing Overpass still shows my routes.
import asyncio, sys, os, json, math, re
from urllib.parse import unquote_plus
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ME = (32.09, 34.88)
KX = 111320 * math.cos(ME[0] * math.pi / 180); KY = 110540
def ll(n, e): return [ME[0] + n / KY, ME[1] + e / KX]
def line(n0, e0, n1, e1, k=20): return [ll(n0 + (n1 - n0) * i / k, e0 + (e1 - e0) * i / k) for i in range(k + 1)]
# OSM relations: id → (route, name, geometry). Nearest: 101 (1 km), then 102 (4 km), 103 (12 km), 104 (25 km).
REL = {101: ('mtb', 'סינגל בן שמן', line(1000, -500, 1000, 1500)), 102: ('bicycle', 'Tel Aviv – Petah Tikva', line(-4000, 0, -4000, 3000)),
       103: ('mtb', 'Kfar Saba loop', line(12000, 0, 13000, 1000)), 104: ('mtb', 'Far trail', line(25000, 0, 26000, 0))}
def bounds(g): la = [p[0] for p in g]; lo = [p[1] for p in g]; return {'minlat': min(la), 'minlon': min(lo), 'maxlat': max(la), 'maxlon': max(lo)}

class M(Mocks):
    def __init__(s): super().__init__(); s.ovfail = False; s.queries = []
    async def handle(s, route):
        u = route.request.url
        if 'overpass' not in u: return await super().handle(route)
        q = unquote_plus((route.request.post_data or '')[5:]); s.queries.append(q)
        if s.ovfail: return await route.abort('failed')
        m = re.search(r'around:(\d+),([\d.]+),([\d.]+)', q)
        if m:
            R, la, lo = int(m.group(1)), float(m.group(2)), float(m.group(3))
            els = [{'type': 'relation', 'id': i, 'bounds': bounds(g), 'tags': {'type': 'route', 'route': r, 'name': n}} for i, (r, n, g) in REL.items()
                   if min(math.hypot((p[0] - la) * KY, (p[1] - lo) * KX) for p in g) <= R]
            return await route.fulfill(json={'elements': els}, headers={'Access-Control-Allow-Origin': '*'})
        m = re.search(r'relation\(id:([\d,]+)\)', q)
        if m:
            els = [{'type': 'relation', 'id': i, 'tags': {'type': 'route', 'route': REL[i][0], 'name': REL[i][1]},
                    'members': [{'type': 'way', 'ref': i * 10, 'role': '', 'geometry': [{'lat': p[0], 'lon': p[1]} for p in REL[i][2]]}]} for i in map(int, m.group(1).split(','))]
            return await route.fulfill(json={'elements': els}, headers={'Access-Control-Allow-Origin': '*'})
        return await route.fulfill(json={'elements': []}, headers={'Access-Control-Allow-Origin': '*'})

LIST = "[...document.querySelectorAll('#nr-list .item')].map(x => ({t: x.querySelector('.t').textContent, s: x.querySelector('.s').textContent}))"
async def main():
    url = serve(8817)
    async with async_playwright() as p:
        m = M(); b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=ME)
        await pg.wait_for_timeout(1500)
        # My routes: one 2.5 km away (from a website), one 60 km away.
        await pg.evaluate(f"saveRoute('Мой Бен-Шемен', {json.dumps(line(2500, 0, 3500, 0))}, 'Ссылка: https://rochvim-kavuh.com/ben-shemen')")
        await pg.evaluate(f"saveRoute('Эйлат', {json.dumps(line(-60000, 0, -61000, 0))}, 'Файл: eilat.gpx')")
        await pg.evaluate("showTab('routes'); routeSeg('trails')")
        await pg.wait_for_function("document.querySelectorAll('#nr-list .item').length > 0", timeout=15000)
        L = await pg.evaluate(LIST)
        check('1.1 the list opens with «Трассы», nearest first', [x['t'] for x in L] == ['סינגל בן שמן', 'Мой Бен-Шемен', 'Tel Aviv – Petah Tikva', 'Kfar Saba loop'], [x['t'] for x in L])
        check('1.2 a far route (25 km, 60 km) is not in the 15 km list', not any(x['t'] in ('Far trail', 'Эйлат') for x in L), [x['t'] for x in L])
        check('1.3 my route is marked «Мой» with its website', 'Мой · rochvim-kavuh.com' in L[1]['s'], L[1]['s'])
        check('1.4 distance and length are shown', '2.00 км' in L[0]['s'] and 'до него' in L[0]['s'], L[0]['s'])
        st = await pg.evaluate("document.getElementById('nr-status').textContent")
        check('1.5 status: count, radius, from you', 'Найдено: 4' in st and '15' in st and 'от вас' in st, st)
        # Radius 5 km: only the two nearest + mine.
        await pg.click('#nr-r [data-r="5000"]'); await pg.wait_for_timeout(1500)
        L = await pg.evaluate(LIST)
        check('2.1 radius 5 km: 12 km route gone', [x['t'] for x in L] == ['סינגל בן שמן', 'Мой Бен-Шемен', 'Tel Aviv – Petah Tikva'], [x['t'] for x in L])
        check('2.2 the radius is remembered', await pg.evaluate("lsGet('nearR')") == 5000)
        await pg.click('#nr-r [data-r="30000"]'); await pg.wait_for_timeout(1500)
        L = await pg.evaluate(LIST)
        check('2.3 radius 30 km: the 25 km trail appears, Eilat does not', 'Far trail' in [x['t'] for x in L] and 'Эйлат' not in [x['t'] for x in L], [x['t'] for x in L])
        # Preview: a tap on the route opens the map with it and a card — nothing starts yet.
        await pg.click('#nr-list .item[data-nv="0"] .t'); await pg.wait_for_timeout(1200)
        pv = await pg.evaluate("({card: !document.getElementById('nr-pv').hidden, map: document.getElementById('sheet-routes').hidden, nav: !!Nav.route, t: document.getElementById('nr-pv-t').textContent, km: document.getElementById('nr-pv-km').textContent, time: document.getElementById('nr-pv-time').textContent, n: document.getElementById('nr-pv-n').textContent, layer: !!NPV.layer && map.hasLayer(NPV.layer)})")
        check('P.1 tap on a route: map with the route and a card, navigation not started', pv['card'] and pv['map'] and not pv['nav'] and pv['layer'], pv)
        check('P.2 card: name, length, time', pv['t'] == 'סינגל בן שמן' and pv['km'] == '2.00' and pv['time'].startswith('~') and 'мин' in pv['time'], pv)
        check('P.3 card: one way, finish from start, distance to the start', 'В одну сторону' in pv['n'] and 'финиш в 2.00 км' in pv['n'] and 'до старта' in pv['n'], pv['n'])
        vis = await pg.evaluate("(() => { const r = document.getElementById('nr-pv').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth; })()")
        check('P.4 the card fits on the screen', vis)
        # Back: the list again, the preview gone.
        await pg.click('#nr-pv-back'); await pg.wait_for_timeout(600)
        r = await pg.evaluate("({list: !document.getElementById('sheet-routes').hidden && !document.getElementById('r-trails').hidden && document.querySelectorAll('#nr-list .item').length, card: !document.getElementById('nr-pv').hidden, layer: !!NPV.layer, nav: !!Nav.route})")
        check('P.5 «← К списку»: back to the same list, preview removed, no navigation', r['list'] == 5 and not r['card'] and not r['layer'] and not r['nav'], r)
        # A loop: the card says so.
        loop = line(0, 3000, 1000, 3000, 10) + line(1000, 3000, 1000, 4000, 10)[1:] + line(1000, 4000, 0, 4000, 10)[1:] + line(0, 4000, 0, 3000, 10)[1:]
        await pg.evaluate(f"nearPreview({{kind: 'mine', name: 'Кольцо', line: {json.dumps(loop)}, d: 3000}})"); await pg.wait_for_timeout(500)
        n = await pg.evaluate("document.getElementById('nr-pv-n').textContent")
        check('P.6 a loop is shown as a loop', n.startswith('Кольцо: старт и финиш в одной точке'), n)
        # «Поехали» on the card: navigation on that route.
        await pg.click('#nr-pv-go'); await pg.wait_for_timeout(1200)
        r = await pg.evaluate("({name: Nav.route && Nav.route.name, card: !document.getElementById('nr-pv').hidden, layer: !!NPV.layer})")
        check('P.7 «Поехали» on the card starts navigation, the card closes', r['name'] == 'Кольцо' and not r['card'] and not r['layer'], r)
        await pg.evaluate("Nav.stop(); showTab('routes'); routeSeg('trails')"); await pg.wait_for_timeout(500)
        # «Поехали» in the list: navigation with that line right away, and it asks how to start (we are 1 km from it).
        await pg.click('#nr-list [data-ng="0"]'); await pg.wait_for_timeout(1500)
        r = await pg.evaluate("({name: Nav.route && Nav.route.name, n: Nav.route && Nav.route.coords.length, ask: !document.getElementById('ask-join').hidden || !document.getElementById('ask-start').hidden})")
        check('3.1 «Поехали» in the list starts navigation on that route', r['name'] == 'סינגל בן שמן' and r['n'] >= 21, r)
        check('3.2 …and asks how to start (way to the start or the nearest point)', r['ask'], r)
        check('no JS errors (ru)', not log['errors'], log['errors'][:3]); await b.close()

        # Overpass down: my routes are still listed, with a note.
        m = M(); m.ovfail = True; b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=ME)
        await pg.wait_for_timeout(1500)
        await pg.evaluate(f"saveRoute('Мой Бен-Шемен', {json.dumps(line(2500, 0, 3500, 0))}, 'Ссылка: https://rochvim-kavuh.com/ben-shemen')")
        await pg.evaluate("showTab('routes'); routeSeg('trails')")
        await pg.wait_for_function("document.getElementById('nr-status').textContent.includes('OpenStreetMap')", timeout=60000)
        L = await pg.evaluate(LIST); st = await pg.evaluate("document.getElementById('nr-status').textContent")
        check('4.1 OSM down: my nearby route still listed, the note says OSM did not answer', [x['t'] for x in L] == ['Мой Бен-Шемен'] and 'не ответил' in st, (L, st))
        check('no JS errors (OSM down)', not log['errors'], log['errors'][:3]); await b.close()

        # Hebrew and English: nothing left untranslated in the block.
        for lang in ('he', 'en'):
            m = M(); b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, geo=ME, locale='he-IL' if lang == 'he' else 'en-US')
            await pg.wait_for_timeout(1500)
            await pg.evaluate(f"saveRoute('Ben Shemen', {json.dumps(line(2500, 0, 3500, 0))}, 'Ссылка: https://rochvim-kavuh.com/x')")
            await pg.evaluate("showTab('routes'); routeSeg('trails')")
            await pg.wait_for_function("document.querySelectorAll('#nr-list .item').length > 0", timeout=15000); await pg.wait_for_timeout(400)
            txt = await pg.evaluate("[document.querySelector('#r-trails h3').textContent, document.getElementById('nr-status').textContent, document.getElementById('nr-list').innerText, document.getElementById('nr-load').textContent].join(' | ')")
            check(f'5 {lang}: no untranslated Russian in «routes near me»', not re.search('[А-Яа-яЁё]', txt), txt[:300])
            check(f'no JS errors ({lang})', not log['errors'], log['errors'][:3]); await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
