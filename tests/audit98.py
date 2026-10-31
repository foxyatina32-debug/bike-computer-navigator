# v98 audit fixes: a ride is never thrown away when saving fails; moving time without GPS is not counted (and a GPS gap
# is not counted twice); pieces of a track after a pause are not joined by a straight line (map, GPX); a backup with a
# read error is not reported as done; SOS says how old an old position is.
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))

# Fake clock + hand-fed fixes: T is "now", fx() feeds a fix east of the start at x metres.
SIM = """(() => { window.__T = Date.now(); const real = Date.now; Date.now = () => window.__T;
  window.__fx = (x, spd = 5) => { const f = {lat: 32.09, lon: 34.88 + x / 94400, acc: 5, alt: 50, altAcc: 5, spd, hdg: 90, t: window.__T, jump: false};
    GPS.fix = f; GPS.lastT = window.__T; Ride.onFix(f); };
  window.__sec = n => { for (let i = 0; i < n; i++) { window.__T += 1000; Ride.tick(); } };
  window.__ride = (secs, x0 = 0, v = 5) => { for (let i = 1; i <= secs; i++) { window.__T += 1000; window.__fx(x0 + i * v, v); Ride.tick(); } return x0 + secs * v; };
})()"""

async def main():
    url = serve(8798)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url, Mocks())
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); GPS.watch = -1")  # only hand-fed fixes from here
        await pg.evaluate(SIM)
        # ---- moving time: no GPS → nothing counted, «Жду GPS» ----
        st = await pg.evaluate("(() => { Ride.start(); GPS.lastT = 0; __sec(20); return {ms: Ride.movingMs, st: document.getElementById('hud-st').textContent}; })()")
        check('recording without any GPS: moving time stays 0, status says the track is not recorded', st['ms'] == 0 and 'Жду GPS' in st['st'], st)
        # ---- a 60-s GPS gap while riding on is counted once ----
        st = await pg.evaluate("""(() => { const x = __ride(10); const a = Ride.movingMs; __sec(60);
          const mid = {ms: Ride.movingMs, st: document.getElementById('hud-st').textContent};
          __T += 1000; __fx(x + 305); Ride.tick(); return {a, mid, ms: Ride.movingMs, st: document.getElementById('hud-st').textContent, brk: Ride.brk.length}; })()""")
        check('60 s without fixes: counted only the first ≤ 5 s while missing, «Жду GPS» shown', st['a'] <= st['mid']['ms'] <= st['a'] + 5000 and 'Жду GPS' in st['mid']['st'], st)
        check('…then ridden at a plausible pace: the gap counted once (≈71 s, not ≈130 s), line kept as one piece', 69000 <= st['ms'] <= 73000 and st['brk'] == 0 and st['st'] == 'Запись', st)
        # ---- manual pause → a separate piece on the map and in GPX ----
        st = await pg.evaluate("""(() => { Ride.pause(); __T += 120000; Ride.start(); const x = 2000; __ride(8, x);
          const ll = Ride.line.getLatLngs(); const g = toGpx('t', Ride.track, true, 'bike', Ride.brk);
          return {brk: Ride.brk.length, rings: Array.isArray(ll[0]) ? ll.length : 1, trkseg: (g.match(/<trkseg>/g) || []).length, pts: (g.match(/<trkpt/g) || []).length, n: Ride.track.length}; })()""")
        check('after a manual pause: a new piece — 2 lines on the map, 2 <trkseg> in GPX, no point lost', st['brk'] == 1 and st['rings'] == 2 and st['trkseg'] == 2 and st['pts'] == st['n'], st)
        # ---- emergency copy keeps the pieces ----
        await pg.evaluate("Ride.persist()"); await pg.wait_for_timeout(300)
        cur = await pg.evaluate("DB.get('kv', 'currentRide').then(c => ({brk: c.v.brk.length, n: c.v.track.length}))")
        check('emergency copy keeps the pieces', cur['brk'] == 1 and cur['n'] > 10, cur)
        # ---- saving fails → the ride is kept ----
        pg.once('dialog', lambda d: asyncio.ensure_future(d.dismiss()))
        st = await pg.evaluate("""(async () => { const put = DB.put; DB.put = (s, v) => s === 'rides' ? Promise.reject(new Error('quota')) : put.call(DB, s, v);
          const n = Ride.track.length, ok = await Ride.stop(true); DB.put = put;
          const cur = await DB.get('kv', 'currentRide');
          return {ok, status: Ride.status, n, kept: Ride.track.length, copy: !!(cur && cur.v && cur.v.track.length === n)}; })()""")
        check('save fails: ride not deleted — paused, track and emergency copy kept, GPX offered', st['ok'] is False and st['status'] == 'paused' and st['kept'] == st['n'] and st['copy'], st)
        st = await pg.evaluate("""(async () => { const ok = await Ride.stop(true); const rides = await DB.all('rides'); const r = rides[rides.length - 1];
          return {ok, status: Ride.status, saved: !!r, brk: r && r.brk && r.brk.length, copy: !!(await DB.get('kv', 'currentRide'))}; })()""")
        check('■ again: saved with its pieces, then cleared', st['ok'] and st['status'] == 'idle' and st['saved'] and st['brk'] == 1 and not st['copy'], st)
        # ---- saved ride: pieces on the map preview and in the detail mini-map series ----
        st = await pg.evaluate("""(async () => { const r = (await DB.all('rides')).pop(); preview(r.track, '#fff', r.brk);
          const ll = previewLayer.getLatLngs(), ser = rideSeries(r.track, r.brk), sg = speedSegments(ser) || [];
          return {rings: Array.isArray(ll[0]) ? ll.length : 1, flat: curRouteCoords().length === r.track.length, serBrk: ser.filter(s => s.brk).length}; })()""")
        check('saved ride: map preview in pieces, 3D/route tools still get all points, speed colours break at the pause', st['rings'] == 2 and st['flat'] and st['serBrk'] == 1, st)
        # ---- backup with a read error ----
        st = await pg.evaluate("""(async () => { lsSet('lastBackup', 0); window.__lastToasts = ''; const tx = DB.tx; DB.tx = function (s, m, fn) { return s === 'rides' ? Promise.reject(new Error('read')) : tx.call(DB, s, m, fn); };
          const ok = await saveBackup(); DB.tx = tx; return {ok, last: lsGet('lastBackup', 0), t: window.__lastToasts}; })()""")
        check('backup: a read error is reported, not a «successful» copy without rides', st['ok'] is False and st['last'] == 0 and 'Копия не сделана' in st['t'], st)
        # ---- SOS: age of an old position ----
        st = await pg.evaluate("""(() => { const g = GPS.good; GPS.good = {lat: 32.09, lon: 34.88, acc: 6, t: Date.now() - 5 * 60000}; const old = SOS.text();
          GPS.good = {lat: 32.09, lon: 34.88, acc: 6, t: Date.now() - 5000}; const fresh = SOS.text(); GPS.good = g; return {old, fresh}; })()""")
        check('SOS: an old position says «Последняя известная позиция … 5 мин назад»; a fresh one does not', 'Последняя известная позиция' in st['old'] and '5 мин назад' in st['old'] and 'Последняя' not in st['fresh'], st)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # ---- translations ----
        for lang, word in [('he', 'ממתין ל-GPS — המסלול לא נרשם'), ('en', 'Waiting for GPS — track not recorded')]:
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks())
            await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); GPS.watch = -1")
            await pg.evaluate(SIM); await pg.evaluate("Ride.start(); GPS.lastT = 0; __sec(3)"); await pg.wait_for_timeout(300)
            t = await pg.inner_text('#hud-st')
            check(f'{lang}: «no GPS» status translated', word in t, t)
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
