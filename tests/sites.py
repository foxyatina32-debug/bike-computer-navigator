# «Мои сайты с маршрутами»: a long address must not push the × button off-screen; v91 removes the ganorbikes.co.il page once.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''))
GANOR = 'https://www.ganorbikes.co.il/courses/' + '%D7%9E%D7%9B%D7%A4%D7%A8-%D7%A1%D7%99%D7%A8%D7%A7%D7%99%D7%9F-%D7%9C%D7%9E%D7%A7%D7%95%D7%A8%D7%95%D7%AA-%D7%94%D7%99%D7%A8%D7%A7%D7%95%D7%9F%2C-%D7%AA%D7%9C-%D7%90%D7%A4%D7%A7-%D7%95%D7%91%D7%A8%D7%99%D7%9B%D7%AA-%D7%94%D7%A0%D7%95%D7%A4%D7%A8%D7%99%D7%9D'
LONG = 'https://example.org/' + 'a%D7%9E' * 60
async def main():
    url = serve(8811); m = Mocks()
    sites = [{'name': 'Rochvim Kavuh', 'url': 'https://rochvim-kavuh.com/'}, {'name': 'ganorbikes.co.il', 'url': GANOR}, {'name': 'example.org', 'url': LONG}]
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=[['velo:sites', json.dumps(sites)], ['velo:sitesV2', 'true']])
        l = await pg.evaluate("JSON.parse(localStorage.getItem('velo:sites'))")
        check('ganorbikes removed, other sites kept', not any('ganorbikes' in x['url'] for x in l) and len(l) == 2, [x['name'] for x in l])
        await pg.click('.tabs button[data-tab=routes]'); await pg.wait_for_timeout(400)
        await pg.evaluate("document.getElementById('st-list').scrollIntoView()"); await pg.wait_for_timeout(300)
        r = await pg.evaluate("""(() => { const bs = [...document.querySelectorAll('#st-list [data-sdel]')]; return bs.map(b => { const q = b.getBoundingClientRect(); return [q.left, q.right]; }); })()""")
        check('every × button is inside the screen', len(r) == 2 and all(a >= 0 and z <= 390 for a, z in r), r)
        btn = pg.locator('#st-list [data-sdel="1"]'); await btn.click(); await btn.click(); await pg.wait_for_timeout(300)
        l = await pg.evaluate("JSON.parse(localStorage.getItem('velo:sites'))")
        check('long-address site can be deleted with ×', len(l) == 1 and l[0]['name'] == 'Rochvim Kavuh')
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(500)
        l = await pg.evaluate("JSON.parse(localStorage.getItem('velo:sites'))")
        check('cleanup runs only once (list unchanged after reload)', len(l) == 1)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
