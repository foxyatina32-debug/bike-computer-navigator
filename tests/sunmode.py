# v117: «Яркое солнце» (light ride screen), «По солнцу» (light from sunrise to sunset), the route card with one main button,
# the legend tab's 44 × 44 tap area, the greeting gone when a section opens. Russian, Hebrew, English.
# Run: python3 tests/sunmode.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.09 + i * 0.0002, 34.88 + (i // 20) * 0.001, 40 + i] for i in range(60)]
LUM = """(sel => { const el = document.querySelector(sel); let c = getComputedStyle(el).backgroundColor; const m = c.match(/[\\d.]+/g).map(Number);
  return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255; })"""
INK = """(sel => { const m = getComputedStyle(document.querySelector(sel)).color.match(/[\\d.]+/g).map(Number); return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255; })"""

async def main():
    url = serve(8871); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, viewport=(375, 667))
        check('default: dark screen as before', not await pg.evaluate("document.body.classList.contains('sun')") and await pg.evaluate(LUM + "('.tabs')") < 0.4)
        await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=map]').open = true")
        await pg.click('#s-theme [data-t=sun]'); await pg.wait_for_timeout(300)
        await pg.evaluate("showTab('rec')"); await pg.wait_for_timeout(300)
        sun = await pg.evaluate("document.body.classList.contains('sun')")
        tabs, hud, ink = await pg.evaluate(LUM + "('.tabs')"), await pg.evaluate(LUM + "('#hud .mini, #hud')"), await pg.evaluate(INK + "('.tabs button:not(.on)')")
        check('«Яркое солнце»: menu and ride panel light, text dark', sun and tabs > 0.8 and ink < 0.35, (round(tabs, 2), round(hud, 2), round(ink, 2)))
        check('«Яркое солнце»: the map is not darkened (dark-map filter off)', await pg.evaluate("getComputedStyle(document.querySelector('#map .tl-base') || document.body).filter") in ('none', ''))
        await pg.evaluate("Nav.set({name: 'Т', coords: " + json.dumps(ROUTE) + ", noAsk: true})"); await pg.wait_for_timeout(500)
        check('«Яркое солнце»: turn banner light', await pg.evaluate(LUM + "('#navb')") > 0.8)
        await pg.evaluate("Nav.stop(); showTab('profile')"); await pg.wait_for_timeout(300)
        check('lists and settings stay dark (used when stopped)', await pg.evaluate(LUM + "('#sheet-profile')") < 0.2 and await pg.evaluate(INK + "('#sheet-profile h3')") > 0.5)
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(500)
        check('the choice is kept after a restart', await pg.evaluate("S.theme === 'sun' && document.body.classList.contains('sun')"))
        # «По солнцу»: light at noon, dark at night (Israel)
        r = await pg.evaluate("""(() => { S.theme = 'auto'; const st = sunTimes(32.09, 34.88, new Date(2026, 5, 21));
            const rise = st.rise.getUTCHours() + st.rise.getUTCMinutes() / 60, set = st.set.getUTCHours() + st.set.getUTCMinutes() / 60;
            const RD = Date.now; Date.now = () => new Date(2026, 5, 21, 12).getTime(); const noon = sunWanted();
            Date.now = () => new Date(2026, 5, 21, 23).getTime(); const night = sunWanted(); Date.now = RD; applyTheme();
            return { rise, set, noon, night }; })()""")
        check('«По солнцу»: sunrise ≈ 02:30 UTC and sunset ≈ 16:50 UTC in Israel on 21 June', 2.2 < r['rise'] < 2.9 and 16.5 < r['set'] < 17.1, r)
        check('«По солнцу»: light at noon, dark at night', r['noon'] and not r['night'], r)
        await pg.evaluate("S.theme = 'dark'; saveS(); applyTheme()")
        check('«Тёмный» returns the dark screen', not await pg.evaluate("document.body.classList.contains('sun')"))

        # route card: one main button, the rest under «⋯»
        await pg.evaluate(f"DB.put('routes', {{ id: 'r1', name: 'Бен-Шемен', coords: {json.dumps(ROUTE)}, dist: 1500, created: Date.now(), src: 'test', source: 'GPX', wpts: [] }})")
        await pg.evaluate("showTab('routes'); routeSeg('mine')"); await pg.wait_for_timeout(500)
        vis = await pg.evaluate("[...document.querySelectorAll('#rt-list .rtit button')].filter(b => b.offsetParent).map(b => b.textContent.trim())")
        check('route card: only «▶ Поехали» and «⋯» visible', vis == ['▶ Поехали', '⋯'], vis)
        big = await pg.evaluate("(() => { const r = document.querySelector('#rt-list [data-nav]').getBoundingClientRect(), m = document.querySelector('#rt-list [data-more]').getBoundingClientRect(); return [r.height, m.width, m.height]; })()")
        check('route card: buttons big enough for gloves (44 px)', all(v >= 44 for v in big), big)
        await pg.click('#rt-list [data-more]'); await pg.wait_for_timeout(200)
        vis = await pg.evaluate("[...document.querySelectorAll('#rt-list .rtit .a2 button')].filter(b => b.offsetParent).map(b => b.textContent.trim())")
        check('«⋯» opens: ⇆ Обратно (v120), Свой старт, Карта, Google, Waze, GPX, Удалить', vis == ['⇆ Обратно', 'Свой старт', 'Карта', 'Google', 'Waze', 'GPX', 'Удалить'], vis)
        await pg.click('#rt-list [data-del]'); await pg.click('#rt-list [data-del]'); await pg.wait_for_timeout(300)
        check('«Удалить» asks once more, then deletes', await pg.evaluate("DB.all('routes').then(r => r.length)") == 0)
        await pg.evaluate(f"DB.put('routes', {{ id: 'r2', name: 'Яркон', coords: {json.dumps(ROUTE)}, dist: 1500, created: Date.now(), src: 'test', source: 'GPX', wpts: [] }}).then(renderRoutes)"); await pg.wait_for_timeout(300)
        await pg.click('#rt-list [data-nav]'); await pg.wait_for_timeout(600)
        check('«▶ Поехали» starts navigation on the map', await pg.evaluate("!!Nav.route && $('#sheet-routes').hidden"))
        # legend tab tap area
        hit = await pg.evaluate("(() => { const t = document.getElementById('legend-tab'), cs = getComputedStyle(t, '::before'); return [cs.top, cs.right, cs.bottom]; })()")
        check('legend tab: tap area 44 × 44', hit == ['-7px', '-24px', '-7px'], hit)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()

        # greeting goes away when a section opens
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, viewport=(375, 667))
        await pg.evaluate("greet()"); await pg.wait_for_timeout(300)
        shown = await pg.evaluate("!document.getElementById('hello').hidden")
        await pg.evaluate("showTab('routes')"); await pg.wait_for_timeout(200)
        check('the greeting is not left over a section', shown and await pg.evaluate("document.getElementById('hello').hidden"))
        await b.close()

        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, viewport=(375, 667))
            await pg.evaluate(f"DB.put('routes', {{ id: 'r1', name: 'X', coords: {json.dumps(ROUTE)}, dist: 1500, created: Date.now(), src: 'test', source: 'GPX', wpts: [] }})")
            await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=map]').open = true"); await pg.wait_for_timeout(400)
            t1 = await pg.evaluate("document.getElementById('s-theme').parentElement.innerText")
            await pg.evaluate("showTab('routes'); routeSeg('mine')"); await pg.wait_for_timeout(400)
            await pg.click('#rt-list [data-more]'); await pg.wait_for_timeout(300)
            t2 = await pg.evaluate("[...document.querySelectorAll('#rt-list .rtit')].map(e => e.innerText).join(' ')")
            ru = [w for w in (t1 + ' ' + t2).split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: screen setting and route card translated', not ru, ru[:6])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
