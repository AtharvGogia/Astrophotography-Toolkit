// Service worker: keeps the site usable in the field without a connection.
//
// - Pages: from the network when it answers (within a few seconds), else the saved copy.
// - The site's CSS, scripts and images: from the cache (their URLs change when they change);
//   unversioned files (the camera list) refresh in the background.
// - Web fonts: from the cache, refreshed in the background.
// - API requests are left alone; the pages fall back to their saved answers themselves.
'use strict';

const CACHE = 'astro-toolkit-v1';
const PAGES = ['/', '/planner', '/exposure', '/framing', '/analyzer'];
const PAGE_WAIT_MS = 6000;

// On install, save every page and the files each one loads.
self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE);
        const assets = new Set(['/manifest.webmanifest', '/favicon.ico']);
        for (const page of PAGES) {
            try {
                const resp = await fetch(page, { cache: 'no-store' });
                if (!resp.ok) continue;
                const html = await resp.clone().text();
                await cache.put(page, resp);
                for (const m of html.matchAll(/(?:src|href)="(\/static\/[^"]+)"/g)) assets.add(m[1].replace(/&amp;/g, '&'));
            } catch (e) { /* offline during install: try again next time */ }
        }
        await Promise.all([...assets].map(async (url) => {
            try {
                const resp = await fetch(url);
                if (resp.ok) await cache.put(url, resp);
            } catch (e) { /* skip */ }
        }));
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
        await self.clients.claim();
    })());
});

function withTimeout(promise, ms) {
    return new Promise((resolve, reject) => {
        const t = setTimeout(() => reject(new Error('timeout')), ms);
        promise.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
    });
}

async function page(request) {
    const cache = await caches.open(CACHE);
    const path = new URL(request.url).pathname;
    try {
        const resp = await withTimeout(fetch(request), PAGE_WAIT_MS);
        if (resp.ok && PAGES.includes(path)) cache.put(path, resp.clone());
        return resp;
    } catch (e) {
        const keep = await cache.match(path) || await cache.match('/');
        if (keep) return keep;
        throw e;
    }
}

async function cacheFirst(request) {
    const cache = await caches.open(CACHE);
    const keep = await cache.match(request);
    if (keep) return keep;
    const resp = await fetch(request);
    if (resp.ok || resp.type === 'opaque') cache.put(request, resp.clone());
    return resp;
}

async function staleWhileRevalidate(request) {
    const cache = await caches.open(CACHE);
    const keep = await cache.match(request);
    const fresh = fetch(request).then((resp) => {
        if (resp.ok || resp.type === 'opaque') cache.put(request, resp.clone());
        return resp;
    }).catch(() => keep);
    return keep || fresh;
}

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);
    if (req.mode === 'navigate' && url.origin === self.location.origin) {
        event.respondWith(page(req));
    } else if (url.origin === self.location.origin && (url.pathname.startsWith('/static/')
               || url.pathname === '/manifest.webmanifest' || url.pathname === '/favicon.ico')) {
        // Versioned URLs (?v=) never change, so the cache is enough; others refresh in the background.
        event.respondWith(url.searchParams.has('v') ? cacheFirst(req) : staleWhileRevalidate(req));
    } else if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
        event.respondWith(staleWhileRevalidate(req));
    }
});
