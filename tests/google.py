# Google Maps Platform integration: Routes API (bicycle), Places search, Google base map, navigation by Google steps.
# Google services are mocked (see harness.Mocks); real keys and real Google answers are not reachable from the sandbox.
# Run: python3 tests/google.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''))
A, B = (32.09, 34.88), (32.096, 34.888)   # mock route: north from A to the corner (32.096, 34.88), then right (east) to B

async def main():
    url = serve(8793); m = Mocks()
    async with async_playwright() as p:
        # --- without a key ---
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate("showTab('routes'); routeSeg('plan'); setRO({engine: 'google'})"); await pg.wait_for_timeout(300)
        note = await pg.evaluate("document.getElementById('pl-engine-note').textContent")
        check('no key: engine note asks for the key', 'ключ' in note, note[:80])
        fit = await pg.evaluate("(e => e.scrollWidth <= e.clientWidth + 1)(document.getElementById('pl-engine'))")
        check('engine buttons fit (iPhone 15 Pro)', fit)
        await pg.evaluate(f"Plan.wps = []; document.getElementById('pl-fromgps').checked = false; addWp([{A[0]},{A[1]}], 'A'); addWp([{B[0]},{B[1]}], 'B')")
        await pg.evaluate("buildPlan()"); await pg.wait_for_timeout(800)
        t = await pg.evaluate("window.__lastToasts")
        check('no key: clear message, no request to Google', 'ключ Google' in t and not any('routes.googleapis' in c for c in m.calls), t[-120:])
        await pg.evaluate("setRO({engine: 'auto'})")
        await b.close()

        # --- with a key ---
        m = Mocks()
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=[['velo:gkey', '"AIzaTEST"'], ['velo:base', '"ihm_mtb_he"']])
        await pg.evaluate("showTab('routes'); routeSeg('plan'); setRO({engine: 'google'})")
        await pg.evaluate(f"Plan.wps = []; document.getElementById('pl-fromgps').checked = false; addWp([{A[0]},{A[1]}], 'A'); addWp([{B[0]},{B[1]}], 'B')")
        await pg.evaluate("buildPlan()"); await pg.wait_for_function("Plan.cand != null", timeout=10000); await pg.wait_for_timeout(500)
        c = await pg.evaluate("({n: Plan.cand.coords.length, first: Plan.cand.coords[0], last: Plan.cand.coords[Plan.cand.coords.length-1], eng: Plan.cand.engine, asc: Plan.cand.ascent, ele: Plan.cand.coords[10][2], steps: Plan.cand.osrmSteps.length, base: baseKey, time: document.getElementById('r-time').textContent, why: document.getElementById('r-eng').textContent})")
        u, h, body = next(x for x in m.bodies if 'routes.googleapis' in x[0])
        check('request: Routes API, BICYCLE, field mask, key header', body.get('travelMode') == 'BICYCLE' and 'routes.polyline.encodedPolyline' in h.get('x-goog-fieldmask', '') and h.get('x-goog-api-key') == 'AIzaTEST' and body.get('languageCode') == 'ru', json.dumps(body)[:160])
        check('polyline decoded to the right place', abs(c['first'][0] - A[0]) < 1e-4 and abs(c['last'][1] - B[1]) < 1e-4 and c['n'] == 41, f"{c['n']} points")
        check('heights added (profile and climb work)', c['ele'] is not None and c['asc'] is not None and c['asc'] > 5, f"ele {c['ele']}, ↑{c['asc']}")
        check('Google route shown on the Google map', c['base'] == 'google', c['base'])
        check('time from Google, beta warning shown', c['time'] in ('0:05', '5 мин', '0 ч 05 мин') or '5' in c['time'], f"{c['time']} · {c['why'][:70]}")
        check('Google route → navigation in this app (Auto)', await pg.evaluate("navMode(Plan.cand)") == 'app')
        await pg.screenshot(path=os.path.join(SHOT, 'g-plan.png'))

        # Navigation with Google's own instruction text and the voice.
        await pg.evaluate("window.__said = []; const s0 = window.say; window.say = (t, ...a) => { window.__said.push(t); return s0(t, ...a); }")
        await pg.click('#r-nav'); await pg.wait_for_timeout(600)
        cues = await pg.evaluate("Nav.route.cues.map(c => c.txt)")
        check('cue uses Google instruction', cues and cues[0] == 'Поверните направо на улицу Тестовую', cues)
        lat = A[0]
        await ctx.set_geolocation({'latitude': lat, 'longitude': A[1], 'accuracy': 5}); await pg.wait_for_timeout(1200)
        await pg.screenshot(path=os.path.join(SHOT, 'g-before-play.png'))
        await pg.evaluate("document.getElementById('c-play').click()")
        for _ in range(50): lat += 0.00011; await ctx.set_geolocation({'latitude': lat, 'longitude': A[1], 'accuracy': 5}); await pg.wait_for_timeout(1000)
        nv = await pg.evaluate("document.getElementById('nv-txt').textContent"); said = [x for x in (await pg.evaluate("window.__said") or []) if x]
        check('banner and voice say the Google turn', 'направо на улицу Тестовую' in nv and any('поверните направо на улицу Тестовую' in x for x in said), f"{nv} · {said[-2:]}")
        await pg.screenshot(path=os.path.join(SHOT, 'g-nav.png'))
        # Rebuild to the finish from off the route: Google again, steps kept.
        n0 = sum('routes.googleapis' in x for x in m.calls)
        await ctx.set_geolocation({'latitude': 32.0955, 'longitude': 34.8835, 'accuracy': 5}); await pg.wait_for_timeout(1000)
        await pg.evaluate("Nav.toFinish(false)"); await pg.wait_for_timeout(1500)
        rr = await pg.evaluate("({cues: Nav.route.cues.map(c => c.txt), eng: Nav.route.opts && Nav.route.opts.engine})")
        check('reroute to finish uses Google', sum('routes.googleapis' in x for x in m.calls) > n0 and rr['eng'] == 'google' and 'улицу' in ' '.join(rr['cues']), rr)
        await pg.evaluate("Nav.stop(); document.getElementById('c-stop').click(); document.getElementById('c-stop').click()")

        # A→B, by roads: Google variants first.
        await pg.evaluate(f"openAB(); AB.terr = 'road'; AB.kind = 'one'; AB.a = [{A[0]},{A[1]}]; AB.b = [{B[0]},{B[1]}]; abRender()")
        await pg.click('#ab-go'); await pg.wait_for_function("AB.vars.length > 0 && !AB.busy", timeout=15000); await pg.wait_for_timeout(400)
        v = await pg.evaluate("AB.vars.map(v => ({g: !!v.google, prof: v.prof, d: Math.round(v.distance)}))")
        check('A→B: Google variants first, BRouter after', len(v) == 3 and v[0]['g'] and v[1]['g'] and not v[2]['g'], v)
        rowtxt = await pg.evaluate("document.querySelector('#ab-res .abv .s').textContent")
        check('A→B: variant marked Google', rowtxt.startswith('Google'), rowtxt[:60])
        await pg.screenshot(path=os.path.join(SHOT, 'g-ab.png'))
        await pg.click('#ab-ride'); await pg.wait_for_timeout(500)
        check('A→B Google variant navigates with Google steps', await pg.evaluate("Nav.route.opts.engine === 'google' && Nav.route.cues[0].txt.includes('Тестовую')"))
        await pg.evaluate("Nav.stop()")

        # Places search on the Google map; Nominatim on other maps.
        r1 = await pg.evaluate("geoSearch('Яркон').then(r => r[0])")
        await pg.evaluate("setBase('ihm_mtb_he')"); r2 = await pg.evaluate("geoSearch('Яркон').then(r => r[0])")
        check('search: Google Places on Google map, Nominatim otherwise', r1.get('src') == 'google' and 'Парк Яркон' in r1['display_name'] and r2.get('src') is None, f"{r1['display_name']} / {r2['display_name']}")

        # Readable errors.
        m.gerr = (403, {'error': {'code': 403, 'message': 'Routes API has not been used in project 1 before or it is disabled.', 'status': 'PERMISSION_DENIED'}})
        e1 = await pg.evaluate(f"googleRoute([[{A[0]},{A[1]}],[{B[0]},{B[1]}]]).then(() => 'ok', e => e.message)")
        m.gerr = (429, {'error': {'code': 429, 'message': 'Quota exceeded', 'status': 'RESOURCE_EXHAUSTED'}})
        e2 = await pg.evaluate(f"googleRoute([[{A[0]},{A[1]}],[{B[0]},{B[1]}]]).then(() => 'ok', e => e.message)")
        check('errors in Russian: API off / quota', 'не включён' in e1 and 'лимит' in e2, f'{e1} | {e2}')
        m.gerr = None
        # Key check in Profile tests the map and the routes.
        await pg.evaluate("document.getElementById('g-key').value = 'AIzaTEST'"); await pg.evaluate("document.getElementById('g-save').click()"); await pg.wait_for_timeout(1500)
        st = await pg.evaluate("document.getElementById('g-st').textContent")
        check('key check: map and routes', '✓ Ключ работает' in st and '✓ Маршруты Google работают' in st, st)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()

        # Hebrew: Google answers in Hebrew.
        m = Mocks()
        b, ctx, pg, log = await open_app(p, url + '?lang=he', m, viewport=(375, 667), storage=[['velo:gkey', '"AIzaTEST"']])
        await pg.evaluate(f"googleRoute([[{A[0]},{A[1]}],[{B[0]},{B[1]}]])")
        body = next(x[2] for x in m.bodies if 'routes.googleapis' in x[0])
        check('Hebrew UI → Google instructions in Hebrew', body.get('languageCode') == 'he')
        await pg.evaluate("showTab('routes'); routeSeg('plan')"); await pg.wait_for_timeout(300)
        fit = await pg.evaluate("(e => e.scrollWidth <= e.clientWidth + 1)(document.getElementById('pl-engine'))")
        check('engine buttons fit (iPhone SE, Hebrew)', fit)
        await pg.screenshot(path=os.path.join(SHOT, 'g-engine-he.png'))
        check('no JS errors (he)', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
