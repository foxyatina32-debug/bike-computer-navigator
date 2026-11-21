// Velocomp helper — Cloudflare Worker (free plan is enough).
//
// What it does for the app (https://foxyatina32-debug.github.io/bike-computer-navigator/):
//   GET  /health                       → {"ok":true,...}  (the app's «Проверить» button)
//   GET  /?url=<link>                  → downloads a route page / GPX / KML from an allowed site and returns it with CORS;
//                                        short links (maps.app.goo.gl …) are followed, the final address is in X-Final-URL
//   POST /strava/token  {code}|{refresh_token} → Strava OAuth token exchange (the client secret stays here, never in the app)
//   GET  /strava/api/<path>            → Strava API v3 (only reading the athlete, routes and route GPX), with the user's token
//
// It is NOT an open proxy: only requests from the app's own address (ALLOWED_ORIGINS) and only to route sites (HOSTS).
//
// Deploy: dash.cloudflare.com → Workers & Pages → Create → Worker → paste this file → Deploy.
// Settings → Variables and Secrets:
//   ALLOWED_ORIGINS       https://foxyatina32-debug.github.io        (comma-separated; optional, this is the default)
//   STRAVA_CLIENT_ID      your Strava app's Client ID                 (only for Strava)
//   STRAVA_CLIENT_SECRET  your Strava app's Client Secret — type «Secret»  (only for Strava)
//   ACCESS_KEY            optional, type «Secret»: a long random word. Then only addresses with it work — paste
//                         https://<name>.<account>.workers.dev/k/<ACCESS_KEY> into the app. The Origin header alone does
//                         not stop a bot or curl (anyone can send it); the key does.
// Then paste the worker address (https://<name>.<account>.workers.dev) in Velocomp → Настройки → Для продвинутых → «Свой прокси».

const VERSION = '2';
const DEFAULT_ORIGINS = 'https://foxyatina32-debug.github.io';
const MAX_BYTES = 15 * 1024 * 1024;
// Sites the app imports routes from (the host itself or any subdomain of it).
const HOSTS = [
  'maps.app.goo.gl', 'goo.gl', 'google.com', 'google.co.il', 'googleusercontent.com', 'drive.google.com',
  'komoot.com', 'komoot.de', 'strava.com', 'ridewithgps.com', 'wikiloc.com', 'alltrails.com', 'trailforks.com',
  'bikemap.net', 'outdooractive.com', 'mapy.cz', 'mapy.com', 'osmand.net', 'openstreetmap.org', 'osm.org',
  'israelhiking.osm.org.il', 'brouter.de', 'bikerouter.de', 'gpsies.com', 'garmin.com', 'connect.garmin.com',
  'github.com', 'raw.githubusercontent.com', 'githubusercontent.com', 'dropbox.com', 'dropboxusercontent.com',
  '1drv.ms', 'onedrive.live.com', 'icloud.com', 'gpx.studio', 'plotaroute.com', 'onthegomap.com', 'calimoto.com'
];
// v2 (audit R14): Google's own country domains, exactly — the old pattern google.[a-z.]+ also let in google.attacker.example
const GOOGLE_TLDS = ['com', 'co.il', 'ru', 'de', 'fr', 'it', 'es', 'nl', 'pl', 'pt', 'at', 'ch', 'be', 'se', 'no', 'dk', 'fi', 'cz', 'gr', 'ie', 'co.uk',
  'com.ua', 'by', 'kz', 'com.tr', 'ca', 'com.au', 'co.nz', 'com.br', 'com.mx', 'co.in', 'ae', 'co.jp', 'co.kr', 'com.sg', 'co.za', 'ge', 'am', 'az', 'md', 'lv', 'lt', 'ee'];
const hostAllowed = h => { h = h.toLowerCase().replace(/\.$/, ''); return HOSTS.concat(GOOGLE_TLDS.map(t => 'google.' + t)).some(x => h === x || h.endsWith('.' + x)); };
const TIMEOUT_MS = 25000, RATE = 60;   // a download may take 25 s; 60 requests a minute from one address (per worker instance)
const hits = new Map();
function rateOk(ip) {
  const now = Date.now(), m = now - 60000, a = (hits.get(ip) || []).filter(t => t > m); a.push(now); hits.set(ip, a);
  if (hits.size > 5000) for (const [k, v] of hits) if (!v.length || v[v.length - 1] < m) hits.delete(k);
  return a.length <= RATE;
}
// reads a body up to the limit — stops (and cancels the download) as soon as it is passed, before the memory is taken
async function readCapped(r, max) {
  if (!r.body) return new Uint8Array(0);
  const rd = r.body.getReader(), parts = []; let n = 0;
  for (;;) { const { done, value } = await rd.read(); if (done) break; n += value.byteLength; if (n > max) { try { await rd.cancel(); } catch {} return null; } parts.push(value); }
  const out = new Uint8Array(n); let o = 0; for (const p of parts) { out.set(p, o); o += p.byteLength; } return out;
}

