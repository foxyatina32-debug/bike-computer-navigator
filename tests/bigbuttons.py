# v151 (audit R18): riding, the main buttons are big enough for a gloved hand on a bumpy trail — pause / stop 48 px,
# the microphone, compass, zoom and «where am I» 48 px, opening the panel 44 px, the legend tab 28 × 44 — in every look,
# with nothing overlapping; standing (no ride, no route) they stay compact. On a small screen (320 × 568) a message does
# not cover the title of the «finish the ride» dialog: it waits and shows when the dialog closes.
# Run: python3 tests/bigbuttons.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.09 + i * 0.0005, 34.88, 20] for i in range(40)]
WANT = {'m-play': 48, 'm-stop': 48, 'hud-max': 44, 't-mic': 48, 't-compass': 48, 'z-in': 48, 'z-out': 48, 'c-loc': 48}
SIZES = """(ids => { const o = {}; for (const id of ids) { const el = document.getElementById(id); if (!el || el.hidden || !el.getClientRects().length) continue; const r = el.getBoundingClientRect(); o[id] = [Math.round(r.width), Math.round(r.height)]; } return o; })"""
OVER = """(() => { const ids = ['m-play','m-stop','hud-max','t-mic','t-compass','z-in','z-out','z-me','c-loc','legend-tab','t-layers','t-mode','t-3d','sos','navb','gsearch'], R = [];
  for (const id of ids) { const el = document.getElementById(id); if (!el || el.hidden || !el.getClientRects().length || getComputedStyle(el).opacity === '0') continue; R.push([id, el.getBoundingClientRect()]); }
  const bad = []; for (let i = 0; i < R.length; i++) for (let j = i + 1; j < R.length; j++) { const a = R[i][1], b = R[j][1]; if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) bad.push(R[i][0] + '×' + R[j][0]); } return bad; })()"""
HIDE = "const h = document.getElementById('hello'); if (h) { h.classList.remove('on'); h.hidden = true; } 0"

async def main():
    url = serve(8937)
    async with async_playwright() as p:
        for theme in ('dark', 'sun', 'md'):
            b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
            await pg.wait_for_timeout(1200)
            await pg.evaluate(HIDE); await pg.evaluate(f"S.theme = {json.dumps(theme)}; saveS(); applyTheme(); document.getElementById('legend-tab').hidden = false; 0")
            idle = await pg.evaluate(SIZES + "(['t-mic', 't-compass', 'm-play'])")
            await pg.evaluate(f"Nav.set({{ name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true }}); Ride.start(); syncRideMode()"); await pg.wait_for_timeout(700)
            sz = await pg.evaluate(SIZES + f"({json.dumps(list(WANT) + ['legend-tab'])})")
            small = {k: v for k, v in sz.items() if k in WANT and (v[0] < WANT[k] or v[1] < WANT[k])}
            lt = sz.get('legend-tab', [0, 0])
            check(f'[{theme}] riding: the main buttons 48 px (the panel\'s opener 44), the legend tab 28 × 44', not small and len([k for k in WANT if k in sz]) >= 7 and lt[0] >= 28 and lt[1] >= 44, (small, sz))
            check(f'[{theme}] riding: nothing overlaps', not await pg.evaluate(OVER), await pg.evaluate(OVER))
            check(f'[{theme}] standing (no ride, no route) the buttons stay compact', all(v[0] <= 44 for v in idle.values()), idle)
            await pg.evaluate("Nav.stop(); Ride.stop(false)")
            check(f'[{theme}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
        # ---- a small screen: a message and the «finish the ride» dialog
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), viewport=(320, 568), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1200); await pg.evaluate(HIDE); await pg.evaluate("S.compass = false; Ride.start()"); await pg.wait_for_timeout(1500)   # no compass question on the taps
        await pg.evaluate("document.getElementById('c-stop').click(); toast('Длинное уведомление в несколько строк, чтобы проверить, что заголовок диалога остаётся виден', 2000)"); await pg.wait_for_timeout(400)
        st = await pg.evaluate("""(() => { const t = document.getElementById('toast'), r = t.getBoundingClientRect(), h = document.querySelector('#ask-stop h2').getBoundingClientRect();
          return { vis: getComputedStyle(t).visibility, hidden: t.hidden, over: !t.hidden && getComputedStyle(t).visibility !== 'hidden' && r.bottom > h.top && r.top < h.bottom }; })()""")
        check('320 × 568: the message does not cover the title of «finish the ride»', not st['over'], st)
        await pg.wait_for_timeout(2500)
        await pg.evaluate("document.getElementById('st-cont') ? document.getElementById('st-cont').click() : document.getElementById('ask-stop').hidden = true"); await pg.wait_for_timeout(400)
        st = await pg.evaluate("({ vis: getComputedStyle(document.getElementById('toast')).visibility, hidden: document.getElementById('toast').hidden, txt: document.getElementById('toast').textContent })")
        check('…it shows when the dialog closes (not lost)', not st['hidden'] and st['vis'] == 'visible' and 'Длинное уведомление' in st['txt'], st)
        check('no JS errors (small screen)', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
