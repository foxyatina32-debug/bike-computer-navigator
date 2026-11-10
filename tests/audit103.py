# v103: «Привет, Вело» listens only while a ride is recording or navigation is on (not from the moment the app opens);
# a tap on 🎤 never starts the wake listener under the command, and after the continuous wake listener the command's
# recognizer waits ~1 s so iOS does not hand it a silent microphone. Every recognizer start/abort is logged with its time.
import asyncio, sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
LOG_SR = '''window.__ev = []; window.__cur = [];
class LSR { start() { this.kind = this.continuous ? 'wake' : 'cmd'; window.__ev.push([performance.now(), 'start', this.kind]); window.__cur.push(this);
    if (this.kind === 'cmd') setTimeout(() => { if (this._ab) return; this.onaudiostart && this.onaudiostart();
      this.onresult && this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: window.__say || 'домой' }], { isFinal: true })] }); this.onend && this.onend(); }, 300); }
  abort() { if (this._ab) return; this._ab = true; window.__ev.push([performance.now(), 'abort', this.kind]); setTimeout(() => { window.__ev.push([performance.now(), 'end', this.kind]); this.onend && this.onend(); }, 40); }
  stop() { this.abort(); } }
window.__endWake = () => { const w = window.__cur.filter(r => r.kind === 'wake' && !r._ab && !r._end).pop(); if (w) { w._end = true; window.__ev.push([performance.now(), 'ios-ended', 'wake']); w.onend && w.onend(); } };
window.__wakeOn = () => window.__cur.some(r => r.kind === 'wake' && !r._ab && !r._end);
window.webkitSpeechRecognition = window.SpeechRecognition = LSR;'''
STORE = [['velo:settings', json.dumps({'wakeword': True})], ['velo:home', json.dumps({'ll': [32.0853, 34.7818], 'name': 'Тель-Авив'})]]
ROUTE = "Nav.set({ name: 'Тест', coords: [[32.09, 34.88], [32.10, 34.88], [32.11, 34.89]], noAsk: true })"

async def tap(pg, sel):
    x, y = await pg.evaluate(f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()")
    await pg.mouse.move(x, y); await pg.mouse.down(); await pg.wait_for_timeout(120); await pg.mouse.up()

async def main():
    url = serve(8837); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=STORE)
        await ctx.add_init_script(LOG_SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true')
        await pg.wait_for_timeout(3500)
        ev = await pg.evaluate("window.__ev.length")
        check('app opened with «Привет, Вело» on, no ride, no navigation: the microphone is not started', ev == 0 and not await pg.evaluate("Voice.waking"), ev)
        await pg.mouse.click(200, 400); await pg.wait_for_timeout(1500)
        check('a tap on the map does not start it either', await pg.evaluate("window.__ev.length") == 0)
        # navigation on → listens; off → stops
        await pg.evaluate(ROUTE)
        await pg.wait_for_function("window.__wakeOn() && Voice.waking", timeout=5000)
        check('navigation started: «Привет, Вело» listening (green dot on 🎤)', await pg.evaluate("document.getElementById('t-mic').classList.contains('wake')"))
        await pg.evaluate("Nav.stop()")
        await pg.wait_for_function("!window.__wakeOn() && !Voice.waking", timeout=5000)
        check('navigation ended (no ride): listening stops', True)
        # a ride recording → listens
        await pg.evaluate("Ride.start()")
        await pg.wait_for_function("window.__wakeOn() && Voice.waking", timeout=5000)
        check('ride recording: «Привет, Вело» listening', True)
        # tap on 🎤 while the wake listener runs: it is aborted first, the command waits ≥ 1 s after its end, no wake start in between
        await pg.evaluate("window.__ev = []; window.__say = 'поехали 32,05 34,85'")
        await tap(pg, '#t-mic')
        await pg.wait_for_function("Nav.route && Nav.route.name.startsWith('32.05')", timeout=8000)
        ev = await pg.evaluate("window.__ev.map(e => [Math.round(e[0]), e[1], e[2]])")
        cmd = [e for e in ev if e[1] == 'start' and e[2] == 'cmd']; wend = [e for e in ev if e[1] == 'end' and e[2] == 'wake']
        wake_before = [e for e in ev if e[1] == 'start' and e[2] == 'wake' and cmd and e[0] < cmd[0][0]]
        check('🎤 during the wake listener: wake aborted, command starts ≥ 1 s after it ended, nothing else in between',
              cmd and wend and cmd[0][0] - wend[0][0] >= 950 and not wake_before, ev)
        check('the command was understood → route', True)
        await pg.click('#vc-x')   # opened by the button (not by the phrase): the rider closes the panel
        # iOS ended the wake listener just before the tap: the tap on 🎤 must not start a new wake listener under the command
        await pg.wait_for_function("window.__wakeOn()", timeout=6000)
        await pg.evaluate("window.__ev = []; window.__say = 'поехали 32,06 34,86'; window.__endWake()")
        await pg.wait_for_timeout(600)
        await pg.evaluate("window.__ev = window.__ev.filter(e => e[1] !== 'start' || e[2] !== 'wake')")   # a restart by the timer before the tap is normal
        await tap(pg, '#t-mic')
        await pg.wait_for_function("Nav.route && Nav.route.name.startsWith('32.06')", timeout=8000)
        ev = await pg.evaluate("window.__ev.map(e => [Math.round(e[0]), e[1], e[2]])")
        cmd = [e for e in ev if e[1] == 'start' and e[2] == 'cmd']
        starts = [e for e in ev if e[1] == 'start' and e[2] == 'wake' and cmd and e[0] < cmd[0][0] and e[0] > ev[0][0] + 600]
        check('🎤 tapped while iOS had just ended the wake listener: no wake listener started under the command', cmd and not starts, ev)
        # ride over, navigation over → off again
        await pg.evaluate("Nav.stop(); Ride.stop(true)")
        await pg.wait_for_function("!window.__wakeOn() && !Voice.waking", timeout=6000)
        check('ride saved and navigation ended: the microphone is off', True)
        await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
        txt = await pg.evaluate("document.getElementById('s-wakeword').closest('label').textContent + ' | ' + document.getElementById('s-wakeword-st').textContent")
        check('Settings say it listens only during a ride or navigation', 'во время поездки или навигации' in txt and 'только во время записи поездки или навигации' in txt, txt)
        b_ = await pg.evaluate("APP_BUILD"); check(f'version text: v{b_} (current build)', f'навигация v{b_}' in await pg.evaluate("document.body.innerText"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, storage=STORE)
            await ctx.add_init_script(LOG_SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true')
            await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(500)
            txt = await pg.evaluate("document.getElementById('s-wakeword').closest('label').textContent + ' | ' + document.getElementById('s-wakeword-st').textContent + ' | ' + ([...document.querySelectorAll('p.note')].map(x => x.textContent).find(x => x.includes('v' + APP_BUILD + ' ')) || '')")
            check(f'[{lang}] wake switch, its note and version text translated', re.search(r'v1\d\d ', txt) and not re.search('[А-Яа-яЁё]', txt), txt[:200])
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
