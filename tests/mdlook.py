# v136: the «Как Google Maps» look. A light Material theme beside «Тёмный» / «Яркое солнце» / «По солнцу»: white surfaces,
# Google blue, light sheets and dialogs, no dark leftovers on the main screens, readable contrast. Bike-type chips on the
# map were tried in v136 and removed in v137 (they repeated the mode button at the top). Route
# cards: length / climb / difficulty / source as chips, «▶ Поехали», Google Maps / Waze / GPX on view, the rest under «⋯».
# A grab handle on the small panel. ru / he / en. Run: python3 tests/mdlook.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.09 + i * 0.0005, 34.88, 20 + i * 2] for i in range(60)]
# dark, nearly grey surfaces left in a light screen (a coloured button — blue, red — is fine)
DARK = """(root) => { const out = [], px = c => (c.match(/[\\d.]+/g) || []).map(Number);
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  for (const el of root.querySelectorAll('*')) { if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    if (/background/.test(el.getAttribute('style') || '')) continue;   // a colour swatch (the route colour — black is one of them)
    const r = el.getBoundingClientRect(); if (r.width < 8 || r.height < 8 || r.bottom < 0 || r.top > innerHeight) continue;
    const c = px(getComputedStyle(el).backgroundColor); if (c.length < 3 || (c.length > 3 && c[3] < .35)) continue;
    if (lum(c) < .2 && Math.max(c[0], c[1], c[2]) - Math.min(c[0], c[1], c[2]) < 60) out.push((el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + [...el.classList].join('.')) + ' ' + getComputedStyle(el).backgroundColor); }
  return out.slice(0, 6); }"""
CONTRAST = """(sel) => { const el = document.querySelector(sel); if (!el) return null; const px = c => (c.match(/[\\d.]+/g) || []).map(Number);
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  let bg = null; for (let e = el; e; e = e.parentElement) { const c = px(getComputedStyle(e).backgroundColor); if (c.length >= 3 && (c.length === 3 || c[3] > .9)) { bg = c; break; } }
  const fg = px(getComputedStyle(el).color), a = lum(fg), b = lum(bg || [255, 255, 255]); return Math.round((Math.max(a, b) + .05) / (Math.min(a, b) + .05) * 10) / 10; }"""

