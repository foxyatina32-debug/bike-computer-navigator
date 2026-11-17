# v114 — a clean map. One «где я» button (the arrow): 1st tap — follow me, 2nd — north up ⇄ heading up; no «моё место»
# crosshair and no «За мной» in the bottom row. The bottom row: «Старт» alone before the ride, «Пауза» + «Стоп» during it.
# «Голос» lives as 🔊 in the route banner. Nothing recorded → the folded strip, not four zero cards (opened by hand stays
# open). Navigating — no «+ Маршрут» and «⟳ Кольцом», no greeting over the banner. Messages above the bottom panel.
# Landscape keeps «За мной» in its side column (the arrow is not shown there). Russian / Hebrew / English, SE and 15 Pro.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.09 + i * 0.0005, 34.88, 20] for i in range(40)]
VIS = "(k => { const e = document.querySelector(k); if (!e) return false; const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return !!(r.width && r.height) && cs.visibility !== 'hidden' && cs.display !== 'none'; })"
BOX = "(k => { const r = document.querySelector(k).getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })"
async def vis(pg, k): return await pg.evaluate(VIS + f"('{k}')")
async def main():
    url = serve(8861); m = Mocks()
    async with async_playwright() as p:
        for lang, vp in (('ru', (393, 852)), ('he', (375, 667)), ('en', (393, 852))):
            tag = f'{lang} {vp[0]}×{vp[1]}'
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, viewport=vp, geo=(32.0901, 34.88))
            await pg.wait_for_timeout(1500)
            st = await pg.evaluate("({c: hudCompact, st: Ride.status})")
            check(f'{tag}: nothing recorded → folded strip with ▶', st['c'] and st['st'] == 'idle' and await vis(pg, '#m-play') and not await vis(pg, '#c-play'), st)
            check(f'{tag}: one «где я» on the map — no crosshair', await vis(pg, '#c-loc') and not await vis(pg, '#z-me') and await vis(pg, '#z-in'))
            await pg.click('#hud-max'); await pg.wait_for_timeout(400)
            row = await pg.evaluate("['c-play','c-stop','c-follow','c-voice'].filter(id => " + VIS + "('#' + id))")
            pb = await pg.evaluate(BOX + "('#c-play')"); hud = await pg.evaluate(BOX + "('.ctrls')")
            check(f'{tag}: opened by hand — only «Старт», full width, tall', row == ['c-play'] and pb[2] - pb[0] > (hud[2] - hud[0]) * .9 and pb[3] - pb[1] >= 54, [row, pb, hud])
            await pg.click('#c-play'); await pg.wait_for_timeout(500)
            row = await pg.evaluate("['c-play','c-stop','c-follow','c-voice'].filter(id => " + VIS + "('#' + id))")
            a, s2 = await pg.evaluate(BOX + "('#c-play')"), await pg.evaluate(BOX + "('#c-stop')")
            check(f'{tag}: recording — «Пауза» and «Стоп», side by side, equal', row == ['c-play', 'c-stop'] and abs((a[2] - a[0]) - (s2[2] - s2[0])) < 3 and await pg.evaluate("!hudCompact"), [row, a, s2])
            await pg.click('#c-play'); await pg.wait_for_timeout(300)
            check(f'{tag}: paused — «Продолжить» and «Стоп»', await pg.evaluate("Ride.status") == 'paused' and await vis(pg, '#c-stop'))
            await pg.click('#c-stop'); await pg.wait_for_timeout(200); await pg.click('#st-del'); await pg.click('#st-del'); await pg.wait_for_timeout(500)
            check(f'{tag}: ride deleted — idle, still open (opened by hand)', await pg.evaluate("Ride.status === 'idle' && !hudCompact") and not await vis(pg, '#c-stop'))
            # «где я»: follow, then rotate
            await pg.evaluate("map.panBy([400, 400], {animate: false}); setFollow(false); setOrientation('north', true)"); await pg.wait_for_timeout(300)
            await pg.click('#c-loc'); await pg.wait_for_timeout(400)
            f1 = await pg.evaluate("({f: GPS.follow, o: S.orient, d: map.distance(map.getCenter(), [GPS.fix.lat, GPS.fix.lon])})")
            await pg.click('#c-loc'); await pg.wait_for_timeout(400)
            f2 = await pg.evaluate("({f: GPS.follow, o: S.orient, t: document.getElementById('toast').textContent})")
            await pg.click('#c-loc'); await pg.wait_for_timeout(400)
            f3 = await pg.evaluate("({f: GPS.follow, o: S.orient})")
            cyr = any('Ѐ' <= ch <= 'ӿ' for ch in (f2['t'] or ''))
            check(f'{tag}: «где я» — 1st tap follows, 2nd turns the map by the phone compass, 3rd north up', f1['f'] and f1['o'] == 'north' and f2['f'] and f2['o'] == 'compass' and f3['o'] == 'north' and f2['t'] and cyr == (lang == 'ru'), [f1, f2, f3])
            # navigation: banner with 🔊, no «+ Маршрут» / «⟳ Кольцом»
            await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {json.dumps(ROUTE)}, noAsk: true}})"); await pg.wait_for_timeout(600)
            # v118: «⟳ Кольцом» may be offered for 15 s after the route is picked (small, temporary) — never as a permanent button
            await pg.evaluate("retHide()")
            check(f'{tag}: navigating — 🔊 in the banner, no «+ Маршрут», no permanent «⟳ Кольцом»', await vis(pg, '#nv-snd') and not await vis(pg, '#t-gpx') and not await vis(pg, '#t-ret'))
            v0 = await pg.evaluate("S.voice"); await pg.click('#nv-snd'); await pg.wait_for_timeout(300)
            st = await pg.evaluate("({v: S.voice, on: document.getElementById('nv-snd').classList.contains('on'), lab: document.getElementById('nv-snd').getAttribute('aria-label'), x: !!Nav.route})")
            check(f'{tag}: 🔊 switches the voice, the route stays', st['v'] == (not v0) and st['on'] == st['v'] and st['x'] and (lang == 'ru' or not any('Ѐ' <= ch <= 'ӿ' for ch in st['lab'])), st)
            await pg.click('#nv-snd'); await pg.wait_for_timeout(200)
            # message above the bottom panel, not over the banner
            await pg.evaluate("toast('x', 4000)"); await pg.wait_for_timeout(100)
            t, nb, hd = await pg.evaluate(BOX + "('#toast')"), await pg.evaluate(BOX + "('#navb')"), await pg.evaluate(BOX + "('#hud')")
            check(f'{tag}: messages sit above the bottom panel, clear of the banner', t[3] <= hd[1] and t[1] > nb[3], [t, nb, hd])
            await pg.evaluate("document.getElementById('hello').hidden = true; greet()"); await pg.wait_for_timeout(300)
            check(f'{tag}: no greeting over the route banner', await pg.evaluate("document.getElementById('hello').hidden"))
            await pg.evaluate("Nav.stop()"); await pg.wait_for_timeout(400)
            check(f'{tag}: navigation over — «+ Маршрут» back', await vis(pg, '#t-gpx'))
            if lang != 'ru':
                lab = await pg.evaluate("document.getElementById('c-loc').getAttribute('aria-label') + ' ' + [...document.querySelectorAll('label.chk')].find(l => l.querySelector('#s-zoombtns')).textContent")
                check(f'{tag}: new labels translated', not any('Ѐ' <= ch <= 'ӿ' for ch in lab), lab)
            check(f'{tag}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
        # landscape: the arrow is hidden there — «За мной» stays in the side column
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, viewport=(844, 390))
        await pg.wait_for_timeout(1200)
        check('landscape: «За мной» kept in the side column, no «Голос», «Стоп» only while riding', await vis(pg, '#c-follow') and not await vis(pg, '#c-voice') and not await vis(pg, '#c-stop'))
        check('landscape: no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
