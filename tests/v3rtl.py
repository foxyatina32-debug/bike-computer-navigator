# v134: Hebrew labels in the 3D view and the fly-over the right way round. MapLibre lays text out left to right by itself;
# without the right-to-left plugin every Hebrew name came out backwards. Now the plugin (@mapbox/mapbox-gl-rtl-text 0.3.0,
# the one MapLibre 5's docs name) is set up when MapLibre loads. Checked with the real MapLibre 5.24.0 and the real
# plugin (downloaded once from npm into tests/.cache): the 3D view asks for it and MapLibre reports it «loaded»; the
# plugin itself turns «תל אביב» into the order it is drawn in. Run: python3 tests/v3rtl.py
import asyncio, sys, os, json, subprocess, tarfile, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app, LIBS
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
NPM = os.path.join(LIBS, 'npm')
PKGS = {'maplibre': ('maplibre-gl', '5.24.0', ['dist/maplibre-gl.js', 'dist/maplibre-gl.css']), 'rtl': ('@mapbox/mapbox-gl-rtl-text', '0.3.0', ['dist/mapbox-gl-rtl-text.js'])}
def ensure():
    for key, (name, ver, files) in PKGS.items():
        d = os.path.join(NPM, key)
        if all(os.path.exists(os.path.join(d, f)) for f in files): continue
        os.makedirs(d, exist_ok=True)
        url = f'https://registry.npmjs.org/{name}/-/{name.split("/")[-1]}-{ver}.tgz'
        data = subprocess.run(['curl', '-sfL', '-m', '120', url], check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for f in files:
                os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
                open(os.path.join(d, f), 'wb').write(t.extractfile('package/' + f).read())
def body(key, f): return open(os.path.join(NPM, key, f), 'rb').read()
ROUTE = [[32.08 + i * 0.0005, 34.78, 20] for i in range(30)]
STYLE = {'version': 8, 'glyphs': 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf', 'sources': {'openmaptiles': {'type': 'vector', 'tiles': ['https://tiles.openfreemap.org/planet/{z}/{x}/{y}.pbf'], 'maxzoom': 14}},
         'layers': [{'id': 'bg', 'type': 'background', 'paint': {'background-color': '#ddd'}}]}

async def main():
    ensure()
    url = serve(9065); m = Mocks(); asked = []
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        async def lib(route):
            u = route.request.url
            if 'mapbox-gl-rtl-text@0.3.0' in u: asked.append(u); return await route.fulfill(body=body('rtl', 'dist/mapbox-gl-rtl-text.js'), content_type='application/javascript', headers={'Access-Control-Allow-Origin': '*'})
            if u.endswith('maplibre-gl.js'): return await route.fulfill(body=body('maplibre', 'dist/maplibre-gl.js'), content_type='application/javascript')
            if u.endswith('maplibre-gl.css'): return await route.fulfill(body=body('maplibre', 'dist/maplibre-gl.css'), content_type='text/css')
            return await route.fallback()
        await ctx.route('https://cdn.jsdelivr.net/npm/**', lib)
        await ctx.route('**/styles/liberty', lambda r: r.fulfill(json=STYLE, headers={'Access-Control-Allow-Origin': '*'}))
        gl = await pg.evaluate("hasWebGL()")
        check('this browser has WebGL (the 3D view can open)', gl)
        await pg.evaluate(f"open3D({json.dumps(ROUTE)})")
        try: await pg.wait_for_function("window.maplibregl && maplibregl.getRTLTextPluginStatus && maplibregl.getRTLTextPluginStatus() === 'loaded'", timeout=20000); st = 'loaded'
        except Exception: st = await pg.evaluate("window.maplibregl && maplibregl.getRTLTextPluginStatus ? maplibregl.getRTLTextPluginStatus() : 'no maplibre'")
        check('3D view (real MapLibre 5.24.0): the right-to-left plugin is requested once and reports «loaded»', st == 'loaded' and len(asked) >= 1 and all('@0.3.0/dist/mapbox-gl-rtl-text.js' in a for a in asked), (st, asked[:2]))
        await pg.evaluate("close3D()"); await pg.evaluate(f"open3D({json.dumps(ROUTE)})"); await pg.wait_for_timeout(1500)
        check('opening the 3D view again: no second setup, no errors', not log['errors'] and await pg.evaluate("maplibregl.getRTLTextPluginStatus()") == 'loaded', log['errors'][:2])
        await pg.evaluate("close3D()")
        # the plugin itself: logical order → the order the letters are drawn in (what MapLibre gets from it for a label)
        pg2 = await ctx.new_page()
        await pg2.goto(url + 'missing.html')
        await pg2.evaluate("""() => new Promise((ok, no) => { self.registerRTLTextPlugin = x => { window.__rtl = x; ok(); };
          const s = document.createElement('script'); s.src = 'https://cdn.jsdelivr.net/npm/@mapbox/mapbox-gl-rtl-text@0.3.0/dist/mapbox-gl-rtl-text.js'; s.onerror = no; document.head.appendChild(s); setTimeout(() => no('timeout'), 15000); })""")
        r = await pg2.evaluate("[window.__rtl.processBidirectionalText('תל אביב', []), window.__rtl.processBidirectionalText('רחוב הרצל 12', [])]")
        check('the plugin draws «תל אביב» as «ביבא לת» (right to left) — what MapLibre lacked', r[0] == ['ביבא לת'], r[0])
        check('… and keeps numbers readable: «רחוב הרצל 12» → «12 לצרה בוחר»', r[1] == ['12 לצרה בוחר'], r[1])
        await pg2.close()
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
