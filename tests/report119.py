# v119: fixes from the external audit of build 118 (R01, V01–V05, I01, I02, D01, R04, greeting).
# Run: python3 tests/report119.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
FAKE_SR = '''window.__sayNext = ''; window.__srStarts = 0;
class FakeSR { start() { window.__srStarts++; setTimeout(() => { if (this._ab) return; const t = window.__sayNext; window.__sayNext = '';
  if (!t) { this.onerror && this.onerror({ error: 'no-speech' }); this.onend && this.onend(); return; }
  const res = [{ transcript: t, confidence: .9 }]; res.isFinal = true; this.onresult && this.onresult({ resultIndex: 0, results: [res] }); this.onend && this.onend(); }, 150); }
  abort() { this._ab = true; } stop() { this._ab = true; } }
window.webkitSpeechRecognition = window.SpeechRecognition = FakeSR;'''
SLOW_ROUTE = """(() => { const orig = window.routeVia; window.__rv = 0;
  window.routeVia = async function () { const n = ++window.__rv; if (window.__slow) await new Promise(r => setTimeout(r, window.__slow)); return orig.apply(this, arguments); }; })()"""
BOX = "(k => { const r = document.querySelector(k).getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })"
def over(a, b): return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
PARSE = [('set home to Tel Aviv', {'kind': 'sethome', 'q': 'tel aviv'}), ('remember home at Modiin', {'kind': 'sethome', 'q': 'modiin'}),
         ('go to Home Center', {'kind': 'place', 'q': 'home center'}), ('не едь домой', {'kind': 'neg'}), ('не надо домой', {'kind': 'neg'}),
         ('улица 31 дом 95 квартира 34 подъезд 88', {'kind': 'place', 'q': 'улица 31 дом 95 квартира 34 подъезд 88'}),
         ('отмена', {'kind': 'cancel'}), ('останови навигацию', {'kind': 'stopnav'}), ('stop navigation', {'kind': 'stopnav'}), ('עצור ניווט', {'kind': 'stopnav'}),
         ('поехали домой', {'kind': 'home'}), ('take me home', {'kind': 'home'}), ('координаты 31.95 34.88', {'kind': 'point', 'll': [31.95, 34.88]})]

def gpx(segs, name='Тест'):
    body = '</trkseg><trkseg>'.join(''.join(f'<trkpt lat="{p[0]}" lon="{p[1]}"/>' if p is not None else '<trkpt/>' for p in sg) for sg in segs)
    return f'<?xml version="1.0"?><gpx version="1.1"><trk><name>{name}</name><trkseg>{body}</trkseg></trk></gpx>'
line = lambda lat0, lon0, n=12: [[round(lat0 + i * 0.0003, 6), lon0] for i in range(n)]   # ~33 m apart

