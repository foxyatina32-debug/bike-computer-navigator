# v140: the «where am I» card on the map — here / ahead ▲ / behind ▼ (settlement names in Hebrew). Here from the address
# server; ahead from the list of settlements (in the direction of travel, or along the route with the distance on it);
# behind after leaving a settlement. The list is kept on the phone: with the map servers and the address server out of
# reach the card still shows here (from the list), ahead and behind. The card is visible in «Как Google Maps» and in
# the other looks, not under the car speedometer. The rider marker in «Как Google Maps»: the arrow while moving.
# Run: python3 tests/places.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
FIX = "([la, lo, spd, hdg, t]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 6, altitude: 40, altitudeAccuracy: 5, speed: spd, heading: hdg }, timestamp: t })"
PT, RH = 'פתח תקווה', 'ראש העין'
def ovp(u):
    return {'elements': [
        {'type': 'node', 'lat': 32.09, 'lon': 34.88, 'tags': {'place': 'city', 'name': 'Petah Tikva', 'name:he': PT}},
        {'type': 'node', 'lat': 32.16, 'lon': 34.885, 'tags': {'place': 'town', 'name': RH}},
        {'type': 'node', 'lat': 32.09, 'lon': 34.80, 'tags': {'place': 'city', 'name': 'בני ברק'}}]}
CARD = """(() => { const w = document.getElementById('locw'), r = w.getBoundingClientRect(), cs = getComputedStyle(w), t = id => document.getElementById(id);
  return { vis: !w.hidden && cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.top >= 0 && r.bottom <= innerHeight, r: { t: r.top, b: r.bottom, l: r.left, r: r.right },
    cur: t('locw-cur').textContent, nx: t('locw-nx').hidden ? null : t('locw-nx-n').textContent, nxd: t('locw-nx').hidden ? null : t('locw-nx-d').textContent,
    pv: t('locw-pv').hidden ? null : t('locw-pv-n').textContent }; })()"""
def apart(a, b): return a['b'] <= b['t'] + 1 or b['b'] <= a['t'] + 1 or a['r'] <= b['l'] + 1 or b['r'] <= a['l'] + 1
ROUTE = [[32.09 + i * 0.001, 34.88 + i * 0.00007, 30] for i in range(80)]

async def ride(pg, t0, la0, n, step=5, spd=5):
    for i in range(n): await pg.evaluate(FIX, [la0 + i * step / 110540, 34.88, spd, 0, t0 + i * 1000]); await pg.wait_for_timeout(40)

