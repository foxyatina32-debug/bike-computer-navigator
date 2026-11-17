# v125: changing the transport (bike / on foot / car) offers to rebuild the route for it.
# Navigating: a dialog «Перестроить маршрут 🚶 пешком?» → rebuilt from the rider to the finish for the new transport,
# through key points of the part ahead (a loop stays a loop); «Оставить» keeps it; no dialog when the route is already for
# that transport; also when the activity is changed in Settings. The planner's result is rebuilt by itself. ru / he / en.
# Run: python3 tests/remode.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.10 + i * 0.0005, 34.88, 20] for i in range(40)]                                   # 2.2 km north
LOOP = ROUTE + [[32.10 + i * 0.0005, 34.884, 20] for i in range(39, -1, -1)]                    # up and back 380 m east
SPY = "(() => { const o = window.routeVia; window.__rv = []; window.routeVia = function (pts, opts, x) { window.__rv.push({ n: pts.length, mode: opts && opts.mode }); return o.apply(this, arguments); }; })()"
ASK = "!document.getElementById('ask-remode').hidden"

async def main():
    url = serve(8991); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(32.1001, 34.88))
        await pg.evaluate(SPY); await pg.evaluate("setMode('bike', true)")
        # 1. a bike route being navigated → switch to «on foot»
        await pg.evaluate(f"Nav.set({{ name: 'Тест', coords: {json.dumps(ROUTE)}, opts: {{ mode: 'bike', bike: RO.bike }}, noAsk: true }})"); await pg.wait_for_timeout(300)
        await pg.evaluate("setMode('foot')"); await pg.wait_for_timeout(300)
        t = await pg.evaluate("[document.getElementById('rm-t').textContent, document.getElementById('rm-info').textContent]")
        check('switching to «on foot» while navigating: «Перестроить маршрут 🚶 пешком?»', await pg.evaluate(ASK) and 'пешком' in t[0] and 'велосипеде' in t[1], t)
        await pg.click('#rm-yes'); await pg.wait_for_function("Nav.route && Nav.route.opts && Nav.route.opts.mode === 'foot'", timeout=10000)
        st = await pg.evaluate("({ name: Nav.route.name, rv: window.__rv.slice(-1)[0], d0: hav([GPS.fix.lat, GPS.fix.lon], Nav.route.coords[0]), end: Nav.route.coords[Nav.route.coords.length - 1] })")
        check('«Перестроить» → a route for walking from the rider to the same finish, named «… · пешком»', st['rv']['mode'] == 'foot' and st['name'] == 'Тест · пешком' and st['d0'] < 30 and abs(st['end'][0] - ROUTE[-1][0]) < 1e-4, st)
        # 2. «Оставить»
        await pg.evaluate("setMode('car')"); await pg.wait_for_timeout(300)
        n0 = await pg.evaluate("window.__rv.length")
        await pg.click('#rm-no'); await pg.wait_for_timeout(300)
        check('«Оставить этот маршрут» keeps it (no new route requested)', await pg.evaluate("Nav.route.opts.mode === 'foot' && document.getElementById('ask-remode').hidden") and await pg.evaluate("window.__rv.length") == n0)
        # 3. the route already for this transport → no dialog
        await pg.evaluate("setMode('bike', true); document.getElementById('ask-remode').hidden = true")
        await pg.evaluate(f"Nav.set({{ name: 'Пеший', coords: {json.dumps(ROUTE)}, opts: {{ mode: 'foot' }}, noAsk: true }})")
        await pg.evaluate("document.getElementById('ask-remode').hidden = true; setMode('foot')"); await pg.wait_for_timeout(300)
        check('the route is already for walking → switching to walking asks nothing', not await pg.evaluate(ASK))
        # 4. a loop keeps its shape: rebuilt through key points of the part ahead
        await pg.evaluate("setMode('bike', true); document.getElementById('ask-remode').hidden = true")
        await pg.evaluate(f"Nav.set({{ name: 'Кольцо', coords: {json.dumps(LOOP)}, opts: {{ mode: 'bike' }}, noAsk: true }})"); await pg.wait_for_timeout(300)
        await pg.evaluate("setMode('car')"); await pg.click('#rm-yes')
        await pg.wait_for_function("Nav.route.opts.mode === 'car'", timeout=10000)
        rv = await pg.evaluate("window.__rv.slice(-1)[0]")
        far = await pg.evaluate("Math.max(...Nav.route.coords.map(c => (c[1] - 34.88) * 111320 * Math.cos(32.1 * Math.PI / 180)))")
        check('a loop rebuilt for the car goes through key points of the part ahead (still reaches the far side)', rv['n'] > 2 and rv['mode'] == 'car' and far > 250, (rv, round(far)))
        # 5. changed in Settings → «Поездка» (activity) → same offer
        await pg.evaluate("document.getElementById('ask-remode').hidden = true; showTab('profile'); document.querySelector('details.grp[data-g=ride]').open = true")
        await pg.click('#s-act [data-a="walk"]'); await pg.wait_for_timeout(300)
        check('the activity changed in Settings («Ходьба») → the same offer', await pg.evaluate(ASK) and 'пешком' in await pg.evaluate("document.getElementById('rm-t').textContent"))
        await pg.click('#rm-no'); await pg.evaluate("Nav.stop(); showTab('rec')")
        # 6. the planner's result is rebuilt by itself
        await pg.evaluate("setMode('bike', true); showTab('routes'); routeSeg('plan'); document.getElementById('pl-fromgps').checked = true; Plan.wps = []; addWp([32.11, 34.88], 'Финиш')")
        await pg.click('#pl-go'); await pg.wait_for_function("!!Plan.cand", timeout=10000)
        await pg.click('#pl-mode [data-m="foot"]')
        await pg.wait_for_function("Plan.cand && Plan.cand.opts.mode === 'foot'", timeout=10000)
        check('the planner: the result is rebuilt for walking by itself', True)
        check('no dialog without navigation', not await pg.evaluate(ASK))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, geo=(32.1001, 34.88))
            await pg.evaluate("setMode('bike', true)")
            await pg.evaluate(f"Nav.set({{ name: 'X', coords: {json.dumps(ROUTE)}, opts: {{ mode: 'bike' }}, noAsk: true }})"); await pg.wait_for_timeout(200)
            await pg.evaluate("setMode('car')"); await pg.wait_for_timeout(300)
            txt = await pg.evaluate("document.querySelector('#ask-remode .box').innerText")
            ru = [w for w in txt.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: the dialog translated', await pg.evaluate(ASK) and not ru, (txt.replace('\n', ' | ')[:140], ru[:5]))
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