async def main():
    url = serve(8901); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await ctx.add_init_script(FAKE_SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(800)
        # ---- V03 / V04 / V05: phrases
        bad = [(t, g, w) for t, w in PARSE for g in [await pg.evaluate('t => Voice.parse(t)', t)] if g != w]
        check('V03/V04/V05: «set home to …», «Home Center», «не едь домой», four numbers of an address, «отмена», «останови навигацию»', not bad, bad)
        # ---- V05: «останови навигацию» stops it; «не едь домой» does nothing
        await pg.evaluate("lsSet('home', { ll: [32.0853, 34.7818], name: 'Тель-Авив' })")
        await pg.evaluate("window.__sayNext = 'поехали домой'"); await pg.click('#t-mic')
        await pg.wait_for_function("Nav.route && Nav.route.name === 'Домой'", timeout=15000)
        await pg.wait_for_timeout(300)
        nb, vc = await pg.evaluate(BOX + "('#navb')"), await pg.evaluate(BOX + "('#vc')")
        check('V01: after the voice route starts, the panel is below the turn banner (manoeuvre visible)', not over(nb, vc), [nb, vc])
        await pg.wait_for_timeout(3000)
        check('V01: …and closes by itself ~2.5 s later', await pg.evaluate("document.getElementById('vc').hidden"))
        await pg.click('#t-mic'); await pg.wait_for_timeout(200); await pg.evaluate("window.__sayNext = 'останови навигацию'"); await pg.click('#vc-mic')
        await pg.wait_for_function("!Nav.route", timeout=8000)
        check('V05: «останови навигацию» by voice stops navigation', 'остановлена' in await pg.evaluate("document.getElementById('vc-st').textContent"))
        await pg.evaluate("window.__sayNext = 'не едь домой'"); await pg.click('#vc-mic'); await pg.wait_for_timeout(1500)
        check('V03: «не едь домой» → nothing done, says so', not await pg.evaluate("!!Nav.route") and 'ничего не делаю' in await pg.evaluate("document.getElementById('vc-st').textContent"))
        # ---- V02: ✕ while the route is being built → no navigation later
        await pg.evaluate(SLOW_ROUTE); await pg.evaluate("window.__slow = 3000")
        await pg.evaluate("window.__sayNext = 'поехали 32,05 34,85'"); await pg.click('#vc-mic'); await pg.wait_for_timeout(1500)
        await pg.click('#vc-x'); await pg.wait_for_timeout(4500)
        check('V02: ✕ while building the route — no navigation starts afterwards', not await pg.evaluate("!!Nav.route") and await pg.evaluate("document.getElementById('vc').hidden"))
        await pg.evaluate("window.__slow = 0")

        # ---- R01: planner result goes stale when the points or options change
        await pg.evaluate("showTab('routes'); routeSeg('plan'); document.getElementById('pl-fromgps').checked = true; Plan.wps = []; addWp([32.08, 34.80], 'Финиш')")
        await pg.click('#pl-go'); await pg.wait_for_function("!!Plan.cand", timeout=15000)
        await pg.click('#pl-wps [data-rm="0"]'); await pg.wait_for_timeout(300)
        check('R01: finish removed → the old result is gone (no «Ехать» to a point that was removed)', await pg.evaluate("!Plan.cand && document.getElementById('pl-result').hidden"))
        await pg.evaluate("addWp([32.08, 34.80], 'Финиш')"); await pg.click('#pl-go'); await pg.wait_for_function("!!Plan.cand", timeout=15000)
        other = await pg.evaluate("Object.keys(BIKES).find(k => k !== RO.bike)")
        await pg.evaluate(f"setRO({{ bike: '{other}' }})"); await pg.wait_for_timeout(200)
        check('R01: bike changed after building → the result is cleared', await pg.evaluate("!Plan.cand"))
        await pg.evaluate("window.__slow = 2000"); await pg.click('#pl-go'); await pg.wait_for_timeout(500)
        await pg.evaluate("addWp([32.07, 34.79], 'Ещё точка')"); await pg.wait_for_timeout(2600)
        check('R01: a point added while building → the stale result is not shown', await pg.evaluate("!Plan.cand"))
        await pg.evaluate("window.__slow = 0")

        # ---- R04: an older search answer does not replace the newer one
        await pg.evaluate("""(() => { const o = window.geoSuggest; window.geoSuggest = async (q, n) => { if (q === 'старый') { await new Promise(r => setTimeout(r, 1500));
            return [{ lat: '32.1', lon: '34.8', display_name: 'Старый результат, Израиль' }]; } return [{ lat: '32.2', lon: '34.9', display_name: 'Новый результат, Израиль' }]; }; })()""")
        await pg.evaluate("geocode('старый'); setTimeout(() => geocode('новый'), 100)"); await pg.wait_for_timeout(2200)
        res = await pg.evaluate("document.getElementById('geo-res').innerText")
        check('R04: a late answer of an older search does not replace the newer results', 'Новый' in res and 'Старый' not in res, res[:80])

        # ---- I01 / I02: import
        imp = lambda txt, fn: pg.evaluate("([t, f]) => { window.__lastToasts = ''; try { return parseRouteFile(t, f).map(r => ({ name: r.name, n: r.coords.length, km: cumDist(r.coords).pop() / 1000 })); } catch (e) { return 'ERR ' + e.message; } }", [txt, fn])
        far = await imp(gpx([line(32.10, 34.80), line(32.15, 34.85)]), 'segments.gpx')
        check('I01: two GPX pieces km apart → two routes, no invented straight line', isinstance(far, list) and len(far) == 2 and all(r['km'] < 0.5 for r in far) and 'часть 1/2' in far[0]['name'], far)
        near = await imp(gpx([line(32.10, 34.80), line(32.1036, 34.80)]), 'near.gpx')
        check('I01: pieces 30 m apart (a GPS gap) → one route', isinstance(near, list) and len(near) == 1, near)
        gj = await imp(json.dumps({'type': 'Feature', 'properties': {'name': 'G'}, 'geometry': {'type': 'MultiLineString', 'coordinates': [[[c[1], c[0]] for c in line(32.10, 34.80)], [[c[1], c[0]] for c in line(32.15, 34.85)]]}}), 'g.geojson')
        check('I01: GeoJSON MultiLineString far apart → two routes', isinstance(gj, list) and len(gj) == 2, gj)
        badp = await imp(gpx([line(32.10, 34.80)[:5] + [[999, 999], None] + line(32.1015, 34.80)[:5]]), 'bad.gpx')
        toasts = await pg.evaluate('window.__lastToasts')
        check('I02: a point 999,999 and a point without lat/lon are dropped (not 0,0), with a message', isinstance(badp, list) and len(badp) == 1 and badp[0]['n'] == 10 and 'неверными координатами: 2' in toasts, (badp, toasts[-80:]))
        allbad = await imp(gpx([[[999, 999], [500, 1], None]]), 'allbad.gpx')
        check('I02: a file with only impossible coordinates → clear error, nothing saved', isinstance(allbad, str) and 'нет правильных координат' in allbad, allbad)

        # ---- D01: backup without sign-in tokens
        await pg.evaluate("lsSet('acct', { email: 'x@y', uid: 'u', idToken: 'AUDIT_DUMMY_ID', refreshToken: 'AUDIT_DUMMY_REFRESH', exp: 0 }); lsSet('sync', { items: {}, at: 1 })")
        txt = await pg.evaluate("makeBackupFile().then(f => f.text())")
        check('D01: backup file has no sign-in tokens or sync state', 'AUDIT_DUMMY' not in txt and '"acct"' not in txt and '"sync"' not in txt)
        await pg.evaluate("lsSet('acct', null); lsSet('sync', null)")
        # ---- greeting finishing after a section was opened
        await pg.evaluate("Nav.stop(); showTab('profile')"); await pg.evaluate("greet()"); await pg.wait_for_timeout(400)
        check('greeting: not shown over a section that is already open', await pg.evaluate("document.getElementById('hello').hidden"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # ---- Hebrew / English: new messages translated
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            await pg.evaluate(f"(() => {{ window.__lastToasts = ''; try {{ parseRouteFile({json.dumps(gpx([line(32.10, 34.80)[:5] + [[999, 999]], line(32.15, 34.85)]))}, 'x.gpx'); }} catch (e) {{}} }})()")
            await pg.wait_for_timeout(300)
            t = await pg.evaluate("document.getElementById('toast').textContent")
            check(f'{lang}: import messages translated', t and not any('Ѐ' <= ch <= 'ӿ' for ch in t), t)
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
