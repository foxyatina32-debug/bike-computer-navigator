# v131: route variants compared in words (like Google's alternatives with their trade-offs). In «Из точки в точку» each
# variant says how it differs from the chosen one — «на 6 мин дольше, зато на 180 м меньше подъёма и больше асфальта:
# 83% против 30%» — and gets a badge when it is clearly the best in something (fastest, least climb, most asphalt /
# trails). Asphalt is neutral for an off-road ride, trails count as a plus there. ru / he / en. Run: python3 tests/abwords.py
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
def line(n, e0): return [[32.09 + k * 0.0009, 34.88 + e0, 20] for k in range(n)]
VARS = [  # A: mixed, B: longer on asphalt with little climb, C: short but mostly trails
    {'coords': line(100, 0), 'distance': 10000, 'ascent': 300, 'mix': [3000, 5000, 2000], 'prof': 'A'},
    {'coords': line(120, 0.01), 'distance': 12000, 'ascent': 120, 'mix': [10000, 1500, 500], 'prof': 'B'},
    {'coords': line(95, -0.01), 'distance': 9500, 'ascent': 320, 'mix': [1000, 3000, 5500], 'prof': 'C'},
]
SHOW = "([vars, sel, terr]) => { openAB(); AB.terr = terr; AB.vars = vars; AB.sel = sel; abShow(); }"
ROWS = "[...document.querySelectorAll('#ab-res .abv')].map(e => ({ bdg: (e.querySelector('.bdg') || {}).textContent || '', cmp: (e.querySelector('.cmp') || {}).textContent || '' }))"

async def main():
    url = serve(9051); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await pg.evaluate("setMode('bike', true)")
        await pg.evaluate(SHOW, [VARS, 0, 'mixed']); await pg.wait_for_timeout(300)
        r = await pg.evaluate(ROWS)
        check('three variants, the chosen one has no comparison line', len(r) == 3 and r[0]['cmp'] == '', r)
        check('badges: B — least climb and most asphalt, C — most trails', '⛰ меньше подъёма' in r[1]['bdg'] and '🛣 больше асфальта' in r[1]['bdg'] and '🌲 больше троп' in r[2]['bdg'], [x['bdg'] for x in r])
        check('B against A: «на 180 м меньше подъёма», «больше асфальта: 83% против 30%»', r[1]['cmp'].startswith('По сравнению с выбранным: ') and 'на 180 м меньше подъёма' in r[1]['cmp'] and 'больше асфальта: 83% против 30%' in r[1]['cmp'], r[1]['cmp'])
        check('C against A: worse first, then «зато» (mixed terrain: trails told plainly)', 'больше троп: 58% против 20%' in r[2]['cmp'] and 'меньше асфальта: 11% против 30%' in r[2]['cmp'], r[2]['cmp'])
        t = await pg.evaluate("[0, 1, 2].map(i => Math.round((AB.vars[i].gdur || rideTime(AB.vars[i], RO.bike, 'bike')) / 60))")
        dt = t[1] - t[0]
        want = (f'на {abs(dt)} мин дольше' if dt > 0 else f'на {abs(dt)} мин быстрее') if abs(dt) >= 3 else ''
        check('time difference in words when it is ≥ 3 min', want in r[1]['cmp'], (t, r[1]['cmp']))
        # tap another variant: the words are now against it
        await pg.click('#ab-res .abv[data-v="1"]'); await pg.wait_for_timeout(300)
        r = await pg.evaluate(ROWS)
        check('tap B: B has no comparison, A is told against B («на 180 м больше подъёма»)', r[1]['cmp'] == '' and 'на 180 м больше подъёма' in r[0]['cmp'], [x['cmp'] for x in r])
        # off-road ride: trails are the plus, asphalt neutral
        await pg.evaluate(SHOW, [VARS, 0, 'off']); await pg.wait_for_timeout(300)
        r = await pg.evaluate(ROWS)
        c = r[2]['cmp']
        check('off-road: «зато … больше троп», asphalt only mentioned', ', зато ' in c and c.index('зато') < c.index('больше троп') and 'меньше асфальта' in c.split('зато')[-1], c)
        # almost the same
        same = [VARS[0], {**VARS[0], 'coords': line(100, 0.002), 'distance': 10100, 'ascent': 310}]
        await pg.evaluate(SHOW, [same, 0, 'mixed']); await pg.wait_for_timeout(300)
        r = await pg.evaluate(ROWS)
        check('a near twin: «Почти как выбранный», no badges', r[1]['cmp'] == 'Почти как выбранный' and r[0]['bdg'] == '' and r[1]['bdg'] == '', r)
        check('one variant: no comparison at all', (await pg.evaluate(SHOW, [VARS[:1], 0, 'mixed']) or True) and await pg.evaluate("!document.querySelector('#ab-res .cmp, #ab-res .bdg')"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            await pg.evaluate("setMode('bike', true)")
            await pg.evaluate(SHOW, [VARS, 0, 'mixed']); await pg.wait_for_timeout(500)
            txt = await pg.evaluate("[...document.querySelectorAll('#ab-res .cmp, #ab-res .bdg')].map(e => e.textContent).join(' | ')")
            cyr = [w for w in txt.split() if any('Ѐ' <= ch <= 'ӿ' for ch in w)]
            check(f'{lang}: the comparison translated', txt and not cyr, (txt[:220], cyr[:5]))
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
