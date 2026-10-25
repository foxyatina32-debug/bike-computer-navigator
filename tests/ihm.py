# Israel Hiking Map / Mapeak "Share" links → saved routes (with their marked points), incl. a link inside a pasted WhatsApp message.
# The share JSON follows IsraelHiking.Common ShareUrl / DataContainer (routes → segments → latlngs, markers); the API itself is mocked.
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))

def seg(lat0, lon0, n, rt='Bike', alt=True):
    return {'routingType': rt, 'routePoint': {'lat': lat0, 'lng': lon0}, 'latlngs': [dict({'lat': round(lat0 + i * 0.0004, 6), 'lng': round(lon0 + i * 0.0003, 6)}, **({'alt': 40 + i} if alt else {})) for i in range(n)]}
def share(sid, title, routes):
    return json.dumps({'id': sid, 'title': title, 'description': '', 'osmUserId': '1', 'viewsCount': 3, 'creationDate': '2026-10-01T10:00:00Z', 'lastModifiedDate': '2026-10-01T10:00:00Z',
                       'dataContainer': {'routes': routes, 'northEast': {'lat': 32.2, 'lng': 35}, 'southWest': {'lat': 32, 'lng': 34.8}, 'baseLayer': None, 'overlays': []}, 'base64Preview': ''})
ONE = share('abc123', 'Бен-Шемен — סינגל', [{'id': 'r1', 'name': 'route', 'color': '#f00', 'markers': [{'latlng': {'lat': 31.95, 'lng': 34.92}, 'title': 'מעיין', 'type': 'star', 'urls': []}, {'latlng': {'lat': 31.96, 'lng': 34.93}, 'title': 'Кафе', 'type': 'cafe', 'urls': []}],
                                                 'segments': [seg(31.95, 34.92, 40), seg(31.95 + 39 * 0.0004, 34.92 + 39 * 0.0003, 30, alt=False)]}])
TWO = share('two22', 'Модиин', [{'id': 'a', 'name': 'Северная петля', 'markers': [], 'segments': [seg(31.9, 35.0, 25, 'None')]}, {'id': 'b', 'name': 'Южная', 'markers': [], 'segments': [seg(31.88, 35.01, 20)]}])
PTS = share('pts9', 'Только точки', [{'id': 'p', 'name': 'x', 'markers': [{'latlng': {'lat': 32, 'lng': 35}, 'title': 'A'}], 'segments': []}])
FB = share('fb1', 'Через mapeak', [{'id': 'f', 'name': 'f', 'markers': [], 'segments': [seg(32.0, 34.9, 15)]}])

async def main():
    url = serve(8782); m = Mocks()
    m.pages['israelhiking.osm.org.il/api/urls/abc123'] = (ONE, 'application/json')
    m.pages['mapeak.com/api/urls/two22'] = (TWO, 'application/json')
    m.pages['israelhiking.osm.org.il/api/urls/pts9'] = (PTS, 'application/json')
    m.pages['mapeak.com/api/urls/fb1'] = (FB, 'application/json')   # the old domain has no such share → 404 → mapeak
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        async def imp(raw):
            await pg.evaluate("window.__lastToasts = ''; showTab('gpx')")
            await pg.evaluate(f"importInput({json.dumps(raw)})"); await pg.wait_for_timeout(700)
            return await pg.evaluate("document.getElementById('url-stat').textContent")
        async def routes(): return await pg.evaluate("DB.all('routes').then(a => a.sort((x, y) => x.created - y.created).map(r => ({name: r.name, n: r.coords.length, w: r.wpts.map(w => w.name), src: r.source, alt: r.coords.filter(c => c[2] != null).length, km: +(r.dist / 1000).toFixed(2)})))")
        st = await imp('https://israelhiking.osm.org.il/share/abc123'); r = await routes()
        check('share link → one route named by the share title', 'Добавлено маршрутов: 1' in st and r and r[-1]['name'] == 'Бен-Шемен — סינגל', (st, r[-1:] if r else r))
        check('both segments joined, shared point not doubled, heights kept where given', r[-1]['n'] == 69 and r[-1]['alt'] == 40, r[-1])
        check('marked points come along as route points', r[-1]['w'] == ['מעיין', 'Кафе'], r[-1]['w'])
        check('source shows the site', r[-1]['src'] == 'Ссылка: israelhiking.osm.org.il', r[-1]['src'])
        st = await imp('Смотри какой маршрут! https://mapeak.com/share/two22 едем в субботу?'); r = await routes()
        check('link inside a pasted WhatsApp message, mapeak.com, two routes', 'Добавлено маршрутов: 2' in st and [x['name'] for x in r[-2:]] == ['Модиин · Северная петля', 'Модиин · Южная'], (st, [x['name'] for x in r[-2:]]))
        st = await imp('https://israelhiking.osm.org.il/?s=abc123')
        check('old link form ?s=<id>', 'Добавлено маршрутов: 1' in st, st)
        st = await imp('https://israelhiking.osm.org.il/share/fb1'); r = await routes()
        check('old domain does not answer → same share from mapeak.com', 'Добавлено маршрутов: 1' in st and r[-1]['name'] == 'Через mapeak', (st, r[-1]['name']))
        st = await imp('https://israelhiking.osm.org.il/share/pts9')
        check('share with points only → clear message', 'нет линии маршрута' in st, st)
        st = await imp('https://israelhiking.osm.org.il/')
        check('site link without a share → explains how to get the link', 'ссылка «Поделиться»' in st, st)
        # ride it: Маршруты → Мои → «Ехать»
        rid = await pg.evaluate("DB.all('routes').then(a => a.find(r => r.name === 'Бен-Шемен — סינגל').id)")
        await pg.evaluate(f"DB.get('routes', '{rid}').then(r => {{ showTab('rec'); Nav.set({{ name: r.name, coords: r.coords, wpts: r.wpts, rid: r.id }}); }})"); await pg.wait_for_timeout(800)
        nv = await pg.evaluate("Nav.route ? {n: Nav.route.coords.length, w: (Nav.route.wpts || []).length} : null")
        check('navigation runs on it with its 2 points', nv and nv['n'] == 69 and nv['w'] == 2, nv)
        hint = await pg.evaluate("document.body.innerText.includes('Israel Hiking Map (ссылка «Поделиться»)') || document.documentElement.innerHTML.includes('Israel Hiking Map (ссылка «Поделиться»)')")
        check('help text lists Israel Hiking Map', hint)
        errs = log['errors'] + [t for k, t in log['console'] if k == 'error' and '404' not in t]
        check('no JS errors', not errs, errs[:3])
        await b.close()
        for lang, word in (('en', 'no route line'), ('he', 'אין קו מסלול')):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            await pg.evaluate("showTab('gpx')"); await pg.evaluate("importInput('https://israelhiking.osm.org.il/share/pts9')"); await pg.wait_for_timeout(700)
            st = await pg.evaluate("document.getElementById('url-stat').textContent")
            check(f'[{lang}] message translated', word in st, st)
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
