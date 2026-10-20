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
// Then paste the worker address (https://<name>.<account>.workers.dev) in Velocomp → Настройки → Для продвинутых → «Свой прокси».

const VERSION = '1';
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
const hostAllowed = h => { h = h.toLowerCase().replace(/\.$/, ''); return HOSTS.some(x => h === x || h.endsWith('.' + x)) || /(^|\.)google\.[a-z.]+$/.test(h); };

function cors(origin, extra = {}) {
  return { 'Access-Control-Allow-Origin': origin, 'Vary': 'Origin', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type', 'Access-Control-Expose-Headers': 'X-Final-URL', 'Access-Control-Max-Age': '86400', ...extra };
}
const json = (obj, status, origin) => new Response(JSON.stringify(obj), { status, headers: cors(origin, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }) });

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const allowed = (env.ALLOWED_ORIGINS || DEFAULT_ORIGINS).split(',').map(s => s.trim()).filter(Boolean);
    const origin = req.headers.get('Origin') || '';
    const okOrigin = allowed.includes(origin) || (env.ALLOW_LOCALHOST === '1' && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin));
    if (req.method === 'OPTIONS') return new Response(null, { status: okOrigin ? 204 : 403, headers: okOrigin ? cors(origin) : {} });
    if (url.pathname === '/health') return json({ ok: true, app: 'velocomp-worker', version: VERSION, strava: !!(env.STRAVA_CLIENT_ID && env.STRAVA_CLIENT_SECRET) }, 200, okOrigin ? origin : '*');
    if (!okOrigin) return new Response('Forbidden: this worker only serves the Velocomp app', { status: 403 });

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
        for (let hop = 0; hop < 8; hop++) {
          r = await fetch(cur, { redirect: 'manual', headers: { 'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1', 'Accept-Language': 'en,ru,he' } });
          const loc = r.headers.get('Location');
          if (r.status >= 300 && r.status < 400 && loc) {
            const next = new URL(loc, cur);
            if (!/^https?:$/.test(next.protocol) || !hostAllowed(next.hostname)) return json({ error: 'redirect_not_allowed', url: next.href }, 403, origin);
            cur = next.href; continue;
          }
          break;
        }
        const len = +(r.headers.get('Content-Length') || 0);
        if (len > MAX_BYTES) return json({ error: 'too_large' }, 413, origin);
        const buf = await r.arrayBuffer();
        if (buf.byteLength > MAX_BYTES) return json({ error: 'too_large' }, 413, origin);
        return new Response(buf, { status: r.status, headers: cors(origin, { 'Content-Type': r.headers.get('Content-Type') || 'application/octet-stream', 'X-Final-URL': cur, 'Cache-Control': 'no-store' }) });
      }
      return json({ error: 'not_found' }, 404, origin);
    } catch (e) {
      return json({ error: 'worker_error', message: String(e && e.message || e) }, 502, origin);
    }
  }
};
