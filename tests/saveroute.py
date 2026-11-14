# v110: a ridden track is kept as a route in «Маршруты → Мои».
# After «Завершить и сохранить» the app offers «⭐ В мои маршруты» / «📄 Файл GPX» / «Не надо» (not for a short ride and not
# when the ride followed a route that is already saved); the ride in History has a «⭐ В мои маршруты» button and the same
# item in its ⋯ menu; no duplicates; the route opens and navigates like any other; Hebrew and English.
# Run: python3 tests/saveroute.py
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks
from ride import open_app, Rider, dense, ll, GPX
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

# A ride with no route: 400 m north, 300 m east, 300 m north (≈1 km, two bends).
PATH = [(0, 0), (0, 400), (300, 400), (300, 700)]
DIALOGS = []
def on_dialog(d):
    DIALOGS.append(d.message); asyncio.ensure_future(d.accept('Круг у дома'))

async def ride_and_stop(pg, rd, path, v=6):
    await pg.click('#m-play' if await pg.is_visible('#m-play') else '#c-play'); await pg.clock.run_for(500)
    await rd.go(path, v=v); await rd.stand(3)
    if not await pg.is_visible('#c-stop'): await pg.click('#hud-max'); await pg.clock.run_for(400)
    await pg.click('#c-stop'); await pg.clock.run_for(200)
    await pg.click('#st-save'); await pg.clock.run_for(1200)

