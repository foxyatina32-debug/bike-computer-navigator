# v116: «🎬 Видео пролёта» — the ride's 3D fly-over filmed as a video for WhatsApp. From «Поделиться поездкой»: 3D opens
# with a readable map canvas, waits for the map, films the whole fly-over (overview → swoop → flight → pull-back) into a
# 720×1280 video with the name, the numbers and the profile drawn over the map; «● Запись видео» while filming, no pause /
# speed buttons, touching the map doesn't pause; at the end — «🎬 Видео готово» with a preview and «📤 Отправить видео»
# (the phone's share menu with the video file). Leaving mid-film cancels it. Hebrew / English translated.
# MapLibre is a stub (its canvas is a plain canvas painted here); real 3D filming is checked on the phone.
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''), flush=True)
STUB = """window.maplibregl = { Map: class { constructor(o) { this.o = o; window.__mlopts = o; this.src = {}; this.lay = []; this.cam = {}; this.h = {}; this.paint = {}; this.layout = {}; window.__ml = this;
  this.cv = document.createElement('canvas'); this.cv.width = 390; this.cv.height = 844; setTimeout(() => this.h.load && this.h.load(), 30); }
  getCanvas() { const g = this.cv.getContext('2d'); g.fillStyle = `hsl(${(this.cam.bearing || 0) | 0},50%,40%)`; g.fillRect(0, 0, 390, 844); return this.cv; }
  on(e, f) { this.h[e] = f; } addSource(id, s) { this.src[id] = s; } getSource(id) { const s = this.src[id]; return s && { setData: d => { s.data = d; } }; } addLayer(l) { this.lay.push(l); }
  jumpTo(c) { Object.assign(this.cam, c); } easeTo(c) { Object.assign(this.cam, c); } flyTo(c) { Object.assign(this.cam, c); } stop() {} setPadding(p) { this.cam.padding = p; } areTilesLoaded() { return true; }
  setPaintProperty(l, k, v) { this.paint[l + '.' + k] = v; } setLayoutProperty(l, k, v) { this.layout[l + '.' + k] = v; } getPitch() { return this.cam.pitch || 0; } getBearing() { return this.cam.bearing || 0; }
  cameraForBounds(b) { return { center: [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2], zoom: 13 }; } setSky() {} remove() {} } };"""
