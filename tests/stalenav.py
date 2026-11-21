# v151 (audit R02): a reroute answered late never replaces a newer route and never brings back a stopped navigation.
# The router is held back; meanwhile another route is chosen / the navigation is stopped; then the old answer arrives.
# Run: python3 tests/stalenav.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
OLD = [[32.09 + i * 0.0005, 34.88, 20] for i in range(40)]
NEW = [[32.09, 34.88 + i * 0.0005, 20] for i in range(40)]
FIX = "([la, lo, t]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 5, altitude: 30, altitudeAccuracy: 5, speed: 5, heading: 90 }, timestamp: t })"
HOLD = """(() => { window.__held = []; const orig = window.__origRoute = window.__origRoute || routeVia;
  routeVia = (...a) => new Promise((res, rej) => window.__held.push(() => orig(...a).then(res, rej))); 0 })()"""
RELEASE = "(() => { const h = window.__held || []; window.__held = []; h.forEach(f => f()); return h.length; })()"

async def main():
    url = serve(8909)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1200)
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); S.tofinish = false; 0")
        t0 = await pg.evaluate("Date.now()")
        async def at(la, lo, k): await pg.evaluate(FIX, [la, lo, t0 + k * 1000])
        # ---- 1: a reroute of OLD answered after NEW was chosen
        await pg.evaluate(f"Nav.set({{ name: 'OLD', coords: {json.dumps(OLD)}, noAsk: true }})"); await at(32.095, 34.884, 1)
        await pg.evaluate(HOLD)
        await pg.evaluate("Nav.rejoin(false); 0"); await pg.wait_for_timeout(200)
        held = await pg.evaluate("window.__held.length")
        await pg.evaluate(f"Nav.set({{ name: 'NEW', coords: {json.dumps(NEW)}, noAsk: true }})")
        free = await pg.evaluate("!Nav.rejoining")
        n = await pg.evaluate(RELEASE); await pg.wait_for_timeout(1500)
        st = await pg.evaluate("({ name: Nav.route && Nav.route.name, n: Nav.route && Nav.route.coords.length, rr: !!(Nav.route && Nav.route.rr) })")
        check('a reroute of OLD answered after NEW was chosen: NEW stays', held >= 1 and n >= 1 and st['name'] == 'NEW' and st['n'] == len(NEW) and not st['rr'], (held, n, st))
        check('…and NEW may reroute at once (not blocked by the old request)', free)
        # ---- 2: «к финишу» answered after the navigation was stopped
        await pg.evaluate(f"Nav.set({{ name: 'OLD', coords: {json.dumps(OLD)}, noAsk: true }})"); await at(32.096, 34.885, 3)
        await pg.evaluate(HOLD)
        await pg.evaluate("Nav.toFinish(false); 0"); await pg.wait_for_timeout(200)
        await pg.evaluate("Nav.stop()")
        await pg.evaluate(RELEASE); await pg.wait_for_timeout(1500)
        check('«к финишу» answered after the navigation was stopped: it stays stopped', await pg.evaluate("Nav.route === null"), await pg.evaluate("Nav.route && Nav.route.name"))
        # ---- 3: a reroute that belongs to the current route still applies
        await pg.evaluate("routeVia = window.__origRoute; 0")
        await pg.evaluate(f"Nav.set({{ name: 'CUR', coords: {json.dumps(OLD)}, noAsk: true }})"); await at(32.097, 34.886, 5)
        await pg.evaluate("Nav.toFinish(false)"); await pg.wait_for_timeout(800)
        st = await pg.evaluate("({ name: Nav.route && Nav.route.name, rr: !!(Nav.route && Nav.route.rr) })")
        check('a reroute of the current route still applies', st['name'] == 'CUR' and st['rr'], st)
        await pg.evaluate("Nav.stop()")
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
