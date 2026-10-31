# v100 audit fixes: own sections (pieces of way the map lacks) go into the backup and come back on restore; the
# «Сохранить участок?» question no longer covers the ride panel or dims the map; ids are escaped in the lists and a
# backup with odd ids is not inserted.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
WAY = {'id': 'w1', 'coords': [[32.09, 34.88], [32.0905, 34.881], [32.091, 34.882]], 'len': 190, 'at': 1790000000000}

async def main():
    url = serve(8799)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url, Mocks())
        # ---- backup carries own sections ----
        await pg.evaluate(f"(async () => {{ await NewWays.init(); NewWays.ways = [{json.dumps(WAY)}]; await NewWays.store(); }})()")
        d = await pg.evaluate("(async () => JSON.parse(await (await makeBackupFile()).text()))()")
        check('backup file contains own sections', len(d.get('myWays') or []) == 1 and d['myWays'][0]['id'] == 'w1', d.get('myWays'))
        # ---- restore: sections merged back, odd ids skipped ----
        await pg.evaluate("(async () => { NewWays.ways = []; await NewWays.store(); })()")
        bad = '"><img src=x onerror="window.__pwned=1">'
        bk = {'app': 'velokomp', 'ver': 2, 'rides': [{'id': bad, 'name': 'x', 'start': 1, 'track': []}, {'id': 'ok1', 'name': 'Норм', 'start': 1790000000000, 'end': 1790000600000, 'dist': 1000, 'movingMs': 600000, 'track': [[32.09, 34.88, 0, 1790000000000], [32.1, 34.88, 0, 1790000600000]]}],
              'routes': [], 'myWays': [WAY, {'id': 'w2', 'coords': [[95, 34.8], [32.1, 34.8]]}]}
        path = '/tmp/claude-0/-home-claude/dbab2f42-fb46-580b-9989-372f3297d602/scratchpad/bk100.json'
        open(path, 'w', encoding='utf-8').write(json.dumps(bk, ensure_ascii=False))
        await pg.evaluate("window.__lastToasts = ''")
        await pg.set_input_files('#bk-file', path); await pg.wait_for_timeout(1500)
        st = await pg.evaluate("(async () => ({ways: NewWays.ways.map(w => w.id), rides: (await DB.all('rides')).map(r => r.id), t: window.__lastToasts, saved: ((await DB.get('kv', 'myWays')) || {}).ways.length}))()")
        check('restore: own section back on the phone and saved, a bad one (latitude 95) skipped', st['ways'] == ['w1'] and st['saved'] == 1 and '1 участок' in st['t'], st)
        check('restore: a ride with an odd id is skipped, a normal one restored', 'ok1' in st['rides'] and bad not in st['rides'], st)
        # ---- ids escaped in lists ----
        await pg.evaluate(f"DB.put('rides', {{id: 'q\"x', name: 'Кавычка', start: 1790000000000, end: 1790000600000, dist: 500, movingMs: 300000, track: []}})")
        await pg.click('.tabs [data-tab="history"]'); await pg.wait_for_timeout(1200)
        st = await pg.evaluate("({card: !!document.querySelector('[data-open=\\'q\"x\\']'), pwned: !!window.__pwned})")
        check('history: an id with a quote stays one attribute (escaped), nothing injected', st['card'] and not st['pwned'], st)
        await pg.click('.tabs [data-tab="rec"]'); await pg.wait_for_timeout(400)
        # ---- the question floats over the map ----
        await pg.evaluate("NewWays.done({pts: [[32.09, 34.88], [32.0904, 34.8805], [32.0908, 34.881], [32.0912, 34.8815], [32.0916, 34.882]], off: 8})")
        await pg.wait_for_timeout(400)
        st = await pg.evaluate("""(() => { const a = document.getElementById('ask-nw'), cs = getComputedStyle(a), box = a.querySelector('.box').getBoundingClientRect(),
            hud = document.getElementById('hud').getBoundingClientRect(), top = document.querySelector('.top').getBoundingClientRect(),
            hit = document.elementFromPoint(hud.left + hud.width / 2, hud.top + 20), mapHit = document.elementFromPoint(innerWidth / 2, box.top - 12);
            return {shown: !a.hidden, bg: cs.backgroundColor, overHud: box.bottom > hud.top, underTop: box.top < top.bottom, hudTap: !!(hit && hit.closest('#hud')), mapTap: !!(mapHit && mapHit.closest('#map'))}; })()""")
        check('«Сохранить участок?» shown without dimming; ride panel and map stay visible and tappable', st['shown'] and st['bg'] in ('rgba(0, 0, 0, 0)', 'transparent') and not st['overHud'] and not st['underTop'] and st['hudTap'] and st['mapTap'], st)
        await pg.click('#nw-no'); await pg.wait_for_timeout(300)
        check('«Нет» closes it', await pg.evaluate("document.getElementById('ask-nw').hidden"))
        for vp in [(320, 568)]:
            await pg.set_viewport_size({'width': vp[0], 'height': vp[1]}); await pg.wait_for_timeout(300)
            await pg.evaluate("NewWays.done({pts: [[32.09, 34.88], [32.0904, 34.8805], [32.0908, 34.881], [32.0912, 34.8815], [32.0916, 34.882]], off: 8})"); await pg.wait_for_timeout(400)
            st = await pg.evaluate("(() => { const b = document.querySelector('#ask-nw .box').getBoundingClientRect(), y = document.getElementById('nw-yes').getBoundingClientRect(), n = document.getElementById('nw-no').getBoundingClientRect(); return {top: b.top, bottom: b.bottom, h: innerHeight, yes: y.bottom <= innerHeight && y.top >= 0, no: n.bottom <= innerHeight && n.top >= 0}; })()")
            check(f'small screen {vp[0]}×{vp[1]}: both buttons on screen', st['yes'] and st['no'], st)
            await pg.click('#nw-no')
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
