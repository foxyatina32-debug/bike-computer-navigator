# 3D view glue: button on the map and on a ride, MapLibre loaded on demand, satellite / map styles, route and fly-over.
# MapLibre itself is replaced by a stub here (no WebGL rendering in the test browser); real rendering is checked on the phone.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []; SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
STUB = """window.maplibregl = { Map: class { constructor(o) { this.o = o; this.src = {}; this.lay = []; this.cam = {}; this.h = {}; window.__ml = this; (window.__mls = window.__mls || []).push(this); setTimeout(() => this.h.load && this.h.load(), 30); }
  on(e, f) { this.h[e] = f; } addSource(id, s) { this.src[id] = s; } getSource(id) { const s = this.src[id]; return s && { setData: d => s.data = d }; } addLayer(l) { this.lay.push(l); }
  jumpTo(c) { Object.assign(this.cam, c); window.__jumps = (window.__jumps || 0) + 1; } easeTo(c) { Object.assign(this.cam, c); } getPitch() { return this.cam.pitch || 0; } getBearing() { return this.cam.bearing || 0; }
  cameraForBounds(b) { this.bounds = b; return { center: [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2], zoom: 14 }; } setSky(s) { this.sky = s; } remove() { this.removed = true; } } };"""
STYLE = json.dumps({'version': 8, 'sources': {'openmaptiles': {'type': 'vector', 'url': 'https://tiles.openfreemap.org/planet'}}, 'glyphs': 'x', 'layers': [
    {'id': 'background', 'type': 'background'}, {'id': 'water', 'type': 'fill', 'source': 'openmaptiles', 'source-layer': 'water'},
    {'id': 'road', 'type': 'line', 'source': 'openmaptiles', 'source-layer': 'transportation'}, {'id': 'label', 'type': 'symbol', 'source': 'openmaptiles', 'source-layer': 'place'}]})
ROUTE = [[32.09 + i * 0.001, 34.88 + (i % 5) * 0.0008, 20 + i] for i in range(30)]
async def main():
    url = serve(8772); m = Mocks()
    m.pages['maplibre-gl@5.24.0/dist/maplibre-gl.js'] = (STUB, 'application/javascript')
    m.pages['maplibre-gl@5.24.0/dist/maplibre-gl.css'] = ('', 'text/css')
    m.pages['tiles.openfreemap.org/styles/liberty'] = (STYLE, 'application/json')
    async with async_playwright() as p:
        for lang in ('ru', 'he'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, viewport=(375, 667) if lang == 'he' else (390, 844))
            vis = await pg.evaluate("!!document.getElementById('t-3d').offsetParent && !window.maplibregl")
            check(f'[{lang}] 3D button on the map; library not loaded until used', vis)
            await pg.evaluate("window.hasWebGLOrig = hasWebGL"); await pg.evaluate("hasWebGL = () => true; 0")
            await pg.click('#t-3d'); await pg.wait_for_function("window.__ml && document.getElementById('v3-load').hidden", timeout=8000)
            st = await pg.evaluate("({open: !document.getElementById('v3d').hidden, sat: __ml.o.style.layers.some(l => l.id === 'v3-sat'), terr: !!__ml.o.style.terrain, b3d: __ml.o.style.layers.some(l => l.type === 'fill-extrusion'), fills: __ml.o.style.layers.filter(l => l.type === 'fill' || l.type === 'line').every(l => l.layout && l.layout.visibility === 'none'), pitch: __ml.cam.pitch, fly: !document.getElementById('v3-fly').hidden, me: !!__ml.src['v3-me']})")
            check(f'[{lang}] opens: satellite, relief, 3D buildings, tilted camera; no route → no fly-over', st['open'] and st['sat'] and st['terr'] and st['b3d'] and st['fills'] and st['pitch'] >= 55 and not st['fly'] and st['me'], st)
            await pg.screenshot(path=os.path.join(SHOT, f'v3d-{lang}.png'))
            await pg.click('#v3-seg [data-s=map]'); await pg.wait_for_function("__mls.length === 2 && document.getElementById('v3-load').hidden", timeout=8000)
            st = await pg.evaluate("({sat: __ml.o.style.layers.some(l => l.id === 'v3-sat'), road: (__ml.o.style.layers.find(l => l.id === 'road').layout || {}).visibility !== 'none', old: __mls[0].removed, saved: lsGet('v3style')})")
            check(f'[{lang}] «Карта»: drawn map with roads, old view freed, choice remembered', not st['sat'] and st['road'] and st['old'] and st['saved'] == 'map', st)
            await pg.click('#v3-x'); check(f'[{lang}] close', await pg.evaluate("document.getElementById('v3d').hidden && __ml.removed"))
            await pg.evaluate(f"Nav.set({{name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true}})"); await pg.wait_for_timeout(300)
            await pg.click('#t-3d'); await pg.wait_for_function("__mls.length === 3 && document.getElementById('v3-load').hidden", timeout=8000)
            st = await pg.evaluate("({line: (__ml.src['v3-rt'].data.features[0] || {}).geometry, lay: __ml.lay.map(l => l.id), fly: !document.getElementById('v3-fly').hidden, b: __ml.bounds})")
            check(f'[{lang}] with a route: line, start/finish, camera on the route, fly-over button', st['line'] and len(st['line']['coordinates']) == 30 and 'v3-rt' in st['lay'] and 'v3-ends' in st['lay'] and st['fly'] and st['b'], {k: v for k, v in st.items() if k != 'line'})
            await pg.evaluate("window.__jumps = 0"); await pg.click('#v3-fly'); await pg.wait_for_timeout(800)
            fl = await pg.evaluate("({j: window.__jumps, z: __ml.cam.zoom, p: __ml.cam.pitch, t: document.getElementById('v3-fly').textContent})")
            await pg.click('#v3-fly'); check(f'[{lang}] fly-over moves the camera along the route and stops', fl['j'] > 10 and fl['p'] > 60 and not await pg.evaluate("V3.fly"), fl)
            await pg.click('#v3-x'); await pg.evaluate("Nav.stop()")
            if lang == 'ru':
                await pg.evaluate("DB.put('rides', {id: 'r3', name: 'T', start: Date.now() - 3600e3, end: Date.now(), type: 'bike', dist: 3000, movingMs: 900000, max: 6, asc: 10, desc: 10, track: " + json.dumps([[p[0], p[1], p[2], 1760000000000 + i * 5000] for i, p in enumerate(ROUTE)]) + "}).then(() => openRide('r3'))"); await pg.wait_for_timeout(800)
                await pg.click('#rd-3d'); await pg.wait_for_function("__mls.length === 4 && document.getElementById('v3-load').hidden", timeout=8000)
                check('ride page → 3D with the ride track', await pg.evaluate("__ml.src['v3-rt'].data.features[0].geometry.coordinates.length === 30"))
                await pg.click('#v3-x')
                await pg.evaluate("hasWebGL = () => false; 0"); await pg.click('#rd-3d'); await pg.wait_for_timeout(300)
                check('no WebGL → message, nothing opens', await pg.evaluate("document.getElementById('v3d').hidden && /3D/.test(window.__lastToasts || '')"))
                check('satellite map is in the free list now', await pg.evaluate("BASIC_BASES.includes('sat')"))
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
