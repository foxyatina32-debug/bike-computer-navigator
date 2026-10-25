# «⟳ Кольцом» on the map during navigation (v90): a one-way route becomes there-and-back / back another way.
# With a way to the start in front, the way back goes to the route's own start, not to where the rider set off.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = [[32.09 + i * 0.0005, 34.88, 20] for i in range(40)]
APPR = [[32.07 + i * 0.001, 34.86 + i * 0.001, 20] for i in range(20)]   # from home to the route start
BOX = "(k => { const r = document.querySelector(k).getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })"
def over(a, b): return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
async def main():
    url = serve(8807)
    async with async_playwright() as p:
        # Phone on its side: the button sits beside «+ Маршрут», over nothing else.
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), viewport=(844, 390), geo=(32.0901, 34.88))
        await pg.wait_for_timeout(1200)
        await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {json.dumps(ROUTE)}, noAsk: true}})"); await pg.wait_for_timeout(600)
        bx = await pg.evaluate("[...document.querySelectorAll('.top button, #navb, .gpxfab:not([hidden]), #t-compass, #t-sos')].filter(e => e.getClientRects().length && !e.classList.contains('ovh')).map(e => { const r = e.getBoundingClientRect(); return [e.id || e.className, r.left, r.top, r.right, r.bottom]; })")
        me = next(x for x in bx if x[0] == 't-ret')
        hit = [x[0] for x in bx if x[0] != 't-ret' and over(me[1:], x[1:])]
        check('landscape: «⟳ Кольцом» visible, over no other button', await pg.is_visible('#t-ret') and not hit and me[1] >= 0, [me, hit])
        await b.close()
        for lang, vp in (('ru', (430, 932)), ('he', (375, 667))):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), viewport=vp, geo=(32.0901, 34.88))
            await pg.wait_for_timeout(1500)
            check(f'{lang}: no «⟳ Кольцом» without navigation', not await pg.is_visible('#t-ret'))
            await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {json.dumps(ROUTE)}, noAsk: true}})"); await pg.wait_for_timeout(500)
            if lang == 'ru':
                r, g, m = [await pg.evaluate(BOX + f"('{k}')") for k in ('#t-ret', '#t-gpx', '#t-mic')]
                check('ru: «⟳ Кольцом» on the map, under «+ Маршрут», nothing overlaps', await pg.is_visible('#t-ret') and r[1] >= g[3] and not over(r, g) and not over(r, m) and r[2] <= vp[0], [r, g, m])
            else:
                vis = await pg.is_visible('#t-ret'); r = await pg.evaluate(BOX + "('#t-ret')")
                others = [await pg.evaluate(BOX + f"('{k}')") for k in ('#t-gpx', '#t-mic', '#z-in')]
                check('he / small screen: button shown, not over other buttons', vis and r[2] <= vp[0] and r[0] >= 0 and not any(over(r, o) for o in others[:2]), [r, others])
            await pg.click('#t-ret'); await pg.wait_for_timeout(200)
            check(f'{lang}: tap asks how: there and back / another way', await pg.is_visible('#ask-ret') and await pg.is_visible('#rt-back') and await pg.is_visible('#rt-loop'))
            await pg.click('#rt-no'); await pg.wait_for_timeout(200)
            check(f'{lang}: «Отмена» keeps the route one way', not await pg.is_visible('#ask-ret') and not await pg.evaluate("Nav.loopy"))
            t0 = await pg.evaluate("Nav.route.total")
            await pg.click('#t-ret'); await pg.click('#rt-back'); await pg.wait_for_function("Nav.route.name.includes('туда и обратно')", timeout=10000)
            st = await pg.evaluate("({t: Nav.route.total, loopy: Nav.loopy, d0: hav(Nav.route.coords[0], Nav.route.coords[Nav.route.coords.length - 1])})")
            await pg.wait_for_timeout(200)
            check(f'{lang}: «⇄ Туда и обратно»: back to the start, twice as long; button gone', abs(st['t'] - 2 * t0) < 30 and st['loopy'] and st['d0'] < 5 and not await pg.is_visible('#t-ret'), st)
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            if lang == 'he': await b.close(); break
            # Way to the start + route (as when navigation starts away from the route).
            await pg.evaluate(f"(() => {{ const a = {json.dumps(APPR)}; Nav.set({{name: 'Маршрут', coords: a.concat({json.dumps(ROUTE)}), noAsk: true, keepView: true, rr: true, ap: a.length, apTo: 'start'}}); }})()")
            await pg.wait_for_timeout(400)
            st0 = await pg.evaluate("({start: Nav.startLL, ap: Nav.route.ap})")
            check('with the way to the start: «⟳ Кольцом» shown', await pg.is_visible('#t-ret') and st0['ap'] == len(APPR), st0)
            await pg.click('#t-ret'); info = await pg.text_content('#rt-info')
            check('dialog says the route length without the way to the start', '2.17' in info and '5.' not in info, info)
            await pg.click('#rt-loop'); await pg.wait_for_function("Nav.route.name.includes('кольцом')", timeout=15000)
            st1 = await pg.evaluate(f"(() => {{ const c = Nav.route.coords, e = c[c.length - 1]; return {{ap: Nav.route.ap, endToRouteStart: Math.round(hav(e, {json.dumps(ROUTE[0])})), endToHome: Math.round(hav(e, {json.dumps(APPR[0])})), start: Nav.startLL, wayKept: hav(c[0], {json.dumps(APPR[0])}) < 5}}; }})()")
            check('«⟳ Назад другой дорогой»: ends at the route start, not at home; the way to the start kept', st1['ap'] == len(APPR) and st1['endToRouteStart'] < 5 and st1['endToHome'] > 2000 and st1['wayKept'], st1)
            check('start marker unchanged', st1['start'] == st0['start'], [st0['start'], st1['start']])
            check('no JS errors (after the way to the start)', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
