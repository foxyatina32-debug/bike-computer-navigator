# v153 audit — load and chaos. (1) A 4-hour ride: 14 400 fixes (a fix a second, 6 m/s, light noise) with navigation on:
# every fix is handled fast (no slowdown as the track grows), the distance is right, the ride saves and reopens. (2) The History
# with 300 rides of 2 000 points: it opens fast, in pages, without piling up memory. (3) Chaos: 400 taps on random visible
# buttons, chips and switches all over the app (every screen it reaches), in every language: no JS error.
# Run: python3 tests/stress153.py
import asyncio, sys, os, json, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

LONG = """(async n => {
  navigator.geolocation.clearWatch(GPS.watch); S.autopause = true;
  const coords = []; for (let i = 0; i < 400; i++) coords.push([32.0 + i * 0.002, 34.8 + Math.sin(i / 9) * 0.004, 30 + 20 * Math.sin(i / 30)]);
  Nav.set({ name: 'Длинный', coords, noAsk: true }); Ride.start();
  const cum = [0]; for (let i = 1; i < coords.length; i++) cum.push(cum[i - 1] + hav(coords[i - 1], coords[i]));
  const at = d => { let i = 1; while (i < cum.length - 1 && cum[i] < d) i++; const k = (d - cum[i - 1]) / (cum[i] - cum[i - 1]), A = coords[i - 1], B = coords[i]; return [A[0] + (B[0] - A[0]) * k, A[1] + (B[1] - A[1]) * k, A[2] + (B[2] - A[2]) * k]; };
  let s = 7; const r = () => (s = (s * 16807) % 2147483647) / 2147483647 - 0.5;
  const t0 = Date.now() + 1000, times = []; let d = 0;
  for (let i = 0; i < n; i++) {
    d = Math.min(cum[cum.length - 1] - 1, i * 6); const p = at(d), nx = r() * 3 / 94300, ny = r() * 3 / 110540;
    const a = performance.now();
    onFix({ coords: { latitude: p[0] + ny, longitude: p[1] + nx, accuracy: 5, altitude: p[2], altitudeAccuracy: 5, speed: 6, heading: 0 }, timestamp: t0 + i * 1000 });
    times.push(performance.now() - a);
    if (i % 600 === 0) await new Promise(res => setTimeout(res, 0));
  }
  const avg = a => a.reduce((x, y) => x + y, 0) / a.length, q = n / 10 | 0;
  return { want: Math.round(d), dist: Math.round(Ride.dist), pts: Ride.track.length, first: +avg(times.slice(0, q)).toFixed(2), last: +avg(times.slice(-q)).toFixed(2), max: +Math.max(...times.slice(10)).toFixed(1), mem: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e6) : 0 };
})"""
HIST = """(async () => {
  const now = Date.now();
  for (let k = 0; k < 300; k++) { const t0 = now - (k + 1) * 864e5, tr = []; for (let i = 0; i < 2000; i++) tr.push([32 + k * 1e-3 + i * 2e-5, 34.8 + (i % 13) * 1e-5, 30 + (i % 40), t0 + i * 1000]);
    await DB.raw.put('rides', { id: 'big' + k, name: 'Поездка ' + k, start: t0, end: t0 + 2e6, type: 'bike', dist: 8800, movingMs: 2e6, max: 8, asc: 40, desc: 40, track: tr }); }
  const m0 = performance.memory ? performance.memory.usedJSHeapSize : 0, a = performance.now();
  HS.per = 'all'; HS.seg = 'list'; HS.lim = 30; showTab('history'); await renderRides();
  const t1 = performance.now() - a;
  for (let i = 0; i < 3; i++) await renderRides();
  await new Promise(r => setTimeout(r, 500));
  return { open: Math.round(t1), cards: document.querySelectorAll('#ride-list .rideit').length, maps: HMAPS.length, grow: performance.memory ? Math.round((performance.memory.usedJSHeapSize - m0) / 1e6) : 0 };
})()"""
CLICKABLE = """(() => { const vis = el => { const r = el.getBoundingClientRect(); if (!r.width || !r.height || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) return false;
  for (let e = el; e && e.nodeType === 1; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity < 0.1 || e.hidden) return false; } return true; };
  const all = [...document.querySelectorAll('button, .chip, .seg button, [data-open], .item, label.chk, summary, a[data-k]')].filter(el => vis(el) && !el.disabled
    && !/app-off|ac-out|rdm-del|st-del|bk-exp|bk-imp|app-install|t-sos|sos-|rs2-share|ri-share|sb-gpx|st-file|rd-gpx|rdm-gpx|wk-|g-save|ac-|share|gpx|install|mail|tel:/.test((el.id || '') + ' ' + (el.className || '') + ' ' + (el.getAttribute('href') || '')));
  return all.map((el, i) => { el.dataset.monkey = i; return i; }).length; })()"""

