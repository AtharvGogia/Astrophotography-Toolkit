// Target search box: suggestions as you type, from /api/targets.
// Keyboard: ↑/↓ to move, Enter to pick, Esc to close.
'use strict';

const TargetSearch = (() => {
    // Round once to whole seconds / arcminutes, then split, so 59.6 s carries into the minute.
    const fmtRA = (deg) => {
        const total = Math.round((((deg % 360) + 360) % 360) / 15 * 3600) % 86400;
        const hh = Math.floor(total / 3600), mm = Math.floor(total / 60) % 60, ss = total % 60;
        return `${hh}h ${String(mm).padStart(2, '0')}m ${String(ss).padStart(2, '0')}s`;
    };
    const fmtDec = (deg) => {
        const total = Math.round(Math.abs(deg) * 60);
        return `${deg < 0 ? '−' : '+'}${Math.floor(total / 60)}° ${String(total % 60).padStart(2, '0')}′`;
    };
    const escapeHtml = (s) => String(s).replace(/[&<>"']/g,
        (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    function attach(input, list, info) {
        let items = [], active = -1, timer = null, seq = 0;
        let selected = null;          // {name, ra, dec, ...} once the user picks a suggestion

        function close() {
            list.hidden = true;
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
            active = -1;
        }

        function setActive(i) {
            const els = list.querySelectorAll('li');
            els.forEach((el, j) => el.setAttribute('aria-selected', String(j === i)));
            active = i;
            if (els[i]) {
                input.setAttribute('aria-activedescendant', els[i].id);
                els[i].scrollIntoView({ block: 'nearest' });
            }
        }

        function render(query) {
            if (!items.length) {
                list.innerHTML = `<li class="combo-empty">No match in the built-in catalogs. Press Calculate to search online.</li>`;
            } else {
                list.innerHTML = items.map((t, i) => {
                    const where = t.kind === 'Constellation' ? 'Constellation' : `${t.kind} in ${t.constellation}`;
                    const mag = t.mag != null ? `<span class="mag">mag ${t.mag.toFixed(1)}</span>` : '';
                    return `<li id="target-opt-${i}" role="option" aria-selected="false" data-i="${i}">
                        <span class="opt-name">${escapeHtml(t.name)}</span>
                        <span class="opt-meta">${escapeHtml(where)}${mag}</span></li>`;
                }).join('');
            }
            list.hidden = false;
            input.setAttribute('aria-expanded', 'true');
            active = -1;
        }

        function pick(i) {
            const t = items[i];
            if (!t) return;
            selected = t;
            input.value = t.name;
            info.textContent = `${t.kind === 'Constellation' ? 'Centre of the constellation' : t.kind} · RA ${fmtRA(t.ra)}, Dec ${fmtDec(t.dec)}`;
            close();
            input.dispatchEvent(new CustomEvent('target-picked', { detail: t }));
        }

        input.addEventListener('input', () => {
            selected = null;
            info.textContent = '';
            clearTimeout(timer);
            const q = input.value.trim();
            if (!q) { close(); return; }
            timer = setTimeout(async () => {
                const mine = ++seq;
                try {
                    const resp = await fetch(`/api/targets?q=${encodeURIComponent(q)}&limit=8`);
                    const data = await resp.json();
                    if (mine !== seq) return;          // a newer keystroke won
                    items = Array.isArray(data) ? data : [];
                    render(q);
                } catch (e) { close(); }
            }, 120);
        });

        input.addEventListener('keydown', (e) => {
            if (list.hidden) {
                if (e.key === 'ArrowDown' && input.value.trim()) input.dispatchEvent(new Event('input'));
                return;
            }
            if (e.key === 'ArrowDown') { e.preventDefault(); setActive(Math.min(items.length - 1, active + 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(Math.max(0, active - 1)); }
            else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); pick(active); }
            else if (e.key === 'Escape') { close(); }
        });

        list.addEventListener('mousedown', (e) => {   // mousedown so it fires before the input blurs
            const li = e.target.closest('li[data-i]');
            if (li) { e.preventDefault(); pick(Number(li.dataset.i)); }
        });
        list.addEventListener('mousemove', (e) => {
            const li = e.target.closest('li[data-i]');
            if (li && Number(li.dataset.i) !== active) setActive(Number(li.dataset.i));
        });
        input.addEventListener('blur', () => setTimeout(close, 100));

        return {
            // The picked catalog entry, if the box still shows its name.
            selection: () => (selected && input.value === selected.name ? selected : null),
            restore(t) { if (t && t.name) { items = [t]; pick(0); } },
        };
    }

    return { attach, fmtRA, fmtDec };
})();
