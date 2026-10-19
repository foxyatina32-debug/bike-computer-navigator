# «Поделиться маршрутом»: picture with the map, description, WhatsApp / share sheet, and the link opening the route for a friend.
# Run: python3 tests/share.py
import asyncio, sys, os, json, re, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ROUTE = [[32.09 + i * 0.0003, 34.88 + (i // 25) * 0.002 + (i % 7) * 0.00004, 40 + i * 0.8] for i in range(120)]

async def main():
    url = serve(8792); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate(f"DB.put('routes', {{ id: 'rt1', name: 'Бен-Шемен кольцо', coords: {json.dumps(ROUTE)}, dist: 3000, asc: 95, created: Date.now(), src: 'test', wpts: [] }})")
        await pg.evaluate("openRouteInfo('rt1', 'routes')"); await pg.wait_for_timeout(500)
        await pg.click('#ri-share'); await pg.wait_for_function("SH.blob != null", timeout=20000); await pg.wait_for_timeout(1500)
        txt = await pg.evaluate("document.getElementById('sh-txt').value")
        check('description: name, km, climb, time, difficulty', all(k in txt for k in ('Бен-Шемен кольцо', 'км', 'набора', 'в движении', 'Сложность')), txt.split('\n')[:3])
        link = next((l for l in txt.split('\n') if '#share&' in l), '')
        gm = next((l for l in txt.split('\n') if 'google.com/maps/dir' in l), '')
        check('description: Velocomp link and Google Maps link', link.startswith('http') and 'origin=' in gm and 'travelmode=bicycling' in gm, f'{len(link)} chars')
        check('link fits a message (no spaces, < 4000 chars)', ' ' not in link and len(link) < 4000, len(link))
        img = await pg.evaluate("(() => { const i = document.getElementById('sh-img'); return [i.naturalWidth, i.naturalHeight]; })()")
        check('picture 1080×1350 ready', img == [1080, 1350], img)
        await pg.screenshot(path=os.path.join(SHOT, 'share-dialog.png'))
        # save the picture itself to look at
        data = await pg.evaluate("new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result); f.readAsDataURL(SH.blob); })")
        import base64; open(os.path.join(SHOT, 'share-card.png'), 'wb').write(base64.b64decode(data.split(',')[1]))
        # editing is kept when late data arrives
        await pg.fill('#sh-txt', 'Мой текст'); await pg.wait_for_timeout(300)
        check('edited text is not overwritten', await pg.evaluate("document.getElementById('sh-txt').value") == 'Мой текст')
        # share sheet gets picture + text
        await pg.evaluate("window.__shared = null; navigator.canShare = () => true; navigator.share = d => { window.__shared = { files: (d.files || []).map(f => f.name + ':' + f.type), text: d.text }; return Promise.resolve(); }; 0")
        await pg.click('#sh-send'); await pg.wait_for_timeout(300)
        sh = await pg.evaluate("window.__shared")
        check('«Отправить»: share sheet gets the picture and the text', sh and sh['files'] == ['marshrut.png:image/png'] and sh['text'] == 'Мой текст', sh)
        await pg.evaluate("window.__opened = null; const o = HTMLAnchorElement.prototype.click; HTMLAnchorElement.prototype.click = function () { window.__opened = this.href; }; 0")
        await pg.click('#sh-wa'); wa = await pg.evaluate("window.__opened")
        check('«WhatsApp»: wa.me with the text', wa and wa.startswith('https://wa.me/?text=') and urllib.parse.unquote(wa).endswith('Мой текст'), (wa or '')[:60])
        await pg.click('#sh-x')
        # share buttons also in the planner and A→B
        check('share buttons in planner and A→B', await pg.evaluate("!!document.getElementById('r-share') && /ab-share/.test(abShow.toString())"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()

        # Friend opens the link (fresh phone, no routes).
        m2 = Mocks()
        path = link.split('#', 1)[1]
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m2)
        await pg.evaluate(f"location.hash = {json.dumps('#' + path)}"); await pg.wait_for_timeout(2500)
        got = await pg.evaluate("DB.all('routes').then(r => r.map(x => ({ n: x.name, d: Math.round(x.dist), ele: x.coords.filter(c => c[2] != null).length, n0: x.coords.length })))")
        title = await pg.evaluate("document.getElementById('ri-title').textContent")
        d0 = await pg.evaluate(f"Math.round(cumDist({json.dumps(ROUTE)}).pop())")
        check('friend: route saved and opened from the link', len(got) == 1 and got[0]['n'] == 'Бен-Шемен кольцо' and title == 'Бен-Шемен кольцо' and abs(got[0]['d'] - d0) < d0 * 0.02 and got[0]['ele'] > 1, f"{got} vs {d0} m")
        await pg.evaluate(f"location.hash = {json.dumps('#' + path)}"); await pg.wait_for_timeout(2000)
        check('friend: opening the link again does not duplicate', await pg.evaluate("DB.all('routes').then(r => r.length)") == 1)
        check('no JS errors (friend)', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
