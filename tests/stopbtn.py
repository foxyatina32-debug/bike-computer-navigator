# v111: the ■ Stop button is always visible.
# Folded panel: a solid red ■ next to ▶ while a ride is recorded or paused (not before the ride), the same «Завершить
# поездку?» dialog; open panel: «Стоп» is solid red, not see-through glass. iPhone SE and 15 Pro, Russian/Hebrew/English.
# Run: python3 tests/stopbtn.py
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks
from ride import open_app, Rider
from playwright.async_api import async_playwright
RES = []
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)

STATE = """(() => { const m = document.getElementById('m-stop'), r = m.getBoundingClientRect(), mini = document.getElementById('mini').getBoundingClientRect();
  const cs = getComputedStyle(m), cp = getComputedStyle(document.getElementById('c-stop'));
  const kids = [...document.querySelectorAll('#mini > .c:not([hidden]) b, #mini > button:not([hidden])')].map(e => e.getBoundingClientRect());
  const spill = [...document.querySelectorAll('#mini > .c:not([hidden]) b')].some(e => e.scrollWidth > e.clientWidth + 1);
  const overlap = spill || kids.some((a, i) => kids.some((b, j) => j > i && a.right > b.left + 1 && b.right > a.left + 1 && a.bottom > b.top + 1 && b.bottom > a.top + 1));
  return { vis: !!(r.width && r.height) && cs.visibility !== 'hidden', bg: cs.backgroundColor, op: +cs.opacity, inside: r.left >= mini.left - 1 && r.right <= mini.right + 1,
           out: kids.some(k => k.right > mini.right + 1 || k.left < mini.left - 1), overlap, cbg: cp.backgroundColor, cop: +cp.opacity }; })()"""

async def run(p, url, m, vp, lang):
    tag = f'{vp[0]}×{vp[1]} {lang}'
    b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m, viewport=vp)
    rd = Rider(pg); await rd.fix(0, 0, 0)
    await pg.evaluate("setCompact(true, false)"); await pg.clock.run_for(300)
    st = await pg.evaluate(STATE)
    check(f'{tag}: before the ride no ■ in the folded panel', not st['vis'], st)
    await pg.click('#m-play'); await pg.clock.run_for(500)
    await rd.go([(0, 0), (0, 300)], v=6)
    # the worst case from a real ride: 3+ hours, tens of km, «осталось» shown while navigating
    await pg.evaluate("document.getElementById('m-rem-c').hidden = false; document.getElementById('m-dist').textContent = '46.3'; document.getElementById('m-time').textContent = '3:33:12'; document.getElementById('m-rem').textContent = '10.00'")
    st = await pg.evaluate(STATE)
    check(f'{tag}: recording — red ■ visible in the folded panel', st['vis'] and st['bg'] == 'rgb(239, 68, 68)' and st['op'] == 1 and st['inside'], st)
    check(f'{tag}: folded panel — nothing overlaps or sticks out', not st['overlap'] and not st['out'], st)
    await pg.click('#m-play'); await pg.clock.run_for(500)   # pause
    st = await pg.evaluate(STATE)
    check(f'{tag}: paused — ■ still visible', st['vis'] and await pg.evaluate("Ride.status") == 'paused', st)
    if vp[0] == 390 and lang == 'ru':
        await pg.screenshot(path='/tmp/stop_folded.png')
    await pg.click('#m-stop'); await pg.clock.run_for(300)
    check(f'{tag}: ■ opens «Завершить поездку?»', await pg.is_visible('#ask-stop') and await pg.is_visible('#st-save'))
    await pg.click('#st-cont'); await pg.clock.run_for(300)
    await pg.click('#hud-max'); await pg.clock.run_for(400)
    st = await pg.evaluate(STATE)
    check(f'{tag}: open panel — «Стоп» solid red', st['cbg'] == 'rgb(239, 68, 68)' and st['cop'] == 1, st)
    if vp[0] == 390 and lang == 'ru':
        await pg.screenshot(path='/tmp/stop_open.png')
    await pg.click('#hud-min'); await pg.clock.run_for(300)
    await pg.click('#m-stop'); await pg.clock.run_for(300)
    await pg.click('#st-save'); await pg.clock.run_for(1200)
    if await pg.is_visible('#ar-no'): await pg.click('#ar-no'); await pg.clock.run_for(300)
    n = len(await pg.evaluate("DB.all('rides')"))
    st = await pg.evaluate(STATE)
    check(f'{tag}: finished from the folded ■ — saved, ■ gone', n == 1 and not st['vis'] and await pg.evaluate("Ride.status") == 'idle', (n, st['vis']))
    check(f'{tag}: no JS errors', not log['errors'], log['errors'][:3])
    await b.close()

async def main():
    url = serve(8853); m = Mocks()
    async with async_playwright() as p:
        for vp in [(390, 844), (375, 667), (320, 568)]:
            for lang in ['ru', 'he', 'en']:
                await run(p, url, m, vp, lang)
    print(f'\n{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)

asyncio.run(main())
