# Route geometry (audit v96): the line the app navigates and draws is exactly the line it got — no swapped coordinates,
# no phantom straight jumps, no false U-turns — both when a route is built and when it is rebuilt after leaving it.
import asyncio, sys, os, json, math, re
from urllib.parse import unquote
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
LAT0, LON0 = 32.10, 34.88
KX = 111320 * math.cos(LAT0 * math.pi / 180); KY = 110540
def ll(n, e): return [round(LAT0 + n / KY, 7), round(LON0 + e / KX, 7)]
def hav(a, b): return math.hypot((a[0] - b[0]) * KY, (a[1] - b[1]) * KX)
STRAIGHT = [ll(i * 50, 0) + [20 + i] for i in range(61)]          # 3 km north, heights 20…80
# Geometry checks done in the page: longest segment, sharpest reversal between consecutive ≥ 8 m legs.
GEO = """(c => { const seg = c.slice(1).map((p, i) => hav(c[i], p)); let rev = 0, at = -1;
  for (let i = 1; i < c.length - 1; i++) { if (hav(c[i - 1], c[i]) < 8 || hav(c[i], c[i + 1]) < 8) continue;
    const d = Math.abs(norm180(bearing(c[i], c[i + 1]) - bearing(c[i - 1], c[i]))); if (d > rev) { rev = d; at = i; } }
  return { n: c.length, maxSeg: Math.round(Math.max(...seg)), rev: Math.round(rev), at, total: Math.round(cumDist(c).pop()) }; })"""

