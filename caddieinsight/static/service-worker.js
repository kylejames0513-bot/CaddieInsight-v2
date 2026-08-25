/* CaddieInsight v2 service worker.
   Static shell is cache-first; pages are network-only with a plain,
   readable offline card as the fallback — the app never pretends a stale
   bag is a live one. */

const CACHE = "ci-static-v1";
const SHELL = [
  "/static/app.css",
  "/static/fonts/barlow-latin-400.woff2",
  "/static/fonts/barlow-latin-500.woff2",
  "/static/fonts/barlow-condensed-latin-600.woff2",
  "/static/fonts/dm-mono-latin-400.woff2",
  "/static/fonts/dm-mono-latin-500.woff2",
  "/static/brand/caddieinsight-logo.png",
  "/static/brand/caddieinsight-logo-inverse.png",
];

const OFFLINE_PAGE = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Offline · CaddieInsight</title>
<style>
  body { margin: 0; background: #f2f2f3; color: #1d1f20;
         font: 400 1rem/1.55 Barlow, "Helvetica Neue", Arial, sans-serif;
         display: grid; place-items: center; min-height: 100vh; }
  main { border: 1px solid #b7b7ba; padding: 32px; max-width: 420px; margin: 20px; }
  h1 { font-size: 1.4rem; text-transform: uppercase; margin: 0 0 10px; }
</style></head>
<body><main>
<h1>No signal out here</h1>
<p>CaddieInsight needs a connection to show live numbers — it will not
show you a stale bag and call it current. Reconnect and reload.</p>
</main></body></html>`;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin === location.origin && url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(event.request).then(
        (hit) =>
          hit ||
          fetch(event.request).then((response) => {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
            return response;
          })
      )
    );
    return;
  }
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(
        () =>
          new Response(OFFLINE_PAGE, {
            headers: { "Content-Type": "text/html; charset=utf-8" },
          })
      )
    );
  }
});
