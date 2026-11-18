# v135: car mode — a round speedometer on the map with the road's speed limit (OpenStreetMap maxspeed), red above the
# limit; and «🚦 Пробки»: Google's traffic layer over the Google map with the user's key (Map Tiles API, layerTraffic as
# an overlay). Not in bike / foot mode; the speedometer can be switched off; traffic leaves with the Google map.
# ru / he / en. Run: python3 tests/carspeed.py
import asyncio, sys, os, json, math
from urllib.parse import unquote_plus
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
LAT0, LON0 = 32.09, 34.88
M = 1 / 110540; KX = 1 / (111320 * math.cos(LAT0 * math.pi / 180))
def pt(n, e=0): return [LAT0 + n * M, LON0 + e * KX]
def way(i, tags, a, b): return {'type': 'way', 'id': i, 'tags': tags, 'geometry': [{'lat': a[0], 'lon': a[1]}, {'lat': b[0], 'lon': b[1]}]}
WAYS = [way(1, {'highway': 'primary', 'maxspeed': '60'}, pt(-500), pt(1500)),            # the road we drive north on
        way(2, {'highway': 'trunk', 'maxspeed': '90'}, pt(-500, 40), pt(1500, 40)),      # a parallel road 40 m east
        way(3, {'highway': 'residential', 'maxspeed': 'IL:urban'}, pt(2000, -500), pt(2000, 500))]   # a street going east
FIX = "([la, lo, spd, hdg, t]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 5, altitude: 30, altitudeAccuracy: 5, speed: spd, heading: hdg }, timestamp: t })"
SPD = "(() => { const e = document.getElementById('spdb'); return { shown: !e.hidden && !e.classList.contains('ovh'), v: document.getElementById('spdb-v').textContent, lim: document.getElementById('spdb-lim').hidden ? null : document.getElementById('spdb-lim').textContent, over: e.classList.contains('over') }; })()"

async def drive(pg, t0, n0, n1, spd, e=0, hdg=0, step=None):
    step = step or spd; out = None; n = n0; i = 0
    while n <= n1:
        la, lo = pt(n, e); await pg.evaluate(FIX, [la, lo, spd, hdg, t0 + i * 1000]); n += step; i += 1
    return t0 + i * 1000

async def setup(p, url, lang, sess):
    m = Mocks(); b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, geo=(LAT0, LON0))
    q = []
    async def ov(route):
        body = unquote_plus((route.request.post_data or '')[5:]); q.append(body)
        await route.fulfill(json={'elements': WAYS if body.startswith('/*sl*/') else []}, headers={'Access-Control-Allow-Origin': '*'})
    await ctx.route('**/api/interpreter', ov)
    async def cs(route):
        sess.append(json.loads(route.request.post_data or '{}')); await route.fulfill(json={'session': 'sess%d' % len(sess), 'expiry': '9999999999'}, headers={'Access-Control-Allow-Origin': '*'})
    await ctx.route('**/v1/createSession**', cs)
    await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)")
    return b, ctx, pg, log, q, m

