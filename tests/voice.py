# Voice commands: phrase parsing (ru / he / en) and the whole flow mic → route → navigation.
# The browser's speech recognizer is replaced by a fake that "hears" window.__sayNext. Run: python3 tests/voice.py
import asyncio, sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''))

FAKE_SR = '''window.__sayNext = ''; window.__sayQ = []; window.__srStarts = 0;
class FakeSR { start() { window.__srStarts++; setTimeout(() => { const t = window.__sayQ.length ? window.__sayQ.shift() : window.__sayNext; window.__sayNext = '';
  if (!t) { this.onerror && this.onerror({ error: 'no-speech' }); this.onend && this.onend(); return; }
  const res = [{ transcript: t, confidence: .9 }]; res.isFinal = true; this.onresult({ resultIndex: 0, results: [res] }); this.onend && this.onend(); }, 150); }
  abort() {} stop() {} }
window.webkitSpeechRecognition = window.SpeechRecognition = FakeSR;'''
NO_SR = 'window.SpeechRecognition = window.webkitSpeechRecognition = undefined;'

PARSE = [
    ('Поехали домой.', {'kind': 'home'}), ('домой', {'kind': 'home'}), ('Веди меня домой пожалуйста', {'kind': 'home'}),
    ('Запомни дом', {'kind': 'sethome'}), ('дом здесь', {'kind': 'sethome'}),
    ('запомни дом улица Герцль 10 Петах-Тиква', {'kind': 'sethome', 'q': 'улица герцль 10 петах-тиква'}),
    ('Поехали 31,95 34,88', {'kind': 'point', 'll': [31.95, 34.88]}), ('поехали 31.95, 34.88', {'kind': 'point', 'll': [31.95, 34.88]}),
    ('поехали 31 точка 95 34 точка 88', {'kind': 'point', 'll': [31.95, 34.88]}), ('поехали 34.88 31.95', {'kind': 'point', 'll': [31.95, 34.88]}),
    ('поехали 31 95 34 88', {'kind': 'point', 'll': [31.95, 34.88]}),
    ('Поехали в Модиин', {'kind': 'place', 'q': 'модиин'}), ('отвези меня на пляж Гордон', {'kind': 'place', 'q': 'пляж гордон'}),
    ('построй маршрут до парка Яркон', {'kind': 'place', 'q': 'парка яркон'}), ('Бен Шемен', {'kind': 'place', 'q': 'бен шемен'}),
    ('улица Герцль 12', {'kind': 'place', 'q': 'улица герцль 12'}),
    ('סע הביתה', {'kind': 'home'}), ('זכור בית', {'kind': 'sethome'}), ('סע למודיעין', {'kind': 'place', 'q': 'למודיעין'}),
    ('Go home', {'kind': 'home'}), ('take me to Yarkon Park', {'kind': 'place', 'q': 'yarkon park'}), ('remember home', {'kind': 'sethome'}),
    ('', None),
]

async def status(pg): return await pg.evaluate("document.getElementById('vc-st').textContent")
async def say(pg, text, wait_for):
    await pg.evaluate(f"window.__sayNext = {text!r}")
    await pg.click('#vc-mic')
    await pg.wait_for_function(wait_for, timeout=15000)

