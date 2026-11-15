# Back to the start during navigation: a one-way route becomes there-and-back / back another way (v90).
# v114: no floating «⟳ Кольцом» and «+ Маршрут» on the map while navigating — the map stays clean; the same choice is in
# «Маршруты» → «Активная навигация» (⇄ Туда и обратно / ⟳ Назад другой дорогой). The mic sits under the route banner.
# With a way to the start in front, the way back goes to the route's own start, not to where the rider set off.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = [[32.09 + i * 0.0005, 34.88, 20] for i in range(40)]
BOX = "(k => { const r = document.querySelector(k).getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })"
def over(a, b): return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
async def main():
    url = serve(8807)
    async with async_playwright() as p:
        for lang, vp in (('ru', (430, 932)), ('he', (375, 667)), ('ru', (844, 390))):
            tag = f'{lang} {vp[0]}×{vp[1]}'
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), viewport=vp, geo=(32.0901, 34.88))
            await pg.wait_for_timeout(1500)
            check(f'{tag}: without navigation «+ Маршрут» on the map, no «⟳ Кольцом»', await pg.is_visible('#t-gpx') and not await pg.is_visible('#t-ret'))
            await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {json.dumps(ROUTE)}, noAsk: true}})"); await pg.wait_for_timeout(600)
            nb, mic = [await pg.evaluate(BOX + f"('{k}')") for k in ('#navb', '#t-mic')]
            check(f'{tag}: navigating — neither «+ Маршрут» nor «⟳ Кольцом»; 🎤 under the banner', not await pg.is_visible('#t-gpx') and not await pg.is_visible('#t-ret') and mic[1] >= nb[3] and not over(mic, nb), [nb, mic])
            await pg.evaluate("showTab('routes'); routeSeg('plan')"); await pg.wait_for_timeout(300)
            check(f'{tag}: «Активная навигация» offers both ways back', await pg.is_visible('#nav-back') and await pg.is_visible('#nav-ret'))
            t0 = await pg.evaluate("Nav.route.total")
            await pg.click('#nav-back'); await pg.wait_for_function("Nav.route.name.includes('туда и обратно')", timeout=10000)
            st = await pg.evaluate("({t: Nav.route.total, loopy: Nav.loopy, d0: hav(Nav.route.coords[0], Nav.route.coords[Nav.route.coords.length - 1])})")
            check(f'{tag}: «⇄ Туда и обратно»: back to the start, twice as long', abs(st['t'] - 2 * t0) < 30 and st['loopy'] and st['d0'] < 5, st)
            await pg.evaluate("Nav.stop(); showTab('rec')"); await pg.wait_for_timeout(500)
            check(f'{tag}: navigation over — «+ Маршрут» back', await pg.is_visible('#t-gpx'))
            check(f'{tag}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
