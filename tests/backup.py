# Simple backup: «📦 Сохранить копию» (share menu → Files / iCloud), weekly reminder, full restore. Run: python3 tests/backup.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
SEED = """(async () => { const now = Date.now();
  await DB.put('routes', { id: 'rt1', name: 'Бен-Шемен', coords: [[32,34.9,50],[32.01,34.91,60]], dist: 1400, asc: 10, created: now, wpts: [] });
  await DB.put('rides', { id: 'rd1', name: 'Поездка', start: now - 3600e3, end: now, type: 'bike', dist: 1400, movingMs: 600000, max: 8, asc: 10, desc: 5, track: [[32,34.9,50,now-3600e3],[32.01,34.91,60,now]] });
  lsSet('dashSlots', ['grade','dist','speed','avg','max','alt','asc','desc','rem','clock','tleft','eta']); lsSet('gsess2', {x: 1}); })()"""
STUB = """window.__shared = null; window.__cancel = false; navigator.canShare = () => true;
  navigator.share = async d => { if (window.__cancel) { const e = new Error('x'); e.name = 'AbortError'; throw e; } window.__shared = await d.files[0].text(); window.__fname = d.files[0].name; }; 0"""

async def main():
    url = serve(8780)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks())
        await pg.evaluate(SEED); await pg.evaluate(STUB)
        await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
        t0 = await pg.evaluate("document.getElementById('bk-last').textContent")
        check('Profile: «📦 Сохранить копию», no copy yet', 'Копий ещё не было' in t0 and 'Сохранить копию' in await pg.evaluate("document.getElementById('bk-exp').textContent"), t0)
        await pg.evaluate("window.__cancel = true"); await pg.click('#bk-exp'); await pg.wait_for_timeout(300)
        check('cancelled share → not counted as a copy', not await pg.evaluate("lsGet('lastBackup', 0)"))
        await pg.evaluate("window.__cancel = false"); await pg.click('#bk-exp'); await pg.wait_for_timeout(500)
        raw = await pg.evaluate("window.__shared"); d = json.loads(raw)
        check('copy file: rides, routes, settings, card layout; no temporary keys', d['app'] == 'velokomp' and len(d['rides']) == 1 and len(d['routes']) == 1 and 'dashSlots' in d['ls'] and 'settings' in d['ls'] and 'gsess2' not in d['ls'] and (await pg.evaluate("window.__fname")).startswith('velokomp-backup-'), list(d['ls'])[:8])
        t1 = await pg.evaluate("document.getElementById('bk-last').textContent")
        check('last copy date shown', t1.startswith('Последняя копия:'), t1)
        open(os.path.join(SHOT, 'backup.json'), 'w').write(raw)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()

        # Reminder: data and no copy for a week → asks (not during a ride); «через неделю» snoozes
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks())
        await pg.evaluate(SEED); await pg.evaluate("lsSet('lastBackup', Date.now() - 8 * 864e5)")
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(7000)
        nag = await pg.evaluate("!document.getElementById('ask-backup').hidden && document.getElementById('bkn-info').textContent")
        check('after a week: reminder with what is at stake', nag and '1 поездка и 1 маршрут' in nag, nag)
        await pg.screenshot(path=os.path.join(SHOT, 'backup-nag.png'))
        await pg.click('#bkn-week')
        snooze = await pg.evaluate("(lsGet('bkNag', 0) - Date.now()) / 864e5")
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(7000)
        check('«Напомнить через неделю» → quiet for 7 days', 6.9 < snooze < 7.1 and await pg.evaluate("document.getElementById('ask-backup').hidden"), round(snooze, 2))
        await pg.evaluate("lsSet('bkNag', 0)"); await pg.click('#c-play'); await pg.evaluate("backupNag()"); await pg.wait_for_timeout(300)
        check('never during a ride', await pg.evaluate("document.getElementById('ask-backup').hidden"))
        await b.close()

        # New phone: restore from the file → routes, rides and settings back
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks())
        await pg.evaluate("showTab('profile')")
        await pg.set_input_files('#bk-file', os.path.join(SHOT, 'backup.json')); await pg.wait_for_timeout(3500)
        await pg.wait_for_function('window.__appReady === true', timeout=20000); await pg.wait_for_timeout(500)
        st = await pg.evaluate("Promise.all([DB.all('routes'), DB.all('rides')]).then(([a, b]) => ({ routes: a.length, rides: b.length, slot0: document.querySelector('.slot').dataset.k }))")
        check('restore on a new phone: routes, rides, card layout', st['routes'] == 1 and st['rides'] == 1 and st['slot0'] == 'grade', st)
        check('no JS errors (restore)', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
