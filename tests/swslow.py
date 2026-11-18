# v129: the app opens on a weak connection. The service worker used to wait for the network without a time limit — on a
# connection that hangs the screen stayed white. Now a page waits ≤ 4 s, then the copy on the phone opens; with no copy it
# still waits for the network (never an empty answer). Requests of the service worker are intercepted to make the server slow.
# Run: python3 tests/swslow.py
import asyncio, sys, os, time
os.environ.setdefault('PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS', '1')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
SLOW = {'on': False, 'delay': 12}

async def main():
    url = serve(9021); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, sw=True)
        async def slow(route):
            if SLOW['on'] and route.request.resource_type in ('document', 'other', 'fetch') and route.request.url.split('?')[0].endswith('/app/'):
                await asyncio.sleep(SLOW['delay'])
            await route.continue_()
        await ctx.route('**/app/**', slow)
        await pg.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.ready.then(() => true)", timeout=15000)
        await pg.reload(); await pg.wait_for_function('window.__appReady === true', timeout=20000); await pg.wait_for_timeout(1500)
        ctrl = await pg.evaluate("!!navigator.serviceWorker.controller")
        check('the service worker controls the page (the copy is saved on the phone)', ctrl)
        cached = await pg.evaluate("caches.open('velo-me-shell-v1').then(c => c.keys()).then(k => k.map(r => new URL(r.url).pathname))")
        check('the page itself is in the copy on the phone', any(x.endswith('/app/') for x in cached), cached[:6])
        # the connection hangs 12 s: the app must still open in a few seconds
        SLOW['on'] = True
        t0 = time.time()
        await pg.goto(url + '?lang=ru', wait_until='commit', timeout=30000)
        try: await pg.wait_for_function("!!document.querySelector('.tabs')", timeout=20000); t = round(time.time() - t0, 1)
        except Exception: t = None
        check('a connection that hangs: the app opens from the copy in ≤ 7 s (was a white screen until the network answered)', t is not None and t <= 7, t)
        SLOW['on'] = False
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