async def main():
    url = serve(8786); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await ctx.add_init_script(FAKE_SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(800)
        # 1. parsing
        bad = []
        for txt, want in PARSE:
            got = await pg.evaluate('t => Voice.parse(t)', txt)
            if got != want: bad.append((txt, got, want))
        check(f'phrases understood ({len(PARSE)} ru/he/en)', not bad, bad)
        # 2. mic button on the map, panel opens and listens
        vis = await pg.evaluate("(() => { const r = document.getElementById('t-mic').getBoundingClientRect(), g = document.getElementById('t-gpx').getBoundingClientRect(); return r.width > 0 && r.top >= g.bottom && r.bottom < innerHeight && getComputedStyle(document.getElementById('t-mic')).visibility === 'visible'; })()")
        check('mic button under «Маршрут», visible', vis)
        await pg.evaluate("window.__sayNext = 'поехали домой'"); await pg.click('#t-mic')
        await pg.wait_for_function("document.getElementById('vc-st').textContent.includes('не задан')", timeout=10000)
        check('«поехали домой» without a home → asks to set it', await pg.evaluate("Nav.route == null"), await status(pg))
        # 3. set home by address (Nominatim mock → Tel Aviv), then go home
        await say(pg, 'запомни дом улица Дизенгоф 50 Тель-Авив', "document.getElementById('vc-st').textContent.includes('Дом запомнен')")
        h = await pg.evaluate("lsGet('home', null)")
        check('«запомни дом <адрес>» saves home', h and abs(h['ll'][0] - 32.0853) < 1e-4 and abs(h['ll'][1] - 34.7818) < 1e-4, h)
        n0 = sum('brouter.de' in u for u in m.calls)
        await say(pg, 'поехали домой', "Nav.route && Nav.route.name === 'Домой'")
        end = await pg.evaluate("Nav.route.coords[Nav.route.coords.length - 1]"); start = await pg.evaluate("Nav.route.coords[0]")
        check('«поехали домой» → route from GPS to home, navigation on', abs(end[0] - 32.0853) < 1e-4 and abs(start[0] - 32.09) < 1e-3 and sum('brouter.de' in u for u in m.calls) > n0, f'{start[:2]} → {end[:2]}; {await status(pg)}')
        check('navigation started without the «how to start» question', await pg.evaluate("document.getElementById('ask-start').hidden && document.getElementById('ask-join').hidden"))
        # 4. coordinates
        await pg.click('#t-mic'); await pg.wait_for_timeout(200)
        if await pg.evaluate("document.getElementById('vc').hidden"): await pg.click('#t-mic')
        await say(pg, 'поехали 32,05 34,85', "Nav.route && Nav.route.name.startsWith('32.05000')")
        end = await pg.evaluate("Nav.route.coords[Nav.route.coords.length - 1]")
        check('«поехали 32,05 34,85» → route to the point', abs(end[0] - 32.05) < 1e-6 and abs(end[1] - 34.85) < 1e-6, end[:2])
        # 5. a place by name
        if await pg.evaluate("document.getElementById('vc').hidden"): await pg.click('#t-mic')
        await say(pg, 'поехали в Тель-Авив', "Nav.route && Nav.route.name === 'Тель-Авив'")
        q = [u for u in m.calls if 'nominatim' in u and 'search' in u][-1]
        check('«поехали в Тель-Авив» → Nominatim search, route, navigation', 'q=%D1%82%D0%B5%D0%BB%D1%8C' in q and 'countrycodes=il' in q, q[:140])
        # 6. typed command (keyboard dictation path) and «already there»
        if await pg.evaluate("document.getElementById('vc').hidden"): await pg.click('#t-mic')
        await pg.fill('#vc-q', 'запомни дом'); await pg.click('#vc-go')
        await pg.wait_for_function("document.getElementById('vc-st').textContent.includes('Дом запомнен')", timeout=10000)
        await pg.fill('#vc-q', 'домой'); await pg.click('#vc-go')
        await pg.wait_for_function("document.getElementById('vc-st').textContent.includes('уже на месте')", timeout=10000)
        check('typed «запомни дом» here, then «домой» → «вы уже на месте»', True)
        # 7. not understood / nothing heard
        await say(pg, '', "document.getElementById('vc-st').textContent.includes('Ничего не услышал')")
        check('silence → «ничего не услышал»', True)
        await pg.click('#vc-x'); await pg.wait_for_timeout(200)
        check('✕ closes the panel', await pg.evaluate("document.getElementById('vc').hidden && !document.getElementById('t-mic').classList.contains('on')"))
        check('no JS errors (ru)', not log['errors'], log['errors'])
        await b.close()

        # 8. «Привет, Вело»
        WAKE_YES = ['привет вело', 'Привет, Вело, поехали домой', 'хей вело', 'эй, вело', 'окей вело', 'Hey Velo go home', 'היי ולו סע הביתה']
        WAKE_NO = ['привет', 'поехали домой', 'привет велосипед', 'велосипед', 'хей']
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await ctx.add_init_script(FAKE_SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(800)
        r = await pg.evaluate('([y, n]) => [y.filter(t => !Voice.wakeRx.test(t.toLowerCase())), n.filter(t => Voice.wakeRx.test(t.toLowerCase()))]', [WAKE_YES, WAKE_NO])
        check('wake phrase: «Привет / Хей / Эй / Окей, Вело» yes, other speech no', r == [[], []], r)
        idle = await pg.evaluate("Voice.waking")
        await pg.evaluate("lsSet('home', {ll: [32.0853, 34.7818], name: 'Тель-Авив'}); document.getElementById('s-wakeword').click()")
        await pg.wait_for_function("Voice.waking && document.getElementById('t-mic').classList.contains('wake')", timeout=5000)
        check('off by default; switch in Profile starts listening (green dot)', idle is False and await pg.evaluate("S.wakeword === true && lsGet('settings', {}) !== null"))
        await pg.evaluate("window.__sayQ = ['Привет, Вело, поехали домой']")
        await pg.wait_for_function("Nav.route && Nav.route.name === 'Домой'", timeout=10000)
        check('«Привет, Вело, поехали домой» in one phrase → navigation home', True, await status(pg))
        await pg.wait_for_function("document.getElementById('vc').hidden && Voice.waking", timeout=10000)
        check('panel closes by itself and listening resumes', True)
        await pg.evaluate("window.__sayQ = ['привет вело', 'поехали 32,05 34,85']")
        await pg.wait_for_function("Nav.route && Nav.route.name.startsWith('32.05000')", timeout=12000)
        check('«Привет, Вело» → «Слушаю» → «поехали 32,05 34,85» → route', True, await status(pg))
        await pg.wait_for_function("document.getElementById('vc').hidden && Voice.waking", timeout=10000)
        await pg.evaluate("window.__sayQ = ['поехали в Тель-Авив', 'привет как дела']"); await pg.wait_for_timeout(1500)
        check('commands without «Привет, Вело» are ignored', await pg.evaluate("Nav.route.name.startsWith('32.05000') && document.getElementById('vc').hidden"))
        await pg.evaluate("document.getElementById('s-wakeword').click()"); await pg.wait_for_timeout(600)
        n = await pg.evaluate("window.__srStarts"); await pg.wait_for_timeout(1500)
        check('switch off → stops listening', await pg.evaluate(f"!Voice.waking && window.__srStarts === {n} && !document.getElementById('t-mic').classList.contains('wake')"))
        check('no JS errors (wake)', not log['errors'], log['errors'])
        await b.close()

        # 9. Russian street names: Hebrew spelling, suggestions while typing, «🏠» sets home
        from urllib.parse import unquote
        def photon(u):
            q = unquote(re.search(r'q=([^&]+)', u).group(1)).replace('+', ' ')
            if 'שפרינצק' in q:
                return {'features': [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [34.8861, 32.0927]}, 'properties': {'street': 'שפרינצק', 'housenumber': '16', 'city': 'פתח תקווה', 'state': 'מחוז המרכז'}},
                                     {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [34.8890, 32.0940]}, 'properties': {'name': 'שפרינצק', 'city': 'פתח תקווה'}}]}
            return {'features': []}
        m.photon = photon
        m.nominatim = lambda u: []   # Nominatim does not know Russian street names
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        he = await pg.evaluate("ruAddrHe('улица Шпринцак 16 Петах-Тиква')")
        check('«улица Шпринцак 16 Петах-Тиква» → «שפרינצק 16 פתח תקווה»', he == ['שפרינצק 16 פתח תקווה'], he)
        await pg.click('#t-mic'); await pg.wait_for_timeout(300)
        await pg.fill('#vc-q', 'запомни дом улица Шпринцак 16 Петах-Тиква')
        await pg.wait_for_function("document.querySelectorAll('#vc-sug .vc-s').length > 0", timeout=8000)
        first = await pg.evaluate("document.querySelector('#vc-sug .vc-s .t').textContent + ' | ' + document.querySelector('#vc-sug .vc-s .s').textContent")
        check('suggestions appear while typing a Russian address', 'שפרינצק 16' in first and 'פתח תקווה' in first, first)
        await pg.click('#vc-sug [data-home="0"]'); await pg.wait_for_timeout(300)
        h = await pg.evaluate("lsGet('home', null)")
        check('🏠 on a suggestion saves it as home', h and abs(h['ll'][0] - 32.0927) < 1e-6 and 'שפרינצק 16' in h['name'], h)
        await pg.fill('#vc-q', 'поехали на Шпринцак 16 Петах-Тиква')
        await pg.wait_for_function("document.querySelectorAll('#vc-sug .vc-s').length > 0", timeout=8000)
        await pg.click('#vc-sug [data-go="0"]')
        await pg.wait_for_function("Nav.route && Nav.route.name.includes('שפרינצק')", timeout=10000)
        end = await pg.evaluate("Nav.route.coords[Nav.route.coords.length - 1]")
        check('➜ on a suggestion → route there', abs(end[0] - 32.0927) < 1e-6, end[:2])
        await pg.evaluate("lsSet('home', null)")
        if await pg.evaluate("document.getElementById('vc').hidden"): await pg.click('#t-mic')
        await pg.fill('#vc-q', 'запомни дом Шпринцак 16, Петах-Тиква'); await pg.click('#vc-go')
        await pg.wait_for_function("document.getElementById('vc-st').textContent.includes('Дом запомнен')", timeout=10000)
        h = await pg.evaluate("lsGet('home', null)")
        check('typed / spoken «запомни дом Шпринцак 16…» finds it too', h and abs(h['ll'][0] - 32.0927) < 1e-6, h)
        await pg.click('#vc-x')
        await pg.evaluate("openAB()"); await pg.fill('#ab-qb', 'Шпринцак 16 Петах-Тиква')
        await pg.wait_for_function("document.querySelectorAll('#ab-rb [data-i]').length > 0", timeout=8000)
        check('«Из точки в точку» search finds the Russian address too', 'שפרינצק' in await pg.evaluate("document.querySelector('#ab-rb [data-i] .t').textContent"))
        # Hebrew addresses in the Russian app
        await pg.evaluate("abHide(); showTab('rec'); lsSet('home', null)"); await pg.wait_for_timeout(400); await pg.click('#t-mic'); await pg.wait_for_timeout(300)
        await pg.fill('#vc-q', 'שפרינצק 16 פתח תקווה')
        await pg.wait_for_function("document.querySelectorAll('#vc-sug .vc-s').length > 0", timeout=8000)
        rtl = await pg.evaluate("document.getElementById('vc-q').matches(':dir(rtl)')")
        check('Hebrew typed in the Russian app: suggestions, field right-to-left', rtl and 'שפרינצק 16' in await pg.evaluate("document.querySelector('#vc-sug .vc-s .t').textContent"), rtl)
        await pg.fill('#vc-q', 'זכור בית שפרינצק 16 פתח תקווה'); await pg.click('#vc-go')
        await pg.wait_for_function("document.getElementById('vc-st').textContent.includes('Дом запомнен')", timeout=10000)
        h = await pg.evaluate("lsGet('home', null)")
        check('«זכור בית שפרינצק 16 פתח תקווה» → home saved', h and abs(h['ll'][0] - 32.0927) < 1e-6, h)
        await pg.fill('#vc-q', 'סע לשפרינצק 16 פתח תקווה'); await pg.click('#vc-go')
        await pg.wait_for_function("Nav.route && Nav.route.name.includes('שפרינצק')", timeout=10000)
        check('«סע לשפרינצק 16 פתח תקווה» → prefix ל dropped, route there', abs((await pg.evaluate("Nav.route.coords[Nav.route.coords.length - 1]"))[0] - 32.0927) < 1e-6)
        await pg.click('#vc-x')
        await pg.evaluate("openAB()"); await pg.fill('#ab-qa', 'שפרינצק 16 פתח תקווה')
        await pg.wait_for_function("document.querySelectorAll('#ab-ra [data-i]').length > 0", timeout=8000)
        check('«Из точки в точку»: Hebrew address found, field right-to-left', await pg.evaluate("document.getElementById('ab-qa').matches(':dir(rtl)') && document.querySelector('#ab-ra [data-i] .t').textContent.includes('שפרינצק')"))
        check('no JS errors (addresses)', not log['errors'], log['errors'])
        await b.close()
        m.photon = None; m.nominatim = None

        # 10. Hebrew and English: panel translated, fits the screen; no recognizer → keyboard hint
        for lang, loc, home_cmd in (('he', 'he-IL', 'סע הביתה'), ('en', 'en-US', 'go home')):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, viewport=(320, 568), locale=loc)
            await ctx.add_init_script(NO_SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(800)
            await pg.click('#t-mic'); await pg.wait_for_timeout(300)
            info = await pg.evaluate("""(() => { const v = document.getElementById('vc'), r = v.getBoundingClientRect();
              const cyr = [...v.querySelectorAll('*')].flatMap(e => [e.textContent, e.placeholder || '', e.getAttribute('aria-label') || '']).filter(t => /[А-Яа-яЁё]/.test(t));
              return { fits: r.left >= 0 && r.right <= innerWidth + 0.5 && r.bottom <= innerHeight, cyr, st: document.getElementById('vc-st').textContent, sup: Voice.supported }; })()""")
            check(f'[{lang}] panel fits iPhone SE, no Russian text', info['fits'] and not info['cyr'], info)
            check(f'[{lang}] without a recognizer → points to keyboard dictation', not info['sup'] and '🎤' in info['st'], info['st'])
            await pg.fill('#vc-q', home_cmd); await pg.click('#vc-go')
            await pg.wait_for_function("document.getElementById('vc-st').classList.contains('err')", timeout=10000)
            st = await status(pg)
            check(f'[{lang}] «{home_cmd}» understood (asks to set home), translated', not any('Ѐ' <= ch <= 'ӿ' for ch in st), st)
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed')
    sys.exit(0 if all(RES) else 1)

asyncio.run(main())
