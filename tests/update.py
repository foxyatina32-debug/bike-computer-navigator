# Auto-update: a newer build on the site reloads the app — at once when idle, after the ride/navigation otherwise.
# Run: python3 tests/update.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''))

async def main():
    url = serve(8785); m = Mocks()
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build = json.load(open(os.path.join(repo, 'version.json')))['build']
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        check('APP_BUILD matches version.json', await pg.evaluate('APP_BUILD') == build, f"{await pg.evaluate('APP_BUILD')} / {build}")
        await pg.evaluate("checkUpdate(true)"); await pg.wait_for_timeout(800)
        check('same build → no reload', await pg.evaluate("!Upd.pending && !window.__reloaded"))
        # newer build while navigating: waits, tells once
        await ctx.route('**/version.json*', lambda r: r.fulfill(json={'build': '999'}))
        await pg.evaluate("window.__mark = 1; Nav.set({ name: 'T', coords: [[32.09, 34.88], [32.1, 34.89]], noAsk: true })")
        await pg.evaluate("checkUpdate(true)"); await pg.wait_for_timeout(800)
        check('new build during navigation → no reload, toast', await pg.evaluate("window.__mark === 1 && Upd.pending && window.__lastToasts.includes('новая версия')"))
        async with pg.expect_navigation(timeout=10000):
            await pg.evaluate("Nav.progress = Nav.route.total - 20; applyUpdate()")
        await pg.wait_for_function('window.__appReady === true', timeout=20000)
        check('route ridden to the finish (no «Завершить») → app reloads to the new version', await pg.evaluate("window.__mark === undefined"))
        await pg.wait_for_timeout(500)
        await pg.wait_for_timeout(6500)
        check('still old after reload (server says 999) → no reload loop', await pg.evaluate("window.__appReady === true && !Upd.pending") and await pg.evaluate("lsGet('updTried', null)") == '999')
        check('after reload: «обновлено» message, no JS errors', not log['errors'], log['errors'])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed')
    sys.exit(0 if all(RES) else 1)
asyncio.run(main())
