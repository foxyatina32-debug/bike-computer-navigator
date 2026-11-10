# v109: the «Где я» button (back to my position) is on screen with the ride panel open and folded alike — visible, on top,
# overlapping nothing (the right-hand buttons step aside), and it works; iPhone SE, iPhone 15 Pro, landscape is the wide
# layout (it has «За мной» in its panel instead).
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
OVER = """(() => {
  const vis = e => { if (!e || e.hidden) return false; const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
    const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const sos = document.getElementById('c-loc'); if (!vis(sos)) return { sos: null };
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
    url = serve(8847); m = Mocks()
    async with async_playwright() as p:
        for name, vp in (('iPhone SE', (375, 667)), ('iPhone 15 Pro', (393, 852))):
            b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, viewport=vp)
            await pg.wait_for_timeout(1200)
            async def st(state):
                await pg.evaluate("placeGpxBtn()"); await pg.wait_for_timeout(500); r = await pg.evaluate(OVER)
                await pg.screenshot(path=os.path.join(SHOT, f"loc-{name.replace(' ', '')}-{state.replace(' ', '-').replace(',', '')}.png"))
                check(f'[{name}] {state}: «Где я» visible, on top, overlaps nothing', r['sos'] and r['onTop'] and r['inScreen'] and not r['hit'], r)
            await pg.evaluate("showTab('rec'); setCompact(false)"); await st('panel open')
            await pg.evaluate("setCompact(true)"); await st('panel folded')
            await pg.evaluate("setCompact(false); Ride.start()"); await st('recording, panel open')
            await pg.evaluate(ROUTE); await st('navigation, panel open')
            await pg.evaluate("setCompact(true)"); await st('navigation, panel folded')
            await pg.evaluate("setCompact(false)")
            # it works: map moved away → «Где я» → following again
            await pg.evaluate("setFollow(false); map.panBy([300, 300], {animate: false})"); await pg.wait_for_timeout(300)
            await pg.click('#c-loc'); await pg.wait_for_timeout(500)
            check(f'[{name}] tap on «Где я» with the panel open: the map follows me again', await pg.evaluate("GPS.follow === true"))
            check(f'[{name}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
