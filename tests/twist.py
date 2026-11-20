# v149: two fingers turn the map, like Google Maps. Real two-finger touches (the browser's touch input): a pinch to zoom
# alone does not turn the map, a small twist (< 12°) neither; a bigger twist turns it the way the fingers turn; turned by
# hand, the map stays so — the phone's compass does not turn it back; the compass label says «Повёрнута»; a tap on the
# compass button brings back the chosen mode; «моё место» and a navigation do too. ru / he / en.
# Run: python3 tests/twist.py
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
def ad(a, b): return abs(((a - b + 180) % 360) - 180)
ROUTE = [[32.09 + i * 0.0005, 34.88, 20] for i in range(40)]
COMPASS = """((h, n) => { for (let i = 0; i < n; i++) feedCompass(h, 10, true); Compass.on = true; Compass.t = Date.now(); })(%s, %s)"""

async def gesture(cdp, cx, cy, r0, r1, a0, a1, steps=12):
    """two fingers around (cx, cy): radius r0→r1 (pinch), angle a0→a1 degrees (twist, clockwise on screen)"""
    def pts(r, a):
        t = math.radians(a)
        return [{'x': cx - r * math.cos(t), 'y': cy - r * math.sin(t), 'id': 1}, {'x': cx + r * math.cos(t), 'y': cy + r * math.sin(t), 'id': 2}]
    await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': pts(r0, a0)})
    for i in range(1, steps + 1):
        k = i / steps
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': pts(r0 + (r1 - r0) * k, a0 + (a1 - a0) * k)})
        await asyncio.sleep(0.03)
    await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    await asyncio.sleep(0.6)

async def main():
    url = serve(8905)
    async with async_playwright() as p:
        for lang, lbl in (('ru', 'Повёрнута'), ('he', 'מסובבת'), ('en', 'Turned')):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), geo=(32.09, 34.88))
            cdp = await ctx.new_cdp_session(pg)
            await pg.wait_for_timeout(1200)
            await pg.evaluate("setOrientation('north', true); const h = document.getElementById('hello'); if (h) { h.classList.remove('on'); h.hidden = true; } 0"); await pg.wait_for_timeout(200)
            cx, cy = 195, 430
            if lang == 'ru':
                z0 = await pg.evaluate("map.getZoom()")
                await gesture(cdp, cx, cy, 60, 130, 0, 0)
                st = await pg.evaluate("({ z: map.getZoom(), h: mapHdg, man: RotMan.on })")
                check('a pinch to zoom: the map zooms, does not turn', st['z'] > z0 + 0.3 and ad(st['h'], 0) < 0.5 and not st['man'], (z0, st))
                await gesture(cdp, cx, cy, 90, 90, 0, 8)
                st = await pg.evaluate("({ h: mapHdg, man: RotMan.on })")
                check('a small twist (8°) while pinching: the map does not turn', ad(st['h'], 0) < 0.5 and not st['man'], st)
            await gesture(cdp, cx, cy, 90, 90, 0, 60)
            st = await pg.evaluate("({ h: mapHdg, b: map.getBearing(), man: RotMan.on, lbl: document.getElementById('compass-lbl').textContent, needle: document.querySelector('#t-compass svg').style.transform })")
            check(f'[{lang}] a twist of 60° clockwise turns the map clockwise (by 60 − 12°); the label says «{lbl}»', ad(st['b'], 48) < 4 and st['man'] and st['lbl'] == lbl and 'rotate' in st['needle'], st)
            if lang != 'ru':
                check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3]); await b.close(); continue
            # turned by hand: the phone's compass does not turn the map back
            await pg.evaluate("setOrientation('compass', true)"); await pg.evaluate(COMPASS % (90, 30)); await pg.wait_for_timeout(500)
            check('compass mode: the map follows the phone (90°)', ad(await pg.evaluate("mapHdg"), 90) < 3, await pg.evaluate("mapHdg"))
            await gesture(cdp, cx, cy, 90, 90, 0, -72)
            h1 = await pg.evaluate("mapHdg")
            for _ in range(10): await pg.evaluate(COMPASS % (90, 5)); await pg.wait_for_timeout(80)
            h2 = await pg.evaluate("mapHdg")
            check('turned by hand in compass mode: stays turned, the phone\'s compass does not turn it back', ad(h1, 150) < 5 and ad(h2, h1) < 1, (h1, h2))
            await pg.evaluate("document.getElementById('t-compass').click()"); await pg.wait_for_timeout(200)
            for _ in range(10): await pg.evaluate(COMPASS % (90, 5)); await pg.wait_for_timeout(80)
            st = await pg.evaluate("({ h: mapHdg, o: S.orient, man: RotMan.on, lbl: document.getElementById('compass-lbl').textContent })")
            check('a tap on the compass: back to the chosen mode (compass), not the next one', st['o'] == 'compass' and not st['man'] and ad(st['h'], 90) < 4 and st['lbl'] == 'Компас', st)
            await pg.evaluate("setOrientation('north', true)"); await pg.wait_for_timeout(200)
            await gesture(cdp, cx, cy, 90, 90, 0, 50)
            await pg.evaluate("document.getElementById('t-compass').click()"); await pg.wait_for_timeout(300)
            st = await pg.evaluate("({ h: mapHdg, o: S.orient, man: RotMan.on })")
            check('north mode: a tap on the compass after turning — north up again', st['o'] == 'north' and not st['man'] and ad(st['h'], 0) < 1, st)
            await gesture(cdp, cx, cy, 90, 90, 0, 50)
            await pg.evaluate("document.getElementById('z-me').click()"); await pg.wait_for_timeout(300)
            check('«моё место» ends the hand-turning too', not await pg.evaluate("RotMan.on") and ad(await pg.evaluate("mapHdg"), 0) < 1)
            await gesture(cdp, cx, cy, 90, 90, 0, 50)
            await pg.evaluate(f"Nav.set({{ name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true }})"); await pg.wait_for_timeout(300)
            check('a navigation started ends the hand-turning', not await pg.evaluate("RotMan.on"))
            await pg.evaluate("Nav.stop()")
            check('[ru] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == "__main__": asyncio.run(main())