async def main():
    url = serve(9089)
    async with async_playwright() as p:
        # ---------- the servers answer
        m = Mocks(); m.overpass = ovp; rev = {'fail': False}
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=[['velo:settings', json.dumps({'theme': 'md'})]])
        async def reverse(route):
            if rev['fail']: return await route.abort('failed')
            la = float(route.request.url.split('lat=')[1].split('&')[0])
            a = {'city': PT} if la < 32.12 else {} if la < 32.15 else {'town': RH}
            await route.fulfill(json={'address': a}, headers={'Access-Control-Allow-Origin': '*'})
        await pg.route('**/nominatim.openstreetmap.org/reverse**', reverse)
        oq = []
        async def interp(route):   # the server stopped at its time limit, but sent what it found — still used
            from urllib.parse import unquote_plus
            q = unquote_plus((route.request.post_data or '')[5:]); oq.append(q)
            j = ovp('') if 'place' in q else {'elements': []}
            if 'place' in q: j['remark'] = 'runtime error: Query timed out in "query" at line 1 after 26 seconds.'
            await route.fulfill(json=j, headers={'Access-Control-Allow-Origin': '*'})
        await pg.route('**/api/interpreter*', interp)
        # what the app fetched at the start (before these answers were set up) is forgotten
        await pg.evaluate("Places.list = null; Places.listAt = null; Places.listT = 0; Places.cur = null; Places.prev = null; localStorage.removeItem('velo:placeList'); localStorage.removeItem('velo:placePrev'); 0")
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)"); t0 = await pg.evaluate("Date.now()")
        await pg.evaluate(FIX, [32.09, 34.88, 0, None, t0]); await pg.wait_for_timeout(300)
        st = await pg.evaluate("(() => { const e = meMarker.getElement(); return { dot: !!e.querySelector('.gdot .gc'), arr: !!e.querySelector('.me-arr') }; })()")
        check('«Как Google Maps», standing, no direction: the blue dot', st['dot'] and not st['arr'], st)
        await ride(pg, t0 + 1000, 32.09, 25); await pg.wait_for_timeout(1500)
        await pg.evaluate("Places.onFix(GPS.fix, true)"); await pg.wait_for_timeout(500)
        st = await pg.evaluate("(() => { const e = meMarker.getElement(), a = e.querySelector('svg.me-arr'); return { dot: !!e.querySelector('.gdot'), rot: a ? a.style.transform : '', fill: a ? a.querySelector('path').getAttribute('fill') : '' }; })()")
        check('…riding: the arrow (Google\'s blue) shows where you are going', not st['dot'] and st['rot'].startswith('rotate(') and st['fill'] == '#1a73e8', st)
        c = await pg.evaluate(CARD)
        check('the card: here (the address server)', c['vis'] and c['cur'] == PT, c)
        check('…ahead ▲ — the next settlement in the direction of travel, with the distance', c['nx'] == RH and c['nxd'].startswith('~') and 'км' in c['nxd'], c)
        cache = await pg.evaluate("lsGet('placeList', null)")
        check('the list of settlements is kept on the phone', cache and len(cache['list']) == 3 and all(len(x['ll']) == 2 for x in cache['list']), cache and len(cache['list']))
        pq = [q for q in oq if 'place' in q]
        check('…the query asks for settlement points (light for the server); a partial answer is used', pq and all(q.count('node[') == 1 and 'nwr[' not in q and 'way[' not in q for q in pq), pq[:1])
        await pg.evaluate(FIX, [32.13, 34.88, 5, 0, t0 + 40000]); await pg.evaluate("Places.onFix(GPS.fix, true)"); await pg.wait_for_timeout(500)
        c = await pg.evaluate(CARD)
        check('between settlements: «מחוץ ליישוב», behind ▼ the one left', c['vis'] and c['cur'] == 'מחוץ ליישוב' and c['pv'] == PT and c['nx'] == RH, c)
        await pg.evaluate(FIX, [32.158, 34.885, 5, 0, t0 + 80000]); await pg.evaluate("Places.onFix(GPS.fix, true)"); await pg.wait_for_timeout(500)
        c = await pg.evaluate(CARD)
        check('in the next one: here it, behind the previous', c['cur'] == RH and c['pv'] == PT, c)
        # along a route: the distance on the route, no «~»
        await pg.evaluate(FIX, [32.09, 34.88, 5, 0, t0 + 120000]); await pg.evaluate("Places.onFix(GPS.fix, true)"); await pg.wait_for_timeout(400)
        await pg.evaluate(f"Nav.set({{ name: 'Север', coords: {json.dumps(ROUTE)}, noAsk: true }})"); await pg.wait_for_timeout(300)
        await ride(pg, t0 + 121000, 32.09, 6); await pg.evaluate("Places.onFix(GPS.fix, true)"); await pg.wait_for_timeout(400)
        c = await pg.evaluate(CARD)
        check('navigating: ahead — the settlement on the route, the distance along it', c['vis'] and c['nx'] == RH and not c['nxd'].startswith('~'), c)
        await pg.evaluate("Nav.stop()"); await pg.wait_for_timeout(300)
        # the address server stops answering: here from the list
        rev['fail'] = True
        await pg.evaluate(FIX, [32.159, 34.885, 5, 0, t0 + 200000]); await pg.evaluate("Places.lastQT = 0; Places.onFix(GPS.fix, true)"); await pg.wait_for_timeout(600)
        c = await pg.evaluate(CARD)
        check('the address server silent: here from the kept list', c['vis'] and c['cur'] == RH, c)
        # car mode: the speedometer is not over the card
        await pg.evaluate(FIX, [32.09, 34.88, 5, 0, t0 + 260000]); await pg.evaluate("Places.onFix(GPS.fix, true); setMode('car', true)")
        await ride(pg, t0 + 261000, 32.09, 5, 14, 14); await pg.evaluate("placeGpxBtn()"); await pg.wait_for_timeout(300)
        c = await pg.evaluate(CARD); sp = await pg.evaluate("(() => { const e = document.getElementById('spdb'), r = e.getBoundingClientRect(); return e.hidden || getComputedStyle(e).display === 'none' ? null : { t: r.top, b: r.bottom, l: r.left, r: r.right }; })()")
        check('car mode: the card visible, the speedometer not over it', c['vis'] and (sp is None or apart(c['r'], sp)), (c['r'], sp))
        await pg.evaluate("setMode('bike', true)")
        check('no JS errors', not log['errors'], log['errors'][:3])
        saved = await pg.evaluate("localStorage.getItem('velo:placeList')")
        await b.close()
        # ---------- a new start, both servers out of reach: the kept list does the job
        m2 = Mocks(); m2.fail.add('overpass'); m2.fail.add('nominatim')
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m2, storage=[['velo:settings', json.dumps({'theme': 'dark'})], ['velo:placeList', saved]])
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)"); t0 = await pg.evaluate("Date.now()")
        await ride(pg, t0, 32.09, 25); await pg.wait_for_timeout(1500); await pg.evaluate("Places.onFix(GPS.fix, true)"); await pg.wait_for_timeout(500)
        c = await pg.evaluate(CARD)
        check('servers out of reach: here from the kept list (another look)', c['vis'] and c['cur'] == PT, c)
        check('…ahead from the kept list', c['nx'] == RH, c)
        await pg.evaluate(FIX, [32.159, 34.885, 5, 0, t0 + 60000]); await pg.evaluate("Places.onFix(GPS.fix, true)"); await pg.wait_for_timeout(500)
        c = await pg.evaluate(CARD)
        check('…and behind after leaving', c['cur'] == RH and c['pv'] == PT, c)
        check('the usual arrow in the other looks', await pg.evaluate("!meMarker.getElement().querySelector('.gdot') && meMarker.getElement().querySelector('svg.me-arr path').getAttribute('fill') === ME_BLUE"))
        check('no JS errors (servers out of reach)', not log['errors'], log['errors'][:3])
        await b.close()
        # ---------- a kept list from far away is not used
        far = json.loads(saved); far['at'] = [31.25, 34.79]; far['list'] = [{'name': 'באר שבע', 'kind': 'city', 'll': [31.25, 34.79]}]
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m2, storage=[['velo:settings', json.dumps({'theme': 'md'})], ['velo:placeList', json.dumps(far)]])
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)"); t0 = await pg.evaluate("Date.now()")
        await ride(pg, t0, 32.09, 10); await pg.evaluate("Places.onFix(GPS.fix, true)"); await pg.wait_for_timeout(400)
        check('a list kept far away (Beersheba) is not used here', await pg.evaluate("!Places.list && document.getElementById('locw').hidden"))
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
