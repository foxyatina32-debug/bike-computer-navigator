# v151 (audit R11): the History does not pile up small maps. 45 rides; the History drawn again and again: the window's
# resize listeners and the live small maps stay the same (they grew by 2 with every redraw: 6 → 8 → 10 → 12 → 14);
# the list comes in pages of 30 with «Показать ещё (15)», which shows the rest. ru / en.
# Run: python3 tests/histmaps.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
COUNT = """(() => { if (!window.__rz) { window.__rz = new Set(); const a = window.addEventListener, r = window.removeEventListener;
  window.addEventListener = function (t, f, o) { if (t === 'resize') window.__rz.add(f); return a.call(this, t, f, o); };
  window.removeEventListener = function (t, f, o) { if (t === 'resize') window.__rz.delete(f); return r.call(this, t, f, o); }; } return 0; })()"""

async def main():
    url = serve(8925)
    async with async_playwright() as p:
        for lang in ('ru', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), geo=(32.09, 34.88))
            await pg.wait_for_timeout(1000)
            await pg.evaluate("""(async () => { const now = Date.now(); for (let i = 0; i < 45; i++) { const t0 = now - (i + 1) * 864e5;
              await DB.put('rides', { id: 'h' + i, name: 'Поездка ' + i, start: t0, end: t0 + 36e5, type: 'bike', dist: 5000 + i, movingMs: 18e5,
                track: [[32.09, 34.88 + i * 1e-3, 30, t0], [32.1, 34.89 + i * 1e-3, 40, t0 + 18e5]] }); } })()""")
            await pg.evaluate(COUNT)
            await pg.evaluate("HS.per = 'all'; showTab('history')"); await pg.wait_for_timeout(1500)
            n = []
            for _ in range(4):
                await pg.evaluate("renderRides()"); await pg.wait_for_timeout(700)
                n.append(await pg.evaluate("({ rz: window.__rz.size, maps: typeof HMAPS === 'undefined' ? 0 : HMAPS.length })"))
            check(f'[{lang}] the History drawn again and again: resize listeners and small maps do not pile up', len(set(x['rz'] for x in n)) == 1 and all(x['maps'] <= 30 for x in n), n)
            st = await pg.evaluate("({ cards: document.querySelectorAll('#ride-list .rideit').length, more: (document.getElementById('h-more') || {}).textContent || '' })")
            want = 'Показать ещё (15)' if lang == 'ru' else 'Show more (15)'
            check(f'[{lang}] 45 rides: 30 cards first, «{want}»', st['cards'] == 30 and st['more'] == want, st)
            await pg.evaluate("document.getElementById('h-more').click()"); await pg.wait_for_timeout(700)
            st = await pg.evaluate("({ cards: document.querySelectorAll('#ride-list .rideit').length, more: !!document.getElementById('h-more') })")
            check(f'[{lang}] «Показать ещё»: all 45, no button left', st['cards'] == 45 and not st['more'], st)
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
