# Compass-turned map while riding: the arrow points along the direction of travel (straight up on the screen),
# even when the phone's compass says it faces sideways. Standing still, the phone's compass turns it again.
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
def ad(a, b): return abs(((a - b + 180) % 360) - 180)
FEED = "window.__h = %s; clearInterval(window.__ci); window.__ci = setInterval(() => { Compass.on = true; feedCompass(window.__h, 10); }, 50)"
ARROW = "(() => { const s = document.querySelector('.me-arr'); const m = s && /rotate\\(([-\\d.]+)deg\\)/.exec(s.style.transform); return {arrow: m ? +m[1] : null, map: mapHdg, moving: Moving.on}; })()"
async def main():
    url = serve(8774)
    async with async_playwright() as p:
        lat, lon = 32.09, 34.88
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(lat, lon))
        await pg.wait_for_timeout(1500)
        await pg.evaluate("setOrientation('compass', true); setFollow(true)")
        await pg.evaluate(FEED % 70)   # phone faces 70° (mounted askew / compass off)
        await pg.wait_for_timeout(1200)
        st = await pg.evaluate(ARROW)
        check('standing: map turned by the phone compass', ad(st['map'], 70) < 4, st)
        # Ride north at ~22 km/h.
        for k in range(12):
            lat += 0.000055
            await ctx.set_geolocation({'latitude': lat, 'longitude': lon, 'accuracy': 5}); await pg.wait_for_timeout(1000)
        st = await pg.evaluate(ARROW)
        check('riding: map turned by the direction of travel', ad(st['map'], 0) < 6, st)
        check('riding: arrow points straight ahead (up), not sideways', st['arrow'] is not None and ad(st['arrow'], 0) < 6, st)
        # Stop.
        for k in range(5):
            await ctx.set_geolocation({'latitude': lat, 'longitude': lon, 'accuracy': 5}); await pg.wait_for_timeout(1000)
        await pg.wait_for_timeout(1500)
        st = await pg.evaluate(ARROW)
        check('stopped: back to the phone compass', not st['moving'] and ad(st['map'], 70) < 6, st)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
