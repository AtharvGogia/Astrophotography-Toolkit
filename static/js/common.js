// Shared helpers for the calculator pages: maths, camera presets, form state.
'use strict';

const Astro = (() => {
    const toDeg = (rad) => rad * 180 / Math.PI;
    const toRad = (deg) => deg * Math.PI / 180;

    // Declinations closer to a pole than this are clamped: 1/cos(dec) blows up at ±90°.
    const MAX_ABS_DEC = 89;

    // Full NPF rule (Frédéric Michaud, Société Astronomique du Havre), k = 1:
    //   t = (16.856·N + 0.0997·F + 13.713·p) / (F · cos δ)
    function npfTime(N, F, p, decDeg) {
        const dec = Math.max(-MAX_ABS_DEC, Math.min(MAX_ABS_DEC, decDeg));
        return (16.856 * N + 0.0997 * F + 13.713 * p) / (F * Math.cos(toRad(dec)));
    }

    // Simplified NPF, which assumes a declination of about 60°.
    const npfSimple = (N, F, p) => (35 * N + 30 * p) / F;

    // 500 rule against the full-frame diagonal (43.27 mm).
    const rule500 = (F, sensorDiagMm) => 500 / (F * 43.27 / sensorDiagMm);

    // Declination of a point on the sensor via the inverse gnomonic (TAN) projection.
    // (x, y) are offsets from the sensor centre in mm, x right and y up. Rotation is the
    // position angle of the frame's top from north through east (0 = north up, east left).
    function sensorPointDec(centerDecDeg, xMm, yMm, F, rotationDeg) {
        const th = toRad(rotationDeg);
        const xi = (-xMm * Math.cos(th) + yMm * Math.sin(th)) / F;   // towards east
        const eta = (xMm * Math.sin(th) + yMm * Math.cos(th)) / F;   // towards north
        const d0 = toRad(centerDecDeg);
        const s = (Math.sin(d0) + eta * Math.cos(d0)) / Math.sqrt(1 + xi * xi + eta * eta);
        return toDeg(Math.asin(Math.max(-1, Math.min(1, s))));
    }

    const fovDeg = (sizeMm, F) => toDeg(2 * Math.atan(sizeMm / 2 / F));

    // ---- Camera presets -------------------------------------------------
    async function loadCameraPresets(select, onPick) {
        let cameras = [];
        try {
            const resp = await fetch('/static/data/cameras.json');
            cameras = await resp.json();
        } catch (e) {
            console.warn('Could not load camera presets', e);
            return;
        }
        for (const cam of cameras) {
            const opt = document.createElement('option');
            opt.value = cam.name;
            opt.textContent = cam.name;
            select.appendChild(opt);
        }
        select.addEventListener('change', () => {
            const cam = cameras.find((c) => c.name === select.value);
            if (cam) onPick({
                widthPx: cam.width_px,
                heightPx: cam.height_px,
                pitchUm: +(cam.sensor_width_mm / cam.width_px * 1000).toFixed(2),
            });
        });
    }

    // ---- Remember form values between visits and pages -------------------
    const STORE_KEY = 'astro-toolkit-form';
    // After a user-started calculation on a narrow screen, scroll the answer into view
    // (the form sits above it). Restored or automatic runs leave the page where it is.
    function revealOnPhone(el, form) {
        if (!el || !window.matchMedia('(max-width: 900px)').matches) return;
        if (form && !form.contains(document.activeElement)) return;
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        requestAnimationFrame(() => el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' }));
    }

    function linkTargetInputs(nameEl, raEl, decEl, box) {
        const clearCoords = () => {
            raEl.value = '';
            decEl.value = '';
            if (box) box.open = false;
        };
        nameEl.addEventListener('target-picked', clearCoords);
        nameEl.addEventListener('input', () => { if (nameEl.value.trim()) clearCoords(); });
        const clearName = () => {
            if (!raEl.value.trim() && !decEl.value.trim()) return;
            if (nameEl.value) {
                nameEl.value = '';
                nameEl.dispatchEvent(new Event('input', { bubbles: true }));   // also clears the search's pick
            }
        };
        raEl.addEventListener('input', clearName);
        decEl.addEventListener('input', clearName);
        // Saved state from before this rule may hold both: the name wins.
        if (nameEl.value.trim() && (raEl.value.trim() || decEl.value.trim())) clearCoords();
    }

    function targetLabel(picked, name, ra, dec, haveCoords) {
        const { fmtRA, fmtDec } = TargetSearch;
        if (haveCoords) return `RA ${fmtRA(ra)}, Dec ${fmtDec(dec)}`;
        if (picked) return `${picked.name.split(' · ')[0]} · RA ${fmtRA(picked.ra)}, Dec ${fmtDec(picked.dec)}`;
        return name;
    }

    function restoreFields(ids) {
        let saved = {};
        try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}'); } catch (e) { /* storage blocked */ }
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el && saved[id] !== undefined && saved[id] !== '') el.value = saved[id];
        }
        const box = document.getElementById('coordsBox');
        if (box && ['customRA', 'customDec'].some((id) => saved[id] !== undefined && saved[id] !== '')) box.open = true;
    }
    function saveFields(ids) {
        let saved = {};
        try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}'); } catch (e) { /* ignore */ }
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el) saved[id] = el.value;
        }
        try { localStorage.setItem(STORE_KEY, JSON.stringify(saved)); } catch (e) { /* ignore */ }
    }

    async function postJSON(url, payload) {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        return resp;
    }

    // Draw constellation figures ({width, height, lines: [{con, points}]}) into an <svg>.
    function drawSkyLines(svg, data) {
        const NS = 'http://www.w3.org/2000/svg';
        svg.innerHTML = '';
        svg.setAttribute('viewBox', `0 0 ${data.width} ${data.height}`);
        svg.style.setProperty('--u', Math.max(data.width, data.height) / 1000);
        for (const line of data.lines) {
            const pl = document.createElementNS(NS, 'polyline');
            pl.setAttribute('points', line.points.map((p) => p.join(',')).join(' '));
            pl.setAttribute('class', 'con-line');
            svg.appendChild(pl);
        }
    }

    // Fetch and draw the figures for a sky preview request (same payload as /api/skymap).
    async function loadSkyLines(svg, payload) {
        svg.innerHTML = '';
        try {
            const resp = await postJSON('/api/skylines', payload);
            if (resp.ok) drawSkyLines(svg, await resp.json());
        } catch (e) { /* lines are decoration; the preview still works without them */ }
    }

    // ---- Times and the Moon ---------------------------------------------------------------
    const timeFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
    const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
    const fmtTime = (ms) => (ms == null ? '—' : timeFmt.format(new Date(ms)));
    const fmtDay = (ms) => dayFmt.format(new Date(ms));
    const timeZoneName = () => Intl.DateTimeFormat().resolvedOptions().timeZone;

    // Local noon of the night that is "tonight" now: before noon, that is still last night.
    function nightStart(dateStr) {
        let d;
        if (dateStr) {
            const [y, m, day] = dateStr.split('-').map(Number);
            d = new Date(y, m - 1, day, 12, 0, 0);
        } else {
            const now = new Date();
            d = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12, 0, 0);
            if (now.getHours() < 12) d.setDate(d.getDate() - 1);
        }
        return d;
    }
    const isoDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const utcIso = (d) => d.toISOString().replace('Z', '').split('.')[0];

    // SVG of the Moon's lit shape (as seen from the northern hemisphere: waxing is lit on the right).
    function moonSVG(illum, waxing, size = 44) {
        const r = size / 2 - 1, c = size / 2;
        const rx = Math.abs(2 * illum - 1) * r;
        const right = waxing ? 1 : 0;                 // sweep flag for the lit limb
        const gibbous = illum > 0.5;
        const sweepBack = gibbous ? right : 1 - right;
        const lit = illum < 0.005 ? '' : illum > 0.995
            ? `<circle cx="${c}" cy="${c}" r="${r}" class="moon-lit"/>`
            : `<path class="moon-lit" d="M ${c} ${c - r} A ${r} ${r} 0 0 ${right} ${c} ${c + r} A ${rx} ${r} 0 0 ${sweepBack} ${c} ${c - r} Z"/>`;
        return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">` +
               `<circle cx="${c}" cy="${c}" r="${r}" class="moon-dark"/>${lit}</svg>`;
    }

    // Motion helpers. All of them do nothing visible under reduced motion or in a hidden tab,
    // so the final state is always what the page shows.
    const motion = (() => {
        const EASE = 'cubic-bezier(0.16, 1, 0.3, 1)';
        const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const still = () => reduced() || document.hidden;
        const easeOut = (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x));

        // A number that counts from its previous value (or 0) to the new one.
        function countTo(el, to, fmt, ms = 650) {
            const prev = parseFloat(el.dataset.v);
            el.dataset.v = String(to);
            cancelAnimationFrame(el._raf);
            if (still()) { el.textContent = fmt(to); return; }
            const from = Number.isFinite(prev) ? prev : 0, t0 = performance.now();
            const frame = (now) => {
                const k = Math.min(1, (now - t0) / ms);
                el.textContent = fmt(from + (to - from) * easeOut(k));
                if (k < 1) el._raf = requestAnimationFrame(frame);
            };
            el._raf = requestAnimationFrame(frame);
        }

        // Children of a list arriving one after another (total delay capped).
        function stagger(nodes, { step = 30, max = 400, ms = 320, delay = null } = {}) {
            if (still()) return;
            const list = [...nodes];
            const s = Math.min(step, max / Math.max(1, list.length));
            list.forEach((n, i) => n.animate(
                [{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }],
                { duration: ms, delay: delay ? delay(n, i) : i * s, easing: EASE, fill: 'backwards' }));
        }

        // The Moon's lit shape growing from new to tonight's phase.
        function sweepMoon(container, illum, waxing, size, ms = 900) {
            cancelAnimationFrame(container._raf);
            container.innerHTML = moonSVG(illum, waxing, size);
            if (still()) return;
            const t0 = performance.now();
            const frame = (now) => {
                const k = Math.min(1, (now - t0) / ms);
                container.innerHTML = moonSVG(illum * easeOut(k), waxing, size);
                if (k < 1) container._raf = requestAnimationFrame(frame);
            };
            container._raf = requestAnimationFrame(frame);
        }

        // A sky image and its constellation lines drifting in, as if the camera had just slewed there.
        function settleSky(els) {
            const pan = reduced() ? [{ opacity: 0 }, { opacity: 1 }]
                : [{ opacity: 0, transform: 'scale(1.06)' }, { opacity: 1, transform: 'none' }];
            for (const e of els) e.animate(pan, { duration: reduced() ? 200 : 1100, easing: EASE, fill: 'backwards' });
        }

        return { EASE, reduced, still, countTo, stagger, sweepMoon, settleSky };
    })();

    return { motion, toDeg, toRad, npfTime, npfSimple, rule500, sensorPointDec, fovDeg,
             loadCameraPresets, restoreFields, saveFields, postJSON, drawSkyLines, loadSkyLines,
             fmtTime, fmtDay, timeZoneName, nightStart, isoDate, utcIso, moonSVG, revealOnPhone,
             linkTargetInputs, targetLabel };
})();
