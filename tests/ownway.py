# v99: riding your own way and pieces of way that are not on the map.
# 1. A route built A→B: off the route, a new way straight to the destination wins when it is shorter than going back.
# 2. A GPX track: the way back is ignored again and again (≥ 1 min, ≥ 400 m away) → «riding your own way», to the finish.
# 3. A missed turn on a GPX track still gets the normal way back to the route.
# 4. Riding 50 m beside a mapped road for ~150 m → «save this section?»; «Save» keeps it (drawn, stored, survives reload),
#    riding it again asks nothing; «No» saves nothing; voice «да» answers; the built-in engine gets it as a way.
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
LAT0, LON0 = 32.10, 34.88
KX = 111320 * math.cos(LAT0 * math.pi / 180); KY = 110540
def ll(n, e): return [LAT0 + n / KY, LON0 + e / KX]
STRAIGHT = [ll(i * 50, 0) + [20] for i in range(61)]                 # 3 km straight north
SPY = "window.__said = []; { const s = window.say; window.say = function (t) { window.__said.push(t); try { return s.apply(this, arguments); } catch (e) {} }; }"
ST = "({name: Nav.route && Nav.route.name, total: Nav.route && Math.round(Nav.route.total), said: window.__said.slice(), first: Nav.route && Nav.route.coords[0], last: Nav.route && Nav.route.coords[Nav.route.coords.length - 1]})"

def road_overpass(u):
    # One mapped road: the north–south line through LON0, from 2 km south to 4 km north.
    g = [{"lat": ll(n, 0)[0], "lon": ll(n, 0)[1]} for n in range(-2000, 4001, 100)]
    return {"elements": [{"type": "way", "id": 1, "geometry": g}]}

async def run(p, url, mocks, start, settings=None):
    st = [['velo:settings', json.dumps({**{'orient': 'compass'}, **(settings or {})})]]
    b, ctx, pg, log = await open_app(p, url + '?lang=ru', mocks, geo=tuple(start), storage=st)
    await pg.wait_for_timeout(1200); await pg.evaluate(SPY)
    async def go(pts, step=8, wait=700, acc=5):
        for (n0, e0), (n1, e1) in zip(pts, pts[1:]):
            d = math.hypot(n1 - n0, e1 - e0); k = max(1, round(d / step))
            for i in range(1, k + 1):
                la, lo = ll(n0 + (n1 - n0) * i / k, e0 + (e1 - e0) * i / k)
                await ctx.set_geolocation({'latitude': la, 'longitude': lo, 'accuracy': acc}); await pg.wait_for_timeout(wait)
    return b, ctx, pg, log, go

def m_of(c): return [round((c[0] - LAT0) * KY), round((c[1] - LON0) * KX)]

