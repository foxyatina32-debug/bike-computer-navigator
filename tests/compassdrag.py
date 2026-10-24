# Map turned by the phone compass: touching / dragging the map never snaps it to north-up,
# and after the map was moved by hand it keeps turning with the phone.
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
FEED = "window.__h = %s; clearInterval(window.__ci); window.__ci = setInterval(() => { Compass.on = true; feedCompass(window.__h, 10); }, 50)"
async def main():
    url = serve(8771)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1500)
        await pg.evaluate("setOrientation('compass', true); setFollow(true)")
        await pg.evaluate(FEED % 90); await pg.wait_for_timeout(1500)
        h0 = await pg.evaluate("mapHdg")
        check('map turns with the phone compass', abs(h0 - 90) < 3, h0)
        # Drag the map with a finger.
        box = await pg.evaluate("(() => { const r = document.getElementById('map').getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()")
        await pg.mouse.move(box['x'], box['y']); await pg.mouse.down()
        await pg.mouse.move(box['x'] + 40, box['y'] + 60, steps=8)
        mid = await pg.evaluate("mapHdg")
        await pg.mouse.up(); await pg.wait_for_timeout(300)
        h1 = await pg.evaluate("({h: mapHdg, follow: GPS.follow})")
        check('touching / dragging keeps the turn (no jump to north)', abs(mid - 90) < 3 and abs(h1['h'] - 90) < 3, {'during': mid, 'after': h1})
        check('dragging stops centring on you', not h1['follow'], h1)
        # Phone turned after the drag: the map follows it although centring is off.
        await pg.evaluate(FEED % 200); await pg.wait_for_timeout(1500)
        h2 = await pg.evaluate("mapHdg")
        check('after a drag the map still turns with the phone', abs(((h2 - 200 + 180) % 360) - 180) < 3, h2)
        # A plain tap.
        await pg.mouse.click(box['x'], box['y']); await pg.wait_for_timeout(500)
        h3 = await pg.evaluate("mapHdg")
        check('a tap does not turn the map', abs(((h3 - 200 + 180) % 360) - 180) < 3, h3)
        # North-up still works.
        await pg.evaluate("clearInterval(window.__ci); setOrientation('north', true)"); await pg.wait_for_timeout(300)
        check('north-up mode keeps north up', await pg.evaluate("mapHdg") == 0)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
