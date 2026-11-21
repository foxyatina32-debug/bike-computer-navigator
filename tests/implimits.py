# v151 (audit R15): limits on imported files, told clearly, and the current ride goes on. A route file over 50 MB, a route
# with more than 300 000 points, a KMZ whose file unpacks to more than 50 MB, a backup over 200 MB: refused with the
# reason (no hang, no crash); a normal GPX still opens; the History chart and route profile of a 200 000-point ride work
# (Math.min(...) of a long array overflowed the stack). ru / en.
# Run: python3 tests/implimits.py
import asyncio, sys, os, json, io, zipfile, struct, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

def kmz_declared(usize):
    """a real KMZ (deflated KML) whose central directory says the file unpacks to usize bytes"""
    kml = '<?xml version="1.0"?><kml><Document><Placemark><LineString><coordinates>34.88,32.09 34.89,32.1</coordinates></LineString></Placemark></Document></kml>'
    b = io.BytesIO(); z = zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED); z.writestr('doc.kml', kml); z.close(); raw = bytearray(b.getvalue())
    cd = raw.find(b'PK\x01\x02'); struct.pack_into('<I', raw, cd + 24, usize)
    return base64.b64encode(bytes(raw)).decode()
GPX = lambda n: '<?xml version="1.0"?><gpx><trk><trkseg>' + ''.join(f'<trkpt lat="{32.09 + i * 1e-5:.6f}" lon="34.88"/>' for i in range(n)) + '</trkseg></trk></gpx>'

async def main():
    url = serve(8927)
    async with async_playwright() as p:
        for lang in ('ru', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', Mocks(), geo=(32.09, 34.88))
            await pg.wait_for_timeout(1000)
            await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); Ride.start(); 0")
            big = 'слишком большой' if lang == 'ru' else 'too big'
            await pg.evaluate("window.__lastToasts = ''; openRouteFiles([{ name: 'huge.gpx', size: 60e6, arrayBuffer: async () => { throw new Error('read'); } }])"); await pg.wait_for_timeout(300)
            t = await pg.evaluate("tr(window.__lastToasts)")
            check(f'[{lang}] a route file of 60 MB: refused with the reason, not read', big in t and '60' in t, t[-140:])
            if lang == 'ru':
                n0 = await pg.evaluate("(async () => (await DB.all('routes')).length)()")
                await pg.evaluate("(async t => { window.__lastToasts = ''; await openRouteFiles([new File([t], 'many.gpx')]); })(%s)" % json.dumps(GPX(300001)))
                t = await pg.evaluate("window.__lastToasts")
                check('a route of 300 001 points: refused («слишком много точек»), nothing saved', 'слишком много точек' in t and await pg.evaluate("(async () => (await DB.all('routes')).length)()") == n0, t[-140:])
                err = await pg.evaluate("(async b64 => { const s = atob(b64), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); try { await parseBuffer(u.buffer, 'x.kmz'); return ''; } catch (e) { return e.message; } })(%s)" % json.dumps(kmz_declared(60_000_000)))
                check('a KMZ whose file unpacks to 60 MB: refused before unpacking', 'слишком большой' in err, err)
                ok = await pg.evaluate("(async b64 => { const s = atob(b64), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); const it = await parseBuffer(u.buffer, 'x.kmz'); return it.length && it[0].coords.length; })(%s)" % json.dumps(kmz_declared(150)))
                check('a normal KMZ still opens', ok == 2, ok)
                await pg.evaluate("(async t => { window.__lastToasts = ''; await openRouteFiles([new File([t], 'ok.gpx')]); })(%s)" % json.dumps(GPX(500)))
                check('a normal GPX still opens', await pg.evaluate("(async () => (await DB.all('routes')).length)()") == n0 + 1)
            await pg.evaluate("window.__lastToasts = ''; document.getElementById('bk-file').onchange({ target: { files: [{ name: 'b.json', size: 3e8, text: async () => '{}' }], value: '' } })"); await pg.wait_for_timeout(300)
            t = await pg.evaluate("tr(window.__lastToasts)")
            check(f'[{lang}] a backup of 300 MB: refused with the reason, nothing changed', big in t and '300' in t, t[-160:])
            check(f'[{lang}] the ride being recorded goes on', await pg.evaluate("Ride.status") == 'rec')
            if lang == 'ru':
                st = await pg.evaluate("""(async () => { const t0 = 1.79e12, tr = []; for (let i = 0; i < 200000; i++) tr.push([32 + i * 2e-5, 34.8 + (i % 9) * 1e-5, 30 + (i % 300) / 10, t0 + i * 1000]);
                  await DB.put('rides', { id: 'longR', name: 'Длинная', start: t0, end: t0 + 2e8, type: 'bike', dist: 440000, movingMs: 2e8, track: tr });
                  try { await openRide('longR'); return 'ok'; } catch (e) { return String(e); } })()""")
                await pg.wait_for_timeout(1500)
                check('a ride of 200 000 points opens (chart, profile) without a stack overflow', st == 'ok' and not any('call stack' in e for e in log['errors']), (st, log['errors'][:2]))
            await pg.evaluate("Ride.stop(false)")
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
