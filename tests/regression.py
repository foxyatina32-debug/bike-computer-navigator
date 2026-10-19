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
        # «■ Стоп» opens one dialog: keep riding / delete (asks twice) / finish and save.
        n0 = await pg.evaluate("DB.all('rides').then(r => r.length)")
        await pg.click('#c-stop'); await pg.wait_for_timeout(300)
        info = await pg.evaluate("document.getElementById('ask-stop').hidden ? null : document.getElementById('ask-stop-info').textContent")
        await pg.click('#st-cont'); await pg.wait_for_timeout(200)
        check('stop dialog: shows the ride, «continue» keeps recording', info and 'км' in info and await pg.evaluate("Ride.status !== 'idle' && document.getElementById('ask-stop').hidden"), info)
        await pg.click('#c-stop'); await pg.wait_for_timeout(200); await pg.click('#st-save'); await pg.wait_for_timeout(500)
        check('stop dialog: «finish and save» saves to History', await pg.evaluate("Ride.status") == 'idle' and await pg.evaluate("DB.all('rides').then(r => r.length)") == n0 + 1)
        await pg.click('#c-play'); lat = await move(ctx, pg, lat, 4)
        await pg.click('#c-stop'); await pg.wait_for_timeout(200); await pg.click('#st-del'); await pg.wait_for_timeout(200)
        armed = await pg.evaluate("Ride.status !== 'idle' && document.querySelector('#st-del b').textContent")
        await pg.click('#st-del'); await pg.wait_for_timeout(500)
        check('stop dialog: delete asks twice, then nothing is saved', armed and 'ещё раз' in armed and await pg.evaluate("Ride.status") == 'idle' and await pg.evaluate("DB.all('rides').then(r => r.length)") == n0 + 1, armed)
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
        # 7. Route card (total / done / left) and the forecast adapting to the rider's pace and the climb ahead.
        await pg.evaluate("showTab('rec')")
        await ctx.set_geolocation({'latitude': 32.09, 'longitude': 34.88, 'accuracy': 5}); await pg.wait_for_timeout(1500)
        await pg.evaluate("Nav.set({name:'ETA test', coords:Array.from({length:201},(_, i)=>[32.09+i*0.0001, 34.88, i<100?50:50+(i-100)*1.5])})")
        await ctx.set_geolocation({'latitude': 32.09, 'longitude': 34.88, 'accuracy': 5}); await pg.wait_for_timeout(1000)
        lat = 32.09
        for _ in range(70): lat += 0.00005; await ctx.set_geolocation({'latitude': lat, 'longitude': 34.88, 'accuracy': 5}); await pg.wait_for_timeout(1000)
        s1 = await pg.evaluate("({done: Nav.progress, total: Nav.route.total, v: Nav.etaPace().v, climb: Nav.route.asc[200], card: [...document.querySelectorAll('.rtb b')].map(x=>x.textContent), left: document.getElementById('r-tleft').textContent, eta: document.getElementById('r-eta').textContent, nav: document.getElementById('nv-etl').textContent})")
        check('route card shows done / left / total', abs(float(s1['card'][0][:-2]) * 1000 - s1['done']) < 20 and s1['card'][2].startswith('2.2'), f"{s1['card']} · {s1['nav']} · {s1['eta']}")
        check('pace learned from riding (~20 km/h)', 17 < s1['v'] * 3.6 < 23, f"{s1['v']*3.6:.1f} km/h, climb ahead {s1['climb']:.0f} m, left {s1['left']}")
        for _ in range(60): lat += 0.0001; await ctx.set_geolocation({'latitude': lat, 'longitude': 34.88, 'accuracy': 5}); await pg.wait_for_timeout(1000)
        s2 = await pg.evaluate("({v: Nav.etaPace().v, left: document.getElementById('r-tleft').textContent})")
        check('forecast reacts to faster riding', s2['v'] > s1['v'] * 1.2, f"{s1['v']*3.6:.1f} → {s2['v']*3.6:.1f} km/h, left {s2['left']}")
        await pg.evaluate("pager.scrollTo({left: 3 * pager.clientWidth})"); await pg.wait_for_timeout(500)
        ov = await pg.evaluate("[...document.querySelectorAll('.page')[3].querySelectorAll('.rtb b, .card .v')].filter(e => e.scrollWidth > e.clientWidth + 1 || e.getBoundingClientRect().right > innerWidth).length")
        await pg.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'route-card.png'))
        check('route page fits the screen', ov == 0, ov)
        await pg.evaluate("Nav.stop()")
        # «С возвращением» says which route it was: name, from → to, length, how much was left, its shape.
        await pg.evaluate("showTab('rec'); Nav.set({name: 'Утренняя петля', coords: Array.from({length: 120}, (_, i) => [32.09 + i * 0.0003, 34.88 + Math.sin(i / 12) * 0.004, 40 + i]), noAsk: true})")
        await pg.wait_for_timeout(500); await pg.evaluate("Nav.showRemaining(2500, 1500); lsSet('activeNav', {...lsGet('activeNav'), at: Date.now() - 60000})")
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(2500)
        rs = await pg.evaluate("({ open: !document.getElementById('ask-resume').hidden, t: document.getElementById('rs-title').textContent, w: document.getElementById('rs-where').textContent, m: document.getElementById('rs-meta').textContent, px: (() => { const c = document.getElementById('rs-thumb'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i]) n++; return n; })() })")
        check('«С возвращением»: name, from → to, km, left, shape', rs['open'] and rs['t'] == 'Утренняя петля' and 'Петах-Тиква' in rs['w'] and '→' in rs['w'] and 'км' in rs['m'] and 'осталось' in rs['m'] and rs['px'] > 300, rs)
        await pg.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'resume.png'))
        await pg.click('#rs-x'); await pg.evaluate("Nav.stop()")
        # «С возвращением» also shows the file the route came from.
        await pg.evaluate("DB.put('routes', {id: 'rf1', name: 'Бен-Шемен синглы', source: 'Файл: Ben-Shemen-2026.gpx', created: Date.now(), dist: 3600, coords: Array.from({length: 40}, (_, i) => [32.09 + i * 0.0009, 34.88, null]), wpts: []})")
        await pg.evaluate("DB.get('routes', 'rf1').then(r => Nav.set({name: r.name, coords: r.coords, rid: r.id, source: r.source, noAsk: true}))"); await pg.wait_for_timeout(500)
        await pg.evaluate("lsSet('activeNav', {...lsGet('activeNav'), at: Date.now() - 60000})")
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(2000)
        rs2 = await pg.evaluate("({ t: document.getElementById('rs-title').textContent, s: document.getElementById('rs-src').hidden ? '' : document.getElementById('rs-src').textContent })")
        check('«С возвращением»: route name and its file name', rs2['t'] == 'Бен-Шемен синглы' and 'Ben-Shemen-2026.gpx' in rs2['s'], rs2)
        await pg.click('#rs-x'); await pg.evaluate("Nav.stop()")
        # Profile: voice test speaks even with prompts off; install shows the iPhone steps.
        await pg.evaluate("showTab('profile'); window.__spoken = []; speechSynthesis.speak = u => window.__spoken.push(u.text); 0")
        await pg.click('#voice-test'); sp = await pg.evaluate("window.__spoken")
        check('«Проверить голос» speaks a test prompt', any('Через двести метров' in x for x in sp), sp)
        await pg.click('#app-install'); await pg.wait_for_timeout(200)
        inst = await pg.evaluate("!document.getElementById('ask-install').hidden && !document.getElementById('in-ios').hidden && document.getElementById('in-and').hidden")
        await pg.click('#in-ok')
        check('«Установить» shows the iPhone steps', inst)
        # ⏻: one dialog — «Закрыть приложение» / «Вернуться в приложение».
        await pg.evaluate("showTab('profile')"); await pg.click('#app-off'); await pg.wait_for_timeout(200)
        d1 = await pg.evaluate("!document.getElementById('ask-off').hidden && document.getElementById('off-close').innerText + ' | ' + document.getElementById('off-back').innerText")
        await pg.click('#off-back'); d2 = await pg.evaluate("document.getElementById('ask-off').hidden")
        check('power off: two buttons, «Вернуться» keeps the app', d1 and 'Закрыть приложение' in d1 and 'Вернуться в приложение' in d1 and d2, d1)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await pg.click('#app-off'); await pg.click('#off-close')
        try:
            await pg.wait_for_url('**/off.html*', timeout=5000)
            txt = await pg.evaluate("document.body.innerText")
            check('«Закрыть»: everything stopped, off screen without «swipe up», button back', 'выключен' in txt and 'смахните' not in txt and 'Вернуться в приложение' in txt, txt[:120])
        except Exception as e:
            check('«Закрыть»: window closed', pg.is_closed(), str(e)[:80])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
