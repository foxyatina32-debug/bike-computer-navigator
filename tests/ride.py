# Ride scenarios: a whole ride simulated second by second with a fake clock (fast and deterministic).
# GPS fixes are fed straight into the app's onFix(); speech and toasts are recorded.
# Run: python3 tests/ride.py
import asyncio, sys, os, json, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, CHROME
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

T0 = 1792310400000  # fixed start time for the fake clock (a Saturday morning, UTC)
LAT0, LON0 = 32.0900, 34.8800
MY, MX = 110540, 111320 * math.cos(LAT0 * math.pi / 180)
def ll(x, y): return [LAT0 + y / MY, LON0 + x / MX]          # metres east/north → lat/lon
# An L-shaped route with two turns: 600 m north, right 600 m east, left 400 m north; climbs 60 m on the last leg.
WAY = [(0, 0), (0, 600), (600, 600), (600, 1000)]
def dense(way, step=20):
    out = []
    for (x0, y0), (x1, y1) in zip(way, way[1:]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
        for k in range(n): out.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
    out.append(way[-1]); return out
PTS = dense(WAY)
def ele(x, y): return 40 + max(0, y - 600) * 0.15 if x >= 600 else 40
GPX = '<?xml version="1.0"?><gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Суббота тест</name><trkseg>' + \
      ''.join(f'<trkpt lat="{ll(x, y)[0]:.7f}" lon="{ll(x, y)[1]:.7f}"><ele>{ele(x, y):.1f}</ele></trkpt>' for x, y in PTS) + '</trkseg></trk></gpx>'

async def open_app(p, url, m, viewport=(390, 844)):
    b = await p.chromium.launch(executable_path=CHROME if os.path.exists(CHROME) else None)
    ctx = await b.new_context(viewport={'width': viewport[0], 'height': viewport[1]}, device_scale_factor=2, is_mobile=True, has_touch=True,
                              user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1',
                              permissions=[], service_workers='block', locale='ru-RU')
    # GPS comes only from our feed: the browser's own geolocation never answers.
    await ctx.add_init_script('navigator.geolocation.watchPosition = () => 1; navigator.geolocation.clearWatch = () => {}; navigator.geolocation.getCurrentPosition = () => {};')
    await ctx.add_init_script('window.__said = []; window.speechSynthesis && (speechSynthesis.speak = u => window.__said.push(u.text));')
    await ctx.route('**/*', m.handle)
    pg = await ctx.new_page()
    log = {'errors': []}
    pg.on('pageerror', lambda e: log['errors'].append(str(e)))
    await pg.clock.install(time=T0)
    await pg.goto(url); await pg.clock.run_for(500)
    await pg.wait_for_function('window.__appReady === true', timeout=20000); await pg.clock.run_for(1500)
    await pg.evaluate("{ const s = window.say; window.say = t => { window.__said.push(t); try { s(t); } catch (e) {} }; }")
    return b, ctx, pg, log

class Rider:
    """Feeds one GPS fix per simulated second along a path of metre coordinates."""
    # iPhone positions wander smoothly (filtered), so the error is correlated from second to second: AR(1), ~3 m typical,
    # plus an occasional 8 m hop (trees, buildings).
    def __init__(s, pg, noise=3.0, seed=1): s.pg = pg; s.noise = noise; s.rnd = random.Random(seed); s.x = 0; s.y = 0; s.ex = 0; s.ey = 0
    async def fix(s, x, y, spd, hdg=None, acc=5, alt=None, jump=False):
        k = 0.92; q = s.noise * math.sqrt(1 - k * k)
        s.ex = k * s.ex + s.rnd.gauss(0, q); s.ey = k * s.ey + s.rnd.gauss(0, q)
        hop = 8 if s.rnd.random() < 0.03 else 0
        nx, ny = x + s.ex + s.rnd.uniform(-hop, hop), y + s.ey + s.rnd.uniform(-hop, hop)
        la, lo = ll(nx, ny)
        js = f"onFix({{coords: {{latitude: {la}, longitude: {lo}, accuracy: {acc}, altitude: {json.dumps(alt)}, altitudeAccuracy: 5, speed: {spd}, heading: {json.dumps(hdg)}}}, timestamp: Date.now()}})"
        await s.pg.evaluate(js); await s.pg.clock.run_for(1000)
    async def go(s, way, v=6.0):
        for (x0, y0), (x1, y1) in zip(way, way[1:]):
            L = math.hypot(x1 - x0, y1 - y0); n = max(1, int(L / v)); h = (math.degrees(math.atan2(x1 - x0, y1 - y0)) + 360) % 360
            for k in range(1, n + 1):
                s.x, s.y = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
                await s.fix(s.x, s.y, v, h, alt=ele(s.x, s.y))
    async def stand(s, secs, feed=True):
        for _ in range(secs):
            if feed: await s.fix(s.x, s.y, 0, None, alt=ele(s.x, s.y))
            else: await s.pg.clock.run_for(1000)

ST = "({prog: Nav.progress, total: Nav.route && Nav.route.total, off: document.getElementById('navb').classList.contains('off'), txt: document.getElementById('nv-txt').textContent, rem: document.getElementById('nv-rem').textContent, eta: document.getElementById('nv-eta').textContent, etl: document.getElementById('nv-etl').textContent, card: [...document.querySelectorAll('.rtb b')].map(x => x.textContent), dist: Ride.dist, moving: Ride.movingMs, status: Ride.status, said: window.__said.filter(Boolean).map(String), toasts: window.__lastToasts || ''})"

async def main():
    url = serve(8797); m = Mocks()
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'saturday.gpx'); open(tmp, 'w', encoding='utf-8').write(GPX)
    async with async_playwright() as p:
        # ---------- 1. Whole ride: import file → ride with turns → café stop → wrong turn → reload → finish → save ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        rd = Rider(pg)
        await rd.fix(0, -5, 0)  # standing at the start
        await pg.set_input_files('#gpx-file', tmp); await pg.clock.run_for(1500)
        check('GPX file imported and listed', await pg.evaluate("document.querySelectorAll('#gpx-list [data-go]').length") == 1)
        await pg.click('#gpx-list [data-go]'); await pg.clock.run_for(1500)
        s = await pg.evaluate(ST)
        check('navigation starts at the start, no questions', s['total'] and abs(s['total'] - 1600) < 30 and await pg.evaluate("document.getElementById('ask-start').hidden && document.getElementById('ask-join').hidden"), f"total {s['total']:.0f} m, card {s['card']}")
        check('compact panel during navigation', await pg.evaluate("document.getElementById('hud').classList.contains('compact')") == await pg.evaluate("!!S.compactNav"))
        await pg.click('#m-play' if await pg.is_visible('#m-play') else '#c-play'); await pg.clock.run_for(500)
        await rd.go([(0, -5), (0, 0)] + WAY[1:2], v=6)  # first leg
        s = await pg.evaluate(ST)
        check('turn announced before the corner', any('направо' in x.lower() for x in s['said']), s['said'])
        check('progress follows the rider', abs(s['prog'] - 600) < 30 and not s['off'], f"{s['prog']:.0f} m, card {s['card']}")
        check('ride distance ≈ ridden', 560 < s['dist'] < 680, f"{s['dist']:.0f} m")
        check('ETA shown with minutes left', 'мин' in s['etl'] and ':' in s['eta'], f"{s['etl']} · {s['eta']}")
        await rd.go([(0, 600), (300, 600)], v=6)
        # café stop 5 min with fixes still arriving: auto-pause, moving time must not grow much
        mv0 = await pg.evaluate('Ride.movingMs'); await rd.stand(300)
        mv1 = await pg.evaluate('Ride.movingMs')
        check('café stop (GPS still coming): moving time paused', mv1 - mv0 < 15000, f"+{(mv1 - mv0) / 1000:.0f} s in 300 s")
        # same stop when iOS stops delivering fixes (phone lying still)
        mv0 = await pg.evaluate('Ride.movingMs'); await rd.stand(180, feed=False)
        mv1 = await pg.evaluate('Ride.movingMs')
        check('stop with no GPS updates: moving time paused', mv1 - mv0 < 15000, f"+{(mv1 - mv0) / 1000:.0f} s in 180 s")
        s0 = await pg.evaluate(ST)
        # wrong turn: 200 m south down a side street, then reroute
        await rd.go([(300, 600), (300, 560), (300, 400)], v=6)
        s = await pg.evaluate(ST)
        rerouted = any('перестроен' in x.lower() or 'вернитесь' in x.lower() for x in s['said'])
        check('off route detected and rerouted', rerouted, s['said'][-3:])
        check('route card keeps the original total after reroute', s['card'] and s['card'][2].startswith('1.6'), s['card'])
        # back onto the route and on
        await rd.go([(300, 400), (300, 600), (600, 600), (600, 700)], v=6)
        s = await pg.evaluate(ST)
        check('back on route after detour', not s['off'], f"{s['txt']} · card {s['card']}")
        # iOS reloads the page mid-ride
        await pg.evaluate('Ride.persist()'); await pg.clock.run_for(500)
        d_before = await pg.evaluate('Ride.dist')
        await pg.reload(); await pg.clock.run_for(500); await pg.wait_for_function('window.__appReady === true', timeout=20000); await pg.clock.run_for(1500)
        await pg.evaluate("{ const s = window.say; window.say = t => { window.__said.push(t); try { s(t); } catch (e) {} }; }")
        await rd.go([(600, 700), (600, 760)], v=6)
        s = await pg.evaluate(ST)
        check('after reload: recording continues', s['status'] == 'rec' and s['dist'] >= d_before, f"{s['status']}, {d_before:.0f} → {s['dist']:.0f} m")
        check('after reload: navigation continues without a tap', s['total'] is not None and await pg.evaluate("document.getElementById('ask-resume').hidden"), f"route {s['total']}, resume dialog shown: {not await pg.evaluate('document.getElementById(\"ask-resume\").hidden')}")
        await rd.go([(600, 760), (600, 1000)], v=4)
        await rd.stand(5)
        s = await pg.evaluate(ST)
        check('finish announced', any('прибыли' in x.lower() for x in s['said']), s['said'][-2:])
        if not await pg.is_visible('#c-stop'): await pg.click('#hud-max'); await pg.clock.run_for(400)
        await pg.click('#c-stop'); await pg.clock.run_for(200); await pg.click('#st-save'); await pg.clock.run_for(1000)
        rides = await pg.evaluate("DB.all('rides')")
        check('ride saved to history', len(rides) == 1 and rides[0]['dist'] > 1500, f"{len(rides)} ride(s), {rides[0]['dist']:.0f} m" if rides else 'none')
        await pg.click('.tabs button[data-tab=history]'); await pg.clock.run_for(500)
        await pg.click('#ride-list .rideit .t'); await pg.clock.run_for(800)
        check('ride details open', await pg.evaluate("!document.getElementById('sheet-ride').hidden"))
        check('no JS errors (whole ride)', not log['errors'], log['errors'][:3])
        await b.close()

        # ---------- 2. Start in the middle of the route ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        rd = Rider(pg); rd.x, rd.y = 0, 300
        await rd.fix(0, 300, 0)
        await pg.evaluate("parseBuffer(new TextEncoder().encode(" + json.dumps(GPX) + ").buffer, 'a.gpx').then(it => Nav.set({name: 'mid', coords: it[0].coords}))")
        await pg.clock.run_for(1500)
        check('mid-route: asks how to start', await pg.evaluate("!document.getElementById('ask-start').hidden"))
        await pg.click('#ask-cont'); await pg.clock.run_for(500)
        await rd.go([(0, 300), (0, 450)], v=6)
        s = await pg.evaluate(ST)
        check('mid-route: card counts from the original start', s['card'] and s['card'][2].startswith('1.6') and s['card'][0].startswith('0.4'), s['card'])
        # GPS jump of 2 km: ignored
        d0 = await pg.evaluate('Ride.dist'); await rd.fix(2000, 2000, 6, 0); s = await pg.evaluate(ST)
        await rd.go([(0, 450), (0, 470)], v=6); s2 = await pg.evaluate(ST)
        check('GPS jump ignored (no distance, no off-route)', not s2['off'] and abs(s2['prog'] - 170) < 30 and s2['dist'] - d0 < 60, f"progress {s2['prog']:.0f} m from the continue point, +{s2['dist'] - d0:.0f} m")
        # poor accuracy (80 m) for 20 s: no false off-route
        for k in range(20): await rd.fix(0, 470 + k * 5, 5, 0, acc=80)
        s = await pg.evaluate(ST)
        check('weak GPS: no false off-route', not s['off'], s['txt'])
        check('no JS errors (mid-route)', not log['errors'], log['errors'][:3])
        await b.close()

        # ---------- 3. A loop ridden the other way round: the track flips itself ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        rd = Rider(pg); rd.x, rd.y = 0, -5
        await rd.fix(0, -5, 0)
        loop = [ll(x, y) + [40] for x, y in dense([(0, 0), (0, 400), (400, 400), (400, 0), (0, 0)])]
        await pg.evaluate(f"Nav.set({{name: 'loop', coords: {json.dumps(loop)}}})"); await pg.clock.run_for(1500)
        await rd.go([(0, -5), (0, 0), (400, 0), (400, 200)], v=6)
        s = await pg.evaluate(ST)
        check('loop ridden the other way: track flipped', any('развёрнут' in x.lower() for x in s['said']) and not s['off'] and 'обратно' in await pg.evaluate("Nav.route.name"), f"{s['said'][-2:]} · {s['txt']} · left {s['rem']}")
        check('flipped loop: progress correct', abs(s['prog'] - 600) < 40, f"{s['prog']:.0f} m")
        check('no JS errors (reverse)', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == "__main__": asyncio.run(main())
