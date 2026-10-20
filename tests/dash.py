# Step 1: Basic / Pro mode. Step 2: customizable telemetry cells (long press → metric).
# Run: python3 tests/dash.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
VIS = "(sel => { const e = document.querySelector(sel); return !!e && e.offsetParent !== null; })"
async def longpress(pg, sel, ms=750):
    b = await pg.locator(sel).bounding_box(); x, y = b['x'] + b['width'] / 2, b['y'] + b['height'] / 2
    await pg.mouse.move(x, y); await pg.mouse.down(); await pg.wait_for_timeout(ms); await pg.mouse.up()

async def main():
    url = serve(8784)
    async with async_playwright() as p:
        # ---- fresh user: Basic by default ----
        m = Mocks(); b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
        st = await pg.evaluate(f"({{ pro: isPro(), keys: {VIS}('#k-tf'), google: {VIS}('#g-key'), mb: {VIS}('#mb-list'), sw: {VIS}('#s-pro') }})")
        check('fresh user: Basic, keys / Google / MBTiles hidden, Pro switch visible', not st['pro'] and not st['keys'] and not st['google'] and not st['mb'] and st['sw'], st)
        await pg.evaluate("showTab('layers')"); await pg.wait_for_timeout(300)
        bases = await pg.evaluate("[...document.querySelectorAll('#ly-base input')].map(i => i.value)")
        check('Basic: only free base maps', sorted(bases) == sorted(['ihm_mtb_he', 'ihm_mtb_en', 'ihm_he', 'osm', 'cyclosm', 'topo', 'sat']), bases)
        await pg.evaluate("showTab('routes'); routeSeg('plan')"); g1 = await pg.evaluate(f"{VIS}('#pl-engine [data-e=google]')")
        await pg.evaluate("showTab('routes'); routeSeg('mine')"); px1 = await pg.evaluate(f"{VIS}('#url-proxy')")
        check('Basic: no Google engine, no proxy option', not g1 and not px1, (g1, px1))
        # switch on Pro
        await pg.evaluate("showTab('profile')"); await pg.click('#s-pro'); await pg.wait_for_timeout(300)
        st2 = await pg.evaluate(f"({{ pro: isPro(), keys: {VIS}('#k-tf'), google: {VIS}('#g-key'), mb: {VIS}('#mb-list'), saved: lsGet('pro') }})")
        await pg.evaluate("showTab('layers')"); n_all = await pg.evaluate("document.querySelectorAll('#ly-base input').length")
        check('Pro on: keys, Google, MBTiles and all layers; remembered', st2['pro'] and st2['keys'] and st2['google'] and st2['mb'] and st2['saved'] is True and n_all > 6, f"{st2} · {n_all} layers")
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(500)
        check('Pro survives a restart', await pg.evaluate("isPro()"))
        # switch Pro off while on a Pro-only map → back to a free map
        await pg.evaluate("setBase('esri_topo'); lsSet('base', 'esri_topo'); setPro(false, true)")
        check('Pro off on a Pro map → free map', await pg.evaluate("baseKey") == 'ihm_mtb_he')
        await b.close()
        # ---- existing user with a Google key: stays Pro (nothing disappears) ----
        b, ctx, pg, log2 = await open_app(p, url + '?lang=ru', Mocks(), storage=[['velo:gkey', '"AIzaX"']])
        check('existing user with keys: Pro kept automatically', await pg.evaluate("isPro()"))
        await b.close()

        # ---- Step 2: cells ----
        m = Mocks(); b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate("showTab('rec'); setCompact(false)"); await pg.wait_for_timeout(300)
        ks = await pg.evaluate("[...document.querySelectorAll('.slot')].map(s => s.dataset.k)")
        check('default cells as before', ks == ['time', 'dist', 'speed', 'avg', 'max', 'alt', 'asc', 'desc', 'rem', 'clock', 'tleft', 'eta'], ks)
        await longpress(pg, '.slot[data-slot="1"]'); await pg.wait_for_timeout(200)
        op = await pg.evaluate("!document.getElementById('ask-metric').hidden && document.querySelectorAll('#mt-list [data-k]').length")
        check('long press (600 ms) opens the metric choice with the whole pool', op == 14, op)
        await pg.screenshot(path=os.path.join(SHOT, 'dash-choose.png'))
        await pg.click('#mt-list [data-k=grade]'); await pg.wait_for_timeout(200)
        await pg.mouse.move(10, 10); await longpress(pg, '.slot[data-slot="0"]', 250); await pg.wait_for_timeout(300)
        short_ok = await pg.evaluate("document.getElementById('ask-metric').hidden")
        check('short tap does not open it', short_ok)
        # contextmenu path too
        await pg.evaluate("document.querySelector('.slot[data-slot=\"5\"]').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true}))")
        await pg.click('#mt-list [data-k=acc]'); await pg.wait_for_timeout(200)
        # ride uphill: gradient ≈ +5 %, accuracy ±5
        await pg.click('#c-play'); lat = 32.09
        for i in range(25):
            lat += 0.00009  # ≈10 m
            await ctx.set_geolocation({'latitude': lat, 'longitude': 34.88, 'accuracy': 5}); await pg.evaluate(f"(() => {{ const f = GPS.fix; }})()")
            await pg.wait_for_timeout(1000)
        # the harness geolocation has no altitude: feed the gradient directly from a climbing track
        await pg.evaluate("Grade.pts = []; Grade.d = 0; for (let i = 0; i < 12; i++) gradeFeed({ lat: 32.1 + i * 0.00009, lon: 34.88, alt: 100 + i * 0.5, acc: 5, t: Date.now() }); renderMetrics()")
        g = await pg.evaluate("document.querySelector('.slot[data-k=grade] [data-v]').textContent + document.querySelector('.slot[data-k=grade] [data-u]').textContent")
        a = await pg.evaluate("document.querySelector('.slot[data-k=acc]').innerText")
        check('Уклон shows the climb (+5 %)', g.startswith('+5') and g.endswith('%'), g)
        check('Точность GPS shows ±5 м', '±5' in a and 'м' in a, a)
        await pg.screenshot(path=os.path.join(SHOT, 'dash-custom.png'))
        await pg.click('#c-stop'); await pg.click('#st-save')
        await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(500)
        ks2 = await pg.evaluate("[...document.querySelectorAll('.slot')].map(s => s.dataset.k)")
        check('layout kept after restart', ks2[1] == 'grade' and ks2[5] == 'acc', ks2)
        # walking: speed cell shows pace
        await pg.evaluate("S.act = 'walk'; renderMetrics()")
        u = await pg.evaluate("document.querySelector('.slot[data-k=speed] [data-u]').textContent")
        check('walking: pace min/km in the speed cell', u == '/км', u)
        await pg.evaluate("S.act = 'bike'; openMetric(0)"); await pg.click('#mt-reset'); await pg.wait_for_timeout(200)
        check('reset brings the default layout back', await pg.evaluate("[...document.querySelectorAll('.slot')].map(s => s.dataset.k).join()") == 'time,dist,speed,avg,max,alt,asc,desc,rem,clock,tleft,eta')
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # Hebrew: labels translated
        b, ctx, pg, log = await open_app(p, url + '?lang=he', Mocks(), viewport=(375, 667))
        await pg.evaluate("openMetric(2)"); await pg.wait_for_timeout(200)
        txt = await pg.evaluate("document.getElementById('ask-metric').innerText")
        import re
        check('Hebrew: chooser translated', not re.search('[А-Яа-яЁё]{3,}', txt), txt[:80])
        check('no JS errors (he)', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
