# v138: stage 1 of the Google Maps look (inside «🗺 Как Google Maps»). Variants День / Ночь / Контраст / По солнцу on Google's
# tokens (no foreign surfaces left: nothing dark in День, nothing glaring in Ночь; 2px black borders in Контраст; readable
# text); Roboto + JetBrains Mono fetched only for this look, steady digits; Material switches (still the same checkboxes);
# the green navigation banner with the «Далее: …» strip and the arrival (red when off the route); the arrow in Google's blue
# with a direction, Google's blue dot without one (v140; the chosen icon is kept; the usual arrow in the other looks); map types as thumbnails.
# ru / he / en. Run: python3 tests/gmstyle.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.09 + i * 0.0005, 34.88, 20 + i] for i in range(60)] + [[32.1195, 34.88 + i * 0.0005, 80] for i in range(1, 40)]
FIX = "([la, lo, spd, hdg, t]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 5, altitude: 30, altitudeAccuracy: 5, speed: spd, heading: hdg }, timestamp: t })"
LUM = "const px = c => (c.match(/[\\d.]+/g) || []).map(Number), lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };"
# surfaces of the wrong kind for the variant: dark neutral ones in a light look, glaring neutral ones in the night look
WRONG = "([sel, night]) => { " + LUM + """ const root = document.querySelector(sel), out = []; if (!root) return ['no ' + sel];
  for (const el of [root, ...root.querySelectorAll('*')]) { if (/background/.test(el.getAttribute('style') || '')) continue;
    const r = el.getBoundingClientRect(); if (r.width < 8 || r.height < 8 || r.bottom < 0 || r.top > innerHeight || (!el.offsetParent && getComputedStyle(el).position !== 'fixed')) continue;
    const c = px(getComputedStyle(el).backgroundColor); if (c.length < 3 || (c.length > 3 && c[3] < .35)) continue;
    const neutral = Math.max(c[0], c[1], c[2]) - Math.min(c[0], c[1], c[2]) < 60, L = lum(c);
    if (neutral && (night ? L > .6 : L < .2)) out.push((el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + [...el.classList].join('.')) + ' ' + getComputedStyle(el).backgroundColor); }
  return out.slice(0, 5); }"""
CONTRAST = "(sel) => { " + LUM + """ const el = document.querySelector(sel); if (!el) return null;
  let bg = null; for (let e = el; e; e = e.parentElement) { const c = px(getComputedStyle(e).backgroundColor); if (c.length >= 3 && (c.length === 3 || c[3] > .9)) { bg = c; break; } }
  const a = lum(px(getComputedStyle(el).color)), b = lum(bg || [255, 255, 255]); return Math.round((Math.max(a, b) + .05) / (Math.min(a, b) + .05) * 10) / 10; }"""
CLS = "['md', 'sun', 'mdn', 'mdc'].filter(c => document.body.classList.contains(c)).join(' ')"

