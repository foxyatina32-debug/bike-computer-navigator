# Account (email + password, Firebase): two phones with one account.
# Phone A registers and uploads rides, routes, own sections and settings; phone B signs in and gets everything (settings → restart);
# a big ride goes in gzipped parts; deletion and a new route travel both ways; wrong password, password reset, sign-out;
# without the Firebase project the section says so; Hebrew and English without untranslated text.
# Firebase (Identity Toolkit, Secure Token, Firestore REST) is replaced by an in-memory fake with per-user access rules.
# Run: python3 tests/account.py
import asyncio, sys, os, json, re, random, base64
from urllib.parse import urlparse, parse_qs, unquote
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

CFG = json.dumps({'apiKey': 'test-key', 'projectId': 'velo-test'})
CORS = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'}

class Firebase:
    def __init__(s): s.users = {}; s.docs = {}; s.resets = []; s.down = False; s.n = 0
    def uid_of(s, tok): return tok[4:] if tok and tok.startswith('tok-') else None
    async def handle(s, route):
        req = route.request; u = req.url; pr = urlparse(u); q = parse_qs(pr.query)
        if req.method == 'OPTIONS': return await route.fulfill(status=204, headers=CORS)
        if s.down: return await route.abort('failed')
        def out(st, body): return route.fulfill(status=st, body=json.dumps(body), headers={**CORS, 'Content-Type': 'application/json'})
        if 'identitytoolkit.googleapis.com' in u:
            if q.get('key') != ['test-key']: return await out(400, {'error': {'message': 'API_KEY_INVALID'}})
            b = json.loads(req.post_data or '{}'); act = pr.path.split(':')[-1]
            if act == 'signUp':
                if b['email'] in s.users: return await out(400, {'error': {'message': 'EMAIL_EXISTS'}})
                if len(b.get('password', '')) < 6: return await out(400, {'error': {'message': 'WEAK_PASSWORD : Password should be at least 6 characters'}})
                s.n += 1; s.users[b['email']] = {'pw': b['password'], 'uid': f'u{s.n}'}
            elif act == 'signInWithPassword':
                us = s.users.get(b['email'])
                if not us or us['pw'] != b.get('password'): return await out(400, {'error': {'message': 'INVALID_LOGIN_CREDENTIALS'}})
            elif act == 'sendOobCode':
                s.resets.append(b['email']); return await out(200, {'email': b['email']})
            us = s.users[b['email']]
            return await out(200, {'idToken': 'tok-' + us['uid'], 'refreshToken': 'ref-' + us['uid'], 'localId': us['uid'], 'email': b['email'], 'expiresIn': '3600'})
        if 'securetoken.googleapis.com' in u:
            rt = parse_qs(req.post_data or '').get('refresh_token', [''])[0]
            if not rt.startswith('ref-'): return await out(400, {'error': {'message': 'INVALID_REFRESH_TOKEN'}})
            uid = rt[4:]; return await out(200, {'id_token': 'tok-' + uid, 'refresh_token': rt, 'user_id': uid, 'expires_in': '3600'})
        if 'firestore.googleapis.com' in u:
            m = re.match(r'/v1/projects/velo-test/databases/\(default\)/documents/users/([^/]+)/items(?:/([^/?]+))?$', pr.path)
            if not m: return await out(404, {'error': {'status': 'NOT_FOUND', 'message': 'bad path'}})
            uid, doc = unquote(m.group(1)), m.group(2) and unquote(m.group(2))
            tok = (req.headers.get('authorization') or '').replace('Bearer ', '')
            if s.uid_of(tok) != uid: return await out(403, {'error': {'status': 'PERMISSION_DENIED', 'message': 'Missing or insufficient permissions.'}})
            col = s.docs.setdefault(uid, {})
            if doc is None:
                mask = q.get('mask.fieldPaths')
                docs = [{'name': n, 'fields': {k: v for k, v in f.items() if not mask or k in mask}} for n, f in sorted(col.items())]
                size = int(q.get('pageSize', ['300'])[0]); start = int(q.get('pageToken', ['0'])[0])
                page = {'documents': docs[start:start + size]} if docs else {}
                if start + size < len(docs): page['nextPageToken'] = str(start + size)
                return await out(200, page)
            if req.method == 'PATCH':
                col[doc] = json.loads(req.post_data)['fields']; return await out(200, {'name': doc, 'fields': col[doc]})
            if doc not in col: return await out(404, {'error': {'status': 'NOT_FOUND', 'message': 'no doc'}})
            return await out(200, {'name': doc, 'fields': col[doc]})
        return await route.continue_()
    def items(s, uid):
        return {f['k']['stringValue']: f for f in s.docs.get(uid, {}).values() if 'k' in f}

