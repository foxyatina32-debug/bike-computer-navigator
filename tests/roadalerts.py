# v122: «Впереди…» — road alerts along the route from OpenStreetMap: bridge, tunnel, level crossing, steps, barrier,
# bollards, ford (300 m ahead, card + voice), traffic lights / stop / give way / speed bump (90 m ahead, card only),
# steep descent and switchbacks on the same card. A bridge you ride UNDER and a gate beside the road are not alerts.
# Kept on the phone: the same route offline still has them. Switch in Settings. Hebrew / English translated.
# Overpass is replaced by a fixture (window.overpass for the «/*ra*/» query). Run: python3 tests/roadalerts.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
LAT0, LON = 32.10, 34.88
M = 1 / 110540                       # one metre north
KX = 1 / (111320 * 0.8471)           # one metre east at 32.1°
ROUTE = [[LAT0 + d * M, LON, 20] for d in range(0, 2201, 20)]   # 2.2 km straight north
def at(d, east=0): return {'lat': LAT0 + d * M, 'lon': LON + east * KX}
def way(tags, d0, d1, east=0, n=4): return {'type': 'way', 'tags': tags, 'geometry': [at(d0 + (d1 - d0) * k / (n - 1), east) for k in range(n)]}
def node(tags, d, east=0): return {'type': 'node', 'tags': tags, **at(d, east)}
ELS = [way({'highway': 'cycleway', 'bridge': 'yes'}, 300, 340),
       node({'railway': 'level_crossing'}, 600),
       way({'highway': 'steps'}, 900, 915),
       node({'highway': 'traffic_signals'}, 1200),
       node({'barrier': 'gate'}, 1400, east=40),                                   # 40 m beside the route: not on it
       {'type': 'way', 'tags': {'highway': 'primary', 'bridge': 'yes'}, 'geometry': [at(1600, -60), at(1600, -20), at(1600, 20), at(1600, 60)]},   # crosses OVER the route
       node({'ford': 'yes'}, 1800), node({'barrier': 'bollard'}, 2000)]
FAKE = f"""(() => {{ window.__said = []; const f = {{ speaking: false, pending: false, cancel() {{}}, speak(u) {{ window.__said.push(u.text); }}, getVoices() {{ return []; }} }};
  Object.defineProperty(window, 'speechSynthesis', {{ value: f, configurable: true }}); S.voice = true;
  const o = window.overpass; window.__raCalls = 0; window.overpass = async q => {{ if (q.startsWith('/*ra*/')) {{ window.__raCalls++; if (window.__raFail) throw new Error('offline'); return {{ elements: {json.dumps(ELS)} }}; }} return o(q); }}; }})()"""
CARD = "(() => { const e = document.getElementById('ahc'); return e.hidden ? null : { t: document.getElementById('ahc-t').textContent, d: document.getElementById('ahc-d').textContent, icon: !!document.querySelector('#ahc-i svg') }; })()"
async def go(pg, d): await pg.evaluate(f"Nav.progress = {d}; Nav.aheadCheck()")

