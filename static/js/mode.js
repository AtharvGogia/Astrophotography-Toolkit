// Low-light (red) mode toggle, remembered per browser.
'use strict';
(() => {
    const KEY = 'astro-low-light';
    const root = document.documentElement;
    const btn = document.getElementById('modeToggle');
    const meta = document.querySelector('meta[name="theme-color"]');
    const sync = () => {
        const on = root.dataset.mode === 'lowlight';
        if (btn) btn.setAttribute('aria-pressed', String(on));
        // The phone's address bar follows the page, so it doesn't glare at night.
        if (meta) meta.content = on ? '#0a0000' : '#100e0b';
    };
    sync();
    if (!btn) return;
    btn.addEventListener('click', () => {
        const on = root.dataset.mode !== 'lowlight';
        const apply = () => { if (on) root.dataset.mode = 'lowlight'; else delete root.dataset.mode; sync(); };
        if (document.startViewTransition) document.startViewTransition(apply); else apply();
        try { localStorage.setItem(KEY, on ? '1' : '0'); } catch (e) { /* storage blocked */ }
        sync();
    });
})();
