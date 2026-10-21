# Wide screen (computer, iPad, phone in landscape): map left, all instruments in a column right; portrait unchanged; keys.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = [[32.09 + i * 0.0008, 34.88 + (i % 9) * 0.0005, 20 + i] for i in range(40)]
GEO = """(() => { const r = e => document.querySelector(e).getBoundingClientRect(); const m = r('#map'), h = r('#hud'), t = r('.tabs');
  const pages = [...document.querySelectorAll('#pager .page')].filter(p => !p.hidden).map(p => p.getBoundingClientRect());
  const over = [...document.querySelectorAll('.top button, #navb, .gpxfab:not([hidden])')].filter(e => e.offsetParent).some(e => e.getBoundingClientRect().right > m.right + 1);
  return {wide: document.body.classList.contains('wide'), mapR: m.right, hudL: h.left, tabsL: t.left, stacked: pages.length > 1 && pages[1].top > pages[0].top + 10, over, hidden: [...document.querySelectorAll('.ovh')].map(e => e.id)}; })()"""
async def main():
    url = serve(8765)
    async with async_playwright() as p:
        for name, vp, lang in (('computer', (1440, 900), 'ru'), ('iPad landscape', (1180, 820), 'he'), ('phone landscape', (844, 390), 'en'), ('phone portrait', (390, 844), 'ru'), ('iPad portrait', (820, 1180), 'ru')):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), viewport=vp)
            await pg.evaluate(f"Nav.set({{name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true}}); setCompact(true)"); await pg.wait_for_timeout(800)
            g = await pg.evaluate(GEO)
            if vp[0] > vp[1]:
                check(f'[{name}] map left, instruments right (not over the map), pages stacked, compact ignored', g['wide'] and g['mapR'] <= g['hudL'] and g['tabsL'] >= g['mapR'] and g['stacked'] and not g['over'], g)
                check(f'[{name}] map buttons not hidden (on a low screen only «моё место» may not fit; «За мной» does the same)', not [x for x in g['hidden'] if not (vp[1] < 500 and x == 'z-me')], g['hidden'])
            else:
                check(f'[{name}] portrait: layout as before', not g['wide'], g)
            if name == 'computer':
                await pg.evaluate("Nav.stop()")
                z = await pg.evaluate("map.getZoom()"); await pg.keyboard.press('+'); await pg.wait_for_timeout(400)
                z1 = await pg.evaluate("map.getZoom()"); await pg.keyboard.press('-'); await pg.wait_for_timeout(400)
                check('keys + / − zoom', z1 == z + 1 and await pg.evaluate("map.getZoom()") == z, (z, z1))
                await pg.keyboard.press('Space'); await pg.wait_for_timeout(300)
                st = await pg.evaluate("Ride.status"); await pg.keyboard.press('Space'); await pg.wait_for_timeout(300)
                check('Space: start / pause', st == 'rec' and await pg.evaluate("Ride.status") == 'paused', st)
                await pg.evaluate("showTab('routes')"); await pg.wait_for_timeout(200)
                v = await pg.evaluate("(() => { const s = document.getElementById('sheet-routes').getBoundingClientRect(), h = document.getElementById('hud'); return {hud: !h.hidden && h.getBoundingClientRect().width > 100 && getComputedStyle(h).display !== 'none', apart: s.right <= h.getBoundingClientRect().left}; })()")
                check('panel open → instruments stay visible beside it', v['hud'] and v['apart'], v)
                await pg.keyboard.press('Escape'); await pg.wait_for_timeout(200)
                check('Esc closes a panel', await pg.evaluate("document.getElementById('sheet-routes').hidden"))
                await pg.evaluate("showTab('routes'); routeSeg('plan')"); await pg.click('#geo-q'); await pg.keyboard.type('a+ b'); await pg.wait_for_timeout(200)
                check('typing in a field is not taken as keys', await pg.evaluate("document.getElementById('geo-q').value") == 'a+ b' and await pg.evaluate("map.getZoom()") == z)
                await pg.evaluate("showTab('rec')")
                await pg.set_viewport_size({'width': 390, 'height': 844}); await pg.wait_for_timeout(400)
                check('turning to portrait switches back', not await pg.evaluate("document.body.classList.contains('wide')"))
            check(f'[{name}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
