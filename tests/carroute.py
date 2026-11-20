# v146: Car mode — the routes are always for the car. With a Google key and a Google map on the screen: Google's driving
# route first (DRIVE); on another map (or without a key): OSRM's car profile, the map not switched; BRouter's car profiles
# as the backup. A route built for the bike and followed in Car mode (the rebuild declined): rerouting goes by car roads,
# not by the bicycle again (it asked BRouter's mountain-bike profile). The round speedometer on a wide car screen and a
# phone: never over the place card, the legend tab, SOS or the compass. Run: python3 tests/carroute.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.10 + i * 0.001, 34.88, 20] for i in range(30)]

async def main():
    url = serve(8901)
    async with async_playwright() as p:
        m = Mocks()
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(32.09, 34.88), storage=[['velo:gkey', '"AIzaTEST"'], ['velo:base', '"google_sat"']])
        await pg.wait_for_timeout(1200)
        await pg.evaluate("setMode('car', true)")
        async def plan(dest):
            n0 = len(m.calls); b0 = len(m.bodies)
            await pg.evaluate(f"(() => {{ showTab('routes'); routeSeg('plan'); Plan.wps = []; addWp({json.dumps(dest)}, 'Цель'); document.getElementById('pl-fromgps').checked = true; buildPlan(); }})()")
            await pg.wait_for_function("Plan.cand || document.getElementById('pl-go').textContent !== 'Строю…'", timeout=20000); await pg.wait_for_timeout(500)
            calls = m.calls[n0:]
            return {
                'google': [bd for (u, h, bd) in m.bodies[b0:] if 'routes.googleapis.com' in u],
                'osrm': [c for c in calls if 'routing.openstreetmap.de/routed-' in c],
                'brouter': [c for c in calls if 'brouter.de' in c],
                'cand': await pg.evaluate("Plan.cand ? { google: !!Plan.cand.google, n: Plan.cand.coords.length, engine: Plan.cand.engine || '' } : null"),
                'base': await pg.evaluate("baseKey"),
            }
        r = await plan([32.12, 34.9])
        check('car + Google key + Google map: Google\'s driving route (DRIVE)', r['google'] and r['google'][0].get('travelMode') == 'DRIVE' and r['cand'] and r['cand']['google'] and not r['osrm'], (r['google'][:1], r['osrm'][:1], r['cand']))
        await pg.evaluate("setBase('ihm_mtb_he'); 0"); await pg.wait_for_timeout(300)
        r = await plan([32.125, 34.905])
        check('car on another map: OSRM\'s car profile, the map stays as chosen', not r['google'] and r['osrm'] and all('/routed-car/' in c for c in r['osrm']) and r['base'] == 'ihm_mtb_he', (r['osrm'][:1], r['base']))
        await pg.evaluate("lsSet('gkey', ''); setBase('google_sat'); 0"); await pg.wait_for_timeout(300)
        r = await plan([32.13, 34.91])
        check('car without a key: OSRM\'s car profile', not r['google'] and r['osrm'] and all('/routed-car/' in c for c in r['osrm']), r['osrm'][:1])
        m.fail.add('routing.openstreetmap.de')
        r = await plan([32.135, 34.915])
        check('OSRM out of reach: BRouter\'s car profile (never a bicycle one)', r['brouter'] and all('profile=car-' in c for c in r['brouter']), r['brouter'][:1])
        m.fail.discard('routing.openstreetmap.de')
        # a bike route followed in Car mode (the rebuild declined): the reroute goes by car roads
        await pg.evaluate("showTab('rec'); setMode('bike', true)")
        await pg.evaluate(f"Nav.set({{ name: 'Велосипедный', coords: {json.dumps(ROUTE)}, opts: {{ bike: 'xc', terrain: 'mixed', engine: 'auto', mode: 'bike' }}, noAsk: true }})"); await pg.wait_for_timeout(300)
        await pg.evaluate("setMode('car', true)"); await pg.wait_for_timeout(200)
        asked = await pg.evaluate("!document.getElementById('ask-remode').hidden")
        await pg.evaluate("document.getElementById('rm-no').click()")
        o = await pg.evaluate("(() => { const x = rrOpts(Nav.route); return { mode: x.mode, engine: x.engine }; })()")
        check('switched to Car on a bike route: asked to rebuild; declined — rerouting still uses the car', asked and o['mode'] == 'car', o)
        n0 = len(m.calls)
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); Nav.lastReroute = 0; Nav.ignoreOffUntil = 0; window.__set0 = Nav.setAt")
        t0 = await pg.evaluate("Date.now()")
        FX = "([la, lo, t]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 5, altitude: 30, altitudeAccuracy: 5, speed: 12, heading: 0 }, timestamp: t })"
        for k in range(8):   # along the route first (joined), then off it to the east
            await pg.evaluate(FX, [32.101 + k * 0.0004, 34.88, t0 + k * 1500]); await pg.wait_for_timeout(150)
        await pg.evaluate("Nav.lastReroute = 0; Nav.ignoreOffUntil = 0; window.__set0 = Nav.setAt")
        for k in range(10):
            await pg.evaluate(FX, [32.1042 + k * 0.0002, 34.8806 + k * 0.0006, t0 + 12000 + k * 1500]); await pg.wait_for_timeout(300)
        try: await pg.wait_for_function("Nav.setAt !== window.__set0 && !Nav.rejoining", timeout=20000)
        except Exception: pass
        calls = m.calls[n0:]
        br = [c for c in calls if 'brouter.de' in c]; os_ = [c for c in calls if 'routing.openstreetmap.de/routed-' in c]
        bikey = [c for c in br if 'profile=car-' not in c] + [c for c in os_ if '/routed-car/' not in c]
        check('off the route in Car mode: rebuilt by car roads (no bicycle profile asked)', (br or os_) and not bikey, (br[:1], os_[:1], bikey[:2]))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # ---- the round speedometer on a wide car screen and on a phone: never over the place card, the legend tab, SOS, the compass
        GEO = "(() => { const r = q => { const e = document.querySelector(q); if (!e || e.hidden || e.classList.contains('ovh')) return null; const b = e.getBoundingClientRect(); return b.width ? { l: b.left, t: b.top, r: b.right, b: b.bottom } : null; }; return { spdb: r('#spdb'), locw: r('#locw'), sos: r('#t-sos'), legend: r('#legend-tab'), compass: r('#t-compass'), hud: r('#hud') }; })()"
        def apart(a, c): return a['r'] <= c['l'] + 1 or c['r'] <= a['l'] + 1 or a['b'] <= c['t'] + 1 or c['b'] <= a['t'] + 1
        for theme, vp in (('md', (960, 600)), ('dark', (1024, 600)), ('md', (800, 480)), ('md', (844, 390)), ('md', (915, 412)), ('dark', (390, 844))):
            b, ctx, pg, log = await open_app(p, url + '?lang=he', Mocks(), viewport=vp, storage=[['velo:settings', json.dumps({'theme': theme, 'gsearch': True})]])
            await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); setMode('car', true)")
            await pg.evaluate(f"Nav.set({{name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true}})"); await pg.wait_for_timeout(300)
            t0 = await pg.evaluate("Date.now()")
            for i in range(8): await pg.evaluate("([la, lo, t]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 6, altitude: 40, altitudeAccuracy: 5, speed: 14, heading: 0 }, timestamp: t })", [32.101 + i * 14 / 110540, 34.88, t0 + i * 1000])
            # the card with all three lines (ahead, here, behind), as on the owner's car screen
            await pg.evaluate("Places.cur = 'פתח תקווה'; Places.next = { name: 'גת רימון', dist: 4800, route: true }; Places.prev = 'גבעת שמואל'; Places.render(); placeGpxBtn()"); await pg.wait_for_timeout(400)
            g = await pg.evaluate(GEO)
            others = [k for k in ('locw', 'sos', 'legend', 'compass') if g[k]]
            hit = [k for k in others if not apart(g['spdb'], g[k])] if g['spdb'] else ['hidden']
            inmap = g['spdb'] and (not g['hud'] or vp[0] < vp[1] or g['spdb']['r'] <= g['hud']['l'])
            check(f'{theme} {vp[0]}×{vp[1]}: the speedometer shown, on the map, clear of the place card / legend / SOS / compass', not hit and inmap, (hit, g['spdb'], g['locw']))
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
