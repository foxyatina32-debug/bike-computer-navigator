# v132: street names at the turns survive a busy OpenStreetMap server. Before: the names were one query with no second
# try — a refused one («429 Too Many Requests», more likely since the start of a route asks more: before the ride, stops,
# voice) or an empty answer with an error remark (which was even kept for the route) left the turns without names.
# Now: retries on the other servers and after 4 s / 10 s, empty / error answers not kept, at most 2 queries at a time
# with street names and road alerts first, ways reused for the same streets (continue from here) without a new query.
# v133: the wait follows the query's own [timeout:N] (+15 s); while navigating one of the 2 is kept for street names /
# road alerts; servers that all hang are not asked round after round.
# Run: python3 tests/streetsbusy.py
import asyncio, sys, os, json, time
from urllib.parse import unquote_plus
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
A, C, B = (32.09, 34.88), (32.096, 34.88), (32.096, 34.888)
ROUTE = [[A[0] + (C[0] - A[0]) * t / 30, A[1], None] for t in range(31)] + [[C[0], C[1] + (B[1] - C[1]) * t / 30, None] for t in range(1, 31)]
def way(i, tags, a, b): return {'type': 'way', 'id': i, 'tags': tags, 'geometry': [{'lat': a[0] - (b[0] - a[0]) * .1, 'lon': a[1] - (b[1] - a[1]) * .1}, {'lat': b[0] + (b[0] - a[0]) * .1, 'lon': b[1] + (b[1] - a[1]) * .1}]}
WAYS = [way(1, {'highway': 'residential', 'name:ru': 'Бялик', 'name': 'ביאליק'}, A, C), way(2, {'highway': 'residential', 'name:ru': 'Жаботинского', 'name': "ז'בוטינסקי"}, C, B)]
CORS = {'Access-Control-Allow-Origin': '*'}
NAMES = "Nav.route && Nav.route.cues[0].txt === 'Поверните направо на улицу Жаботинского'"

class Server:
    def __init__(s): s.mode = 'ok'; s.until = 0; s.log = []; s.inflight = 0; s.peak = 0; s.delay = 0.05; s.low = 0; s.lowpeak = 0; s.t0 = time.time()
    async def handle(s, route):
        q = unquote_plus((route.request.post_data or '')[5:]); kind = 'st' if q.startswith('/*st*/') else 'ra' if q.startswith('/*ra*/') else 'x'
        s.log.append((round(time.time(), 2), kind, route.request.url.split('/')[2]))
        s.inflight += 1; s.peak = max(s.peak, s.inflight)
        if kind == 'x': s.low += 1; s.lowpeak = max(s.lowpeak, s.low)
        try:
            if s.mode == 'hang':
                await asyncio.sleep(30)
                try: await route.fulfill(json={'elements': []}, headers=CORS)
                except Exception: pass
                return
            await asyncio.sleep(s.delay)
            busy = time.time() < s.until
            if busy and s.mode == '429': return await route.fulfill(status=429, body='rate_limited', headers=CORS)
            if busy and s.mode == 'remark': return await route.fulfill(json={'elements': [], 'remark': 'runtime error: Query timed out in "query" at line 1 after 40 seconds.'}, headers=CORS)
            return await route.fulfill(json={'elements': WAYS if kind == 'st' else []}, headers=CORS)
        finally:
            s.inflight -= 1
            if kind == 'x': s.low -= 1

async def start(p, url, srv):
    b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks())
    await ctx.route('**/api/interpreter', srv.handle)
    return b, ctx, pg, log

