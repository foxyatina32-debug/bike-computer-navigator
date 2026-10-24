# Second check (2026-10-24, v75): phone on its side (landscape, upright) keeps the right heading;
# a hairpin on a GPX track is «резко направо», not «развернитесь».
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
def ad(a, b): return abs(((a - b + 180) % 360) - 180)
FEED = """((a, b, g, wk, n) => { for (let i = 0; i < n; i++) { const e = new Event('deviceorientation');
  Object.assign(e, {alpha: a, beta: b, gamma: g, absolute: false}); Object.defineProperty(e, 'webkitCompassHeading', {value: wk});
  Object.defineProperty(e, 'webkitCompassAccuracy', {value: 10}); window.dispatchEvent(e); } })(%s, %s, %s, %s, %s)"""
async def main():
    url = serve(8785)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), viewport=(844, 390), geo=(32.09, 34.88))
        cdp = await ctx.new_cdp_session(pg)
        await cdp.send('Emulation.setDeviceMetricsOverride', {'width': 844, 'height': 390, 'deviceScaleFactor': 3, 'mobile': True, 'screenOrientation': {'type': 'landscapePrimary', 'angle': 90}})
        await pg.wait_for_timeout(1500)
        await pg.evaluate("window.addEventListener('deviceorientation', onOrient, true); Compass.on = true; Att.off = null")
        # Learn north flat: phone top at 100° (gyro frame = true north here).
        await pg.evaluate(FEED % (260, 0, 0, 95, 100)); await pg.wait_for_timeout(500)
        # Stand the phone on its side facing 30° and 200°; the compass value there is whatever iOS gives (here: unrelated numbers).
        for H, a in ((30, 60), (200, 250)):
            await pg.evaluate(FEED % (a, 0, -90, (H * 7 + 123) % 360, 40)); await pg.wait_for_timeout(300)
            h = await pg.evaluate("Compass.hdg")
            check(f'landscape, phone upright facing {H}°: heading {H}°', ad(h, H) < 3, h)
        # Hairpin switchback on a track.
        trk = [[32.20 + i * 0.0002, 34.90, 20] for i in range(15)] + [[32.20 + (14 - i) * 0.0002, 34.90002, 20] for i in range(1, 15)]
        cues = await pg.evaluate(f"(() => {{ const c = {json.dumps(trk)}, cum = cumDist(c); return buildCues(c, cum).filter(x => x.ang !== 'finish').map(x => [x.txt, x.spoken]); }})()")
        check('hairpin on a track: «резко направо», not «развернитесь»', len(cues) == 1 and 'Резко' in cues[0][0] and 'развернитесь' not in cues[0][1], cues)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
