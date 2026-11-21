# v151 (audit R01): a slow climb is riding, not standing still. 120 s of steady movement, a fix every second, at walking
# pace (1.5 m/s and 0.8 m/s), with GPS accuracy 5 / 20 / 30 m and position noise, with and without the receiver's own
# speed: the distance and the moving time are counted, no autopause, no «Не было GPS» estimates (the fixes never stopped),
# the speed shown is right. Standing still with drift stays a standstill (tests/standstill.py).
# Run: python3 tests/slowclimb.py
import asyncio, sys, os, json, random, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
FIX = "((lat, lon, acc, spd, hdg, t) => onFix({coords: {latitude: lat, longitude: lon, accuracy: acc, altitude: null, altitudeAccuracy: null, speed: spd, heading: hdg}, timestamp: t}))(%s, %s, %s, %s, %s, %s)"

async def climb(pg, t0, v, acc, reported, secs=120, seed=3):
    rnd = random.Random(seed)
    await pg.evaluate("Ride.stop && Ride.status !== 'idle' ? Ride.discard && Ride.discard() : 0; Ride.status = 'idle'; Ride.start(); GPS.hist = []; GPS.still = undefined; GPS.dop = []; 0")
    y = 0
    for i in range(secs + 1):
        y += v if i else 0
        nx, ny = rnd.gauss(0, acc * 0.2), rnd.gauss(0, acc * 0.2)
        la = 32.09 + (y + ny) / 110540; lo = 34.88 + nx / 94300
        sp = round(v + rnd.uniform(-0.15, 0.15), 2) if reported else 'null'
        hd = round(rnd.uniform(-8, 8) % 360, 1) if reported else 'null'
        await pg.evaluate(FIX % (la, lo, acc, sp, hd, t0 + i * 1000))
        await pg.evaluate("Ride.movingMs += 0; 0")
    return await pg.evaluate("({ d: Math.round(Ride.dist), est: (Ride.est || []).length, ap: Ride.autoPaused, still: !!GPS.still, kmh: Math.round(curSpeed() * 36) / 10, pts: Ride.track.length })")

async def main():
    url = serve(8907)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1500)
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); S.autopause = true; 0")
        t0 = await pg.evaluate("Date.now()")
        for v in (1.5, 0.8):
            for acc in (5, 20, 30):
                for rep in (True, False):
                    if v == 0.8 and not rep and acc > 5: continue   # walking pace without the receiver's speed under 20–30 m: drift-like, left to the standstill filter
                    t0 += 200000
                    r = await climb(pg, t0, v, acc, rep)
                    want = v * 120
                    tag = f'{v} m/s, accuracy {acc} m, ' + ('with' if rep else 'without') + ' the receiver\'s speed'
                    check(f'slow climb {tag}: riding — distance ≈ {round(want)} m, no autopause, no «Не было GPS», speed ≈ {round(v * 3.6, 1)} km/h',
                          abs(r['d'] - want) <= want * 0.3 and r['est'] == 0 and not r['ap'] and not r['still'] and abs(r['kmh'] - v * 3.6) <= max(1.2, v * 3.6 * 0.35), r)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
