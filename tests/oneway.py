# v151 (audit R04): the built-in router keeps to one-way streets. A short street (100 m) the wrong way against a legal
# detour (700 m): the route takes the detour (it used to take the wrong way — only ×6 dearer). oneway=yes / -1,
# oneway:bicycle=yes, a roundabout; open for bikes against the flow: oneway:bicycle=no, cycleway=opposite_lane,
# cycleway:left=opposite_lane; the legal direction goes straight. With no legal way at all: a clear message, translated.
# Run: python3 tests/oneway.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
# nodes: 0 = A, 1 = B (100 m east of A), 2 = above A, 3 = above B (300 m north)
GRAPH = """((tags, detour) => {
  const E = 100 / 94406, N = 300 / 110540, lat = [32, 32, 32 + N, 32 + N], lon = [34.8, 34.8 + E, 34.8, 34.8 + E];
  const ways = [{ n: Int32Array.from(tags.rev ? [1, 0] : [0, 1]), t: Object.assign({ highway: 'residential' }, tags.t) }];
  if (detour) ways.push({ n: Int32Array.from([0, 2, 3, 1]), t: { highway: 'residential' } });
  return makeGraph({ lat: Float64Array.from(lat), lon: Float64Array.from(lon), ways });
})"""
ROUTE = """((tags, detour, back) => { const G = (%s)(tags, detour); const A = [32, 34.8], B = [32, 34.8 + 100 / 94406];
  try { const r = graphRoute(G, back ? [B, A] : [A, B], 'xc', 'mixed'); return { d: Math.round(r.distance) }; } catch (e) { return { err: e.message, t: tr(e.message) }; } })""" % GRAPH

async def main():
    url = serve(8911)
    async with async_playwright() as p:
        for lang in ('ru', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), geo=(32.0, 34.8))
            await pg.wait_for_timeout(1000)
            run = lambda tags, detour=True, back=False: pg.evaluate(f"({ROUTE})({json.dumps(tags)}, {json.dumps(detour)}, {json.dumps(back)})")
            if lang == 'ru':
                for name, tags in (('oneway=yes (drawn B→A)', {'rev': True, 't': {'oneway': 'yes'}}),
                                   ('oneway=-1 (drawn A→B)', {'t': {'oneway': '-1'}}),
                                   ('oneway:bicycle=yes alone', {'rev': True, 't': {'oneway:bicycle': 'yes'}}),
                                   ('a roundabout', {'rev': True, 't': {'junction': 'roundabout'}})):
                    r = await run(tags)
                    check(f'{name}: the wrong way is closed — the route takes the 700-m detour', r.get('d', 0) >= 650, r)
                for name, tags in (('oneway:bicycle=no', {'rev': True, 't': {'oneway': 'yes', 'oneway:bicycle': 'no'}}),
                                   ('cycleway=opposite_lane', {'rev': True, 't': {'oneway': 'yes', 'cycleway': 'opposite_lane'}}),
                                   ('cycleway:left=opposite_lane', {'rev': True, 't': {'oneway': 'yes', 'cycleway:left': 'opposite_lane'}})):
                    r = await run(tags)
                    check(f'{name}: bikes may go against the flow — straight, 100 m', 90 <= r.get('d', 0) <= 110, r)
                r = await run({'rev': True, 't': {'oneway': 'yes'}}, True, True)
                check('the legal direction of a one-way street goes straight', 90 <= r.get('d', 0) <= 110, r)
                r = await run({'t': {}}, True)
                check('a two-way street goes straight', 90 <= r.get('d', 0) <= 110, r)
            r = await run({'rev': True, 't': {'oneway': 'yes'}}, False)
            want = 'против одностороннего движения' if lang == 'ru' else 'against one-way traffic'
            check(f'[{lang}] no legal way at all: no route, a clear message', 'err' in r and want in r.get('t', ''), r)
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
