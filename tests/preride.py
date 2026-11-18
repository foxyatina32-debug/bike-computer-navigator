# v130: «Перед выездом», ориентиры в подсказках поворотов, остановки одним нажатием.
# «Перед выездом»: a route started by the rider (≥ 2 km, not riding yet) → a card: length, climb, time, arrival; sunset vs
#   arrival; the weather for the hours of the ride (heat, headwind, UV); water on the way + how much to take; hard places
#   (steps…); surface. «➕ Заехать» adds water / café as stops: the route keeps its shape, several stops one after another.
#   Not for short routes, the car, reroutes, when switched off or while riding; closes by itself once moving; waits for
#   the «you are not on the route» question. Landmarks: «у светофора поверните направо», «после моста…», only at the turn
#   it belongs to. «Что по пути» without a Google key: OpenStreetMap water / cafés / stores along the route, «➕ Заехать сюда».
# Overpass, Open-Meteo and the sun are fixtures. ru / he / en. Run: python3 tests/preride.py
import asyncio, sys, os, json, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
LAT0, LON0 = 32.09, 34.88
M = 1 / 110540; KX = 1 / (111320 * math.cos(LAT0 * math.pi / 180))
def pt(n, e): return [round(LAT0 + n * M, 7), round(LON0 + e * KX, 7)]
# 3 km north, a right turn, 3 km east
ROUTE = [pt(n, 0) for n in range(0, 3001, 50)] + [pt(3000, e) for e in range(50, 3001, 50)]
W1, CAFE, W2 = pt(1000, 120), pt(2500, -80), pt(3020, 1500)
def node(ll, **t): return {'type': 'node', 'lat': ll[0], 'lon': ll[1], 'tags': t}
INS = [{'type': 'way', 'tags': {'highway': 'residential', 'surface': 'asphalt'}, 'geometry': [{'lat': c[0], 'lon': c[1]} for c in ROUTE]},
       node(W1, amenity='drinking_water'), node(CAFE, amenity='cafe', name='Кафе Тест'), node(W2, amenity='drinking_water')]
RA = [node(pt(2000, 0), highway='steps'), node(pt(2995, 0), highway='traffic_signals')]
RP = [node(pt(1500, 50), amenity='drinking_water'), node(pt(2200, -60), amenity='cafe', name='Cafe Rpoi'), node(pt(2600, 40), shop='convenience', name='Minimarket'), node(pt(2700, 0), amenity='bench')]
FIX = """([INS, RA, RP, CORNER]) => {
  window.__q = []; window.__said = []; window.CORNER = CORNER;
  window.overpass = async q => { window.__q.push(q); if (q.startsWith('/*ra*/')) return { elements: RA }; if (q.startsWith('/*rpoi*/')) return { elements: RP };
    if (q.includes('shelter')) return { elements: INS }; return { elements: [] }; };
  try { speechSynthesis.speak = u => window.__said.push(u.text); speechSynthesis.cancel = () => {}; } catch {}
  // the sun sets 20 min from now: a 6 km ride (≈ 25 min) ends after it
  window.sunTimes = () => ({ rise: new Date(Date.now() - 5 * 3600000), set: new Date(Date.now() + 20 * 60000) });
}"""
async def forecast(route):
    now = int(time.time()) // 3600 * 3600 - 7200; n = 48
    h = {'time': [now + k * 3600 for k in range(n)], 'temperature_2m': [31] * n, 'apparent_temperature': [35] * n, 'precipitation_probability': [10] * n,
         'weather_code': [1] * n, 'wind_speed_10m': [22] * n, 'wind_direction_10m': [0] * n, 'uv_index': [9] * n}
    await route.fulfill(json={'hourly': h}, headers={'Access-Control-Allow-Origin': '*'})
SHOWN = "!document.getElementById('ask-pre').hidden"
PL = "document.getElementById('pre-list').textContent"

async def start(p, url, m, lang):
    b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, geo=(LAT0, LON0))
    await ctx.route('**/v1/forecast**', forecast)
    await pg.evaluate(FIX, [INS, RA, RP, ROUTE[60]])
    await pg.evaluate("S.preRide = true; saveS(); setMode('bike', true); lsSet('gkey', '')")
    return b, ctx, pg, log

