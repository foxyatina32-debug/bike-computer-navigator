# Heading like Google Maps: gyroscope attitude + compass offset. Standing the phone up (handlebar) must not throw the
# map to another side; turning with the phone upright turns the map; the map follows that heading. v148: turning in place
# follows the gyroscope at once (not the lagging compass); a still phone follows a recalibrated compass in a few seconds.
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
# flat and still: the gyroscope frame at alpha a, the compass at wk, n events
STILL = """((a, wk, n) => { for (let i = 0; i < n; i++) { const e = new Event('deviceorientation'); Object.assign(e, { alpha: a, beta: 0, gamma: 0, absolute: false });
  Object.defineProperty(e, 'webkitCompassHeading', { value: wk }); Object.defineProperty(e, 'webkitCompassAccuracy', { value: 10 }); window.dispatchEvent(e); } })(%s, %s, %s)"""
# a turn in place at 60 events a second, in real time: the gyroscope turns at once, the compass catches up with a lag; the true
# heading starts at 105 (compass 100 + 5° declination). wkShift moves the compass's north (a recalibration). → [[t, error°], …]
SPIN = """((secs, degPerSec, lagS, wk0, total, wkShift) => new Promise(done => {
  const a0 = 320, t0 = performance.now(); total = total || secs + 3; wkShift = wkShift || 0; let wk = wk0 + wkShift, last = t0; const err = [];
  const base = Compass.hdg, id = setInterval(() => {
    const now = performance.now(), el = (now - t0) / 1000, dt = (now - last) / 1000; last = now;
    const rot = Math.min(el, secs) * degPerSec, tru = ((wkShift ? 105 + wkShift : base) + rot) % 360;
    wk += (((wk0 + wkShift + rot - wk) % 360 + 540) % 360 - 180) * (1 - Math.exp(-dt / lagS));
    const e = new Event('deviceorientation'); Object.assign(e, { alpha: ((a0 - rot) % 360 + 360) % 360, beta: 0, gamma: 0, absolute: false });
    Object.defineProperty(e, 'webkitCompassHeading', { value: (wk % 360 + 360) % 360 }); Object.defineProperty(e, 'webkitCompassAccuracy', { value: 10 });
    window.dispatchEvent(e);
    err.push([el, Math.abs((((Compass.hdg - tru) % 360) + 540) % 360 - 180)]);
    if (el > total) { clearInterval(id); done(err); }
  }, 16);
}))"""
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
        # ---- v148: turning in place. The gyroscope turns at once, the iPhone compass lags ~0.5 s behind a turn: the heading
        # must follow the gyroscope (it followed the lagging compass — 60–90° behind at 180°/s, the arrow and map «stuck»)
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1200)
        await pg.evaluate("window.addEventListener('deviceorientation', onOrient, true); Compass.on = true; Att.off = null; 0")
        await pg.evaluate(STILL % (320, 100, 120))
        for spd in (180, 360):
            err = await pg.evaluate(SPIN + f"(2, {spd}, 0.5, 100)")
            during = [e for t, e in err if 0.3 < t < 2]; after = [e for t, e in err if 2.15 < t < 2.6]; settled = [e for t, e in err if t > 4.5]
            check(f'turning in place at {spd}°/s: the heading keeps up with the phone (mean ≤ {spd // 12}°), right after stopping it is there (≤ 4°) and stays',
                  sum(during) / len(during) <= spd / 12 and max(after) <= 4 and max(settled) <= 5, (round(sum(during) / len(during), 1), round(max(after), 1), round(max(settled), 1)))
        # still, the compass settles on a north 20° different (it recalibrated): the heading follows it within a few seconds
        err = await pg.evaluate(SPIN + "(0, 0, 0.5, 100, 7, 20)")
        check('lying still, a recalibrated compass (20° off) is followed within ~7 s', err[-1][1] <= 4, (round(err[0][1], 1), round(err[-1][1], 1)))
        check('no JS errors (turning)', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
