# v104 auto-zoom in navigation: zoom by speed (bike: slow 17 / medium 16 / fast 15), one step closer right before a
# manoeuvre and back after it, changes held a few seconds (no flicker), a manual zoom pauses it for 15 s, nothing while
# the map is not following or with the switch off, never more than one step past the map's own detail (Israel Hiking 16 → 17).
import asyncio, sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
FIX = "((lat, lon, spd, t) => onFix({coords: {latitude: lat, longitude: lon, accuracy: 5, altitude: 30, altitudeAccuracy: 5, speed: spd, heading: null}, timestamp: t}))(%s, %s, %s, %s)"
LAT0, LON0, MLAT, MLON = 32.08, 34.88, 110540, 94300
TURN = 400   # m north, then east
ROUTE = f"Nav.set({{ name: 'Тест', noAsk: true, coords: [[{LAT0}, {LON0}], [{LAT0 + 200 / MLAT}, {LON0}], [{LAT0 + TURN / MLAT}, {LON0}], [{LAT0 + TURN / MLAT}, {LON0 + 300 / MLON}], [{LAT0 + TURN / MLAT}, {LON0 + 600 / MLON}]] }})"

class Rider:
    def __init__(s, pg): s.pg, s.d = pg, 0.0
    def pos(s):
        if s.d <= TURN: return LAT0 + s.d / MLAT, LON0
        return LAT0 + TURN / MLAT, LON0 + (s.d - TURN) / MLON
    async def ride(s, sec, spd):
        for _ in range(sec):
            s.d += spd; la, lo = s.pos()
            await s.pg.evaluate(FIX % (la, lo, spd, 'Date.now()'))
            await s.pg.wait_for_timeout(1000)
        return await s.pg.evaluate("map.getZoom()")

async def main():
    url = serve(8839); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(LAT0, LON0))
        await pg.wait_for_timeout(800)
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); S.autorec = false")
        await pg.evaluate(f"onFix({{coords: {{latitude: {LAT0}, longitude: {LON0}, accuracy: 5, altitude: 30, altitudeAccuracy: 5, speed: 0, heading: null}}, timestamp: Date.now()}})")
        await pg.evaluate(ROUTE); await pg.wait_for_timeout(500)
        await pg.evaluate("setFollow(true); AZ.userAt = 0")   # the fit-to-route at the start counts as a manual zoom (15 s pause); skipped here
        r = Rider(pg)
        z = await r.ride(8, 5.0)
        check('18 km/h, turn far ahead: zoom 16', z == 16, z)
        z = await r.ride(8, 2.5)
        check('9 km/h (climb): zoom 17 — closer', z == 17, z)
        zs = []
        for _ in range(3): zs.append(await r.ride(1, 8.0))
        check('speeding up to 29 km/h: no zoom-out in the first seconds (no flicker)', all(x == 17 for x in zs), zs)
        z = await r.ride(5, 8.0)
        check('29 km/h for a while: zoom 15 — more road ahead', z == 15, (z, round(r.d)))
        # approach the turn at 400 m
        while r.d < TURN - 140: await r.ride(1, 8.0)
        before = await pg.evaluate("map.getZoom()")
        zs = []
        while r.d < TURN - 30: zs.append(await r.ride(1, 8.0))
        nd = await pg.evaluate("Nav.nextD")
        check('approaching the turn (≤120 m): one step closer at once (15 → 16)', before == 15 and zs[-1] == 16 and zs.index(16) <= 2, (before, zs, round(nd or -1)))
        zs = []
        for _ in range(9): zs.append(await r.ride(1, 8.0))
        check('after the turn: back to 15, not before ~5 s', zs[-1] == 15 and zs[:3] == [16, 16, 16], zs)
        # manual zoom: paused for 15 s
        await pg.evaluate("map.setZoom(13, {animate: false})"); await pg.wait_for_timeout(300)
        zs = []
        for _ in range(8): zs.append(await r.ride(1, 8.0))
        check('zoomed by hand: auto-zoom leaves it alone (15 s pause)', all(x == 13 for x in zs), zs)
        await pg.evaluate("AZ.userAt = Date.now() - 16000")
        z = await r.ride(7, 8.0)
        check('after the pause: auto-zoom resumes', z == 15, z)
        # not following (map moved away): nothing
        await pg.evaluate("setFollow(false); map.setZoom(12, {animate: false}); AZ.userAt = 0")
        z = await r.ride(7, 2.5)
        check('map not following the rider: zoom untouched', z == 12, z)
        # switched off
        await pg.evaluate("setFollow(true); S.autozoom = false; map.setZoom(14, {animate: false}); AZ.userAt = 0")
        z = await r.ride(7, 2.5)
        check('switch off: zoom untouched', z == 14, z)
        await pg.evaluate("S.autozoom = true")
        # cap by the map's own detail
        caps = await pg.evaluate("""(() => { const nd = Object.getOwnPropertyDescriptor(Nav, 'nextD'); const out = [];
          const t = (sp, d) => { GPS.spdEma = sp; Nav.nextD = d; return AZ.target().z; };
          out.push(['ihm', AZ.maxNative(), t(2, 50), t(2, 1000)]);
          setBase('osm'); out.push(['osm', AZ.maxNative(), t(2, 50), t(2, 1000)]);
          RO.mode = 'car'; out.push(['car', t(15, 1000), t(25, 1000), t(15, 150)]); RO.mode = 'bike'; setBase('ihm_mtb_he');
          return out; })()""")
        check('Israel Hiking (detail to 16): never past 17, even slow at a turn', caps[0][1] == 16 and caps[0][2] == 17 and caps[0][3] == 17, caps[0])
        check('OpenStreetMap (detail to 19): slow at a turn → 18', caps[1][2] == 18 and caps[1][3] == 17, caps[1])
        check('Car mode: 54 km/h → 15, 90 km/h → 14, at a turn +1', caps[2][1:] == [15, 14, 16], caps[2])
        await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
        lbl = await pg.evaluate("document.getElementById('s-autozoom').closest('label').textContent.trim()")
        check('Settings: «Автомасштаб в навигации…», on by default', 'Автомасштаб в навигации' in lbl and await pg.evaluate("document.getElementById('s-autozoom').checked"), lbl)
        b_ = await pg.evaluate("APP_BUILD"); check(f'version text: v{b_} (current build)', f'навигация v{b_}' in await pg.evaluate("document.body.innerText"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(400)
            txt = await pg.evaluate("document.getElementById('s-autozoom').closest('label').textContent + ' | ' + ([...document.querySelectorAll('p.note')].map(x => x.textContent).find(x => x.includes('v' + APP_BUILD + ' ')) || '')")
            check(f'[{lang}] switch and version text translated', re.search(r'v1\d\d ', txt) and not re.search('[А-Яа-яЁё]', txt), txt[:160])
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
