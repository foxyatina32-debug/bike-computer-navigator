# Loop route (start = finish): at the start it never says «прибыли», even with GPS a few metres on the finish side;
# after riding the whole loop it does.
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
k = 111320 * math.cos(32.1 * math.pi / 180); S = (32.10, 34.88)
pts = []
for d in range(0, 501, 20): pts.append([S[0] + d / 110540, S[1], 50])
for d in range(20, 501, 20): pts.append([S[0] + 500 / 110540, S[1] + d / k, 50])
for d in range(20, 501, 20): pts.append([S[0] + (500 - d) / 110540, S[1] + 500 / k, 50])
for d in range(20, 501, 20): pts.append([S[0], S[1] + (500 - d) / k, 50])
ST = "({prog: Math.round(Nav.progress), finish: !!Nav.said.finish, toasts: window.__lastToasts})"
async def main():
    url = serve(8796)
    async with async_playwright() as p:
        for off, name in (((0, 0), 'at the start'), ((-4 / 110540, 2 / k), 'GPS 4 m on the finish side'), ((-2 / 110540, 6 / k), 'GPS 6 m on the returning leg')):
            b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(S[0] + off[0], S[1] + off[1]))
            await pg.wait_for_timeout(1500)
            await pg.evaluate(f"Nav.set({{name: 'Кольцо', coords: {json.dumps(pts)}}})")
            for i in range(4):
                await ctx.set_geolocation({'latitude': S[0] + off[0], 'longitude': S[1] + off[1], 'accuracy': 8}); await pg.wait_for_timeout(1000)
            r = await pg.evaluate(ST)
            check(f'loop, {name}: no «Финиш» / «прибыли» at the start', not r['finish'] and 'Финиш' not in r['toasts'] and r['prog'] < 50, r)
            if name == 'at the start':
                # Ride the whole loop at ~36 km/h (10 m a second — faster would be thrown away as GPS jumps).
                for a, c in zip(pts, pts[1:]):
                    for t in (0.5, 1.0):
                        await ctx.set_geolocation({'latitude': a[0] + (c[0] - a[0]) * t, 'longitude': a[1] + (c[1] - a[1]) * t, 'accuracy': 5}); await pg.wait_for_timeout(1000)
                await pg.wait_for_timeout(800)
                r = await pg.evaluate(ST)
                check('after the whole loop: «Финиш маршрута»', r['finish'] and 'Финиш' in r['toasts'], r)
            if name == 'GPS 4 m on the finish side':
                # Ride off the other way round (along the last leg backwards): the loop flips, no «Финиш».
                rev = pts[::-1]
                for a, c in zip(rev[:9], rev[1:9]):
                    for t in (0.5, 1.0):
                        await ctx.set_geolocation({'latitude': a[0] + (c[0] - a[0]) * t, 'longitude': a[1] + (c[1] - a[1]) * t, 'accuracy': 5}); await pg.wait_for_timeout(1000)
                r = await pg.evaluate("({name: Nav.route.name, finish: !!Nav.said.finish, toasts: window.__lastToasts})")
                check('loop ridden the other way from its start: flipped, no «Финиш»', r['name'].endswith('(обратно)') and not r['finish'] and 'Финиш' not in r['toasts'], r)
            check(f'{name}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
