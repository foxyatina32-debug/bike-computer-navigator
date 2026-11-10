# The real page as published: dima/index.html with its program inline (the other tests load it as a separate file, which
# hides this), delivered in pieces like a mobile network, in Russian / English / Hebrew — by phone language and by ?lang=.
# The translator must not touch the program's text (v107: a translated string in it broke the start in EN/HE); a start-up
# failure says what happened: the map library did not load, or an error in the program (not «opened in a file viewer»).
# The CDN libraries are not reachable here: they are replaced by empty scripts or a minimal stand-in.
import asyncio, sys, os, re, threading, time, http.server
from playwright.async_api import async_playwright
RES = []
def check(n, ok, info=''): RES.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n + (f' — {info}' if info != '' else ''))
APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dima')
CHROME = os.environ.get('CHROME_PATH', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
BOOM = os.environ.get('VELO_BOOM')   # set by the server per request below

class H(http.server.BaseHTTPRequestHandler):
    def log_message(s, *a): pass
    def do_GET(s):
        p = s.path.split('?')[0]
        b = open(os.path.join(APP, 'index.html'), 'rb').read() if p in ('/', '/index.html', '/boom/') else None
        if b is None: s.send_response(404); s.end_headers(); return
        if p == '/boom/':   # an error in the program right at start-up
            b = b.replace(b"document.getElementById('nojs').hidden = true;", b"throw new Error('boom'); document.getElementById('nojs').hidden = true;", 1)
        s.send_response(200); s.send_header('Content-Type', 'text/html; charset=utf-8'); s.end_headers()
        for i in range(0, len(b), 16384): s.wfile.write(b[i:i + 16384]); s.wfile.flush(); time.sleep(0.02)

async def main():
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 8843), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    src = re.findall(r'<script>(.*?)</script>', open(os.path.join(APP, 'index.html'), encoding='utf-8').read(), re.S)
    cyr = re.compile('[А-Яа-яЁё]')
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME if os.path.exists(CHROME) else None)
        async def page(loc, path, libs):
            ctx = await b.new_context(locale=loc, service_workers='block')
            await ctx.route(lambda u: not u.startswith('http://127.0.0.1'), lambda r: r.abort())
            await ctx.route('https://cdn.jsdelivr.net/**', lambda r: r.fulfill(body=libs, content_type='text/javascript'))   # registered last → wins
            pg = await ctx.new_page(); errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)[:120]))
            await pg.goto('http://127.0.0.1:8843' + path, wait_until='load'); await pg.wait_for_timeout(1200)
            return ctx, pg, errs
        for lang, loc in (('ru', 'ru-RU'), ('en', 'en-US'), ('he', 'he-IL')):
            for how in ('phone language', '?lang='):
                q = f'/?lang={lang}' if how == '?lang=' else '/'
                ctx, pg, errs = await page(loc, q, '')
                dom = await pg.evaluate("[...document.scripts].filter(s => !s.src).map(s => s.text)")
                same = len(dom) == len(src) and all(a == c for a, c in zip(dom, src))
                why = await pg.evaluate("document.getElementById('nojs-why').textContent")
                check(f'[{lang}, {how}] program text untouched by the translator, no SyntaxError', same and not [e for e in errs if 'SyntaxError' in e], errs[:2])
                check(f'[{lang}, {how}] libraries missing → «map library did not load» (in the page language)',
                      ('библиотека карт' in why) if lang == 'ru' else (not cyr.search(why) and ('map library' in why or 'ספריית המפות' in why)), why)
                await ctx.close()
            # an error in the program at start-up: said as such, with the error, translated
            ctx, pg, errs = await page(loc, '/boom/' + (f'?lang={lang}' if lang != 'ru' else ''), 'window.L = window.L || {};')
            why = await pg.evaluate("document.getElementById('nojs-why').textContent")
            ok = ('не запустилось из-за ошибки' in why) if lang == 'ru' else (not cyr.search(why.replace('boom', '')) and ('did not start' in why or 'לא עלתה' in why))
            check(f'[{lang}] an error in the program at start-up: «the app did not start because of an error (boom)», not «file viewer»', ok and 'boom' in why and 'просмотр' not in why, why)
            await ctx.close()
        await b.close()
    srv.shutdown()
    print(f'{sum(RES)}/{len(RES)} passed'); sys.exit(0 if all(RES) else 1)
asyncio.run(main())
