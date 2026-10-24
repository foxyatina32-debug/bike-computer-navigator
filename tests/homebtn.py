# 🏠 button on the map: one tap → route home from wherever you are. No home yet → the panel says how to set it.
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
BOX = "(id => { const r = document.getElementById(id).getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })"
async def main():
    url = serve(8777)
    async with async_playwright() as p:
        for vp in [(375, 667), (393, 852)]:
            m = Mocks()
            b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, viewport=vp, geo=(32.09, 34.88))
            await pg.wait_for_timeout(1500)
            h, mic = await pg.evaluate(BOX + "('t-home')"), await pg.evaluate(BOX + "('t-mic')")
            zin = await pg.evaluate(BOX + "('z-in')")
            check(f'{vp}: 🏠 button is on the map, under 🎤, above the zoom buttons', await pg.is_visible('#t-home') and h[1] >= mic[3] and zin[1] >= h[3], {'home': h, 'mic': mic, 'zin': zin})
            if vp[0] != 375:
                await b.close(); continue
            # No home yet.
            await pg.click('#t-home'); await pg.wait_for_timeout(500)
            st = await pg.evaluate("({open: !document.getElementById('vc').hidden, st: document.getElementById('vc-st').textContent, route: !!Nav.route})")
            check('no home yet: the panel opens and says how to set it, no route', st['open'] and 'не задан' in st['st'] and not st['route'], st)
            await pg.click('#vc-x')
            # Home set → one tap → navigation home.
            await pg.evaluate("lsSet('home', {ll: [32.0853, 34.7818], name: 'Тель-Авив'})")
            await pg.click('#t-home')
            await pg.wait_for_function("Nav.route && Nav.route.name === 'Домой'", timeout=12000)
            r = await pg.evaluate("(() => { const c = Nav.route.coords; return {start: c[0], end: c[c.length - 1], follow: GPS.follow}; })()")
            check('one tap: route from where you are to home, navigation on', abs(r['end'][0] - 32.0853) < 1e-4 and abs(r['start'][0] - 32.09) < 1e-3 and r['follow'], r)
            check('no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