async def main():
    url = serve(9083); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=[['velo:settings', json.dumps({'theme': 'sun'})]])   # an older look (since v145 «Тёмный» is this layout too)
        check('the other looks do not fetch Google\'s fonts', not await pg.evaluate("!!document.getElementById('md-fonts')"))
        await pg.evaluate("showTab('profile')")
        check('the variants show only with «Как Google Maps»', await pg.evaluate("document.getElementById('s-mdv').hidden"))
        await pg.click('#s-theme [data-t="md"]'); await pg.wait_for_timeout(200)
        v = await pg.evaluate("[...document.querySelectorAll('#s-mdv button')].map(b => b.textContent.trim())")
        check('«Как Google Maps»: День / Ночь / Контраст / По солнцу', v == ['☀️ День', '🌙 Ночь', '◐ Контраст', '🌓 По солнцу'] and not await pg.evaluate("document.getElementById('s-mdv').hidden"), v)
        f = await pg.evaluate("[...document.querySelectorAll('link[rel=stylesheet]')].map(l => l.href).filter(h => /fontsource/.test(h))")
        check('Roboto + JetBrains Mono (one version, from the libraries\' server, kept by the service worker)', len(f) == 4 and all('cdn.jsdelivr.net/npm/@fontsource/' in h and '@5.2.8/' in h for h in f) and any('jetbrains-mono' in h for h in f), f)
        st = {}
        for k in ('day', 'night', 'contrast'):
            await pg.click(f'#s-mdv [data-v="{k}"]'); await pg.wait_for_timeout(150)
            st[k] = await pg.evaluate(f"({{ cls: {CLS}, meta: document.querySelector('meta[name=theme-color]').content, dark: darkMapOn(), saved: lsGet('settings', {{}}).mdVariant }})")
        check('День: light (+ the light map chrome), white status bar, the map not darkened', st['day']['cls'] == 'md sun' and st['day']['meta'] == '#ffffff' and not st['day']['dark'], st['day'])
        check('Ночь: Google Maps Night — dark status bar, the map darkened (as set), remembered', st['night']['cls'] == 'md mdn' and st['night']['meta'] == '#1f1f1f' and st['night']['dark'] and st['night']['saved'] == 'night', st['night'])
        check('Контраст: a light look with the contrast class', st['contrast']['cls'] == 'md sun mdc', st['contrast'])
        await pg.evaluate("window.sunTimes = () => ({ rise: new Date(Date.now() + 3600000), set: new Date(Date.now() + 7200000) })")
        await pg.click('#s-mdv [data-v="auto"]'); await pg.wait_for_timeout(150)
        a1 = await pg.evaluate(CLS)
        await pg.evaluate("window.sunTimes = () => ({ rise: new Date(Date.now() - 7200000), set: new Date(Date.now() + 7200000) }); applyTheme()")
        check('По солнцу: night before sunrise, day at noon', a1 == 'md mdn' and await pg.evaluate(CLS) == 'md sun', (a1, await pg.evaluate(CLS)))
        # ---------- no foreign surfaces, readable text — in each variant
        await pg.evaluate(f"DB.put('routes', {{ id: 'r1', name: 'Сингл', coords: {json.dumps(ROUTE)}, dist: 6000, asc: 60, created: Date.now(), source: 'GPX', wpts: [] }})")
        for k, night in (('day', False), ('night', True), ('contrast', False)):
            await pg.evaluate(f"S.mdVariant = '{k}'; applyTheme(); showTab('profile'); document.querySelectorAll('details.grp').forEach(d => d.open = true)"); await pg.wait_for_timeout(250)
            bad = await pg.evaluate(WRONG, ['#sheet-profile', night])
            for js in ("showTab('routes'); routeSeg('mine')", "routeSeg('plan')", "showTab('history')", "showTab('layers')"):
                await pg.evaluate(js); await pg.wait_for_timeout(200); bad += await pg.evaluate(WRONG, ['.sheet:not([hidden])', night])
            await pg.evaluate("showTab('rec'); setCompact(false, true)"); await pg.wait_for_timeout(200); bad += await pg.evaluate(WRONG, ['#hud', night])
            await pg.evaluate("setCompact(true, true)")
            check(f'{k}: Настройки, Маршруты, Построить, История, Слои, the ride panel — no surfaces of the wrong kind', not bad, bad[:5])
            await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(150)
            c = [await pg.evaluate(CONTRAST, s) for s in ('#sheet-profile h2', '.grp > summary small', '#s-mdv .on', '#app-install')]
            check(f'{k}: text readable (contrast ≥ 4.5: title, small text, the chosen variant, the main button)', all(x and x >= 4.5 for x in c), c)
        bw = await pg.evaluate("(() => { S.mdVariant = 'contrast'; applyTheme(); const t = getComputedStyle(document.querySelector('.tabs')), bt = getComputedStyle(document.querySelector('#sheet-profile .btn')); return [t.borderTopWidth, t.borderTopColor, bt.borderTopWidth, bt.borderTopColor]; })()")
        check('Контраст: 2px black borders (the menu, the buttons)', bw == ['2px', 'rgb(0, 0, 0)', '2px', 'rgb(0, 0, 0)'], bw)
        # ---------- switches
        await pg.evaluate("S.mdVariant = 'day'; applyTheme(); document.querySelector('details.grp[data-g=ride]').open = true"); await pg.wait_for_timeout(450)   # the switch colours ease in
        sw = await pg.evaluate("(() => { const i = document.getElementById('s-autopause'), c = getComputedStyle(i); return { app: c.appearance || c.webkitAppearance, w: c.width, h: c.height, on: i.checked, bg: c.backgroundColor }; })()")
        await pg.click('#s-autopause'); await pg.wait_for_timeout(450)
        after = await pg.evaluate("({ on: document.getElementById('s-autopause').checked, S: S.autopause, bg: getComputedStyle(document.getElementById('s-autopause')).backgroundColor })")
        check('settings on / off as Material switches (52×32, blue when on) — still the same checkbox: a tap changes the setting', sw['app'] == 'none' and sw['w'] == '52px' and sw['h'] == '32px' and sw['on'] and sw['bg'] == 'rgb(11, 87, 208)' and not after['on'] and after['S'] is False and after['bg'] != sw['bg'], (sw, after))
        await pg.click('#s-autopause')
        # ---------- the banner
        await pg.evaluate("showTab('rec'); navigator.geolocation.clearWatch(GPS.watch)"); t0 = await pg.evaluate("Date.now()")
        await pg.evaluate(f"Nav.set({{ name: 'Яркон', coords: {json.dumps(ROUTE)}, noAsk: true }})")
        for i in range(6): await pg.evaluate(FIX, [32.09 + i * 5 / 110540, 34.88, 5, 10, t0 + i * 1000])
        await pg.wait_for_timeout(300)
        bn = await pg.evaluate("(() => { const n = document.getElementById('navb'), x = document.getElementById('nv-next'); return { bg: getComputedStyle(n).backgroundColor, strip: getComputedStyle(x).display, sbg: getComputedStyle(x).backgroundColor, t: document.getElementById('nv-next-t').textContent, eta: document.getElementById('nv-next-eta').textContent, dist: getComputedStyle(document.getElementById('nv-dist')).fontFamily, r: getComputedStyle(n.querySelector('.r')).display }; })()")
        check('navigation: the green banner (#0f7b43) with the darker strip (#0b5e33)', bn['bg'] == 'rgb(15, 123, 67)' and bn['strip'] == 'flex' and bn['sbg'] == 'rgb(11, 94, 51)', bn)
        check('the strip: «Далее: финиш» and the arrival «HH:MM · 5.0x км»; the right column moved into it', bn['t'] == 'Далее: финиш' and bn['eta'][2] == ':' and bn['eta'].endswith(' км') and bn['r'] == 'none', bn)
        check('steady digits: the distance in JetBrains Mono', 'JetBrains Mono' in bn['dist'], bn['dist'])
        g = await pg.evaluate(CONTRAST, '#nv-txt')
        check('white text on the green banner readable (≥ 4.5)', g and g >= 4.5, g)
        await pg.evaluate("Nav.render(true, 60)"); await pg.wait_for_timeout(100)
        off = await pg.evaluate("({ bg: getComputedStyle(document.getElementById('navb')).backgroundColor, t: document.getElementById('nv-next-t').textContent })")
        check('off the route: the banner red, the strip says the arrow shows the way back', off['bg'] == 'rgb(217, 48, 37)' and 'Стрелка' in off['t'], off)
        # ---------- the marker: the arrow in Google's blue while the direction is known (v140), the blue dot without it
        dot = await pg.evaluate("(() => { const e = meMarker.getElement(), a = e.querySelector('svg.me-arr'); return { gdot: !!e.querySelector('.gdot'), rot: a ? a.style.transform : '', fill: a ? a.querySelector('path').getAttribute('fill') : '' }; })()")
        check('with a direction: the arrow in Google\'s blue, turned to the course (not the faint cone)', not dot['gdot'] and dot['rot'].startswith('rotate(') and dot['fill'] == '#1a73e8', dot)
        dot = await pg.evaluate("(() => { const st = markerState; markerState = () => null; lastIconHdg = 'x'; refreshMe(); const e = meMarker.getElement(), r = { gc: !!e.querySelector('.gdot .gc'), pulse: !!e.querySelector('.gdot .gp'), arr: !!e.querySelector('.me-arr') }; markerState = st; lastIconHdg = 'x'; refreshMe(); return r; })()")
        check('no direction known: Google\'s blue dot with a pulse', dot['gc'] and dot['pulse'] and not dot['arr'], dot)
        await pg.evaluate("S.meIcon = 'bike'; lastIconHdg = 'x'; refreshMe()")
        check('an icon chosen in Settings is kept in this look', await pg.evaluate("!meMarker.getElement().querySelector('.gdot') && !!meMarker.getElement().querySelector('.me-badge')"))
        await pg.evaluate("S.meIcon = 'arrow'; S.theme = 'sun'; applyTheme()"); await pg.wait_for_timeout(100)
        check('the other looks keep the usual arrow', await pg.evaluate("!meMarker.getElement().querySelector('.gdot') && !!meMarker.getElement().querySelector('svg.me-arr')"))
        await pg.evaluate("Nav.stop()")
        # ---------- map types
        ly0 = await pg.evaluate("showTab('layers'), getComputedStyle(document.querySelector('#ly-base .lyth')).display")
        await pg.evaluate("S.theme = 'md'; S.mdVariant = 'day'; applyTheme(); renderLayers()"); await pg.wait_for_timeout(200)
        ly = await pg.evaluate("(() => { const g = getComputedStyle(document.getElementById('ly-base')), t = document.querySelector('#ly-base .layer .lyth'); return { grid: g.display, cols: g.gridTemplateColumns.split(' ').length, thumb: t.style.backgroundImage, on: !!document.querySelector('#ly-base .layer:has(input:checked)'), over: getComputedStyle(document.querySelector('#ly-over input')).appearance }; })()")
        check('map types as a grid of thumbnails (two columns, a tile of each map), the chosen one marked; extra layers with switches', ly0 == 'none' and ly['grid'] == 'grid' and ly['cols'] == 2 and '/13/' in ly['thumb'] and ly['on'] and ly['over'] == 'none', (ly0, ly))
        await pg.click('#ly-base .layer:nth-of-type(2)'); await pg.wait_for_timeout(200)
        check('a tap on a thumbnail switches the map', await pg.evaluate("baseKey === document.querySelector('#ly-base .layer:nth-of-type(2) input').value"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, storage=[['velo:settings', json.dumps({'theme': 'md', 'mdVariant': 'night', 'preRide': False})]])
            await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)"); t0 = await pg.evaluate("Date.now()")
            await pg.evaluate(f"Nav.set({{ name: 'R', coords: {json.dumps(ROUTE)}, noAsk: true }})")
            for i in range(4): await pg.evaluate(FIX, [32.09 + i * 5 / 110540, 34.88, 5, 10, t0 + i * 1000])
            await pg.wait_for_timeout(500)
            t = await pg.evaluate("document.getElementById('nv-next').textContent + ' | ' + [...document.querySelectorAll('#s-mdv button')].map(b => b.textContent).join(' ')")
            cyr = [w for w in t.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: the strip and the variants translated; the night variant kept', not cyr and ('Then:' in t if lang == 'en' else 'אחר כך:' in t) and await pg.evaluate(CLS) == 'md mdn', (t[:160], cyr[:4]))
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
