# QA harness for Velokomp: serves index.html from this repo with real Leaflet + leaflet-rotate,
# real Chromium (iPhone viewport, emulated GPS) and mocked external services (map tiles, BRouter, Overpass, Nominatim…).
import asyncio, http.server, threading, os, re, json, base64, sys
import subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SP = os.path.join(HERE, '.cache')          # served root: /libs/... lives here
LIBS = os.path.join(SP, 'libs')
CHROME = os.environ.get('CHROME_PATH', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
# 1x1 grey PNG used for every mocked map tile
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGPw9vYGAAHbAQe+ZeiyAAAAAElFTkSuQmCC')

def ensure_libs():
    # Leaflet 1.9.4 sources and leaflet-rotate 0.2.8, the same versions index.html loads from the CDN.
    os.makedirs(LIBS, exist_ok=True)
    for name, url, tag in [('leaflet-src', 'https://github.com/Leaflet/Leaflet', 'v1.9.4'), ('lr', 'https://github.com/Raruto/leaflet-rotate', 'v0.2.8')]:
        if not os.path.isdir(os.path.join(LIBS, name)):
            subprocess.run(['git', 'clone', '-q', '--depth', '1', '--branch', tag, url, os.path.join(LIBS, name)], check=True)

def app_html():
    src = open(REPO + '/index.html', encoding='utf-8').read()
    i = src.index('<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>')
    j = src.index('<script>', i); k = src.rindex('</script>')
    main = src[j + len('<script>'):k]
    loader = '''<script type="module">
import * as Lns from '/libs/leaflet-src/src/Leaflet.js';
window.L = Object.assign({}, Lns); for (const k of Object.keys(L)) if (L[k] && L[k][Symbol.toStringTag] === 'Module') L[k] = Object.assign({}, L[k]);
const add = src => new Promise((r, e) => { const s = document.createElement('script'); s.src = src; s.onload = r; s.onerror = e; document.body.appendChild(s); });
await add('/libs/lr/dist/leaflet-rotate.js');
await add('/__main.js');
{ const t = window.toast; window.__lastToasts = ''; window.toast = function (m, ms) { window.__lastToasts += m + ' | '; return t(m, ms); }; }
window.__appReady = true;
</script>'''
    html = src[:i] + loader + src[k + len('</script>'):]
    html = html.replace('https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css', '/libs/leaflet-src/dist/leaflet.css')
    return html, main

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=SP, **k)
    def log_message(s, *a): pass
    def translate_path(s, path):
        if path.startswith('/app/'): return os.path.join(REPO, path[5:].split('?')[0])
        fp = super().translate_path(path)
        if not os.path.exists(fp) and os.path.exists(fp + '.js'): return fp + '.js'
        return fp
    def _send(s, body, ctype):
        b = body.encode() if isinstance(body, str) else body
        s.send_response(200); s.send_header('Content-Type', ctype); s.send_header('Content-Length', str(len(b))); s.send_header('Cache-Control', 'no-store'); s.end_headers(); s.wfile.write(b)
    def do_GET(s):
        p = s.path.split('?')[0]
        if p in ('/app/', '/app/index.html'): return s._send(app_html()[0], 'text/html; charset=utf-8')
        if p == '/__main.js': return s._send(app_html()[1], 'text/javascript; charset=utf-8')
        if p.endswith('/package.json'): return s._send('export const version="1.9.4";', 'text/javascript')
        return super().do_GET()

def serve(port):
    ensure_libs()
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f'http://127.0.0.1:{port}/app/'

# ---- mocked external services (the real ones are not reachable from this sandbox) ----
class Mocks:
    def __init__(s): s.calls = []; s.fail = set(); s.brouter = None; s.overpass = None; s.pages = {}
    async def handle(s, route):
        u = route.request.url; s.calls.append(u)
        host = re.sub(r'^https?://([^/]+).*', r'\1', u)
        if '127.0.0.1' in host: return await route.continue_()
        if any(f in u for f in s.fail): return await route.abort('failed')
        if 'brouter.de' in u:
            if s.brouter: return await route.fulfill(json=s.brouter(u))
            ll = re.search(r'lonlats=([^&]+)', u).group(1).replace('%7C', '|')
            pts = [list(map(float, x.split(','))) for x in ll.split('|')]
            coords = []
            for a, b in zip(pts, pts[1:]):
                for t in range(10): coords.append([a[0] + (b[0]-a[0])*t/10, a[1] + (b[1]-a[1])*t/10, 50 + t])
            coords.append([pts[-1][0], pts[-1][1], 60])
            msgs = [["Longitude","Latitude","Elevation","Distance","CostPerKm","ElevCost","TurnCost","NodeCost","InitialCost","WayTags","NodeTags","Time","Energy"],
                    [str(pts[0][0]), str(pts[0][1]), "50", "1000", "0","0","0","0","0","highway=residential surface=asphalt","","0","0"]]
            return await route.fulfill(json={"type":"FeatureCollection","features":[{"type":"Feature","properties":{"track-length":"1000","filtered ascend":"10","messages":msgs},"geometry":{"type":"LineString","coordinates":coords}}]})
        if 'nominatim' in u:
            return await route.fulfill(json=[{"lat":"32.0853","lon":"34.7818","display_name":"Тель-Авив, Израиль","name":"Тель-Авив"}])
        if 'overpass' in u:
            return await route.fulfill(json=s.overpass(u) if s.overpass else {"elements": []})
        if 'routed-bike' in u:
            return await route.fulfill(json={"code":"Ok","routes":[{"distance":1500,"geometry":{"type":"LineString","coordinates":[[34.88,32.09],[34.89,32.095],[34.9,32.1]]},"legs":[{"steps":[]}]}]})
        for k, v in s.pages.items():
            if k in u: return await route.fulfill(body=v[0], content_type=v[1], headers={'Access-Control-Allow-Origin': '*'})
        if re.search(r'\.(png|jpg|jpeg)(\?|$)|/tile/|tiles?\.|Tiles/|mtbTiles|2dtiles', u):
            return await route.fulfill(body=PNG, content_type='image/png', headers={'Access-Control-Allow-Origin': '*'})
        return await route.fulfill(status=404, body='')

async def open_app(p, url, mocks, viewport=(390, 844), geo=(32.09, 34.88), storage=None, sw=False, locale='ru-RU'):
    b = await p.chromium.launch(executable_path=CHROME if os.path.exists(CHROME) else None)
    ctx = await b.new_context(viewport={'width': viewport[0], 'height': viewport[1]}, device_scale_factor=2, is_mobile=True, has_touch=True,
                              user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1',
                              geolocation={'latitude': geo[0], 'longitude': geo[1], 'accuracy': 5}, permissions=['geolocation'],
                              service_workers='allow' if sw else 'block', accept_downloads=True, locale=locale)
    if storage: await ctx.add_init_script('(' + json.dumps(storage) + ').forEach(([k,v])=>{ if(!localStorage.getItem(k)) localStorage.setItem(k,v) })')
    await ctx.route('**/*', mocks.handle)
    pg = await ctx.new_page()
    log = {'errors': [], 'console': []}
    pg.on('pageerror', lambda e: log['errors'].append(str(e)))
    pg.on('console', lambda m: log['console'].append((m.type, m.text)) if m.type in ('error', 'warning') else None)
    await pg.goto(url); await pg.wait_for_function('window.__appReady === true', timeout=20000); await pg.wait_for_timeout(800)
    return b, ctx, pg, log
