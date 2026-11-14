# Fly-over like Strava: «Пролёт» on a ride opens the 3D view and starts by itself; overview → swoop to the start →
# the camera follows a smoothed line (no shaking on a noisy GPS track), the ridden part lights up, a dot rides the track,
# distance / time / climb / elevation and a profile with a scrubber; pause, 1×/2×/4×, tap the map to pause, finish with
# a pull-back to the whole route, replay, stop. Without WebGL — a 2D fly-over on the ride's small map.
# MapLibre is a stub (no WebGL here): the test checks the camera and layer calls, real rendering is checked on the phone.
import asyncio, sys, os, json, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []; SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
STUB = """window.maplibregl = { Map: class { constructor(o) { this.o = o; this.src = {}; this.lay = []; this.cam = {}; this.h = {}; this.paint = {}; this.layout = {}; window.__ml = this; (window.__mls = window.__mls || []).push(this); window.__cams = []; setTimeout(() => this.h.load && this.h.load(), 30); }
  on(e, f) { this.h[e] = f; } addSource(id, s) { this.src[id] = s; } getSource(id) { const s = this.src[id]; return s && { setData: d => { s.data = d; s.sets = (s.sets || 0) + 1; } }; } addLayer(l) { this.lay.push(l); }
  jumpTo(c) { Object.assign(this.cam, c); window.__jumps = (window.__jumps || 0) + 1; window.__cams.push(JSON.parse(JSON.stringify(this.cam))); }
  easeTo(c) { Object.assign(this.cam, c); window.__eases = (window.__eases || []).concat([JSON.parse(JSON.stringify(c))]); }
  flyTo(c) { Object.assign(this.cam, c); window.__flys = (window.__flys || []).concat([JSON.parse(JSON.stringify(c))]); }
  stop() { window.__stops = (window.__stops || 0) + 1; } setPadding(p) { this.cam.padding = p; } areTilesLoaded() { return !window.__busy; }
  setPaintProperty(l, k, v) { this.paint[l + '.' + k] = v === undefined ? null : v; } setLayoutProperty(l, k, v) { this.layout[l + '.' + k] = v; }
  getPitch() { return this.cam.pitch || 0; } getBearing() { return this.cam.bearing || 0; }
  cameraForBounds(b, o) { this.bounds = b; return { center: [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2], zoom: 13 }; } setSky(s) { this.sky = s; } remove() { this.removed = true; } } };"""
STYLE = json.dumps({'version': 8, 'sources': {'openmaptiles': {'type': 'vector', 'url': 'https://tiles.openfreemap.org/planet'}}, 'glyphs': 'x', 'layers': [
    {'id': 'background', 'type': 'background'}, {'id': 'road', 'type': 'line', 'source': 'openmaptiles', 'source-layer': 'transportation'}]})
# A ~6 km ride: a big S-curve with GPS noise (±6 m every second), a 3-minute stop in the middle, climbing 0 → 120 m and down again.
random.seed(7)
TRACK = []; t = 1760000000000; lat0, lon0 = 32.08, 34.88
for i in range(1300):
    a = i / 1299; la = lat0 + a * 0.045; lo = lon0 + 0.012 * math.sin(a * 2 * math.pi)
    la += random.uniform(-1, 1) * 6 / 111000; lo += random.uniform(-1, 1) * 6 / 94000
    TRACK.append([round(la, 7), round(lo, 7), round(120 * math.sin(a * math.pi) + random.uniform(-2, 2), 1), t]); t += 1000
    if i == 650:
        for k in range(180): t += 1000; TRACK.append([TRACK[-1][0], TRACK[-1][1], TRACK[-1][2], t])
def _hav(a, b):
    la1, la2 = math.radians(a[0]), math.radians(b[0]); dl = math.radians(b[1] - a[1])
    return 2 * 6371008.8 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dl / 2) ** 2))
