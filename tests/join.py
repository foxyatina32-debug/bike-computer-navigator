# Away from a route: «Проложить путь до старта» is the main button and leads to the route's START, then the whole route.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
# Route going north from 32.10; the rider stands at 32.115 east of its middle (nearest point is 1.5 km from the start).
ROUTE = [[32.10 + i * 0.001, 34.88, 20] for i in range(30)]
async def main():
    url = serve(8769)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.115, 34.89))
        await pg.wait_for_timeout(1500)
        await pg.evaluate(f"Nav.set({{name: 'Кольцо', coords: {json.dumps(ROUTE)}}})"); await pg.wait_for_timeout(300)
        await ctx.set_geolocation({'latitude': 32.115, 'longitude': 34.8901, 'accuracy': 5}); await pg.wait_for_timeout(1500)
        st = await pg.evaluate("({open: !document.getElementById('ask-join').hidden, first: document.querySelector('#ask-join .btn').id, pri: document.getElementById('aj-start').classList.contains('pri'), nearPri: document.getElementById('aj-near').classList.contains('pri'), near: document.getElementById('aj-near').innerText})")
        check('dialog: «до старта» first and main, «ближайшая точка» says the beginning is skipped', st['open'] and st['first'] == 'aj-start' and st['pri'] and not st['nearPri'] and 'пропущено' in st['near'], st)
        await pg.click('#aj-start'); await pg.wait_for_function("Nav.route && Nav.route.rr && Nav.startAt > 0", timeout=15000)
        r = await pg.evaluate("(() => { const c = Nav.route.coords, s = [32.10, 34.88]; let k = c.findIndex(p => hav(p, s) < 5); return {k, n: c.length, startAt: Nav.startAt, first: c[0], total: Nav.route.total}; })()")
        check('route leads to the start of the route first, then the whole route', r['k'] > 0 and r['n'] - r['k'] >= 30 and r['startAt'] > 0, r)
        # Stray on the way to the start (default «к финишу» is on): the way is rebuilt to the START, the whole route stays.
        await pg.evaluate("Nav.lastReroute = 0; Nav.ignoreOffUntil = 0; window.__set0 = Nav.setAt")
        for k in range(6):
            await ctx.set_geolocation({'latitude': 32.118 + k * 0.0001, 'longitude': 34.896, 'accuracy': 5}); await pg.wait_for_timeout(1200)
        await pg.wait_for_function("Nav.setAt !== window.__set0 && !Nav.rejoining", timeout=15000)
        r = await pg.evaluate("(() => { const c = Nav.route.coords, s = [32.10, 34.88]; let k = c.findIndex(p => hav(p, s) < 5); return {k, n: c.length, ap: Nav.route.ap, approaching: Nav.approaching(), first: c[0], last: c[c.length - 1]}; })()")
        check('strayed on the way: rebuilt to the start, then the whole route (not straight to the finish)', r['k'] > 0 and r['n'] - r['k'] >= 30 and r['approaching'], r)
        an = await pg.evaluate("JSON.parse(localStorage.getItem('velo:activeNav') || 'null')")
        check('the way-to-route mark survives a reload', an is not None and (an.get('ap', 0) > 0 and an.get('apTo') == 'start'), {k: an.get(k) for k in ('ap', 'apTo')} if an else None)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