function cors(origin, extra = {}) {
  return { 'Access-Control-Allow-Origin': origin, 'Vary': 'Origin', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type', 'Access-Control-Expose-Headers': 'X-Final-URL', 'Access-Control-Max-Age': '86400', ...extra };
}
const json = (obj, status, origin) => new Response(JSON.stringify(obj), { status, headers: cors(origin, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }) });

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    // the owner's key in the address (/k/<ACCESS_KEY>/…), when one is set
    if (env.ACCESS_KEY) {
      const pre = '/k/' + env.ACCESS_KEY;
      if (url.pathname !== pre && !url.pathname.startsWith(pre + '/')) return new Response('Forbidden', { status: 403 });
      url.pathname = url.pathname.slice(pre.length) || '/';
    }
    const allowed = (env.ALLOWED_ORIGINS || DEFAULT_ORIGINS).split(',').map(s => s.trim()).filter(Boolean);
    const origin = req.headers.get('Origin') || '';
    const okOrigin = allowed.includes(origin) || (env.ALLOW_LOCALHOST === '1' && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin));
    if (req.method === 'OPTIONS') return new Response(null, { status: okOrigin ? 204 : 403, headers: okOrigin ? cors(origin) : {} });
    if (url.pathname === '/health') return json({ ok: true, app: 'velocomp-worker', version: VERSION, strava: !!(env.STRAVA_CLIENT_ID && env.STRAVA_CLIENT_SECRET) }, 200, okOrigin ? origin : '*');
    if (!okOrigin) return new Response('Forbidden: this worker only serves the Velocomp app', { status: 403 });
    if (!rateOk(req.headers.get('CF-Connecting-IP') || 'any')) return json({ error: 'too_many_requests' }, 429, origin);

    try {
      // ---- Strava OAuth: the secret never leaves the worker ----
      if (url.pathname === '/strava/token' && req.method === 'POST') {
        if (!env.STRAVA_CLIENT_ID || !env.STRAVA_CLIENT_SECRET) return json({ error: 'strava_not_configured' }, 501, origin);
        const b = await req.json().catch(() => ({}));
        const form = new URLSearchParams({ client_id: env.STRAVA_CLIENT_ID, client_secret: env.STRAVA_CLIENT_SECRET });
        if (b.code) { form.set('code', String(b.code)); form.set('grant_type', 'authorization_code'); }
        else if (b.refresh_token) { form.set('refresh_token', String(b.refresh_token)); form.set('grant_type', 'refresh_token'); }
        else return json({ error: 'code_or_refresh_token_required' }, 400, origin);
        const r = await fetch('https://www.strava.com/oauth/token', { method: 'POST', body: form });
        const j = await r.json().catch(() => ({}));
        // Only what the app needs (no secrets back).
        return json(r.ok ? { access_token: j.access_token, refresh_token: j.refresh_token, expires_at: j.expires_at, athlete: j.athlete ? { id: j.athlete.id, firstname: j.athlete.firstname, lastname: j.athlete.lastname } : null } : { error: j.message || 'strava_error', status: r.status }, r.ok ? 200 : 502, origin);
      }
      if (url.pathname === '/strava/client') return json({ client_id: env.STRAVA_CLIENT_ID || null }, 200, origin);
      if (url.pathname.startsWith('/strava/api/') && req.method === 'GET') {
        const path = url.pathname.slice('/strava/api/'.length);
        // read-only: the athlete, their routes, a route, a route's GPX
        if (!/^(athlete|athletes\/\d+\/routes|routes\/\d+|routes\/\d+\/export_gpx)$/.test(path)) return json({ error: 'path_not_allowed' }, 403, origin);
        const auth = req.headers.get('Authorization') || '';
        if (!/^Bearer [\w.-]+$/.test(auth)) return json({ error: 'token_required' }, 401, origin);
        const r = await fetch('https://www.strava.com/api/v3/' + path + url.search, { headers: { Authorization: auth } });
        return new Response(r.body, { status: r.status, headers: cors(origin, { 'Content-Type': r.headers.get('Content-Type') || 'application/octet-stream', 'Cache-Control': 'no-store' }) });
      }

      // ---- fetch a route page / file from an allowed site ----
      if (url.pathname === '/' && req.method === 'GET') {
        const target = url.searchParams.get('url');
        if (!target) return json({ error: 'url_required' }, 400, origin);
        let t; try { t = new URL(target); } catch { return json({ error: 'bad_url' }, 400, origin); }
        if (!/^https?:$/.test(t.protocol) || !hostAllowed(t.hostname)) return json({ error: 'host_not_allowed', host: t.hostname }, 403, origin);
        // follow redirects ourselves: every hop must stay on an allowed site
        let cur = t.href, r;
        const ac = new AbortController(), timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
        try {
        for (let hop = 0; hop < 8; hop++) {
          r = await fetch(cur, { redirect: 'manual', signal: ac.signal, headers: { 'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1', 'Accept-Language': 'en,ru,he' } });
          const loc = r.headers.get('Location');
          if (r.status >= 300 && r.status < 400 && loc) {
            const next = new URL(loc, cur);
            if (!/^https?:$/.test(next.protocol) || !hostAllowed(next.hostname)) return json({ error: 'redirect_not_allowed', url: next.href }, 403, origin);
            cur = next.href; continue;
          }
          break;
        }
        const len = +(r.headers.get('Content-Length') || 0);
        if (len > MAX_BYTES) { try { r.body && r.body.cancel(); } catch {} return json({ error: 'too_large' }, 413, origin); }
        const buf = await readCapped(r, MAX_BYTES);
        if (!buf) return json({ error: 'too_large' }, 413, origin);
        return new Response(buf, { status: r.status, headers: cors(origin, { 'Content-Type': r.headers.get('Content-Type') || 'application/octet-stream', 'X-Final-URL': cur, 'Cache-Control': 'no-store' }) });
        } catch (e) { if (ac.signal.aborted) return json({ error: 'timeout' }, 504, origin); throw e; }
        finally { clearTimeout(timer); }
      }
      return json({ error: 'not_found' }, 404, origin);
    } catch (e) {
      return json({ error: 'worker_error', message: String(e && e.message || e) }, 502, origin);
    }
  }
};
