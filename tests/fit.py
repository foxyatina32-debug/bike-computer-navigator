# FIT files (Garmin, Wahoo, Zwift, Komoot…): import as a workout into History and as a route.
# The FIT files are generated here: little/big endian, compressed timestamps, developer fields, a course file without a session.
import asyncio, sys, os, struct, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []; SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))

def crc(data):
    t = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401, 0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]; c = 0
    for b in data:
        x = t[c & 0xF]; c = (c >> 4) & 0x0FFF; c ^= x ^ t[b & 0xF]
        x = t[c & 0xF]; c = (c >> 4) & 0x0FFF; c ^= x ^ t[(b >> 4) & 0xF]
    return c

def fit_file(be=False, compressed=False, dev=False, course=False, n=300, kcal=321, t0=1130000000):
    E = '>' if be else '<'; out = bytearray()
    def defn(local, gnum, fields, devf=None):
        out.extend(bytes([0x40 | local | (0x20 if devf else 0), 0, 1 if be else 0]) + struct.pack(E + 'H', gnum) + bytes([len(fields)]) + b''.join(bytes(f) for f in fields))
        if devf: out.extend(bytes([len(devf)]) + b''.join(bytes(f) for f in devf))
    defn(0, 0, [(0, 1, 0x00), (1, 2, 0x84), (4, 4, 0x86)]); out.extend(bytes([0, 6 if course else 4]) + struct.pack(E + 'HI', 1, t0))
    if dev:
        defn(1, 207, [(3, 1, 0x02)]); out.extend(bytes([1, 0]))
        defn(1, 206, [(0, 1, 0x02), (1, 1, 0x02), (2, 1, 0x02), (3, 8, 0x07)]); out.extend(bytes([1, 0, 0, 0x84]) + b'power\0\0\0')
    rf = [(0, 4, 0x85), (1, 4, 0x85), (78, 4, 0x86), (3, 1, 0x02), (4, 1, 0x02), (6, 2, 0x84)]; devf = [(0, 2, 0)] if dev else None
    defn(2, 20, [(253, 4, 0x86)] + rf, devf)
    if compressed: defn(3, 20, rf, devf)
    sc = lambda d: int(round(d * 2 ** 31 / 180)); ts = t0
    for i in range(n):
        if i: ts += 3 if compressed and i % 7 == 0 else 1
        body = struct.pack(E + 'iiIBBH', sc(32.087 + i * 0.00005), sc(34.887 + math.sin(i / 30) * 0.0005), int(round((550 + 20 * math.sin(i / 40)) * 5)), 110 + i % 40, 80, 5000)
        if dev: body += struct.pack(E + 'H', 200 + i % 50)
        out.extend((bytes([0x80 | (3 << 5) | (ts & 0x1f)]) if compressed and i else bytes([2]) + struct.pack(E + 'I', ts)) + body)
    if not course:
        defn(4, 19, [(253, 4, 0x86), (11, 2, 0x84)]); out.extend(bytes([4]) + struct.pack(E + 'IH', ts, 100))
        defn(5, 18, [(253, 4, 0x86), (5, 1, 0x00), (11, 2, 0x84)]); out.extend(bytes([5]) + struct.pack(E + 'IBH', ts, 2, kcal))
    hdr = bytearray(struct.pack('<BBHI4s', 14, 0x20, 2132, len(out), b'.FIT')); hdr += struct.pack('<H', crc(hdr))
    data = bytes(hdr) + bytes(out); return data + struct.pack('<H', crc(data))

