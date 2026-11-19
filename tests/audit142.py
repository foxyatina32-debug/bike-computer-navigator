# v142 audit: every screen in every look (Тёмный, Яркое солнце, Как Google Maps — День / Ночь / Контраст, and День on the
# small iPhone SE) and in Russian,
# Hebrew and English: no JS errors; nothing wider than the screen; no Russian left in he/en (text, placeholders, hints);
# no broken words (undefined, NaN, null, [object…], ${…}, the replacement glyph); no text cut off without «…»; text readable
# (contrast ≥ 3 against what is behind it);
# no broken pictures; no button left without text, icon or name; nothing lying over an open dialog. Screenshots go to tests/.cache/audit142.
# Run: python3 tests/audit142.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'audit142'); os.makedirs(SHOT, exist_ok=True)

ROUTE = [[32.09 + i * 0.0002, 34.88 + (i // 20) * 0.001, 40 + i] for i in range(60)]
SEED = f"""(async () => {{
  const now = Date.now();
  await DB.put('routes', {{ id: 'rt1', name: 'Бен-Шемен кольцо', coords: {json.dumps(ROUTE)}, dist: 1500, asc: 59, created: now, src: 'test', wpts: [] }});
  await DB.put('rides', {{ id: 'rd1', name: 'Поездка 18.10', start: now - 3600e3, end: now, type: 'bike', dist: 1500, movingMs: 600000, max: 9, asc: 59, desc: 10, routeId: 'rt1',
    track: {json.dumps([[c[0], c[1], c[2]] for c in ROUTE])}.map((c, i) => [c[0], c[1], c[2], now - 3600e3 + i * 10000]) }});
}})()"""
FIX = "([la, lo, spd, t]) => onFix({ coords: { latitude: la, longitude: lo, accuracy: 6, altitude: 40, altitudeAccuracy: 5, speed: spd, heading: 0 }, timestamp: t })"
VIS = """const vis = el => { if (el.closest('[hidden]')) return false; const r = el.getBoundingClientRect(); if (!r.width || !r.height || r.bottom < 0 || r.top > innerHeight) return false;
  for (let e = el; e && e.nodeType === 1; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false; } return true; };"""
AUDIT = "(lang) => { " + VIS + """
  const W = innerWidth, over = [], left = new Set(), bad = new Set(), cut = [], img = [], mute = [], dim = [];
  const px = c => (c.match(/[\\d.]+/g) || []).map(Number), lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  const userData = /Бен-Шемен|Поездка 18|Русский|Тель-Авив/;
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('.leaflet-tile-pane') || ['SCRIPT', 'STYLE', 'svg', 'path'].includes(el.tagName)) continue;
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!el.closest('.leaflet-container') && (r.right > W + 1 || r.left < -1)) { let p = el.parentElement, clip = false; while (p) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden' || o === 'clip') { clip = true; break; } p = p.parentElement; } if (!clip) over.push((el.id || el.className || el.tagName) + ' ' + Math.round(r.left) + '..' + Math.round(r.right)); }
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue).join('').trim();
    if (own) {
      if (lang !== 'ru' && /[А-Яа-яЁё]{3,}/.test(own) && !userData.test(own)) left.add(own.slice(0, 60));
      if (/\\bundefined\\b|\\bNaN\\b|\\bnull\\b|\\[object|\\$\\{|\\uFFFD|\\{\\{/.test(own)) bad.add(own.slice(0, 60));
      const ox = cs.overflowX, oy = cs.overflowY;
      if ((ox === 'hidden' || ox === 'clip') && el.scrollWidth > el.clientWidth + 2 && cs.textOverflow !== 'ellipsis' && !el.closest('.leaflet-container')) cut.push((el.id || el.className || el.tagName) + ': ' + own.slice(0, 30));
      if ((oy === 'hidden' || oy === 'clip') && el.scrollHeight > el.clientHeight + 3 && cs.webkitLineClamp === 'none' && !el.closest('.leaflet-container') && el.clientHeight > 0) cut.push('↕ ' + (el.id || el.className || el.tagName) + ': ' + own.slice(0, 30));
    }
    if (own && !el.closest('.leaflet-tile-pane,.leaflet-marker-pane,.leaflet-overlay-pane,.leaflet-shadow-pane') && cs.textShadow === 'none' && !el.disabled && !el.closest('[disabled]') && !/gradient|url/.test(cs.backgroundImage)) {   // readable: contrast ≥ 3 against what is behind
      // what is behind: the semi-transparent layers composited over the first opaque one
      let bg = null; const lay = [];
      for (let e = el; e; e = e.parentElement) { const ec = getComputedStyle(e); if (/gradient|url/.test(ec.backgroundImage)) { lay.length = 0; break; } const c = px(ec.backgroundColor); if (c.length >= 3 && (c.length === 3 || c[3] > .05)) { lay.push(c); if (c.length === 3 || c[3] > .85) { bg = c.slice(0, 3); break; } } }
      if (bg) for (let i = lay.length - 2; i >= 0; i--) { const a = lay[i][3]; bg = bg.map((v, j) => lay[i][j] * a + v * (1 - a)); }
      let op = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) op *= +getComputedStyle(e).opacity;
      if (bg && op > .6) { const fg = px(cs.color); if (fg.length < 4 || fg[3] > .6) { const A = lum(fg), B = lum(bg), k = (Math.max(A, B) + .05) / (Math.min(A, B) + .05); if (k < 3) dim.push((el.id || el.className || el.tagName) + ': ' + own.slice(0, 20) + ' ' + k.toFixed(1)); } }
    }
    if (lang !== 'ru') for (const a of ['placeholder', 'aria-label', 'title']) { const v = el.getAttribute(a); if (v && /[А-Яа-яЁё]{3,}/.test(v) && !userData.test(v)) left.add('@' + a + ': ' + v.slice(0, 50)); }
    if (el.tagName === 'IMG' && el.complete && !el.naturalWidth && !el.closest('.leaflet-container')) img.push(el.src.slice(0, 80));
    if (el.tagName === 'BUTTON' && !el.closest('.leaflet-container') && !el.textContent.trim() && !el.querySelector('svg,img,canvas,i,span') && !el.getAttribute('aria-label') && !el.title && !getComputedStyle(el).backgroundImage.includes('url')) mute.push(el.id || el.className || 'button');
  }
  // nothing lies over an open dialog (the greeting, a floating button…)
  const cover = [];
  for (const box of document.querySelectorAll('.ask:not([hidden]) .box')) { if (!vis(box)) continue; const r = box.getBoundingClientRect();
    for (const [fx, fy] of [[.5, .12], [.5, .5], [.25, .3], [.75, .3], [.5, .85]]) { const x = r.left + r.width * fx, y = r.top + Math.min(r.height, innerHeight - r.top) * fy; const e = document.elementFromPoint(x, y);
      if (e && !e.closest('.ask')) cover.push((e.id || e.className || e.tagName) + ''); } }
  return { cover: [...new Set(cover)].slice(0, 3), over: over.slice(0, 4), left: [...left].slice(0, 6), bad: [...bad].slice(0, 4), cut: cut.slice(0, 4), img: img.slice(0, 3), mute: mute.slice(0, 4), dim: [...new Set(dim)].slice(0, 4) }; }"""

SCREENS = [
    ('map', "showTab('rec')"),
    ('metric', "openMetric(0)"),
    ('legend', "document.getElementById('mt-x').click(); setBase('ihm_mtb'); Legend.open = true; updateLegend()"),
    ('nav', "Legend.open = false; updateLegend(); showTab('rec'); Nav.set({name: 'Бен-Шемен кольцо', coords: " + json.dumps(ROUTE) + ", rid: 'rt1', noAsk: true}); setCompact(false)"),
    ('map-pages', "setCompact(false); syncPages(); pager.scrollTo({left: 3 * pager.clientWidth})"),
    ('nav-compact', "setCompact(true)"),
    ('car', "Nav.stop(); setMode('car', true)"),
    ('stop-dialog', "setMode('bike', true); Ride.start(); document.getElementById('c-stop').click()"),
    ('add', "document.getElementById('st-cont').click(); Ride.stop(false); setCompact(false); openAdd()"),
    ('routes-mine', "showTab('routes'); routeSeg('mine')"),
    ('routes-plan', "showTab('routes'); routeSeg('plan')"),
    ('routes-trails', "showTab('routes'); routeSeg('trails')"),
    ('ab', "openAB()"),
    ('route-info', "openRouteInfo('rt1')"),
    ('share', "openRouteInfo('rt1', 'routes').then(() => document.getElementById('ri-share').click())"),
    ('history', "document.getElementById('sh-x').click(); showTab('history')"),
    ('ride', "openRide('rd1')"),
    ('profile', "showTab('profile'); document.querySelectorAll('#sheet-profile details.grp').forEach(d => d.open = true)"),
    ('profile-end', "document.getElementById('sheet-profile').scrollTop = 1e6"),
    ('layers', "showTab('layers')"),
    ('sos', "showTab('rec'); SOS.open()"),
    ('voice', "SOS.close(); document.getElementById('t-mic').click()"),
    ('place-card', "document.getElementById('vc').hidden = true; map.fire('contextmenu', { latlng: L.latLng(32.1, 34.9) })"),
    ('install', "map.closePopup(); showTab('profile'); document.getElementById('app-install').click()"),
    ('off-dialog', "document.getElementById('in-ok').click(); document.getElementById('app-off').click()"),
]
LOOKS = [('dark', {}), ('sun', {'theme': 'sun'}), ('md-day', {'theme': 'md', 'mdVariant': 'day'}), ('md-night', {'theme': 'md', 'mdVariant': 'night'}), ('md-contrast', {'theme': 'md', 'mdVariant': 'contrast'}),
         ('md-day-SE', {'theme': 'md', 'mdVariant': 'day'})]   # the small iPhone (SE, 375 × 667) in «Как Google Maps»

async def main():
    url = serve(8797); m = Mocks()
    only = sys.argv[1:]   # e.g. md-day he
    async with async_playwright() as p:
        for look, st in LOOKS:
            if only and look not in only: continue
            for lang in ('ru', 'he', 'en'):
                if len(only) > 1 and lang not in only: continue
                tag = f'{look}-{lang}'
                b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, viewport=(375, 667) if look.endswith('-SE') else (390, 844), storage=[['velo:settings', json.dumps(st)]])
                await pg.evaluate(SEED); await pg.wait_for_timeout(300)
                await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)"); t0 = await pg.evaluate("Date.now()")
                for i in range(8): await pg.evaluate(FIX, [32.09 + i * 4 / 110540, 34.88, 4, t0 + i * 1000])
                probs = []
                for name, js in SCREENS:
                    try: await pg.evaluate(js + "; 0")
                    except Exception as e: probs.append(f'{name}: does not open — {str(e)[:100]}'); continue
                    await pg.wait_for_timeout(600)
                    a = await pg.evaluate(AUDIT, lang)
                    await pg.screenshot(path=os.path.join(SHOT, f'{tag}-{name}.png'))
                    for k, label in (('cover', 'something over the dialog'), ('over', 'wider than the screen'), ('left', 'Russian left'), ('bad', 'broken words'), ('cut', 'text cut off'), ('img', 'broken picture'), ('mute', 'button without text or icon'), ('dim', 'text hard to read')):
                        if a[k]: probs.append(f'{name}: {label} {a[k]}')
                check(f'[{tag}] all {len(SCREENS)} screens: letters, pictures and layout in place', not probs, probs[:8])
                check(f'[{tag}] no JS errors', not log['errors'], log['errors'][:3])
                await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
