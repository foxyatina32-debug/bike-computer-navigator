# Off the route / against the route in the middle of a ride (audit v93). The app must either turn the rider back to the
# route or rebuild the way so the route is still followed to the finish — never silently drop the route or cut it short.
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
LAT0, LON0 = 32.10, 34.88
KX = 111320 * math.cos(LAT0 * math.pi / 180); KY = 110540
def ll(n, e): return [LAT0 + n / KY, LON0 + e / KX]
STRAIGHT = [ll(i * 50, 0) + [20] for i in range(61)]                 # 3 km straight north
# Open «U»: 1.5 km north, 300 m east, 1.5 km south — the finish is 300 m east of the start.
U = [ll(i * 50, 0) + [20] for i in range(31)] + [ll(1500, e) + [20] for e in range(50, 301, 50)] + [ll(1500 - i * 50, 300) + [20] for i in range(1, 31)]
SPY = "window.__said = []; { const s = window.say; window.say = function (t) { window.__said.push(t); try { return s.apply(this, arguments); } catch (e) {} }; }"
ST = "({name: Nav.route && Nav.route.name, total: Nav.route && Math.round(Nav.route.total), prog: Math.round(Nav.progress), said: window.__said.slice(), txt: document.getElementById('nv-txt').textContent, icon: document.getElementById('nv-icon').innerHTML, an: !!localStorage.getItem('velo:activeNav') && localStorage.getItem('velo:activeNav') !== 'null'})"

async def run(p, url, mocks, start, settings=None):
    st = [['velo:settings', json.dumps({**{'orient': 'compass'}, **(settings or {})})]]
    b, ctx, pg, log = await open_app(p, url + '?lang=ru', mocks, geo=tuple(start), storage=st)
    await pg.wait_for_timeout(1200); await pg.evaluate(SPY)
    async def go(pts, step=8, wait=1000, acc=5):
        # Ride through pts (metres north/east), one fix per `wait` ms every `step` metres.
        for (n0, e0), (n1, e1) in zip(pts, pts[1:]):
            d = math.hypot(n1 - n0, e1 - e0); k = max(1, round(d / step))
            for i in range(1, k + 1):
                la, lo = ll(n0 + (n1 - n0) * i / k, e0 + (e1 - e0) * i / k)
                await ctx.set_geolocation({'latitude': la, 'longitude': lo, 'accuracy': acc}); await pg.wait_for_timeout(wait)
    return b, ctx, pg, log, go

