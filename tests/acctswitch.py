# v147: two accounts on one phone stay apart. Signed in as A (its route, ride and settings with a map key synced), then out;
# a route made while signed out; then signed in as B: B gets the new route, but none of A's routes, rides or settings; A's
# map key leaves the phone (B neither gets nor uses it); back to A: A gets nothing of B's and its key comes back. Both accounts keep their own data in the cloud.
# Firebase is the in-memory fake of tests/account.py. Run: python3 tests/acctswitch.py
import asyncio, sys, os, json, base64, gzip
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks
from account import Firebase, phone, synced
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

def body(f):   # what a document holds: base64 bytes, gzipped or not (one part is enough for the settings)
    if not f or 'b' not in f: return ''
    raw = base64.b64decode(f['b']['bytesValue'] or '')
    if f.get('z', {}).get('stringValue') == 'gzip': raw = gzip.decompress(raw)
    return raw.decode('utf-8', 'replace')

async def sign(pg, email, reg):
    await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true")
    await pg.fill('#ac-email', email); await pg.fill('#ac-pass', 'secret77'); await pg.click('#ac-reg' if reg else '#ac-login')
    try: await pg.wait_for_event('load', timeout=4000); await pg.wait_for_function('window.__appReady === true', timeout=20000)
    except Exception: pass
    await synced(pg)

async def main():
    url = serve(8903); m = Mocks(); fb = Firebase()
    async with async_playwright() as p:
        b, ctx, pg, log = await phone(p, url, m, fb)
        pg.on('dialog', lambda d: asyncio.ensure_future(d.accept()))   # «Выйти из аккаунта?» → yes
        await pg.evaluate("""(async () => {
          await DB.put('routes', { id: 'rtA', name: 'Маршрут А', coords: [[32.09,34.88,40],[32.1,34.89,60]], dist: 1500, asc: 20, created: 1, src: 'test', wpts: [] });
          await DB.put('rides', { id: 'rdA', name: 'Поездка А', start: 1.7e12, end: 1.7e12 + 3600e3, type: 'bike', dist: 1500, movingMs: 6e5, track: [[32.09,34.88,40,1.7e12],[32.1,34.89,60,1.7e12+6e5]] });
          lsSet('gkey', 'AIza-of-A');
        })()""")
        await sign(pg, 'a@example.com', True)
        ua = fb.users['a@example.com']['uid']; ia = fb.items(ua)
        check('account A: its route, ride and settings uploaded', all(k in ia for k in ('routes~rtA', 'rides~rdA', 'ls~all')), sorted(ia))
        await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true")
        await pg.click('#ac-out'); await pg.wait_for_timeout(400)
        await pg.evaluate("DB.put('routes', { id: 'rtFree', name: 'Сделан без аккаунта', coords: [[32.09,34.88,40],[32.11,34.9,60]], dist: 2500, asc: 20, created: 2, src: 'test', wpts: [] })")
        await sign(pg, 'b@example.com', True)
        ub = fb.users['b@example.com']['uid']; ib = fb.items(ub)
        check('account B: none of A\'s routes and rides uploaded to it', not any(k in ib for k in ('routes~rtA', 'rides~rdA')), sorted(ib))
        la = body(fb.items(ua).get('ls~all')); ls = body(ib.get('ls~all'))
        check('(the check reads the settings: A\'s own copy has its map key)', 'AIza-of-A' in la, la[:80])
        check('account B: A\'s settings (A\'s map key) not uploaded to it', 'AIza-of-A' not in ls, ls[:120])
        check('account B: the route made while signed out is uploaded to it', 'routes~rtFree' in ib, sorted(ib))
        loc = await pg.evaluate("(async () => (await DB.all('routes')).map(r => r.id).sort())()")
        check('A\'s rides and routes stay on the phone (nothing deleted)', 'rtA' in loc and 'rtFree' in loc, loc)
        k = await pg.evaluate("({ gkey: lsGet('gkey', ''), toast: window.__lastToasts || '' })")
        await pg.wait_for_timeout(3800); t = await pg.evaluate("window.__lastToasts || ''")
        check('A\'s map key is not left for B to use; the phone says so', k['gkey'] == '' and 'прежнего аккаунта' in t, (k['gkey'], t[-160:]))
        ia2 = fb.items(ua)
        check('account A in the cloud unchanged: nothing of B\'s added, nothing deleted', 'routes~rtFree' not in ia2 and all(k in ia2 for k in ('routes~rtA', 'rides~rdA')) and not ia2['routes~rtA'].get('d', {}).get('booleanValue'), sorted(ia2))
        # a new route while B is signed in goes to B only
        await pg.evaluate("(async () => { await DB.put('routes', { id: 'rtB', name: 'Маршрут Б', coords: [[32.09,34.88,40],[32.12,34.91,60]], dist: 3500, asc: 20, created: 3, src: 'test', wpts: [] }); Sync.mark('routes', 'rtB'); })()")
        await pg.wait_for_timeout(300); await pg.evaluate("Sync.run()"); await synced(pg)
        check('a route saved while B is signed in goes to B', 'routes~rtB' in fb.items(ub))
        # back to A
        await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true")
        await pg.click('#ac-out'); await pg.wait_for_timeout(400)
        await sign(pg, 'a@example.com', False)
        ia3 = fb.items(ua)
        check('back to A: B\'s routes are not uploaded to A', not any(k in ia3 for k in ('routes~rtB', 'routes~rtFree')), sorted(ia3))
        check('back to A: A\'s map key comes back from its account', await pg.evaluate("lsGet('gkey', '')") == 'AIza-of-A', await pg.evaluate("lsGet('gkey', '')"))
        check('the whose-is-what record (and the kept list of settlements) never sent with the settings', not any(w in body(fb.items(x).get('ls~all')) for x in (ua, ub) for w in ('syncOwn', 'syncLast', 'placeList')))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