async def main():
    url = serve(9041); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await start(p, url, m, 'ru')
        # ---------- 1. the card
        await pg.evaluate(f"Nav.set({{ name: 'Тестовый', coords: {json.dumps(ROUTE)} }})")
        try: await pg.wait_for_function(SHOWN, timeout=8000); shown = True
        except Exception: shown = False
        check('a route started by the rider → «Перед выездом»', shown)
        await pg.wait_for_function(f"{PL}.includes('Вода по пути') && {PL}.includes('Жара')", timeout=10000)
        sm = await pg.evaluate("document.getElementById('pre-sum').textContent"); tx = await pg.evaluate(PL)
        check('summary: name, length, time, arrival', 'Тестовый' in sm and '6.0' in sm and 'прибытие' in sm, sm)
        check('sunset before the arrival → «приедете … после заката», take lights', '🌇' in tx and 'после заката' in tx and 'фонари' in tx, tx[:200])
        check('weather for the ride: heat 35° by feel, headwind 22 km/h (the first half goes into the wind), UV 9', 'Жара до 35°' in tx and 'Встречный ветер до 22 км/ч' in tx and 'УФ-индекс 9' in tx, tx)
        check('water: 2 points, the first in 1 km, how much to take', 'Вода по пути: 2 точки, первая через 1.0' in tx and 'л воды' in tx, tx)
        check('hard places: the steps on the route', 'По пути: лестница' in tx, tx)
        check('surface: asphalt 100%', 'Асфальт 100%' in tx, tx)
        st = await pg.evaluate("document.getElementById('pre-stops').innerText")
        check('«Заехать по пути»: water, café, water — each with «➕ Заехать»', st.count('➕ Заехать') == 3 and 'Кафе Тест' in st, st.replace('\n', ' | '))
        # ---------- 2. stops one tap each: the route keeps its shape
        await pg.click('#pre-stops [data-pst="0"]')
        await pg.wait_for_function("Nav.wpts.length === 1", timeout=10000)
        r1 = await pg.evaluate(f"(() => {{ const c = Nav.route.coords, near = q => Math.min(...c.map(x => hav(x, q))); return {{ w1: near({W1}), end: hav(c[c.length - 1], {ROUTE[-1]}), st: hav(c[0], {ROUTE[0]}), corner: near({ROUTE[60]}), total: Nav.route.total }}; }})()")
        check('«➕ Заехать» water → the route goes by it, start / turn / finish kept', r1['w1'] < 30 and r1['end'] < 1 and r1['st'] < 1 and r1['corner'] < 5, r1)
        await pg.wait_for_function("document.getElementById('pre-stops').textContent.includes('✓ В маршруте')", timeout=5000)
        check('the card stays open and marks it «✓ В маршруте»', await pg.evaluate(SHOWN))
        await pg.click('#pre-stops [data-pst="1"]')
        await pg.wait_for_function("Nav.wpts.length === 2", timeout=10000)
        r2 = await pg.evaluate(f"(() => {{ const c = Nav.route.coords, near = q => Math.min(...c.map(x => hav(x, q))); return {{ w1: near({W1}), cafe: near({CAFE}), names: Nav.wpts.map(w => w.name), end: hav(c[c.length - 1], {ROUTE[-1]}) }}; }})()")
        check('a second stop: both on the route, in their order, finish kept', r2['w1'] < 30 and r2['cafe'] < 30 and r2['names'] == ['Вода', 'Кафе Тест'] and r2['end'] < 1, r2)
        dup = await pg.evaluate(f"addStop({{ ll: {W1}, name: 'Вода' }})")
        check('the same stop again → «уже в маршруте», nothing changes', dup is False and 'уже в маршруте' in await pg.evaluate("window.__lastToasts") and await pg.evaluate("Nav.wpts.length") == 2)
        # ---------- 3. landmark from the road features: lights at the turn
        lm = await pg.evaluate("""(() => { const r = Nav.route, al = nearOn(r.coords, r.cum, CORNER).along, i = r.cues.reduce((b, c, k) => Math.abs(c.d - al) < Math.abs(r.cues[b].d - al) ? k : b, 0); const cue = r.cues[i];
          Nav.lost = false; Nav.joined = true; Nav.progress = cue.d - 150; window.__said = []; Nav.render();
          return { txt: document.getElementById('nv-txt').textContent, said: window.__said.slice() }; })()""")
        check('a traffic light at the turn → the banner says «🚦 у светофора»', '🚦 у светофора' in lm['txt'], lm['txt'])
        check('… and the voice: «Через 150 метров у светофора поверните направо»', any('Через 150 метров у светофора поверните направо' in s for s in lm['said']), lm['said'])
        # ---------- 4. «Поехали»
        await pg.click('#pre-go'); await pg.wait_for_timeout(1600)
        check('«Поехали» closes it, it does not come back', not await pg.evaluate(SHOWN))
        # ---------- 5. «Что по пути» without a Google key: OpenStreetMap
        await pg.evaluate("Nav.progress = 0; showRiderPOIs()")
        await pg.wait_for_function("RPOI.list.length > 0", timeout=8000)
        q = await pg.evaluate("window.__q.filter(x => x.startsWith('/*rpoi*/')).slice(-1)[0] || ''")
        info = await pg.evaluate("({ n: RPOI.list.length, types: RPOI.list.map(x => x.type), layers: RPOI.layer.getLayers().length, base: baseKey })")
        check('no Google key → OpenStreetMap along the route ahead: water, café, store (a bench is not a stop)', 'around:300' in q and sorted(info['types']) == ['cafe', 'shop', 'water'] and info['layers'] == 3, info)
        check('the map stays as it was (not switched to Google)', not info['base'].startswith('google'), info['base'])
        await pg.evaluate("RPOI.layer.getLayers()[1].openPopup()"); await pg.wait_for_timeout(200)
        pop = await pg.evaluate("document.querySelector('.leaflet-popup .pop').textContent")
        check('popup: name, «через … км по маршруту», «➕ Заехать сюда»', 'Cafe Rpoi' in pop and 'по маршруту' in pop and '➕ Заехать сюда' in pop, pop)
        await pg.click('.leaflet-popup [data-rp="via"]')
        await pg.wait_for_function("Nav.wpts.length === 3 && !RPOI.layer", timeout=10000)
        r3 = await pg.evaluate(f"(() => {{ const c = Nav.route.coords, near = q => Math.min(...c.map(x => hav(x, q))); return {{ w1: near({W1}), cafe: near({CAFE}), rp: near({pt(2200, -60)}), names: Nav.wpts.map(w => w.name) }}; }})()")
        check('«➕ Заехать сюда» → a third stop, the earlier ones kept, in order', r3['w1'] < 30 and r3['cafe'] < 30 and r3['rp'] < 30 and r3['names'] == ['Вода', 'Cafe Rpoi', 'Кафе Тест'], r3)
        await pg.evaluate("Nav.stop(); showRiderPOIs()"); await pg.wait_for_function("RPOI.list.length > 0", timeout=8000)
        q = await pg.evaluate("window.__q.filter(x => x.startsWith('/*rpoi*/')).slice(-1)[0] || ''")
        await pg.evaluate("RPOI.layer.getLayers()[0].openPopup()"); await pg.wait_for_timeout(200)
        pop = await pg.evaluate("document.querySelector('.leaflet-popup .pop').textContent")
        check('without a route: around you (2.5 km), «Маршрут сюда»', 'around:2500' in q and 'Маршрут сюда' in pop, pop)
        await pg.evaluate("map.closePopup(); riderPOIsClear()")
        # ---------- 6. when not shown
        async def none(js, wait=2600):
            await pg.evaluate("preHide(true); document.querySelectorAll('.ask').forEach(x => x.hidden = true)")
            await pg.evaluate(js); await pg.wait_for_timeout(wait); return not await pg.evaluate(SHOWN)
        check('switched off in Settings → not shown', await none(f"S.preRide = false; Nav.set({{ name: 'A', coords: {json.dumps(ROUTE)} }})"))
        await pg.evaluate("S.preRide = true")
        check('a short route (1.5 km) → not shown', await none(f"Nav.set({{ name: 'B', coords: {json.dumps(ROUTE[:31])} }})"))
        check('by car → not shown', await none(f"Nav.set({{ name: 'C', coords: {json.dumps(ROUTE)}, opts: {{ mode: 'car' }} }})"))
        check('a reroute / continue from here → not shown', await none(f"Nav.set({{ name: 'D', coords: {json.dumps(ROUTE)}, keepView: true }})"))
        check('started while riding (12 km/h+) → not shown', await none(f"GPS.fix = {{ ...GPS.fix, spd: 6 }}; Nav.set({{ name: 'E', coords: {json.dumps(ROUTE)} }})", 5600))
        await pg.evaluate("GPS.fix = { ...GPS.fix, spd: 0 }")
        await pg.evaluate(f"Nav.set({{ name: 'F', coords: {json.dumps(ROUTE)} }})"); await pg.wait_for_function(SHOWN, timeout=8000)
        await pg.evaluate("GPS.fix = { ...GPS.fix, spd: 6 }"); await pg.wait_for_timeout(5600)
        check('shown, then the rider sets off → it closes by itself', not await pg.evaluate(SHOWN))
        await pg.evaluate("GPS.fix = { ...GPS.fix, spd: 0 }; Nav.stop()")
        # ---------- 7. the «not on the route» question comes first
        FAR = [[c[0] + 0.04, c[1]] for c in ROUTE]   # the route starts 4.4 km north of the rider
        await pg.evaluate(f"Nav.set({{ name: 'G', coords: {json.dumps(FAR)} }})")
        await pg.wait_for_function("!document.getElementById('ask-join').hidden", timeout=8000); await pg.wait_for_timeout(1500)
        first = not await pg.evaluate(SHOWN)
        await pg.click('#aj-no')
        try: await pg.wait_for_function(SHOWN, timeout=5000); after = True
        except Exception: after = False
        check('far from the route: «Вы не на маршруте» first, «Перед выездом» after the answer', first and after, (first, after))
        await pg.evaluate("Nav.stop()")
        # ---------- 8. landmarks: only at the turn they belong to
        TWO = [pt(n, 0) for n in range(0, 1001, 20)] + [pt(1000, e) for e in range(20, 101, 20)] + [pt(n, 100) for n in range(1020, 2001, 20)]
        lmk = await pg.evaluate(f"""(() => {{ S.preRide = false; Nav.set({{ name: 'L', coords: {json.dumps(TWO)}, noAsk: true }}); const r = Nav.route;
          const cs = r.cues.filter(c => c.ang !== 'finish'), i1 = r.cues.indexOf(cs[0]), i2 = r.cues.indexOf(cs[1]), d1 = cs[0].d, d2 = cs[1].d;
          const t = a => {{ r.ahead = a; return [cueLandmark(r, i1), cueLandmark(r, i2)].map(x => x ? x[1] : null); }};
          return {{ d: [Math.round(d1), Math.round(d2)], ang: [cs[0].ang, cs[1].ang],
            lights: t([{{ kind: 'signals', d: d1 - 8 }}]), stop: t([{{ kind: 'stop', d: d2 - 10 }}]), far: t([{{ kind: 'signals', d: d1 - 60 }}]),
            bridge1: t([{{ kind: 'bridge', d: d1 - 120, len: 60 }}]), bridge2: t([{{ kind: 'bridge', d: d1 + 15, len: 30 }}]), both: t([{{ kind: 'giveway', d: d1 - 5 }}, {{ kind: 'signals', d: d1 + 2 }}]) }}; }})()""")
        check('two turns found (right, then left)', len(lmk['d']) == 2 and lmk['ang'][0] > 60 and lmk['ang'][1] < -60, lmk)
        check('lights 8 m before the first turn → «у светофора» for it only', lmk['lights'] == ['у светофора', None], lmk['lights'])
        check('«Stop» before the second → «у знака «Стоп»» for it only', lmk['stop'] == [None, 'у знака «Стоп»'], lmk['stop'])
        check('lights 60 m before → no landmark', lmk['far'] == [None, None], lmk['far'])
        check('a bridge ending 60 m before the first turn → «после моста» for it, not for the second', lmk['bridge1'] == ['после моста', None], lmk['bridge1'])
        check('a bridge between the turns → «после моста» for the second only', lmk['bridge2'] == [None, 'после моста'], lmk['bridge2'])
        check('lights and give-way at one junction → the lights', lmk['both'][0] == 'у светофора', lmk['both'])
        await pg.evaluate("Nav.stop()")
        # ---------- 9. riding through a stop: off the route to the water, turn round there, back — no «wrong way», no reroute
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); S.preRide = false")
        await pg.evaluate(f"Nav.set({{ name: 'R', coords: {json.dumps(ROUTE)}, opts: {{ mode: 'bike', bike: RO.bike }}, noAsk: true }})")
        ok = await pg.evaluate(f"addStop({{ ll: {W1}, name: 'Вода' }})")
        await pg.evaluate("(() => { const o = window.routeVia; window.__rv = 0; window.routeVia = function () { window.__rv++; return o.apply(this, arguments); }; window.__lastToasts = ''; })()")
        pts = await pg.evaluate("(() => { const r = Nav.route, out = []; for (let d = 0; d < 1600; d += 5) { const a = ptAlong(r.coords, r.cum, d), b = ptAlong(r.coords, r.cum, d + 5); out.push([a[0], a[1], bearing(a, b)]); } return out; })()")
        t0 = await pg.evaluate("Date.now()"); trace = []
        for i, (la, lo, h) in enumerate(pts):
            trace.append(await pg.evaluate("([la, lo, h, t]) => { onFix({ coords: { latitude: la, longitude: lo, accuracy: 5, altitude: 30, altitudeAccuracy: 5, speed: 5, heading: h }, timestamp: t }); return [Nav.progress, !!Nav.wrongWay, Nav.offCount]; }", [la, lo, h, t0 + i * 1000]))
        drop = max(max(0, a[0] - b[0]) for a, b in zip(trace, trace[1:]))
        rv = await pg.evaluate("window.__rv"); toasts = await pg.evaluate("window.__lastToasts")
        check('riding through the stop: the place on the route only moves on, no «wrong way», not «off the route», no reroute',
              ok and drop < 30 and not any(x[1] for x in trace) and max(x[2] for x in trace) < 3 and rv == 0 and trace[-1][0] > 1500,
              {'drop': round(drop, 1), 'wrong': any(x[1] for x in trace), 'off': max(x[2] for x in trace), 'reroutes': rv, 'end': round(trace[-1][0])})
        check('… and at the water: «📍 Вода»', '📍 Вода' in toasts, toasts[:160])
        await pg.evaluate("Nav.stop()")
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # ---------- 10. he / en
        for lang in ('he', 'en'):
            b, ctx, pg, log = await start(p, url, m, lang)
            await pg.evaluate(f"Nav.set({{ name: 'Test', coords: {json.dumps(ROUTE)} }})")
            await pg.wait_for_function(SHOWN, timeout=8000)
            await pg.wait_for_function("document.getElementById('pre-stops').textContent.length > 0 && !/…$/.test(document.getElementById('pre-list').textContent.trim())", timeout=10000); await pg.wait_for_timeout(300)
            txt = await pg.evaluate("document.querySelector('#ask-pre .box').innerText")
            ru = [w for w in txt.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w) and w not in ('Кафе', 'Тест')]
            check(f'{lang}: «Перед выездом» translated', not ru, (txt.replace('\n', ' | ')[:260], ru[:6]))
            await pg.click('#pre-go')
            lm = await pg.evaluate("""(() => { const r = Nav.route, al = nearOn(r.coords, r.cum, CORNER).along, i = r.cues.reduce((b, c, k) => Math.abs(c.d - al) < Math.abs(r.cues[b].d - al) ? k : b, 0), cue = r.cues[i];
              Nav.lost = false; Nav.joined = true; Nav.progress = cue.d - 150; window.__said = []; Nav.render(); })()""")
            await pg.wait_for_timeout(300)   # the page translates new texts right after they appear
            lm = await pg.evaluate("({ txt: document.getElementById('nv-txt').textContent, said: window.__said.join(' / ') })")
            want = 'ברמזור' if lang == 'he' else 'at the traffic lights'
            cyr = any('Ѐ' <= ch <= 'ӿ' for ch in lm['txt'] + lm['said'])
            check(f'{lang}: the landmark on the banner and by voice, translated', want in lm['txt'] and want in lm['said'] and not cyr, lm)
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