STYLE = json.dumps({'version': 8, 'sources': {'openmaptiles': {'type': 'vector', 'url': 'https://tiles.openfreemap.org/planet'}}, 'glyphs': 'x', 'layers': [{'id': 'background', 'type': 'background'}]})
TRACK = []; t = 1760000000000
for i in range(400): a = i / 399; TRACK.append([32.08 + a * 0.02, 34.88 + 0.006 * math.sin(a * 6), round(50 + 60 * math.sin(a * math.pi), 1), t]); t += 1500
SHARE = "window.__shared = []; navigator.canShare = () => true; navigator.share = d => { window.__shared.push({ n: d.files[0].name, s: d.files[0].size, ty: d.files[0].type }); return Promise.resolve(); }; 0"
async def main():
    url = serve(8881); m = Mocks()
    m.pages['maplibre-gl@5.24.0/dist/maplibre-gl.js'] = (STUB, 'application/javascript'); m.pages['maplibre-gl@5.24.0/dist/maplibre-gl.css'] = ('', 'text/css')
    m.pages['tiles.openfreemap.org/styles/liberty'] = (STYLE, 'application/json')
    async with async_playwright() as p:
        for lang in ('ru', 'he'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            await pg.evaluate("hasWebGL = () => true; 0"); await pg.evaluate(SHARE)
            await pg.evaluate("DB.put('rides', {id: 'v1', name: 'T', start: 1760000000000, end: " + str(t) + ", type: 'bike', dist: 2300, movingMs: 590000, max: 8, asc: 60, desc: 60, track: " + json.dumps(TRACK) + "}).then(r => DB.get('rides', 'v1')).then(r => openRideShare(r))")
            await pg.wait_for_timeout(800)
            check(f'[{lang}] «🎬 Видео пролёта» in «Поделиться поездкой»', await pg.is_visible('#rs2-video') and await pg.evaluate("canRecord()"), await pg.evaluate("recMime()"))
            await pg.click('#rs2-video')
            await pg.wait_for_function("VREC.cur && V3.fx && V3.fx.rec", timeout=12000)
            st = await pg.evaluate("({pdb: !!(__mlopts.preserveDrawingBuffer && __mlopts.canvasContextAttributes.preserveDrawingBuffer), cls: document.getElementById('v3d').classList.contains('recording'), badge: getComputedStyle(document.getElementById('vrec-b')).display, play: getComputedStyle(document.getElementById('fx-play')).display, sh: document.getElementById('ask-rshare').hidden, w: VREC.cur.out.width, h: VREC.cur.out.height, mult: V3.fx.mult})")
            check(f'[{lang}] filming: readable map canvas, 720×1280, «● Запись видео», no pause/speed, share dialog closed', st['pdb'] and st['cls'] and st['badge'] == 'block' and st['play'] == 'none' and st['sh'] and st['w'] == 720 and st['h'] == 1280, st)
            await pg.wait_for_timeout(2500)
            await pg.evaluate("document.getElementById('v3d-map').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}))")
            check(f'[{lang}] touching the map does not pause the film', await pg.evaluate("!!V3.fx && (V3.fx.playing || V3.fx.phase === 'intro')"))
            px = await pg.evaluate("(() => { const g = VREC.cur.out.getContext('2d'); const a = g.getImageData(360, 600, 1, 1).data, b = g.getImageData(60, 60, 1, 1).data; return [Array.from(a), Array.from(b)]; })()")
            check(f'[{lang}] the film frame has the map and the overlay drawn', sum(px[0][:3]) > 60, px)
            await pg.evaluate("V3.fx.d = V3.fx.P.total - 30")
            await pg.wait_for_function("!document.getElementById('ask-vrec').hidden", timeout=30000)
            st = await pg.evaluate("({info: document.getElementById('vr-info').textContent, size: VREC.last.blob.size, ty: VREC.last.blob.type, name: VREC.last.name, rec: document.getElementById('v3d').classList.contains('recording'), src: !!document.getElementById('vr-video').src})")
            check(f'[{lang}] at the end — «🎬 Видео готово» with the preview, length and size', st['size'] > 2000 and st['src'] and not st['rec'] and ':' in st['info'] and st['name'].split('.')[-1] in ('mp4', 'webm'), st)
            await pg.click('#vr-send'); await pg.wait_for_timeout(400)
            sh = await pg.evaluate("window.__shared")
            check(f'[{lang}] «📤 Отправить видео» — the share menu gets the video file', len(sh) == 1 and sh[0]['ty'].startswith('video/') and sh[0]['s'] > 2000, sh)
            if lang == 'he':
                ui = await pg.evaluate("[...document.querySelectorAll('#ask-vrec h2, #ask-vrec button, #vrec-b')].map(e => e.textContent).join(' | ')")
                check('[he] the video dialog and the badge are translated', not any('Ѐ' <= ch <= 'ӿ' for ch in ui), ui)
            # cancel mid-film
            await pg.click('#vr-again'); await pg.wait_for_function("VREC.cur && V3.fx && V3.fx.rec", timeout=12000); await pg.wait_for_timeout(800)
            await pg.click('#v3-x'); await pg.wait_for_timeout(600)
            check(f'[{lang}] closing 3D mid-film cancels it — no video dialog, recorder gone', await pg.evaluate("VREC.cur === null && document.getElementById('ask-vrec').hidden && document.getElementById('v3d').hidden"))
            await pg.evaluate("openRideShare(null); 0")
            await pg.evaluate("DB.get('rides', 'v1').then(r => open3D(r.track))"); await pg.wait_for_timeout(1500)
            check(f'[{lang}] an ordinary 3D afterwards neither films nor keeps the canvas readable', await pg.evaluate("!__mlopts.preserveDrawingBuffer && VREC.cur === null"))
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