FB_HOSTS = re.compile(r'https://(identitytoolkit|securetoken|firestore)\.googleapis\.com/.*')
LEFTOVER = """(() => { const out = new Set(), g = document.querySelector('details.grp[data-g=acct]');
  const walk = n => { if (n.nodeType === 3) { if (/[А-Яа-яЁё]{3,}/.test(n.nodeValue)) out.add(n.nodeValue.trim().slice(0, 60)); return; }
    if (n.nodeType !== 1 || n.hidden || getComputedStyle(n).display === 'none') return;
    for (const a of ['placeholder']) if (n.getAttribute && /[А-Яа-яЁё]{3,}/.test(n.getAttribute(a) || '')) out.add(a + ': ' + n.getAttribute(a));
    for (const c of n.childNodes) walk(c); };
  walk(g); return [...out]; })()"""

async def phone(p, url, m, fb, lang='ru', cfg=True):
    st = [('velo:fbcfg', CFG)] if cfg else []
    b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, storage=st)
    await ctx.route(FB_HOSTS, fb.handle)
    await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true")
    return b, ctx, pg, log

async def synced(pg, ms=15000):
    await pg.wait_for_function("() => !Sync.busy && Sync.meta().at > 0", timeout=ms)
    await pg.wait_for_timeout(200)

TRK = lambda n, seed: (lambda r: [[32.09 + i * 1e-5 + r.random() * 1e-5, 34.88 + r.random() * 1e-5, 40 + r.random() * 5, 1.7e12 + i * 1000] for i in range(n)])(random.Random(seed))

