# v118: 🎤 answers every tap. After «ничего не услышал» / «не понял» / a finished command, 🎤 on the map listens again (it used
# to close the panel); while listening it stops and says so; while the last command is still searching or building a route,
# a new tap drops that command and listens — the new command wins, the old result never replaces it. Quick repeated taps
# leave it working. The recognizer is a fake that "hears" window.__sayNext. Run: python3 tests/voiceagain.py
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks, open_app
from playwright.async_api import async_playwright
FAKE_SR = '''window.__sayNext = ''; window.__sayQ = []; window.__srStarts = 0;
class FakeSR { start() { window.__srStarts++; if (window.__hold) return; setTimeout(() => { if (this._ab) return; const t = window.__sayQ.length ? window.__sayQ.shift() : window.__sayNext; window.__sayNext = '';
  if (!t) { this.onerror && this.onerror({ error: 'no-speech' }); this.onend && this.onend(); return; }
  const res = [{ transcript: t, confidence: .9 }]; res.isFinal = true; this.onresult && this.onresult({ resultIndex: 0, results: [res] }); this.onend && this.onend(); }, 150); }
  abort() { this._ab = true; } stop() { this._ab = true; } }   // like a real recognizer: nothing more after abort
window.webkitSpeechRecognition = window.SpeechRecognition = FakeSR;'''
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
ST = "document.getElementById('vc-st').textContent"
SLOW = """(() => { const orig = window.routeVia; window.__rv = 0;
  window.routeVia = async function (pts, o, x) { const n = ++window.__rv; if (n === 1) await new Promise(r => setTimeout(r, 4000)); return orig.apply(this, arguments); }; })()"""

async def tap_map_mic(pg, say=None):
    # the open panel covers 🎤 on the map: then the rider taps 🎤 in the panel
    if say is not None: await pg.evaluate(f"window.__sayNext = {say!r}")
    await pg.click('#t-mic' if await pg.evaluate("document.getElementById('vc').hidden") else '#vc-mic')

async def main():
    url = serve(8881); m = Mocks()
    async with async_playwright() as p:
        for lang in ('ru', 'he'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            await ctx.add_init_script(FAKE_SR); await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(800)
            await pg.evaluate("lsSet('home', { ll: [32.0853, 34.7818], name: 'Тель-Авив' })")
            # 1. nothing heard → 🎤 on the map again: listens again, the panel stays
            await tap_map_mic(pg, ''); await pg.wait_for_timeout(2500)
            nothing = await pg.evaluate(ST)
            n0 = await pg.evaluate('window.__srStarts')
            await tap_map_mic(pg, ''); await pg.wait_for_timeout(2000)
            check(f'{lang}: after «nothing heard» 🎤 listens again (panel stays open)', await pg.evaluate('window.__srStarts') > n0 and not await pg.evaluate("document.getElementById('vc').hidden"), (nothing, n0))
            # 2. not understood → 🎤 again → a command works
            await tap_map_mic(pg, 'запомни дом здесь сейчас же немедленно'); await pg.wait_for_timeout(2500)
            await tap_map_mic(pg, 'поехали домой' if lang == 'ru' else 'סע הביתה')
            await pg.wait_for_function("Nav.route && /Домой|הביתה/.test(Nav.route.name)", timeout=15000)
            check(f'{lang}: a second tap after a finished attempt takes the next command', True)
            await pg.evaluate("Nav.stop(); showTab('rec')"); await pg.wait_for_timeout(300)
            # 3. while listening: a tap stops and says so
            if await pg.evaluate("document.getElementById('vc').hidden"): await tap_map_mic(pg, None)
            await pg.evaluate("window.__sayQ = []; window.__sayNext = ''")
            await pg.evaluate("window.__hold = true")   # the recognizer keeps listening (hears nothing yet)
            await pg.click('#vc-mic'); await pg.wait_for_timeout(1700)
            await tap_map_mic(pg); await pg.wait_for_timeout(300)
            st = await pg.evaluate(ST)
            check(f'{lang}: while listening, 🎤 stops and says «tap 🎤 to say it again»', ('Остановлено' in st or 'נעצר' in st) and '🎤' in st and not await pg.evaluate("document.getElementById('vc-mic').classList.contains('rec')"), st)
            await pg.evaluate("window.__hold = false")
            await pg.reload(); await pg.wait_for_function('window.__appReady === true'); await pg.wait_for_timeout(800)
            # 4. while the last command is still building the route: a new tap is heard and wins
            await pg.evaluate(SLOW)
            await tap_map_mic(pg, 'поехали 32,05 34,85'); await pg.wait_for_timeout(1800)
            busy1 = await pg.evaluate(ST)
            await tap_map_mic(pg, 'поехали домой' if lang == 'ru' else 'סע הביתה')
            await pg.wait_for_function("Nav.route && /Домой|הביתה/.test(Nav.route.name)", timeout=15000)
            await pg.wait_for_timeout(4500)   # the first (slow) command finishes meanwhile — it must not take over
            name = await pg.evaluate("Nav.route && Nav.route.name")
            check(f'{lang}: during «building the route…» 🎤 listens at once; the new command wins, the old result is dropped', bool(name) and ('Домой' in name or 'הביתה' in name) and await pg.evaluate('window.__rv') == 2, (busy1, name))
            await pg.evaluate("Nav.stop(); showTab('rec')"); await pg.wait_for_timeout(300)
            # 5. quick repeated taps: still works afterwards
            for _ in range(6): await tap_map_mic(pg); await pg.wait_for_timeout(120)
            await pg.wait_for_timeout(1500)
            if await pg.evaluate("document.getElementById('vc').hidden"): await tap_map_mic(pg, None); await pg.wait_for_timeout(300)
            await pg.evaluate("window.__sayNext = 'поехали 32,05 34,85'"); await pg.click('#vc-mic')
            await pg.wait_for_function("Nav.route && Nav.route.name.startsWith('32.05000')", timeout=15000)
            check(f'{lang}: after six quick taps the next command still works', True)
            check(f'{lang}: no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
