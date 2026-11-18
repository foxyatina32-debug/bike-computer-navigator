# v129: the map follows its own size. In the home-screen mode iPhone can change the height after start without a «resize»
# event, and the map kept the old size (a dark band under the menu). The container is resized here without any window event.
# Run: python3 tests/mapfit.py
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
async def main():
    url = serve(9031); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, viewport=(390, 844))
        size = "(() => { const s = map.getSize(), r = document.getElementById('map').getBoundingClientRect(); return [s.x, s.y, Math.round(r.width), Math.round(r.height)]; })()"
        a = await pg.evaluate(size)
        check('at start the map has the size of its place on the screen', a[0] == a[2] and a[1] == a[3], a)
        # the place grows by 60 px at the bottom without any window «resize» (as iPhone does when the safe area settles)
        await pg.evaluate("document.getElementById('map').style.bottom = '-60px'"); await pg.wait_for_timeout(500)
        c = await pg.evaluate(size)
        check('the place of the map changes with no «resize» event: the map takes the new size by itself', c[1] == c[3] and c[1] == a[1] + 60, c)
        await pg.evaluate("document.getElementById('map').style.bottom = ''"); await pg.wait_for_timeout(500)
        d = await pg.evaluate(size)
        check('and back', d[1] == d[3] == a[1], d)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
