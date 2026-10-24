# Heading like Google Maps: gyroscope attitude + compass offset. Standing the phone up (handlebar) must not throw the
# map to another side; turning with the phone upright turns the map; the map follows that heading.
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
def ad(a, b): return abs(((a - b + 180) % 360) - 180)
# iPhone: alpha is relative (gyroscope frame), webkitCompassHeading is the magnetic heading of the top of the phone.
FEED = """((a, b, g, wk, n) => { for (let i = 0; i < n; i++) { const e = new Event('deviceorientation');
  Object.assign(e, {alpha: a, beta: b, gamma: g, absolute: false}); Object.defineProperty(e, 'webkitCompassHeading', {value: wk});
  Object.defineProperty(e, 'webkitCompassAccuracy', {value: 10}); window.dispatchEvent(e); } })(%s, %s, %s, %s, %s)"""
async def main():
    url = serve(8772)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1500)
        await pg.evaluate("window.addEventListener('deviceorientation', onOrient, true); Compass.on = true; Att.off = null; setOrientation('compass', true); setFollow(true)")
        await pg.wait_for_timeout(300)
        # Flat in the hand, gyroscope frame rotated 40° from north: top of the phone points to 100° magnetic → 105° true.
        await pg.evaluate(FEED % (-40 % 360, 0, 0, 100, 200)); await pg.wait_for_timeout(1200)
        h = await pg.evaluate("Compass.hdg")
        check('flat: heading = compass + declination', ad(h, 105) < 2, h)
        # Stand the phone up (handlebar mount) facing the same way; the plain compass value goes wild there.
        for wk in (280, 20, 200, 310):
            await pg.evaluate(FEED % (-40 % 360, 88, 0, wk, 20))
        await pg.wait_for_timeout(300)
        h2 = await pg.evaluate("Compass.hdg")
        check('upright on the handlebar: same heading, no jump from the compass glitch', ad(h2, 105) < 3, h2)
        # Turn right by 30° with the phone upright (gyroscope alpha goes down by 30).
        await pg.evaluate(FEED % ((-40 - 30) % 360, 88, 0, 280, 60)); await pg.wait_for_timeout(1200)
        h3 = await pg.evaluate("({c: Compass.hdg, m: mapHdg})")
        check('upright, turning with the phone turns the heading', ad(h3['c'], 135) < 3, h3)
        check('the map follows the phone', ad(h3['m'], 135) < 4, h3)
        # Half-tilted (45°): still the same direction.
        await pg.evaluate(FEED % ((-40 - 30) % 360, 45, 0, 130, 60)); await pg.wait_for_timeout(500)
        h4 = await pg.evaluate("Compass.hdg")
        check('half-tilted: same direction', ad(h4, 135) < 3, h4)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
