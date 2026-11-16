# v123: the «Вы не на маршруте» window comes at once when it is needed.
# - far from the route with a rough fix (indoors, ±80 m): at once, no 20 s wait for a better fix;
# - near the route with a rough fix and the phone standing still (no new fixes): decided by the timer after ≤ 20 s;
# - GPS not on yet: the last known place (≤ 30 min) far from the route → asked at once; an old one (> 30 min) → waits for GPS.
# Run: python3 tests/joinfast.py
import asyncio, sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.10 + i * 0.0005, 34.88, 20] for i in range(60)]
ASK = "!document.getElementById('ask-join').hidden"
# Geolocation under the test's control: one fix with the given accuracy, then silence (a phone lying still).
def geo_once(lat, lon, acc):
    return f"""(() => {{ const cbs = []; window.__fire = () => cbs.forEach(cb => cb({{ coords: {{ latitude: {lat}, longitude: {lon}, accuracy: {acc}, altitude: null, altitudeAccuracy: null, speed: null, heading: null }}, timestamp: Date.now() }}));
  navigator.geolocation.watchPosition = (ok) => {{ cbs.push(ok); setTimeout(() => window.__fire(), 300); return 1; }};
  navigator.geolocation.getCurrentPosition = (ok) => setTimeout(() => ok({{ coords: {{ latitude: {lat}, longitude: {lon}, accuracy: {acc} }}, timestamp: Date.now() }}), 300); }})()"""
NO_GPS = "(() => { navigator.geolocation.watchPosition = () => 1; navigator.geolocation.getCurrentPosition = () => {}; })()"

async def start(p, url, m, init, storage=None):
    b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=storage)
    await ctx.add_init_script(init); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(1200)
    return b, ctx, pg, log

async def time_to_ask(pg, limit):
    t0 = time.time()
    await pg.evaluate(f"Nav.set({{ name: 'Тест', coords: {json.dumps(ROUTE)} }})")
    try: await pg.wait_for_function(ASK, timeout=limit * 1000); return round(time.time() - t0, 1)
    except Exception: return None

async def main():
    url = serve(8961); m = Mocks()
    async with async_playwright() as p:
        # 1. 5 km from the route, fix ±80 m
        b, ctx, pg, log = await start(p, url, m, geo_once(32.055, 34.88, 80))
        t = await time_to_ask(pg, 6)
        check('far from the route with a rough fix (±80 m): the window comes at once (< 2 s)', t is not None and t < 2, t)
        check('…and it says how far', '4.' in await pg.evaluate("document.getElementById('aj-info').textContent") or 'км' in await pg.evaluate("document.getElementById('aj-info').textContent"), await pg.evaluate("document.getElementById('aj-info').textContent"))
        await b.close()
        # 2. 150 m beside the route, fix ±80 m, no new fixes: the timer decides within ~20 s
        b, ctx, pg, log = await start(p, url, m, geo_once(32.11, 34.8818, 80))
        t = await time_to_ask(pg, 26)
        check('near the route with a rough fix and no new fixes: decided by itself within ~20 s', t is not None and 15 <= t <= 23, t)
        await b.close()
        # 3. GPS not on yet, last known place 10 min ago, 5 km away → at once
        b, ctx, pg, log = await start(p, url, m, NO_GPS)
        await pg.evaluate("lsSet('lastFix', { lat: 32.055, lon: 34.88, t: Date.now() - 600000 })")
        t = await time_to_ask(pg, 4)
        check('no GPS yet, last known place (10 min) far away: the window comes at once', t is not None and t < 1.5, t)
        await b.close()
        # 4. last known place 2 hours old → not trusted, waits for GPS
        b, ctx, pg, log = await start(p, url, m, NO_GPS)
        await pg.evaluate("lsSet('lastFix', { lat: 32.055, lon: 34.88, t: Date.now() - 7200000 })")
        t = await time_to_ask(pg, 3)
        check('last known place 2 hours old: not used (waits for GPS)', t is None, t)
        # 5. on the route itself: no window at all
        await b.close()
        b, ctx, pg, log = await start(p, url, m, geo_once(32.1101, 34.88, 10))
        t = await time_to_ask(pg, 4)
        check('standing on the route: no «Вы не на маршруте» window', t is None, t)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