async def main():
    url = serve(8831)
    async with async_playwright() as p:
        # ---- 1. Built route A→B, the rider turns off towards the destination another way.
        m = Mocks(); b, ctx, pg, log, go = await run(p, url, m, ll(0, 0))
        await pg.evaluate(f"Nav.set({{name: 'Домой', coords: {json.dumps(STRAIGHT)}, opts: {{bike: 'xc', terrain: 'mixed', engine: 'auto', mode: 'bike'}}, noAsk: true}}); Nav.setAt -= 300000")
        await go([(0, 0), (300, 0), (300, 300)])
        await pg.wait_for_function("window.__said.some(x => x && x.includes('к финишу'))", timeout=40000)
        s = await pg.evaluate(ST)
        check('1.1 built route, off towards the finish: rebuilt to the finish, not back', any(x and 'перестроен к финишу' in x for x in s['said']), s['said'])
        check('1.2 …the new way starts where the rider is and ends at the destination', m_of(s['first'])[1] > 30 and m_of(s['last']) == [3000, 0], (m_of(s['first']), m_of(s['last'])))
        check('1.3 …never «back to the route»', not any(x and 'Возвращаемся на маршрут' in x for x in s['said']), s['said'])
        check('1 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 2. GPX track: the way back is ignored, the rider keeps going east.
        m = Mocks(); b, ctx, pg, log, go = await run(p, url, m, ll(0, 0))
        await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(STRAIGHT)}, noAsk: true}}); Nav.setAt -= 300000")
        await go([(0, 0), (300, 0), (300, 1100)])
        s = await pg.evaluate(ST)
        n_back = sum(1 for x in s['said'] if x and ('Возвращаемся на маршрут' in x or 'вернитесь на маршрут' in x))
        own = [x for x in s['said'] if x and 'своей дорогой' in x]
        check('2.1 GPX track: first the way back is offered', n_back >= 1, s['said'])
        check('2.2 ignored again and again → «riding your own way», rebuilt to the finish', len(own) >= 1, s['said'])
        check('2.3 …the way back is offered only a few times before that', n_back <= 3, n_back)
        check('2.4 …the route now ends at the finish of the track', m_of(s['last']) == [3000, 0], m_of(s['last']))
        check('2 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 3. A missed turn on a GPX track: still back to the route.
        m = Mocks(); b, ctx, pg, log, go = await run(p, url, m, ll(0, 0))
        await pg.evaluate(f"Nav.set({{name: 'Трек', coords: {json.dumps(STRAIGHT)}, noAsk: true}}); Nav.setAt -= 300000")
        await go([(0, 0), (300, 0), (300, 120)])
        await pg.wait_for_function("Nav.route && Nav.route.rr", timeout=40000)
        s = await pg.evaluate(ST)
        check('3.1 missed turn on a track: the way back to the route, not to the finish', any(x and ('Возвращаемся на маршрут' in x or 'вернитесь на маршрут' in x) for x in s['said']) and not any(x and 'своей дорогой' in x for x in s['said']), s['said'])
        check('3 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 4. A section that is not on the map.
        m = Mocks(); m.overpass = road_overpass
        b, ctx, pg, log, go = await run(p, url, m, ll(0, 0))
        await pg.evaluate("Ride.start()")
        await go([(0, 0), (200, 0), (230, 50), (330, 50), (360, 0), (420, 0)])
        await pg.wait_for_timeout(500)
        a = await pg.evaluate("({open: !document.getElementById('ask-nw').hidden, info: document.getElementById('nw-info').textContent, len: NewWays.ask && Math.round(NewWays.ask.len), said: window.__said.slice()})")
        check('4.1 back on the road after an unmapped piece: «save this section?»', a['open'] and a['len'] and a['len'] >= 100, a)
        check('4.2 …said aloud', any(x and 'нет на карте' in x for x in a['said']), a['said'])
        await pg.click('#nw-yes'); await pg.wait_for_timeout(500)
        r = await pg.evaluate("(async () => { const v = await DB.get('kv', 'myWays'); return {n: v && v.ways.length, drawn: NewWays.layer.getLayers().length, open: !document.getElementById('ask-nw').hidden, maxE: v && Math.max(...v.ways[0].coords.map(q => (q[1] - 34.88) * 111320 * Math.cos(32.1 * Math.PI / 180)))}; })()")
        check('4.3 «Save»: stored and drawn on the map, dialog closed', r['n'] == 1 and r['drawn'] == 1 and not r['open'], r)
        check('4.4 …the stored piece is the one ridden (≈50 m east of the road)', r['maxE'] and 40 <= r['maxE'] <= 60, r)
        # ride the same piece again: it is on «my map» now
        await go([(420, 0), (360, 0), (330, 50), (230, 50), (200, 0), (150, 0)])
        a = await pg.evaluate("({open: !document.getElementById('ask-nw').hidden, q: NewWays.queue.length, ask: !!NewWays.ask})")
        check('4.5 riding the saved piece again asks nothing', not a['open'] and not a['ask'] and a['q'] == 0, a)
        # built-in engine: the saved piece becomes a way joined to the road
        g = await pg.evaluate("""(() => { const lat = [], lon = []; for (let n = 0; n <= 600; n += 50) { lat.push(32.1 + n / 110540); lon.push(34.88); }
          const reg = { lat: Float64Array.from(lat), lon: Float64Array.from(lon), ways: [{ n: Int32Array.from(lat.map((_, i) => i)), t: { highway: 'residential' } }] };
          const r2 = NewWays.addTo(reg); return { ways: r2.ways.length, nodes: r2.lat.length, orig: reg.ways.length, mine: r2.ways.slice(1).every(w => w.t.highway === 'path') }; })()""")
        check('4.6 built-in engine: the piece and its two joins to the road are added as ways', g['ways'] == g['orig'] + 3 and g['mine'] and g['nodes'] > 13, g)
        # «No» saves nothing; voice «да» answers the question
        await go([(150, 0), (200, 0), (230, -50), (330, -50), (360, 0), (420, 0)])
        a = await pg.evaluate("!document.getElementById('ask-nw').hidden")
        check('4.7 another unmapped piece (west side): asked again', a)
        await pg.click('#nw-no'); await pg.wait_for_timeout(400)
        n = await pg.evaluate("(async () => (await DB.get('kv', 'myWays')).ways.length)()")
        check('4.8 «No»: nothing more saved', n == 1, n)
        await pg.evaluate("NewWays.done({ pts: [[32.1, 34.881], [32.1003, 34.8815], [32.1006, 34.8815], [32.1009, 34.8815], [32.1012, 34.8815], [32.1015, 34.8815], [32.1018, 34.881]], off: 6 })")
        v = await pg.evaluate("Voice.parse('да')")
        check('4.9 voice «да» while the question is open → save', v and v.get('kind') == 'nwyes', v)
        v2 = await pg.evaluate("Voice.parse('дальше по улице')")
        check('4.10 …«дальше …» is not «да»', not v2 or v2.get('kind') != 'nwyes', v2)
        await pg.click('#nw-yes'); await pg.wait_for_timeout(400)
        await pg.reload(); await pg.wait_for_timeout(1800)
        r = await pg.evaluate("({n: NewWays.ways.length, drawn: NewWays.layer ? NewWays.layer.getLayers().length : 0})")
        check('4.11 after a reload the saved pieces are back on the map', r['n'] == 2 and r['drawn'] == 2, r)
        # delete from the map popup
        await pg.evaluate("NewWays.remove(NewWays.ways[0].id)"); await pg.wait_for_timeout(300)
        n = await pg.evaluate("(async () => (await DB.get('kv', 'myWays')).ways.length)()")
        check('4.12 a piece can be deleted', n == 1, n)
        check('4 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 5. Setting off: never asked.
        m = Mocks(); m.overpass = road_overpass
        b, ctx, pg, log, go = await run(p, url, m, ll(0, 0), {'newways': False})
        await pg.evaluate("Ride.start()")
        await go([(0, 0), (200, 0), (230, 50), (330, 50), (360, 0), (420, 0)])
        check('5.1 setting off: no question', await pg.evaluate("document.getElementById('ask-nw').hidden && !NewWays.ask"))
        check('5 no JS errors', not log['errors'], log['errors'][:3]); await b.close()

        # ---- 6. Hebrew and English: the dialog is translated.
        for lang in ['he', 'en']:
            m = Mocks(); b, ctx, pg, log = await open_app(p, url + '?lang=' + lang, m, geo=tuple(ll(0, 0)))
            await pg.wait_for_timeout(1200)
            await pg.evaluate("NewWays.inited = true; NewWays.done({ pts: [[32.1, 34.881], [32.1003, 34.8815], [32.1006, 34.8815], [32.1009, 34.8815], [32.1012, 34.8815], [32.1015, 34.8815], [32.1018, 34.881]], off: 6 })")
            await pg.wait_for_timeout(300)
            t = await pg.evaluate("document.getElementById('ask-nw').innerText")
            import re
            check(f'6 {lang}: dialog without untranslated Russian', not re.search('[А-Яа-яЁё]', t), t)
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
