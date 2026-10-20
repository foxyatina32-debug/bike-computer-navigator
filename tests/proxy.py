# Step 3: own Cloudflare Worker as the first proxy (public proxies as fallback). Run: python3 tests/proxy.py
import asyncio, sys, os, json, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
GPX = '<?xml version="1.0"?><gpx version="1.1"><trk><name>Вади Кельт</name><trkseg>' + ''.join(f'<trkpt lat="{31.84 + i*0.001}" lon="{35.4 + i*0.001}"><ele>{100+i}</ele></trkpt>' for i in range(30)) + '</trkseg></trk></gpx>'
def wk(req):
    u = urllib.parse.urlparse(req.url); q = urllib.parse.parse_qs(u.query)
    if u.path == '/health': return 200, {'ok': True, 'app': 'velocomp-worker', 'version': '1', 'strava': False}, {'Content-Type': 'application/json'}
    if u.path == '/' and 'url' in q:
        t = q['url'][0]
        if t == 'https://files.bikemap.net/route-1.gpx': return 200, GPX, {'Content-Type': 'application/gpx+xml', 'X-Final-URL': t}
        if t == 'https://maps.app.goo.gl/XyZ': return 200, '<html></html>', {'Content-Type': 'text/html', 'X-Final-URL': 'https://www.google.com/maps/dir/32.09,34.88/32.1,34.9/'}
    return 404, {'error': 'not_found'}, {}

async def main():
    url = serve(8781)
    async with async_playwright() as p:
        m = Mocks(); m.wk = wk; m.fail.add('https://files.bikemap.net/')   # the site blocks direct browser downloads
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=[['velo:pro', 'true']])
        await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(200)
        vis = await pg.evaluate("document.getElementById('wk-url').offsetParent !== null")
        await pg.fill('#wk-url', 'https://wk.test.workers.dev/'); await pg.click('#wk-save'); await pg.wait_for_timeout(800)
        st = await pg.evaluate("document.getElementById('wk-st').textContent"); saved = await pg.evaluate("lsGet('worker')")
        check('Pro: worker address checked and saved', vis and st.startswith('✓') and saved == 'https://wk.test.workers.dev', f'{st} · {saved}')
        await pg.evaluate("showTab('routes'); routeSeg('mine'); importInput('https://files.bikemap.net/route-1.gpx')"); await pg.wait_for_timeout(2500)
        r = await pg.evaluate("DB.all('routes').then(r => r.map(x => x.name))")
        via = [c for c in m.calls if 'wk.test.workers.dev/?url=' in c]
        check('blocked site → downloaded through own worker (no public proxy)', 'Вади Кельт' in ' '.join(r) and via and not any('corsproxy' in c or 'allorigins' in c for c in m.calls), f'{r}')
        await pg.evaluate("importInput('https://maps.app.goo.gl/XyZ')"); await pg.wait_for_timeout(3000)
        r2 = await pg.evaluate("DB.all('routes').then(r => r.map(x => x.name))")
        check('short Google link expanded by the worker', any('Google' in x for x in r2) and not any('allorigins' in c for c in m.calls), r2)
        await pg.evaluate("showTab('profile')"); await pg.fill('#wk-url', 'https://wk.test.workers.dev/nothing'); await pg.click('#wk-save'); await pg.wait_for_timeout(800)
        st2 = await pg.evaluate("document.getElementById('wk-st').textContent")
        check('wrong address → clear error, old one kept', st2.startswith('✗') and await pg.evaluate("lsGet('worker')") == 'https://wk.test.workers.dev', st2)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # no worker, proxies off → the old clear message
        m = Mocks(); m.fail.add('https://files.bikemap.net/')
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        msg = await pg.evaluate("fetchText('https://files.bikemap.net/route-1.gpx').then(() => 'ok', e => e.message)")
        check('no worker: message suggests the proxy option', 'прокси' in msg, msg[:90])
        # no worker, public proxies on → fallback chain used
        await pg.evaluate("S.urlProxy = true"); n0 = len(m.calls)
        await pg.evaluate("fetchText('https://files.bikemap.net/route-1.gpx').catch(() => 0)")
        check('fallback: public proxies when no worker', any('corsproxy.io' in c for c in m.calls[n0:]))
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
