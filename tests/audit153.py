# v153 audit — the widest one: every screen and dialog of audit142 plus those added since (no fresh GPS, off the route, end of
# navigation, «not on the route», changing the travel mode, before the ride, sharing a ride, a route's menu, a ride saved with
# gaps, History in pages and its progress tab, routes near me, the account signed in, search results, the map turned by hand,
# riding with the big buttons) — in every look (Тёмный как Google Maps, Яркое солнце, По солнцу, Как Google Maps · День /
# Ночь / Контраст), in Russian, Hebrew and English, on the iPhone (390 × 844), the small one (375 × 667), the smallest
# (320 × 568), the big one (430 × 932) and turned sideways (844 × 390).
# Fails on: JS errors; anything wider than the screen; Russian left in he/en; broken words; text cut off; unreadable text
# (contrast < 3); broken pictures; buttons without a name; something over an open dialog; the map's floating buttons
# overlapping each other. Also writes, for review (not failing): small touch targets (< 32 px) and text below the strict
# contrast (4.5 for small text) — tests/.cache/audit153/report.txt; screenshots next to it.
# Run: python3 tests/audit153.py [look] [lang] [size]
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from audit142 import AUDIT, VIS, FIX, ROUTE, SCREENS as SCREENS142
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'audit153'); os.makedirs(OUT, exist_ok=True)

