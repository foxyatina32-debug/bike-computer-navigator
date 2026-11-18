# v131: «открыто ли сейчас и когда доедете». Opening hours from OpenStreetMap are read (weekdays, ranges, several
# intervals, past midnight, 24/7, off, «, Sa …» as one more rule; anything else → unknown, nothing claimed): open now,
# «открыто до 14:00», «закрыто · откроется в 08:00», and at the arrival «к вашему приезду (≈ 15:20) — закрыто» — in the
# «Что по пути» popups and in «Перед выездом». Shabbat (Friday sunset −20 min … Saturday sunset +40 min) on the way →
# «многие кафе и магазины закрыты». ru / he / en. Run: python3 tests/openhours.py
import asyncio, sys, os, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
import preride as P
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
UNIT = """() => {
  const at = (wd, h, m = 0) => { const d = new Date(2026, 10, 15, h, m); d.setDate(d.getDate() + ((wd - d.getDay()) + 7) % 7); return d; };
  const o = (s, d) => ohOpenAt(s, d), hm = d => d ? [d.getDay(), d.getHours(), d.getMinutes()] : null;
  const IL = 'Su-Th 08:00-22:00; Fr 08:00-14:00; Sa off';
  return {
    week: [o('Mo-Fr 08:00-17:00', at(3, 10)), o('Mo-Fr 08:00-17:00', at(3, 18)), o('Mo-Fr 08:00-17:00', at(6, 10))],
    next: hm(ohNext('Mo-Fr 08:00-17:00', at(3, 18))),
    il: [o(IL, at(5, 13)), o(IL, at(5, 15)), o(IL, at(6, 12)), o(IL, at(0, 9))],
    all: [o('24/7', at(6, 3)), o('24/7', at(2, 15))],
    night: [o('Mo-Su 18:00-02:00', at(2, 1)), o('Mo-Su 18:00-02:00', at(2, 3)), o('Mo-Su 18:00-02:00', at(2, 19))],
    lunch: [o('Mo-Fr 08:00-12:00,14:00-18:00', at(3, 13)), hm(ohNext('Mo-Fr 08:00-12:00,14:00-18:00', at(3, 13)))],
    comma: [o('Mo-Fr 08:00-17:00, Sa 09:00-13:00', at(6, 10)), o('Mo-Fr 08:00-17:00, Sa 09:00-13:00', at(0, 10))],
    ph: o('Mo-Fr 08:00-17:00; PH off', at(3, 10)),
    wrap: [o('Fr-Mo 10:00-12:00', at(0, 11)), o('Fr-Mo 10:00-12:00', at(3, 11))],
    unknown: ['sunrise-sunset', 'Jan-Mar Mo-Fr 08:00-17:00', 'Mo-Fr 08:00-17:00 "by appointment"', 'PH off', '', 'Mo-Fr 08:00-17:00 || "call"'].map(s => o(s, at(3, 10))),
  };
}"""
SHAB = """() => { const lat = 32.08, lon = 34.78, fri = new Date(2026, 10, 20, 12), sat = new Date(2026, 10, 21, 12);
  const f = sunTimes(lat, lon, fri).set.getTime(), s = sunTimes(lat, lon, sat).set.getTime(), A = t => shabbatAt(new Date(t), lat, lon);
  return [A(f - 3600000), A(f - 600000), A(s + 1800000), A(s + 3600000), shabbatAt(new Date(2026, 10, 18, 20), lat, lon)]; }"""

def hhmm(t): return f'{t.hour:02d}:{t.minute:02d}'
def window(a_min, b_min):
    # «Mo-Su HH:MM-HH:MM» from now + a_min (down to 5 min) to now + b_min (up to 5 min), local time like the browser's
    now = datetime.datetime.now().replace(second=0, microsecond=0)
    a = now + datetime.timedelta(minutes=a_min); a -= datetime.timedelta(minutes=a.minute % 5)
    b = now + datetime.timedelta(minutes=b_min); b += datetime.timedelta(minutes=(5 - b.minute % 5) % 5)
    return f'Mo-Su {hhmm(a)}-{hhmm(b)}'

