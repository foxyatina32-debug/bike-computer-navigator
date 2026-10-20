# Route colour and rider icon (Profile). Run: python3 tests/look.py
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''))
async def main():
    url = serve(8782); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate("Nav.set({ name: 'T', coords: [[32.09, 34.88], [32.1, 34.89]], noAsk: true })")
        check('default route colour is pink', (await pg.evaluate("Nav.line.options.color")).lower() == '#ff5fae')
        await pg.click('.tabs button[data-tab=profile]'); await pg.wait_for_timeout(300)
        n = await pg.evaluate("document.querySelectorAll('#s-rcol [data-c]').length")
        await pg.click('#s-rcol [data-c="#34c759"]'); await pg.wait_for_timeout(200)
        check(f'pick green from {n} colours → route on the map turns green, saved', await pg.evaluate("Nav.line.options.color === '#34c759' && S.routeColor === '#34c759' && lsGet('settings', {}) !== null"), await pg.evaluate("Nav.line.options.color"))
        await pg.evaluate("const i = document.getElementById('s-rcol-pick'); i.value = '#123abc'; i.dispatchEvent(new Event('input')); i.dispatchEvent(new Event('change'))"); await pg.wait_for_timeout(200)
        check('custom colour (colour picker) → applied', await pg.evaluate("Nav.line.options.color === '#123abc' && document.querySelector('#s-rcol label.chip').classList.contains('on')"))
        icons = await pg.evaluate("document.querySelectorAll('#s-meicon [data-mi]').length")
        await pg.click('#s-meicon [data-mi="car"]'); await pg.wait_for_timeout(400)
        html = await pg.evaluate("meMarker.getElement().innerHTML")
        check(f'pick 🚗 from {icons} icons → marker shows the car', '🚗' in html and 'me-badge' in html, html[:80])
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(1500)
        st = await pg.evaluate("[getComputedStyle(document.documentElement).getPropertyValue('--route').trim(), meMarker && meMarker.getElement().innerHTML.includes('🚗')]")
        check('after a reload: colour and icon kept', st[0].lower() == '#123abc' and st[1], st)
        await pg.evaluate("S.meIcon = 'arrow'; saveS(); renderLookSettings(); lastIconHdg = 'x'; meMarker.setIcon(meIcon(markerState()))")
        check('back to the arrow', 'me-badge' not in await pg.evaluate("meMarker.getElement().innerHTML"))
        check('no JS errors', not log['errors'], log['errors'])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
