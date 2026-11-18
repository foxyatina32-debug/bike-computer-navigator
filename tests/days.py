# v131: a long route by days (bikepacking, like Maps' day-by-day trips). In the route info, for a route ≥ 40 km:
# «По дням» — 30 / 50 / 70 / 100 km a day → stages about equal, each day ending at a place to sleep near the route
# (OpenStreetMap camp sites / huts / guest houses / hostels / hotels within 3 km, near the ideal split, nearer to the
# route is better); per day distance, climb, time, water points; «🏁 Финиш» on the last; nights numbered on the map.
# No places → equal days, said so. ru / he / en. Run: python3 tests/days.py
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
LAT0, LON0 = 31.0, 34.9
M = 1 / 110540; KX = 1 / (111320 * math.cos(LAT0 * math.pi / 180))
def pt(n, e=0, lat0=LAT0): return [round(lat0 + n * M, 7), round(LON0 + e * KX, 7)]
def route(km, lat0=LAT0): return [pt(n, 0, lat0) + [200 + 80 * math.sin(n / 7000)] for n in range(0, km * 1000 + 1, 100)]
R150 = route(150)
def node(ll, **t): return {'type': 'node', 'lat': ll[0], 'lon': ll[1], 'tags': t}
STAYS = [node(pt(52000, 200), tourism='camp_site', name='חניון לילה A'), node(pt(95000, 1500), tourism='hotel', name='Hotel B'), node(pt(60000, 2800), tourism='guest_house', name='Guest C'), node(pt(30000, 6000), tourism='hotel', name='Too Far')]
WATER = [node(pt(d * 1000, 30), amenity='drinking_water') for d in (10, 70, 120)]
FIX = """([stays, water]) => { window.__fail = false; window.overpass = async q => { if (q.startsWith('/*stay*/')) { if (window.__fail) throw new Error('offline'); return { elements: stays }; } if (q.includes('shelter')) return { elements: water }; return { elements: [] }; }; }"""
OUT = "[...document.querySelectorAll('#in-dout .dayc')].map(e => e.innerText.replace(/\\n/g, ' | '))"

async def open_info(pg, name, coords):
    await pg.evaluate(f"openRouteInfo(null, 'rec', {{ name: {json.dumps(name)}, coords: {json.dumps(coords)} }})"); await pg.wait_for_timeout(500)

async def main():
    url = serve(9059); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate(FIX, [STAYS, WATER]); await pg.evaluate("S.fit = 1; setMode('bike', true)")
        await open_info(pg, 'Поход', R150)
        check('route ≥ 40 km: «По дням» with 30 / 50 / 70 / 100 km a day', await pg.evaluate("!!document.getElementById('in-days') && document.querySelectorAll('#in-dkm button').length === 4"))
        await pg.click('#in-load'); await pg.wait_for_function("document.querySelector('#ins .poisum')", timeout=10000)
        await pg.click('#in-dkm [data-k="50"]'); await pg.click('#in-days')
        await pg.wait_for_function("document.querySelectorAll('#in-dout .dayc').length > 0", timeout=10000)
        d = await pg.evaluate(OUT)
        check('150 km at 50 km a day → 3 days', len(d) == 3, d)
        check('day 1 ends at the camp site 52 km on, 200 m off (nearer than the guest house 60 km on, 2.8 km off)', d[0].startswith('День 1 · 52.') and 'חניון לילה A' in d[0] and 'кемпинг' in d[0], d[0])
        check('day 2 ends at the hotel 95 km on, 1.5 km off the route', d[1].startswith('День 2 · 43.') and 'Hotel B' in d[1] and ('1.49 км от маршрута' in d[1] or '1.50 км от маршрута' in d[1]), d[1])
        check('day 3: «🏁 Финиш», 55 km', d[2].startswith('День 3 · 55.') and '🏁 Финиш' in d[2], d[2])
        check('each day: climb, riding time, water points (1 each)', all('↗' in x and '≈' in x and '💧 1' in x for x in d), d)
        far = await pg.evaluate("Days.plan.days.some(x => x.stay && x.stay.name === 'Too Far')")
        check('a place 6 km from the route is not offered', not far)
        await pg.click('#in-dmap'); await pg.wait_for_timeout(400)
        mk = await pg.evaluate("Days.layer ? Days.layer.getLayers().filter(l => l instanceof L.Marker).map(l => l.getElement() && l.getElement().textContent) : null")
        check('«Показать на карте»: the nights numbered 🌙1, 🌙2 on the map, the clear chip shown', mk == ['🌙1', '🌙2'] and await pg.evaluate("!document.getElementById('ins-chip').hidden && document.body.dataset.tab !== 'rinfo'"), mk)
        await pg.click('#ins-chip'); await pg.wait_for_timeout(200)
        check('the chip clears it', await pg.evaluate("!Days.layer"))
        await open_info(pg, 'Поход', R150); await pg.click('#in-dkm [data-k="100"]'); await pg.click('#in-days')
        await pg.wait_for_function("document.querySelectorAll('#in-dout .dayc').length > 0", timeout=10000)
        d = await pg.evaluate(OUT)
        check('100 km a day → 2 days (the night nearest the middle, counting how far off)', len(d) == 2 and 'Guest C' in d[0], d)
        # no places to sleep (no connection): equal days, said so
        R2 = route(150, 31.3)
        await pg.evaluate("window.__fail = true"); await open_info(pg, 'Без ночёвок', R2); await pg.click('#in-dkm [data-k="50"]'); await pg.click('#in-days')
        await pg.wait_for_function("document.querySelectorAll('#in-dout .dayc').length > 0", timeout=10000)
        t = await pg.evaluate("document.getElementById('in-dout').innerText")
        check('no places loaded → «дни поровну», «Ночёвка не найдена — конец дня на 50-м км»', 'дни поровну' in t and 'Ночёвка не найдена — конец дня на 50-м км' in t, t[:200])
        await pg.evaluate("window.__fail = false")
        await open_info(pg, 'Один день', route(60, 31.6)); await pg.click('#in-dkm [data-k="70"]'); await pg.click('#in-days'); await pg.wait_for_timeout(800)
        check('60 km at 70 km a day → «Маршрут на один день»', 'Маршрут на один день' in await pg.evaluate("document.getElementById('in-dout').textContent"))
        await open_info(pg, 'Короткий', route(30, 31.8))
        check('a route under 40 km has no «По дням»', not await pg.evaluate("!!document.getElementById('in-days')"))
        check('the km a day are remembered', await pg.evaluate("S.dayKm") == 70)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            await pg.evaluate(FIX, [STAYS, WATER]); await pg.evaluate("setMode('bike', true)")
            await open_info(pg, 'Trip', R150); await pg.click('#in-dkm [data-k="50"]'); await pg.click('#in-days')
            await pg.wait_for_function("document.querySelectorAll('#in-dout .dayc').length > 0", timeout=10000); await pg.wait_for_timeout(400)
            t = await pg.evaluate("(() => { const i = document.getElementById('in-days'); return [...i.closest('#ins').querySelectorAll('h3')].pop().textContent + ' | ' + i.textContent + ' | ' + document.getElementById('in-dout').innerText; })()")
            cyr = [w for w in t.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: «По дням» translated', not cyr and ('יום 1' in t if lang == 'he' else 'Day 1' in t), (t.replace('\n', ' | ')[:240], cyr[:5]))
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