async def main():
    url = serve(8851); m = Mocks()
    async with async_playwright() as p:
        # ---------- 1. Ride without a route → offer → save to «Мои» ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        pg.on('dialog', on_dialog)
        rd = Rider(pg); await rd.fix(0, -5, 0)
        await ride_and_stop(pg, rd, [(0, -5)] + PATH)
        st = await pg.evaluate("({open: !document.getElementById('ask-asroute').hidden, info: document.getElementById('ar-info').textContent, yes: document.getElementById('ar-yes').textContent, rides: 0})")
        check('after «Завершить и сохранить»: «Сохранить как маршрут?» is offered', st['open'] and 'км' in st['info'] and 'мои маршруты' in st['yes'].lower(), st)
        n_rides = len(await pg.evaluate("DB.all('rides')"))
        check('the ride itself is in History already (offer comes after saving)', n_rides == 1, n_rides)
        await pg.click('#ar-yes'); await pg.clock.run_for(800)
        routes = await pg.evaluate("DB.all('routes')")
        check('name asked once, with a sensible default', len(DIALOGS) == 1 and DIALOGS[0], DIALOGS)
        ok = len(routes) == 1 and routes[0]['name'] == 'Круг у дома' and routes[0]['source'] == 'Моя поездка'
        check('route saved to «Маршруты → Мои» with the given name', ok, [(r['name'], r['source']) for r in routes])
        r0 = routes[0] if routes else {'dist': 0, 'coords': []}
        check('route length ≈ ridden (≈1 km)', 900 < r0['dist'] < 1150, f"{r0['dist']:.0f} m")
        check('track thinned out (not a point every second), bends kept', 4 <= len(r0['coords']) < 120, len(r0['coords']))
        ride = (await pg.evaluate("DB.all('rides')"))[0]
        check('ride remembers its route (no duplicates later)', ride.get('savedRoute') == r0.get('id'))
        toasts = await pg.evaluate("window.__lastToasts")
        check('toast says where it went', 'Маршруты → Мои' in toasts, toasts[-120:])
        listed = await pg.evaluate("document.getElementById('rt-list').innerText")
        check('listed in «Маршруты → Мои» with source «Моя поездка»', 'Круг у дома' in listed and 'Моя поездка' in listed, listed.replace('\n', ' | ')[:160])

        # History → the ride: button shows it is saved; pressing again makes no copy
        await pg.click('.tabs button[data-tab=history]'); await pg.clock.run_for(500)
        await pg.click('#ride-list .rideit .t'); await pg.clock.run_for(800)
        lab = await pg.evaluate("document.getElementById('rd-asroute').textContent")
        check('ride details: «✓ В моих маршрутах»', 'В моих маршрутах' in lab, lab)
        await pg.click('#rd-asroute'); await pg.clock.run_for(600)
        check('pressed again: no duplicate, says it is there', len(await pg.evaluate("DB.all('routes')")) == 1 and 'Уже есть' in await pg.evaluate("window.__lastToasts"))
        # the saved route navigates like any other
        await pg.evaluate("showTab('routes'); routeSeg('mine')"); await pg.clock.run_for(400)
        await pg.click('#rt-list [data-nav]'); await pg.clock.run_for(1500)
        tot = await pg.evaluate("Nav.route && Nav.route.total")
        check('saved route starts navigation', tot and abs(tot - r0['dist']) < 60, tot)
        await pg.evaluate("Nav.stop && Nav.stop()"); await pg.clock.run_for(300)
        check('no JS errors (save from offer)', not log['errors'], log['errors'][:3])
        await b.close()

        # ---------- 2. «Не надо», then the button in History; ⋯ menu; route deleted → can be saved again ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        DIALOGS.clear(); pg.on('dialog', on_dialog)
        rd = Rider(pg); await rd.fix(0, -5, 0)
        await ride_and_stop(pg, rd, [(0, -5)] + PATH)
        await pg.click('#ar-no'); await pg.clock.run_for(400)
        check('«Не надо»: nothing saved as a route', len(await pg.evaluate("DB.all('routes')")) == 0 and await pg.evaluate("document.getElementById('ask-asroute').hidden"))
        await pg.click('.tabs button[data-tab=history]'); await pg.clock.run_for(500)
        await pg.click('#ride-list .rideit .t'); await pg.clock.run_for(800)
        lab = await pg.evaluate("document.getElementById('rd-asroute').textContent")
        check('ride details: «⭐ В мои маршруты» button', 'В мои маршруты' in lab, lab)
        await pg.click('#rd-asroute'); await pg.clock.run_for(800)
        n = len(await pg.evaluate("DB.all('routes')"))
        lab = await pg.evaluate("document.getElementById('rd-asroute').textContent")
        check('button saves it later, label turns to ✓', n == 1 and 'В моих маршрутах' in lab, (n, lab))
        rid = (await pg.evaluate("DB.all('routes')"))[0]['id']
        await pg.evaluate(f"DB.del('routes', '{rid}')"); await pg.clock.run_for(200)
        await pg.click('#rd-more'); await pg.clock.run_for(300)
        check('⋯ menu has «⭐ В мои маршруты»', await pg.is_visible('#rdm-route'))
        await pg.click('#rdm-route'); await pg.clock.run_for(800)
        check('route deleted from «Мои» → can be saved again from the menu', len(await pg.evaluate("DB.all('routes')")) == 1)
        # name prompt cancelled → nothing saved
        await pg.evaluate("(async () => { for (const r of await DB.all('routes')) await DB.del('routes', r.id); })()"); await pg.clock.run_for(200)
        pg.remove_listener('dialog', on_dialog); pg.once('dialog', lambda d: asyncio.ensure_future(d.dismiss()))
        await pg.click('#rd-asroute'); await pg.clock.run_for(600)
        check('name dialog cancelled → nothing saved', len(await pg.evaluate("DB.all('routes')")) == 0)
        check('no JS errors (History button)', not log['errors'], log['errors'][:3])
        await b.close()

        # ---------- 3. No offer: short ride; ride along a saved route ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        pg.on('dialog', on_dialog)
        rd = Rider(pg); await rd.fix(0, -5, 0)
        await ride_and_stop(pg, rd, [(0, -5), (0, 200)])
        check('short ride (≈200 m): no offer', await pg.evaluate("document.getElementById('ask-asroute').hidden"))
        await rd.go([(0, 200), (0, -5)]); await rd.stand(2)   # back to the start of the GPX route
        tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'saveroute.gpx'); open(tmp, 'w', encoding='utf-8').write(GPX)
        await pg.set_input_files('#gpx-file', tmp); await pg.clock.run_for(1500)
        await pg.click('#gpx-list [data-go]'); await pg.clock.run_for(1500)
        check('GPX route navigating from its start', await pg.evaluate("!!Nav.route && !!Nav.rid"), await pg.evaluate("[!!Nav.route, Nav.rid || null, document.getElementById('ask-start').hidden, document.getElementById('ask-join').hidden]"))
        await ride_and_stop(pg, rd, [(0, -5), (0, 600), (600, 600)])
        check('ride along a saved route: no offer (the route is already there)', await pg.evaluate("document.getElementById('ask-asroute').hidden"))
        check('no JS errors (no offer)', not log['errors'], log['errors'][:3])
        await b.close()

        # ---------- 4. Hebrew and English ----------
        for lang, want in (('he', 'לשמור כמסלול?'), ('en', 'Save as a route?')):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            pg.on('dialog', lambda d: asyncio.ensure_future(d.accept('Ben Shemen loop')))
            rd = Rider(pg); await rd.fix(0, -5, 0)
            await ride_and_stop(pg, rd, [(0, -5)] + PATH)
            txt = await pg.evaluate("document.getElementById('ask-asroute').innerText")
            check(f'[{lang}] offer translated, no Russian left', want in txt and not any('Ѐ' <= ch <= 'ӿ' for ch in txt), txt.replace('\n', ' | '))
            await pg.click('#ar-yes'); await pg.clock.run_for(800)
            src = [r['source'] for r in await pg.evaluate("DB.all('routes')")]
            rows = await pg.evaluate("document.getElementById('rt-list').innerText")
            check(f'[{lang}] saved; «Моя поездка» shown translated in the list', len(src) == 1 and 'Ben Shemen loop' in rows and not any('Ѐ' <= ch <= 'ӿ' for ch in rows), rows.replace('\n', ' | ')[:160])
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == "__main__": asyncio.run(main())
