# v131: questions by voice on the way (like asking Maps, without AI or keys): «где вода?» (along the route ahead, or
# around you with the side of the world; then «заехать» adds it as a stop), «сколько до финиша?» (distance, time,
# arrival), «когда подъём?» (the next climb from the route's heights: how far, how long, how high, the grade; «вы на
# подъёме» while on it), «успею до заката?», «что впереди?» (the next turn with its landmark, the next road feature).
# A destination («поехали …») is still a destination. Answers are spoken and shown. ru / he / en. Run: python3 tests/voiceask.py
import asyncio, sys, os, json, math, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
LAT0, LON0 = 32.09, 34.88
M = 1 / 110540; KX = 1 / (111320 * math.cos(LAT0 * math.pi / 180))
def pt(n, e, h=None): return [round(LAT0 + n * M, 7), round(LON0 + e * KX, 7)] + ([h] if h is not None else [])
def alt(d): return 50 if d < 1000 else 50 + (d - 1000) * 0.1 if d < 2000 else 150
# 2.5 km north (flat 1 km, then 1 km up at 10 %, then flat), a right turn, 500 m east
ROUTE = [pt(n, 0, alt(n)) for n in range(0, 2501, 25)] + [pt(2500, e, 150) for e in range(25, 501, 25)]
PARSE = {
    'ru': {'где вода': 'water', 'где ближайшая вода': 'water', 'сколько до воды': 'water', 'сколько до финиша': 'finish', 'сколько осталось': 'finish', 'когда приедем': 'finish',
           'когда следующий подъём': 'climb', 'сколько до подъёма': 'climb', 'успею до заката': 'sunset', 'когда закат': 'sunset', 'что впереди': 'ahead', 'заехать': 'addstop'},
    'en': {'where is the nearest water': 'water', 'how far to the finish': 'finish', 'how much longer': 'finish', 'when is the next climb': 'climb', 'will I make it before sunset': 'sunset', "what's ahead": 'ahead', 'stop there': 'addstop'},
    'he': {'איפה יש מים': 'water', 'כמה נשאר': 'finish', 'מתי נגיע': 'finish', 'מתי העלייה הבאה': 'climb', 'מתי השקיעה': 'sunset', 'מה לפנינו': 'ahead', 'לעצור שם': 'addstop'},
}
FIX = """(water) => {
  window.__said = []; try { speechSynthesis.speak = u => window.__said.push(u.text); speechSynthesis.cancel = () => {}; } catch {}
  window.overpass = async q => ({ elements: q.startsWith('/*rpoi*/') ? water : [] });
}"""
ASK = "async q => { window.__said = []; Voice.open(); await Voice.run(q); return { said: window.__said.slice(-1)[0] || '', st: document.getElementById('vc-st').textContent }; }"
AT = "p => { Nav.lost = false; Nav.joined = true; Nav.progress = p; }"

