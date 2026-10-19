# Every screen on iPhone SE and iPhone 15 Pro, in Russian, Hebrew and English:
# no JS errors, nothing wider than the screen, no untranslated Russian left in he/en.
# Run: python3 tests/screens.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'screens'); os.makedirs(SHOT, exist_ok=True)

ROUTE = [[32.09 + i * 0.0002, 34.88 + (i // 20) * 0.001, 40 + i] for i in range(60)]
SEED = f"""(async () => {{
  const now = Date.now();
  await DB.put('routes', {{ id: 'rt1', name: 'Бен-Шемен кольцо', coords: {json.dumps(ROUTE)}, dist: 1500, asc: 59, created: now, src: 'test', wpts: [] }});
  await DB.put('rides', {{ id: 'rd1', name: 'Поездка 18.10', start: now - 3600e3, end: now, type: 'bike', dist: 1500, movingMs: 600000, max: 9, asc: 59, desc: 10, routeId: 'rt1',
    track: {json.dumps([[c[0], c[1], c[2]] for c in ROUTE])}.map((c, i) => [c[0], c[1], c[2], now - 3600e3 + i * 10000]) }});
}})()"""
# Russian words that may legitimately stay: user data (route/ride names) and the language picker.
OVERFLOW = """(() => { const W = innerWidth, bad = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('.leaflet-container') || el.closest('[hidden]')) continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;
    if (r.right > W + 1 || r.left < -1) { if (el.closest('.pager') || el.closest('.hscroll') || el.closest('[style*="overflow"]')) continue; let p = el.parentElement, clip = false; while (p) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') { clip = true; break; } p = p.parentElement; } if (!clip) bad.push((el.id || el.className || el.tagName) + ' ' + Math.round(r.left) + '..' + Math.round(r.right)); }
  }
  return [document.documentElement.scrollWidth > W + 1 ? 'PAGE ' + document.documentElement.scrollWidth : null, ...bad.slice(0, 5)].filter(Boolean); })()"""
LEFTOVER = """(() => { const out = new Set();
  const walk = n => { if (n.nodeType === 3) { if (/[А-Яа-яЁё]{3,}/.test(n.nodeValue) && !/Бен-Шемен|Поездка 18|Русский/.test(n.nodeValue)) out.add(n.nodeValue.trim().slice(0, 50)); return; }
    if (n.nodeType !== 1 || ['SCRIPT', 'STYLE'].includes(n.tagName) || n.hidden || n.closest('.leaflet-container')) return;
    if (getComputedStyle(n).display === 'none') return; for (const c of n.childNodes) walk(c); };
  walk(document.body); return [...out].slice(0, 6); })()"""

async def visit(pg, name, js, lang, tag):
    try: await pg.evaluate(js)
    except Exception as e: check(f'[{tag}] {name} opens', False, str(e)[:120]); return
    await pg.wait_for_timeout(700)
    ov = await pg.evaluate(OVERFLOW)
    lo = await pg.evaluate(LEFTOVER) if lang != 'ru' else []
    await pg.screenshot(path=os.path.join(SHOT, f'{tag}-{name}.png'))
    check(f'[{tag}] {name}: fits the screen' + (', translated' if lang != 'ru' else ''), not ov and not lo, (ov + lo)[:6])

SCREENS = [
    ('map', "showTab('rec')"),
    ('map-pages', "showTab('rec'); setCompact(false); pager.scrollTo({left: 3 * pager.clientWidth})"),
    ('nav', "showTab('rec'); Nav.set({name: 'Бен-Шемен кольцо', coords: " + json.dumps(ROUTE) + ", rid: 'rt1', noAsk: true}); setCompact(false)"),
    ('nav-compact', "setCompact(true)"),
    ('stop-dialog', "Nav.stop(); Ride.start(); document.getElementById('c-stop').click()"),
    ('add', "document.getElementById('st-cont').click(); Ride.stop(false); openAdd()"),
    ('routes-mine', "showTab('routes'); routeSeg('mine')"),
    ('routes-plan', "showTab('routes'); routeSeg('plan')"),
    ('routes-trails', "showTab('routes'); routeSeg('trails')"),
    ('ab', "openAB()"),
    ('route-info', "openRouteInfo('rt1')"),
    ('history', "showTab('history')"),
    ('ride', "openRide('rd1')"),
    ('profile', "showTab('profile')"),
    ('layers', "showTab('layers')"),
    ('install', "showTab('profile'); document.getElementById('app-install').click()"),
]

async def main():
    url = serve(8795); m = Mocks()
    async with async_playwright() as p:
        for vp, vtag in [((375, 667), 'SE'), ((393, 852), '15Pro')]:
            for lang in ('ru', 'he', 'en'):
                tag = f'{vtag}-{lang}'
                b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, viewport=vp)
                await pg.evaluate(SEED); await pg.wait_for_timeout(300)
                for name, js in SCREENS: await visit(pg, name, js, lang, tag)
                check(f'[{tag}] no JS errors', not log['errors'], log['errors'][:3])
                await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