async def main():
    url = serve(8831); m = Mocks(); fb = Firebase()
    async with async_playwright() as p:
        # v128: accounts are switched off for now — the section is gone, nothing syncs, saving is not hooked
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=[('velo:fbcfg', CFG), ('velo:acct', json.dumps({'email': 'a@b', 'uid': 'u1', 'idToken': 'tok-u1', 'refreshToken': 'ref-u1', 'exp': 0}))])
        if not await pg.evaluate("ACCOUNTS_ON"):
            await ctx.route(FB_HOSTS, fb.handle); await pg.wait_for_timeout(4000)
            await pg.evaluate("DB.put('routes', { id: 'r1', name: 'X', coords: [[32.09,34.88,1],[32.1,34.89,2]], dist: 1, created: 1, source: 't', wpts: [] })")
            await pg.wait_for_timeout(1500)
            check('accounts off: no «Аккаунт» section in Settings', not await pg.evaluate("!!document.querySelector('details.grp[data-g=acct]')"))
            check('accounts off: nothing is sent anywhere, even with an old sign-in saved', not fb.docs and await pg.evaluate("!lsGet('sync', null)"))
            check('no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
            print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
        await b.close()
        # ---- not configured: the section says so, no requests to Firebase
        b, ctx, pg, log = await phone(p, url, m, fb, cfg=False)
        check('no Firebase project: the section says accounts are not set up', await pg.is_visible('#ac-off') and not await pg.is_visible('#ac-in'))
        await b.close()

        # ---- phone A: data made before signing in, then registration
        b, ctx, A, logA = await phone(p, url, m, fb)
        big = TRK(60000, 1)
        await A.evaluate(f"""(async () => {{
          await DB.put('routes', {{ id: 'rtA', name: 'Бен-Шемен кольцо', coords: [[32.09,34.88,40],[32.1,34.89,60]], dist: 1500, asc: 20, created: 1, src: 'test', wpts: [] }});
          await DB.put('rides', {{ id: 'rdA', name: 'Поездка А', start: 1.7e12, end: 1.7e12 + 3600e3, type: 'bike', dist: 1500, movingMs: 6e5, track: [[32.09,34.88,40,1.7e12],[32.1,34.89,60,1.7e12+6e5]] }});
          await DB.put('rides', {{ id: 'rdBig', name: 'Длинная', start: 1.7e12, end: 1.8e12, type: 'bike', dist: 90000, movingMs: 6e7, track: {json.dumps(big)} }});
          await DB.put('kv', {{ id: 'myWays', ways: [{{ id: 'w1', coords: [[32.09,34.88],[32.091,34.881]], len: 140, at: 1 }}] }});
          S.voice = false; saveS(); lsSet('gkey', 'AIza-test');
        }})()""")
        check('signed out: the sign-in form is shown', await A.is_visible('#ac-in') and await A.is_visible('#ac-email'))
        await A.fill('#ac-email', 'rider@example.com'); await A.fill('#ac-pass', '123')
        await A.click('#ac-reg'); await A.wait_for_timeout(600)
        check('short password: clear message', 'не меньше 6 символов' in await A.evaluate('window.__lastToasts'))
        await A.fill('#ac-pass', 'secret77'); await A.click('#ac-reg')
        await synced(A)
        uid = fb.users['rider@example.com']['uid']; it = fb.items(uid)
        check('registered: the account is shown on the phone', 'rider@example.com' in await A.inner_text('#ac-who') and await A.is_visible('#ac-user'), await A.inner_text('#ac-st'))
        check('rides, routes, own sections and settings uploaded', all(k in it for k in ['rides~rdA', 'rides~rdBig', 'routes~rtA', 'kv~myWays', 'ls~all']), sorted(it))
        check('the password is not kept on the phone', 'secret77' not in await A.evaluate("JSON.stringify(localStorage)"))
        parts = [n for n in fb.docs[uid] if n.endswith('.1')]
        check('a big ride is gzipped and split into parts (1 MB per document)', it['rides~rdBig']['z']['stringValue'] == 'gzip' and int(it['rides~rdBig']['n']['integerValue']) >= 2 and parts,
              (it['rides~rdBig']['n'], len(base64.b64decode(it['rides~rdBig']['b']['bytesValue']))))
        check('status: synced', 'Синхронизировано' in await A.inner_text('#ac-st'), await A.inner_text('#ac-st'))
        bA = b   # phone A stays on

        # ---- phone B: wrong password, then the right one → everything arrives, settings restart the app
        b, ctx, B, logB = await phone(p, url, m, fb)
        await B.fill('#ac-email', 'rider@example.com'); await B.fill('#ac-pass', 'wrong-pass'); await B.click('#ac-login'); await B.wait_for_timeout(600)
        check('wrong password: «Неверная почта или пароль»', 'Неверная почта или пароль' in await B.evaluate('window.__lastToasts') and await B.is_visible('#ac-in'))
        await B.fill('#ac-pass', 'secret77'); await B.click('#ac-login')
        await B.wait_for_event('load', timeout=20000)   # settings from the account → restart
        await B.wait_for_function('window.__appReady === true', timeout=20000); await B.wait_for_timeout(500)
        got = await B.evaluate("""(async () => { const rd = await DB.all('rides'), rt = await DB.all('routes'), w = await DB.get('kv', 'myWays');
          const big = rd.find(r => r.id === 'rdBig');
          return { rides: rd.map(r => r.id).sort(), routes: rt.map(r => r.id), ways: w ? w.ways.length : 0, big: big ? big.track.length : 0, last: big ? big.track[59999] : null,
                   voice: S.voice, gkey: lsGet('gkey', ''), acct: !!(Acct.u && Acct.u.email) }; })()""")
        check('phone B: rides and routes from the account', got['rides'] == ['rdA', 'rdBig'] and got['routes'] == ['rtA'], got)
        check('phone B: the big ride is whole (60 000 points, same last point)', got['big'] == 60000 and got['last'] == big[59999], got['big'])
        check('phone B: own sections of way', got['ways'] == 1)
        check('phone B: settings and map keys moved (after the restart)', got['voice'] is False and got['gkey'] == 'AIza-test', got)
        check('phone B: still signed in after the restart', got['acct'])

        # ---- deletion on B and a new route on A travel to the other phone
        await B.evaluate("DB.del('routes', 'rtA')"); await B.evaluate("Sync.run()"); await B.wait_for_function("!Sync.busy")
        check('deleted on B → marked deleted in the account', fb.items(uid)['routes~rtA']['d']['booleanValue'] is True)
        await A.evaluate("Sync.run()"); await A.wait_for_timeout(300); await A.wait_for_function("!Sync.busy")
        check('phone A: the route deleted on B is gone', await A.evaluate("DB.get('routes', 'rtA').then(r => !r)"))
        await A.evaluate("DB.put('routes', { id: 'rtNew', name: 'Новый', coords: [[32.09,34.88,40],[32.1,34.89,60]], dist: 1500, created: Date.now(), src: 'test', wpts: [] })")
        await A.wait_for_function("!!Sync.meta().items['routes~rtNew'] && !Sync.meta().items['routes~rtNew'].dirty", timeout=15000)
        await B.evaluate("Sync.run()"); await B.wait_for_timeout(300); await B.wait_for_function("!Sync.busy")
        check('a route saved on A appears on B by itself (no button)', await B.evaluate("DB.get('routes', 'rtNew').then(r => !!r)"))
        loads = []; A.on('load', lambda: loads.append('A')); B.on('load', lambda: loads.append('B'))
        for _ in range(2):
            for ph in (A, B): await ph.evaluate("Sync.run()"); await ph.wait_for_timeout(300); await ph.wait_for_function("!Sync.busy")
        await A.wait_for_timeout(2500)
        check('two phones in sync: no endless restarts for settings', not loads, loads)
        await bA.close()

        # ---- no internet: a clear status, nothing lost; back online → sent
        fb.down = True
        await B.evaluate("DB.put('routes', { id: 'rtOff', name: 'Без сети', coords: [[32.09,34.88,40],[32.1,34.89,60]], dist: 1500, created: Date.now(), src: 'test', wpts: [] })")
        await B.evaluate("Sync.run()"); await B.wait_for_timeout(300); await B.wait_for_function("!Sync.busy")
        st = await B.inner_text('#ac-st')
        check('no connection: the status says so', 'Нет связи' in st, st)
        fb.down = False; await B.evaluate("Sync.run()"); await B.wait_for_timeout(300); await B.wait_for_function("!Sync.busy")
        check('back online: the change made offline is sent', 'routes~rtOff' in fb.items(uid))

        # ---- someone else's data is not reachable
        fb.users['other@example.com'] = {'pw': 'x' * 8, 'uid': 'u99'}
        r = await B.evaluate("fetch('https://firestore.googleapis.com/v1/projects/velo-test/databases/(default)/documents/users/u99/items', { headers: { Authorization: 'Bearer ' + Acct.u.idToken } }).then(r => r.status)")
        check("another account's data is refused (403)", r == 403)

        # ---- expired sign-in: refreshed by itself
        await B.evaluate("(() => { const u = Acct.u; u.exp = 0; u.idToken = 'tok-stale'; lsSet('acct', u); })()")
        await B.evaluate("Sync.run()"); await B.wait_for_timeout(300); await B.wait_for_function("!Sync.busy")
        check('an expired sign-in is renewed without asking for the password', await B.evaluate("Acct.u.idToken") == 'tok-' + uid and not await B.evaluate("Sync.err"))

        # ---- password reset, sign-out
        B.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
        await B.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true")
        await B.click('#ac-out'); await B.wait_for_timeout(300)
        check('sign-out: the form is back, rides stay on the phone', await B.is_visible('#ac-in') and await B.evaluate("DB.all('rides').then(r => r.length)") == 2 and not await B.evaluate("lsGet('acct', null)"))
        await B.fill('#ac-email', 'rider@example.com'); await B.click('#ac-forgot'); await B.wait_for_timeout(500)
        check('«Забыли пароль?» sends the reset email', fb.resets == ['rider@example.com'] and 'отправлено' in await B.evaluate('window.__lastToasts'))
        check('no JS errors on the phones', not logB['errors'] and not logA['errors'], (logB['errors'] + logA['errors'])[:3])
        await b.close()

        # ---- registering an existing email
        b, ctx, C, logC = await phone(p, url, m, fb)
        await C.fill('#ac-email', 'rider@example.com'); await C.fill('#ac-pass', 'another1'); await C.click('#ac-reg'); await C.wait_for_timeout(600)
        check('the same email again: «уже зарегистрирована»', 'уже зарегистрирована' in await C.evaluate('window.__lastToasts'))
        await b.close()

        # ---- Hebrew and English
        for lang in ('he', 'en'):
            b, ctx, pg, log = await phone(p, url, m, fb, lang=lang)
            lo = await pg.evaluate(LEFTOVER)
            await pg.fill('#ac-email', 'rider@example.com'); await pg.fill('#ac-pass', 'secret77'); await pg.click('#ac-login')
            await pg.wait_for_event('load', timeout=20000); await pg.wait_for_function('window.__appReady === true', timeout=20000)
            await pg.evaluate("showTab('profile'); document.querySelector('details.grp[data-g=acct]').open = true"); await pg.wait_for_timeout(600)
            lo += await pg.evaluate(LEFTOVER)
            check(f'{lang}: the account section is translated (signed out and signed in)', not lo, lo[:5])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
