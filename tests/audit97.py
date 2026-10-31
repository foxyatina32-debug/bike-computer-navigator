# v97 audit fixes: location banner per platform with «Повторить», no endless «Жду GPS…» when location is denied,
# last known position for planning, 3D button dimmed offline, «В поездке» mode hides extra map buttons on the move.
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
VIS = "id => { const e = document.getElementById(id); return !!e && !e.hidden && getComputedStyle(e).opacity !== '0' && getComputedStyle(e).pointerEvents !== 'none'; }"

async def main():
    url = serve(8797)
    async with async_playwright() as p:
        # ---- location denied → banner, retry ----
        b, ctx, pg, log = await open_app(p, url, Mocks())
        await ctx.clear_permissions()
        await pg.evaluate("GPS.fix = null; geoRetry()"); await pg.wait_for_timeout(800)
        st = await pg.evaluate("({ban: !document.getElementById('geohelp').hidden, how: document.getElementById('gh-how').textContent, denied: GPS.denied})")
        check('denied: banner shown with the iPhone Safari steps', st['ban'] and st['denied'] and 'Настройки веб-сайта' in st['how'], st)
        await pg.click('#gh-x'); await pg.wait_for_timeout(200)
        await pg.evaluate("window.__lastToasts = ''")
        await pg.click('#z-me'); await pg.wait_for_timeout(800)
        st = await pg.evaluate("({ban: !document.getElementById('geohelp').hidden, t: window.__lastToasts})")
        check('denied: «моё место» opens the banner, not «Жду GPS…»', st['ban'] and 'Жду GPS' not in st['t'], st)
        await pg.click('#gh-retry'); await pg.wait_for_timeout(800)
        check('«Повторить» while still denied: banner comes back', await pg.evaluate("!document.getElementById('geohelp').hidden && GPS.denied"))
        await ctx.grant_permissions(['geolocation'])
        await pg.wait_for_function("!!GPS.fix", timeout=8000)
        st = await pg.evaluate("({ban: !document.getElementById('geohelp').hidden, denied: GPS.denied, last: lsGet('lastFix', null)})")
        check('allowed in settings: picked up by itself, banner gone, position remembered', not st['ban'] and not st['denied'] and st['last'] and abs(st['last']['lat'] - 32.09) < 1e-3, st)
        how = await pg.evaluate("""(() => { const r = {}, d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'userAgent');
          for (const [k, ua] of Object.entries({chrome: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0 Mobile/15E148 Safari/604.1',
              android: 'Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36', pc: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0'})) {
            Object.defineProperty(navigator, 'userAgent', {value: ua, configurable: true}); r[k] = geoPlatform() + ': ' + GEO_HOW[geoPlatform()]; }
          delete navigator.userAgent; return r; })()""")
        check('Chrome on iPhone: steps for Settings → Chrome', how['chrome'].startswith('ios-other') and 'Chrome → Геопозиция' in how['chrome'], how['chrome'])
        check('Android and computer get their own steps', how['android'].startswith('android') and how['pc'].startswith('desktop'), how)
        # ---- planning without a fix: last known position (≤ 30 min), else wait ----
        r = await pg.evaluate("""(() => { const f = GPS.fix; GPS.fix = null;
          lsSet('lastFix', {lat: 32.1, lon: 34.9, t: Date.now() - 5 * 60e3}); const a = planStart();
          lsSet('lastFix', {lat: 32.1, lon: 34.9, t: Date.now() - 2 * 3600e3}); const b = planStart();
          GPS.fix = f; return {a, b, t: window.__lastToasts}; })()""")
        check('no fix: planning starts from the last known point, older than 30 min is not used', r['a'] == [32.1, 34.9] and r['b'] is None and 'последнюю известную' in r['t'], r)
        # ---- «Точная геопозиция» off ----
        r = await pg.evaluate("""(() => { const fx = (acc, k) => onFix({coords: {latitude: 32.09, longitude: 34.88, accuracy: acc, altitude: null, altitudeAccuracy: null, speed: null, heading: null}, timestamp: Date.now() + k});
          fx(3000, 1); const one = !document.getElementById('geohelp').hidden; fx(3000, 2); fx(3000, 3);
          const g = document.getElementById('geohelp'), a = {one, ban: !g.hidden, kind: g.dataset.kind, t: document.getElementById('gh-t').textContent, how: document.getElementById('gh-how').textContent, retry: !document.getElementById('gh-retry').hidden};
          fx(8, 4); a.after = !g.hidden; return a; })()""")
        check('approximate location (km accuracy) 3 times: banner with the «Точная геопозиция» steps, gone with real GPS', not r['one'] and r['ban'] and r['kind'] == 'approx' and 'Точная геопозиция' in r['how'] and not r['retry'] and not r['after'], r)
        # ---- 3D button ----
        check('3D button active online', not await pg.evaluate("document.getElementById('t-3d').classList.contains('na')"))
        await ctx.set_offline(True); await pg.wait_for_timeout(300)
        check('3D button dimmed offline', await pg.evaluate("document.getElementById('t-3d').classList.contains('na')"))
        await ctx.set_offline(False); await pg.wait_for_timeout(300)
        check('3D button back online', not await pg.evaluate("document.getElementById('t-3d').classList.contains('na')"))
        # ---- «В поездке» ----
        await pg.evaluate("window.__mv = setInterval(() => { GPS.fix = Object.assign({}, GPS.fix, {spd: 6, t: Date.now()}); }, 300); Ride.status = 'rec'; Ride.autoPaused = false")
        await pg.wait_for_timeout(6500)
        st = await pg.evaluate(f"(() => {{ const v = {VIS}; return {{on: document.body.classList.contains('ridemode'), gpx: v('t-gpx'), layers: v('t-layers'), zin: v('z-in'), me: v('z-me'), sos: v('t-sos'), compass: v('t-compass'), hud: v('hud')}}; }})()")
        check('moving while recording: extra buttons hidden; «моё место», SOS, compass and cards stay', st['on'] and not st['gpx'] and not st['layers'] and not st['zin'] and st['me'] and st['sos'] and st['compass'] and st['hud'], st)
        await pg.mouse.click(200, 300); await pg.wait_for_timeout(500)
        check('a tap on the map brings the buttons back', not await pg.evaluate("document.body.classList.contains('ridemode')"))
        await pg.wait_for_timeout(9500)
        check('…and they hide again after 8 s', await pg.evaluate("document.body.classList.contains('ridemode')"))
        await pg.evaluate("Ride.autoPaused = true"); await pg.wait_for_timeout(1300)
        check('stop (auto-pause): buttons back', not await pg.evaluate("document.body.classList.contains('ridemode')"))
        await pg.evaluate("Ride.autoPaused = false; S.rideMode = false"); await pg.wait_for_timeout(6000)
        check('setting off: buttons never hide', not await pg.evaluate("document.body.classList.contains('ridemode')"))
        await pg.evaluate("clearInterval(window.__mv); Ride.status = 'idle'")
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # ---- Hebrew / English: banner and setting translated ----
        for lang, word in [('he', 'אין גישה למיקום'), ('en', 'No access to location')]:
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks())
            await ctx.clear_permissions(); await pg.evaluate("GPS.fix = null; geoRetry()"); await pg.wait_for_timeout(800)
            t = await pg.inner_text('#geohelp')
            s = await pg.evaluate("document.getElementById('s-ridemode').parentElement.textContent")
            check(f'{lang}: banner and setting translated', word in t and not any('Ѐ' <= c <= 'ӿ' for c in t + s), (t, s))
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
