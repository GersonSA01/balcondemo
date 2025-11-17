// Service Worker placeholder
// Este archivo existe para evitar errores 404 cuando el navegador intenta cargar un service worker
// Si no necesitas un service worker, puedes dejar este archivo vacío o eliminarlo
// y desregistrar el service worker desde las DevTools del navegador

// Desregistrar cualquier service worker anterior si existe
self.addEventListener('install', function(event) {
    // No hacer nada, solo instalar
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    // Limpiar service workers antiguos
    event.waitUntil(
        caches.keys().then(function(cacheNames) {
            return Promise.all(
                cacheNames.map(function(cacheName) {
                    return caches.delete(cacheName);
                })
            );
        }).then(function() {
            // Desregistrar este service worker
            return self.registration.unregister();
        })
    );
});

// No interceptar ninguna petición
self.addEventListener('fetch', function(event) {
    // Dejar que todas las peticiones pasen sin interceptar
    return;
});

