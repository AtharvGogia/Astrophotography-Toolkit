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
    // Times show in the observing site's time zone (saved with the location), so a plan for a
    // trip abroad reads in the times you'll see there. Without one, this device's zone is used.
    const deviceZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
    const zoneOk = {};
    function knownZone(tz) {             // an older browser may not know a newer zone name
        if (!(tz in zoneOk)) {
            try { new Intl.DateTimeFormat('en-US', { timeZone: tz }); zoneOk[tz] = true; }
            catch (e) { zoneOk[tz] = false; }
        }
        return zoneOk[tz];
    }
    function siteZone() {
        try {
            const loc = JSON.parse(localStorage.getItem('astro-location') || 'null');
            if (loc && typeof loc.tz === 'string' && knownZone(loc.tz)) return loc.tz;
        } catch (e) { /* storage blocked */ }
        return null;
    }
    const timeZoneName = () => siteZone() || deviceZone();
    const FORMATS = {
        time: { hour: '2-digit', minute: '2-digit', hour12: false },
        day: { weekday: 'short', day: 'numeric', month: 'short' },
        parts: { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' },
    };
    const formatters = {};
    function formatter(kind) {
        const zone = timeZoneName(), key = `${kind}|${zone}`;
        if (!formatters[key]) {
            const locale = kind === 'parts' ? 'en-US' : undefined;
            try { formatters[key] = new Intl.DateTimeFormat(locale, { ...FORMATS[kind], timeZone: zone }); }
            catch (e) { formatters[key] = new Intl.DateTimeFormat(locale, FORMATS[kind]); }   // unknown zone name
        }
        return formatters[key];
    }
    const fmtTime = (ms) => (ms == null ? '—' : formatter('time').format(new Date(ms)));
    const fmtDay = (ms) => formatter('day').format(new Date(ms));

    // Calendar date and clock time of a moment, in the display zone.
    function zoned(ms) {
        const p = {};
        for (const part of formatter('parts').formatToParts(new Date(ms))) p[part.type] = part.value;
        return { y: +p.year, m: +p.month, d: +p.day, h: +p.hour % 24, min: +p.minute, s: +p.second };
    }
    // The moment a wall-clock time (y, m 1-12, d, hour) happens in the display zone.
    // A time skipped by a clock change (e.g. 00:00 on a midnight spring-forward) gives the moment
    // just after the jump, so the date never slips back a day.
    function offsetAt(t) {
        const z = zoned(t);
        return Date.UTC(z.y, z.m - 1, z.d, z.h, z.min, z.s) - t;
    }
    function zonedToMs(y, m, d, h) {
        const want = Date.UTC(y, m - 1, d, h);
        const o1 = offsetAt(want), t1 = want - o1;
        const o2 = offsetAt(t1);
        if (o1 === o2) return t1;
        const t2 = want - o2;
        if (offsetAt(t2) === o2) return t2;
        return Math.max(t1, t2);
    }

    // Noon at the site on the night that is "tonight" now: before noon, that is still last night.
    function nightStart(dateStr) {
        let y, m, d;
        if (dateStr) {
            [y, m, d] = dateStr.split('-').map(Number);
        } else {
            const now = zoned(Date.now());
            ({ y, m, d } = now);
            if (now.h < 12) {
                const prev = new Date(Date.UTC(y, m - 1, d) - 86400000);
                [y, m, d] = [prev.getUTCFullYear(), prev.getUTCMonth() + 1, prev.getUTCDate()];
            }
        }
        return new Date(zonedToMs(y, m, d, 12));
    }
    // The site's calendar date of a moment, as YYYY-MM-DD.
    function isoDate(date) {
        const z = zoned(date.getTime());
        return `${z.y}-${String(z.m).padStart(2, '0')}-${String(z.d).padStart(2, '0')}`;
    }
    const utcIso = (d) => d.toISOString().replace('Z', '').split('.')[0];

    // ---- Offline: the last answers, kept for use in the field -----------------------------------
    // Pages save their last good answer; when a request fails for want of a connection they show
    // it again, with a note saying when it was saved.
    const OFFLINE_KEY = 'astro-offline-';
    const saved = {
        put(kind, data) {
            try { localStorage.setItem(OFFLINE_KEY + kind, JSON.stringify({ at: Date.now(), data })); } catch (e) { /* full or blocked */ }
        },
        get(kind) {
            try { return JSON.parse(localStorage.getItem(OFFLINE_KEY + kind) || 'null'); } catch (e) { return null; }
        },
    };
    // fetch() rejects with a TypeError when there is no connection (not for HTTP errors).
    const isOffline = (err) => !navigator.onLine || err instanceof TypeError;
    function offlineNote(el, at, what) {
        if (!el) return;
        if (at == null) { el.hidden = true; return; }
        el.textContent = `No connection: showing the ${what} saved ${fmtDay(at)}, ${fmtTime(at)}.`;
        el.hidden = false;
    }

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
             fmtTime, fmtDay, timeZoneName, siteZone, deviceZone, zoned, zonedToMs, saved, isOffline, offlineNote, nightStart, isoDate, utcIso, moonSVG, revealOnPhone,
             linkTargetInputs, targetLabel };
})();
