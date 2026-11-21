# v151 (audit R05): one finish of a ride. Two «Стоп → сохранить» at once (a slow phone storage) make one ride, not two;
# while it is being saved the ■ buttons are off and the ride takes no more points; a failed save leaves the ride on pause
# with its track, and ■ then saves it once; the route made from the ride is made once; a failing emergency copy is told.
# Run: python3 tests/stopsave.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
FIX = "([la, lo, t]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 5, altitude: 30, altitudeAccuracy: 5, speed: 6, heading: 0 }, timestamp: t })"
COUNT = "(async () => (await DB.all('rides')).length)()"

async def main():
    url = serve(8915)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1200)
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); S.autopause = false; 0")
        t = [await pg.evaluate("Date.now()")]
        async def ride(n, lat0):
            await pg.evaluate("Ride.start()")
            for i in range(n):
                t[0] += 1000; await pg.evaluate(FIX, [lat0 + i * 6 / 110540, 34.88, t[0]])
        await ride(20, 32.09)
        n0 = await pg.evaluate(COUNT); pts = await pg.evaluate("Ride.track.length")
        # ---- two finishes at once, the storage slow
        await pg.evaluate("window.__put = DB.put; DB.put = (st, v) => new Promise(r => setTimeout(r, 900)).then(() => window.__put(st, v)); 0")
        await pg.evaluate("window.__p = [Ride.stop(true), Ride.stop(true)]; 0")
        st = await pg.evaluate("({ same: window.__p[0] === window.__p[1], cstop: document.getElementById('c-stop').disabled, mstop: document.getElementById('m-stop').disabled, ask: [...document.querySelectorAll('#ask-stop button')].every(b => b.disabled), status: Ride.status })")
        t[0] += 1000; await pg.evaluate(FIX, [32.0912, 34.88, t[0]])
        res = await pg.evaluate("Promise.all(window.__p)")
        await pg.evaluate("DB.put = window.__put; 0")
        rides = await pg.evaluate("(async () => (await DB.all('rides')).map(r => r.track.length))()")
        check('two «Стоп → сохранить» at once: one ride saved, not two; both get the answer', res == [True, True] and len(rides) == n0 + 1, (res, n0, rides))
        check('while saving: the same answer for both, ■ buttons and the finish dialog are off, the ride is no longer recording', st['same'] and st['cstop'] and st['mstop'] and st['ask'] and st['status'] == 'paused', st)
        check('a fix arriving while saving is not added to the saved ride', rides and rides[-1] == pts, (rides, pts))
        check('after saving: idle, the buttons work again', await pg.evaluate("Ride.status === 'idle' && !Ride.stopping && !document.getElementById('m-stop').disabled && [...document.querySelectorAll('#ask-stop button')].every(b => !b.disabled)"))
        # ---- a failed save
        await ride(20, 32.095)
        pts = await pg.evaluate("Ride.track.length")
        pg.once('dialog', lambda d: asyncio.ensure_future(d.dismiss()))
        await pg.evaluate("window.__put = DB.put; DB.put = (st, v) => st === 'rides' ? Promise.reject(new Error('QuotaExceeded')) : window.__put(st, v); 0")
        ok = await pg.evaluate("Ride.stop(true)")
        st = await pg.evaluate("({ status: Ride.status, n: Ride.track.length })")
        check('a failed save: «not saved», the ride stays on pause with its whole track', ok is False and st['status'] == 'paused' and st['n'] == pts, (ok, st))
        await pg.evaluate("DB.put = window.__put; 0")
        n1 = await pg.evaluate(COUNT)
        ok = await pg.evaluate("Ride.stop(true)")
        check('■ again: saved once', ok is True and await pg.evaluate(COUNT) == n1 + 1)
        # ---- the route from the ride, asked twice at once: made once
        await ride(110, 32.1)
        await pg.evaluate("Ride.stop(true)")
        r0 = await pg.evaluate("(async () => (await DB.all('routes')).length)()")
        await pg.evaluate("Promise.all([quickSave(Ride.lastSaved), quickSave(Ride.lastSaved)])"); await pg.wait_for_timeout(1500)
        r1 = await pg.evaluate("(async () => (await DB.all('routes')).length)()")
        check('the route made from the ride, asked twice at once: one route', r1 == r0 + 1, (r0, r1))
        # ---- the emergency copy failing is told
        await ride(5, 32.11)
        await pg.evaluate("window.__put = DB.put; DB.put = (st, v) => st === 'kv' ? Promise.reject(new Error('QuotaExceeded')) : window.__put(st, v); window.__lastToasts = ''; 0")
        await pg.evaluate("Ride.persist().catch(() => {})"); await pg.wait_for_timeout(300)
        tt = await pg.evaluate("window.__lastToasts || ''")
        check('the emergency copy cannot be saved: the rider is told', 'аварийную копию' in tt, tt[-160:])
        await pg.evaluate("DB.put = window.__put; 0"); await pg.evaluate("Ride.persist()"); await pg.wait_for_timeout(300)
        check('…and told again when it works', 'снова сохраняется' in await pg.evaluate("window.__lastToasts || ''"))
        await pg.evaluate("Ride.stop(false)")
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
