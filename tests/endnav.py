# ✕ on the navigation banner: asks first; «Продолжить» keeps the route, «Завершить» ends navigation (ride recording goes on).
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = [[32.09 + i * 0.0005, 34.88, 20] for i in range(30)]
async def main():
    url = serve(8793)
    async with async_playwright() as p:
        for lang, vp in (('ru', (375, 667)), ('he', (393, 852))):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), viewport=vp, geo=(32.0901, 34.88))
            await pg.wait_for_timeout(1500)
            check(f'{lang}: no ✕ without navigation', not await pg.is_visible('#nv-x'))
            await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {json.dumps(ROUTE)}, noAsk: true}}); Ride.start()"); await pg.wait_for_timeout(600)
            box = await pg.evaluate("(() => { const r = document.getElementById('nv-x').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom, innerWidth]; })()")
            check(f'{lang}: ✕ visible on the banner, inside the screen', await pg.is_visible('#nv-x') and box[0] >= 0 and box[1] >= 0 and box[2] <= box[4], box)
            await pg.click('#nv-x'); await pg.wait_for_timeout(300)
            check(f'{lang}: tapping ✕ asks first', await pg.is_visible('#ask-endnav') and await pg.evaluate("!!Nav.route"))
            await pg.click('#en-no'); await pg.wait_for_timeout(300)
            check(f'{lang}: «Продолжить» keeps navigating', not await pg.is_visible('#ask-endnav') and await pg.evaluate("!!Nav.route"))
            await pg.click('#nv-x'); await pg.wait_for_timeout(300); await pg.click('#en-yes'); await pg.wait_for_timeout(400)
            st = await pg.evaluate("({route: !!Nav.route, banner: !document.getElementById('navb').hidden, ride: Ride.status, flag: !!document.querySelector('.rte-fin')})")
            check(f'{lang}: «Завершить» ends navigation, recording continues', not st['route'] and not st['banner'] and st['ride'] == 'rec' and not st['flag'], st)
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
