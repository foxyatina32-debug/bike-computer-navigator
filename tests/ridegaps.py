# v151 (audit R08, part of R15): a ride with gaps in its recording is not one line. Two recorded pieces of 1.1 km with an
# unrecorded 8.9 km between them (a manual pause): no route made by itself after «Сохранить» (it used to be one 11 km route
# with a straight line over the gap); «В мои маршруты» offers to join the gap along the roads (the router asked, never a
# straight line) or to keep the pieces as separate routes; a stretch counted without GPS (est) is a gap too; a stop where
# the ride goes on from the same place (≤ 40 m) is not; «Ещё раз» joins the gap along the roads, or takes the longest piece;
# the fly-over jumps the gap (its length 2.2 km, not 11 km) and draws no line over it; a 150 000-point track does not
# break the 3D fly-over (Math.min(...) overflowed the stack).
# Run: python3 tests/ridegaps.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
T0 = 1.79e12
def piece(lat0, lon0, n, t0, step=10):   # n points 10 m apart going north, one per 2 s
    return [[lat0 + i * step / 110540, lon0, 30, t0 + i * 2000] for i in range(n)]
A = piece(32.09, 34.88, 111, T0)                       # 1.1 km
B = piece(32.18, 34.88, 111, T0 + 3600e3)              # 1.1 km, 8.9 km further north (after a pause)
RIDE = {'id': 'gap1', 'name': 'С разрывом', 'start': T0, 'end': T0 + 4000e3, 'type': 'bike', 'dist': 2200, 'movingMs': 900e3, 'max': 6, 'asc': 0, 'desc': 0,
        'track': A + B, 'brk': [B[0][3]]}
C = piece(32.09, 34.9, 60, T0)
D = piece(32.09 + 590 / 110540 + 25 / 110540, 34.9, 60, T0 + 900e3)   # goes on 25 m from where it stopped
RIDE2 = {'id': 'gap2', 'name': 'Стоп у кафе', 'start': T0, 'end': T0 + 1100e3, 'type': 'bike', 'dist': 1200, 'movingMs': 300e3, 'track': C + D, 'brk': [D[0][3]]}
E = piece(32.2, 34.95, 60, T0); F = piece(32.2 + 3000 / 110540, 34.95, 60, T0 + 400e3)
RIDE3 = {'id': 'gap3', 'name': 'Без GPS', 'start': T0, 'end': T0 + 600e3, 'type': 'bike', 'dist': 4200, 'movingMs': 500e3, 'track': E + F, 'est': [{'t0': E[-1][3], 't1': F[0][3], 'm': 2400, 'by': 'line'}]}
ROUTES = "(async () => (await DB.all('routes')).map(r => ({ n: r.name, d: Math.round(cumDist(r.coords).pop()) })))()"
STUB = "routeVia = async pts => ({ coords: [[pts[0][0], pts[0][1], null], [(pts[0][0] + pts[1][0]) / 2, pts[0][1] + 0.01, null], [pts[1][0], pts[1][1], null]], distance: 0 }); 0"