T0RIDE = "Date.now() - 864e5"
SEED = f"""(async () => {{
  const now = Date.now();
  await DB.put('routes', {{ id: 'rt1', name: 'Бен-Шемен кольцо', coords: {json.dumps(ROUTE)}, dist: 1500, asc: 59, created: now, src: 'test', wpts: [] }});
  const tr = {json.dumps([[c[0], c[1], c[2]] for c in ROUTE])}.map((c, i) => [c[0], c[1], c[2], now - 3600e3 + i * 10000]);
  await DB.put('rides', {{ id: 'rd1', name: 'Поездка 18.10', start: now - 3600e3, end: now, type: 'bike', dist: 1500, movingMs: 600000, max: 9, asc: 59, desc: 10, routeId: 'rt1', track: tr }});
  await DB.put('rides', {{ id: 'rdGap', name: 'Поездка 17.10', start: now - 90000e3, end: now - 86000e3, type: 'bike', dist: 2200, movingMs: 900000, max: 7, asc: 20, desc: 20,
    track: tr.slice(0, 30).concat(tr.slice(30).map(p => [p[0] + 0.05, p[1], p[2], p[3] + 3600e3])), brk: [tr[30][3] + 3600e3] }});
  for (let i = 0; i < 34; i++) {{ const t0 = now - (i + 3) * 864e5; await DB.put('rides', {{ id: 'h' + i, name: 'Поездка ' + i, start: t0, end: t0 + 36e5, type: i % 5 ? 'bike' : 'run', dist: 5000 + i * 100, movingMs: 18e5, max: 8, asc: 30, desc: 30,
    track: [[32.09, 34.88 + i * 1e-3, 30, t0], [32.1, 34.89 + i * 1e-3, 40, t0 + 18e5]] }}); }}
}})()"""
NAV = "Nav.set({name: 'Бен-Шемен кольцо', coords: " + json.dumps(ROUTE) + ", rid: 'rt1', noAsk: true})"
SCREENS = SCREENS142 + [
    ('nav-riding', "document.getElementById('ask-off').hidden = true; showTab('rec'); " + NAV + "; Ride.start(); syncRideMode(); setCompact(true)"),
    ('nav-stale-gps', "GPS.spdEma = 5; GPS.lastT = Date.now() - 31000; Nav.stale()"),
    ('nav-off-route', "GPS.lastT = Date.now(); Nav.offFrom = [32.09, 34.88]; Nav.offPt = [32.091, 34.882]; Nav.render(true, 140)"),
    ('end-nav', "Nav.render(); document.getElementById('nv-x').click()"),
    ('not-on-route', "document.getElementById('en-no').click(); Nav.offerJoin([32.1, 34.95])"),
    ('travel-mode', "document.getElementById('ask-join').hidden = true; Nav.choosing = false; document.getElementById('t-mode').click()"),
    ('remode', "document.getElementById('ask-mode').hidden = true; modeChanged('bike', 'foot', false)"),
    ('turned-map', "document.getElementById('ask-remode').hidden = true; Ride.stop(false); Nav.stop(); setCompact(false); RotMan.on = true; setMapBearing(40); renderCompass()"),
    ('before-ride', "RotMan.on = false; setMapBearing(0); S.preRide = true; " + NAV.replace(", noAsk: true", "") .replace("rid: 'rt1'", "rid: 'rt1', noAsk: true") + "; preArm(); preRender()"),
    ('ride-share', "preHide(true); Nav.stop(); (async () => openRideShare(await DB.get('rides', 'rd1')))()"),
    ('route-menu', "document.getElementById('ask-rshare').hidden = true; (async () => routeMenu(await DB.get('routes', 'rt1'), 'mine'))()"),
    ('saved-with-gaps', "document.getElementById('ask-rt').hidden = true; (async () => showSaveBar(await DB.get('rides', 'rdGap'), null, false, false, true))()"),
    ('history-pages', "document.getElementById('savebar').hidden = true; HS.per = 'all'; HS.seg = 'list'; HS.lim = 30; showTab('history'); renderRides(); setTimeout(() => document.getElementById('sheet-history').scrollTop = 1e6, 300)"),
    ('history-progress', "HS.seg = 'prog'; renderRides()"),
    ('near-me', "HS.seg = 'list'; document.getElementById('sh-x') && document.getElementById('sh-x').click(); showTab('routes'); routeSeg('trails')"),
    ('account-in', "lsSet('acct', { email: 'rider@example.com', uid: 'u1', idToken: 't', refreshToken: 'r', exp: Date.now() + 36e5 }); showTab('profile'); document.querySelector('details.grp[data-g=acct]') && (document.querySelector('details.grp[data-g=acct]').open = true); renderAcct(); document.querySelector('details.grp[data-g=acct]') && document.querySelector('details.grp[data-g=acct]').scrollIntoView()"),
    ('search-results', "lsSet('acct', null); renderAcct(); showTab('rec'); const q = document.querySelector('#gsearch input'); if (q) { q.focus(); q.value = 'Тель-Авив'; q.dispatchEvent(new Event('input', { bubbles: true })); }"),
]
LOOKS = {'dark': {}, 'sun': {'theme': 'sun'}, 'auto': {'theme': 'auto'}, 'md-day': {'theme': 'md', 'mdVariant': 'day'}, 'md-night': {'theme': 'md', 'mdVariant': 'night'}, 'md-contrast': {'theme': 'md', 'mdVariant': 'contrast'}}
SIZES = {'iphone': (390, 844), 'se': (375, 667), 'small': (320, 568), 'max': (430, 932), 'land': (844, 390)}
# every look in every language on the usual iPhone; the other sizes in the two main looks
PLAN = [(l, g, 'iphone') for l in LOOKS for g in ('ru', 'he', 'en')] + [(l, g, z) for l in ('dark', 'sun') for g in ('ru', 'he', 'en') for z in ('se', 'small', 'max', 'land')]
EXTRA = "() => { " + VIS + """
  const small = new Set(), low = new Set();
  const px = c => (c.match(/[\\d.]+/g) || []).map(Number), lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  for (const el of document.querySelectorAll('button, a[href], [role=button], input[type=checkbox], select, .chip, .seg button')) {
    if (el.closest('.leaflet-tile-pane,.leaflet-control-attribution') || !vis(el)) continue;
    const r = el.getBoundingClientRect(); if (Math.min(r.width, r.height) < 32 && !el.closest('p.note')) small.add((el.id ? '#' + el.id : (el.className || el.tagName) + ':' + (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 14)) + ' ' + Math.round(r.width) + '×' + Math.round(r.height));
  }
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('.leaflet-tile-pane,.leaflet-marker-pane,.leaflet-overlay-pane') || !vis(el)) continue;
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue).join('').trim(); if (!own) continue;
    const cs = getComputedStyle(el); if (cs.textShadow !== 'none' || /gradient|url/.test(cs.backgroundImage) || el.disabled || el.closest('[disabled]')) continue;
    const big = parseFloat(cs.fontSize) >= 24 || (parseFloat(cs.fontSize) >= 18.6 && +cs.fontWeight >= 700); if (big) continue;
    let bg = null; const lay = [];
    for (let e = el; e; e = e.parentElement) { const ec = getComputedStyle(e); if (/gradient|url/.test(ec.backgroundImage)) { lay.length = 0; break; } const c = px(ec.backgroundColor); if (c.length >= 3 && (c.length === 3 || c[3] > .05)) { lay.push(c); if (c.length === 3 || c[3] >= .99) { bg = c.slice(0, 3); break; } } }
    if (!bg) continue; for (let i = lay.length - 2; i >= 0; i--) { const a = lay[i][3]; bg = bg.map((v, j) => lay[i][j] * a + v * (1 - a)); }
    let op = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) op *= +getComputedStyle(e).opacity; if (op < .9) continue;
    const fg = px(cs.color); if (fg.length >= 4 && fg[3] < .9) continue;
    const A = lum(fg), B = lum(bg), k = (Math.max(A, B) + .05) / (Math.min(A, B) + .05);
    if (k < 4.5) low.add((el.id ? '#' + el.id : String(el.className).split(' ')[0] || el.tagName) + ' «' + own.slice(0, 18) + '» ' + k.toFixed(2));
  }
  // the map's floating buttons do not overlap each other (only when the map is showing)
  const ids = ['m-play','m-stop','hud-max','t-mic','t-compass','z-in','z-out','z-me','c-loc','legend-tab','t-layers','t-mode','t-3d','t-sos','t-gpx','t-ret','gsearch'], R = [];
  if ([...document.querySelectorAll('.sheet')].every(s => s.hidden) && [...document.querySelectorAll('.ask')].every(a => a.hidden))
    for (const id of ids) { const el = document.getElementById(id); if (el && vis(el) && getComputedStyle(el).pointerEvents !== 'none') R.push([id, el.getBoundingClientRect()]); }
  const clash = []; for (let i = 0; i < R.length; i++) for (let j = i + 1; j < R.length; j++) { const a = R[i][1], b = R[j][1]; if (a.left < b.right - 2 && b.left < a.right - 2 && a.top < b.bottom - 2 && b.top < a.bottom - 2) clash.push(R[i][0] + '×' + R[j][0] + (window.__clashDbg ? ' ' + JSON.stringify([a, b].map(r => [r.left, r.top, r.width, r.height].map(Math.round))) + ' ' + document.getElementById(R[i][0]).className + '/' + document.getElementById(R[j][0]).className : '')); }
  return { small: [...small], low: [...low], clash }; }"""

