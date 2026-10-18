# Regression tests for bugs found in the QA audit (2026-10-18). Run: python3 tests/regression.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(ok); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''))
async def move(ctx, pg, lat, n):
    for _ in range(n):
        lat += 0.00005; await ctx.set_geolocation({'latitude': lat, 'longitude': 34.88, 'accuracy': 5}); await pg.wait_for_timeout(1000)
    return lat
async def main():
    url = serve(8799); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        # 1. Distance ridden during a manual pause must not be added on resume (also across a reload).
        await pg.click('#c-play'); lat = await move(ctx, pg, 32.09, 6)
        await pg.click('#c-play'); d1 = await pg.evaluate('Ride.dist'); lat = await move(ctx, pg, lat, 10)
        await pg.click('#c-play'); await pg.evaluate('Ride.persist()'); await pg.wait_for_timeout(300)
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(800)
        lat = await move(ctx, pg, lat, 3); gain = await pg.evaluate('Ride.dist') - d1
        check('pause gap not counted (resume + reload)', gain < 25, f'{gain:.0f} m (≈55 m ridden while paused)')
        await pg.click('#c-stop'); await pg.click('#c-stop'); await pg.wait_for_timeout(400)
        # 2. «Add points by tapping the map» leaves enough map to tap; toasts never block taps.
        await pg.click('.tabs button[data-tab=routes]'); await pg.evaluate("routeSeg('plan')"); await pg.check('#pl-tap'); await pg.wait_for_timeout(400)
        top = await pg.evaluate("Math.max(document.querySelector('.top').getBoundingClientRect().bottom, document.getElementById('t-gpx').getBoundingClientRect().bottom)")
        sh = await pg.evaluate("document.getElementById('sheet-routes').getBoundingClientRect().top")
        for f in (.3, .6, .85): await pg.touchscreen.tap(160, top + (sh - top) * f); await pg.wait_for_timeout(600)
        check('tap-to-add: map area free and points added', sh - top > 150 and await pg.evaluate('Plan.wps.length') == 3, f'{sh - top:.0f}px free')
        check('toast does not intercept taps', await pg.evaluate("getComputedStyle(document.getElementById('toast')).pointerEvents") == 'none')
        await pg.uncheck('#pl-tap'); await pg.evaluate("showTab('rec')")
        # 3. Back gesture from ride details returns to the list.
        await pg.evaluate("DB.put('rides',{id:'r1',name:'T',start:Date.now()-3600e3,end:Date.now(),dist:1000,movingMs:600000,max:5,asc:1,desc:1,track:[[32,34.8,null,Date.now()-3600e3],[32.01,34.8,null,Date.now()]]})")
        await pg.click('.tabs button[data-tab=history]'); await pg.click('#ride-list .rideit .t'); await pg.wait_for_timeout(300)
        await pg.go_back(); await pg.wait_for_timeout(300)
        check('back from ride details → history', await pg.evaluate("!document.getElementById('sheet-history').hidden && document.getElementById('sheet-ride').hidden"))
        # 4. Network errors are reported in Russian, not browser English.
        m.fail.add('overpass')
        msg = await pg.evaluate("overpass('[out:json];node(1);out;').then(()=>'ok', e=>e.message)")
        check('readable network error', msg in ('нет связи с сервером', 'нет интернета'), msg)
        m.fail.discard('overpass')
        # 5. Wrong backup file → clear message.
        tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'not-backup.gpx'); open(tmp, 'w').write('<gpx></gpx>')
        await pg.click('.tabs button[data-tab=profile]'); await pg.set_input_files('#bk-file', tmp); await pg.wait_for_timeout(500)
        t = await pg.evaluate('window.__lastToasts')
        check('wrong backup file message', 'не резервная копия' in t, t[-80:])
        # 6. Point-to-point: same point refused; a search made stale by changing options or closing the sheet is discarded.
        slow = {'on': False}
        async def br(route):
            if slow['on']: await asyncio.sleep(2)
            await m.handle(route)
        await ctx.route('https://brouter.de/**', br)
        await pg.evaluate("openAB(); AB.a=[32.09,34.88]; AB.b=[32.09,34.88]; abRender()")
        check('A→B: start = finish refused', await pg.evaluate("document.getElementById('ab-go').disabled"))
        await pg.evaluate("AB.b=[32.1,34.9]; abClear(); abRender()"); slow['on'] = True
        await pg.click('#ab-go'); await pg.wait_for_timeout(400); await pg.click('#ab-terr button[data-t=road]'); await pg.wait_for_timeout(2800)
        check('A→B: options changed during search → old results not shown', await pg.evaluate("AB.vars.length === 0 && AB.lines.length === 0"))
        await pg.click('#ab-go'); await pg.wait_for_timeout(400); await pg.evaluate("showTab('rec')"); await pg.wait_for_timeout(2800)
        check('A→B: sheet closed during search → nothing left on the map', await pg.evaluate("AB.lines.length === 0"))
        slow['on'] = False
        await pg.evaluate("openAB()"); await pg.click('#ab-go'); await pg.wait_for_timeout(1500)
        check('A→B: normal search shows variants', await pg.evaluate("AB.vars.length >= 1 && AB.lines.length >= 1"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
