# «⟳ Кольцо от меня» (v88): a loop of the chosen length from where you are, back to the start; another variant on a second tap.
import asyncio, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
CAND = "(() => { const c = Plan.cand; if (!c) return null; const cum = cumDist(c.coords); return {len: cum[cum.length - 1], first: c.coords[0], last: c.coords[c.coords.length - 1], name: c.name, wps: Plan.wps.length, res: !document.getElementById('pl-result').hidden}; })()"
async def main():
    url = serve(8804)
    async with async_playwright() as p:
        for lang in ('ru', 'he'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), geo=(32.09, 34.88))
            await pg.wait_for_timeout(1500)
            await pg.click('.tabs [data-tab="routes"]'); await pg.click('#rseg [data-r="plan"]'); await pg.wait_for_timeout(300)
            check(f'{lang}: «Кольцо от меня» is on the planner', await pg.is_visible('#pl-loop') and await pg.is_visible('#pl-loop-km'))
            if lang == 'he': await b.close(); continue
            await pg.fill('#pl-loop-km', '25'); await pg.click('#pl-loop')
            await pg.wait_for_function("Plan.cand && Plan.cand.name.startsWith('Кольцо')", timeout=20000)
            c = await pg.evaluate(CAND)
            here = [32.09, 34.88]; d0 = math.hypot((c['first'][0] - here[0]) * 110540, (c['first'][1] - here[1]) * 94300); d1 = math.hypot((c['last'][0] - here[0]) * 110540, (c['last'][1] - here[1]) * 94300)
            check('loop starts and ends where you are', d0 < 30 and d1 < 30, {'d_start': round(d0), 'd_end': round(d1)})
            check('loop length within ~12 % of 25 km', abs(c['len'] - 25000) / 25000 <= 0.12, round(c['len']))
            check('result shown with «Начать», points editable (3 + finish)', c['res'] and c['wps'] == 4, c)
            first = c['first']; mid1 = await pg.evaluate("Plan.wps[1].ll")
            await pg.click('#pl-loop'); await pg.wait_for_function(f"Plan.wps.length && Math.abs(Plan.wps[1].ll[0] - {mid1[0]}) > 1e-4", timeout=20000)
            mid2 = await pg.evaluate("Plan.wps[1].ll")
            check('second tap: another variant', abs(mid2[0] - mid1[0]) > 1e-4 or abs(mid2[1] - mid1[1]) > 1e-4, {'v1': mid1, 'v2': mid2})
            # Direction «Восток»: the far point is east of the start.
            await pg.click('#pl-loop-dir [data-d="90"]'); await pg.click('#pl-loop'); await pg.wait_for_timeout(3000)
            far = await pg.evaluate("Plan.wps[1].ll")
            check('direction «Восток»: the loop goes east', far[1] > 34.88 + 0.02, far)
            await pg.click('#r-nav'); await pg.wait_for_timeout(800)
            st = await pg.evaluate("({route: !!Nav.route, loopy: Nav.loopy, name: Nav.route && Nav.route.name})")
            check('«Начать»: navigation on the loop (start = finish)', st['route'] and st['loopy'], st)
            check('no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
