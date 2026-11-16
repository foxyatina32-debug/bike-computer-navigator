# v115: after a ride — «📤 Отправить друзьям» right in the «✓ Сохранено» bar. A picture for WhatsApp: the map with the track
# (real map tiles), distance, moving time, average and max speed, climb, start–finish time, elevation profile; or your own
# photo behind the track. With it — a text (all the numbers, where from → where to), editable; «📤 Отправить картинку и
# текст» opens the phone's share menu with the picture and the text. The ride page «Создать открытку» opens the same.
# Russian / Hebrew / English: the text and the picture labels follow the app language.
# Run: python3 tests/rideshare.py
import asyncio, sys, os, io, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import serve, Mocks
from ride import open_app, Rider
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw
RES = []; SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
def check(name, ok, info=''):
    RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (f' — {info}' if info != '' else ''), flush=True)
PATH = [(0, -5), (0, 0), (0, 400), (300, 400), (300, 700), (600, 900)]
def tile():
    im = Image.new('RGB', (256, 256), (236, 232, 222)); d = ImageDraw.Draw(im)
    for k in range(0, 256, 64): d.line([(k, 0), (k, 256)], fill=(255, 255, 255), width=6); d.line([(0, k), (256, k)], fill=(255, 255, 255), width=6)
    d.rectangle([90, 90, 160, 150], fill=(200, 225, 190)); b = io.BytesIO(); im.save(b, 'PNG'); return b.getvalue()
def photo():
    im = Image.new('RGB', (900, 1200), (40, 90, 140)); d = ImageDraw.Draw(im); d.ellipse([200, 300, 700, 800], fill=(220, 170, 60)); b = io.BytesIO(); im.save(b, 'JPEG'); return b.getvalue()
SHARE = "() => { window.__shared = []; navigator.canShare = () => true; navigator.share = d => { window.__shared.push({ n: d.files[0].name, s: d.files[0].size, t: d.text || '' }); return Promise.resolve(); }; }"
async def wait_blob(pg, n=60):
    for _ in range(n):
        await pg.clock.run_for(250)
        if await pg.evaluate("!!RS2.blob && !!document.getElementById('rs2-img').getAttribute('src')"): return True
    return False
async def main():
    url = serve(8871); m = Mocks(); m.pages['tile-cyclosm.openstreetmap.fr'] = (tile(), 'image/png')
    async with async_playwright() as p:
        for lang in ('ru', 'he', 'en'):
            b, ctx, pg, log = await open_app(p, url + f'?lang={lang}', m)
            await pg.evaluate(SHARE)
            rd = Rider(pg); await rd.fix(0, -5, 0)
            await pg.click('#m-play'); await pg.clock.run_for(500)
            await rd.go(PATH, v=6); await rd.stand(3)
            if not await pg.is_visible('#c-stop'): await pg.click('#hud-max'); await pg.clock.run_for(400)
            await pg.click('#c-stop'); await pg.clock.run_for(200); await pg.click('#st-save'); await pg.clock.run_for(1500)
            for _ in range(150):   # the route name waits for the town (a network answer in real time): «Сохраняю…» meanwhile
                if not await pg.evaluate("!!document.getElementById('savebar').dataset.pending"): break
                await pg.wait_for_timeout(100); await pg.clock.run_for(200)
            check(f'[{lang}] after saving — «📤 Отправить друзьям» in the bar', await pg.is_visible('#sb-share'), await pg.evaluate("document.getElementById('sb-share').textContent"))
            n0 = sum('tile-cyclosm' in c for c in m.calls)
            await pg.click('#sb-share'); await pg.clock.run_for(300)
            ok = await wait_blob(pg)
            st = await pg.evaluate("({open: !document.getElementById('ask-rshare').hidden, bar: !document.getElementById('savebar').hidden, w: document.getElementById('rs2-img').naturalWidth, h: document.getElementById('rs2-img').naturalHeight})")
            check(f'[{lang}] the dialog opens with the picture 1080×1350, the bar goes away', ok and st['open'] and not st['bar'] and st['w'] == 1080 and st['h'] == 1350, st)
            check(f'[{lang}] the picture has a real map under the track (map tiles loaded)', sum('tile-cyclosm' in c for c in m.calls) > n0)
            for _ in range(12): await pg.clock.run_for(250)
            txt = await pg.evaluate("document.getElementById('rs2-txt').value")
            ride = (await pg.evaluate("DB.all('rides')"))[0]
            km = await pg.evaluate(f"fmtKm({ride['dist']})")
            cyr = any('Ѐ' <= ch <= 'ӿ' for ch in txt)
            check(f'[{lang}] the text: distance, moving time, speed, climb, where from', km in txt and '📏' in txt and '⏱' in txt and '⚡' in txt and '📍' in txt and (lang == 'ru') == cyr, txt.replace('\n', ' | '))
            if lang == 'ru':
                data = await pg.evaluate("(async () => { const b = RS2.blob; const r = new FileReader(); return await new Promise(res => { r.onload = () => res(r.result); r.readAsDataURL(b); }); })()")
                open(os.path.join(SHOT, 'rideshare-card.png'), 'wb').write(base64.b64decode(data.split(',')[1]))
                await pg.screenshot(path=os.path.join(SHOT, 'rideshare-dialog.png'))
            await pg.fill('#rs2-txt', txt + '\nКлассно покатались!');
            await pg.click('#rs2-send'); await pg.clock.run_for(500)
            sh = await pg.evaluate("window.__shared")
            check(f'[{lang}] «📤 Отправить» — the share menu gets the picture and the edited text', len(sh) == 1 and sh[0]['n'].endswith('.png') and sh[0]['s'] > 20000 and 'Классно покатались!' in sh[0]['t'], sh)
            # own photo behind the track, then back to the map
            p0 = await pg.evaluate("document.getElementById('rs2-photo').textContent")
            await pg.set_input_files('#cd-file', files=[{'name': 'p.jpg', 'mimeType': 'image/jpeg', 'buffer': photo()}]); await pg.clock.run_for(300)
            ok = await wait_blob(pg)
            p1 = await pg.evaluate("document.getElementById('rs2-photo').textContent")
            check(f'[{lang}] «📷 Своё фото фоном» — the picture is rebuilt on the photo; the button offers the map back', ok and await pg.evaluate("!!RS2.img") and p1 != p0, (p0, p1))
            await pg.click('#rs2-photo'); await pg.clock.run_for(300); ok = await wait_blob(pg)
            check(f'[{lang}] «🗺 Карта вместо фото» — back to the map', ok and await pg.evaluate("RS2.img === null") and await pg.evaluate("document.getElementById('rs2-photo').textContent") == p0)
            if lang != 'ru':
                ui = await pg.evaluate("[...document.querySelectorAll('#ask-rshare h2, #ask-rshare p, #ask-rshare button')].map(e => e.textContent).join(' | ')")
                check(f'[{lang}] the dialog is translated', not any('Ѐ' <= ch <= 'ӿ' for ch in ui), ui)
            await pg.click('#rs2-x'); await pg.clock.run_for(200)
            # the ride page: «Создать открытку» opens the same dialog
            await pg.evaluate(f"openRide('{ride['id']}')"); await pg.clock.run_for(800)
            await pg.click('#rd-card'); await pg.clock.run_for(300)
            check(f'[{lang}] ride page «Создать открытку» → the same share dialog', await pg.is_visible('#ask-rshare') and await wait_blob(pg))
            check(f'[{lang}] no JS errors', not log['errors'], log['errors'][:3])
            await b.close()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
if __name__ == '__main__': asyncio.run(main())
