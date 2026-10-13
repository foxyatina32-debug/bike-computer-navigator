// ВелоНав: приложение открывается без интернета. Плитки карт хранятся отдельно, в IndexedDB.
const V='velonav-v2';
const SHELL=['./','./index.html','./manifest.webmanifest','./icon-180.png','./icon-512.png'];
const LIBS=['https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css','https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'];
self.addEventListener('install',e=>{e.waitUntil((async()=>{const c=await caches.open(V);await c.addAll(SHELL);
  for(const u of LIBS){try{await c.add(new Request(u,{mode:'cors'}))}catch(_){}}self.skipWaiting()})())});
self.addEventListener('activate',e=>{e.waitUntil((async()=>{for(const k of await caches.keys())if(k!==V)await caches.delete(k);await self.clients.claim()})())});
self.addEventListener('fetch',e=>{const r=e.request;if(r.method!=='GET')return;const u=new URL(r.url);
  const own=u.origin===location.origin,lib=LIBS.includes(r.url)||u.host==='fonts.googleapis.com'||u.host==='fonts.gstatic.com';
  if(!own&&!lib)return;
  if(r.mode==='navigate'||own){ // сначала сеть, чтобы обновления приходили сразу; без сети — из кэша
    e.respondWith(fetch(r).then(res=>{if(res.ok){const cp=res.clone();caches.open(V).then(c=>c.put(r,cp))}return res})
      .catch(()=>caches.match(r,{ignoreSearch:true}).then(m=>m||caches.match('./index.html'))));return}
  e.respondWith(caches.match(r).then(m=>m||fetch(r).then(res=>{const cp=res.clone();caches.open(V).then(c=>c.put(r,cp));return res})))});
