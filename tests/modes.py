# Travel modes: bicycle / on foot / car — routes, speeds, voice timing, ride type.
# Run: python3 tests/modes.py
import asyncio, sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
A, B = (32.09, 34.88), (32.1, 34.9)

async def plan(pg):
    await pg.evaluate(f"Plan.wps = []; document.getElementById('pl-fromgps').checked = false; addWp([{A[0]},{A[1]}], 'A'); addWp([{B[0]},{B[1]}], 'B'); Plan.cand = null; buildPlan()")
    await pg.wait_for_function("Plan.cand != null", timeout=15000); await pg.wait_for_timeout(300)
    return await pg.evaluate("({ eng: Plan.cand.engine, mode: Plan.cand.opts.mode, time: document.getElementById('r-time').textContent, why: document.getElementById('r-eng').textContent })")

async def main():
    url = serve(8788); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        # top pill → chooser
        await pg.click('#t-mode'); await pg.wait_for_timeout(200)
        await pg.screenshot(path=os.path.join(SHOT, 'modes-chooser.png'))
        await pg.click('#md-foot'); await pg.wait_for_timeout(300)
        st = await pg.evaluate("({ mode: RO.mode, act: S.act, pill: document.getElementById('t-mode').innerText })")
        check('chooser: «Пешком» → mode foot, ride type walk, pill says so', st['mode'] == 'foot' and st['act'] == 'walk' and 'Пешком' in st['pill'], st)
        # foot route: BRouter hiking profile, bike options hidden
        await pg.evaluate("showTab('routes'); routeSeg('plan'); setRO({engine: 'auto'})"); await pg.wait_for_timeout(200)
        hid = await pg.evaluate("[document.getElementById('pl-bike'), document.getElementById('pl-terrain')].every(e => e.offsetParent === null) && document.getElementById('pl-mode').offsetParent !== null")
        r = await plan(pg)
        prof = [c for c in m.calls if 'brouter.de' in c][-1]
        check('on foot: BRouter hiking-mountain, bike options hidden', 'profile=hiking-mountain' in prof and 'пешком' in r['eng'] and hid, f"{r} · {hid}")
        await pg.screenshot(path=os.path.join(SHOT, 'modes-foot-plan.png'))
        # car route: OSRM car first, time without traffic
        await pg.evaluate("setMode('car', true)"); n0 = len(m.calls)
        r = await plan(pg)
        car_calls = [c for c in m.calls[n0:] if 'routed-car' in c]
        check('car: OSRM car route, time without traffic, ride type car', car_calls and r['eng'] == 'OSRM · автомобиль' and 'без пробок' in r['why'] and await pg.evaluate("S.act") == 'car', r)
        gm = await pg.evaluate("gmapsUrl([32.1, 34.9], null)")
        check('car: Google Maps hand-off in driving mode', 'travelmode=driving' in gm, gm[-40:])
        # car speeds are not GPS jumps
        await pg.evaluate("showTab('rec')"); await pg.click('#c-play'); lat = 32.0
        await ctx.set_geolocation({'latitude': lat, 'longitude': 34.85, 'accuracy': 5}); await pg.wait_for_timeout(1000)
        for _ in range(12): lat += 0.00025; await ctx.set_geolocation({'latitude': lat, 'longitude': 34.85, 'accuracy': 5}); await pg.wait_for_timeout(1000)
        rd = await pg.evaluate("({ d: Ride.dist, max: Ride.max * 3.6 })")
        check('car: 90 km/h counted (not dropped as GPS jumps)', rd['d'] > 250 and rd['max'] > 70, rd)
        await pg.click('#c-stop'); await pg.click('#st-save'); await pg.wait_for_timeout(300)
        # voice: car gets the turn ~600 m ahead, bicycle ~220 m
        coords = [[32.05 + i * 0.0001, 34.8, None] for i in range(101)] + [[32.06, 34.8 + i * 0.00012, None] for i in range(1, 60)]
        await pg.evaluate(f"window.__said = []; const s0 = window.say; window.say = (t, ...a) => {{ window.__said.push(t); return s0(t, ...a); }}; Nav.set({{ name: 'car', coords: {json.dumps(coords)}, opts: {{ mode: 'car' }}, noAsk: true }})")
        for la in (32.0530, 32.0533, 32.0536, 32.0539, 32.0542, 32.0545, 32.0548):
            await ctx.set_geolocation({'latitude': la, 'longitude': 34.8, 'accuracy': 5}); await pg.wait_for_timeout(1000)
        said = await pg.evaluate("window.__said.filter(Boolean)")
        check('car: turn announced ~500 m ahead', any(x.startswith('Через 5') or x.startswith('Через 6') for x in said), said)
        await pg.evaluate("Nav.stop()")
        # A→B on foot gives variants
        await pg.evaluate(f"setMode('foot', true); openAB(); AB.kind = 'one'; AB.a = [{A[0]},{A[1]}]; AB.b = [{B[0]},{B[1]}]; abRender()")
        abh = await pg.evaluate("[document.getElementById('ab-terr'), document.getElementById('ab-diff')].every(e => e.offsetParent === null)")
        await pg.click('#ab-go'); await pg.wait_for_function("AB.vars.length > 0 && !AB.busy", timeout=15000)
        v = await pg.evaluate("AB.vars.map(x => x.prof)")
        check('A→B on foot: variant, surface/difficulty hidden', v and 'пешком' in v[0] and abh, f"{v} · {abh}")
        await pg.click('#ab-ride'); await pg.wait_for_timeout(300)
        check('A→B on foot: navigation keeps the mode', await pg.evaluate("Nav.route.opts.mode") == 'foot')
        await pg.evaluate("Nav.stop()")
        # Profile ride type ↔ mode
        await pg.evaluate("showTab('profile')"); await pg.click('#s-act [data-a=bike]'); await pg.wait_for_timeout(200)
        check('Profile «Вело» → mode bicycle', await pg.evaluate("RO.mode") == 'bike' and 'MTB' in await pg.evaluate("document.getElementById('t-mode').innerText"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # Google with a key: DRIVE / WALK
        m = Mocks()
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=[['velo:gkey', '"AIzaTEST"']])
        await pg.evaluate("setMode('car', true); showTab('routes'); routeSeg('plan'); setRO({engine: 'google'})"); await plan(pg)
        await pg.evaluate("setMode('foot', true)"); await plan(pg)
        modes = [x[2].get('travelMode') for x in m.bodies if 'routes.googleapis' in x[0]]
        check('Google: DRIVE for car, WALK on foot', modes[:2] == ['DRIVE', 'WALK'], modes)
        check('no JS errors (Google)', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
