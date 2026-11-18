// Low-light (red) mode toggle, remembered per browser.
'use strict';
(() => {
    const KEY = 'astro-low-light';
    const root = document.documentElement;
    const btn = document.getElementById('modeToggle');
    const sync = () => btn && btn.setAttribute('aria-pressed', String(root.dataset.mode === 'lowlight'));
    sync();
    if (!btn) return;
    btn.addEventListener('click', () => {
        const on = root.dataset.mode !== 'lowlight';
        if (on) root.dataset.mode = 'lowlight'; else delete root.dataset.mode;
        try { localStorage.setItem(KEY, on ? '1' : '0'); } catch (e) { /* storage blocked */ }
        sync();
    });
})();