async def main():
    url = serve(8943)
    async with async_playwright() as p:
        # ---- 1: a 4-hour ride
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.0, 34.8))
        await pg.wait_for_timeout(1200)
        r = await pg.evaluate(LONG + "(14400)")
        check('4-hour ride (14 400 fixes): the distance is right (±3 %)', abs(r['dist'] - r['want']) <= r['want'] * 0.03, r)
        check('…every fix handled fast and no slowdown as the track grows (avg < 3 ms, the last tenth < 2× the first + 1 ms)', r['last'] < 3 and r['last'] <= r['first'] * 2 + 1, r)
        ok = await pg.evaluate("(async () => { const s = await Ride.stop(true); const rd = Ride.lastSaved; await openRide(rd.id); return s && !!document.querySelector('#sheet-ride:not([hidden])') && rd.track.length > 1000; })()")
        check('…it saves and reopens', ok)
        check('no JS errors (long ride)', not log['errors'], log['errors'][:3])
        await b.close()
        # ---- 2: a big History
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.0, 34.8))
        await pg.wait_for_timeout(1200)
        h = await pg.evaluate(HIST)
        check('History with 300 rides of 2 000 points: opens in < 3 s, 30 cards, small maps not piling up', h['open'] < 3000 and h['cards'] == 30 and h['maps'] <= 30, h)
        check('no JS errors (big History)', not log['errors'], log['errors'][:3])
        await b.close()
        # ---- 3: chaos
        for lang in ('ru', 'he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), geo=(32.09, 34.88))
            pg.on('dialog', lambda d: asyncio.ensure_future(d.dismiss()))
            await pg.wait_for_timeout(1200)
            await pg.evaluate("""(async () => { const now = Date.now(); await DB.put('routes', { id: 'rtM', name: 'Маршрут М', coords: [[32.09,34.88,40],[32.095,34.885,50],[32.1,34.89,60]], dist: 1500, asc: 20, created: now, src: 'test', wpts: [] });
              await DB.put('rides', { id: 'rdM', name: 'Поездка М', start: now - 36e5, end: now, type: 'bike', dist: 1500, movingMs: 6e5, max: 8, asc: 20, desc: 20, track: [[32.09,34.88,40,now-36e5],[32.095,34.885,50,now-30e5],[32.1,34.89,60,now-24e5]] }); })()""")
            rnd = random.Random(11 + len(lang)); taps = 0; t_end = time.time() + 100
            while taps < 400 and time.time() < t_end:
                n = await pg.evaluate(CLICKABLE)
                if not n: await pg.evaluate("showTab(['rec', 'routes', 'history', 'profile'][Math.floor(Math.random() * 4)])"); continue
                k = rnd.randrange(n)
                try: await pg.evaluate(f"(() => {{ const el = document.querySelector('[data-monkey=\"{k}\"]'); if (el) el.click(); }})()")
                except Exception: pass
                taps += 1
                if taps % 25 == 0: await pg.evaluate("document.querySelectorAll('.ask:not([hidden])').forEach(a => a.hidden = true); showTab(['rec', 'routes', 'history', 'profile'][Math.floor(Math.random() * 4)])")
                await pg.wait_for_timeout(60)
            await pg.wait_for_timeout(800)
            errs = [e for e in log['errors'] if 'ResizeObserver' not in e]
            check(f'[{lang}] chaos: {taps} random taps all over the app — no JS error', not errs, errs[:4])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
