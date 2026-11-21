# v151 (audit R06, R07): only fresh GPS counts. A fix 71 s older than the last one, 1 km away, adds nothing (it used to add
# ~1 km); a repeated fix and a stale cached one are dropped; five older fixes that agree (the phone's clock set back) are
# taken. Navigation: the fixes stopped while riding → after 20 s the banner says «Нет свежего GPS» with the age instead
# of the old instruction, «Перестроить» waits for the signal; standing (iPhone sends few fixes) the instruction stays
# for 2 min; a fresh fix brings it back. Height: 400 fixes standing with the GPS height jumping 30 ↔ 45 m add no climb
# (it used to add 113 m); a real climb of 100 m over 500 m is counted. ru / en.
# Run: python3 tests/gpsfresh.py
import asyncio, sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
FIX = "([la, lo, t, sp, alt, aa]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 5, altitude: alt, altitudeAccuracy: aa, speed: sp, heading: sp > 0 ? 0 : null }, timestamp: t })"
ROUTE = [[32.09 + i * 0.0005, 34.88, 20] for i in range(40)] + [[32.1095, 34.88 + i * 0.0005, 20] for i in range(1, 30)]
M = 1 / 110540

async def main():
    url = serve(8917)
    async with async_playwright() as p:
        for lang in ('ru', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), geo=(32.09, 34.88))
            await pg.wait_for_timeout(1200)
            await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); GPS.fix = null; S.autopause = true; 0")
            t = [await pg.evaluate("Date.now()")]
            async def fx(la, lo=34.88, sp=5, alt=30, aa=5, dt=1000):
                t[0] += dt; await pg.evaluate(FIX, [la, lo, t[0], sp, alt, aa])
            if lang == 'ru':
                await pg.evaluate("Ride.start()")
                for i in range(20): await fx(32.09 + i * 5 * M)
                d0 = await pg.evaluate("Ride.dist"); f0 = await pg.evaluate("GPS.fix.t")
                await pg.evaluate(FIX, [32.09 + 1000 * M, 34.88, t[0] - 71000, 5, 30, 5])
                st = await pg.evaluate("({ d: Ride.dist, t: GPS.fix.t })")
                check('a fix 71 s older than the last one, 1 km away: no distance added, the position unchanged', abs(st['d'] - d0) < 1 and st['t'] == f0, (d0, st))
                await pg.evaluate(FIX, [32.09 + 19 * 5 * M, 34.88, t[0], 5, 30, 5])
                check('the same fix delivered twice: ignored', abs(await pg.evaluate("Ride.dist") - d0) < 1)
                for i in range(20, 25): await fx(32.09 + i * 5 * M)
                await pg.evaluate("Ride.stop(false)")
                # the phone's clock set back (the system time too): five agreeing older fixes are taken
                t[0] += 180000; await pg.evaluate(FIX, [32.0914, 34.88, t[0], 5, 30, 5])
                base = await pg.evaluate("Date.now()")
                for k in range(5): await pg.evaluate(FIX, [32.0915 + k * 5 * M, 34.88, base + k * 1000, 5, 30, 5])
                check('the clock set back: after five agreeing fixes the GPS goes on', await pg.evaluate("GPS.fix && GPS.fix.t") == base + 4000, await pg.evaluate("GPS.fix && GPS.fix.t"))
                t[0] = await pg.evaluate("Date.now()")
                await pg.evaluate("GPS.fix = null; 0")
                await pg.evaluate(FIX, [32.093, 34.88, t[0] - 60000, 5, 30, 5])
                check('a cached fix a minute old: not taken as the current position', await pg.evaluate("GPS.fix === null"))
                await fx(32.09, dt=0)
            # ---- navigation
            await pg.evaluate(f"Nav.set({{ name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true }})")
            for i in range(12): await fx(32.09 + i * 6 * M, sp=6)
            await pg.wait_for_timeout(300)
            txt0 = await pg.evaluate("document.getElementById('nv-txt').textContent")
            await pg.evaluate("GPS.lastT = Date.now() - 25000; 0"); await pg.wait_for_timeout(1300)
            st = await pg.evaluate("({ txt: document.getElementById('nv-txt').textContent, d: document.getElementById('nv-dist').textContent, cls: document.getElementById('navb').classList.contains('stale') })")
            want = 'Нет свежего GPS' if lang == 'ru' else 'No fresh GPS'
            check(f'[{lang}] the fixes stopped while riding (25 s): «{want}» with the age, not the old instruction', want in st['txt'] and st['cls'] and ('25' in st['d'] or '26' in st['d']), (txt0, st))
            if lang == 'ru':
                n0 = await pg.evaluate("Nav.gen"); await pg.evaluate("window.__lastToasts = ''; Nav.rejoin(false)"); await pg.wait_for_timeout(300)
                check('«Перестроить» on a stale fix: waits for the signal (says so), nothing rebuilt from the old place', 'Нет свежего GPS' in await pg.evaluate("window.__lastToasts") and await pg.evaluate("Nav.gen") == n0)
                await pg.evaluate("GPS.spdEma = 0; GPS.lastT = Date.now() - 60000; Nav.render()")
                check('standing (iPhone sends few fixes): after a minute the instruction stays', 'Нет свежего GPS' not in await pg.evaluate("document.getElementById('nv-txt').textContent"), await pg.evaluate("document.getElementById('nv-txt').textContent"))
                await pg.evaluate("GPS.lastT = Date.now() - 130000; Nav.render()")
                check('…after 2 min standing: «Нет свежего GPS»', 'Нет свежего GPS' in await pg.evaluate("document.getElementById('nv-txt').textContent"))
            await fx(32.09 + 12 * 6 * M, sp=6, dt=25000); await pg.wait_for_timeout(300)
            st = await pg.evaluate("({ txt: document.getElementById('nv-txt').textContent, cls: document.getElementById('navb').classList.contains('stale') })")
            check(f'[{lang}] a fresh fix: the instruction is back', want not in st['txt'] and not st['cls'], st)
            await pg.evaluate("Nav.stop()")
            if lang == 'ru':
                # ---- height while standing: 400 fixes, the GPS height jumping 30 ↔ 45 m every 20 s
                rnd = random.Random(5)
                await pg.evaluate("Ride.start()")
                for i in range(400):
                    await fx(32.095 + rnd.gauss(0, 1) * M, 34.88 + rnd.gauss(0, 1) / 94300, sp=0, alt=30 if (i // 20) % 2 == 0 else 45, aa=15)
                st = await pg.evaluate("({ asc: Math.round(Ride.asc), desc: Math.round(Ride.desc), d: Math.round(Ride.dist) })")
                check('400 fixes standing, the GPS height jumping 30 ↔ 45 m: no climb, no descent', st['asc'] <= 3 and st['desc'] <= 3, st)
                await pg.evaluate("Ride.stop(false)")
                await pg.evaluate("Ride.start()")
                for i in range(126): await fx(32.1 + i * 4 * M, sp=4, alt=30 + i * 4 * 0.2 + rnd.gauss(0, 1), aa=5)
                st = await pg.evaluate("({ asc: Math.round(Ride.asc), desc: Math.round(Ride.desc), d: Math.round(Ride.dist) })")
                check('a real climb of 100 m over 500 m: counted (≈ 100 m)', 80 <= st['asc'] <= 115 and st['desc'] <= 10, st)
                await pg.evaluate("Ride.stop(false)")
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
