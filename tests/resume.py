# Launch: the «С возвращением» dialog only after closing during navigation, until «Продолжить» or «без маршрута»; clean start → greeting.
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []; SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ROUTE = "[[32.09,34.88,10],[32.095,34.88,20],[32.1,34.885,30]]"
async def state(pg): return await pg.evaluate("({ask: !document.getElementById('ask-resume').hidden, hello: !document.getElementById('hello').hidden, txt: document.getElementById('hello').textContent, an: !!lsGet('activeNav', null)})")
async def main():
    url = serve(8775)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks())
        st = await state(pg); check('clean start: greeting, no dialog', st['hello'] and not st['ask'] and ('Добр' in st['txt']), st)
        await pg.screenshot(path=os.path.join(SHOT, 'hello.png'))
        await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {ROUTE}, noAsk: true}})"); await pg.wait_for_timeout(400)
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(1200)
        st = await state(pg); check('closed during navigation → dialog, no greeting', st['ask'] and not st['hello'], st)
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(1200)
        st = await state(pg); check('not answered → dialog again next time', st['ask'], st)
        await pg.click('#rs-x'); await pg.wait_for_timeout(300)
        check('«Продолжить без маршрута» forgets the route', not (await state(pg))['an'])
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(1200)
        st = await state(pg); check('after «без маршрута»: clean start with greeting', not st['ask'] and st['hello'], st)
        await pg.evaluate(f"Nav.set({{name: 'Тест', coords: {ROUTE}, noAsk: true}})"); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(1200)
        await pg.click('#rs-cont'); await pg.wait_for_timeout(300)
        check('«Продолжить» → navigation on', await pg.evaluate("!!Nav.route"))
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(1200)
        st = await state(pg); check('closed again during navigation → reminded again', st['ask'], st)
        await pg.click('#rs-new'); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(1200)
        st = await state(pg); check('«Новый маршрут» also forgets it', not st['ask'] and not st['an'], st)
        check('no JS errors', not log['errors'], log['errors'][:3]); await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks())
            await pg.wait_for_timeout(500); st = await state(pg); check(f'[{lang}] greeting translated', st['hello'] and not any('Ѐ' <= c <= 'ӿ' for c in st['txt']), st['txt'])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
