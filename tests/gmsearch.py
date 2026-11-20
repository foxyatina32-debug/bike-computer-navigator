# v139: stage 2 of the Google Maps look; v143: the search bar in every look. The search pill on top (no route followed): results
# in a floating card, a tap shows the place with a red pin and its card (kept clear of the buttons), ✕ clears; «🎤» and «+»
# in the pill (their own buttons step aside); the top buttons as chips under the pill. No capsule above the panel (v142:
# not wanted) — the GPS dot stays in the mode chip, SOS right above the panel. Navigation brings the old top back; a setting
# turns the pill off. Тёмный and Яркое солнце have the same bar in their own colours (a found place gets the red pin too).
# ru / he / en. Run: python3 tests/gmsearch.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.09 + i * 0.0005, 34.88, 20 + i] for i in range(60)]
FIX = "([la, lo, spd, t, alt]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 6, altitude: alt, altitudeAccuracy: 5, speed: spd, heading: 0 }, timestamp: t })"
def photon(u):
    if 'zzz' in u: return {'type': 'FeatureCollection', 'features': []}
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [34.7818, 32.0853]}, 'properties': {'name': 'Тель-Авив', 'country': 'Израиль', 'state': 'Тель-Авивский округ', 'type': 'city'}},
        {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [34.80, 32.10]}, 'properties': {'name': 'Тель-Авив, порт', 'city': 'Тель-Авив', 'country': 'Израиль', 'type': 'locality'}}]}
R = "(q => { const e = document.querySelector(q); if (!e) return null; const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return { t: r.top, b: r.bottom, l: r.left, r: r.right, vis: !e.hidden && cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 }; })"
def apart(a, b): return a and b and (a['b'] <= b['t'] + 1 or b['b'] <= a['t'] + 1 or a['r'] <= b['l'] + 1 or b['r'] <= a['l'] + 1)
async def rect(pg, q): return await pg.evaluate(R + f"({json.dumps(q)})")