async def main():
    url = serve(9063)
    async with async_playwright() as p:
        # 1. the server refuses everything for 6 s (429)
        srv = Server(); b, ctx, pg, log = await start(p, url, srv)
        srv.mode, srv.until = '429', time.time() + 6
        await pg.evaluate(f"Nav.set({{ name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true }})")
        try: await pg.wait_for_function(NAMES, timeout=25000); ok = True
        except Exception: ok = False
        st = [x for x in srv.log if x[1] == 'st']
        check('server busy for 6 s («429»): the street names still come (tried again)', ok, (len(st), sorted({x[2] for x in st})))
        check('… on the other servers too, then after a pause', len({x[2] for x in st}) >= 2 and st[-1][0] - st[0][0] >= 4, [(round(x[0] - st[0][0], 1), x[2]) for x in st])
        # 2. continue from here (the same streets): no new query, the names are there
        n0 = len([x for x in srv.log if x[1] == 'st'])
        await pg.evaluate(f"Nav.set({{ name: 'T', coords: {json.dumps(ROUTE[8:])}, noAsk: true, keepView: true }})")
        await pg.wait_for_timeout(1500)
        check('a route on the same streets (continue from here): names without a new query', await pg.evaluate(NAMES) and len([x for x in srv.log if x[1] == 'st']) == n0, len([x for x in srv.log if x[1] == 'st']) - n0)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # 3. a busy server answers «200» with nothing and an error remark: not kept, asked again
        srv = Server(); b, ctx, pg, log = await start(p, url, srv)
        srv.mode, srv.until = 'remark', time.time() + 6
        await pg.evaluate(f"Nav.set({{ name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true }})")
        try: await pg.wait_for_function(NAMES, timeout=25000); ok = True
        except Exception: ok = False
        check('an empty answer with «runtime error … timed out»: asked again, the names come', ok)
        kept = await pg.evaluate("DB.get('kv', 'st:' + insKey(Nav.route.coords)).then(v => v ? v.ways.length : -1)")
        check('… and what is kept for the route is the real answer, not the empty one', kept == 2, kept)
        await b.close()
        # 4. at most 2 queries at a time, street names first
        srv = Server(); srv.delay = 0.6; b, ctx, pg, log = await start(p, url, srv)
        order = await pg.evaluate("""async () => { const done = []; const qs = ['/*a*/', '/*b*/', '/*c*/', '/*d*/', '/*st*/'].map(t => overpass(t + '[out:json];node(1);out;').then(() => done.push(t)));
          await Promise.all(qs); return done; }""")
        check('5 queries at once → never more than 2 at the server', srv.peak <= 2, srv.peak)
        check('the street-name query goes before the waiting ones', order.index('/*st*/') <= 2, order)
        check('not navigating: 2 long queries may run together', srv.lowpeak == 2, srv.lowpeak)
        # 5. v133: the wait follows the query's own limit
        t = await pg.evaluate("typeof ovTimeout !== 'function' ? null : [ovTimeout('/*st*/[out:json][timeout:40];way(1);out;'), ovTimeout(overpassGraphQuery(31, 34, 31.1, 34.1, 180)), ovTimeout('[out:json];node(1);out;')]")
        check('the wait for an answer = the query\'s [timeout:N] + 15 s (street names 55 s, an offline area 195 s)', t == [55000, 195000, 60000], t)
        await b.close()
        # 6. v133: navigating — long queries never take both slots, the street names start at once
        srv = Server(); srv.delay = 1.5; b, ctx, pg, log = await start(p, url, srv)
        await pg.evaluate(f"Nav.set({{ name: 'T', coords: {json.dumps(ROUTE)}, noAsk: true }})"); await pg.wait_for_function(NAMES, timeout=15000)
        srv.log.clear(); srv.lowpeak = 0
        r = await pg.evaluate("""async () => { const t0 = Date.now(), lows = ['/*a*/', '/*b*/', '/*c*/'].map(t => overpass(t + '[out:json];node(1);out;'));
          await new Promise(r => setTimeout(r, 200)); const s0 = Date.now(); await overpass('/*st*/[out:json][timeout:40];way(1);out;'); const st = Date.now() - s0; await Promise.all(lows); return { st, all: Date.now() - t0 }; }""")
        check('navigating: at most 1 long query at a time — a slot stays free for the street names', srv.lowpeak == 1, srv.lowpeak)
        check('… so the street names come right away (not after the 3 long ones)', r['st'] < 2500, r)
        await b.close()
        # 7. v133: every server hangs → asked once each, not round after round
        srv = Server(); srv.mode = 'hang'; b, ctx, pg, log = await start(p, url, srv)
        t0 = time.time()
        err = await pg.evaluate("overpass('/*h*/[out:json][timeout:1];node(1);out;').then(() => 'ok', e => e.name)")
        dt = time.time() - t0
        check('all servers hang: one try each (3 × 16 s), then the error — no more rounds', err == 'AbortError' and len(srv.log) == 3 and dt < 60, (err, len(srv.log), round(dt)))
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
