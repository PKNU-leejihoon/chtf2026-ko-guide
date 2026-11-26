const cacheName = "chtf26-field-BUILD_REVISION";
const scope = self.registration.scope;
const shell = new URL("index.html", scope).href;
const catalog = [shell, new URL("data.json", scope).href, new URL("products.json", scope).href];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(cacheName).then(cache =>
    cache.addAll(catalog.map(url => new Request(url, { cache: "reload" })))));
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => key.startsWith("chtf26-field-") && key !== cacheName)
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