async def main():
    url = serve(9069)
    async with async_playwright() as p:
        sess = []
        b, ctx, pg, log, q, m = await setup(p, url, 'ru', sess)
        await pg.evaluate("setMode('car', true)")
        t0 = await pg.evaluate("Date.now()")
        t = await drive(pg, t0, 0, 140, 14)
        await pg.wait_for_timeout(400)
        s = await pg.evaluate(SPD)
        check('car mode: the round speedometer shows 50 km/h, the road\'s limit «60» beside it', s['shown'] and s['v'] == '50' and s['lim'] == '60' and not s['over'], s)
        check('the limits came with one OpenStreetMap query for the square around', sum(1 for x in q if x.startswith('/*sl*/')) == 1, len(q))
        t = await drive(pg, t, 150, 400, 19.5)
        s = await pg.evaluate(SPD)
        check('70 km/h on a 60 road → the circle turns red', s['v'] == '70' and s['over'], s)
        t = await drive(pg, t, 410, 600, 17.5)
        s = await pg.evaluate(SPD)
        check('63 km/h: within the margin (+4) — not red', s['v'] == '63' and not s['over'], s)
        check('the parallel road 40 m away (90) is not taken', s['lim'] == '60', s)
        # turning onto the street going east (maxspeed IL:urban) → 50 after two fixes
        for i, e in enumerate(range(-300, 1, 12)):
            la, lo = pt(2000, e); await pg.evaluate(FIX, [la, lo, 12, 90, t + i * 1000])
        t += 40000
        s = await pg.evaluate(SPD)
        check('onto a street «IL:urban» (another square of the map) → its limit 50', s['lim'] == '50', s)
        u = await pg.evaluate("['50', '30 mph', 'IL:urban', 'IL:rural', 'none', 'signals'].map(maxspeedKmh)")
        check('limits read: 50 → 50, «30 mph» → 48, IL:urban → 50; IL:rural / none / signals → no sign', u == [50, 48, 50, None, None, None], u)
        geo = await pg.evaluate("(() => { const s = document.getElementById('spdb').getBoundingClientRect(), o = document.getElementById('t-sos').getBoundingClientRect(), h = document.getElementById('hud').getBoundingClientRect(); return { s: [s.left, s.top, s.bottom], sos: [o.top], hud: h.top }; })()")
        check('placed on the left, above SOS, clear of it and of the panel', geo['s'][0] < 30 and geo['s'][2] <= geo['sos'][0] - 4 and geo['s'][2] < geo['hud'], geo)
        await pg.evaluate("setMode('bike', true)")
        check('bike mode: no speedometer, no «🚦»', not (await pg.evaluate(SPD))['shown'] and await pg.evaluate("document.getElementById('t-traffic').hidden"))
        await pg.evaluate("setMode('car', true)"); await drive(pg, t, 620, 640, 14)
        await pg.evaluate("document.getElementById('s-spdb').click()")
        check('switched off in Settings → hidden', not (await pg.evaluate(SPD))['shown'])
        await pg.evaluate("document.getElementById('s-spdb').click()"); await drive(pg, t + 30000, 650, 670, 14)
        check('… and back on', (await pg.evaluate(SPD))['shown'])
        # traffic
        check('car mode: «🚦» on the map', await pg.evaluate("!document.getElementById('t-traffic').hidden"))
        await pg.evaluate("lsSet('gkey', '')"); await pg.click('#t-traffic'); await pg.wait_for_timeout(300)
        check('no Google key → says the key is needed, nothing switched on', 'Map Tiles API' in await pg.evaluate("window.__lastToasts") and not await pg.evaluate("Traffic.on"))
        await pg.evaluate("lsSet('gkey', 'TEST-KEY'); setBase('ihm_mtb_he')"); await pg.click('#t-traffic')
        await pg.wait_for_function("Traffic.layer && Traffic.layer._s", timeout=8000); await pg.wait_for_timeout(600)
        tb = [x for x in sess if x.get('layerTypes') == ['layerTraffic']]
        st = await pg.evaluate("({ base: baseKey, on: Traffic.on, layer: map.hasLayer(Traffic.layer), btn: document.getElementById('t-traffic').classList.contains('on'), tiles: [...document.querySelectorAll('img.leaflet-tile')].filter(i => /2dtiles/.test(i.src) && i.src.includes(Traffic.layer._s)).length })")
        check('«🚦» with a key → the Google map plus a traffic layer (Map Tiles API: layerTraffic, overlay)', st['base'].startswith('google') and st['on'] and st['layer'] and st['btn'] and tb and tb[0].get('overlay') is True and st['tiles'] > 0, (st, tb[:1]))
        await pg.evaluate("setBase('ihm_mtb_he')"); await pg.wait_for_timeout(200)
        check('another map chosen → traffic goes away (only on the Google map), said so', not await pg.evaluate("Traffic.on || map.hasLayer(Traffic.layer)") and 'только на карте Google' in await pg.evaluate("window.__lastToasts"))
        await pg.click('#t-traffic'); await pg.wait_for_timeout(300); await pg.evaluate("setMode('bike', true)")
        check('leaving car mode → traffic off, «🚦» hidden', not await pg.evaluate("Traffic.on") and await pg.evaluate("document.getElementById('t-traffic').hidden"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            sess = []; b, ctx, pg, log, q, m = await setup(p, url, lang, sess)
            await pg.evaluate("setMode('car', true); lsSet('gkey', '')"); t0 = await pg.evaluate("Date.now()"); await drive(pg, t0, 0, 100, 14)
            await pg.wait_for_timeout(3000); await pg.evaluate("trafficSet(true)"); await pg.wait_for_timeout(500)   # (no tap: a first tap asks for the compass, its message would cover this one)
            txt = await pg.evaluate("document.getElementById('toast').textContent + ' | ' + document.getElementById('s-spdb').parentElement.textContent + ' | ' + document.querySelector('#spdb small').textContent")
            cyr = [w for w in txt.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: the speedometer, the setting and the traffic message translated', not cyr and 'Map Tiles API' in txt and (await pg.evaluate(SPD))['shown'], (txt[:220], cyr[:4]))
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