async def main():
    url = serve(9087); m = Mocks(); m.photon = photon
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.wait_for_timeout(1500)
        ST = "({ gsr: document.body.classList.contains('gsr'), pill: !document.getElementById('gsearch').hidden, mic: getComputedStyle(document.getElementById('t-mic')).display !== 'none', gpx: !document.getElementById('t-gpx').hidden })"
        st = await pg.evaluate(ST)
        check('the setting off: no bar, 🎤 and «+ Маршрут» in place', not st['gsr'] and not st['pill'] and st['mic'] and st['gpx'], st)
        # ---------- v143: every look — a phone with nothing saved has the bar on; Тёмный first
        await pg.evaluate("delete S.gsearch; saveS(); applyTheme(); placeGpxBtn()"); await pg.wait_for_timeout(300)
        st = await pg.evaluate(ST); pill, top = await rect(pg, '#gsearch'), await rect(pg, '.top')
        check('Тёмный: the search bar on top by default, «+» and 🎤 in it', st['gsr'] and st['pill'] and not st['mic'] and not st['gpx'] and pill['t'] < 60 and top['t'] >= pill['b'] - 1, (st, pill, top))
        LUM = "const px = c => (c.match(/[\\d.]+/g) || []).map(Number), lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };"
        COL = "(() => { " + LUM + " const g = document.getElementById('gsearch'), cs = getComputedStyle(g), bg = px(cs.backgroundColor), ph = px(getComputedStyle(document.getElementById('gs-q'), '::placeholder').color), q = getComputedStyle(document.getElementById('gs-q')); const k = (a, b) => { const A = lum(a), B = lum(b); return Math.round((Math.max(A, B) + .05) / (Math.min(A, B) + .05) * 10) / 10; }; return { bgL: Math.round(lum(bg) * 100) / 100, text: k(px(cs.color), bg), field: q.backgroundColor, border: q.borderTopWidth, add: getComputedStyle(document.getElementById('gs-add')).backgroundColor }; })()"
        c = await pg.evaluate(COL)
        check('…in its own colours: dark glass, light text, the yellow «+», the field without a box of its own', c['bgL'] < .1 and c['text'] >= 7 and (lambda v: v[0] > 200 and v[1] > 200 and v[2] < 160)([int(x) for x in c['add'][4:-1].split(',')]) and c['field'] in ('rgba(0, 0, 0, 0)', 'transparent') and c['border'] == '0px', c)
        await pg.evaluate("showTab('profile')")
        check('the setting is in every look (under «Экран»), on', await pg.evaluate("!document.getElementById('s-gs-wrap').hidden && document.getElementById('s-gsearch').checked"))
        await pg.click('#s-theme [data-t="sun"]'); await pg.evaluate("showTab('rec')"); await pg.wait_for_timeout(300)
        c = await pg.evaluate(COL); st = await pg.evaluate(ST)
        check('Яркое солнце: the bar too — white, dark text', st['gsr'] and st['pill'] and c['bgL'] > .8 and c['text'] >= 7, (st, c))
        await pg.evaluate("showTab('profile')")
        await pg.click('#s-theme [data-t="md"]'); await pg.wait_for_timeout(200)
        await pg.evaluate("showTab('rec')"); await pg.wait_for_timeout(300)
        # ---------- the pill and the chips
        pill, top, cmp, zin = [await rect(pg, q) for q in ('#gsearch', '.top', '#t-compass', '#z-in')]
        check('«Как Google Maps»: the search pill on top (Google\'s white)', await pg.evaluate("document.body.classList.contains('gsr')") and pill['vis'] and pill['t'] < 60, pill)
        check('the top buttons are chips under the pill', top['t'] >= pill['b'] - 1 and top['t'] - pill['b'] < 30, (pill, top))
        check('the compass and the zoom below the chips, nothing over the pill', cmp['t'] >= top['b'] - 1 and zin['t'] >= top['b'] - 1 and apart(pill, cmp) and apart(pill, zin), (cmp, zin))
        st = await pg.evaluate("({ mic: getComputedStyle(document.getElementById('t-mic')).display, gpx: document.getElementById('t-gpx').hidden })")
        check('the separate 🎤 and «+» buttons step aside (they are in the pill)', st['mic'] == 'none' and st['gpx'], st)
        await pg.click('#gs-mic'); await pg.wait_for_timeout(300)
        check('🎤 in the pill opens the voice command', await pg.evaluate("!document.getElementById('vc').hidden"))
        await pg.evaluate("document.getElementById('vc-x') ? document.getElementById('vc-x').click() : 0; document.getElementById('vc').hidden = true; 0")
        await pg.click('#gs-add'); await pg.wait_for_timeout(300)
        check('«+» in the pill opens «Маршруты» (add a route)', await pg.evaluate("!document.getElementById('sheet-routes').hidden"))
        await pg.evaluate("showTab('rec')"); await pg.wait_for_timeout(300)
        # ---------- search
        await pg.fill('#gs-q', 'Те'); await pg.wait_for_timeout(600)
        check('two letters: no search yet', await pg.evaluate("document.getElementById('gs-res').hidden && !document.getElementById('gs-x').hidden"))
        await pg.fill('#gs-q', 'Тель-Авив'); await pg.wait_for_timeout(1200)
        n = await pg.evaluate("document.querySelectorAll('#gs-res [data-gi]').length")
        res = await rect(pg, '#gs-res')
        check('typing shows the results in a card under the pill', n == 2 and res['vis'] and res['t'] >= pill['b'] - 1, (n, res))
        txt = await pg.evaluate("document.querySelector('#gs-res [data-gi=\"0\"]').textContent")
        check('a result: the name and the area', 'Тель-Авив' in txt, txt)
        await pg.click('#gs-res [data-gi="0"]'); await pg.wait_for_timeout(700)
        pop = await pg.evaluate("(() => { const p = document.querySelector('.leaflet-popup'); if (!p) return null; const r = p.getBoundingClientRect(); return { t: r.top, b: r.bottom, h4: p.querySelector('h4').textContent, btn: [...p.querySelectorAll('[data-pp]')].map(x => x.dataset.pp) }; })()")
        check('a tap: the place card (Маршрут сюда / Добавить точку / Google Maps / Waze)', pop and pop['h4'] == 'Тель-Авив' and pop['btn'] == ['here', 'add', 'gm', 'wz'], pop)
        check('…with a red pin, the results card closed, the map not following', await pg.evaluate("!!document.querySelector('.leaflet-marker-pane .gpin') && document.getElementById('gs-res').hidden && !GPS.follow"))
        lw, hud = await rect(pg, '#locw'), await rect(pg, '#hud')
        low = max(x['b'] for x in (pill, top, lw) if x and x['vis'])
        check('the card is kept clear of the buttons on top and the panel', pop and pop['t'] >= low and pop['b'] <= hud['t'], (pop, low, hud['t']))
        await pg.click('.leaflet-popup [data-pp="add"]'); await pg.wait_for_timeout(300)
        wp = await pg.evaluate("Plan.wps.map(w => w.ll.map(v => +(+v).toFixed(4)))")
        check('«Добавить точку» adds it to the plan', wp[-1:] == [[32.0853, 34.7818]] and await pg.evaluate("!document.getElementById('sheet-routes').hidden"), wp)
        check('closing the card removes the pin', not await pg.evaluate("!!document.querySelector('.leaflet-marker-pane .gpin')"))
        await pg.evaluate("Plan.wps = []; showTab('rec')"); await pg.wait_for_timeout(300)
        await pg.click('#gs-x'); await pg.wait_for_timeout(200)
        check('✕ clears the search', await pg.evaluate("document.getElementById('gs-q').value === '' && document.getElementById('gs-x').hidden && document.getElementById('gs-res').hidden"))
        await pg.fill('#gs-q', 'zzzqq'); await pg.press('#gs-q', 'Enter'); await pg.wait_for_timeout(1200)
        g = await pg.evaluate("(document.querySelector('#gs-res .gempty') || {}).textContent || ''")
        n = await pg.evaluate("document.querySelectorAll('#gs-res [data-gi]').length")
        check('Enter: the full search (here the address search answers)', n >= 1 or 'Ничего' in g, (n, g))
        await pg.click('#gs-x')
        # ---------- long press: the same card with a red pin
        await pg.evaluate("map.fire('contextmenu', { latlng: L.latLng(32.1, 34.9), containerPoint: L.point(195, 500), originalEvent: new MouseEvent('contextmenu') })"); await pg.wait_for_timeout(400)
        check('a long press: the card with a red pin', await pg.evaluate("!!document.querySelector('.leaflet-popup [data-pp=\"here\"]') && !!document.querySelector('.leaflet-marker-pane .gpin')"))
        await pg.click('.leaflet-popup [data-pp="here"]'); await pg.wait_for_timeout(400)
        wp = await pg.evaluate("Plan.wps.map(w => w.ll.map(v => +(+v).toFixed(3)))")
        check('«Маршрут сюда» builds a route there from my place', wp == [[32.1, 34.9]] and await pg.evaluate("document.getElementById('pl-fromgps').checked"), wp)
        await pg.evaluate("Plan.wps = []; showTab('rec')"); await pg.wait_for_timeout(300)
        # ---------- no capsule above the panel (v142: not wanted) — the GPS dot in the mode chip, SOS right above the panel
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)"); t0 = await pg.evaluate("Date.now()")
        for i in range(20): await pg.evaluate(FIX, [32.09 + i * 4 / 110540, 34.88, 4, t0 + i * 1000, 40 + i * 0.4])
        for comp in ('false', 'true'):
            await pg.evaluate(f"setCompact({comp}); placeGpxBtn()"); await pg.wait_for_timeout(400)
            st = await pg.evaluate("({ cap: !!document.getElementById('gcap') || !!document.querySelector('.gcap'), gd: getComputedStyle(document.getElementById('gps-dot')).display })")
            hud, sos = await rect(pg, '#hud'), await rect(pg, '#t-sos')
            check(f'{"small" if comp == "true" else "big"} panel: no capsule, the GPS dot in the mode chip, SOS right above the panel', not st['cap'] and st['gd'] != 'none' and sos['vis'] and 0 <= hud['t'] - sos['b'] <= 20, (st, sos, hud['t']))
        await pg.evaluate("setMode('car', true)")
        for i in range(21, 26): await pg.evaluate(FIX, [32.09 + i * 4 / 110540, 34.88, 14, t0 + i * 1000, 40])
        await pg.evaluate("placeGpxBtn()"); await pg.wait_for_timeout(300)
        sp, sos = [await rect(pg, q) for q in ('#spdb', '#t-sos')]
        check('car mode: the round speedometer clear of SOS', sp and sp['vis'] and apart(sp, sos), (sp, sos))
        await pg.evaluate("setMode('bike', true)")
        # ---------- navigation: the old top back
        await pg.evaluate(f"Nav.set({{ name: 'Яркон', coords: {json.dumps(ROUTE)}, noAsk: true }})"); await pg.wait_for_timeout(400)
        st = await pg.evaluate("({ gsr: document.body.classList.contains('gsr'), pill: !document.getElementById('gsearch').hidden, mic: getComputedStyle(document.getElementById('t-mic')).display !== 'none' })")
        check('navigating: no search pill, 🎤 back', not st['gsr'] and not st['pill'] and st['mic'], st)
        nb = await rect(pg, '#navb')
        check('…the green banner on top', nb['vis'] and nb['t'] < 80, nb)
        await pg.evaluate("Nav.clear ? Nav.clear() : Nav.stop()"); await pg.wait_for_timeout(400)
        check('the route ended: the pill is back', await pg.evaluate("document.body.classList.contains('gsr') && !document.getElementById('gsearch').hidden"))
        # ---------- the setting
        await pg.evaluate("showTab('profile')"); await pg.click('#s-gsearch'); await pg.wait_for_timeout(200)
        await pg.evaluate("showTab('rec')"); await pg.wait_for_timeout(300)
        st = await pg.evaluate("({ gsr: document.body.classList.contains('gsr'), mic: getComputedStyle(document.getElementById('t-mic')).display !== 'none', saved: lsGet('settings', {}).gsearch })")
        check('the setting off: no pill, 🎤 back (remembered)', not st['gsr'] and st['mic'] and st['saved'] is False, st)
        await pg.evaluate("showTab('profile')"); await pg.click('#s-gsearch'); await pg.evaluate("showTab('rec')"); await pg.wait_for_timeout(300)
        await pg.evaluate("showTab('profile')"); await pg.click('#s-theme [data-t="dark"]'); await pg.evaluate("showTab('rec')"); await pg.wait_for_timeout(300)
        st = await pg.evaluate("({ gsr: document.body.classList.contains('gsr'), pin: (map.fire('contextmenu', { latlng: L.latLng(32.1, 34.9) }), !!document.querySelector('.leaflet-marker-pane .gpin')), card: !!document.querySelector('.leaflet-popup [data-pp=\"here\"]') })")
        check('Тёмный: the bar stays; a long press gives the card without the pin (as before)', st['gsr'] and not st['pin'] and st['card'], st)
        await pg.evaluate("map.closePopup()"); await pg.fill('#gs-q', 'Тель-Авив'); await pg.wait_for_timeout(1200)
        await pg.click('#gs-res [data-gi="0"]'); await pg.wait_for_timeout(700)
        st = await pg.evaluate("({ pin: !!document.querySelector('.leaflet-marker-pane .gpin'), h4: (document.querySelector('.leaflet-popup h4') || {}).textContent })")
        check('Тёмный: a found place — the card with the red pin', st['pin'] and st['h4'] == 'Тель-Авив', st)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # ---------- languages
        for lang, ph, gl in (('he', 'חיפוש מקום או כתובת', 'שורת חיפוש למעלה'), ('en', 'Search for a place or address', 'The search bar on top')):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, storage=[['velo:settings', json.dumps({'theme': 'md', 'compact': True})]])
            await pg.wait_for_timeout(1500)
            await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)"); t0 = await pg.evaluate("Date.now()")
            for i in range(5): await pg.evaluate(FIX, [32.09 + i * 4 / 110540, 34.88, 4, t0 + i * 1000, 40])
            await pg.evaluate("setCompact(true); placeGpxBtn()"); await pg.wait_for_timeout(300)
            st = await pg.evaluate("({ ph: document.getElementById('gs-q').placeholder, gl: document.getElementById('s-gs-wrap').textContent, dir: getComputedStyle(document.getElementById('gsearch')).direction, x: document.getElementById('gs-x').getAttribute('aria-label') })")
            check(f'{lang}: the pill and its setting translated', st['ph'] == ph and gl in st['gl'] and st['x'] != 'Очистить' and (st['dir'] == 'rtl') == (lang == 'he'), st)
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
