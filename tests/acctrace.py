# v151 (audit R03): switching accounts while a sync or a token refresh is under way. Account A's sync is held up by the
# network; meanwhile A signs out and B signs in; then A's answers arrive: nothing of A's goes into B's account, B's sync
# record is not overwritten by A's, the phone stays signed in as B, and B's own sync then runs normally. The same with
# A's token refresh answered late: it does not write A's tokens over B's sign-in. A sync not disturbed works as before.
# Firebase is the in-memory fake of tests/account.py with a gate on its answers. Run: python3 tests/acctrace.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks
from account import Firebase, phone, synced
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

class Gated(Firebase):
    def __init__(s): super().__init__(); s.gate = {}; s.held = 0
    async def handle(s, route):
        u = route.request.url
        for host, ev in list(s.gate.items()):
            if host in u and route.request.method != 'OPTIONS' and not ev.is_set():
                s.held += 1; await ev.wait()
        return await super().handle(route)
    def hold(s, host): s.gate[host] = asyncio.Event()
    def release(s, host): s.gate.pop(host).set()

async def sign_in(pg, email, reg=False):
    await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true")
    await pg.fill('#ac-email', email); await pg.fill('#ac-pass', 'secret77'); await pg.click('#ac-reg' if reg else '#ac-login')
    await pg.wait_for_function("() => !!Acct.u && Acct.u.email === %s" % json.dumps(email), timeout=8000)

async def sign_out(pg):
    await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true")
    await pg.click('#ac-out'); await pg.wait_for_function("() => !Acct.u", timeout=5000)

ROUTE = "(n => DB.put('routes', { id: 'rtA', name: n, coords: [[32.09,34.88,40],[32.1,34.89,60]], dist: 1500, asc: 20, created: 1, src: 'test', wpts: [] }))"

async def main():
    url = serve(8913); m = Mocks(); fb = Gated()
    async with async_playwright() as p:
        b, ctx, pg, log = await phone(p, url, m, fb)
        pg.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
        await sign_in(pg, 'b@example.com', True); await synced(pg); await sign_out(pg)   # B exists
        await pg.evaluate(ROUTE + "('Маршрут А')")
        await sign_in(pg, 'a@example.com', True); await synced(pg)
        ua, ub = fb.users['a@example.com']['uid'], fb.users['b@example.com']['uid']
        check('(account A synced its route)', 'routes~rtA' in fb.items(ua), sorted(fb.items(ua)))
        # ---- 1: A's sync held up; A out, B in; then A's answers arrive
        fb.hold('firestore.googleapis.com')
        await pg.evaluate(ROUTE + "('Маршрут А, изменён')"); await pg.evaluate("clearTimeout(Sync.t); Sync.run(); 0")
        await pg.wait_for_timeout(500); held = fb.held
        await sign_out(pg); await sign_in(pg, 'b@example.com')
        fb.release('firestore.googleapis.com')
        await synced(pg); await pg.wait_for_timeout(1500); await synced(pg)
        ib = fb.items(ub)
        check('A\'s sync held up, then B signed in: A\'s route is not written into B\'s account', held >= 1 and 'routes~rtA' not in ib, (held, sorted(ib)))
        st = await pg.evaluate("({ who: Acct.u && Acct.u.email, uid: Acct.u && Acct.u.uid, keys: Object.keys(Sync.meta().items), last: lsGet('syncLast', null), err: Sync.err })")
        check('B\'s sync record is B\'s (A\'s items not in it); the phone is signed in as B; no error shown', st['who'] == 'b@example.com' and 'routes~rtA' not in st['keys'] and st['last'] == ub and not st['err'], st)
        await pg.evaluate("(async () => { await DB.put('routes', { id: 'rtB', name: 'Маршрут Б', coords: [[32.09,34.88,40],[32.12,34.91,60]], dist: 3500, asc: 20, created: 3, src: 'test', wpts: [] }); clearTimeout(Sync.t); Sync.run(); })()")
        await pg.wait_for_timeout(300); await synced(pg)
        check('B\'s own sync then works: its new route goes to B, not to A', 'routes~rtB' in fb.items(ub) and 'routes~rtB' not in fb.items(ua))
        # ---- 2: A's token refresh answered after B signed in
        await sign_out(pg); await sign_in(pg, 'a@example.com'); await synced(pg)
        fb.hold('securetoken.googleapis.com')
        await pg.evaluate("(() => { const u = Acct.u; u.exp = 0; lsSet('acct', u); clearTimeout(Sync.t); Sync.run(); })()")
        await pg.wait_for_timeout(500); held2 = fb.held - held
        await sign_out(pg); await sign_in(pg, 'b@example.com')
        fb.release('securetoken.googleapis.com'); await pg.wait_for_timeout(1500); await synced(pg)
        st = await pg.evaluate("({ who: Acct.u && Acct.u.email, uid: Acct.u && Acct.u.uid, tok: Acct.u && Acct.u.idToken })")
        check('A\'s token refresh answered after B signed in: B stays signed in with B\'s own token', held2 >= 1 and st['uid'] == ub and st['tok'] == 'tok-' + ub, (held2, st))
        # ---- 3: an expired token refreshed once for requests asked together
        n0 = sum(1 for c in m.calls if 'securetoken' in c)
        calls = []
        ctx.on('request', lambda r: calls.append(r.url) if 'securetoken' in r.url else None)
        await pg.evaluate("(() => { const u = Acct.u; u.exp = 0; lsSet('acct', u); })()")
        toks = await pg.evaluate("Promise.all([Acct.token(), Acct.token(), Acct.token()])")
        check('requests asked together share one token refresh', len(calls) == 1 and len(set(toks)) == 1 and toks[0] == 'tok-' + ub, (len(calls), toks))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
