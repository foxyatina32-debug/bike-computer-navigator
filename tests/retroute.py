# Any route → «Туда и обратно» / «Назад другой дорогой» (v89): on the planner result and during navigation.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
CAND = "(() => { const c = Plan.cand; const cum = cumDist(c.coords); return {len: Math.round(cum[cum.length - 1]), d0: Math.round(hav(c.coords[0], c.coords[c.coords.length - 1])), loop: c.loop, name: c.name, note: document.getElementById('r-ret-note').hidden ? '' : document.getElementById('r-ret-note').textContent, on: document.querySelector('#r-ret .on').dataset.k}; })()"
async def main():
    url = serve(8806)
    async with async_playwright() as p:
        m = Mocks()
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(32.09, 34.88))
        await pg.wait_for_timeout(1500)
        await pg.click('.tabs [data-tab="routes"]'); await pg.click('#rseg [data-r="plan"]'); await pg.wait_for_timeout(300)
        await pg.evaluate("Plan.wps = []; addWp([32.12, 34.90], 'Точка Б'); buildPlan()")
        await pg.wait_for_function("Plan.cand && !document.getElementById('pl-result').hidden", timeout=15000)
        one = await pg.evaluate(CAND)
        check('built A→B: switch shown, «В одну сторону» on', await pg.is_visible('#r-ret') and one['on'] == 'one' and one['d0'] > 1000, one)
        await pg.click('#r-ret [data-k="back"]'); await pg.wait_for_function("Plan.cand.name.includes('туда и обратно')", timeout=15000)
        bk = await pg.evaluate(CAND)
        check('«Туда и обратно»: twice the length, ends at the start', abs(bk['len'] - 2 * one['len']) < 30 and bk['d0'] < 5 and bk['loop'], bk)
        n0 = sum('nogos=' in u for u in m.calls)
        await pg.click('#r-ret [data-k="loop"]'); await pg.wait_for_function("Plan.cand.name.includes('кольцом')", timeout=15000)
        lp = await pg.evaluate(CAND)
        check('«Назад другой дорогой»: the way back asked to avoid the way there (no-go areas), ends at the start', sum('nogos=' in u for u in m.calls) > n0 and lp['d0'] < 5 and lp['loop'], lp)
        check('no other way here (test router goes straight back): says so', 'почти тем же путём' in lp['note'], lp['note'])
        await pg.click('#r-ret [data-k="one"]'); await pg.wait_for_function("document.querySelector('#r-ret .on').dataset.k === 'one'", timeout=15000)
        o2 = await pg.evaluate(CAND)
        check('back to «В одну сторону»: the original route again', o2['len'] == one['len'] and not o2['loop'], o2)
        await pg.click('#r-ret [data-k="back"]'); await pg.wait_for_function("Plan.cand.name.includes('туда и обратно')", timeout=15000)
        await pg.click('#r-nav'); await pg.wait_for_timeout(800)
        st = await pg.evaluate("({route: !!Nav.route, loopy: Nav.loopy, name: Nav.route && Nav.route.name})")
        check('«Начать» on «туда и обратно»: navigation here, start = finish', st['route'] and st['loopy'], st)
        # During navigation: a one-way GPX track → there and back.
        trk = [[32.09 + i * 0.0005, 34.88, 40] for i in range(40)]
        await pg.evaluate(f"Nav.set({{name: 'GPX трек', coords: {json.dumps(trk)}, noAsk: true}})"); await pg.wait_for_timeout(400)
        t0 = await pg.evaluate("Nav.route.total")
        await pg.evaluate("navReturn('back')"); await pg.wait_for_function("Nav.route.name.includes('туда и обратно')", timeout=10000)
        t1 = await pg.evaluate("({t: Nav.route.total, d0: hav(Nav.route.coords[0], Nav.route.coords[Nav.route.coords.length - 1]), loopy: Nav.loopy})")
        check('during navigation «⇄ Туда и обратно»: the track doubles and returns to its start', abs(t1['t'] - 2 * t0) < 30 and t1['d0'] < 5 and t1['loopy'], t1)
        await pg.evaluate(f"Nav.set({{name: 'GPX трек', coords: {json.dumps(trk)}, noAsk: true}})"); await pg.wait_for_timeout(300)
        await pg.evaluate("navReturn('loop')"); await pg.wait_for_function("Nav.route.name.includes('кольцом')", timeout=15000)
        check('during navigation «⟳ Назад другой дорогой»: route back to the start added', await pg.evaluate("hav(Nav.route.coords[0], Nav.route.coords[Nav.route.coords.length - 1]) < 5"))
        await pg.evaluate("navReturn('back')"); await pg.wait_for_timeout(500)
        check('already a loop: not doubled again', 'уже возвращается' in await pg.evaluate("window.__lastToasts"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
