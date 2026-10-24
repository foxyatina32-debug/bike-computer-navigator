# Fixes from the 2026-10-24 navigation audit (v73): each check fails on v72.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = [[32.10 + i * 0.0005, 34.88, 20] for i in range(60)]   # 3.3 km straight north
async def main():
    url = serve(8792)
    async with async_playwright() as p:
        # Older saved settings had «к финишу» on: switched once to «назад на трассу».
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88), storage=[['velo:settings', json.dumps({'tofinish': True, 'orient': 'compass'})]])
        await pg.wait_for_timeout(1500)
        check('4.2 off the route: back to the route by default (old «к финишу» switched off once)', await pg.evaluate("S.tofinish === false && !document.getElementById('s-tofinish').checked"))
        lat, lon = 32.09, 34.88
        async def at(la, lo, acc=5, wait=1000):
            await ctx.set_geolocation({'latitude': la, 'longitude': lo, 'accuracy': acc}); await pg.wait_for_timeout(wait)
        # 4. One wild GPS point: the marker stays at the last good one.
        for k in range(4): lat += 0.00005; await at(lat, lon)
        await at(lat + 0.02, lon, wait=700)
        r = await pg.evaluate("(() => { const m = meMarker.getLatLng(); return {jump: GPS.fix.jump, d: hav([m.lat, m.lng], [GPS.good.lat, GPS.good.lon])}; })()")
        check('4.4 a rejected GPS outlier does not move the arrow / map', r['jump'] and r['d'] < 30, r)
        # 1. Ride the track, turn back for 6 s: the track is NOT flipped.
        lat = 32.1001; await at(lat, lon, wait=1500)
        await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(ROUTE)}}}); Nav.setAt -= 300000")
        await pg.wait_for_timeout(400)
        for k in range(10): lat += 0.00005; await at(lat, lon)
        for k in range(6): lat -= 0.00005; await at(lat, lon)
        n1 = await pg.evaluate("Nav.route.name")
        check('4.1 a short turn-back (6 s) does not flip the whole track', n1 == 'Трек', n1)
        for k in range(10): lat += 0.00005; await at(lat, lon)
        # ...but riding against it for 15 s does.
        for k in range(16): lat -= 0.00006; await at(lat, lon)
        n2 = await pg.evaluate("Nav.route.name")
        check('4.1 riding against the track for 15 s still flips it', n2 == 'Трек (обратно)', n2)
        # 3. Weak GPS (accuracy 120 m) pulls the point 80 m aside: no departure, no reroute.
        await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(ROUTE)}, noAsk: true}}); Nav.setAt -= 300000")
        lat = 32.1101
        for k in range(4): lat += 0.00005; await at(lat, lon)
        c0 = await pg.evaluate("Nav.route.coords.length")
        for k in range(6): lat += 0.00005; await at(lat, lon + 0.00085, acc=120)
        r = await pg.evaluate("({off: Nav.offCount, n: Nav.route.coords.length, name: Nav.route.name, txt: document.getElementById('nv-txt').textContent})")
        check('4.3 weak GPS drifting aside is not a departure (no reroute)', r['off'] == 0 and r['n'] == c0, r)
        # ...a real departure with good GPS still is.
        await pg.evaluate("window.__rr0 = Nav.lastReroute")
        for k in range(5): lat += 0.00005; await at(lat, lon + 0.0012, acc=5)
        r = await pg.evaluate("({off: Nav.offCount, rerouted: Nav.lastReroute > window.__rr0})")
        check('4.3 a real departure with good GPS is still detected (reroute)', r['off'] >= 3 or r['rerouted'], r)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
