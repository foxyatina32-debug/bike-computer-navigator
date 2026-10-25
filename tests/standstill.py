# Standing still with GPS drift (as indoors / at a light): the speedometer shows 0, autopause works, no distance added.
# Riding slowly (4 km/h, good GPS) and normally (20 km/h) still shows the real speed.
import asyncio, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
# Feed onFix directly: iOS-like positions with an optional reported speed (Chromium's emulation can't send speed).
FIX = "((lat, lon, acc, spd, t) => onFix({coords: {latitude: lat, longitude: lon, accuracy: acc, altitude: null, altitudeAccuracy: null, speed: spd, heading: null}, timestamp: t}))(%s, %s, %s, %s, %s)"
async def main():
    url = serve(8789)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1500)
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)")
        random.seed(7); t0 = await pg.evaluate("Date.now()")
        k = 94300  # m per degree of longitude here
        async def stand(sec, acc, reported):
            sp = []
            for i in range(sec):
                la = 32.09 + random.uniform(-8, 8) / 110540; lo = 34.88 + random.uniform(-8, 8) / k
                sp_rep = 'null' if reported is None else round(random.uniform(0.3, reported), 2)
                await pg.evaluate(FIX % (la, lo, acc, sp_rep, t0 + i * 1000)); sp.append(await pg.evaluate("Math.round(curSpeed() * 36) / 10"))
            return sp
        sp = await stand(20, 18, None)
        check('standing, GPS wandering ±8 m, no speed from iOS: speedometer 0 after a few seconds', all(x == 0 for x in sp[6:]), sp)
        t0 += 30000
        sp = await stand(20, 12, 1.0)
        check('standing, iOS reports 0.3–1 m/s noise: speedometer 0 after a few seconds', all(x == 0 for x in sp[6:]), sp)
        # Recording while standing: autopause on, no distance.
        await pg.evaluate("Ride.start()"); t0 += 30000
        await stand(20, 15, None)
        r = await pg.evaluate("({ap: Ride.autoPaused, d: Ride.dist})")
        check('recording at a standstill: autopause, no distance from drift', r['ap'] and r['d'] < 15, r)
        # Slow climb 4 km/h with good GPS (acc 5), no reported speed: shows ~4 km/h.
        t0 += 30000; la = 32.10; sp = []
        for i in range(16):
            la += 1.1 / 110540; await pg.evaluate(FIX % (la, 34.88, 5, 'null', t0 + i * 1000)); sp.append(await pg.evaluate("Math.round(curSpeed() * 36) / 10"))
        check('slow climb 4 km/h (good GPS): real speed shown within ~10 s of setting off', all(3 <= x <= 5 for x in sp[11:]), sp)
        # Riding 20 km/h with reported speed: unaffected.
        t0 += 30000; sp = []
        for i in range(10):
            la += 5.6 / 110540; await pg.evaluate(FIX % (la, 34.88, 5, 5.6, t0 + i * 1000)); sp.append(await pg.evaluate("Math.round(curSpeed() * 36) / 10"))
        check('riding 20 km/h: speed unchanged', all(19 <= x <= 21 for x in sp[3:]), sp)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
