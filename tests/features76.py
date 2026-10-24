# v76 (from the comparison with Google Maps / Waze / Off-Road / Komoot / Trailforks):
# «затем…», steep-descent and hairpin warnings ahead, rider lower in heading-up modes, the Emergency screen.
import asyncio, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
FAKE = """(() => { window.__said = []; let speaking = false;
  const fake = { get speaking() { return speaking; }, pending: false, cancel() { speaking = false; }, speak(u) { window.__said.push(u.text); }, getVoices() { return []; } };
  Object.defineProperty(window, 'speechSynthesis', { value: fake, configurable: true }); S.voice = true; })()"""
def north(lat0, lon0, metres, step=20, alt=None):
    pts = []
    for i in range(int(metres / step) + 1):
        a = alt(i * step) if alt else 50
        pts.append([lat0 + i * step / 110540, lon0, a])
    return pts
async def main():
    url = serve(8786)
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', Mocks(), geo=(32.09, 34.88))
        await pg.wait_for_timeout(1500)
        await pg.evaluate(FAKE)
        lat, lon = 32.10, 34.88
        async def at(la, lo, wait=900):
            await ctx.set_geolocation({'latitude': la, 'longitude': lo, 'accuracy': 5}); await pg.wait_for_timeout(wait)
        # 1. «затем»: right turn at 600 m, left turn 80 m after it.
        k = 111320 * math.cos(32.1 * math.pi / 180)
        r1 = north(lat, lon, 600) + [[lat + 600 / 110540, lon + d / k, 50] for d in range(20, 81, 20)]
        e = r1[-1]; r1 += [[e[0] + d / 110540, e[1], 50] for d in range(20, 401, 20)]
        await at(lat + 290 / 110540, lon, 1200)
        await pg.evaluate(f"Nav.set({{name: 'Т1', coords: {json.dumps(r1)}, noAsk: true}})"); await pg.wait_for_timeout(300)
        for m in range(300, 520, 12): await at(lat + m / 110540, lon, 800)
        txt = await pg.inner_text('#nv-txt'); said = await pg.evaluate("window.__said.join(' | ')")
        check('«затем»: the next turn is shown under the current one', 'затем' in txt and 'налево' in txt.split('затем')[1], txt)
        check('«затем»: and spoken after the first turn', 'затем поверните налево' in said or 'затем налево' in said, said[-160:])
        # 2. Steep descent: flat 500 m, then 15% down for 200 m, then flat.
        def alt(d): return 100 if d < 500 else 100 - min(200, d - 500) * 0.15
        r2 = north(32.13, 34.88, 1000, alt=alt)
        await pg.evaluate("window.__said = []")
        await at(32.13 + 100 / 110540, 34.88, 1500)
        await pg.evaluate(f"Nav.set({{name: 'Т2', coords: {json.dumps(r2)}, noAsk: true}})"); await pg.wait_for_timeout(300)
        h = await pg.evaluate("Nav.route.ahead")
        check('steep descent found on the route (≈15%, ≈200 m, starting ≈500 m)', len(h) == 1 and h[0]['kind'] == 'desc' and 12 <= h[0]['pct'] <= 18 and 140 <= h[0]['len'] <= 260 and 440 <= h[0]['d'] <= 520, h)
        s0 = await pg.evaluate("window.__said.length")
        for m in range(112, 160, 12): await at(32.13 + m / 110540, 34.88, 800)
        early = await pg.evaluate(f"window.__said.slice({s0}).join(' | ')")
        for m in range(172, 260, 12): await at(32.13 + m / 110540, 34.88, 800)
        said = await pg.evaluate("window.__said.join(' | ')"); toasts = await pg.evaluate("window.__lastToasts")
        check('not announced too early (350 m before)', 'спуск' not in early, early)
        check('announced ~300 m before: «через … метров крутой спуск, … процентов»', 'крутой спуск' in said and 'процентов' in said and 'Впереди крутой спуск' in toasts, said[-140:])
        # 3. Hairpins: 4 sharp turns within 200 m (zig-zag of 50 m legs).
        r3 = north(32.16, 34.88, 300); e = r3[-1]; la, lo = e[0], e[1]
        for leg in range(4):
            dx = 50 / k * (1 if leg % 2 == 0 else -1)
            for t in range(1, 6): r3.append([la + 4 / 110540 * t / 5, lo + dx * t / 5, 50])
            la, lo = r3[-1][0], r3[-1][1]
            r3.append([la + 10 / 110540, lo, 50]); la = r3[-1][0]
        r3 += [[la + d / 110540, lo, 50] for d in range(20, 201, 20)]
        await pg.evaluate(f"Nav.set({{name: 'Т3', coords: {json.dumps(r3)}, noAsk: true}})"); await pg.wait_for_timeout(300)
        h = await pg.evaluate("Nav.route.ahead.map(x => x.kind + ':' + (x.n || ''))")
        check('hairpin series found (3+ sharp turns within 300 m)', any(x.startswith('serp') for x in h), h)
        # 4. Rider lower on the screen in heading-up with a route; in the middle with north up.
        await pg.evaluate(f"Nav.set({{name: 'Т2', coords: {json.dumps(r2)}, noAsk: true}}); setOrientation('course', true); setFollow(true)")
        for m in range(260, 330, 12): await at(32.13 + m / 110540, 34.88, 800)
        await pg.wait_for_timeout(1200)
        pos = "(() => { const p = map.latLngToContainerPoint(meMarker.getLatLng()), v = viewPad(); return {y: p.y, mid: (v.top + innerHeight - v.bottom) / 2, vis: innerHeight - v.top - v.bottom}; })()"
        a = await pg.evaluate(pos)
        await pg.evaluate("setOrientation('north', true)"); await pg.wait_for_timeout(1200); n = await pg.evaluate(pos)
        check('heading-up: rider ~20% of the view below the middle (more road ahead)', a['y'] - a['mid'] > 0.15 * a['vis'], a)
        check('north up: rider in the middle', abs(n['y'] - n['mid']) < 0.05 * n['vis'], n)
        # 5. Emergency screen.
        await pg.evaluate("Nav.stop()"); await pg.wait_for_timeout(300)
        check('SOS button on the map', await pg.is_visible('#t-sos'))
        await pg.evaluate("(() => { window.__wa = null; const o = HTMLAnchorElement.prototype.click; HTMLAnchorElement.prototype.click = function () { if (/wa\\.me/.test(this.href)) { window.__wa = this.href; return; } return o.call(this); }; return true; })()")
        await pg.click('#t-sos'); await pg.wait_for_timeout(500)
        st = await pg.evaluate("({open: !document.getElementById('ask-sos').hidden, ll: document.getElementById('sos-ll').textContent, meta: document.getElementById('sos-meta').textContent, tel: [...document.querySelectorAll('#ask-sos a[href^=\"tel:\"]')].map(a => a.getAttribute('href')), g: [GPS.fix.lat, GPS.fix.lon]})")
        check('Emergency: coordinates of where I am, accuracy, 101 / 100 / 102', st['open'] and st['ll'] == f"{st['g'][0]:.5f}, {st['g'][1]:.5f}" and 'Точность' in st['meta'] and st['tel'] == ['tel:101', 'tel:100', 'tel:102'], st)
        await pg.click('#sos-wa'); await pg.wait_for_timeout(300)
        wa = await pg.evaluate("window.__wa")
        check('«Отправить в WhatsApp»: message with the coordinates and a map link', wa and 'wa.me' in wa and 'maps.google.com' in wa and f"{st['g'][0]:.5f}" in wa, (wa or '')[:160])
        await pg.click('#sos-x'); await pg.wait_for_timeout(200)
        check('Emergency closes', await pg.evaluate("document.getElementById('ask-sos').hidden"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