async def main():
    url = serve(8941); m = Mocks()
    args = sys.argv[1:]
    plan = [x for x in PLAN if all(a in x for a in args)]
    report = open(os.path.join(OUT, 'report.txt' if not args else 'report-' + '-'.join(args) + '.txt'), 'w', encoding='utf-8')
    async with async_playwright() as p:
        for look, lang, size in plan:
            tag = f'{look}-{lang}-{size}'
            st = dict(LOOKS[look], gsearch=True)
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, viewport=SIZES[size], storage=[['velo:settings', json.dumps(st)]])
            await pg.evaluate(SEED); await pg.wait_for_timeout(300)
            await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch)"); t0 = await pg.evaluate("Date.now()")
            for i in range(8): await pg.evaluate(FIX, [32.09 + i * 4 / 110540, 34.88, 4, t0 + i * 1000])
            probs, warn = [], {}
            for name, js in SCREENS:
                try: await pg.evaluate("(() => { " + js + "; })(); 0")
                except Exception as e: probs.append(f'{name}: does not open — {str(e)[:120]}'); continue
                await pg.wait_for_timeout(650)
                a = await pg.evaluate(AUDIT, lang); x = await pg.evaluate(EXTRA)
                await pg.screenshot(path=os.path.join(OUT, f'{tag}-{name}.png'))
                for k, label in (('cover', 'something over the dialog'), ('over', 'wider than the screen'), ('left', 'Russian left'), ('bad', 'broken words'), ('cut', 'text cut off'), ('img', 'broken picture'), ('mute', 'button without text or icon'), ('dim', 'hard to read')):
                    if a[k]: probs.append(f'{name}: {label} {a[k]}')
                if x['clash']: probs.append(f'{name}: map buttons overlap {x["clash"]}')
                for k in ('small', 'low'):
                    for v in x[k]: warn.setdefault(k, {}).setdefault(v, set()).add(name)
            for k, d in warn.items():
                for v, where in sorted(d.items()): report.write(f'{tag}\t{k}\t{v}\t{",".join(sorted(where))}\n')
            check(f'[{tag}] {len(SCREENS)} screens and dialogs: letters, pictures and layout in place', not probs, probs[:10])
            check(f'[{tag}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    report.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