async def main():
    url = serve(9055); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        u = await pg.evaluate(UNIT)
        check('weekdays: Wed 10:00 open, Wed 18:00 closed, Sat closed; next change Thu 08:00', u['week'] == [True, False, False] and u['next'] == [4, 8, 0], u)
        check('Israeli week «Su-Th …; Fr 08:00-14:00; Sa off»: Fri 13:00 open, Fri 15:00 closed, Sat closed, Sun open', u['il'] == [True, False, False, True], u['il'])
        check('24/7 always open', u['all'] == [True, True])
        check('past midnight «18:00-02:00»: Tue 01:00 open (from Monday), 03:00 closed, 19:00 open', u['night'] == [True, False, True], u['night'])
        check('lunch break: Wed 13:00 closed, opens 14:00', u['lunch'] == [False, [3, 14, 0]], u['lunch'])
        check('«…, Sa 09:00-13:00» is one more rule: Sat 10:00 open, Sun closed', u['comma'] == [True, False], u['comma'])
        check('«PH off» does not close ordinary days; days wrapping round the week (Fr-Mo)', u['ph'] is True and u['wrap'] == [True, False], (u['ph'], u['wrap']))
        check('anything not understood → unknown (null), nothing claimed', u['unknown'] == [None] * 6, u['unknown'])
        sh = await pg.evaluate(SHAB)
        check('Shabbat: Fri an hour before sunset — no; 10 min before — yes; Sat 30 min after sunset — yes, an hour after — no; Wednesday — no', sh == [False, True, True, False, False], sh)
        await b.close()
        # ---------- «Что по пути»: hours in the popups (relative to now)
        OPEN, CLOSING, LATER = window(-120, 240), window(-60, 10), window(120, 180)
        RP = [P.node(P.pt(1000, 30), amenity='cafe', name='Cafe Open', opening_hours=OPEN),
              P.node(P.pt(3000, 1500), shop='convenience', name='Shop Closing', opening_hours=CLOSING),
              P.node(P.pt(2000, -40), amenity='cafe', name='Cafe Later', opening_hours=LATER),
              P.node(P.pt(2500, 40), amenity='cafe', name='Cafe Weird', opening_hours='sunrise-sunset')]
        INS = P.INS[:2] + [P.node(P.CAFE, amenity='cafe', name='Кафе Позже', opening_hours=LATER), P.INS[3]]
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(P.LAT0, P.LON0))
        await ctx.route('**/v1/forecast**', P.forecast)
        await pg.evaluate(P.FIX, [INS, P.RA, RP, P.ROUTE[60]])
        await pg.evaluate("setMode('bike', true); lsSet('gkey', '')")
        await pg.evaluate(f"Nav.set({{ name: 'Часы', coords: {json.dumps(P.ROUTE)}, noAsk: true }})")
        await pg.evaluate("showRiderPOIs()"); await pg.wait_for_function("RPOI.list.length === 4", timeout=8000)
        async def pop(name):
            await pg.evaluate(f"(() => {{ const i = RPOI.list.findIndex(x => x.name === {json.dumps(name)}); RPOI.layer.getLayers()[i].openPopup(); }})()"); await pg.wait_for_timeout(250)
            return await pg.evaluate("(() => { const e = document.querySelector('.leaflet-popup .pop'); return { t: e.textContent, ok: !!e.querySelector('.ohok'), no: !!e.querySelector('.ohno') }; })()")
        a = await pop('Cafe Open')
        check('open for hours: «открыто», green, the hours shown', 'открыто' in a['t'] and 'к вашему приезду' not in a['t'] and a['ok'] and OPEN in a['t'], a)
        c = await pop('Shop Closing')
        check('closes in 10 min, 6 km away: «открыто до …» and «к вашему приезду (≈ …) — закрыто», red', 'открыто до' in c['t'] and 'к вашему приезду' in c['t'] and '— закрыто' in c['t'] and c['no'], c)
        d = await pop('Cafe Later')
        check('opens in 2 h: «закрыто · откроется в …»', 'закрыто · откроется в' in d['t'] and d['no'], d)
        w = await pop('Cafe Weird')
        check('hours not understood: only the hours, no claim', 'открыто' not in w['t'] and 'закрыто' not in w['t'] and 'sunrise-sunset' in w['t'], w)
        await pg.evaluate("map.closePopup(); riderPOIsClear(); Nav.stop()")
        # ---------- «Перед выездом»: the café on the way is closed when you get there; Shabbat
        await pg.evaluate("S.preRide = true; saveS(); window.shabbatAt = () => true")
        await pg.evaluate(f"Nav.set({{ name: 'Шабат', coords: {json.dumps(P.ROUTE)} }})")
        await pg.wait_for_function(P.SHOWN, timeout=8000)
        await pg.wait_for_function("document.getElementById('pre-stops').textContent.includes('Кафе Позже')", timeout=10000)
        st = await pg.evaluate("(() => { const r = [...document.querySelectorAll('#pre-stops .prstop')].find(e => e.textContent.includes('Кафе Позже')); return { t: r.textContent, no: !!r.querySelector('small.ohno') }; })()")
        check('«Перед выездом»: the café 10 min away says «закрыто · откроется в …», red (closed when you get there)', 'закрыто · откроется в' in st['t'] and st['no'], st)
        tx = await pg.evaluate(P.PL)
        check('Shabbat during the ride → «🕯 Шабат: многие кафе и магазины по пути закрыты»', '🕯' in tx and 'Шабат: многие кафе и магазины по пути закрыты' in tx, tx[:120])
        await pg.click('#pre-go'); await pg.evaluate("Nav.stop(); window.shabbatAt = () => false")
        await pg.evaluate(f"Nav.set({{ name: 'Будни', coords: {json.dumps(P.ROUTE)} }})"); await pg.wait_for_function(P.SHOWN, timeout=8000); await pg.wait_for_timeout(600)
        check('not Shabbat → no such line', 'Шабат' not in await pg.evaluate(P.PL))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        # ---------- he / en
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, geo=(P.LAT0, P.LON0))
            await pg.evaluate(P.FIX, [INS, P.RA, RP, P.ROUTE[60]])
            await pg.evaluate(f"setMode('bike', true); lsSet('gkey', ''); Nav.set({{ name: 'T', coords: {json.dumps(P.ROUTE)}, noAsk: true }}); showRiderPOIs()")
            await pg.wait_for_function("RPOI.list.length === 4", timeout=8000)
            await pg.evaluate("RPOI.layer.getLayers()[RPOI.list.findIndex(x => x.name === 'Shop Closing')].openPopup()"); await pg.wait_for_timeout(400)
            t = await pg.evaluate("document.querySelector('.leaflet-popup .pop').textContent")
            want = ('כשתגיעו' if lang == 'he' else 'when you get there')
            cyr = [w for w in t.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: the hours in words translated', want in t and not cyr, (t[:160], cyr[:4]))
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
