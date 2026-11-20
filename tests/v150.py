# v150 — fixes after the audit of v149:
#  1. GPS gone while the ride panel collapses: no JS error (the deferred re-centre read GPS.fix after it was gone).
#  2. A long GPS gap that is counted: marked (est, dashed grey line, a toast, «Без GPS (оценка)» in the ride), the solid
#     track is broken there; on a route being followed the gap is measured along the route.
#  3. Restoring a backup is all or nothing: a storage failure in the middle leaves rides, routes and settings as they were.
#  4. Another account signed in: the previous account's rides and routes are not listed and not put into a backup.
# Run: python3 tests/v150.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

FEED = """window.__fix = (lat, lon, t, spd) => onFix({ coords: { latitude: lat, longitude: lon, accuracy: 5, altitude: null, altitudeAccuracy: null, speed: spd, heading: 90 }, timestamp: t });"""

async def main():
    url = serve(8950); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url, m)
        await pg.evaluate(FEED)

        # ---- 1. collapse the panel, the fix disappears before the deferred re-centre ----
        log['errors'].clear()
        await pg.evaluate("""(() => { GPS.follow = true; if (!GPS.fix) __fix(32.09, 34.88, Date.now(), 0); setCompact(false); setCompact(true, true); GPS.fix = null; })()""")
        await pg.wait_for_timeout(300)
        check('panel collapsed while the GPS fix disappears: no JS error', not log['errors'], log['errors'])
        await pg.evaluate("setCompact(false, true)")

        # ---- 2. a counted GPS gap is marked ----
        r = await pg.evaluate("""(async () => {
          Ride.start(); const t0 = Date.now() + 1000; let lon = 34.88; const dLon = 5 / (111320 * Math.cos(32.09 * Math.PI / 180));
          for (let i = 0; i < 20; i++) { __fix(32.09, lon, t0 + i * 1000, 5); lon += dLon; }
          const before = Ride.dist; window.__lastToasts = '';
          // 2 minutes without GPS (screen locked), then 600 m further on: a plausible 5 m/s
          lon += dLon * 120; __fix(32.09, lon, t0 + 19000 + 121000, 5);
          for (let i = 1; i < 6; i++) { lon += dLon; __fix(32.09, lon, t0 + 140000 + i * 1000, 5); }
          return { before, after: Ride.dist, est: Ride.est, brk: Ride.brk.length, dashed: Ride.estLine ? Ride.estLine.getLatLngs().length : 0, toast: window.__lastToasts };
        })()""")
        e = r['est']
        check('the gap is recorded as an estimate (by straight line)', len(e) == 1 and e[0]['by'] == 'line' and 550 < e[0]['m'] < 650, e)
        check('the gap still counts in the distance', 550 < r['after'] - r['before'] < 700, round(r['after'] - r['before']))
        check('the solid track is broken at the gap, a dashed line drawn across it', r['brk'] >= 1 and r['dashed'] == 1, (r['brk'], r['dashed']))
        check('the rider is told', 'Не было GPS' in r['toast'] and 'по прямой' in r['toast'], r['toast'][-140:])
        await pg.evaluate("Ride.persist()")
        await pg.wait_for_timeout(200)
        kept = await pg.evaluate("(async () => ((await DB.get('kv', 'currentRide')) || {}).v.est)()")
        check('the mark survives a reload (kept with the unfinished ride)', kept and len(kept) == 1, kept)
        saved = await pg.evaluate("""(async () => { await Ride.stop(true); const r = Ride.lastSaved; await openRide(r.id); await new Promise(z => setTimeout(z, 400));
          return { est: r.est, row: document.querySelector('#rd-body').textContent }; })()""")
        check('the saved ride keeps the mark and shows «Без GPS (оценка)»', saved['est'] and 'Без GPS (оценка)' in saved['row'], (saved['est'], 'Без GPS' in saved['row']))
        await pg.evaluate("showTab('rec')")

        # along the route: a zigzag route, the gap from one end of it to the other
        al = await pg.evaluate("""(() => {
          const c = []; for (let i = 0; i <= 10; i++) c.push([32.09 + (i % 2 ? 0.002 : 0), 34.88 + i * 0.001, 0]);
          Nav.set({ name: 'zigzag', coords: c });
          const a = [c[0][0], c[0][1], null, 0], z = [c[10][0], c[10][1], null, 600000], d = hav(a, z);
          const m = gapAlong(a, z, d, 600000), off = gapAlong([32.2, 34.88, null, 0], z, d, 600000);
          Nav.stop && Nav.stop();
          return { d, m, total: Nav.route ? Nav.route.total : null, off };
        })()""")
        check('on a route the gap is measured along it (longer than the straight line)', al['m'] and al['m'] > al['d'] * 1.3, (round(al['d']), al['m'] and round(al['m'])))
        check('a gap end far from the route: no route measure (straight line)', al['off'] is None, al['off'])

        # ---- 3. restore: all or nothing ----
        base = await pg.evaluate("""(async () => {
          await DB.put('rides', { id: 'keep1', name: 'Было', start: 1, end: 2, type: 'bike', dist: 10, movingMs: 1, track: [[32,34,0,1],[32.001,34,0,2]] });
          lsSet('marker', 'old');
          return { rides: (await DB.all('rides')).map(r => r.id).sort(), routes: (await DB.all('routes')).length };
        })()""")
        bk = {'app': 'velokomp', 'ver': 2, 'ls': {'marker': '"new"'},
              'rides': [{'id': f'r{i}', 'name': f'R{i}', 'start': 10 + i, 'end': 20 + i, 'type': 'bike', 'dist': 100, 'movingMs': 1, 'track': [[32, 34, 0, 1], [32.001, 34, 0, 2]]} for i in range(5)],
              'routes': [{'id': f't{i}', 'name': f'T{i}', 'coords': [[32, 34, 0], [32.01, 34, 0]], 'dist': 1000, 'created': i} for i in range(3)]}
        # the phone's storage fails on the 4th write
        await pg.evaluate("""(() => { const P = IDBObjectStore.prototype, put = P.put; let n = 0; window.__unpatch = () => { P.put = put; };
          P.put = function (...a) { if (++n === 4) throw new DOMException('disk full', 'QuotaExceededError'); return put.apply(this, a); }; })()""")
        window_toasts = "window.__lastToasts = ''"
        await pg.evaluate(window_toasts)
        await pg.set_input_files('#bk-file', files=[{'name': 'velocomp-backup.json', 'mimeType': 'application/json', 'buffer': json.dumps(bk).encode()}])
        await pg.wait_for_timeout(700)
        await pg.evaluate("__unpatch()")
        aft = await pg.evaluate("""(async () => ({ rides: (await DB.all('rides')).map(r => r.id).sort(), routes: (await DB.all('routes')).length, marker: lsGet('marker', null), toast: window.__lastToasts }))()""")
        check('failure in the middle: no ride or route of the backup written', aft['rides'] == base['rides'] and aft['routes'] == base['routes'], (aft['rides'], aft['routes']))
        check('failure in the middle: settings untouched', aft['marker'] == 'old', aft['marker'])
        check('failure in the middle: the phone says nothing changed', 'ничего не изменилось' in aft['toast'] and 'места' in aft['toast'], aft['toast'][-160:])
        # settings refused by full storage: the old ones come back
        r3 = await pg.evaluate("""(async () => {
          lsSet('marker', 'old'); lsSet('marker2', 'old2');
          const S0 = Storage.prototype.setItem; let n = 0;
          Storage.prototype.setItem = function (k, v) { if (String(k).startsWith('velo:marker') && ++n === 2) throw new DOMException('full', 'QuotaExceededError'); return S0.call(this, k, v); };
          let res; try { res = await restoreBackup({ app: 'velokomp', ls: { marker: '"new"', marker2: '"new2"' }, rides: [], routes: [] }); } finally { Storage.prototype.setItem = S0; }
          return { res, m1: lsGet('marker', null), m2: lsGet('marker2', null) };
        })()""")
        check('settings refused half-way: the previous ones are put back', r3['res']['ns'] == -1 and r3['m1'] == 'old' and r3['m2'] == 'old2', r3)
        # and a good restore writes everything
        ok = await pg.evaluate("""(async (bk) => { bk.ls = {}; const res = await restoreBackup(bk); return { res, rides: (await DB.all('rides')).length, routes: (await DB.all('routes')).length }; })""" + f"({json.dumps(bk)})")
        check('a good backup: everything restored', ok['res']['nr'] == 5 and ok['res']['nt'] == 3 and ok['rides'] == len(base['rides']) + 5 and ok['routes'] == base['routes'] + 3, ok)
        bad = await pg.evaluate("(async () => { try { await restoreBackup({ app: 'other' }); return 'no error'; } catch (e) { return e.message; } })()")
        check('not a backup: refused', 'не резервная копия' in bad, bad)

        # ---- 4. another account signed in ----
        acc = await pg.evaluate("""(async () => {
          await DB.put('routes', { id: 'rtA', name: 'Маршрут А', coords: [[32.09,34.88,40],[32.1,34.89,60]], dist: 1500, created: 9 });
          await DB.put('rides', { id: 'rdA', name: 'Поездка А', start: 5, end: 6, type: 'bike', dist: 1500, movingMs: 6e5, track: [[32.09,34.88,40,5],[32.1,34.89,60,6]] });
          lsSet('syncOwn', { 'routes~rtA': 'uidA', 'rides~rdA': 'uidA' });
          lsSet('acct', { email: 'b@example.com', uid: 'uidB', idToken: 'x', refreshToken: 'y', exp: 0 });
          const routesB = (await DB.all('routes')).map(r => r.id), ridesB = (await DB.allStrict('rides')).map(r => r.id);
          const bkB = JSON.parse(await (await makeBackupFile()).text());
          lsSet('acct', { email: 'a@example.com', uid: 'uidA', idToken: 'x', refreshToken: 'y', exp: 0 });
          const routesA = (await DB.all('routes')).map(r => r.id);
          lsSet('acct', null);
          const routesOut = (await DB.all('routes')).map(r => r.id), still = !!(await DB.get('routes', 'rtA'));
          return { routesB, ridesB, bkRoutes: bkB.routes.map(r => r.id), bkRides: bkB.rides.map(r => r.id), routesA, routesOut, still };
        })()""")
        check('account B: A\'s route and ride not listed', 'rtA' not in acc['routesB'] and 'rdA' not in acc['ridesB'], (acc['routesB'], acc['ridesB']))
        check('account B: A\'s route and ride not in B\'s backup', 'rtA' not in acc['bkRoutes'] and 'rdA' not in acc['bkRides'], (acc['bkRoutes'], acc['bkRides']))
        check('account A again (or signed out): its route is back, nothing deleted', 'rtA' in acc['routesA'] and 'rtA' in acc['routesOut'] and acc['still'], (acc['routesA'], acc['routesOut']))

        check('no JS errors', not log['errors'], log['errors'])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed')
    sys.exit(0 if all(RES) else 1)

asyncio.run(main())
