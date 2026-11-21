# v151 (audit R09, R10). R09: own sections of way belong to an account. Signed in as A, its section is synced; then B signs
# in on the same phone: A's section is not on the map, not in B's backup, not used by the router, not uploaded to B; B's
# own new section goes to B only; back to A: A's section is back, B's is not shown. R10: a backup with a damaged route
# (coords {bad: true}) and a damaged ride: those are skipped and counted, the good ones restored, nothing breaks; the
# account's damaged copy is not written either. Firebase is the in-memory fake of tests/account.py.
# Run: python3 tests/accways.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks
from account import Firebase, phone, synced
from acctswitch import body
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

async def sign(pg, email, reg):
    await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true")
    await pg.fill('#ac-email', email); await pg.fill('#ac-pass', 'secret77'); await pg.click('#ac-reg' if reg else '#ac-login')
    await pg.wait_for_function("() => !!Acct.u && Acct.u.email === %s" % json.dumps(email), timeout=8000)
    await synced(pg)
async def out(pg):
    await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true")
    await pg.click('#ac-out'); await pg.wait_for_function("() => !Acct.u", timeout=5000)
WAYS = "(() => ({ ways: NewWays.ways.map(w => w.id), drawn: NewWays.layer ? NewWays.layer.getLayers().length : 0 }))()"
BACKUP = "(async () => JSON.parse(await (await makeBackupFile()).text()).myWays.map(w => w.id))()"

async def main():
    url = serve(8923); m = Mocks(); fb = Firebase()
    async with async_playwright() as p:
        b, ctx, pg, log = await phone(p, url, m, fb)
        pg.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
        await pg.evaluate("(async () => { await NewWays.init(); NewWays.ways.push({ id: 'wA', coords: [[32.09, 34.88], [32.091, 34.881]], len: 140, at: 1 }); await NewWays.store(); })()")
        await sign(pg, 'a@example.com', True)
        ua = fb.users['a@example.com']['uid']
        check('(account A synced its own section)', 'wA' in body(fb.items(ua).get('kv~myWays')))
        await out(pg); await sign(pg, 'b@example.com', True)
        ub = fb.users['b@example.com']['uid']
        st = await pg.evaluate(WAYS)
        check('B signed in: A\'s section is not on the map', st['ways'] == [] and st['drawn'] == 0, st)
        check('B\'s backup has no A\'s section', await pg.evaluate(BACKUP) == [])
        check('A\'s section is not uploaded to B', 'wA' not in body(fb.items(ub).get('kv~myWays')))
        check('the router does not use it either (the built-in engine adds NewWays.ways)', await pg.evaluate("NewWays.addTo({ lat: new Float64Array(0), lon: new Float64Array(0), ways: [] }).ways.length") == 0)
        await pg.evaluate("(async () => { NewWays.ways.push({ id: 'wB', coords: [[32.1, 34.9], [32.101, 34.901]], len: 140, at: 2 }); await NewWays.store(); clearTimeout(Sync.t); Sync.run(); })()")
        await pg.wait_for_timeout(300); await synced(pg)
        bb, ba = body(fb.items(ub).get('kv~myWays')), body(fb.items(ua).get('kv~myWays'))
        check('B\'s own new section goes to B only; A\'s copy in the cloud unchanged', 'wB' in bb and 'wA' not in bb and 'wA' in ba and 'wB' not in ba, (bb[:80], ba[:80]))
        await out(pg); await sign(pg, 'a@example.com', False)
        st = await pg.evaluate(WAYS)
        check('back to A: A\'s section is back, B\'s is not shown', st['ways'] == ['wA'] and st['drawn'] == 1, st)
        check('A\'s backup: its own section only', await pg.evaluate(BACKUP) == ['wA'])
        # ---- R10: a backup with damaged records
        good_rt = {'id': 'rtOk', 'name': 'Хороший', 'coords': [[32.09, 34.88, 40], [32.1, 34.89, 60]], 'dist': 1500, 'created': 1, 'wpts': []}
        bad_rt = {'id': 'rtBad', 'name': 'Битый', 'coords': {'bad': True}, 'dist': 1, 'created': 1}
        bad_rt2 = {'id': 'rtBad2', 'name': 'Битый 2', 'coords': [[32.09, 'x'], [999, 34.88]], 'created': 1}
        good_rd = {'id': 'rdOk', 'name': 'Хорошая', 'start': 1.7e12, 'end': 1.7e12 + 6e5, 'type': 'bike', 'dist': 1500, 'movingMs': 6e5, 'track': [[32.09, 34.88, 40, 1.7e12], [32.1, 34.89, 60, 1.7e12 + 6e5]]}
        bad_rd = {'id': 'rdBad', 'name': 'Битая', 'start': 'вчера', 'track': 'нет'}
        d = {'app': 'velokomp', 'ver': 2, 'rides': [good_rd, bad_rd], 'routes': [good_rt, bad_rt, bad_rt2], 'ls': {}}
        res = await pg.evaluate(f"restoreBackup({json.dumps(d)})")
        have = await pg.evaluate("(async () => ({ rt: (await DB.all('routes')).map(r => r.id), rd: (await DB.all('rides')).map(r => r.id) }))()")
        check('a backup with damaged records: the good ones restored, the damaged skipped and counted', res['nr'] == 1 and res['nt'] == 1 and res['bad'] == 3 and 'rtOk' in have['rt'] and 'rtBad' not in have['rt'] and 'rtBad2' not in have['rt'] and 'rdBad' not in have['rd'], (res, have))
        await pg.evaluate("(async () => { const r = await DB.get('routes', 'rtOk'); Nav.set(r); })()"); await pg.wait_for_timeout(300)
        check('the restored route starts without errors', await pg.evaluate("Nav.route && Nav.route.name") == 'Хороший'); await pg.evaluate("Nav.stop()")
        err = await pg.evaluate(f"restoreBackup({json.dumps({'app': 'velokomp', 'ver': 2, 'routes': [bad_rt]})}).then(() => '', e => e.message)")
        check('only damaged records: «not restored», with the reason', 'повреждены' in err, err)
        err = await pg.evaluate("restoreBackup({ app: 'velokomp', ver: 9, routes: [] }).then(() => '', e => e.message)")
        check('a backup from a newer app version: refused with the reason', 'более новой версией' in err, err)
        # the account's damaged copy is not written
        got = await pg.evaluate("(async () => { const g = {}; await Sync.apply('routes~rtX', { id: 'rtX', name: 'X', coords: { bad: true } }, new Map(), g); return { g, have: !!(await DB.get('routes', 'rtX')) }; })()")
        check('a damaged route from the account: not written', not got['have'] and got['g'].get('bad') == 1, got)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
