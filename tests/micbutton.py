# v105: no «Привет, Вело» — the microphone never starts by itself (at launch, during a ride, during navigation, even with
# the old setting saved as on); voice only by the 🎤 button, whose recognizer starts right after the tap. Recognizer
# starts/aborts are logged with their time.
import asyncio, sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
LOG_SR = '''window.__ev = [];
class LSR { start() { window.__ev.push([performance.now(), 'start', this.continuous ? 'wake' : 'cmd']);
    if (!this.continuous) setTimeout(() => { if (this._ab) return; this.onaudiostart && this.onaudiostart();
      this.onresult && this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: window.__say || 'домой' }], { isFinal: true })] }); this.onend && this.onend(); }, 300); }
  abort() { if (this._ab) return; this._ab = true; window.__ev.push([performance.now(), 'abort', this.continuous ? 'wake' : 'cmd']); setTimeout(() => this.onend && this.onend(), 40); }
  stop() { this.abort(); } }
window.webkitSpeechRecognition = window.SpeechRecognition = LSR;'''
STORE = [['velo:settings', json.dumps({'wakeword': True})], ['velo:home', json.dumps({'ll': [32.0853, 34.7818], 'name': 'Тель-Авив'})]]

async def main():
    url = serve(8837); m = Mocks()
    async with async_playwright() as p:
        b, ctx, pg, log = await open_app(p, url + '?lang=ru', m, storage=STORE)
        await ctx.add_init_script(LOG_SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true')
        await pg.wait_for_timeout(3000)
        check('app opened (old «Привет, Вело» setting on): no microphone', await pg.evaluate("window.__ev.length") == 0)
        check('the old setting is saved as off; no switch for it in Settings', await pg.evaluate("lsGet('settings', {}).wakeword") is False and await pg.evaluate("!document.getElementById('s-wakeword')"))
        await pg.evaluate("Nav.set({ name: 'Тест', noAsk: true, coords: [[32.09, 34.88], [32.10, 34.88], [32.11, 34.89]] })"); await pg.wait_for_timeout(3500)
        check('navigation on: no microphone', await pg.evaluate("window.__ev.length") == 0 and not await pg.evaluate("Voice.waking"))
        await pg.evaluate("Ride.start()"); await pg.mouse.click(200, 420); await pg.wait_for_timeout(3500)
        check('ride recording and a tap on the map: no microphone', await pg.evaluate("window.__ev.length") == 0)
        # 🎤 by hand
        x, y = await pg.evaluate("(() => { const r = document.getElementById('t-mic').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
        await pg.evaluate("window.__say = 'поехали 32,05 34,85'; window.__t0 = performance.now()")
        await pg.mouse.move(x, y); await pg.mouse.down(); await pg.wait_for_timeout(120); await pg.mouse.up()
        await pg.wait_for_function("Nav.route && Nav.route.name.startsWith('32.05')", timeout=8000)
        ev = await pg.evaluate("window.__ev.map(e => [Math.round(e[0] - window.__t0), e[1], e[2]])")
        cmd = [e for e in ev if e[1] == 'start' and e[2] == 'cmd']
        check('🎤: only the command recognizer, it starts within ~1 s of the tap, and the command works', cmd and not [e for e in ev if e[2] == 'wake'] and cmd[0][0] < 1100, ev)
        await pg.click('#vc-x'); await pg.wait_for_timeout(3000)
        n = await pg.evaluate("window.__ev.filter(e => e[1] === 'start').length")
        check('panel closed: the microphone stays off', n == 1, n)
        b_ = await pg.evaluate("APP_BUILD"); await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(300)
        check(f'version text: v{b_} (current build)', f'навигация v{b_}' in await pg.evaluate("document.body.innerText"))
        check('no JS errors', not log['errors'], log['errors'][:3])
        await b.close()
        for lang in ('he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, storage=STORE)
            await pg.evaluate("showTab('profile')"); await pg.wait_for_timeout(400)
            ver = await pg.evaluate("[...document.querySelectorAll('p.note')].map(x => x.textContent).find(x => x.includes('v' + APP_BUILD + ' ')) || ''")
            check(f'[{lang}] version text translated', ver and not re.search('[А-Яа-яЁё]', ver), ver[:120])
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
