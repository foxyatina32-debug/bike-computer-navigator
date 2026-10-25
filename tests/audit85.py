# General audit 2026-10-25 (v85): each check fails on v84.
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
FIX = "((lat, lon, acc, spd, t) => onFix({coords: {latitude: lat, longitude: lon, accuracy: acc, altitude: 50, altitudeAccuracy: 5, speed: spd, heading: null}, timestamp: t}))(%s, %s, %s, %s, %s)"
k = 111320 * math.cos(32.1 * math.pi / 180); S = (32.10, 34.88)
loop = []
for d in range(0, 501, 20): loop.append([S[0] + d / 110540, S[1], 50])
for d in range(20, 501, 20): loop.append([S[0] + 500 / 110540, S[1] + d / k, 50])
for d in range(20, 501, 20): loop.append([S[0] + (500 - d) / 110540, S[1] + 500 / k, 50])
for d in range(20, 501, 20): loop.append([S[0], S[1] + (500 - d) / k, 50])
async def main():
    url = serve(8803)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1500); await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)")
        # 1. Standing at a light, screen locked, 3 km ridden in 10 min, screen back on.
        await pg.evaluate("Ride.start()")
        t0 = await pg.evaluate("Date.now()"); la = 32.09
        for i in range(12): await pg.evaluate(FIX % (la, 34.88, 5, 0, t0 + i * 1000))
        await pg.evaluate("Ride.lastTick = Date.now() + 600000")
        t1 = t0 + 12000 + 600000; la2 = la + 3000 / 110540
        for i in range(8): await pg.evaluate(FIX % (la2 + i * 5.5 / 110540, 34.88, 5, 5.5, t1 + i * 1000))
        r = await pg.evaluate("({d: Math.round(Ride.dist), m: Math.round(Ride.movingMs / 1000)})")
        check('a 10-min locked-screen gap (3 km) after standing: ~3 km and ~10 min, counted once', 2950 < r['d'] < 3150 and 540 < r['m'] < 640, r)
        await b.close()
        # 2. Reload right after starting a loop, standing at its start (GPS on the finish side): no «Финиш».
        b, ctx, pg, log2 = await open_app(p, url + '?lang=ru', Mocks(), geo=(S[0] - 4 / 110540, S[1] + 2 / k))
        await pg.wait_for_timeout(1500)
        await pg.evaluate(f"Nav.set({{name: 'Кольцо', coords: {json.dumps(loop)}}})"); await pg.wait_for_timeout(1500)
        await pg.evaluate("window.__appUpdated = true"); await pg.reload(); await pg.wait_for_timeout(2500)
        await pg.evaluate("(() => { const b = document.getElementById('rs-cont'); if (b && !document.getElementById('ask-resume').hidden) b.click(); })()")
        for i in range(4):
            await ctx.set_geolocation({'latitude': S[0] - 4 / 110540, 'longitude': S[1] + 2 / k, 'accuracy': 8}); await pg.wait_for_timeout(1000)
        r = await pg.evaluate("({route: !!Nav.route, prog: Nav.route ? Math.round(Nav.progress) : null, finish: Nav.route ? !!Nav.said.finish : null, toasts: window.__lastToasts})")
        check('loop restored after a restart at its start: no «Финиш маршрута»', r['route'] and not r['finish'] and 'Финиш' not in r['toasts'], r)
        check('no JS errors', not log['errors'] and not log2['errors'], (log['errors'] + log2['errors'])[:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
