# Route on every base map and in every map orientation: the line sits on the right place, above the map, under the markers.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []; SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'layers'); os.makedirs(SHOT, exist_ok=True)
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = [[32.09 + i * 0.0006, 34.88 + (i % 7) * 0.0004, 20] for i in range(12)]
# Screen position of the route's vertices as drawn, against where the map says those points are.
PROBE = """(() => {
  const ln = Nav.line, el = ln && ln._path; if (!el) return {err: 'no line'};
  const m = el.getScreenCTM(), mb = map.getContainer().getBoundingClientRect(), segs = el.getAttribute('d').match(/[ML][^ML]+/g) || [];
  const drawn = segs.map(s => s.slice(1).trim().split(/[ ,]+/).map(Number)).map(([x, y]) => new DOMPoint(x, y).matrixTransform(m));
  const ll = ln.getLatLngs(), want = ll.map(p => map.latLngToContainerPoint(p)).map(p => ({x: p.x + mb.left, y: p.y + mb.top}));
  // Leaflet simplifies the line, so every drawn vertex must lie on the true route (distance to the nearest segment).
  const segD = (p, a, b) => { const dx = b.x - a.x, dy = b.y - a.y, l = dx * dx + dy * dy, t = l ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l)) : 0; return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy); };
  let worst = 0; drawn.forEach(d => { let best = Infinity; for (let i = 1; i < want.length; i++) best = Math.min(best, segD(d, want[i - 1], want[i])); worst = Math.max(worst, best); });
  const inView = q => q.x > mb.left + 2 && q.x < mb.right - 2 && q.y > mb.top + 2 && q.y < mb.bottom - 2;
  // An end may be cut only when that end of the route is outside the screen.
  const e0 = inView(want[0]) ? Math.hypot(drawn[0].x - want[0].x, drawn[0].y - want[0].y) : 0, e1 = inView(want[want.length - 1]) ? Math.hypot(drawn[drawn.length - 1].x - want[want.length - 1].x, drawn[drawn.length - 1].y - want[want.length - 1].y) : 0;
  const ends = Math.max(e0, e1), endsRaw = Math.max(Math.hypot(drawn[0].x - want[0].x, drawn[0].y - want[0].y), Math.hypot(drawn[drawn.length - 1].x - want[want.length - 1].x, drawn[drawn.length - 1].y - want[want.length - 1].y));
  const tilePane = map.getPane('tilePane'), ovPane = ln.getPane(), mk = map.getPane('markerPane');
  const z = p => +getComputedStyle(p).zIndex || 0;
  return {n: drawn.length, m: want.length, ends: Math.round(ends * 10) / 10, worst: Math.round(worst * 10) / 10, sameParent: tilePane.parentNode === ovPane.parentNode || tilePane.closest('.leaflet-rotate-pane') === ovPane.closest('.leaflet-rotate-pane'), above: z(ovPane) > z(tilePane), under: z(mk) > z(ovPane), bearing: Math.round(map.getBearing ? map.getBearing() : 0)};
})()"""
async def main():
    url = serve(8773); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=[['velo:pro', 'true'], ['velo:tfkey', '"T"'], ['velo:mapykey', '"M"'], ['velo:gkey', '"AIzaTEST"']])
        await pg.evaluate(f"Nav.set({{name: 'Проверка', coords: {json.dumps(ROUTE)}, noAsk: true}}); setCompact(true)"); await pg.wait_for_timeout(800)
        bases = await pg.evaluate("Object.keys(BASES)")
        bad = []
        for k in bases:
            await pg.evaluate(f"setBase('{k}')"); await pg.wait_for_timeout(250)
            r = await pg.evaluate(PROBE)
            ok = r.get('n', 0) >= 2 and r['worst'] < 1.5 and r['ends'] < 1.5 and r['above'] and r['under'] and r['sameParent'] and await pg.evaluate(f"baseKey === '{k}'")
            if not ok: bad.append((k, r))
        check(f'route in place on all {len(bases)} base maps', not bad, bad[:3])
        await pg.evaluate("setBase('ihm_mtb_he')")
        for b_ in (0, 37, 90, 180, 251):
            await pg.evaluate(f"map.setBearing({b_})"); await pg.wait_for_timeout(300)
            r = await pg.evaluate(PROBE)
            check(f'map turned {b_}°: route on the right place, turns with the map', r.get('n', 0) >= 2 and r['worst'] < 1.5 and r['ends'] < 1.5 and r['sameParent'], r)
            await pg.screenshot(path=os.path.join(SHOT, f'bearing-{b_}.png'))
        for o in ('north', 'compass', 'course'):
            await pg.evaluate(f"setOrientation('{o}')"); await pg.wait_for_timeout(400)
            r = await pg.evaluate(PROBE)
            check(f'orientation «{o}»: route on the right place', r.get('n', 0) >= 2 and r['worst'] < 1.5 and r['ends'] < 1.5, r)
        for z in (11, 14, 17, 19):
            await pg.evaluate(f"map.setZoom({z}, {{animate: false}})"); await pg.wait_for_timeout(300)
            r = await pg.evaluate(PROBE)
            check(f'zoom {z}: route on the right place', r.get('n', 0) >= 2 and r['worst'] < 1.5, r)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
