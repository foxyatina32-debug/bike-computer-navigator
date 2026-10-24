# Fixes from the 2026-10-24 navigation audit (v73): each check fails on v72.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = [[32.10 + i * 0.0005, 34.88, 20] for i in range(60)]   # 3.3 km straight north
async def main():
    url = serve(8792)
    async with async_playwright() as p:
        # Older saved settings had «к финишу» on: switched once to «назад на трассу».
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88), storage=[['velo:settings', json.dumps({'tofinish': True, 'orient': 'compass'})]])
        await pg.wait_for_timeout(1500)
        check('4.2 off the route: back to the route by default (old «к финишу» switched off once)', await pg.evaluate("S.tofinish === false && !document.getElementById('s-tofinish').checked"))
        lat, lon = 32.09, 34.88
        async def at(la, lo, acc=5, wait=1000):
            await ctx.set_geolocation({'latitude': la, 'longitude': lo, 'accuracy': acc}); await pg.wait_for_timeout(wait)
        # 4. One wild GPS point: the marker stays at the last good one.
        for k in range(4): lat += 0.00005; await at(lat, lon)
        await at(lat + 0.02, lon, wait=700)
        r = await pg.evaluate("(() => { const m = meMarker.getLatLng(); return {jump: GPS.fix.jump, d: hav([m.lat, m.lng], [GPS.good.lat, GPS.good.lon])}; })()")
        check('4.4 a rejected GPS outlier does not move the arrow / map', r['jump'] and r['d'] < 30, r)
        # 1. Ride the track, turn back for 6 s: the track is NOT flipped.
        lat = 32.1001; await at(lat, lon, wait=1500)
        await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(ROUTE)}}}); Nav.setAt -= 300000")
        await pg.wait_for_timeout(400)
        for k in range(10): lat += 0.00005; await at(lat, lon)
        for k in range(6): lat -= 0.00005; await at(lat, lon)
        n1 = await pg.evaluate("Nav.route.name")
        check('4.1 a short turn-back (6 s) does not flip the whole track', n1 == 'Трек', n1)
        for k in range(10): lat += 0.00005; await at(lat, lon)
        # ...but riding against it for 15 s does.
        for k in range(16): lat -= 0.00006; await at(lat, lon)
        n2 = await pg.evaluate("Nav.route.name")
        check('4.1 riding against the track for 15 s still flips it', n2 == 'Трек (обратно)', n2)
        # 3. Weak GPS (accuracy 120 m) pulls the point 80 m aside: no departure, no reroute.
        await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(ROUTE)}, noAsk: true}}); Nav.setAt -= 300000")
        lat = 32.1101
        for k in range(4): lat += 0.00005; await at(lat, lon)
        c0 = await pg.evaluate("Nav.route.coords.length")
        for k in range(6): lat += 0.00005; await at(lat, lon + 0.00085, acc=120)
        r = await pg.evaluate("({off: Nav.offCount, n: Nav.route.coords.length, name: Nav.route.name, txt: document.getElementById('nv-txt').textContent})")
        check('4.3 weak GPS drifting aside is not a departure (no reroute)', r['off'] == 0 and r['n'] == c0, r)
        # ...a real departure with good GPS still is.
        await pg.evaluate("window.__rr0 = Nav.lastReroute")
        for k in range(5): lat += 0.00005; await at(lat, lon + 0.0012, acc=5)
        r = await pg.evaluate("({off: Nav.offCount, rerouted: Nav.lastReroute > window.__rr0})")
        check('4.3 a real departure with good GPS is still detected (reroute)', r['off'] >= 3 or r['rerouted'], r)
        # 5. A wiggly track (S-jogs every ~30 m) gives no turn prompts; a real right turn still does.
        wig = []; la, lo = 32.20, 34.90
        for i in range(40):
            la += 0.00027; lo += (0.00012 if (i // 1) % 2 else -0.00012) if 10 < i < 30 else 0; wig.append([la, lo, 20])
        for i in range(15): lo += 0.0003; wig.append([la, lo, 20])
        cues = await pg.evaluate(f"(() => {{ const c = {json.dumps(wig)}, cum = cumDist(c); return buildCues(c, cum).filter(x => x.ang !== 'finish').map(x => [Math.round(x.d), x.ang]); }})()")
        check('4.5 wiggly trail: no false turn prompts, the real right turn is kept', len(cues) == 1 and isinstance(cues[0][1], (int, float)) and cues[0][1] > 45, cues)
        # 6. Voice: a waypoint message does not cut off a turn prompt that is being spoken.
        r = await pg.evaluate("""(() => { const log = []; let speaking = false;
          const fake = { get speaking() { return speaking; }, pending: false, cancel() { log.push('cancel'); speaking = false; }, speak(u) { log.push('speak:' + u.text); speaking = true; }, getVoices() { return []; } };
          Object.defineProperty(window, 'speechSynthesis', { value: fake, configurable: true });
          S.voice = true; say('Через 200 метров поверните направо', true); say('Точка маршрута: родник'); const a = log.slice();
          log.length = 0; say('Через 50 метров поверните налево', true); return {waypoint: a, turn: log}; })()""")
        check('4.6 a turn prompt is not cut off by a waypoint message (queued after it)', r['waypoint'] == ['cancel', 'speak:Через 200 метров поверните направо', 'speak:Точка маршрута: родник'], r)
        check('4.6 a new turn prompt still speaks at once', r['turn'][0] == 'cancel', r)
        # 7. Back after a 10-minute locked screen, 3 km further: moving time grows with the distance.
        r = await pg.evaluate("""(() => { Ride.status = 'idle'; Ride.start(); const t0 = Date.now() - 700000;
          Ride.onFix({lat: 32.30, lon: 34.80, acc: 5, spd: 5, t: t0, alt: null});
          Ride.onFix({lat: 32.3001, lon: 34.80, acc: 5, spd: 5, t: t0 + 2000, alt: null});
          const m0 = Ride.movingMs, d0 = Ride.dist;
          Ride.onFix({lat: 32.327, lon: 34.80, acc: 5, spd: 5, t: t0 + 602000, alt: null});
          return {dd: Ride.dist - d0, dt: (Ride.movingMs - m0) / 1000}; })()""")
        check('4.7 after a 10-min gap: 3 km added with ~10 min of moving time (not 5 s)', 2900 < r['dd'] < 3100 and 550 < r['dt'] < 620, r)
        # 10. Standing on flat ground with GPS height jumping ±8 m: (almost) no climb.
        r = await pg.evaluate("""(() => { Ride.status = 'idle'; Ride.start(); let t = Date.now();
          for (let i = 0; i < 120; i++) Ride.onFix({lat: 32.4, lon: 34.8, acc: 5, spd: 0, t: t + i * 1000, alt: 50 + (i % 2 ? 8 : -8) * Math.random(), altAcc: 10});
          return Math.round(Ride.asc); })()""")
        check('4.10 GPS height jitter (±8 m) does not add up to a climb', r <= 10, r)
        # 9. Phone upright from the start (north never learned): riding east steadily sets north from the GPS course.
        r = await pg.evaluate("""(() => { window.addEventListener('deviceorientation', onOrient, true); Compass.on = true; Att.off = null; Att.abs = false; Compass.hdg = null;
          GPS.fix = {lat: 32.5, lon: 34.8, acc: 5, spd: 5, hdg: 90, jump: false, t: Date.now()}; GPS.lastT = Date.now(); Moving.on = true; Moving.hdg = 90;
          for (let i = 0; i < 40; i++) { const e = new Event('deviceorientation'); Object.assign(e, {alpha: 123, beta: 88, gamma: 0, absolute: false});
            Object.defineProperty(e, 'webkitCompassHeading', {value: 300}); window.dispatchEvent(e); }
          return {off: Att.off, hdg: Compass.hdg}; })()""")
        check('4.9 upright phone, never calibrated: north taken from the GPS course', r['hdg'] is not None and abs(((r['hdg'] - 90 + 180) % 360) - 180) < 3, r)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
