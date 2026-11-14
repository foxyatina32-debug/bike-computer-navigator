# v110/v112: a ridden track is kept as a route in «Маршруты → Мои».
# v112: ■ → «Завершить поездку?» offers how to save: «✓ Сохранить» (History + «Мои маршруты», automatic name «Town · date ·
# km», no keyboard), «📄 Сохранить + файл GPX» (share sheet right on the tap), «Только в Историю». Then a bar with
# «Переименовать» / «📄 Файл». Not as a route for a short ride or a ride along a route that is already saved. The ride in
# History keeps the «⭐ В мои маршруты» button and ⋯ item; no duplicates; the route navigates; Hebrew and English.
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

async def ride_and_stop(pg, rd, path, v=6, how='#st-save'):
    await pg.click('#m-play' if await pg.is_visible('#m-play') else '#c-play'); await pg.clock.run_for(500)
    await rd.go(path, v=v); await rd.stand(3)
    if not await pg.is_visible('#c-stop'): await pg.click('#hud-max'); await pg.clock.run_for(400)
    await pg.click('#c-stop'); await pg.clock.run_for(200)
    await pg.click(how); await pg.clock.run_for(1200)

async def main():
    url = serve(8851); m = Mocks()
    async with async_playwright() as p:
        # ---------- 1. Ride without a route → offer → save to «Мои» ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        pg.on('dialog', on_dialog)
        rd = Rider(pg); await rd.fix(0, -5, 0)
        await ride_and_stop(pg, rd, [(0, -5)] + PATH)
        bar = await pg.evaluate("({open: !document.getElementById('savebar').hidden, t: document.getElementById('savebar').innerText})")
        check('«✓ Сохранить»: one tap, no name asked, bar «✓ Сохранено» with «Переименовать» and «📄 Файл»', bar['open'] and 'Сохранено' in bar['t'] and 'Переименовать' in bar['t'] and 'Файл' in bar['t'] and not DIALOGS, bar['t'].replace('\n', ' | '))
        n_rides = len(await pg.evaluate("DB.all('rides')"))
        check('the ride is in History', n_rides == 1, n_rides)
        routes = await pg.evaluate("DB.all('routes')")
        nm = routes[0]['name'] if routes else ''
        check('…and in «Маршруты → Мои» with an automatic name «town · date · km»', len(routes) == 1 and nm.startswith('Петах-Тиква · ') and nm.endswith(' км') and routes[0]['source'] == 'Моя поездка', nm)
        check('bar shows the name', nm and nm in bar['t'])
        await pg.click('#sb-ren'); await pg.clock.run_for(600)
        routes = await pg.evaluate("DB.all('routes')"); ride = (await pg.evaluate("DB.all('rides')"))[0]
        check('«Переименовать»: route and ride get the new name', len(DIALOGS) == 1 and routes[0]['name'] == 'Круг у дома' and ride.get('name') == 'Круг у дома', (DIALOGS, routes[0]['name'], ride.get('name')))
        await pg.clock.run_for(6000)
        check('bar goes away by itself', await pg.evaluate("document.getElementById('savebar').hidden"))
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
        check('no JS errors (one-tap save)', not log['errors'], log['errors'][:3])
        await b.close()

        # ---------- 2. «Не надо», then the button in History; ⋯ menu; route deleted → can be saved again ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        DIALOGS.clear(); pg.on('dialog', on_dialog)
        rd = Rider(pg); await rd.fix(0, -5, 0)
        await ride_and_stop(pg, rd, [(0, -5)] + PATH, how='#st-hist')
        bar = await pg.evaluate("document.getElementById('savebar').innerText")
        check('«Только в Историю»: ride saved, nothing as a route, bar without «Переименовать»', len(await pg.evaluate("DB.all('routes')")) == 0 and len(await pg.evaluate("DB.all('rides')")) == 1 and 'Поездка сохранена' in bar and not await pg.is_visible('#sb-ren') and await pg.is_visible('#sb-gpx'), bar.replace('\n', ' | '))
        await pg.click('#sb-x'); await pg.clock.run_for(200)
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
        check('short ride (≈200 m): History only, not a route', len(await pg.evaluate("DB.all('routes')")) == 0 and len(await pg.evaluate("DB.all('rides')")) == 1)
        await rd.go([(0, 200), (0, -5)]); await rd.stand(2)   # back to the start of the GPX route
        tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'saveroute.gpx'); open(tmp, 'w', encoding='utf-8').write(GPX)
        await pg.set_input_files('#gpx-file', tmp); await pg.clock.run_for(1500)
        await pg.click('#gpx-list [data-go]'); await pg.clock.run_for(1500)
        check('GPX route navigating from its start', await pg.evaluate("!!Nav.route && !!Nav.rid"), await pg.evaluate("[!!Nav.route, Nav.rid || null, document.getElementById('ask-start').hidden, document.getElementById('ask-join').hidden]"))
        n0 = len(await pg.evaluate("DB.all('routes')"))
        await ride_and_stop(pg, rd, [(0, -5), (0, 600), (600, 600)])
        bar = await pg.evaluate("document.getElementById('savebar').innerText")
        check('ride along a saved route: no duplicate route, bar says it is already there', len(await pg.evaluate("DB.all('routes')")) == n0 and 'уже есть' in bar, bar.replace('\n', ' | '))
        check('no JS errors (not as a route)', not log['errors'], log['errors'][:3])
        await b.close()

        # ---------- 4. «📄 Сохранить + файл GPX»: the share sheet opens on the tap, the ride is saved as well ----------
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate("() => { window.__shared = []; navigator.canShare = () => true; navigator.share = d => { window.__shared.push({ n: d.files[0].name, s: d.files[0].size }); return Promise.resolve(); }; }")
        rd = Rider(pg); await rd.fix(0, -5, 0)
        await ride_and_stop(pg, rd, [(0, -5)] + PATH, how='#st-file')
        sh = await pg.evaluate("window.__shared")
        check('«+ файл GPX»: share sheet with a .gpx file', len(sh) == 1 and sh[0]['n'].endswith('.gpx') and sh[0]['s'] > 500, sh)
        check('…and the ride is in History and «Мои маршруты»', len(await pg.evaluate("DB.all('rides')")) == 1 and len(await pg.evaluate("DB.all('routes')")) == 1)
        check('no JS errors (file)', not log['errors'], log['errors'][:3])
        await b.close()

        # ---------- 5. Hebrew and English ----------
        for lang, want in (('he', 'רק להיסטוריה'), ('en', 'History only')):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            rd = Rider(pg); await rd.fix(0, -5, 0)
            await pg.click('#m-play' if await pg.is_visible('#m-play') else '#c-play'); await pg.clock.run_for(500)
            await rd.go([(0, -5)] + PATH, v=6); await rd.stand(3)
            if not await pg.is_visible('#c-stop'): await pg.click('#hud-max'); await pg.clock.run_for(400)
            await pg.click('#c-stop'); await pg.clock.run_for(200)
            txt = await pg.evaluate("document.getElementById('ask-stop').innerText")
            check(f'[{lang}] save choices translated, no Russian left', want in txt and not any('Ѐ' <= ch <= 'ӿ' for ch in txt), txt.replace('\n', ' | '))
            await pg.click('#st-save'); await pg.clock.run_for(1200)
            bar = await pg.evaluate("document.getElementById('savebar').innerText")
            check(f'[{lang}] bar translated, no Russian left', bar and not any('Ѐ' <= ch <= 'ӿ' for ch in bar), bar.replace('\n', ' | '))
            rows = await pg.evaluate("document.getElementById('rt-list').innerText")
            check(f'[{lang}] saved as a route; list without Russian', len(await pg.evaluate("DB.all('routes')")) == 1 and not any('Ѐ' <= ch <= 'ӿ' for ch in rows), rows.replace('\n', ' | ')[:160])
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == "__main__": asyncio.run(main())
