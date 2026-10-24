# Start (green ▶) and finish (checkered flag) markers on every route; the start stays where the planned route begins.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = [[32.10 + i * 0.001, 34.88, 20] for i in range(30)]
ENDS = "(() => { const s = Nav.flagMk && Nav.flagMk.getLatLng(), f = Nav.finMk && Nav.finMk.getLatLng(); return {s: s && [s.lat, s.lng], f: f && [f.lat, f.lng], sIcon: !!document.querySelector('.rte-st'), fIcon: !!document.querySelector('.rte-fin')}; })()"
def near(a, b): return a and abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6
async def main():
    url = serve(8778)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.115, 34.89))
        await pg.wait_for_timeout(1500)
        await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {json.dumps(ROUTE)}}})"); await pg.wait_for_timeout(300)
        e = await pg.evaluate(ENDS)
        check('a route gets a start marker at its start and a finish flag at its end', e['sIcon'] and e['fIcon'] and near(e['s'], ROUTE[0][:2]) and near(e['f'], ROUTE[-1][:2]), e)
        # Way to the start: the start marker stays at the route's start, not where the rider is.
        await ctx.set_geolocation({'latitude': 32.115, 'longitude': 34.8901, 'accuracy': 5}); await pg.wait_for_timeout(1500)
        await pg.click('#aj-start'); await pg.wait_for_function("Nav.route && Nav.route.rr", timeout=15000)
        e = await pg.evaluate(ENDS)
        check('with the way to the start: start marker at the route start, flag at the finish', near(e['s'], ROUTE[0][:2]) and near(e['f'], ROUTE[-1][:2]), e)
        # Reload in the middle: markers come back in the same places.
        await pg.reload(); await pg.wait_for_timeout(2500)
        await pg.evaluate("(() => { const b = document.getElementById('rs-cont'); if (b && !document.getElementById('ask-resume').hidden) b.click(); })()"); await pg.wait_for_timeout(800)
        e = await pg.evaluate(ENDS)
        check('after a reload: same start and finish', near(e['s'], ROUTE[0][:2]) and near(e['f'], ROUTE[-1][:2]), e)
        # Stop navigation: markers removed.
        await pg.evaluate("Nav.stop()"); await pg.wait_for_timeout(200)
        e = await pg.evaluate(ENDS)
        check('navigation stopped: no start / finish markers left', not e['s'] and not e['f'] and not e['sIcon'] and not e['fIcon'], e)
        # Reversed route: start and finish swap.
        await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {json.dumps(ROUTE)}, noAsk: true}}); Nav.reverse()"); await pg.wait_for_timeout(300)
        e = await pg.evaluate(ENDS)
        check('reversed: start at the old finish, flag at the old start', near(e['s'], ROUTE[-1][:2]) and near(e['f'], ROUTE[0][:2]), e)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
