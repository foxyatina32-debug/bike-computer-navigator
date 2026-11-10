# v102 audit fixes: ride recording starts by itself when you start moving (bike or on foot, not in Car mode, not right
# after ■, can be turned off) with the first seconds kept; a reminder when riding on a manual pause; personal API keys
# stay out of the backup file (an old copy with keys still restores them); «Что рядом» has its own Google counter
# (1 000 free a month); a storage read error is not shown as «no rides»; no Strava text left; Hebrew and English.
import asyncio, sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
FIX = "((lat, lon, acc, spd, t) => onFix({coords: {latitude: lat, longitude: lon, accuracy: acc, altitude: 30, altitudeAccuracy: 5, speed: spd, heading: null}, timestamp: t}))(%s, %s, %s, %s, %s)"
STUB = """window.__shared = null; navigator.canShare = () => true;
  navigator.share = async d => { window.__shared = await d.files[0].text(); window.__fname = d.files[0].name; }; 0"""
M_LAT = 110540

async def ride(pg, t0, sec, spd=5.0, lat0=32.09):
    # northwards at spd m/s, one fix a second, good GPS with the speed reported (as on iPhone)
    for i in range(sec):
        await pg.evaluate(FIX % (lat0 + spd * i / M_LAT, 34.88, 5, spd, t0 + i * 1000))
    return lat0 + spd * sec / M_LAT

async def fresh(p, url, m, lang='ru'):
    b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
    await pg.wait_for_timeout(800)
    await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)")
    return b, pg, log

