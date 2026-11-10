# v108: the SOS button never overlaps another control and is never hidden under one (the legend tab on the left edge in
# landscape; the open legend on iPhone SE; the Mapy.com logo, seen on a real iPhone) — iPhone SE, iPhone 15 Pro and landscape; map, ride panel, recording,
# navigation, compact panel, open legend.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
OVER = """(() => {
  const vis = e => { if (!e || e.hidden) return false; const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
    const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const sos = document.getElementById('t-sos'); if (!vis(sos)) return { sos: null };
  const a = sos.getBoundingClientRect(), hit = [];
  const cands = document.querySelectorAll('button, a, input, .hud, .mini, .navb, #elev, .leaflet-control, .lg-tab, .legend, .sheet, .geohelp, .toast, #r-card, .card, .slot, .dots, canvas');
  for (const e of cands) {
    if (e === sos || sos.contains(e) || e.contains(sos) || !vis(e)) continue;
    const r = e.getBoundingClientRect(), ix = Math.min(a.right, r.right) - Math.max(a.left, r.left), iy = Math.min(a.bottom, r.bottom) - Math.max(a.top, r.top);
    if (ix > 1 && iy > 1) hit.push((e.id ? '#' + e.id : e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : e.tagName) + ` ${Math.round(ix)}×${Math.round(iy)}`);
  }
  const top = document.elementFromPoint(a.left + a.width / 2, a.top + a.height / 2);
  return { sos: [Math.round(a.left), Math.round(a.top), Math.round(a.width), Math.round(a.height)], hit: [...new Set(hit)], onTop: !!top && (top === sos || sos.contains(top)), inScreen: a.top >= 0 && a.bottom <= innerHeight };
})()"""
ROUTE = "Nav.set({ name: 'Тест', noAsk: true, coords: [[32.09, 34.88], [32.10, 34.88], [32.11, 34.89], [32.12, 34.90]] })"

async def main():
    url = serve(8845); m = Mocks()
    async with async_playwright() as p:
        for name, vp in (('iPhone SE', (375, 667)), ('iPhone 15 Pro', (393, 852)), ('landscape', (852, 393))):
            b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, viewport=vp)
            await pg.wait_for_timeout(1200)
            async def st(state):
                await pg.wait_for_timeout(700); r = await pg.evaluate(OVER)
                check(f'[{name}] {state}: SOS visible, on top, overlaps nothing', r['sos'] and r['onTop'] and r['inScreen'] and not r['hit'], r)
            await st('map')
            await pg.evaluate("showTab('rec')"); await st('ride panel')
            await pg.evaluate("Ride.start()"); await st('recording')
            await pg.evaluate(ROUTE); await pg.evaluate("setFollow(true)"); await st('navigation')
            await pg.evaluate("setCompact(true)"); await st('navigation, compact panel')
            await pg.evaluate("setCompact(false); Legend.open = true; updateLegend()"); await st('legend open')
            # Mapy.com map: its logo sits bottom-left above the panel (their terms: always visible)
            await pg.evaluate("Legend.open = false; lsSet('mapykey', 'TEST'); setBase('mapy_basic')"); await pg.wait_for_timeout(400)
            check(f'[{name}] Mapy.com map: its logo shown', await pg.evaluate("!!document.getElementById('mapy-logo') && !document.getElementById('mapy-logo').hidden"))
            await st('Mapy.com map (logo)')
            await pg.evaluate("Nav.stop(); Ride.stop(false); Ride.stop(false)"); await pg.wait_for_timeout(500); await st('Mapy.com map, no ride')
            check(f'[{name}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