async def main():
    url = serve(8829)
    async with async_playwright() as p:
        # ---------- 1. Built routes: the router's line is navigated and drawn as it came ----------
        m = Mocks()
        BR = [[LON0 + e / KX, LAT0 + n / KY, 30 + k] for k, (n, e) in enumerate([(0, 0), (200, 0), (200, 300), (600, 300), (600, 100)])]
        m.brouter = lambda u: {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {'track-length': '1300', 'filtered ascend': '4'}, 'geometry': {'type': 'LineString', 'coordinates': BR}}]}
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=tuple(ll(0, 0)))
        await pg.wait_for_timeout(1200)
        r = await pg.evaluate("routeVia([[32.1, 34.88], [32.1054, 34.881]], {...curOpts(), engine: 'brouter', bike: 'xc'}, {quiet: true})")
        got = [[round(c[0], 7), round(c[1], 7), c[2]] for c in r['coords']]
        want = [[round(c[1], 7), round(c[0], 7), c[2]] for c in BR]
        check('1.1 BRouter: [lon, lat, ele] → [lat, lon, ele], every point, in order', got == want, got[:2])
        await pg.evaluate("r => Nav.set({name: 'BR', coords: r.coords, opts: {bike: 'xc'}, noAsk: true})", r)
        d = await pg.evaluate("(() => { const a = Nav.route.coords, b = Nav.line.getLatLngs(); return {n: a.length, m: b.length, max: Math.max(...a.map((c, i) => hav(c, [b[i].lat, b[i].lng])))}; })()")
        check('1.2 the line on the map is the navigated line, point for point', d['n'] == d['m'] and d['max'] < 0.01, d)
        m2 = Mocks(); await b.close()
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m2, geo=tuple(ll(0, 0)))
        await pg.wait_for_timeout(1200)
        r = await pg.evaluate("osrmRoute([[32.09, 34.88], [32.1, 34.9]])")
        check('1.3 OSRM: [lon, lat] → [lat, lon]', [round(x, 3) for x in r['coords'][1][:2]] == [32.095, 34.89] and [round(x, 3) for x in r['coords'][-1][:2]] == [32.1, 34.9], r['coords'])
        await b.close()

        # ---------- 2. OSM route relations are joined into one line without phantom jumps ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=tuple(ll(0, 0)))
        await pg.wait_for_timeout(1200)
        def way(pts, role=''): return {'type': 'way', 'role': role, 'geometry': [{'lat': q[0], 'lon': q[1]} for q in pts]}
        main = [ll(i * 50, 0) for i in range(41)]                                 # 2 km north, cut into 4 ways
        w = [main[0:11], main[10:21], main[20:31], main[30:41]]
        shuffled = [way(w[2][::-1]), way(w[0]), way(w[3]), way(w[1][::-1])]        # out of order, two reversed
        rel = lambda members: {'elements': [{'type': 'relation', 'id': 1, 'tags': {'type': 'route', 'route': 'mtb', 'name': 'T'}, 'members': members}]}
        g = await pg.evaluate(f"(() => {{ const it = itemsFromOverpass({json.dumps(rel(shuffled))})[0]; return {GEO}(it.line); }})()")
        check('2.1 ways out of order / reversed → one continuous line, the right length', g['maxSeg'] <= 51 and abs(g['total'] - 2000) < 30 and g['rev'] < 30, g)
        loop = [ll(0, 0), ll(500, 0), ll(500, 500), ll(0, 500), ll(0, 0)]
        lw = [way([loop[0], loop[1]]), way([loop[2], loop[1]]), way([loop[3], loop[4]]), way([loop[2], loop[3]])]
        g = await pg.evaluate(f"(() => {{ const it = itemsFromOverpass({json.dumps(rel(lw))})[0]; return {GEO}(it.line); }})()")
        check('2.2 a loop relation → a closed loop of the right length', abs(g['total'] - 2000) < 30 and g['maxSeg'] <= 505, g)
        stray = shuffled + [way([ll(9000, 4000), ll(9200, 4000)])]               # a stray way 9 km away
        g = await pg.evaluate(f"(() => {{ const it = itemsFromOverpass({json.dumps(rel(stray))})[0]; return {GEO}(it.line); }})()")
        check('2.3 a stray way far away is NOT joined by a phantom straight line', g['maxSeg'] <= 51 and abs(g['total'] - 2000) < 30, g)
        alt = shuffled + [way([ll(1000, 0), ll(1000, 400), ll(1500, 400), ll(1500, 0)], 'alternative')]
        g = await pg.evaluate(f"(() => {{ const it = itemsFromOverpass({json.dumps(rel(alt))})[0]; return {GEO}(it.line); }})()")
        check('2.4 an «alternative» branch is drawn but not glued into the line to ride', abs(g['total'] - 2000) < 30 and g['rev'] < 30, g)
        gap = [way(w[0]), way(w[1]), way([q for q in main[22:31]]), way(w[3])]   # a 100 m hole in the mapping
        g = await pg.evaluate(f"(() => {{ const it = itemsFromOverpass({json.dumps(rel(gap))})[0]; return {GEO}(it.line); }})()")
        check('2.5 a small hole in the mapping (100 m) is bridged, nothing dropped', abs(g['total'] - 2000) < 30 and g['maxSeg'] <= 101, g)
        await b.close()

        # ---------- 3. Rebuilding the way back: joins the route exactly, keeps the rest of it as it was ----------
        async def ride_off(mk_brouter):
            m = Mocks()
            if mk_brouter: m.brouter = mk_brouter
            b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=tuple(ll(0, 0)))
            await pg.wait_for_timeout(1200)
            await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(STRAIGHT)}, noAsk: true}}); Nav.setAt -= 300000")
            for k in range(1, 31):   # ride 300 m north on the route
                la, lo = ll(k * 10, 0); await ctx.set_geolocation({'latitude': la, 'longitude': lo, 'accuracy': 5}); await pg.wait_for_timeout(700)
            for k in range(1, 13):   # then 120 m east, off the route
                la, lo = ll(300 + k * 3, k * 10); await ctx.set_geolocation({'latitude': la, 'longitude': lo, 'accuracy': 5}); await pg.wait_for_timeout(700)
            await pg.wait_for_function("Nav.route && Nav.route.rr", timeout=40000)
            return b, ctx, pg, log
        def brpath(pts):
            co = [[q[1], q[0], 40] for q in pts]
            return {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {'track-length': '500'}, 'geometry': {'type': 'LineString', 'coordinates': co}}]}
        def ends(u):
            q = unquote(re.search(r'lonlats=([^&]+)', u).group(1)).split('|'); return [[float(x.split(',')[1]), float(x.split(',')[0])] for x in q]
        TAIL = "(() => { const c = Nav.route.coords, o = %s; const k = c.findIndex(q => Math.abs(q[1] - 34.88) < 1e-6); const t = c.slice(k + 1); const j0 = t.length ? o.findIndex(x => hav(x, t[0]) < 0.5) : -1; return {k, j0, same: k > 0 && j0 > 0 && t.length === o.length - j0 && t.every((q, i) => hav(q, o[j0 + i]) < 0.5 && q[2] === o[j0 + i][2]), first: c[0], last: c[c.length - 1]}; })()" % json.dumps(STRAIGHT)
        b, ctx, pg, log = await ride_off(None)
        t = await pg.evaluate(TAIL); g = await pg.evaluate(f"{GEO}(Nav.route.coords)")
        check('3.1 after a reroute: the rest of the route is the original, point for point (heights too)', t['k'] > 0 and t['same'], t)
        check('3.2 …starts where the rider is (off the route), ends at the original finish', (t['first'][1] - LON0) * KX > 30 and hav(t['last'], STRAIGHT[-1]) < 0.5, t)
        check('3.3 …no false U-turn in the joined line', g['rev'] < 150, g)
        check('3 no JS errors', not log['errors'], log['errors'][:3]); await b.close()
        # The router snaps its end to a road 90 m beside the route: the line still reaches the route (no skipped join).
        def snapped(u):
            a, z = ends(u)[0], ends(u)[-1]; zz = [z[0], z[1] + 90 / KX]
            return brpath([a, [(a[0] + zz[0]) / 2, (a[1] + zz[1]) / 2], zz])
        b, ctx, pg, log = await ride_off(snapped)
        r = await pg.evaluate("(() => { const c = Nav.route.coords; const k = c.findIndex(q => hav(q, [q[0], 34.88]) < 0.5); return {k, gap: k > 0 ? Math.round(hav(c[k - 1], c[k])) : null, onRoute: k > 0 ? hav(c[k], [c[k][0], 34.88]) : null}; })()")
        check('3.4 router end 90 m off the route: the way back still joins the route at its point', r['k'] > 0 and r['gap'] is not None and r['gap'] <= 95, r)
        check('3.4 no JS errors', not log['errors'], log['errors'][:3]); await b.close()
        # The router reaches the route 120 m beyond its target and comes back: joined where it first touches — no U-turn.
        def overshoot(u):
            a, z = ends(u)[0], ends(u)[-1]; far = [z[0] + 120 / KY, z[1]]
            return brpath([a, [(a[0] + far[0]) / 2, (a[1] + far[1]) / 2 + 30 / KX], far, [(far[0] + z[0]) / 2, z[1]], z])
        b, ctx, pg, log = await ride_off(overshoot)
        g = await pg.evaluate(f"{GEO}(Nav.route.coords)"); t = await pg.evaluate(TAIL)
        check('3.5 router overshoots the join point: no false U-turn on the route', g['rev'] < 150, g)
        check('3.6 …and the rest of the route is still the original', t['same'], t)
        check('3.5 no JS errors', not log['errors'], log['errors'][:3]); await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
