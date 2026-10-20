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
  if (u === 'https://www.strava.com/oauth/token') { const b = String(o.body); return new Response(JSON.stringify({ access_token: 'AT', refresh_token: 'RT', expires_at: 2e9, athlete: { id: 7, firstname: 'Dima', lastname: 'S', email: 'x' }, secret_echo: b.includes('client_secret=SEC') }), { headers: { 'Content-Type': 'application/json' } }); }
  if (u.startsWith('https://www.strava.com/api/v3/')) return new Response(JSON.stringify({ path: u, auth: o.headers && o.headers.Authorization }), { headers: { 'Content-Type': 'application/json' } });
  return new Response('nope', { status: 404 });
};
const env = { STRAVA_CLIENT_ID: '123', STRAVA_CLIENT_SECRET: 'SEC' };
const req = (path, o = {}) => W.fetch(new Request('https://wk.example.workers.dev' + path, { headers: { Origin: ORIGIN, ...(o.headers || {}) }, method: o.method || 'GET', body: o.body }), o.env || env);

let r = await req('/health'); let j = await r.json();
check('health', r.status === 200 && j.ok && j.app === 'velocomp-worker' && j.strava === true, JSON.stringify(j));
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
r = await req('/strava/token', { method: 'POST', body: JSON.stringify({ code: 'C1' }), headers: { 'Content-Type': 'application/json' } }); j = await r.json();
const tokCall = calls.find(c => c[0] === 'https://www.strava.com/oauth/token');
check('Strava token: secret added in the worker, not returned', r.status === 200 && j.access_token === 'AT' && j.athlete.firstname === 'Dima' && !('email' in j.athlete) && !JSON.stringify(j).includes('SEC') && String(tokCall[1].body).includes('grant_type=authorization_code'), JSON.stringify(j));
r = await req('/strava/token', { method: 'POST', body: JSON.stringify({ refresh_token: 'RT' }), headers: { 'Content-Type': 'application/json' } });
check('Strava refresh', r.status === 200 && String(calls[calls.length - 1][1].body).includes('grant_type=refresh_token'));
r = await req('/strava/api/athletes/7/routes?per_page=50', { headers: { Authorization: 'Bearer AT' } }); j = await r.json();
check('Strava API: routes list forwarded with the token', r.status === 200 && j.path === 'https://www.strava.com/api/v3/athletes/7/routes?per_page=50' && j.auth === 'Bearer AT');
r = await req('/strava/api/activities', { headers: { Authorization: 'Bearer AT' } });
check('Strava API: only read-only route paths', r.status === 403);
r = await req('/strava/token', { method: 'POST', body: '{"code":"x"}', env: {} });
check('Strava not configured → clear error', r.status === 501);
r = await W.fetch(new Request('https://wk.example.workers.dev/', { method: 'OPTIONS', headers: { Origin: ORIGIN } }), env);
check('CORS preflight', r.status === 204 && r.headers.get('Access-Control-Allow-Headers').includes('Authorization'));
console.log(`${pass}/${pass + fail} passed`); process.exit(fail ? 1 : 0);
