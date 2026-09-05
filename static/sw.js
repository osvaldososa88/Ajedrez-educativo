const CACHE_NAME = 'ajedrez-educativo-v1';
const STATIC_ASSETS = [
  '/static/css/styles.css',
  '/static/js/chess_ui.js',
  '/static/js/chessboard_app.js',
  '/static/js/analysis_app.js',
  '/static/js/training_app.js',
  '/static/js/training_creator.js',
  '/static/js/pwa.js',
  '/static/js/notifications.js',
  '/static/js/chat.js',
  '/manifest.json',
  '/static/img/pwa-icon-192.png',
  '/static/img/pwa-icon-512.png',
  '/static/img/pwa-icon-maskable.png'
];

// Instalación: cachear recursos estáticos
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activación: limpiar caches antiguos
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => name !== CACHE_NAME)
            .map((name) => caches.delete(name))
        );
      })
      .then(() => self.clients.claim())
  );
});

// Estrategia: network-first para navegaciones, cache-first para estáticos
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Solo manejar peticiones del mismo origen
  if (url.origin !== self.location.origin) return;

  // Para navegaciones (HTML): network-first con fallback a cache
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match('/')))
    );
    return;
  }

  // Para estáticos: cache-first con actualización en background
  if (request.destination === 'style' || request.destination === 'script' || request.destination === 'image' || request.destination === 'font') {
    event.respondWith(
      caches.match(request).then((cached) => {
        const fetchPromise = fetch(request)
          .then((response) => {
            if (response && response.status === 200) {
              const clone = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
            }
            return response;
          })
          .catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }

  // Para API: network-only (no cachear respuestas dinámicas)
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/games/') || url.pathname.startsWith('/analysis/')) {
    return;
  }
});