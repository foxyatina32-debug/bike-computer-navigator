# v106: a new destination by voice during a ride — 🎤 stays on screen in «В поездке» mode while the other extra buttons
# hide, and the spoken place replaces the current route; the yellow «→» in the voice panel: while the phone is still
# listening it takes what was heard so far, while a search runs it says so, with nothing to search it asks for an address.
import asyncio, sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
VIS = "id => { const e = document.getElementById(id); return !!e && !e.hidden && getComputedStyle(e).opacity !== '0' && getComputedStyle(e).pointerEvents !== 'none'; }"
# Recognizer stub: window.__mode = 'final' answers the phrase at once; 'slow' only sends it as an interim result and keeps listening.
SR = '''window.__say = ''; window.__mode = 'final'; window.__starts = 0;
class SSR { start() { window.__starts++; setTimeout(() => { if (this._ab) return; this.onaudiostart && this.onaudiostart();
      const r = Object.assign([{ transcript: window.__say }], { isFinal: window.__mode === 'final' });
      this.onresult && this.onresult({ resultIndex: 0, results: [r] }); if (window.__mode === 'final') this.onend && this.onend(); }, 250); }
  abort() { this._ab = true; setTimeout(() => this.onend && this.onend(), 30); } stop() { this.abort(); } }
window.webkitSpeechRecognition = window.SpeechRecognition = SSR;'''

async def main():
    url = serve(8841); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m)
        await ctx.add_init_script(SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(800)
        await pg.evaluate("Nav.set({ name: 'Старый маршрут', noAsk: true, coords: [[32.09, 34.88], [32.10, 34.88], [32.11, 34.89]] }); showTab('rec')")
        # riding: recording, moving — «В поездке» hides the extra buttons
        await pg.evaluate("window.__mv = setInterval(() => { GPS.fix = Object.assign({}, GPS.fix || {lat: 32.09, lon: 34.88, acc: 5}, {spd: 6, t: Date.now()}); }, 300); Ride.status = 'rec'; Ride.autoPaused = false")
        await pg.wait_for_timeout(6500)
        st = await pg.evaluate(f"(() => {{ const v = {VIS}; return {{on: document.body.classList.contains('ridemode'), mic: v('t-mic'), gpx: v('t-gpx'), layers: v('t-layers')}}; }})()")
        check('riding during navigation: extra buttons hidden, 🎤 stays visible and tappable', st['on'] and st['mic'] and not st['gpx'] and not st['layers'], st)
        await pg.evaluate("window.__say = 'поехали 32,05 34,85'; window.__mode = 'final'")
        await pg.click('#t-mic')
        await pg.wait_for_function("Nav.route && Nav.route.name.startsWith('32.05')", timeout=10000)
        check('a new destination said during the ride replaces the current route', await pg.evaluate("Nav.route.name") != 'Старый маршрут')
        await pg.evaluate("clearInterval(window.__mv); Ride.status = 'idle'")
        if not await pg.evaluate("document.getElementById('vc').hidden"): await pg.click('#vc-x')
        await pg.wait_for_timeout(500)
        # «→» while still listening: takes what was heard so far
        await pg.evaluate("window.__say = 'поехали 32,06 34,86'; window.__mode = 'slow'")
        await pg.click('#t-mic'); await pg.wait_for_timeout(1700)
        h = await pg.evaluate("document.getElementById('vc-heard').textContent")
        check('the phone heard the phrase but has not finished listening', '32,06' in h and await pg.evaluate("Voice.listening"), h)
        await pg.click('#vc-go')
        await pg.wait_for_function("Nav.route && Nav.route.name.startsWith('32.06')", timeout=10000)
        check('yellow «→» while still listening: route built from what was heard', not await pg.evaluate("Voice.listening"))
        # «→» while a search runs: says so
        await pg.fill('#vc-q', 'поехали 32,07 34,87')
        await pg.evaluate("navigator.geolocation.clearWatch(GPS.watch); GPS.watch = -1; window.__waitFix = GPS.fix; GPS.fix = null")    # waiting for GPS keeps the search busy
        await pg.click('#vc-go'); await pg.wait_for_timeout(300)
        await pg.fill('#vc-q', 'поехали 32,08 34,88'); await pg.click('#vc-go'); await pg.wait_for_timeout(200)
        s1 = await pg.evaluate("document.getElementById('vc-st').textContent")
        check('yellow «→» while a search is running: «Уже ищу — секунду…» (not silence)', 'Уже ищу' in s1, s1)
        await pg.evaluate("GPS.fix = window.__waitFix; onFix({coords: {latitude: GPS.fix.lat, longitude: GPS.fix.lon, accuracy: 5, altitude: null, altitudeAccuracy: null, speed: 0, heading: null}, timestamp: Date.now()})")
        await pg.wait_for_function("Nav.route && Nav.route.name.startsWith('32.07')", timeout=10000)
        check('…and the first search finishes', True)
        # «→» with nothing typed and nothing heard
        await pg.fill('#vc-q', ''); await pg.wait_for_timeout(600); await pg.click('#vc-go'); await pg.wait_for_timeout(200)
        s2 = await pg.evaluate("document.getElementById('vc-st').textContent")
        check('yellow «→» with an empty field: asks for an address', 'Скажите адрес' in s2, s2)
        b_ = await pg.evaluate("APP_BUILD"); await pg.click('#vc-x'); await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
        check(f'version text: v{b_} (current build)', f'навигация v{b_}' in await pg.evaluate("document.body.innerText"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            await ctx.add_init_script(SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(500)
            await pg.click('#t-mic'); await pg.wait_for_timeout(1200); await pg.click('#vc-go'); await pg.wait_for_timeout(300)
            s2 = await pg.evaluate("document.getElementById('vc-st').textContent")
            await pg.click('#vc-x'); await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
            txt = s2 + ' | ' + await pg.evaluate("document.getElementById('s-ridemode').parentElement.textContent + ' | ' + ([...document.querySelectorAll('p.note')].map(x => x.textContent).find(x => x.includes('v' + APP_BUILD + ' ')) || '')")
            check(f'[{lang}] «→» hint, «В поездке» switch and version text without Russian', re.search(r'v1\d\d ', txt) and not re.search('[А-Яа-яЁё]', txt), txt[:220])
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
