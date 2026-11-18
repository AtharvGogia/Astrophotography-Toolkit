// Serves the toolkit on its own domain by forwarding every request to the Cloud Run service.
// Cloud Run picks the service by the Host header, so a plain DNS record pointing at it does not
// work; this Worker sends the request on with Cloud Run's own host instead.
//
// Cloud Run scales to zero, so the first visit after a quiet spell waits while a container
// starts. When a page takes longer than a moment, the visitor gets a small "starting up" page
// that waits for the app's /health and then loads what they asked for.

const ORIGIN = "https://astro-toolkit-356863378440.asia-south1.run.app";
const PATIENCE_MS = 2500;

function forward(request: Request, incoming: URL): Promise<Response> {
  const target = new URL(incoming.pathname + incoming.search, ORIGIN);
  const headers = new Headers(request.headers);
  headers.set("X-Forwarded-Host", incoming.host);
  headers.set("X-Forwarded-Proto", "https");
  return fetch(target, { method: request.method, headers, body: request.body, redirect: "manual" });
}

function keepRedirectsHere(response: Response, host: string): Response {
  // Redirects from the app name Cloud Run's host; point them back at this domain.
  const location = response.headers.get("Location");
  if (!location || !location.startsWith(ORIGIN)) return response;
  const out = new Response(response.body, response);
  out.headers.set("Location", location.replace(ORIGIN, `https://${host}`));
  return out;
}

export default {
  async fetch(request: Request, _env: unknown, ctx: ExecutionContext): Promise<Response> {
    const incoming = new URL(request.url);
    const upstream = forward(request, incoming).then((r) => keepRedirectsHere(r, incoming.host));

    const wantsPage = request.method === "GET" && (request.headers.get("Accept") || "").includes("text/html");
    if (!wantsPage) return upstream;

    const late = new Promise<null>((resolve) => setTimeout(() => resolve(null), PATIENCE_MS));
    const first = await Promise.race([upstream, late]);
    if (first) return first;

    // Still starting: let the request carry on waking the container, and show the waiting page.
    ctx.waitUntil(upstream.then(() => undefined, () => undefined));
    return new Response(STARTING_PAGE, {
      status: 503,
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Retry-After": "5" },
    });
  },
};

// Same palette as the site ("Dark sky reserve"), and the red low-light mode when it is on.
const STARTING_PAGE = `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#100e0b">
<title>Starting up · Astrophotography Toolkit</title>
<script>try{if(localStorage.getItem('astro-low-light')==='1')document.documentElement.dataset.mode='lowlight'}catch(e){}</script>
<style>
  :root { --bg:#100e0b; --text:#e6dccb; --dim:#b0a592; --accent:#d98b52; --rule:#3a3127; }
  :root[data-mode="lowlight"] { --bg:#0a0000; --text:#d23a2a; --dim:#b82e20; --accent:#b8281c; --rule:#3a0c0c; }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body { display: grid; place-items: center; padding: 24px; background: var(--bg); color: var(--text);
         font: 400 1rem/1.55 "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 30em; text-align: center; }
  h1 { margin: 0 0 .6rem; font: 400 1.75rem/1.2 Fraunces, Georgia, serif; }
  p { margin: 0 0 .5rem; color: var(--dim); }
  .ring { width: 34px; height: 34px; margin: 0 auto 1.4rem; border-radius: 50%;
          border: 2px solid var(--rule); border-top-color: var(--accent); animation: spin 900ms linear infinite; }
  .time { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: .875rem; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .ring { animation-duration: 2.4s; } }
</style></head>
<body><main role="status" aria-live="polite">
  <div class="ring" aria-hidden="true"></div>
  <h1>Firing up the server…</h1>
  <p>The toolkit sleeps on Google Cloud when nobody is using it, so the first visit takes a few
     seconds while it starts. This page loads by itself when it's ready.</p>
  <p class="time" id="t"></p>
</main>
<script>
  const t0 = Date.now(), el = document.getElementById('t');
  setInterval(() => { el.textContent = Math.round((Date.now() - t0) / 1000) + ' s'; }, 1000);
  async function wait() {
    for (;;) {
      try {
        const ctl = new AbortController(); const stop = setTimeout(() => ctl.abort(), 20000);
        const r = await fetch('/health', { cache: 'no-store', signal: ctl.signal });
        clearTimeout(stop);
        if (r.ok) { location.reload(); return; }
      } catch (e) { /* still starting */ }
      await new Promise((ok) => setTimeout(ok, 1500));
    }
  }
  wait();
</script>
</body></html>`;
