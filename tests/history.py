# History like a sports journal: summary, period, month groups, cards with a map; ride page with map, gauge, chart, data.
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []; SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
GPX = '''<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"><trk><name>Ride with HR</name><type>cycling</type><trkseg>''' + ''.join(
    f'<trkpt lat="{32.08 + i * 0.00008:.6f}" lon="{34.88 + math.sin(i / 9) * 0.002:.6f}"><ele>{30 + 10 * math.sin(i / 15):.1f}</ele><time>2026-10-11T13:{i // 60 % 60:02d}:{i % 60:02d}Z</time><extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>{120 + i % 30}</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>'
    for i in range(0, 1800, 5)) + '</trkseg></trk></gpx>'
async def main():
    url = serve(8776); m = Mocks()
    async with async_playwright() as p:
        for lang in ('ru', 'he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            # an old ride (last year) and a recorded ride this month
            await pg.evaluate("""(() => { const now = Date.now(), tr = []; for (let i = 0; i < 400; i++) tr.push([32.09 + i * 0.00005, 34.88 + Math.sin(i / 40) * 0.001, 20 + i * 0.05, now - 3600e3 + i * 5000]);
              return Promise.all([DB.put('rides', { id: 'a', name: 'Поездка 18.10, 16:43', start: now - 3600e3, end: now - 1600e3, type: 'bike', dist: 2200, movingMs: 1900000, max: 6.5, asc: 20, desc: 3, track: tr }),
                DB.put('rides', { id: 'b', name: 'Кольцо Бен-Шемен', start: new Date(new Date().getFullYear() - 1, 5, 3, 7).getTime(), end: new Date(new Date().getFullYear() - 1, 5, 3, 9).getTime(), type: 'bike', dist: 31000, movingMs: 5400000, max: 11, asc: 300, desc: 300, track: tr.map(p => [p[0] + .1, p[1], p[2], p[3]]) })]); })()""")
            if lang == 'ru':
                with open(os.path.join(SHOT, 'hr.gpx'), 'w') as f: f.write(GPX)
                await pg.evaluate("showTab('history')"); await pg.set_input_files('#act-file', os.path.join(SHOT, 'hr.gpx')); await pg.wait_for_timeout(1200)
            await pg.evaluate("HS.per = 'all'; showTab('history')"); await pg.wait_for_timeout(1500)
            n = 3 if lang == 'ru' else 2
            st = await pg.evaluate("({sum: document.getElementById('hist-sum').innerText, mon: [...document.querySelectorAll('.hmon')].length, cards: document.querySelectorAll('#ride-list .rcard').length, maps: document.querySelectorAll('#ride-list .rcmap.leaflet-container').length, t: document.querySelector('#ride-list .rcard .t').textContent})")
            check(f'[{lang}] list: summary, month groups, cards with a map', str(n) in st['sum'] and st['mon'] >= 2 and st['cards'] == n and st['maps'] >= 1, st)
            lt = await pg.evaluate("document.getElementById('ride-list').innerText")
            if lang == 'ru': check('old automatic name shown by time of day', 'Поездка 18.10' not in lt and any(x in lt for x in ('Утренняя поездка', 'Дневная поездка', 'Вечерняя поездка', 'Ночная поездка')))
            await pg.screenshot(path=os.path.join(SHOT, f'hist-list-{lang}.png'))
            await pg.click('#h-per [data-p=month]'); await pg.wait_for_timeout(400)
            c2 = await pg.evaluate("document.querySelectorAll('#ride-list .rcard').length")
            check(f'[{lang}] «Месяц» leaves out last year', c2 == n - 1 or (lang == 'ru' and c2 in (1, 2)), c2)
            await pg.click('#h-per [data-p=all]'); await pg.wait_for_timeout(300)
            rid = 'a' if lang != 'ru' else await pg.evaluate("HS.list.find(r => r.imported).id")
            await pg.evaluate(f"openRide('{rid}')"); await pg.wait_for_timeout(1500)
            d = await pg.evaluate("({map: !!document.querySelector('#rd-mapel.leaflet-container'), lines: document.querySelectorAll('#rd-mapel path.leaflet-interactive, #rd-mapel svg path').length, gauge: !!document.querySelector('.gsvg'), chart: !!document.getElementById('rd-chart'), body: document.getElementById('rd-body').innerText})")
            check(f'[{lang}] ride page: map with coloured track, gauge, chart', d['map'] and d['lines'] >= 2 and d['gauge'] and d['chart'], {k: v for k, v in d.items() if k != 'body'})
            if lang == 'ru':
                check('imported GPX: heart rate shown', 'уд/мин' in d['body'] and 'макс 145' in d['body'], d['body'][-300:])
                check('no weight → calories ask for weight', 'Указать вес' in d['body'])
                await pg.evaluate("S.weight = 80; saveS(); openRide(HS.cur.id)"); await pg.wait_for_timeout(600)
                body = await pg.evaluate("document.getElementById('rd-body').innerText")
                check('with weight → calories estimate', '≈' in body and 'ккал' in body, [l for l in body.split('\n') if 'ккал' in l])
                await pg.screenshot(path=os.path.join(SHOT, 'hist-ride-top.png'))
                await pg.evaluate("document.getElementById('sheet-ride').scrollTop = 700"); await pg.wait_for_timeout(300)
                bx = await pg.evaluate("(r => [r.x, r.y, r.width, r.height])(document.getElementById('rd-chart').getBoundingClientRect())")
                await pg.mouse.click(bx[0] + bx[2] * .5, bx[1] + bx[3] * .5); await pg.wait_for_timeout(200)
                sc = await pg.evaluate("document.getElementById('rd-scrub').textContent")
                check('chart scrub shows time, speed, height, pulse', 'км/ч' in sc and '❤️' in sc, sc)
                await pg.screenshot(path=os.path.join(SHOT, 'hist-ride-mid.png'))
                await pg.evaluate("document.getElementById('sheet-ride').scrollTop = 1e5"); await pg.wait_for_timeout(300)
                await pg.screenshot(path=os.path.join(SHOT, 'hist-ride-bottom.png'))
                await pg.evaluate("document.getElementById('sheet-ride').scrollTop = 0"); await pg.click('#rd-fly'); await pg.wait_for_timeout(1500)
                fl = await pg.evaluate("!!RD.fly && document.getElementById('rd-fly').textContent.includes('Стоп')")
                await pg.click('#rd-fly'); check('fly-over runs and stops', fl and not await pg.evaluate("RD.fly"))
                await pg.click('#rd-card'); vis = await pg.evaluate("!document.getElementById('ask-card').hidden")
                await pg.evaluate("window.__shared = null; shareFile = async (f) => { window.__shared = f.name + ':' + f.size; return 'shared'; }; 0"); await pg.click('#cd-plain'); await pg.wait_for_timeout(1500)
                check('postcard: choice with/without photo, image made', vis and await pg.evaluate("!!window.__shared"), await pg.evaluate("window.__shared"))
                await pg.click('#rd-again'); await pg.wait_for_timeout(500)
                check('«Повторить маршрут» starts navigation on the track', await pg.evaluate("!!Nav.route && !document.getElementById('hud').hidden"))
                await pg.evaluate("Nav.stop()")
                await pg.evaluate("openRide('a')"); await pg.wait_for_timeout(500); await pg.click('#rd-more'); await pg.click('#rdm-del'); await pg.click('#rdm-del'); await pg.wait_for_timeout(600)
                check('⋯ → delete (two taps)', not await pg.evaluate("DB.get('rides', 'a')"))
            else:
                await pg.screenshot(path=os.path.join(SHOT, f'hist-ride-{lang}.png'))
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