async def main():
    url = serve(9077); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate("setMode('bike', true)")
        # ---------- the theme
        await pg.evaluate("showTab('profile')")
        names = await pg.evaluate("[...document.querySelectorAll('#s-theme button')].map(b => b.textContent.trim())")
        check('Settings → Экран: «🗺 Как Google Maps» beside the other looks', '🗺 Как Google Maps' in names and len(names) == 4, names)
        await pg.click('#s-theme [data-t="md"]'); await pg.wait_for_timeout(300)
        st = await pg.evaluate("({ md: document.body.classList.contains('md'), sun: document.body.classList.contains('sun'), acc: getComputedStyle(document.body).getPropertyValue('--accent').trim(), dark: darkMapOn(), meta: document.querySelector('meta[name=theme-color]').content, saved: lsGet('settings', {}).theme })")
        check('«Как Google Maps» on: light screen, Google blue, the map not darkened, white status bar, remembered', st['md'] and st['sun'] and st['acc'] == '#1a73e8' and not st['dark'] and st['meta'] == '#ffffff' and st['saved'] == 'md', st)
        await pg.evaluate("document.querySelectorAll('details.grp').forEach(d => d.open = true)")
        d = await pg.evaluate(DARK, None) if False else await pg.evaluate(f"({DARK})(document.getElementById('sheet-profile') || document.querySelector('.sheet:not([hidden])'))")
        check('Settings (all groups open): no dark grey surfaces left', not d, d)
        c = [await pg.evaluate(CONTRAST, s) for s in ('#sheet-profile h2, .sheet:not([hidden]) h2', '.grp > summary small', '#s-theme .on')]
        check('Settings: text readable (contrast ≥ 4.5)', all(x and x >= 4.5 for x in c), c)
        await pg.evaluate(f"DB.put('routes', {{ id: 'r1', name: 'Сингл Бен-Шемен', coords: {json.dumps(ROUTE)}, dist: 16400, asc: 285, created: Date.now(), source: 'Israel Hiking', wpts: [] }})")
        for tab, js in (('Маршруты · Мои', "showTab('routes'); routeSeg('mine')"), ('Маршруты · Построить', "routeSeg('plan')"), ('История', "showTab('history')")):
            await pg.evaluate(js); await pg.wait_for_timeout(400)
            d = await pg.evaluate(f"({DARK})(document.querySelector('.sheet:not([hidden])'))")
            check(f'{tab}: no dark grey surfaces left', not d, d)
        await pg.evaluate("showTab('rec'); setCompact(false, true)"); await pg.wait_for_timeout(300)
        d = await pg.evaluate(f"({DARK})(document.getElementById('hud'))")
        tb = await pg.evaluate("(() => { const b = document.querySelector('.tabs button.on'); return [getComputedStyle(b).backgroundColor, getComputedStyle(b).color]; })()")
        check('the ride panel light; the bottom menu marks the tab Material-style (light blue pill)', not d and tb[0] == 'rgb(211, 227, 253)', (d, tb))
        await pg.evaluate("setCompact(true, true); S.preRide = true")
        await pg.evaluate("GPS.fix = GPS.fix ? { ...GPS.fix, spd: 0 } : GPS.fix")
        await pg.evaluate(f"Nav.set({{ name: 'Тест', coords: {json.dumps(ROUTE)} }})")
        await pg.wait_for_function("!document.getElementById('ask-pre').hidden", timeout=8000)
        d = await pg.evaluate(f"({DARK})(document.querySelector('#ask-pre .box'))")
        bx = await pg.evaluate("getComputedStyle(document.querySelector('#ask-pre .box')).backgroundColor")
        check('a dialog («Перед выездом»): white card, nothing dark in it', bx == 'rgb(255, 255, 255)' and not d, (bx, d))
        await pg.click('#pre-go'); await pg.evaluate("Nav.stop(); S.preRide = false")
        # ---------- v137: no bike chips on the map — the mode button at the top does it (no duplicate)
        await pg.evaluate("setMode('bike', true); placeGpxBtn()")
        check('v137: no row of bike buttons on the map (the mode button at the top changes the bike)', await pg.evaluate("!document.getElementById('bchips') && !document.getElementById('s-bchips') && !!document.getElementById('t-mode')"))
        # ---------- route cards
        await pg.evaluate("showTab('routes'); routeSeg('mine')"); await pg.wait_for_timeout(400)
        card = await pg.evaluate("(() => { const c = document.querySelector('#rt-list .rtit'); return { chips: [...c.querySelectorAll('.rchips b')].map(b => b.textContent), vis: [...c.querySelectorAll('button')].filter(b => b.offsetParent).map(b => b.textContent.trim()) }; })()")
        check('route card: chips — length, climb, difficulty, source', card['chips'][:2] == ['16.4 км', '↗ 285 м'] and card['chips'][2] in ('Лёгкий', 'Средний', 'Сложный') and card['chips'][3] == 'Israel Hiking', card['chips'])
        check('route card: «▶ Поехали», «⋯» and Google Maps / Waze / GPX on view', card['vis'] == ['▶ Поехали', '⋯', 'Google Maps', 'Waze', 'GPX'], card['vis'])
        await pg.evaluate("window.__ext = []; window.openExt = (a, d, c) => window.__ext.push([a, c ? c.length : 0]); 0")
        await pg.click('#rt-list [data-gm]'); await pg.click('#rt-list [data-wz]')
        check('Google Maps gets the whole route, Waze the start', await pg.evaluate("window.__ext") == [['google', 60], ['waze', 0]], await pg.evaluate("window.__ext"))
        await pg.click('#rt-list [data-more]'); await pg.wait_for_timeout(200)
        more = await pg.evaluate("[...document.querySelectorAll('#rt-list .a2 button')].filter(b => b.offsetParent).map(b => b.textContent.trim())")
        check('«⋯»: ⇆ Обратно, Свой старт, Карта, Удалить', more == ['⇆ Обратно', 'Свой старт', 'Карта', 'Удалить'], more)
        # ---------- handle; back to dark
        await pg.evaluate("showTab('rec'); setCompact(true, true)")
        check('the small panel has a grab handle', await pg.evaluate("(() => { const g = document.querySelector('#mini .mgrab'); return !!g && g.getBoundingClientRect().width > 20; })()"))
        await pg.evaluate("showTab('profile')"); await pg.click('#s-theme [data-t="dark"]')
        st = await pg.evaluate("({ cls: ['md', 'mdn', 'mdk', 'sun'].filter(c => document.body.classList.contains(c)).join(' '), acc: getComputedStyle(document.body).getPropertyValue('--accent').trim(), meta: document.querySelector('meta[name=theme-color]').content })")
        # v144: «Тёмный как Google Maps» — this layout in the dark look's colours (the slate screen, the yellow accent)
        check('«Тёмный как Google Maps»: the same layout, dark slate and yellow', st['cls'] == 'md mdn mdk' and st['acc'] == '#fde047' and st['meta'] == '#0b1120', st)
        # «🌓 По солнцу» (v144): the same layout all day — «Как Google Maps · День» by day, «Тёмный как Google Maps» at night
        CL = "['md', 'mdn', 'mdk', 'sun'].filter(c => document.body.classList.contains(c)).join(' ')"
        await pg.evaluate("window.sunTimes = () => ({ rise: new Date(Date.now() - 7200000), set: new Date(Date.now() + 7200000) }); S.theme = 'auto'; applyTheme()")
        day = await pg.evaluate("({ cls: " + CL + ", acc: getComputedStyle(document.body).getPropertyValue('--accent').trim() })")
        await pg.evaluate("window.sunTimes = () => ({ rise: new Date(Date.now() + 3600000), set: new Date(Date.now() + 7200000) }); applyTheme()")
        night = await pg.evaluate("({ cls: " + CL + ", acc: getComputedStyle(document.body).getPropertyValue('--accent').trim() })")
        check('«По солнцу»: by day Google\'s light layout, at night «Тёмный как Google Maps» — the buttons stay, only the colours change', day['cls'] == 'md sun' and day['acc'] == '#1a73e8' and night['cls'] == 'md mdn mdk' and night['acc'] == '#fde047', (day, night))
        await pg.evaluate("S.theme = 'dark'; applyTheme()")
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, storage=[['velo:settings', json.dumps({'theme': 'md', 'preRide': False})]])
            await pg.evaluate("setMode('bike', true); placeGpxBtn()"); await pg.wait_for_timeout(500)
            t = await pg.evaluate("[...document.querySelectorAll('#s-theme button')].map(b => b.textContent).join(' ')")
            cyr = [w for w in t.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: the theme buttons translated; the theme kept', not cyr and await pg.evaluate("document.body.classList.contains('md')"), (t.replace('\n', ' ')[:200], cyr[:4]))
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
