# v125: the map turns around you with the phone compass again.
# - iPhone permission: a request that fails because the touch was not a real tap is asked again on the next tap;
#   a refusal is final for the launch; listening with no data from the phone lets the next tap ask again.
# - Standing still in «По компасу», turning the phone turns the map.
# - «Где я» while following: compass ↔ north (v114 sent it to «по ходу» and the phone compass was lost).
# - Once after the update a saved «по ходу» / «север» goes back to «по компасу».
import asyncio, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
def ad(a, b): return abs(((a - b + 180) % 360) - 180)
# iPhone: alpha relative (gyroscope frame), webkitCompassHeading = magnetic heading of the top of the phone. Fed for ms.
FEED = """((a, wk, ms) => new Promise(res => { const t0 = Date.now(); const id = setInterval(() => {
  const e = new Event('deviceorientation'); Object.assign(e, {alpha: a, beta: 10, gamma: 0, absolute: false});
  Object.defineProperty(e, 'webkitCompassHeading', {value: wk}); Object.defineProperty(e, 'webkitCompassAccuracy', {value: 10});
  window.dispatchEvent(e); if (Date.now() - t0 > ms) { clearInterval(id); res(); } }, 30); }))(%s, %s, %s)"""
RESET = """(mode => { window.removeEventListener('deviceorientation', onOrient, true); window.removeEventListener('deviceorientationabsolute', onOrientAbs, true);
  Object.assign(Compass, {on: false, hdg: null, t: 0, denied: false, asking: false, retry: 0, onAt: 0}); window.__asks = 0;
  DeviceOrientationEvent.requestPermission = () => { window.__asks++;
    if (mode === 'deny') return Promise.resolve('denied');
    if (mode === 'drag-first' && window.__asks === 1) return Promise.reject(new DOMException('Requesting device orientation access requires a user gesture to prompt', 'NotAllowedError'));
    return Promise.resolve('granted'); }; })('%s')"""
async def tap(pg):  # a tap on an empty part of the map
    await pg.touchscreen.tap(195, 420); await pg.wait_for_timeout(250)
async def main():
    url = serve(8931)
    async with async_playwright() as p:
        # saved «по ходу» from v114's «Где я» → back to «по компасу» once
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88), storage=[['velo:settings', json.dumps({'orient': 'course', 'compassOn2': 1})]])
        st = await pg.evaluate("({o: S.orient, c: S.compass, m: S.orient125, saved: JSON.parse(localStorage.getItem('velo:settings')).orient})")
        check('after the update: «по ходу» saved by v114 → «по компасу» again', st['o'] == 'compass' and st['c'] and st['m'] == 1 and st['saved'] == 'compass', st)
        await pg.evaluate("setOrientation('north', true)"); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(500)
        check('chosen later, «север» stays after a restart (the reset is once)', await pg.evaluate("S.orient") == 'north')
        await pg.evaluate("setOrientation('compass', true); setFollow(true)")

        # 1st touch is the end of a map drag (not a tap) → request fails → the next tap asks again and the compass works
        await pg.evaluate(RESET % 'drag-first')
        await pg.evaluate("document.getElementById('map').dispatchEvent(new Event('touchend', {bubbles: true}))"); await pg.wait_for_timeout(250)  # end of a drag: no click
        r1 = await pg.evaluate("({on: Compass.on, asks: __asks})")
        await tap(pg); r2 = await pg.evaluate("({on: Compass.on, asks: __asks})")
        check('iPhone: a failed request (not a tap) is asked again on the next tap', not r1['on'] and r1['asks'] == 1 and r2['on'] and r2['asks'] == 2, [r1, r2])

        # standing still, turning the phone turns the map
        await pg.evaluate(FEED % (320, 100, 1500)); await pg.wait_for_timeout(200)
        s1 = await pg.evaluate("({h: Compass.hdg, m: mapHdg, f: compassFresh(), d: compassDrives()})")
        check('standing: heading from the phone compass (+5° declination), map turned to it', s1['f'] and s1['d'] and ad(s1['h'], 105) < 3 and ad(s1['m'], 105) < 4, s1)
        await pg.evaluate(FEED % (230, 190, 1500)); await pg.wait_for_timeout(200)
        s2 = await pg.evaluate("({h: Compass.hdg, m: mapHdg})")
        check('turning the phone 90° turns the map 90° around you', ad(s2['h'], 195) < 3 and ad(s2['m'], 195) < 4, s2)
        await pg.evaluate(FEED % (320, 100, 1500)); await pg.wait_for_timeout(200)
        s3 = await pg.evaluate("({m: mapHdg, arrow: !!document.querySelector('.me-arr')})")
        check('and back; the arrow is shown', ad(s3['m'], 105) < 4 and s3['arrow'], s3)

        # «Где я» while following: compass → north → compass
        await pg.evaluate("setFollow(true)")
        await pg.click('#c-loc'); await pg.wait_for_timeout(300)
        g1 = await pg.evaluate("({o: S.orient, m: mapHdg, t: document.getElementById('toast').textContent})")
        await pg.click('#c-loc'); await pg.wait_for_timeout(200)
        await pg.evaluate(FEED % (320, 100, 1200)); await pg.wait_for_timeout(200)
        g2 = await pg.evaluate("({o: S.orient, m: mapHdg, t: document.getElementById('toast').textContent})")
        check('«Где я»: compass → north up → compass (never stuck on «по ходу»)', g1['o'] == 'north' and ad(g1['m'], 0) < 1 and g2['o'] == 'compass' and ad(g2['m'], 105) < 4 and 'компас' in g1['t'] and 'компас' in g2['t'], [g1, g2])

        # listening, but the phone sends nothing → the next tap asks again
        await pg.evaluate(RESET % 'grant'); await tap(pg)
        w1 = await pg.evaluate("Compass.on"); await pg.wait_for_timeout(6500)
        w2 = await pg.evaluate("Compass.on"); await tap(pg)
        w3 = await pg.evaluate("({on: Compass.on, asks: __asks})")
        check('no data from the phone for 4 s → the next tap turns the compass on again', w1 and not w2 and w3['on'] and w3['asks'] == 2, [w1, w2, w3])

        # refusal: told once, not asked again on every tap
        await pg.evaluate(RESET % 'deny'); await tap(pg)
        d1 = await pg.evaluate("({on: Compass.on, asks: __asks, t: document.getElementById('toast').textContent})")
        await tap(pg); await tap(pg)
        d2 = await pg.evaluate("__asks")
        check('compass refused: a message once, no asking on every tap', not d1['on'] and d1['asks'] == 1 and 'не разрешён' in d1['t'] and d2 == 1, [d1, d2])
        check('no JS errors', not log['errors'], log['errors'])
        await b.close()
        # Hebrew / English: the new messages are translated
        for lang, word in (('he', 'מצפן'), ('en', 'compass')):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), geo=(32.09, 34.88))
            await pg.evaluate("setOrientation('compass', true); setFollow(true)")
            await pg.click('#c-loc'); await pg.wait_for_timeout(300); t1 = await pg.evaluate("document.getElementById('toast').textContent")
            await pg.click('#c-loc'); await pg.wait_for_timeout(300); t2 = await pg.evaluate("document.getElementById('toast').textContent")
            cyr = any('Ѐ' <= ch <= 'ӿ' for ch in t1 + t2)
            check(f'{lang}: «Где я» messages translated', not cyr and word in (t1 + t2).lower() and not log['errors'], [t1, t2, log['errors']])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