TOTAL_KM = sum(_hav(a, b) for a, b in zip(TRACK, TRACK[1:])) / 1000
async def main():
    url = serve(8781); m = Mocks()
    m.pages['maplibre-gl@5.24.0/dist/maplibre-gl.js'] = (STUB, 'application/javascript')
    m.pages['maplibre-gl@5.24.0/dist/maplibre-gl.css'] = ('', 'text/css')
    m.pages['tiles.openfreemap.org/styles/liberty'] = (STYLE, 'application/json')
    async with async_playwright() as p:
        for lang in ('ru', 'he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, viewport=(375, 667) if lang == 'he' else (390, 844))
            await pg.evaluate("hasWebGL = () => true; 0")
            await pg.evaluate("DB.put('rides', {id: 'fx1', name: 'T', start: 1760000000000, end: " + str(t) + ", type: 'bike', dist: 6000, movingMs: 1300000, max: 8, asc: 120, desc: 120, track: " + json.dumps(TRACK) + "}).then(() => openRide('fx1'))")
            await pg.wait_for_timeout(700)
            await pg.click('#rd-fly')
            await pg.wait_for_function("window.__ml && V3.fx && window.__flys", timeout=8000)
            st = await pg.evaluate("({open: !document.getElementById('v3d').hidden, ui: !document.getElementById('v3-fx').hidden, cls: document.getElementById('v3d').classList.contains('flying'), lm: __ml.src['v3-rt'].lineMetrics, fly: __flys[0], me: __ml.layout['v3-me.visibility'], phase: V3.fx.phase})")
            f0 = st['fly']; d0 = math.hypot((f0['center'][0] - TRACK[0][1]) * 94000, (f0['center'][1] - TRACK[0][0]) * 111000)
            check(f'[{lang}] «Пролёт» on a ride → 3D opens and the fly-over starts by itself: swoop to the start, tilted, rider low on the screen',
                  st['open'] and st['ui'] and st['cls'] and st['lm'] and st['phase'] == 'intro' and d0 < 30 and f0['pitch'] >= 55 and f0['padding']['top'] > 150 and f0['duration'] >= 2000 and st['me'] == 'none', {**st, 'd0': round(d0)})
            await pg.wait_for_function("V3.fx && V3.fx.phase === 'fly' && __jumps > 60", timeout=8000)
            await pg.wait_for_timeout(2500)
            cams = await pg.evaluate("__cams.slice(-150)")
            dbs = [abs(((c2['bearing'] - c1['bearing'] + 540) % 360) - 180) for c1, c2 in zip(cams, cams[1:])]
            dz = [abs(c2['zoom'] - c1['zoom']) for c1, c2 in zip(cams, cams[1:])]
            # camera centre path: distance between frames must vary smoothly (no jitter from the GPS noise)
            steps = [math.hypot((c2['center'][0] - c1['center'][0]) * 94000, (c2['center'][1] - c1['center'][1]) * 111000) for c1, c2 in zip(cams, cams[1:])]
            jerk = max(abs(s2 - s1) for s1, s2 in zip(steps, steps[1:])) if len(steps) > 2 else 99
            check(f'[{lang}] camera is smooth on a noisy track: turns ≤ 2.5°/frame, steady zoom, no jitter in movement',
                  len(cams) > 100 and max(dbs) <= 2.5 and max(dz) < .05 and jerk < 3, {'maxdb': round(max(dbs), 2), 'maxdz': round(max(dz), 3), 'jerk': round(jerk, 2), 'pitch': cams[-1]['pitch']})
            fx = await pg.evaluate("({d: V3.fx.d, total: V3.fx.P.total, grad: __ml.paint['v3-rt.line-gradient'], dot: __ml.src['v3-dot'].data.features.length, dist: document.getElementById('fx-d').textContent, time: document.getElementById('fx-t').textContent, tw: !document.getElementById('fx-tw').hidden, g: document.getElementById('fx-g').textContent, e: document.getElementById('fx-e').textContent, z: V3.fx.zoom, gs: V3.fx.gs})")
            check(f'[{lang}] ridden part lights up, the dot rides, distance / time / climb / elevation update',
                  fx['d'] > 50 and fx['grad'] and fx['grad'][0] == 'step' and 0 < fx['grad'][3] < .5 and fx['dot'] == 1 and float(fx['dist']) > 0 and fx['tw'] and ':' in fx['time'] and fx['e'] != '' and 13 < fx['z'] < 16.5, fx)
            # speed: real fly-over takes 20–70 s for 1×, not a dash at 0.5 km/s
            check(f'[{lang}] pace: ~160 m/s at zoom 15, whole ride 20–70 s', 20 <= fx['total'] / fx['gs'] <= 70, round(fx['total'] / fx['gs'], 1))
            # pause / resume
            await pg.click('#fx-play'); d1 = await pg.evaluate("V3.fx.d"); await pg.wait_for_timeout(600); d2 = await pg.evaluate("V3.fx.d")
            lab = await pg.evaluate("document.getElementById('fx-play').textContent")
            await pg.click('#fx-play'); await pg.wait_for_timeout(1500); d3 = await pg.evaluate("V3.fx.d")
            check(f'[{lang}] pause stops, ▶ continues', d1 == d2 and lab == '▶' and d3 > d2, (d1, d2, d3, lab))
            # 2× is faster
            r1 = await pg.evaluate("new Promise(r => { const a = V3.fx.d; setTimeout(() => r(V3.fx.d - a), 1000); })")
            await pg.click('#fx-spd'); await pg.wait_for_timeout(1200)
            r2 = await pg.evaluate("new Promise(r => { const a = V3.fx.d; setTimeout(() => r(V3.fx.d - a), 1000); })")
            check(f'[{lang}] 2× flies faster', r2 > r1 * 1.6 and await pg.evaluate("document.getElementById('fx-spd').textContent") == '2×', (round(r1), round(r2)))
            await pg.click('#fx-spd'); await pg.click('#fx-spd')
            # slow tiles → slows down instead of flying over blank ground
            await pg.evaluate("window.__busy = true"); await pg.wait_for_timeout(1200)
            r3 = await pg.evaluate("new Promise(r => { const a = V3.fx.d; setTimeout(() => r(V3.fx.d - a), 1000); })")
            await pg.evaluate("window.__busy = false")
            check(f'[{lang}] tiles still loading → slows down', r3 < r1 * .7, (round(r1), round(r3)))
            # tap the map → pause
            await pg.evaluate("document.getElementById('v3d-map').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}))")
            check(f'[{lang}] touching the map pauses', not await pg.evaluate("V3.fx.playing"))
            # scrub on the profile
            box = await pg.locator('#fx-prof').bounding_box()
            await pg.mouse.click(box['x'] + box['width'] * .5, box['y'] + box['height'] / 2)
            sc = await pg.evaluate("({f: V3.fx.d / V3.fx.P.total, grad: __ml.paint['v3-rt.line-gradient'][3]})")
            check(f'[{lang}] tap on the profile jumps there', abs(sc['f'] - .5) < .03 and abs(sc['grad'] - .5) < .03, sc)
            await pg.screenshot(path=os.path.join(SHOT, f'flyover-{lang}.png'))
            # finish
            await pg.evaluate("V3.fx.d = V3.fx.P.total - 15"); await pg.click('#fx-play')
            await pg.wait_for_function("V3.fx && V3.fx.phase === 'end'", timeout=6000); await pg.wait_for_timeout(900)
            en = await pg.evaluate("({grad: __ml.paint['v3-rt.line-gradient'], ease: (window.__eases || []).slice(-1)[0], btn: document.getElementById('fx-play').textContent, dist: document.getElementById('fx-d').textContent})")
            check(f'[{lang}] finish: whole route lit, camera pulls back to the whole route, ↻ to replay',
                  en['grad'][3] == 1 and en['ease'] and en['ease']['padding']['top'] == 0 and en['ease']['pitch'] <= 55 and en['btn'] == '↻' and abs(float(en['dist']) - TOTAL_KM) < .2, en)
            n = await pg.evaluate("__flys.length"); await pg.click('#fx-play'); await pg.wait_for_timeout(200)
            check(f'[{lang}] ↻ replays from the start', await pg.evaluate(f"__flys.length === {n + 1} && V3.fx.d === 0 && V3.fx.phase === 'intro'"))
            await pg.click('#fx-x')
            sp = await pg.evaluate("({fx: V3.fx, ui: document.getElementById('v3-fx').hidden, cls: document.getElementById('v3d').classList.contains('flying'), grad: __ml.paint['v3-rt.line-gradient'], pad: __ml.cam.padding, me: __ml.layout['v3-me.visibility'], dot: __ml.src['v3-dot'].data.features.length, bot: !!document.querySelector('.v3bot').offsetParent})")
            check(f'[{lang}] ✕ ends the fly-over: plain 3D back, line colour restored, no offset', sp['fx'] is None and sp['ui'] and not sp['cls'] and sp['grad'] is None and sp['pad']['top'] == 0 and sp['me'] == 'visible' and sp['dot'] == 0 and sp['bot'], sp)
            # ▶ Пролёт in 3D again, then close the whole 3D mid-flight
            await pg.click('#v3-fly'); await pg.wait_for_timeout(300)
            await pg.click('#v3-x'); await pg.wait_for_timeout(300)
            check(f'[{lang}] closing 3D during the fly-over stops everything', await pg.evaluate("V3.fx === null && document.getElementById('v3d').hidden"))
            if lang != 'ru':
                txt = await pg.evaluate("[...document.querySelectorAll('#v3-fx span, #v3-fx small')].map(e => e.textContent).join(' ') + ' ' + [...document.querySelectorAll('#v3-fx button')].map(e => e.getAttribute('aria-label')).join(' ')")
                check(f'[{lang}] fly-over panel translated', not any('Ѐ' <= ch <= 'ӿ' for ch in txt), txt)
            if lang == 'ru':
                await pg.evaluate("hasWebGL = () => false; 0"); await pg.click('#rd-fly'); await pg.wait_for_timeout(1500)
                tw = await pg.evaluate("({v3: document.getElementById('v3d').hidden, fly: !!RD.fly, dot: !!RD.dot, btn: document.getElementById('rd-fly').textContent})")
                await pg.click('#rd-fly')
                check('no WebGL → 2D fly-over on the ride map, ■ stops it', tw['v3'] and tw['fly'] and tw['dot'] and 'Стоп' in tw['btn'] and not await pg.evaluate("RD.fly"), tw)
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
