'use strict';

(() => {
    const $ = (id) => document.getElementById(id);
    const SVG = 'http://www.w3.org/2000/svg';
    const POLL_MS = 400;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    // ---- Optional lens hint ----------------------------------------------------------
    let cameras = [];
    fetch('/static/data/cameras.json').then((r) => r.json()).then((list) => {
        cameras = list;
        for (const cam of list) {
            const opt = document.createElement('option');
            opt.value = cam.name;
            opt.textContent = cam.name;
            $('cameraPreset').appendChild(opt);
        }
    }).catch(() => {});

    function fovHint() {
        const cam = cameras.find((c) => c.name === $('cameraPreset').value);
        const F = Number($('hintFocal').value);
        if (!cam || !(F > 0)) return null;
        return 2 * Math.atan(cam.sensor_width_mm / 2 / F) * 180 / Math.PI;
    }

    // ---- Progress -----------------------------------------------------------------------
    let timer = null;
    function startClock() {
        const t0 = Date.now();
        clearInterval(timer);
        $('elapsed').textContent = '0:00';
        timer = setInterval(() => {
            const s = Math.floor((Date.now() - t0) / 1000);
            $('elapsed').textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
        }, 500);
    }

    async function getJSON(url, options) {
        const resp = await fetch(url, options);
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);
        return data;
    }

    // ---- Overlay --------------------------------------------------------------------------
    function el(name, attrs, text) {
        const node = document.createElementNS(SVG, name);
        for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
        if (text != null) node.textContent = text;
        return node;
    }

    function drawOverlay(a) {
        const svg = $('overlay');
        svg.innerHTML = '';
        svg.setAttribute('viewBox', `0 0 ${a.width} ${a.height}`);
        // Sizes in image pixels, scaled so labels read the same on any photo size.
        const u = Math.max(a.width, a.height) / 1000;
        svg.style.setProperty('--u', u);
        const fs = 13 * u;

        const grid = el('g', { class: 'layer-grid', 'data-layer': 'grid' });
        for (const line of a.grid) {
            const pts = line.points.map((p) => p.join(',')).join(' ');
            grid.appendChild(el('polyline', { points: pts, class: `grid-${line.kind}` }));
            const [x, y] = line.points[0];
            const tx = Math.min(Math.max(x, 4 * u), a.width - 60 * u), ty = Math.min(Math.max(y, 14 * u), a.height - 6 * u);
            grid.appendChild(el('text', { x: tx + 4 * u, y: ty - 4 * u, 'font-size': fs * 0.8, class: 'grid-label' }, line.label));
        }

        const cons = el('g', { class: 'layer-constellations', 'data-layer': 'constellations' });
        for (const line of a.lines || []) {
            cons.appendChild(el('polyline', { points: line.points.map((p) => p.join(',')).join(' '), class: 'con-line' }));
        }
        for (const c of a.constellations) {
            cons.appendChild(el('text', { x: c.x, y: c.y, 'font-size': fs * (c.share > 0.25 ? 1.6 : 1.2),
                                          'text-anchor': 'middle', class: 'con-label' }, c.name.toUpperCase()));
        }

        // Labels sit to the right of their marker, or to the left near the right-hand edge.
        // Items arrive most important first; a label that would overlap one already placed is
        // skipped (the marker stays, and its name shows on hover).
        const placed = [];
        const overlaps = (b) => placed.some((p) => b.x0 < p.x1 && b.x1 > p.x0 && b.y0 < p.y1 && b.y1 > p.y0);
        const label = (x, y, r, text, size, cls) => {
            const flip = x > a.width * 0.8;
            const w = text.length * size * 0.56, tx = flip ? x - r - 4 * u : x + r + 4 * u;
            const box = { x0: flip ? tx - w : tx, x1: flip ? tx : tx + w, y0: y - size * 0.85, y1: y + size * 0.25 };
            if (overlaps(box)) return null;
            placed.push(box);
            return el('text', { x: tx, y, 'font-size': size, 'text-anchor': flip ? 'end' : 'start', class: cls }, text);
        };
        const marker = (shape, title) => { shape.appendChild(el('title', {}, title)); return shape; };

        const stars = el('g', { class: 'layer-stars', 'data-layer': 'stars' });
        const dsos = el('g', { class: 'layer-dsos', 'data-layer': 'dsos' });
        // Bright stars get first claim on label space, then deep-sky objects, then fainter stars.
        const queue = [
            ...a.stars.filter((s) => s.mag < 2).map((s) => ['star', s]),
            ...a.dsos.map((d) => ['dso', d]),
            ...a.stars.filter((s) => s.mag >= 2).map((s) => ['star', s]),
        ];
        for (const [kind, o] of queue) {
            if (kind === 'dso') {
                const r = Math.max(o.r, 7 * u);
                dsos.appendChild(marker(el('circle', { cx: o.x, cy: o.y, r, class: 'dso-ring' }), `${o.label} (${o.kind})`));
                const t = label(o.x, o.y + fs * 0.35, r, o.label.replace(' · ', '  '), fs, 'dso-label');
                if (t) dsos.appendChild(t);
            } else {
                const r = (o.mag < 1 ? 11 : o.mag < 2.5 ? 9 : 7) * u;
                stars.appendChild(marker(el('circle', { cx: o.x, cy: o.y, r, class: 'star-ring' }), `${o.full}, mag ${o.mag.toFixed(1)}`));
                const t = label(o.x, o.y - r * 0.6, r - 1 * u, o.label, fs * 0.95, 'star-label');
                if (t) stars.appendChild(t);
            }
        }

        // Draw order: grid at the back, constellation names, then objects on top.
        for (const g of [grid, cons, dsos, stars]) svg.appendChild(g);
        syncLayers();
    }

    function syncLayers() {
        for (const btn of document.querySelectorAll('.layer')) {
            const on = btn.getAttribute('aria-pressed') === 'true';
            const g = $('overlay').querySelector(`g[data-layer="${btn.dataset.layer}"]`);
            if (g) g.style.display = on ? '' : 'none';
        }
    }
    for (const btn of document.querySelectorAll('.layer')) {
        btn.addEventListener('click', () => {
            btn.setAttribute('aria-pressed', String(btn.getAttribute('aria-pressed') !== 'true'));
            syncLayers();
        });
    }

    // ---- Results -----------------------------------------------------------------------
    function showResult(res) {
        const s = res.solution, a = res.annotations;
        const fmtRA = TargetSearch.fmtRA, fmtDec = TargetSearch.fmtDec;
        const stats = [
            ['Centre RA', fmtRA(s.ra)],
            ['Centre Dec', fmtDec(s.dec)],
            ['Field', `${s.fov_w.toFixed(1)}° × ${s.fov_h.toFixed(1)}°`],
            ['Rotation', `${s.rotation.toFixed(1)}°`],
            ['Pixel scale', `${s.scale_arcsec.toFixed(1)}″/px`],
            ['Stars matched', `${s.matched}`],
            ['Accuracy', `${(s.rms_arcsec / s.scale_arcsec).toFixed(1)} px`],
            ['Solved in', `${s.seconds.toFixed(1)} s`],
        ];
        const dl = $('solutionStats');
        dl.innerHTML = '';
        for (const [k, v] of stats) {
            const div = document.createElement('div');
            const dt = document.createElement('dt'); dt.textContent = k;
            const dd = document.createElement('dd'); dd.textContent = v;
            div.append(dt, dd);
            dl.appendChild(div);
        }

        const rows = $('objectRows');
        rows.innerHTML = '';
        const add = (name, type, con) => {
            const tr = document.createElement('tr');
            for (const text of [name, type, con]) {
                const td = document.createElement('td');
                td.textContent = text || '';
                tr.appendChild(td);
            }
            rows.appendChild(tr);
        };
        for (const d of a.dsos) add(d.label, d.kind, d.constellation);
        for (const st of a.stars) add(st.full, `Star, mag ${st.mag.toFixed(1)}`, st.constellation);
        for (const c of a.constellations) add(c.name, 'Constellation', '');
        if (!rows.children.length) add('Nothing from the built-in catalogs in this field.', '', '');

        $('photoCaption').textContent =
            `${res.filename}. Labels come from the HYG and OpenNGC catalogs, placed using the solved position` +
            `${s.parity_flipped ? ' (the photo appears mirrored)' : ''}.`;
        drawOverlay(a);
        $('output').hidden = false;
    }

    // ---- Submit ---------------------------------------------------------------------------
    $('analyzeForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        $('analyzerError').textContent = '';
        const file = $('imageUpload').files[0];
        if (!file) {
            $('analyzerError').textContent = 'Choose a photo first.';
            return;
        }

        const btn = $('analyzeBtn');
        btn.disabled = true;
        btn.textContent = 'Working…';
        $('output').hidden = true;
        $('progress').hidden = false;
        $('progressBar').value = 0;
        $('progressMsg').textContent = `Sending ${file.name} to the solver…`;
        startClock();

        try {
            const form = new FormData();
            form.append('image', file);
            const hint = fovHint();
            if (hint) form.append('fov_hint', hint.toFixed(2));
            const { job_id: jobId } = await getJSON('/api/analyze', { method: 'POST', body: form });

            let job;
            for (;;) {
                await sleep(POLL_MS);
                job = await getJSON(`/api/jobs/${jobId}`);
                $('progressBar').value = Math.round(job.progress * 100);
                $('progressMsg').textContent = job.message;
                if (job.state === 'done' || job.state === 'failed') break;
            }
            if (job.state === 'failed') throw new Error(job.error || 'The photo could not be solved.');

            const img = $('photo');
            img.src = job.result.preview;
            await img.decode().catch(() => {});
            showResult(job.result);
            $('progress').hidden = true;
            $('output').scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (err) {
            $('analyzerError').textContent = err.message;
            $('progressMsg').textContent = 'Stopped.';
        } finally {
            clearInterval(timer);
            btn.disabled = false;
            btn.textContent = 'Analyze';
        }
    });
})();
