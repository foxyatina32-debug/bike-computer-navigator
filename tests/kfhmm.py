# v124: Kalman filter for navigation + HMM matching to the route (Newson & Krumm 2009).
# Kalman: noisy GPS (σ 6 m) on a straight ride → the filtered position is clearly closer to the truth than the raw fixes;
#   standing still the position does not wander; a jump (signal regained far away) starts the filter again, no gliding.
# HMM: a switchback climb (legs 12 m apart), slow (no GPS course), GPS pulled towards the next leg → the place on the route
#   moves on steadily instead of jumping to the leg above; a loop's start / finish, the plain match is kept when lost.
# Run: python3 tests/kfhmm.py
import asyncio, sys, os, json, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
M = 1 / 110540; KX = 1 / (111320 * math.cos(32.1 * math.pi / 180))
LAT0, LON0 = 32.10, 34.88
def pt(n, e): return [LAT0 + n * M, LON0 + e * KX]

async def main():
    url = serve(8981); m = Mocks(); rnd = random.Random(7)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        # ---- Kalman: straight north at 5 m/s, 120 s, GPS noise σ = 6 m, Doppler speed ±0.3 m/s
        fixes, truth = [], []
        for k in range(120):
            n = 5 * k; truth.append(pt(n, 0))
            la, lo = pt(n + rnd.gauss(0, 6), rnd.gauss(0, 6))
            sp = 5 + rnd.gauss(0, 0.3); fixes.append({'lat': la, 'lon': lo, 'acc': 6, 'spd': sp, 'rawSpd': sp, 'hdg': rnd.gauss(0, 3), 't': 1e12 + k * 1000})
        res = await pg.evaluate("fx => { KF.st = null; GPS.still = false; return fx.map(f => { const o = KF.step(f); return [o.lat, o.lon, o.v]; }); }", fixes)
        err = lambda a, t: math.hypot((a[0] - t[0]) / M, (a[1] - t[1]) / KX)
        raw = math.sqrt(sum(err([f['lat'], f['lon']], t) ** 2 for f, t in zip(fixes[10:], truth[10:])) / 110)
        kf = math.sqrt(sum(err(r, t) ** 2 for r, t in zip(res[10:], truth[10:])) / 110)
        check('Kalman: on a straight ride the position error drops (RMS raw vs filtered)', kf < raw * 0.6, f'raw {raw:.1f} м → filtered {kf:.1f} м')
        check('Kalman: speed follows the real 5 m/s', all(abs(r[2] - 5) < 0.8 for r in res[10:]), [round(r[2], 2) for r in res[10:15]])
        # standing still 60 s with the same noise
        still = [{'lat': pt(rnd.gauss(0, 6), rnd.gauss(0, 6))[0], 'lon': pt(0, rnd.gauss(0, 6))[1], 'acc': 6, 'spd': 0, 'rawSpd': 0, 'hdg': None, 't': 2e12 + k * 1000} for k in range(60)]
        rs = await pg.evaluate("fx => { KF.st = null; GPS.still = true; const o = fx.map(f => KF.step(f)); GPS.still = false; return o.map(x => [x.lat, x.lon]); }", still)
        spread_raw = max(err([f['lat'], f['lon']], pt(0, 0)) for f in still[10:]); spread_kf = max(err(r, pt(0, 0)) for r in rs[10:])
        check('Kalman: standing still the position does not wander', spread_kf < spread_raw * 0.5, f'raw up to {spread_raw:.1f} м → filtered up to {spread_kf:.1f} м')
        # v129: walking 1.2 m/s with a weak signal (±20 m) while the app zeroes the speed («standing» / weak fix):
        # the receiver did not say «0», so the filter must not freeze — the position keeps up with the walker
        for still in (True, False):
            wk = [{'lat': pt(1.2 * k + rnd.gauss(0, 12), 0)[0], 'lon': LON0, 'acc': 20, 'spd': 0, 'rawSpd': None, 'hdg': None, 't': 4e12 + k * 1000} for k in range(120)]
            wo = await pg.evaluate("([fx, st]) => { KF.st = null; GPS.still = st; const o = fx.map(f => KF.step(f).lat); GPS.still = false; return o; }", [wk, still])
            lag = [1.2 * k - (o - LAT0) / M for k, o in enumerate(wo)]
            mean_lag = sum(lag[60:]) / 60
            check(f'Kalman: walking with a weak signal, the app sees «standing»={still} — no freezing (mean lag after 1 min)', abs(mean_lag) < 10, f'{mean_lag:.1f} м (v124–v128: 30–65 м)')
        # a repeated fix (same time) changes nothing
        rep = await pg.evaluate(f"(() => {{ KF.st = null; GPS.still = false; const f = {{ lat: {LAT0}, lon: {LON0}, acc: 5, spd: 5, rawSpd: 5, hdg: 0, t: 5e12 }}; KF.step(f); KF.step({{ ...f, lat: {LAT0} + 5 * {M}, t: 5e12 + 1000 }}); const a = KF.step({{ ...f, lat: {LAT0} + 5 * {M}, t: 5e12 + 1000 }}), b = KF.out(); return Math.abs(a.lat - b.lat) < 1e-12; }})()")
        check('Kalman: the same fix repeated (iPhone does that) is not a new measurement', rep)
        # a jump: 2 km away after 5 s → starts again at the new place
        j = await pg.evaluate(f"(() => {{ KF.st = null; GPS.still = false; for (let k = 0; k < 10; k++) KF.step({{ lat: {LAT0} + k * 5 * {M}, lon: {LON0}, acc: 5, spd: 5, hdg: 0, t: 3e12 + k * 1000 }}); const o = KF.step({{ lat: {LAT0 + 2000 * M}, lon: {LON0}, acc: 5, spd: 5, hdg: 0, t: 3e12 + 15000 }}); return [o.lat, o.lon]; }})()")
        check('Kalman: a jump starts the filter again (no gliding across the map)', err(j, pt(2000, 0)) < 1, round(err(j, pt(2000, 0)), 2))

        # ---- HMM: switchback climb — 8 legs of 100 m, 12 m apart, alternating direction
        route = []
        for leg in range(8):
            e = leg * 12
            ns = range(0, 101, 5) if leg % 2 == 0 else range(100, -1, -5)
            route += [pt(n, e) + [50 + leg * 3] for n in ns]
        route += [pt(-10 * k, 84) + [74] for k in range(1, 41)]   # then 400 m away south: a one-way route, not a loop
        await pg.evaluate(f"Nav.set({{ name: 'Серпантин', coords: {json.dumps(route)}, noAsk: true }}); Nav.lost = false; Nav.progress = 0; Nav.hmm = null")
        # riding the first leg slowly (no course), GPS pulled 8–10 m east, towards leg 2 (12 m away, the opposite direction)
        seq = []
        for k in range(18):
            n = 5 + k * 5; seq.append(pt(n + rnd.gauss(0, 2), 9 + rnd.gauss(0, 1)))
        out = await pg.evaluate("ps => { Nav.hmm = null; Nav.lost = false; Nav.progress = 0; return ps.map(p => { const h = Nav.locate(p, null, true, 6), q = Nav.locate(p, null, false); Nav.progress = h.along; return [Math.round(h.along), Math.round(q.along)]; }); }", seq)
        hmm_al = [o[0] for o in out]; plain_al = [o[1] for o in out]
        jumps_h = sum(1 for a, b in zip(hmm_al, hmm_al[1:]) if abs(b - a) > 40); jumps_p = sum(1 for a, b in zip(plain_al, plain_al[1:]) if abs(b - a) > 40)
        check('HMM: on a switchback with GPS pulled to the next leg, the place on the route stays on the leg ridden', hmm_al[-1] < 110 and jumps_h == 0, f'HMM {hmm_al[:6]}… / plain match {plain_al[:6]}…')
        check('HMM: the plain match alone would jump to the next leg here (the case it is for)', jumps_p > 0 or max(plain_al) > 110, plain_al[:8])
        # a long gap → starts from the plain match again
        r2 = await pg.evaluate(f"(() => {{ Nav.hmm.t -= 60000; const h = Nav.locate({json.dumps(pt(55, 84))}, null, true, 6); return [Math.round(h.along), !!Nav.hmm && Nav.hmm.c.length > 0]; }})()")
        check('HMM: after a long gap it starts again from the plain match', r2[1], r2)
        await pg.evaluate("Nav.stop()")
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