async def main():
    url = serve(8941); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(LAT0 - 30 * M, LON))
        await pg.evaluate(FAKE)
        await pg.evaluate(f"Nav.set({{ name: 'Тест', coords: {json.dumps(ROUTE)}, noAsk: true }})")
        await pg.wait_for_function("Nav.route.ahead.some(h => h.kind === 'bridge')", timeout=8000)
        kinds = await pg.evaluate("Nav.route.ahead.map(h => h.kind + '@' + Math.round(h.d))")
        check('alerts found on the route: bridge, level crossing, steps, lights, ford, bollards', [k.split('@')[0] for k in kinds] == ['bridge', 'rail', 'steps', 'signals', 'ford', 'bollard'], kinds)
        check('positions along the route are right (±15 m)', all(abs(int(k.split('@')[1]) - want) <= 15 for k, want in zip(kinds, [300, 600, 900, 1200, 1800, 2000])), kinds)
        check('a bridge crossing OVER the route and a gate 40 m beside it are not alerts', not any(k.startswith('gate') for k in kinds) and sum(k.startswith('bridge') for k in kinds) == 1, kinds)
        # card timing
        await go(pg, 0); c0 = await pg.evaluate(CARD)
        await go(pg, 10); c1 = await pg.evaluate(CARD)
        check('300 m before the bridge: no card yet at 300+ m… then «Мост, через 290 м» with a sign', c0 is None and c1 and c1['t'] == 'Мост' and c1['d'] == 'через 290 м' and c1['icon'], (c0, c1))
        await go(pg, 200); c2 = await pg.evaluate(CARD)
        await go(pg, 292); c3 = await pg.evaluate(CARD)
        check('the distance counts down; «сейчас» at the bridge', c2 and c2['d'] == 'через 100 м' and c3 and c3['d'] == 'сейчас', (c2, c3))
        said = await pg.evaluate("window.__said.join(' | ')")
        check('said once: «через 300 метров мост»', said.count('мост') == 1 and 'Через 300 метров мост' in said, said)
        await go(pg, 360); c4 = await pg.evaluate(CARD)
        check('passed — the card goes', c4 is None or c4['t'] != 'Мост', c4)
        await go(pg, 590); c5 = await pg.evaluate(CARD)
        check('level crossing: card «Ж/д переезд» and voice', c5 and c5['t'] == 'Ж/д переезд' and 'железнодорожный переезд' in await pg.evaluate("window.__said.join(' | ')"), c5)
        await go(pg, 870); c6 = await pg.evaluate(CARD)
        check('steps: «Лестница — велосипед в руки»', c6 and c6['t'] == 'Лестница — велосипед в руки', c6)
        await go(pg, 1050); c7 = await pg.evaluate(CARD)
        await go(pg, 1130); c8 = await pg.evaluate(CARD)
        n_said = await pg.evaluate("window.__said.length")
        check('traffic lights: not at 150 m, card at 70 m, no voice', c7 is None and c8 and c8['t'] == 'Светофор' and not any('Светофор' in x or 'светофор' in x for x in await pg.evaluate("window.__said")), (c7, c8))
        await go(pg, 1560); c9 = await pg.evaluate(CARD)
        check('under the road bridge: no «Мост» card', c9 is None or c9['t'] != 'Мост', c9)
        await go(pg, 1700); c10 = await pg.evaluate(CARD)
        check('ford: «Брод — переезд через воду»', c10 and c10['t'] == 'Брод — переезд через воду', c10)
        nb, card = await pg.evaluate("[document.getElementById('navb').getBoundingClientRect().bottom, document.getElementById('ahc').getBoundingClientRect().top]")
        check('the card sits under the turn banner', card >= nb, (nb, card))
        # switch off: no OSM cards, no voice (steep descent / switchbacks stay)
        await pg.evaluate("S.alerts = false; Nav.aheadSaid = {}; window.__said = []"); await go(pg, 1950); c11 = await pg.evaluate(CARD)
        check('«Впереди…» switched off: no card, no voice', c11 is None and not await pg.evaluate("window.__said.length"), c11)
        await pg.evaluate("S.alerts = true")
        # steep descent on the same card
        await pg.evaluate("Nav.route.ahead.push({ kind: 'desc', d: 2100, len: 80, pct: 14 }); Nav.route.ahead.sort((a, b) => a.d - b.d); Nav.aheadSaid = {}")
        await go(pg, 2050); c12 = await pg.evaluate(CARD)
        check('steep descent on the card: «Крутой спуск 14%»', c12 and c12['t'] == 'Крутой спуск 14%', c12)
        # cached: the same route again with no network → alerts still there
        await pg.evaluate("Nav.stop(); window.__raFail = true"); await pg.wait_for_timeout(300)
        n0 = await pg.evaluate("window.__raCalls")
        await pg.evaluate(f"Nav.set({{ name: 'Тест', coords: {json.dumps(ROUTE)}, noAsk: true }})")
        await pg.wait_for_function("Nav.route.ahead.some(h => h.kind === 'bridge')", timeout=8000)
        check('the same route offline: alerts from the phone (no new request)', await pg.evaluate("window.__raCalls") == n0)
        # a reroute keeps the alerts without asking again
        await pg.evaluate(f"Nav.set({{ name: 'Тест', coords: {json.dumps(ROUTE[20:])}, noAsk: true, keepView: true, rr: true }})"); await pg.wait_for_timeout(200)
        kinds2 = await pg.evaluate("Nav.route.ahead.map(h => h.kind)")
        check('after a reroute the alerts are matched to the new line at once', 'rail' in kinds2 and 'bridge' not in kinds2, kinds2)
        await pg.evaluate("Nav.stop()")
        check('navigation stopped — no card left', await pg.evaluate("document.getElementById('ahc').hidden"))
        check('Settings switch present and on', await pg.evaluate("document.getElementById('s-alerts').checked"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, geo=(LAT0 - 30 * M, LON))
            await pg.evaluate(FAKE)
            await pg.evaluate(f"Nav.set({{ name: 'X', coords: {json.dumps(ROUTE)}, noAsk: true }})")
            await pg.wait_for_function("Nav.route.ahead.some(h => h.kind === 'bridge')", timeout=8000)
            out = []
            for d in (100, 400, 700, 1150): await go(pg, d); out.append(await pg.evaluate(CARD))
            txt = ' '.join(c['t'] + ' ' + c['d'] for c in out if c) + ' ' + ' '.join(await pg.evaluate("window.__said"))
            ru = [w for w in txt.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: cards and voice translated', len([c for c in out if c]) == 4 and not ru, (txt[:160], ru[:5]))
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
