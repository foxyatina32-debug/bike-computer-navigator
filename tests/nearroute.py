# Starting a route while standing near (but not on) its road somewhere in the middle: a dialog always asks how to start —
# from the nearest point or via the route's start — at any distance, not only when far away or right on the line.
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = [[32.10 + i * 0.001, 34.88, 20] for i in range(30)]          # north from 32.10, ~3.2 km
KX = 111320 * math.cos(32.115 * math.pi / 180)
ST = "({start: !document.getElementById('ask-start').hidden, join: !document.getElementById('ask-join').hidden})"
async def main():
    url = serve(8811)
    async with async_playwright() as p:
        for off in (20, 50, 65, 75, 120):
            lon = 34.88 + off / KX
            b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.115, lon))
            await pg.wait_for_timeout(1500)
            await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {json.dumps(ROUTE)}}})"); await pg.wait_for_timeout(300)
            await ctx.set_geolocation({'latitude': 32.115, 'longitude': lon + 1e-7, 'accuracy': 5}); await pg.wait_for_timeout(1500)
            st = await pg.evaluate(ST)
            check(f'{off} m from the middle of the route: a start dialog is shown', st['start'] or st['join'], st)
            if off in (65, 75):
                r = await pg.evaluate("({open: !document.getElementById('ask-join').hidden, near: document.getElementById('aj-near').innerText, start: !document.getElementById('aj-start').hidden})")
                check(f'{off} m: both «к ближайшей точке» and «до старта» offered', r['open'] and 'ближайшей' in r['near'] and r['start'], r)
                await pg.click('#aj-near'); await pg.wait_for_function("Nav.route && Nav.route.rr && Nav.route.apTo === 'near'", timeout=15000)
                t = await pg.evaluate("({total: Nav.route.total, last: Nav.route.coords[Nav.route.coords.length - 1]})")
                check(f'{off} m: «к ближайшей точке» → short way onto the road, then on to the finish', t['total'] < 2500 and abs(t['last'][0] - ROUTE[-1][0]) < 1e-6, t)
            check(f'{off} m: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
