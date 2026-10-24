# Offline download options (map, «вместе со слоем MTB-трасс», depth) are remembered after a restart.
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
ST = "({ov: document.getElementById('dl-overlay').checked, z: document.querySelector('#dl-depth .on').dataset.z, layer: document.getElementById('dl-layer').value, n: document.getElementById('dl-layer').options.length})"
async def main():
    url = serve(8788)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1500)
        await pg.click('.tabs [data-tab="profile"]'); await pg.wait_for_timeout(400)
        s0 = await pg.evaluate(ST)
        check('defaults: MTB layer on, +3, a map chosen', s0['ov'] and s0['z'] == '3' and s0['layer'], s0)
        layers = await pg.evaluate("[...document.getElementById('dl-layer').options].map(o => o.value)")
        other = next((v for v in layers if v != s0['layer']), s0['layer'])
        await pg.evaluate("document.getElementById('dl-overlay').click(); document.querySelector('#dl-depth [data-z=\"5\"]').click()")
        await pg.select_option('#dl-layer', other); await pg.wait_for_timeout(300)
        await pg.reload(); await pg.wait_for_timeout(2000)
        await pg.click('.tabs [data-tab="profile"]'); await pg.wait_for_timeout(400)
        s1 = await pg.evaluate(ST)
        check('after a restart: MTB layer off, +5 and the chosen map are kept', not s1['ov'] and s1['z'] == '5' and s1['layer'] == other, {'before': s0, 'after': s1, 'chose': other})
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
