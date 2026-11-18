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
    function restoreFields(ids) {
        let saved = {};
        try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}'); } catch (e) { /* storage blocked */ }
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el && saved[id] !== undefined && saved[id] !== '') el.value = saved[id];
        }
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

    return { toDeg, toRad, npfTime, npfSimple, rule500, sensorPointDec, fovDeg,
             loadCameraPresets, restoreFields, saveFields, postJSON, drawSkyLines, loadSkyLines };
})();