async def main():
    url = serve(8813)
    async with async_playwright() as p:
        # ---- 1. A GPX track (no router options), 500 m ridden, then 30 s back along it: not flipped — told to turn round, again and again.
        m = Mocks(); b, ctx, pg, log, go = await run(p, url, m, ll(0, 0))
        await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(STRAIGHT)}}})"); await pg.wait_for_timeout(300)
        await go([(0, 0), (500, 0)])
        await go([(500, 0), (230, 0)])
        s = await pg.evaluate(ST)
        check('1.1 GPX mid-ride, riding back 270 m: the track is NOT flipped', s['name'] == 'Трек', s['name'])
        check('1.2 …the rider is told to turn round (voice)', any('развернитесь' in x.lower() for x in s["said"] if x), s['said'][-3:])
        check('1.3 …the banner shows a U-turn', 'scaleX' in s['icon'] and 'развернитесь' in s['txt'].lower(), s['txt'])
        n1 = sum('развернитесь' in x.lower() for x in s["said"] if x)
        await go([(230, 0), (0, 0)])
        s = await pg.evaluate(ST)
        n2 = sum('развернитесь' in x.lower() for x in s["said"] if x)
        check('1.4 still riding the wrong way: reminded again', n2 > n1, f'{n1} → {n2}')
        await go([(0, 0), (60, 0)])
        s = await pg.evaluate(ST)
        check('1.5 turned round: normal guidance again', 'развернитесь' not in s['txt'].lower() and 'scaleX' not in s['icon'], s['txt'])
        check('1.6 route still active and saved for a reload', s['an'] and abs(s['total'] - 3018) < 5, s)
        check('1 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 2. Auto-reroute off: leaving the route is said once, the arrow points back to the route.
        m = Mocks(); b, ctx, pg, log, go = await run(p, url, m, ll(0, 0), {'reroute': False})
        await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(STRAIGHT)}}})"); await pg.wait_for_timeout(300)
        await go([(0, 0), (300, 0), (300, 160)])
        s = await pg.evaluate(ST)
        check('2.1 off the route: the banner says so', 'стороне' in s['txt'], s['txt'])
        check('2.2 …and it is said aloud', any('сошли' in x.lower() for x in s["said"] if x), s['said'][-3:])
        check('2.3 …the arrow points back to the route (left), not straight ahead', 'rotate(-' in s['icon'] or 'scaleX' in s['icon'], s['icon'][:90])
        await go([(300, 160), (300, 220)])
        s = await pg.evaluate(ST)
        check('2.4 said only once while still off', sum('сошли' in x.lower() for x in s["said"] if x) == 1, s['said'][-4:])
        check('2.5 route kept (not dropped) while off', s['an'] and abs(s['total'] - 3018) < 5, s)
        await go([(300, 220), (360, 0), (420, 0)])
        s = await pg.evaluate(ST)
        check('2.6 back on the route: guidance resumes', 'стороне' not in s['txt'] and s['prog'] > 380, s)
        check('2 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 3. Off the route with the router failing (no network): the route stays, the arrow points to it.
        m = Mocks(); m.fail.add('brouter.de'); m.fail.add('routes.googleapis.com'); m.fail.add('routing.openstreetmap.de')
        b, ctx, pg, log, go = await run(p, url, m, ll(0, 0))
        await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(STRAIGHT)}}})"); await pg.wait_for_timeout(300)
        await go([(0, 0), (300, 0), (300, -160)])
        await pg.wait_for_timeout(3000)
        s = await pg.evaluate(ST)
        check('3.1 reroute failed: route still there', s['an'] and abs(s['total'] - 3018) < 5 and s['name'] == 'Трек', s)
        check('3.2 …arrow points back to the route (right)', 'rotate(' in s['icon'] and 'rotate(0 ' not in s['icon'] or 'scaleX' in s['icon'], s['icon'][:90])
        check('3 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 4. Reroute back to the route never cuts the route short to a nearby finish.
        m = Mocks(); b, ctx, pg, log, go = await run(p, url, m, ll(0, 0))
        await pg.evaluate(f"Nav.set({{name: 'Подкова', coords: {json.dumps(U)}}})"); await pg.wait_for_timeout(300)
        t0 = await pg.evaluate("Math.round(Nav.route.total)")
        await go([(0, 0), (300, 0), (300, 60), (300, 140), (300, 200)])
        await pg.wait_for_function("Nav.route && Nav.route.rr", timeout=30000)
        s = await pg.evaluate(ST)
        check('4.1 near the finish of a horseshoe: the way back keeps the rest of the route', s['total'] > t0 - 900, f"route {t0} m → after reroute {s['total']} m")
        check('4 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 5. A planned route (router options): riding back is a U-turn warning, again after a while.
        m = Mocks(); b, ctx, pg, log, go = await run(p, url, m, ll(0, 0))
        await pg.evaluate(f"Nav.set({{name: 'План', coords: {json.dumps(STRAIGHT)}, opts: {{bike: 'xc'}}}})"); await pg.wait_for_timeout(300)
        await go([(0, 0), (400, 0), (150, 0)])
        s = await pg.evaluate(ST)
        n1 = sum('развернитесь' in x.lower() for x in s["said"] if x)
        check('5.1 planned route, riding back: U-turn on the banner', 'scaleX' in s['icon'] and n1 >= 1, s['txt'])
        await go([(150, 0), (0, 0)])
        s = await pg.evaluate(ST)
        check('5.2 …reminded again', sum('развернитесь' in x.lower() for x in s["said"] if x) > n1, s['said'][-3:])
        check('5 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 6. A huge dense track that does not fit in storage is still saved (thinned), so a reload brings it back.
        m = Mocks(); b, ctx, pg, log, go = await run(p, url, m, ll(0, 0))
        await pg.evaluate("(() => { const o = Storage.prototype.setItem; Storage.prototype.setItem = function (k, v) { if (String(v).length > 300000) throw new DOMException('full', 'QuotaExceededError'); return o.call(this, k, v); }; })()")
        dense = [ll(i * 1.0, 3 * math.sin(i / 40)) + [20] for i in range(20000)]   # 20 km, a point every metre
        await pg.evaluate(f"Nav.set({{name: 'Длинный', coords: {json.dumps(dense)}}})"); await pg.wait_for_timeout(500)
        r = await pg.evaluate("(() => { const a = JSON.parse(localStorage.getItem('velo:activeNav') || 'null'); return a ? {n: a.coords.length, last: a.coords[a.coords.length - 1], name: a.name} : null; })()")
        check('6.1 too big for storage: saved thinned, ends kept', r and r['name'] == 'Длинный' and 100 < r['n'] < 20000 and abs(r['last'][0] - dense[-1][0]) < 1e-5, r and {k: r[k] for k in ('n', 'name')})
        check('6 no JS errors', not log['errors'], log['errors'][:3]); await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
