# Street names at turns: «Поверните направо на улицу X» + «с улицы Y»; unnamed ways say «без названия».
# Run: python3 tests/streets.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
A, C, B = (32.09, 34.88), (32.096, 34.88), (32.096, 34.888)   # north to the corner, then right (east)
ROUTE = [[A[0] + (C[0] - A[0]) * t / 30, A[1], None] for t in range(31)] + [[C[0], C[1] + (B[1] - C[1]) * t / 30, None] for t in range(1, 31)]
def way(i, tags, a, b): return {'type': 'way', 'id': i, 'tags': tags, 'geometry': [{'lat': a[0] - (b[0] - a[0]) * .1, 'lon': a[1] - (b[1] - a[1]) * .1}, {'lat': b[0] + (b[0] - a[0]) * .1, 'lon': b[1] + (b[1] - a[1]) * .1}]}

async def run(p, url, ways, lang='ru'):
    m = Mocks(); m.overpass = lambda u: {'elements': ways}
    b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
    await pg.evaluate(f"Nav.set({{name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true}})")
    await pg.wait_for_function("Nav.route.cues[0].streets === true", timeout=10000)
    q = await pg.evaluate("({ txt: Nav.route.cues[0].txt, sp: Nav.route.cues[0].spoken, from: Nav.route.cues[0].from || '' })")
    lat = A[0]
    for _ in range(6): lat += 0.0001; await ctx.set_geolocation({'latitude': lat, 'longitude': A[1], 'accuracy': 5}); await pg.wait_for_timeout(1000)
    banner = await pg.evaluate("document.getElementById('nv-txt').innerText")
    return b, pg, log, q, banner

async def main():
    url = serve(8789)
    async with async_playwright() as p:
        b, pg, log, q, banner = await run(p, url, [way(1, {'highway': 'residential', 'name': 'ביאליק', 'name:ru': 'Бялик'}, A, C), way(2, {'highway': 'residential', 'name': "ז'בוטינסקי", 'name:ru': 'Жаботинского'}, C, B)])
        check('named: turn onto street, from street', q['txt'] == 'Поверните направо на улицу Жаботинского' and q['from'] == 'с улицы Бялик', q)
        check('named: voice says the street', q['sp'] == 'поверните направо на улицу Жаботинского', q['sp'])
        check('banner shows both lines', 'на улицу Жаботинского' in banner and 'с улицы Бялик' in banner, banner)
        await pg.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'streets.png'))
        check('no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        b, pg, log, q, banner = await run(p, url, [way(1, {'highway': 'residential'}, A, C), way(2, {'highway': 'track'}, C, B)])
        check('unnamed: «на грунтовку без названия», «с улицы без названия»', q['txt'] == 'Поверните направо на грунтовку без названия' and q['from'] == 'с улицы без названия' and q['sp'].endswith('на грунтовку без названия'), q)
        await b.close()

        b, pg, log, q, banner = await run(p, url, [way(1, {'highway': 'path', 'name': 'שביל ישראל'}, A, C), way(2, {'highway': 'tertiary', 'name': 'הרצל'}, C, B)])
        check('Hebrew-only name: shown, not spoken by the Russian voice', q['txt'] == 'Поверните направо на улицу הרצל' and q['from'] == 'с тропы שביל ישראל' and q['sp'] == 'поверните направо', q)
        await b.close()

        b, pg, log, q, banner = await run(p, url, [])
        check('no OSM data: plain prompt', q['txt'] == 'Поверните направо' and not q['from'], q)
        await b.close()

        b, pg, log, q, banner = await run(p, url, [way(1, {'highway': 'residential', 'name': 'ביאליק'}, A, C), way(2, {'highway': 'residential', 'name': 'הרצל'}, C, B)], lang='he')
        check('Hebrew UI: Hebrew names spoken', 'הרצל' in q['sp'], q)
        check('no JS errors (he)', not log['errors'], log['errors'][:3]); await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
