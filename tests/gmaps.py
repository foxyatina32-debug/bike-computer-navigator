# Google Maps integration: key turning points in Google Maps links, import of any Google Maps link (short, place, pin),
# rider stops along the route (Places Nearby, «Заехать сюда»). Run: python3 tests/gmaps.py
import asyncio, sys, os, json, re
from urllib.parse import parse_qs, urlparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''))

async def main():
    url = serve(8783); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        # ---- module 2: turning points
        zig = await pg.evaluate("""(() => { const c = []; let la = 32.0, lo = 34.8;
          for (let k = 0; k < 14; k++) { for (let i = 0; i < 20; i++) { c.push([la, lo]); if (k % 2) la += 0.0005; else lo += 0.0005; } }
          c.push([la, lo]); return c; })()""")
        kp = await pg.evaluate('c => routeKeyPoints(c, 9)', zig)
        check('RDP: a route with 13 turns → at most 9 key points, in order', 1 <= len(kp) <= 9 and kp == sorted(kp, key=lambda x: zig.index(x)), len(kp))
        straight = await pg.evaluate("routeKeyPoints([[32,34.8],[32.001,34.801],[32.002,34.802],[32.003,34.803]], 9)")
        check('RDP: straight line → no extra points', straight == [], straight)
        corner = await pg.evaluate("routeKeyPoints([[32,34.8],[32.005,34.8],[32.01,34.8],[32.01,34.805],[32.01,34.81]], 9)")
        check('RDP: one corner → exactly the corner', corner == [[32.01, 34.8]], corner)
        u = await pg.evaluate('c => gmapsUrl(c[c.length - 1], c)', zig)
        q = parse_qs(urlparse(u).query); w = q.get('waypoints', [''])[0].split('|')
        check('Google Maps link: bicycling, ≤ 9 waypoints, starts at the route start when you are elsewhere', q['travelmode'] == ['bicycling'] and 2 <= len(w) <= 9 and w[0] == '32.000000,34.800000', f'{len(w)} waypoints')
        su = await pg.evaluate('c => shareGmaps(c)', zig); sq = parse_qs(urlparse(su).query)
        check('shared Google Maps link: origin, destination, ≤ 9 turning waypoints', sq['origin'] == ['32.000000,34.800000'] and 1 <= len(sq['waypoints'][0].split('|')) <= 9)

        # ---- module 3: any Google Maps link
        async def imp(link):
            return await pg.evaluate("l => routesFromInput(l).then(r => ({ name: r[0].name, a: r[0].coords[0], b: r[0].coords[r[0].coords.length - 1] }), e => ({ err: e.message }))", link)
        dir_full = 'https://www.google.com/maps/dir/32.09,34.88/32.1,34.9/@32.09,34.89,14z/data=!4m2!4m1!3e1'
        m.pages['api.allorigins.win/get'] = (json.dumps({'contents': '', 'status': {'url': dir_full, 'http_code': 200}}), 'application/json')
        r = await imp('https://maps.app.goo.gl/AbCdEf123')
        check('short maps.app.goo.gl → expanded, route through its points', 'err' not in r and abs(r['b'][0] - 32.1) < 1e-6 and abs(r['b'][1] - 34.9) < 1e-6, r)
        m.pages['api.allorigins.win/get'] = (json.dumps({'contents': '', 'status': {'url': 'https://consent.google.com/m?continue=' + dir_full.replace('/', '%2F').replace(':', '%3A').replace(',', '%2C').replace('!', '%21').replace('@', '%40')}}), 'application/json')
        r = await imp('https://maps.app.goo.gl/Consent1')
        check('short link behind the Google consent page → still expanded', 'err' not in r and abs(r['b'][0] - 32.1) < 1e-6, r)
        m.pages['api.allorigins.win/get'] = (json.dumps({'contents': '<html>no link</html>', 'status': {'url': 'https://maps.app.goo.gl/x'}}), 'application/json')
        m.pages['corsproxy.io'] = ('<html>nothing</html>', 'text/html')
        r = await imp('https://maps.app.goo.gl/Broken')
        check('short link that cannot be expanded → clear advice', 'скопируйте полную ссылку' in r.get('err', ''), r)
        del m.pages['corsproxy.io']
        m.pages['api.allorigins.win/get'] = (json.dumps({'contents': '<meta content="https://www.google.com/maps/place/X/@32.2,34.95,15z/data=!3m1!4b1!4m6!3m5!1s0:0!8m2!3d32.2071!4d34.9512">', 'status': {'url': 'https://maps.app.goo.gl/y'}}), 'application/json')
        r = await imp('https://maps.app.goo.gl/InPage')
        check('short link, final address only inside the page → found there', 'err' not in r and abs(r['b'][0] - 32.2071) < 1e-6, r)
        r = await imp('https://www.google.com/maps/place/%D7%A7%D7%A4%D7%94/@32.05,34.75,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d32.0712!4d34.7801!16s')
        check('place link: pin !3d/!4d (not the map centre @) → route from GPS to it', 'err' not in r and abs(r['a'][0] - 32.09) < 1e-3 and abs(r['b'][0] - 32.0712) < 1e-6 and abs(r['b'][1] - 34.7801) < 1e-6, r)
        r = await imp('https://maps.google.com/?q=32.11,34.85')
        check('?q=lat,lng → route to the point', 'err' not in r and abs(r['b'][0] - 32.11) < 1e-6 and abs(r['b'][1] - 34.85) < 1e-6, r)
        r = await imp('https://www.google.com/maps/@32.2,34.9,15z')
        check('only a map position @lat,lng → route to it', 'err' not in r and abs(r['b'][0] - 32.2) < 1e-6, r)
        r = await imp('https://www.google.com/maps/dir/Tel+Aviv/32.1,34.9/data=!4m6!4m5!1m2!1d34.7818!2d32.0853!1m0!3e1')
        check('A→B link with a named place still works (data !1d lon !2d lat)', 'err' not in r and abs(r['a'][0] - 32.0853) < 1e-4, r)

        # ---- module 4: rider stops
        await pg.evaluate("showRiderPOIs()"); await pg.wait_for_timeout(500)
        check('stops without a Google key → asks for the key', 'ключ Google с Places API' in await pg.evaluate("window.__lastToasts"))
        await pg.evaluate("lsSet('gkey', 'TEST-KEY'); Nav.set({ name: 'Тест', coords: [[32.09, 34.88], [32.13, 34.88]], noAsk: true }); setBase('ihm_mtb_he')")
        n0 = len([x for x in m.bodies if 'searchNearby' in x[0]])
        await pg.click('#t-gpx'); await pg.wait_for_timeout(300); await pg.click('#qa-poi')
        await pg.wait_for_function("RPOI.list.length > 0", timeout=10000)
        bodies = [x for x in m.bodies if 'searchNearby' in x[0]][n0:]
        types = bodies[0][2]['includedTypes'] if bodies else []
        check('stops along the route: several circles ahead, bike shop / store / gas / café', len(bodies) >= 2 and set(types) == {'bicycle_store', 'convenience_store', 'gas_station', 'cafe'} and bodies[0][1].get('x-goog-api-key') == 'TEST-KEY', f'{len(bodies)} requests')
        check('markers on the map, map switched to Google', await pg.evaluate("RPOI.layer && RPOI.layer.getLayers().length === RPOI.list.length && /^google/.test(baseKey)"), await pg.evaluate("RPOI.list.length"))
        p0 = await pg.evaluate("RPOI.list[0]")
        await pg.evaluate("RPOI.layer.getLayers()[0].openPopup()"); await pg.wait_for_timeout(200)
        pop = await pg.evaluate("document.querySelector('.leaflet-popup .pop').textContent")
        check('popup: name, type, distance, open now, «Заехать сюда»', p0['name'] in pop and 'км' in pop and 'Заехать сюда' in pop, pop[:120])
        await pg.click('.leaflet-popup [data-rp="via"]')
        await pg.wait_for_function("!RPOI.layer && Nav.route && Nav.route.name === 'Тест'", timeout=10000)
        near = await pg.evaluate("c => Math.min(...Nav.route.coords.map(x => hav(x, c)))", p0['ll'])
        end = await pg.evaluate("Nav.route.coords[Nav.route.coords.length - 1]")
        check('«Заехать сюда» → route goes via the stop to the same finish', near < 30 and abs(end[0] - 32.13) < 1e-6, f'{near:.0f} m from the stop')
        check('no JS errors', not log['errors'], log['errors'])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed')
    sys.exit(0 if all(RES) else 1)
asyncio.run(main())
