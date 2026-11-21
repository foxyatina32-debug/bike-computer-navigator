# v151 (audit R16). Big items: their parts carry the version in the id, the main document names it, the previous version's
# parts are deleted (they used to stay for ever and two versions could mix); another phone reads the new version whole; the
# old format (parts without a version) is still read. A hung server: the request gives up (time limit), the status says
# so, «Синхронизация…» does not stay for ever and the next sync works. Automatic syncs with nothing changed do not read
# the whole list again within 15 min; a tap on «Синхронизировать» and a local change always sync.
# Firebase is the in-memory fake of tests/account.py. Run: python3 tests/syncparts.py
import asyncio, sys, os, json, base64, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks
from account import phone, synced, TRK
from acctrace import Gated, sign_in
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
RIDE = "(n => ({ id: 'rdBig', name: 'Длинная', start: 1.7e12, end: 1.8e12, type: 'bike', dist: 90000, movingMs: 6e7, track: (() => { const t = []; let s = %d; const r = () => (s = (s * 16807) %% 2147483647) / 2147483647; for (let i = 0; i < n; i++) t.push([32.09 + i * 1e-5 + r() * 1e-5, 34.88 + r() * 1e-5, 40 + r() * 5, 1.7e12 + i * 1000]); return t; })() }))"

def parts(fb, uid):
    return sorted(n for n in fb.docs.get(uid, {}) if '.' in n)

async def main():
    url = serve(8929); m = Mocks(); fb = Gated()
    async with async_playwright() as p:
        b, ctx, A, log = await phone(p, url, m, fb)
        await sign_in(A, 'rider@example.com', True); await synced(A)
        uid = fb.users['rider@example.com']['uid']
        await A.evaluate("(async () => { await DB.put('rides', (%s)(60000)); clearTimeout(Sync.t); Sync.run(); })()" % (RIDE % 7)); await A.wait_for_timeout(300); await synced(A)
        main_ = next(f for f in fb.docs[uid].values() if f.get('k', {}).get('stringValue') == 'rides~rdBig')
        p1 = parts(fb, uid); pv1 = main_.get('pv', {}).get('stringValue')
        check('a big ride: parts with the version in their ids, the main document names it', pv1 and p1 and all(('.' + pv1 + '.') in x for x in p1) and int(main_['n']['integerValue']) == len(p1) + 1, (pv1, p1[:3]))
        await A.wait_for_timeout(5)
        await A.evaluate("(async () => { await DB.put('rides', (%s)(55000)); clearTimeout(Sync.t); Sync.run(); })()" % (RIDE % 11)); await A.wait_for_timeout(300); await synced(A)
        main_ = next(f for f in fb.docs[uid].values() if f.get('k', {}).get('stringValue') == 'rides~rdBig')
        p2 = parts(fb, uid); pv2 = main_.get('pv', {}).get('stringValue')
        check('changed again: new parts under the new version, the old version\'s parts deleted', pv2 and pv2 != pv1 and p2 and all(('.' + pv2 + '.') in x for x in p2) and not any(x in p2 for x in p1), (pv2, len(p1), len(p2)))
        # phone B, same account: reads the new version whole
        b2, ctx2, B, logB = await phone(p, url, m, fb)
        B.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
        await sign_in(B, 'rider@example.com'); await synced(B)
        n = await B.evaluate("(async () => { const r = await DB.get('rides', 'rdBig'); return r ? r.track.length : 0; })()")
        check('another phone reads the new version whole', n == 55000, n)
        # the old format: parts without a version
        docs = fb.docs[uid]; mk = next(k for k, f in docs.items() if f.get('k', {}).get('stringValue') == 'rides~rdBig')
        f = docs[mk]; allb = base64.b64decode(f['b']['bytesValue']) + b''.join(base64.b64decode(docs[x]['c']['bytesValue']) for x in sorted(parts(fb, uid), key=lambda x: int(x.rsplit('.', 1)[1])))
        for x in parts(fb, uid): del docs[x]
        half = len(allb) // 2
        docs[mk] = {**{k: v for k, v in f.items() if k != 'pv'}, 'u': {'integerValue': str(int(f['u']['integerValue']) + 1000)}, 'n': {'integerValue': '2'}, 'b': {'bytesValue': base64.b64encode(allb[:half]).decode()}}
        docs[mk + '.1'] = {'c': {'bytesValue': base64.b64encode(allb[half:]).decode()}}
        await B.evaluate("(async () => { await DB.raw.del('rides', 'rdBig'); const m = Sync.meta(); delete m.items['rides~rdBig']; lsSet('sync', m); clearTimeout(Sync.t); await Sync.run(); })()"); await synced(B)
        n = await B.evaluate("(async () => { const r = await DB.get('rides', 'rdBig'); return r ? r.track.length : 0; })()")
        check('the old format (parts without a version) is still read', n == 55000, n)
        await b2.close()
        # ---- a hung server: the time limit
        fb.hold('firestore.googleapis.com')
        await A.evaluate("(() => { const st = window.setTimeout; window.__st = st; window.setTimeout = (f, ms, ...a) => st(f, ms >= 20000 ? 400 : ms, ...a); clearTimeout(Sync.t); Sync.run(); })()")
        await A.wait_for_timeout(2500)
        st = await A.evaluate("({ busy: Sync.busy, err: Sync.err, txt: document.getElementById('ac-st').textContent })")
        check('a hung server: the request gives up, «Синхронизация…» does not stay, the status says so', not st['busy'] and 'не ответил' in st['err'] and 'не ответил' in st['txt'], st)
        await A.evaluate("window.setTimeout = window.__st; 0")
        fb.release('firestore.googleapis.com')
        await A.evaluate("clearTimeout(Sync.t); Sync.run()"); await synced(A)
        check('…the next sync works', await A.evaluate("!Sync.err"))
        # ---- automatic syncs with nothing changed
        lists = []
        ctx.on('request', lambda r: lists.append(r.url) if 'firestore' in r.url and 'pageSize' in r.url else None)
        await A.evaluate("Sync.run(true)"); await A.wait_for_timeout(300); await A.evaluate("Sync.run(true)"); await A.wait_for_timeout(300)
        n_auto = len(lists)
        await A.evaluate("Sync.run()"); await A.wait_for_timeout(300); await synced(A)
        n_tap = len(lists) - n_auto
        await A.evaluate("(async () => { await DB.put('routes', { id: 'rt9', name: 'Новый', coords: [[32.09,34.88,40],[32.1,34.89,60]], dist: 1500, asc: 20, created: 9, src: 'test', wpts: [] }); clearTimeout(Sync.t); Sync.run(true); })()")
        await A.wait_for_timeout(300); await synced(A)
        check('automatic syncs with nothing changed: no new full listing; a tap and a local change do sync', n_auto == 0 and n_tap >= 1 and 'routes~rt9' in fb.items(uid), (n_auto, n_tap))
        check('no JS errors', not log['errors'] and not logB['errors'], (log['errors'][:2], logB['errors'][:2]))
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
