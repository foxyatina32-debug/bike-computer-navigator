// Unit test for cloudflare-worker.js (Node 18+): node tests/worker_test.mjs
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os'; import { join, dirname } from 'node:path'; import { fileURLToPath, pathToFileURL } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const tmp = mkdtempSync(join(tmpdir(), 'wk-')); const f = join(tmp, 'worker.mjs');
writeFileSync(f, readFileSync(join(here, '..', 'cloudflare-worker.js'), 'utf8'));
const W = (await import(pathToFileURL(f).href)).default;
let pass = 0, fail = 0; const check = (n, ok, info = '') => { ok ? pass++ : fail++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (info ? ' — ' + info : '')); };
const ORIGIN = 'https://foxyatina32-debug.github.io';
const calls = [];
globalThis.fetch = async (u, o = {}) => {
  u = String(u); calls.push([u, o]);
  if (u === 'https://maps.app.goo.gl/abc') return new Response('', { status: 302, headers: { Location: 'https://www.google.com/maps/dir/32.1,34.8/32.2,34.9' } });
  if (u === 'https://maps.app.goo.gl/evil') return new Response('', { status: 302, headers: { Location: 'http://169.254.169.254/latest' } });
  if (u.startsWith('https://www.google.com/maps/dir/')) return new Response('<html>maps</html>', { headers: { 'Content-Type': 'text/html' } });
  if (u === 'https://www.wikiloc.com/t.gpx') return new Response('<gpx></gpx>', { headers: { 'Content-Type': 'application/gpx+xml' } });
  return new Response('nope', { status: 404 });
};
const env = {};
const req = (path, o = {}) => W.fetch(new Request('https://wk.example.workers.dev' + path, { headers: { Origin: ORIGIN, ...(o.headers || {}) }, method: o.method || 'GET', body: o.body }), o.env || env);

let r = await req('/health'); let j = await r.json();
check('health', r.status === 200 && j.ok && j.app === 'velocomp-worker' && j.version === '3' && !('strava' in j), JSON.stringify(j));
r = await W.fetch(new Request('https://wk.example.workers.dev/?url=' + encodeURIComponent('https://www.wikiloc.com/t.gpx'), { headers: { Origin: 'https://evil.example' } }), env);
check('other sites cannot use it (origin)', r.status === 403);
r = await req('/?url=' + encodeURIComponent('https://www.wikiloc.com/t.gpx'));
check('fetches an allowed route file with CORS', r.status === 200 && (await r.text()) === '<gpx></gpx>' && r.headers.get('Access-Control-Allow-Origin') === ORIGIN);
r = await req('/?url=' + encodeURIComponent('https://maps.app.goo.gl/abc'));
check('expands a short Google link (X-Final-URL)', r.headers.get('X-Final-URL') === 'https://www.google.com/maps/dir/32.1,34.8/32.2,34.9' && /X-Final-URL/.test(r.headers.get('Access-Control-Expose-Headers')), r.headers.get('X-Final-URL'));
r = await req('/?url=' + encodeURIComponent('https://example.com/a'));
check('not an open proxy: other hosts refused', r.status === 403);
r = await req('/?url=' + encodeURIComponent('https://maps.app.goo.gl/evil'));
check('redirect to a non-allowed address refused', r.status === 403);
// v3: the unused Strava stub is gone — none of its addresses answer, nothing goes to Strava
const n0 = calls.length;
const gone = [await req('/strava/token', { method: 'POST', body: '{"code":"x"}' }), await req('/strava/client'), await req('/strava/api/athlete', { headers: { Authorization: 'Bearer AT' } })];
check('v3: the Strava stub is removed (404, nothing sent to Strava)', gone.every(x => x.status === 404) && !calls.slice(n0).some(c => c[0].includes('strava.com')));
r = await W.fetch(new Request('https://wk.example.workers.dev/', { method: 'OPTIONS', headers: { Origin: ORIGIN } }), env);
check('CORS preflight', r.status === 204 && r.headers.get('Access-Control-Allow-Methods') === 'GET, OPTIONS');
// v2 (audit R14): exact Google domains, a capped download, the owner's key, a rate limit
const fetch0 = globalThis.fetch;
globalThis.fetch = async (u, o = {}) => {
  u = String(u);
  if (u === 'https://google.attacker.example/route.gpx') return new Response('<gpx/>');
  if (u === 'https://www.google.co.il/maps/dir/1,2/3,4') return new Response('<html>il</html>');
  if (u === 'https://www.wikiloc.com/huge.gpx') { let n = 0; return new Response(new ReadableStream({ pull(c) { if (n++ > 40) c.close(); else c.enqueue(new Uint8Array(1024 * 1024)); } })); }
  return fetch0(u, o);
};
r = await req('/?url=' + encodeURIComponent('https://google.attacker.example/route.gpx'));
check('R14: google.attacker.example is not Google — refused', r.status === 403);
r = await req('/?url=' + encodeURIComponent('https://www.google.co.il/maps/dir/1,2/3,4'));
check('R14: google.co.il still allowed', r.status === 200 && (await r.text()) === '<html>il</html>');
r = await req('/?url=' + encodeURIComponent('https://www.wikiloc.com/huge.gpx'));
check('R14: a download without a size header is stopped at 15 MB while streaming', r.status === 413);
const envK = { ...env, ACCESS_KEY: 'k3y-long-random' };
r = await req('/?url=' + encodeURIComponent('https://www.wikiloc.com/t.gpx'), { env: envK });
check('R14: with ACCESS_KEY set, an address without the key is refused (Origin alone is not enough)', r.status === 403);
r = await req('/k/k3y-long-random/?url=' + encodeURIComponent('https://www.wikiloc.com/t.gpx'), { env: envK });
check('R14: …with the key in the address it works', r.status === 200 && (await r.text()) === '<gpx></gpx>');
r = await req('/k/k3y-long-random/health', { env: envK }); j = await r.json();
check('R14: the health check with the key', r.status === 200 && j.version === '3');
let last = 0; for (let i = 0; i < 70; i++) { r = await W.fetch(new Request('https://wk.example.workers.dev/?url=' + encodeURIComponent('https://www.wikiloc.com/t.gpx'), { headers: { Origin: ORIGIN, 'CF-Connecting-IP': '203.0.113.9' } }), env); last = r.status; }
check('R14: more than 60 requests a minute from one address → 429', last === 429);
console.log(`${pass}/${pass + fail} passed`); process.exit(fail ? 1 : 0);