async def main():
    url = serve(8919)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1200)
        dialogs = []
        async def on_dialog(d):
            dialogs.append(d.message); ans = pg.__dict__.get('_answers') or []
            await (d.accept() if (ans.pop(0) if ans else False) else d.dismiss())
        pg.on('dialog', lambda d: asyncio.ensure_future(on_dialog(d)))
        def answers(*a): pg.__dict__['_answers'] = list(a)
        for r in (RIDE, RIDE2, RIDE3): await pg.evaluate(f"DB.put('rides', {json.dumps(r)})")
        n = await pg.evaluate("(r => (rideRouteParts(r) || []).length)(%s)" % json.dumps(RIDE))
        check('a ride with an 8.9 km unrecorded gap: two pieces, not one line', n == 2 and await pg.evaluate("(r => rideRouteCoords(r) === null)(%s)" % json.dumps(RIDE)), n)
        # ---- «Сохранить»: no route made by itself
        r0 = await pg.evaluate(ROUTES)
        await pg.evaluate("(async () => { const r = await DB.get('rides', 'gap1'); await quickSave(r); })()"); await pg.wait_for_timeout(500)
        r1 = await pg.evaluate(ROUTES); sub = await pg.evaluate("document.getElementById('sb-sub').textContent")
        check('«Сохранить»: no 11-km route with a straight line made by itself; the bar says why', len(r1) == len(r0) and 'разрывы' in sub, (r1, sub))
        # ---- «В мои маршруты»: separate pieces
        answers(False, True)
        await pg.evaluate("(async () => { const r = await DB.get('rides', 'gap1'); delete r.savedRoute; await rideToRoute(r); })()"); await pg.wait_for_timeout(300)
        r2 = await pg.evaluate(ROUTES); new = [x for x in r2 if x not in r1]
        check('«В мои маршруты»: asked; the pieces kept as two separate routes of ~1.1 km', len(dialogs) >= 2 and len(new) == 2 and all(1000 <= x['d'] <= 1200 for x in new), (dialogs[-2:], new))
        # ---- joined along the roads (the router asked)
        await pg.evaluate("window.__rv = routeVia; " + STUB)
        answers(True, True)
        await pg.evaluate("(async () => { const r = await DB.get('rides', 'gap1'); delete r.savedRoute; await rideToRoute(r, true); })()"); await pg.wait_for_timeout(300)
        r3 = await pg.evaluate(ROUTES); new = [x for x in r3 if x not in r2]
        via = await pg.evaluate("(async () => (await DB.all('routes')).some(r => r.coords.some(c => c[1] > 34.885 && c[1] < 34.895)))()")
        check('…or joined along the roads: one route, the gap filled by the router\'s way (not a straight line)', len(new) == 1 and via and new[0]['d'] > 11200, new)
        # ---- est is a gap too; a stop and on from the same place is not
        n3 = await pg.evaluate("(r => (rideRouteParts(r) || []).length)(%s)" % json.dumps(RIDE3))
        check('a stretch counted without GPS (est) is not road geometry: two pieces', n3 == 2, n3)
        n2 = await pg.evaluate("(r => (rideRouteParts(r) || []).length)(%s)" % json.dumps(RIDE2))
        await pg.evaluate("(async () => { const r = await DB.get('rides', 'gap2'); await quickSave(r); })()"); await pg.wait_for_timeout(500)
        r4 = await pg.evaluate(ROUTES); new = [x for x in r4 if x not in r3]
        check('a café stop, on from 25 m away: one piece, the route made as before', n2 == 1 and len(new) == 1, (n2, new))
        # ---- «Ещё раз»
        await pg.evaluate("openRide('gap1')"); await pg.wait_for_timeout(800)
        await pg.evaluate("document.getElementById('rd-again').click()"); await pg.wait_for_timeout(800)
        tot = await pg.evaluate("Nav.route && Math.round(Nav.route.total)"); via = await pg.evaluate("!!Nav.route && Nav.route.coords.some(c => c[1] > 34.885 && c[1] < 34.895)")
        check('«Ещё раз»: the gap joined along the roads (the router\'s way)', via and tot > 11200, tot)
        await pg.evaluate("Nav.stop(); routeVia = async () => { throw new Error('нет связи'); }; 0")
        await pg.evaluate("openRide('gap1')"); await pg.wait_for_timeout(800)
        await pg.evaluate("document.getElementById('rd-again').click()"); await pg.wait_for_timeout(800)
        tot = await pg.evaluate("Nav.route && Math.round(Nav.route.total)")
        check('«Ещё раз» with no router: the longest piece (1.1 km), not 11 km with a straight line', tot and 1000 <= tot <= 1200, tot)
        await pg.evaluate("Nav.stop(); routeVia = window.__rv; 0")
        # ---- fly-over
        st = await pg.evaluate("""(r => { const c = r.track, cuts = trackCuts(c, r.brk, r.est), P = v3FlyPrep(c, cuts); V3.coords = c; V3.cuts = cuts; const g = v3Data().features[0].geometry; V3.coords = null; V3.cuts = null;
          return { total: Math.round(P.total), geo: g.type, parts: g.coordinates.length }; })(%s)""" % json.dumps(RIDE))
        check('the fly-over jumps the gap: 2.2 km, not 11 km; the 3D line is two pieces', 2100 <= st['total'] <= 2300 and st['geo'] == 'MultiLineString' and st['parts'] == 2, st)
        st = await pg.evaluate("""(() => { const c = []; for (let i = 0; i < 150000; i++) c.push([32 + i * 1e-5, 34.8 + (i % 7) * 1e-5, 30 + (i % 50), 1.79e12 + i * 1000]);
          try { const P = v3FlyPrep(c); return { ok: !!P, b: P.bounds }; } catch (e) { return { err: String(e) }; } })()""")
        check('a 150 000-point track: the 3D fly-over is prepared (no stack overflow)', st.get('ok'), st)
        await pg.evaluate("openRide('gap1')"); await pg.wait_for_timeout(800)
        await pg.evaluate("hasWebGL = () => false; document.getElementById('rd-fly').click()"); await pg.wait_for_timeout(2500)
        st = await pg.evaluate("""(() => { let n = 0, maxJ = 0; RD.map.eachLayer(l => { if (l instanceof L.Polyline && !(l instanceof L.Polygon)) { const ll = l.getLatLngs().flat(3); for (let i = 1; i < ll.length; i++) maxJ = Math.max(maxJ, ll[i - 1].distanceTo(ll[i])); n++; } }); return { n, maxJ: Math.round(maxJ) }; })()""")
        await pg.evaluate("rdStopFly()")
        check('the fly-over on the small map: no line drawn over the gap', st['maxJ'] < 1000, st)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
