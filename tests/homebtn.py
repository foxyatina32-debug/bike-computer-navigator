# «🏠 Поехали домой» on the Routes tab: one tap → route home from wherever you are. No home yet → the panel says how to set it.
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
async def main():
    url = serve(8777)
    async with async_playwright() as p:
        for lang, word in [('ru', 'Поехали домой'), ('en', 'Go home'), ('he', 'סע הביתה')]:
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), viewport=(375, 667), geo=(32.09, 34.88))
            await pg.wait_for_timeout(1500)
            await pg.click('.tabs [data-tab="routes"]'); await pg.wait_for_timeout(400)
            for sub in ('mine', 'plan', 'trails'):
                await pg.click(f'#rseg [data-r="{sub}"]'); await pg.wait_for_timeout(200)
                check(f'{lang}/{sub}: button on the Routes tab', await pg.is_visible('#rt-home') and word in await pg.inner_text('#rt-home'))
            check(f'{lang}: no map button any more', await pg.evaluate("!document.getElementById('t-home')"))
            if lang != 'ru':
                await b.close(); continue
            check('no home yet: the hint under the button says so', 'не задан' in await pg.inner_text('#rt-home-s'))
            await pg.click('#rt-home'); await pg.wait_for_timeout(500)
            st = await pg.evaluate("({open: !document.getElementById('vc').hidden, st: document.getElementById('vc-st').textContent, route: !!Nav.route, map: document.getElementById('sheet-routes').hidden})")
            check('no home yet: map + panel that says how to set it, no route', st['open'] and st['map'] and 'не задан' in st['st'] and not st['route'], st)
            await pg.click('#vc-x')
            await pg.evaluate("lsSet('home', {ll: [32.0853, 34.7818], name: 'Тель-Авив'})")
            await pg.click('.tabs [data-tab="routes"]'); await pg.wait_for_timeout(400)
            check('saved home shown under the button', 'Тель-Авив' in await pg.inner_text('#rt-home-s'))
            await pg.click('#rt-home')
            await pg.wait_for_function("Nav.route && Nav.route.name === 'Домой'", timeout=12000)
            r = await pg.evaluate("(() => { const c = Nav.route.coords; return {start: c[0], end: c[c.length - 1], follow: GPS.follow, map: document.getElementById('sheet-routes').hidden}; })()")
            check('one tap: route from where you are to home, navigation on the map', abs(r['end'][0] - 32.0853) < 1e-4 and abs(r['start'][0] - 32.09) < 1e-3 and r['follow'] and r['map'], r)
            check('no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