async def main():
    url = serve(9057); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, geo=(LAT0, LON0))
        bad = [(q, r) for q, w in PARSE['ru'].items() for r in [await pg.evaluate("q => Voice.parse(q)", q)] if not r or r.get('kind') != 'ask' or r.get('what') != w]
        check('ru: the questions are understood (water, finish, climb, sunset, ahead, «заехать»)', not bad, bad)
        k = await pg.evaluate("['поехали в Модиин', 'поехали домой', 'стоп навигация', 'поехали на родник Эйн Хемед'].map(q => (Voice.parse(q) || {}).kind)")
        check('destinations and commands stay as they were («поехали … родник» is a place)', k == ['place', 'home', 'stopnav', 'place'], k)
        await pg.evaluate(FIX, [{'type': 'node', 'lat': pt(1000, 60)[0], 'lon': pt(1000, 60)[1], 'tags': {'amenity': 'drinking_water'}}])
        r = await pg.evaluate(ASK, 'сколько до финиша')
        check('no route: «Навигация не идёт»', 'Навигация не идёт' in r['said'], r)
        await pg.evaluate(f"Nav.set({{ name: 'Подъём', coords: {json.dumps(ROUTE)}, noAsk: true }})")
        await pg.evaluate(AT, 200)
        r = await pg.evaluate(ASK, 'сколько до финиша')
        check('«сколько до финиша»: «До финиша 2,8 километра, примерно … минут, прибытие в …» (spoken and shown)', re.match(r'До финиша 2,8 километра, примерно \d+ минут\S*, прибытие в \d\d:\d\d$', r['said']) and r['st'] == r['said'], r)
        r = await pg.evaluate(ASK, 'когда следующий подъём')
        mm = re.match(r'Подъём через (\d+) метров: (\S+) километр\S*, (\d+) метров вверх, в среднем (\d+)%$', r['said'])
        check('«когда подъём»: «Подъём через ~800 метров: ~1 километр, ~100 метров вверх, в среднем ~10%»', mm and 700 <= int(mm[1]) <= 850 and 85 <= int(mm[3]) <= 105 and 8 <= int(mm[4]) <= 12, r['said'])
        await pg.evaluate(AT, 1400)
        r = await pg.evaluate(ASK, 'сколько до подъёма')
        check('on the climb: «Вы на подъёме: ещё … и … метров вверх»', r['said'].startswith('Вы на подъёме: ещё ') and 'вверх' in r['said'], r['said'])
        await pg.evaluate(AT, 2200)
        r = await pg.evaluate(ASK, 'когда подъём')
        check('after the last climb: «Больших подъёмов до финиша нет»', r['said'] == 'Больших подъёмов до финиша нет', r['said'])
        await pg.evaluate(AT, 200)
        await pg.evaluate("window.sunTimes = () => ({ rise: new Date(Date.now() - 6 * 3600000), set: new Date(Date.now() + 15 * 60000) })")
        r = await pg.evaluate(ASK, 'успею до заката')
        check('sunset in 15 min, ~20 min to go: «не успеваете … Включите фонари»', '— не успеваете: приедете примерно через' in r['said'] and 'Включите фонари' in r['said'], r['said'])
        await pg.evaluate("window.sunTimes = () => ({ rise: new Date(Date.now() - 6 * 3600000), set: new Date(Date.now() + 90 * 60000) })")
        r = await pg.evaluate(ASK, 'успею до заката')
        check('sunset in 1.5 h: «Успеваете: прибытие около …, запас …»', re.search(r'Успеваете: прибытие около \d\d:\d\d, запас 1 час', r['said']), r['said'])
        await pg.evaluate("Nav.route.ahead = [{ kind: 'steps', d: 1500 }, ...Nav.route.ahead.filter(h => h.kind !== 'steps')]")
        r = await pg.evaluate(ASK, 'что впереди')
        check('«что впереди»: the next turn and the next road feature', r['said'].startswith('Через 2,3 километра поверните направо') and 'через 1,3 километра лестница' in r['said'], r['said'])
        r = await pg.evaluate(ASK, 'где вода')
        check('«где вода»: along the route ahead, how far off, and «скажите «заехать»»', r['said'].startswith('Вода через 800 метров по маршруту, 50 метров в стороне от маршрута') and 'заехать' in r['said'], r['said'])
        r = await pg.evaluate(ASK, 'заехать')
        n = await pg.evaluate("Nav.wpts.length")
        check('«заехать» → the water becomes a stop on the route', r['said'] == 'Остановка добавлена в маршрут' and n == 1, (r['said'], n))
        await pg.evaluate("Nav.stop()")
        await pg.evaluate(FIX, [{'type': 'node', 'lat': pt(250, 250)[0], 'lon': pt(250, 250)[1], 'tags': {'amenity': 'drinking_water', 'name': 'Фонтанчик'}}])
        r = await pg.evaluate(ASK, 'где ближайшая вода')
        check('no route: «Ближайшая вода — 350 метров, на северо-востоке — Фонтанчик»', r['said'] == 'Ближайшая вода — 350 метров, на северо-востоке — Фонтанчик', r['said'])
        r = await pg.evaluate(ASK, 'заехать')
        check('«заехать» without a route → asks first', 'Сначала спросите' in r['said'], r['said'])
        await pg.evaluate("window.sunTimes = () => ({ rise: new Date(Date.now() - 6 * 3600000), set: new Date(Date.now() + 60 * 60000) })")
        r = await pg.evaluate(ASK, 'когда закат')
        check('sunset without a route: «Закат в …, через 1 час»', re.match(r'Закат в \d\d:\d\d, через 1 час$', r['said']), r['said'])
        hint = await pg.evaluate("document.getElementById('vc-ex').textContent")
        check('the voice panel suggests the questions', '«где вода?»' in hint and '«сколько до финиша?»' in hint, hint)
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('en', 'he'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, geo=(LAT0, LON0))
            bad = [(q, r) for q, w in PARSE[lang].items() for r in [await pg.evaluate("q => Voice.parse(q)", q)] if not r or r.get('kind') != 'ask' or r.get('what') != w]
            check(f'{lang}: the questions are understood', not bad, bad)
            await pg.evaluate(FIX, [{'type': 'node', 'lat': pt(1000, 60)[0], 'lon': pt(1000, 60)[1], 'tags': {'amenity': 'drinking_water'}}])
            await pg.evaluate(f"Nav.set({{ name: 'Climb', coords: {json.dumps(ROUTE)}, noAsk: true }})"); await pg.evaluate(AT, 200)
            out = []
            for q in [k for k, w in PARSE[lang].items() if w in ('finish', 'climb', 'ahead', 'water')]:
                out.append((await pg.evaluate(ASK, q))['said'])
            cyr = [s for s in out if any('Ѐ' <= ch <= 'ӿ' for ch in s)]
            want = ('to the finish' if lang == 'en' else 'עד הסיום')
            check(f'{lang}: the answers spoken in the language', any(want in s for s in out) and not cyr and all(out), (out, cyr))
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