async def main():
    url = serve(8835); m = Mocks()
    async with async_playwright() as p:
        # 1. Riding off without ▶: recording starts by itself, the first seconds are in the ride.
        b, pg, log = await fresh(p, url, m)
        t0 = await pg.evaluate("Date.now()")
        await ride(pg, t0, 10)
        check('first 10 s of riding: not yet recording', await pg.evaluate("Ride.status") == 'idle')
        await ride(pg, t0 + 10000, 20, lat0=32.09 + 50 / M_LAT)
        r = await pg.evaluate("({st: Ride.status, n: Ride.track.length, d: Math.round(Ride.dist), start: Ride.startTs, toast: window.__lastToasts, saved: 0})")
        check('after ~20 s of riding at 18 km/h: recording on by itself', r['st'] == 'rec', r)
        check('the ride starts at the first moving second, not when recording switched on', abs(r['start'] - t0) <= 2000 and r['d'] >= 120 and r['n'] >= 20, r)
        check('toast says recording is on and where to turn it off', 'запись поездки включена' in r['toast'] and 'Настройках' in r['toast'], r['toast'][-160:])
        saved = await pg.evaluate("DB.get('kv', 'currentRide').then(x => !!(x && x.v && x.v.track.length))")
        check('the started ride is saved to the phone at once (survives a reload)', saved)
        # ■ → save; riding on right after does not start a new ride (15 min quiet)
        await pg.evaluate("Ride.stop(true)"); await pg.wait_for_timeout(300)
        t1 = await pg.evaluate("Date.now()")
        await ride(pg, t1, 40, lat0=32.10)
        check('after ■ and riding on: no new ride by itself for a while', await pg.evaluate("Ride.status") == 'idle')
        n = await pg.evaluate("DB.all('rides').then(a => a.length)")
        check('the stopped ride is in History', n == 1, n)
        await pg.evaluate("AutoRec.quietUntil = 0")
        # 2. Standing with GPS drift: never starts.
        t2 = await pg.evaluate("Date.now()")
        for i in range(40):
            await pg.evaluate(FIX % (32.11 + ((i * 7) % 11 - 5) / M_LAT, 34.88 + ((i * 3) % 7 - 3) / 94300, 15, 'null', t2 + i * 1000))
        check('standing 40 s with GPS drift: no recording', await pg.evaluate("Ride.status") == 'idle')
        # 3. Car mode: never starts.
        await pg.evaluate("S.act = 'car'; RO.mode = 'car'")
        t3 = await pg.evaluate("Date.now()")
        await ride(pg, t3, 40, spd=8, lat0=32.12)
        check('Car mode: no recording by itself', await pg.evaluate("Ride.status") == 'idle')
        await pg.evaluate("S.act = 'bike'; RO.mode = 'bike'")
        # 4. Faster than a bike (43+ km/h, e.g. in a car in bike mode): no recording.
        t4 = await pg.evaluate("Date.now()")
        await ride(pg, t4, 40, spd=16, lat0=32.13)
        check('moving at 58 km/h in bike mode: no recording', await pg.evaluate("Ride.status") == 'idle')
        # 5. Turned off in Settings.
        await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
        lbl = await pg.evaluate("document.getElementById('s-autorec').closest('label').textContent.trim()")
        check('Settings: switch «Начинать запись поездки, когда вы поехали», on by default', 'Начинать запись' in lbl and await pg.evaluate("document.getElementById('s-autorec').checked"), lbl)
        await pg.click('#s-autorec'); await pg.evaluate("showTab('map')")
        t5 = await pg.evaluate("Date.now()")
        await ride(pg, t5, 40, lat0=32.14)
        check('switched off: riding does not start recording', await pg.evaluate("Ride.status") == 'idle' and await pg.evaluate("lsGet('settings', {}).autorec") is False)
        await pg.evaluate("S.autorec = true; saveS()")
        # 6. On foot: a walking pace starts it too.
        await pg.evaluate("S.act = 'walk'; RO.mode = 'foot'")
        t6 = await pg.evaluate("Date.now()")
        await ride(pg, t6, 70, spd=1.4, lat0=32.15)
        check('on foot at 5 km/h: recording on by itself', await pg.evaluate("Ride.status") == 'rec')
        await pg.evaluate("Ride.stop(true)"); await pg.evaluate("AutoRec.quietUntil = 0; S.act = 'bike'; RO.mode = 'bike'")
        # 7. Manual pause and riding on: one reminder, the ride stays paused.
        await pg.evaluate("Ride.start()"); t7 = await pg.evaluate("Date.now()")
        la = await ride(pg, t7, 5, lat0=32.16); await pg.evaluate("Ride.pause(); window.__lastToasts = ''")
        await ride(pg, t7 + 5000, 75, lat0=la)
        r = await pg.evaluate("({st: Ride.status, t: window.__lastToasts})")
        check('riding on a manual pause for a minute: reminder «Запись на паузе», still paused', r['st'] == 'paused' and r['t'].count('Запись на паузе') == 1, r)
        await pg.evaluate("Ride.stop(true)")
        # 8. Google counter: «Что рядом» counted on its own, against 1 000.
        await pg.evaluate("localStorage.setItem('velo:gkey', JSON.stringify('AIzaTEST'))")
        await pg.evaluate("searchRiderPOIsNearby(32.09, 34.88).catch(() => {})"); await pg.wait_for_timeout(1900)
        await pg.evaluate("showTab('profile'); renderGUse()"); await pg.wait_for_timeout(200)
        u = await pg.evaluate("gUse.get()"); txt = await pg.evaluate("(document.getElementById('g-use') || {}).textContent || ''")
        check('«Что рядом» counted separately from search, limit ~1 000', u.get('nearby') == 1 and not u.get('places') and 'Что рядом: 1 из ~1' in txt, f"{u} · {txt[-120:]}")
        # 9. Backup without the keys; an old copy with keys still restores them.
        await pg.evaluate("lsSet('tfkey', 'TF-SECRET'); lsSet('mapykey', 'MAPY-SECRET')")
        await pg.evaluate(STUB); await pg.click('#bk-exp'); await pg.wait_for_timeout(600)
        raw = await pg.evaluate("window.__shared") or ''
        d = json.loads(raw) if raw else {}
        check('backup file: no Google / Thunderforest / Mapy.com keys', raw and 'AIzaTEST' not in raw and 'TF-SECRET' not in raw and 'MAPY-SECRET' not in raw and 'settings' in d.get('ls', {}), list(d.get('ls', {}))[:10])
        check('backup file named velocomp-backup-…', (await pg.evaluate("window.__fname") or '').startswith('velocomp-backup-'))
        await pg.evaluate("localStorage.removeItem('velo:gkey'); localStorage.removeItem('velo:tfkey')")
        old = {'app': 'velokomp', 'ver': 2, 'rides': [], 'routes': [], 'ls': {'gkey': json.dumps('AIzaOLD'), 'tfkey': json.dumps('TF-OLD')}}
        path = os.path.join(tempfile.mkdtemp(prefix='velo-'), 'old.json'); open(path, 'w').write(json.dumps(old))
        pg.on('dialog', lambda dl: asyncio.ensure_future(dl.accept()))
        await pg.set_input_files('#bk-file', path); await pg.wait_for_timeout(1500)
        k = await pg.evaluate("[lsGet('gkey', ''), lsGet('tfkey', '')]")
        check('an older copy that has keys: keys restored', k == ['AIzaOLD', 'TF-OLD'], k)
        check('no JS errors (riding, counter, backup)', not log['errors'], log['errors'][:3])
        await b.close()
        b, pg, log = await fresh(p, url, m)
        # 10. Read error in History: a clear message, not «no rides».
        await pg.evaluate("window.__allStrict = DB.allStrict; DB.allStrict = () => Promise.reject(new Error('io')); 0")
        await pg.evaluate("showTab('history')"); await pg.evaluate("renderRides()"); await pg.wait_for_timeout(300)
        h = await pg.evaluate("document.getElementById('ride-list').innerText")
        check('History, storage read error: «Не удалось прочитать поездки…»', 'Не удалось прочитать поездки' in h, h[:120])
        await pg.evaluate("DB.allStrict = window.__allStrict; 0")
        # 11. No Strava text; version 102.
        await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
        body = await pg.evaluate("document.body.innerText")
        check('Settings: no Strava mentioned for the own proxy', 'нужен для Strava' not in body and 'Strava настроена' not in body)
        b_ = await pg.evaluate("APP_BUILD")
        check(f'version text: v{b_} (current build)', f'навигация v{b_}' in body)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # 12. Hebrew and English: new texts translated.
        for lang in ('he', 'en'):
            b, pg, log = await fresh(p, url, m, lang)
            t0 = await pg.evaluate("Date.now()")
            await ride(pg, t0, 30)
            r = await pg.evaluate("({st: Ride.status, t: tr(window.__lastToasts)})")   # the hook keeps the text before toast() translates it
            await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
            lbl = await pg.evaluate("document.getElementById('s-autorec').closest('label').textContent")
            ver = await pg.evaluate("[...document.querySelectorAll('p.note')].map(x => x.textContent).find(x => x.includes('v' + APP_BUILD + ' ')) || ''")
            import re
            cyr = re.compile('[А-Яа-яЁё]')
            check(f'[{lang}] auto-start works, toast, switch and version text without Russian', r['st'] == 'rec' and not cyr.search(r['t']) and not cyr.search(lbl) and ver and not cyr.search(ver), (r['t'][-90:], lbl.strip(), ver[:60]))
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
