const cacheName = "chtf26-location-BUILD_REVISION";
const scope = self.registration.scope;
const shell = new URL("index.html", scope).href;
const catalog = ["index.html", "data.json", "products.json", "location.css", "venue.js", "location.js"]
  .map(path => new URL(path, scope).href);

self.addEventListener("install", event => {
  event.waitUntil((async()=>{
    const cache=await caches.open(cacheName);
    await cache.addAll(catalog.map(url=>new Request(url,{cache:"reload"})));
    if((await caches.keys()).some(key=>key.startsWith("chtf26-field-")))await self.skipWaiting();
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