async def main():
    url = serve(8781); m = Mocks(); os.makedirs(SHOT, exist_ok=True)
    files = {'ride.fit': fit_file(be=True, compressed=True, dev=True), 'ride_le.fit': fit_file(kcal=450, t0=1130100000), 'course.fit': fit_file(course=True, t0=1130200000), 'broken.fit': fit_file()[:14] + bytes(range(200, 256)) * 4}
    for k, v in files.items(): open(os.path.join(SHOT, k), 'wb').write(v)
    P = lambda k: os.path.join(SHOT, k)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate("showTab('history')")
        await pg.set_input_files('#act-file', [P('ride.fit'), P('ride_le.fit')]); await pg.wait_for_timeout(1500)
        t = await pg.evaluate("window.__lastToasts")
        rides = await pg.evaluate("DB.all('rides').then(a => a.filter(r => r.imported).map(r => ({n: r.track.length, kcal: r.kcal, type: r.type, dist: Math.round(r.dist), hr: r.track.filter(p => p[4]).length, start: r.start, asc: Math.round(r.asc)})))")
        check('two FIT workouts added to History', 'Добавлено тренировок: 2' in t and len(rides) == 2, t)
        r = next((x for x in rides if x['kcal'] == 321), None)
        check('big-endian + compressed timestamps + developer fields: 300 points, pulse, bike, 321 kcal', r and r['n'] == 300 and r['hr'] == 300 and r['type'] == 'bike', r)
        check('distance and start time from the file', r and 1600 < r['dist'] < 1800 and r['start'] == (1130000000 + 631065600) * 1000, r)
        check('little-endian file: calories 450 from the session', any(x['kcal'] == 450 for x in rides), rides)
        rid = await pg.evaluate("DB.all('rides').then(a => a.find(r => r.kcal === 321).id)")
        await pg.evaluate(f"openRide('{rid}')"); await pg.wait_for_timeout(1500)
        body = await pg.evaluate("document.getElementById('rd-body').innerText")
        check('ride page shows calories from the file and pulse', '321' in body and 'ккал' in body and 'уд/мин' in body, [l for l in body.split('\n') if 'ккал' in l or 'уд/мин' in l])
        await pg.screenshot(path=P('fit-ride.png'))
        await pg.evaluate("window.__lastToasts = ''")
        await pg.set_input_files('#act-file', P('ride.fit')); await pg.wait_for_timeout(1000)
        check('same FIT again → not duplicated', 'уже были: 1' in await pg.evaluate("window.__lastToasts"), await pg.evaluate("window.__lastToasts"))
        await pg.evaluate("window.__lastToasts = ''")
        await pg.set_input_files('#act-file', P('course.fit')); await pg.wait_for_timeout(800)
        t = await pg.evaluate("window.__lastToasts")
        check('course FIT into History: added (it has time stamps) or explained', 'Добавлено тренировок: 1' in t or 'маршрут' in t, t)
        await pg.evaluate("window.__lastToasts = ''")
        await pg.set_input_files('#act-file', P('broken.fit')); await pg.wait_for_timeout(800)
        t = await pg.evaluate("window.__lastToasts")
        check('broken FIT → message, app keeps working', 'broken.fit' in t, t)
        # as a route
        await pg.evaluate("showTab('gpx')"); await pg.set_input_files('#gpx-file', P('course.fit')); await pg.wait_for_timeout(1200)
        gl = await pg.evaluate("document.getElementById('gpx-list').innerText")
        check('course FIT opens as a route: name and length', 'course' in gl and 'км' in gl, gl[:200])
        await pg.screenshot(path=P('fit-route.png'))
        await pg.click('#gpx-list [data-go]'); await pg.wait_for_timeout(800)
        nv = await pg.evaluate("Nav.route ? {n: Nav.route.coords.length, name: Nav.route.name} : null")
        check('«Ехать» starts navigation on the FIT route', nv and nv['n'] >= 2, nv)
        await pg.evaluate("window.__lastToasts = ''")
        await pg.set_input_files('#gpx-file', P('broken.fit')); await pg.wait_for_timeout(800)
        check('broken FIT as a route → message', 'broken.fit' in await pg.evaluate("window.__lastToasts"))
        errs = log['errors'] + [t for k, t in log['console'] if k == 'error']
        check('no JS errors', not errs, errs[:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
