# «По ходу» map like Google / Apple Maps: between 1-per-second GPS points the map pans and turns every frame,
# not in one jump per second; a 90° turn is turned gradually.
import asyncio, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
def ad(a, b): return abs(((a - b + 180) % 360) - 180)
SAMPLE = "(() => { const c = map.getCenter(); return [c.lat, c.lng, mapHdg]; })()"
async def main():
    url = serve(8775)
    async with async_playwright() as p:
        lat, lon = 32.09, 34.88
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(lat, lon))
        await pg.wait_for_timeout(1500)
        await pg.evaluate("S.compass = false; Compass.on = false; Compass.hdg = null; setOrientation('course', true); setFollow(true)")
        samples = []
        async def ride(n, dlat, dlon):
            nonlocal lat, lon
            for k in range(n):
                lat += dlat; lon += dlon
                await ctx.set_geolocation({'latitude': lat, 'longitude': lon, 'accuracy': 5})
                for j in range(10):
                    await pg.wait_for_timeout(100); samples.append(await pg.evaluate(SAMPLE))
        await ride(8, 0.000055, 0)                       # north, ~6 m/s
        north = samples[-30:]
        # Map centre moves in every 0.1 s slice, not only once a second.
        # (Leaflet moves the map by whole pixels: at zoom 16 one pixel ≈ 2 m, i.e. a 1-px step every ~⅓ s at 22 km/h.)
        steps = [math.hypot((b_[0] - a[0]) * 110540, (b_[1] - a[1]) * 94000) for a, b_ in zip(north, north[1:])]
        run = longest = 0
        for d in steps:
            run = run + 1 if d < 0.05 else 0; longest = max(longest, run)
        check('riding: the map moves steadily (never stands still for half a second, no jumps)', longest <= 3 and max(steps) < 2.5, {'longest_still_x100ms': longest, 'max_step_m': round(max(steps), 2)})
        check('riding north: map turned to the direction of travel', ad(samples[-1][2], 0) < 8, samples[-1][2])
        del samples[:-1]
        await ride(8, 0, 0.000065)                       # turn right: east
        turns = [ad(b_[2], a[2]) for a, b_ in zip(samples, samples[1:])]
        moving = sum(1 for x in turns if x > 1)
        # (a headless browser's timers jitter by tens of ms: one 0.1 s sample may hold ~1.3 frames' worth of turn)
        check('a 90° turn is turned gradually (over many frames, no big step)', max(turns) < 30 and moving >= 6, {'max_step_deg': round(max(turns), 1), 'turning_slices': moving})
        check('after the turn the map faces east', ad(samples[-1][2], 90) < 10, samples[-1][2])
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
