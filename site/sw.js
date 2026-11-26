const cacheName = "chtf26-location-BUILD_REVISION";
const scope = self.registration.scope;
const shell = new URL("index.html", scope).href;
const catalog = ["index.html", "data.json", "products.json", "location.css", "venue.js", "location.js", "meeting.js"]
  .map(path => new URL(path, scope).href);

self.addEventListener("install", event => {
  event.waitUntil((async()=>{
    const cache=await caches.open(cacheName);
    await cache.addAll(catalog.map(url=>new Request(url,{cache:"reload"})));
    if((await caches.keys()).some(key=>key!==cacheName&&/^chtf26-(field|location)-/.test(key)))await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => /^chtf26-(field|location)-/.test(key) && key !== cacheName)
    .map(key => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  url.search = "";
  url.hash = "";
  const key = event.request.mode === "navigate" && url.href === scope ? shell : url.href;
  if (catalog.includes(key)) {
    event.respondWith(caches.open(cacheName).then(cache => cache.match(key)).then(response =>
      response || fetch(event.request)));
  }
});

// 집합 알림: 서버는 내용 없는 푸시만 보내고, 문구는 페이지가 남겨 둔 마지막 상태로 만든다.
self.addEventListener("push", event => {
  event.waitUntil((async()=>{
    let state = {};
    try { state = await (await (await caches.open("chtf26-meeting")).match("meeting-state")).json(); } catch {}
    const left = state.due ? Math.round((state.due - Date.now()) / 60000) : null;
    const walk = Number.isFinite(state.dist) && state.dist !== null
      ? `하차 지점까지 약 ${Math.round(state.dist / 10) * 10}m · 도보 약 ${Math.max(1, Math.round(state.dist * 1.3 / 75))}분` : "하차 지점을 확인하세요";
    await self.registration.showNotification(left !== null && left > 0 ? `버스 집합 ${left}분 전` : "버스 집합 시간", {
      body: walk, tag: "chtf26-meeting", renotify: true
    });
  })());
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil((async()=>{
    const url = new URL("#meeting", scope).href;
    const open = (await clients.matchAll({ type: "window", includeUncontrolled: true }))[0];
    if (open) { await open.focus(); return open.navigate(url); }
    return clients.openWindow(url);
  })());
});
