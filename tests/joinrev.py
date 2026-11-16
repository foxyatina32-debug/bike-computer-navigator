# v120: the «Вы не на маршруте» window and riding a route the other way.
# - «Проложить путь до старта на велосипеде» (the mode in the label), «Продолжить навигацию — доберусь сам» keeps navigating;
# - far from the route: «До старта в Google Maps (на велосипеде)» opens Google Maps (bicycle) to the start, navigation stays on;
# - the finish nearer than the start: «⇆ Ехать в обратную сторону» — the route from its finish; then the window asks about the new start;
# - «⇆ Обратно» in «⋯» of a saved route; routes saved in one go keep their order. Hebrew / English translated.
# Run: python3 tests/joinrev.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
# A one-way route going north: start 32.10, finish ~32.13 (≈3.3 km). The rider stands 4 km south / 1 km north of it.
ROUTE = [[32.10 + i * 0.0005, 34.88, 20] for i in range(67)]
OPEN = "window.__opened = []; window.open = (u) => { window.__opened.push(u); return null; }; document.addEventListener('click', e => { const a = e.target.closest && e.target.closest('a[target=_blank]'); if (a) { e.preventDefault(); window.__opened.push(a.href); } }, true);"

async def ask(pg, geo):
    await pg.evaluate("Nav.stop(); showTab('rec')")
    await pg.context.set_geolocation({'latitude': geo[0], 'longitude': geo[1], 'accuracy': 5})
    await pg.wait_for_function(f"GPS.fix && Math.abs(GPS.fix.lat - {geo[0]}) < 1e-4", timeout=10000)
    await pg.evaluate(f"Nav.set({{ name: 'Тест', coords: {json.dumps(ROUTE)}, rid: 'r1' }})")
    await pg.wait_for_function("!document.getElementById('ask-join').hidden", timeout=10000)
    return await pg.evaluate("""(() => { const v = id => !document.getElementById(id).hidden; return { start: v('aj-start') && document.getElementById('aj-start-t').textContent,
        rev: v('aj-rev'), gm: v('aj-gm') && document.getElementById('aj-gm-t').textContent, no: document.querySelector('#aj-no b').textContent, info: document.getElementById('aj-info').textContent }; })()""")

