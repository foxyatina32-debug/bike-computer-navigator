# Audit v58: every tab/segment/group in basic and Pro, ru/he/en, no JS errors; Pro layers grouping; pages follow navigation.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
async def main():
    url = serve(8777)
    async with async_playwright() as p:
        for lang in ('ru', 'he', 'en'):
            for pro in (False, True):
                m = Mocks(); st = [['velo:pro', json.dumps(pro)], ['velo:sgrp', '["ride"]']]
                b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, storage=st)
                t = f'[{lang} {"Pro" if pro else "basic"}]'
                await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(200)
                g = await pg.evaluate("[...document.querySelectorAll('#sheet-profile details.grp')].map(d => [d.dataset.g, d.open])")
                check(t + ' settings: 6 groups, only the first open', len(g) == 6 and [x[1] for x in g] == [True] + [False]*5, g)
                await pg.evaluate("document.querySelectorAll('#sheet-profile details.grp').forEach(d => d.open = true)"); await pg.wait_for_timeout(200)
                v = await pg.evaluate("({sw: !!document.getElementById('s-pro').offsetParent, keys: !!document.getElementById('k-tf').offsetParent, ver: document.querySelector('#sheet-profile').innerText.includes('v58'), saved: lsGet('sgrp').length})")
                check(t + ' Pro switch always visible, keys only in Pro, groups remembered', v['sw'] and v['keys'] == pro and v['saved'] == 6, v)
                await pg.click('#s-layers'); await pg.wait_for_timeout(200)
                lg = await pg.evaluate("[...document.querySelectorAll('#ly-base .lyg')].map(e => e.textContent)")
                check(t + ' layers: grouped only in Pro', (len(lg) >= 2) == pro, lg)
                await pg.evaluate("showTab('rec')"); await pg.wait_for_timeout(300); await pg.click('#t-gpx'); await pg.wait_for_timeout(200)
                r = await pg.evaluate("({tab: !document.getElementById('sheet-routes').hidden, mine: !document.getElementById('r-mine').hidden, tiles: document.querySelectorAll('#r-mine .qa button').length, pin: !!document.getElementById('t-route'), add: !!document.getElementById('sheet-add')})")
                check(t + ' «+ Маршрут» → Routes «Мои» with 6 tiles; no pin, no add sheet', r == {'tab': True, 'mine': True, 'tiles': 6, 'pin': False, 'add': False}, r)
                await pg.click('#qa-plan'); await pg.wait_for_timeout(200)
                e = await pg.evaluate("({plan: !document.getElementById('r-plan').hidden, eng: !!document.getElementById('pl-engine').offsetParent})")
                check(t + ' «Построить»: engine choice only in Pro', e['plan'] and e['eng'] == pro, e)
                d0 = await pg.evaluate("[...document.querySelectorAll('#dots i')].filter(i => !i.hidden).length")
                await pg.evaluate("showTab('rec'); Nav.set({name: 'T', coords: [[32.09,34.88,10],[32.095,34.88,20],[32.1,34.885,30]], noAsk: true})"); await pg.wait_for_timeout(1000)
                d1 = await pg.evaluate("[...document.querySelectorAll('#dots i')].filter(i => !i.hidden).length")
                await pg.evaluate("Nav.stop()"); await pg.wait_for_timeout(1000)
                d2 = await pg.evaluate("[...document.querySelectorAll('#dots i')].filter(i => !i.hidden).length")
                check(t + ' card pages: 2 without a route, 4 while navigating', (d0, d1, d2) == (2, 4, 2), (d0, d1, d2))
                for tab in ('history', 'routes', 'profile', 'layers', 'rec'): await pg.evaluate(f"showTab('{tab}')"); await pg.wait_for_timeout(150)
                check(t + ' no JS errors', not log['errors'], log['errors'][:3])
                await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