async def main():
    url = serve(8911); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(32.064, 34.88))
        await pg.evaluate(OPEN)
        # 1. 4 km south of the start: labels, Google Maps offered, no «reverse» (the start is nearer)
        a = await ask(pg, (32.064, 34.88))
        nt = await pg.evaluate("document.getElementById('aj-near-t').textContent")
        check('far before the start: «Проложить путь до старта на велосипеде», «Продолжить навигацию — доберусь сам»', nt == 'Проложить путь до старта на велосипеде' and a['no'] == 'Продолжить навигацию — доберусь сам', (nt, a))
        check('far: «До старта в Google Maps (на велосипеде)» offered; no «reverse» while the start is nearer', a['gm'] == 'До старта в Google Maps (на велосипеде)' and not a['rev'], a)
        await pg.click('#aj-gm'); await pg.wait_for_timeout(500)
        u = await pg.evaluate("window.__opened.pop() || ''")
        check('«До старта в Google Maps» → Google Maps, bicycle, to the route start; navigation stays on', 'google.com/maps/dir' in u and 'travelmode=bicycling' in u and 'destination=32.100000%2C34.880000' in u.replace(',', '%2C')
              and await pg.evaluate("!!Nav.route && Nav.declined && document.getElementById('ask-join').hidden"), u)
        # 2. «Продолжить навигацию — доберусь сам»: navigation continues with the arrow
        await ask(pg, (32.064, 34.88)); await pg.click('#aj-no'); await pg.wait_for_timeout(400)
        check('«Продолжить навигацию» keeps the route and navigation on', await pg.evaluate("!!Nav.route && Nav.route.name === 'Тест' && Nav.declined"))
        check('no JS errors (before the start)', not log['errors'], log['errors'][:3])
        await b.close()
        # 3. 1 km past the finish (a new start of the app there: a GPS jump of 8 km is rightly ignored as an outlier)
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(32.142, 34.88))
        await pg.evaluate(OPEN)
        a = await ask(pg, (32.142, 34.88))
        check('the finish is nearer: «⇆ Ехать в обратную сторону» offered, with both distances', a['rev'] and 'Финиш ближе' in await pg.evaluate("document.getElementById('aj-rev-s').textContent"), await pg.evaluate("document.getElementById('aj-rev-s').textContent"))
        await pg.click('#aj-rev'); await pg.wait_for_timeout(800)
        st = await pg.evaluate("({ name: Nav.route.name, first: Nav.route.coords[0][0], last: Nav.route.coords[Nav.route.coords.length - 1][0], ask: !document.getElementById('ask-join').hidden, rev: !document.getElementById('aj-rev').hidden })")
        check('«⇆ Ехать в обратную сторону» → the route from its finish to its start', st['name'] == 'Тест (обратно)' and st['first'] > 32.13 and abs(st['last'] - 32.10) < 1e-6, st)
        check('…then asked how to reach the new start (no second «reverse»)', st['ask'] and not st['rev'], st)
        await pg.click('#aj-no'); await pg.wait_for_timeout(200)
        # 4. a loop route: never «reverse»
        loop = ROUTE + [[32.10 + i * 0.0005, 34.881, 20] for i in range(66, -1, -1)]
        await pg.evaluate("Nav.stop()"); await pg.wait_for_timeout(300)
        await pg.evaluate(f"Nav.set({{ name: 'Кольцо', coords: {json.dumps(loop)} }})")
        await pg.wait_for_function("!document.getElementById('ask-join').hidden", timeout=10000)
        check('a loop: no «reverse» in the window', await pg.evaluate("document.getElementById('aj-rev').hidden"))
        await pg.click('#aj-no'); await pg.evaluate("Nav.stop()")
        # 5. near the route (300 m): no Google Maps button
        await b.close(); b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(32.11, 34.8835))
        await pg.context.set_geolocation({'latitude': 32.11, 'longitude': 34.8835, 'accuracy': 5})
        await pg.wait_for_function("GPS.fix && Math.abs(GPS.fix.lat - 32.11) < 1e-4", timeout=10000)
        await pg.evaluate(f"Nav.set({{ name: 'Тест', coords: {json.dumps(ROUTE)} }})"); await pg.wait_for_timeout(1500)
        near_gm = await pg.evaluate("!document.getElementById('ask-join').hidden && !document.getElementById('aj-gm').hidden")
        check('close to the route: no Google Maps button', not near_gm)
        await pg.evaluate("document.getElementById('ask-join').hidden || Nav.joinChoice('no'); Nav.stop()")
        # 6. «⇆ Обратно» in «⋯» of a saved route
        await pg.evaluate(f"DB.put('routes', {{ id: 'r1', name: 'Мой маршрут', coords: {json.dumps(ROUTE)}, dist: 3300, created: Date.now(), source: 'GPX', wpts: [{{ ll: [32.105, 34.88], name: 'A' }}, {{ ll: [32.12, 34.88], name: 'B' }}] }})")
        await pg.evaluate("showTab('routes'); routeSeg('mine')"); await pg.wait_for_timeout(400)
        await pg.click('#rt-list [data-more]'); await pg.wait_for_timeout(200)
        vis = await pg.evaluate("[...document.querySelectorAll('#rt-list .a2 button')].map(b => b.textContent.trim())")
        check('«⋯» of a route has «⇆ Обратно» first', vis[0] == '⇆ Обратно', vis)
        await pg.click('#rt-list [data-rev]'); await pg.wait_for_timeout(500)
        st = await pg.evaluate("({ name: Nav.route.name, first: Nav.route.coords[0][0], w: Nav.wpts.map(w => w.name), tab: $('#sheet-routes').hidden })")
        check('«⇆ Обратно» → navigation from the finish, points of interest in reverse order, on the map', st['name'] == 'Мой маршрут (обратно)' and st['first'] > 32.13 and st['w'] == ['B', 'A'] and st['tab'], st)
        await pg.evaluate("Nav.stop()")
        # 7. routes saved in one go keep their order
        order = await pg.evaluate(f"(async () => {{ const c = {json.dumps(ROUTE[:5])}; const a = await saveRoute('Первый', c, 't'), b = await saveRoute('Второй', c, 't'), d = await saveRoute('Третий', c, 't'); return [a.created < b.created, b.created < d.created]; }})()")
        check('routes saved in the same moment keep their order', order == [True, True], order)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, geo=(32.142, 34.88))
            a = await ask(pg, (32.142, 34.88))
            txt = await pg.evaluate("document.querySelector('#ask-join .box').innerText")
            ru = [w for w in txt.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: the window translated («reverse» offered)', not ru and a['rev'], ru[:6])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
