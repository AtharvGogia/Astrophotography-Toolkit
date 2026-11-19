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

    function showProgress(p) {
        if (typeof p.progress === 'number') $('progressBar').value = Math.round(p.progress * 100);
        if (p.message) $('progressMsg').textContent = p.message;
    }

    // Upload the photo. On hosts that solve inside the upload request, the reply streams one JSON
    // line per progress update and then the finished job; elsewhere it is one JSON object.
    async function postPhoto(form) {
        const resp = await fetch('/api/analyze', {
            method: 'POST', body: form, headers: { Accept: 'application/x-ndjson, application/json' } });
        const type = resp.headers.get('Content-Type') || '';
        if (!resp.ok || !type.includes('ndjson') || !resp.body) {
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);
            return data;
        }
        const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
        let buf = '', last = null;
        for (;;) {
            const { value, done } = await reader.read();
            if (value) buf += value;
            let nl;
            while ((nl = buf.indexOf('\n')) >= 0) {
                const line = buf.slice(0, nl).trim();
                buf = buf.slice(nl + 1);
                if (!line) continue;
                last = JSON.parse(line);
                if (last.job) return last;
                showProgress(last);
            }
            if (done) break;
        }
        throw new Error('The connection closed before the photo was solved. Please try again.');
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
            cons.appendChild(el('polyline', { points: line.points.map((p) => p.join(',')).join(' '),
                                              class: fgClass(line, 'con-line') }));
        }
        for (const c of a.constellations) {
            cons.appendChild(el('text', { x: c.x, y: c.y, 'font-size': fs * (c.share > 0.25 ? 1.6 : 1.2),
                                          'text-anchor': 'middle', class: fgClass(c, 'con-label') }, c.name.toUpperCase()));
        }

        // Labels sit to the right of their marker, or to the left near the right-hand edge.
        // Items arrive most important first; a label that would overlap one already placed is
        // skipped (the marker stays, and its name shows on hover).
        const placed = [];
        const overlaps = (b) => placed.some((p) => b.x0 < p.x1 && b.x1 > p.x0 && b.y0 < p.y1 && b.y1 > p.y0);
        // Foreground labels are placed after all open-sky ones, so they never push one aside.
        const placedFg = [];
        const label = (x, y, r, text, size, cls, isFg) => {
            const flip = x > a.width * 0.8;
            const w = text.length * size * 0.56, tx = flip ? x - r - 4 * u : x + r + 4 * u;
            const box = { x0: flip ? tx - w : tx, x1: flip ? tx : tx + w, y0: y - size * 0.85, y1: y + size * 0.25 };
            if (overlaps(box) || (isFg && placedFg.some((p) => box.x0 < p.x1 && box.x1 > p.x0 && box.y0 < p.y1 && box.y1 > p.y0))) return null;
            (isFg ? placedFg : placed).push(box);
            return el('text', { x: tx, y, 'font-size': size, 'text-anchor': flip ? 'end' : 'start', class: cls }, text);
        };
        const marker = (shape, title) => { shape.appendChild(el('title', {}, title)); return shape; };

        const stars = el('g', { class: 'layer-stars', 'data-layer': 'stars' });
        const dsos = el('g', { class: 'layer-dsos', 'data-layer': 'dsos' });
        // Bright stars get first claim on label space, then deep-sky objects, then fainter stars.
        const ordered = [
            ...a.stars.filter((s) => s.mag < 2).map((s) => ['star', s]),
            ...a.dsos.map((d) => ['dso', d]),
            ...a.stars.filter((s) => s.mag >= 2).map((s) => ['star', s]),
        ];
        const queue = [...ordered.filter(([, o]) => !o.fg), ...ordered.filter(([, o]) => o.fg)];
        for (const [kind, o] of queue) {
            if (kind === 'dso') {
                const r = Math.max(o.r, 7 * u);
                dsos.appendChild(marker(el('circle', { cx: o.x, cy: o.y, r, class: fgClass(o, 'dso-ring') }), `${o.label} (${o.kind})`));
                const t = label(o.x, o.y + fs * 0.35, r, o.label.replace(' · ', '  '), fs, fgClass(o, 'dso-label'), o.fg);
                if (t) dsos.appendChild(t);
            } else {
                const r = (o.mag < 1 ? 11 : o.mag < 2.5 ? 9 : 7) * u;
                stars.appendChild(marker(el('circle', { cx: o.x, cy: o.y, r, class: fgClass(o, 'star-ring') }), `${o.full}, mag ${o.mag.toFixed(1)}`));
                const t = label(o.x, o.y - r * 0.6, r - 1 * u, o.label, fs * 0.95, fgClass(o, 'star-label'), o.fg);
                if (t) stars.appendChild(t);
            }
        }

        // Draw order: grid at the back, constellation names, then objects on top.
        for (const g of [grid, cons, dsos, stars]) svg.appendChild(g);
        // Once the photo is solved, the figures are drawn across it, then the names fade in.
        if (!Astro.motion.still()) {
            const ease = Astro.motion.EASE;
            [...cons.querySelectorAll('.con-line:not(.fg)')].forEach((l, i) => {
                l.setAttribute('pathLength', '1');
                l.animate([{ strokeDasharray: '1 2', strokeDashoffset: 1 }, { strokeDasharray: '1 2', strokeDashoffset: 0 }],
                          { duration: 700, delay: Math.min(i * 20, 500), easing: ease, fill: 'backwards' });
            });
            for (const t of cons.querySelectorAll('text')) t.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 400, delay: 600, fill: 'backwards' });
            for (const g of [dsos, stars]) g.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 400, delay: 450, fill: 'backwards' });
        }
        $('fgToggle').hidden = !a.foreground;
        syncLayers();
    }

    // Items the server found to lie over the foreground (no stars visible there) carry fg.
    function fgClass(item, cls) {
        return item.fg ? `${cls} fg` : cls;
    }

    function syncLayers() {
        for (const btn of document.querySelectorAll('.layer')) {
            const on = btn.getAttribute('aria-pressed') === 'true';
            const g = $('overlay').querySelector(`g[data-layer="${btn.dataset.layer}"]`);
            if (g) g.style.display = on ? '' : 'none';
        }
        $('overlay').classList.toggle('show-fg', $('fgToggle').getAttribute('aria-pressed') === 'true');
    }
    for (const btn of document.querySelectorAll('.layer, #fgToggle')) {
        btn.addEventListener('click', () => {
            btn.setAttribute('aria-pressed', String(btn.getAttribute('aria-pressed') !== 'true'));
            syncLayers();
        });
    }

    // ---- Download: the photo with its labels, as one PNG --------------------------------------
    // The overlay is styled by the site's CSS, which an exported SVG can't see, so each element's
    // computed style is copied onto a clone first. The image shows the layers switched on now.
    const EXPORT_STYLES = ['display', 'visibility', 'opacity', 'fill', 'fill-opacity', 'stroke', 'stroke-opacity',
        'stroke-width', 'stroke-dasharray', 'stroke-linejoin', 'stroke-linecap', 'paint-order', 'font-family',
        'font-size', 'font-weight', 'font-style', 'letter-spacing', 'text-anchor', 'dominant-baseline'];
    let lastFilename = 'photo';

    async function downloadAnnotated() {
        const img = $('photo'), svg = $('overlay');
        for (const anim of svg.getAnimations({ subtree: true })) anim.finish();   // no half-drawn lines
        const w = img.naturalWidth, h = img.naturalHeight;
        if (!w || !h) throw new Error('the photo has not finished loading. Try again in a moment.');
        const clone = svg.cloneNode(true);
        const from = [svg, ...svg.querySelectorAll('*')], to = [clone, ...clone.querySelectorAll('*')];
        from.forEach((node, i) => {
            const cs = getComputedStyle(node);
            to[i].setAttribute('style', EXPORT_STYLES.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(';'));
            to[i].removeAttribute('class');
        });
        clone.setAttribute('xmlns', SVG);
        clone.setAttribute('width', w);
        clone.setAttribute('height', h);
        const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }));
        try {
            const labels = new Image();
            labels.src = url;
            await labels.decode();
            const canvas = document.createElement('canvas');
            canvas.width = w; canvas.height = h;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, w, h);
            ctx.drawImage(labels, 0, 0, w, h);
            const blob = await new Promise((ok) => canvas.toBlob(ok, 'image/png'));
            if (!blob) throw new Error('this browser could not make the PNG (the image may be too large).');
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${lastFilename.replace(/\.[^.]+$/, '')}-annotated.png`;
            document.body.appendChild(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(a.href), 5000);
        } finally {
            URL.revokeObjectURL(url);
        }
    }
    $('downloadBtn').addEventListener('click', async () => {
        const btn = $('downloadBtn');
        btn.disabled = true;
        $('analyzerError').textContent = '';
        try { await downloadAnnotated(); }
        catch (err) { $('analyzerError').textContent = 'The image could not be saved: ' + err.message; }
        finally { btn.disabled = false; }
    });

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
        lastFilename = res.filename || 'photo';
        $('output').hidden = false;
        Astro.revealOnPhone($('output'));
    }

    // ---- Upload size ------------------------------------------------------------------------
    // Big JPG/PNG/WebP photos are shrunk in the browser before upload: the solver works on a
    // ~2000 px copy anyway, uploads get much faster, and hosted servers cap request sizes.
    const MAX_UPLOAD_MB = Number($('analyzeForm').dataset.maxUploadMb) || 300;
    const SHRINK_ABOVE_BYTES = Math.min(24, MAX_UPLOAD_MB * 0.8) * 1024 * 1024;
    const SHRINK_TO_PX = 4096;
    const BROWSER_DECODABLE = /^image\/(jpeg|png|webp)$/;

    async function prepareUpload(file) {
        if (file.size <= SHRINK_ABOVE_BYTES) return file;
        if (!BROWSER_DECODABLE.test(file.type)) {
            if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
                throw new Error(`That file is ${(file.size / 1048576).toFixed(0)} MB; this site accepts up to ${MAX_UPLOAD_MB} MB. ` +
                                'Export a JPG and try again.');
            }
            return file;
        }
        const bitmap = await createImageBitmap(file);
        const scale = Math.min(1, SHRINK_TO_PX / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(bitmap.width * scale);
        canvas.height = Math.round(bitmap.height * scale);
        canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        bitmap.close?.();
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
        if (!blob) return file;
        return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' });
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
        $('resultsEmpty').hidden = true;
        $('progress').hidden = false;
        $('progressBar').value = 0;
        $('progressMsg').textContent = `Sending ${file.name} to the solver…`;
        startClock();

        try {
            const upload = await prepareUpload(file);
            if (upload !== file) $('progressMsg').textContent = `Shrunk ${file.name} for upload. Sending it to the solver…`;
            const form = new FormData();
            form.append('image', upload);
            const hint = fovHint();
            if (hint) form.append('fov_hint', hint.toFixed(2));
            const started = await postPhoto(form);

            // Some hosts solve inside the upload request and send the finished job straight back.
            let job = started.job;
            while (!job || (job.state !== 'done' && job.state !== 'failed')) {
                await sleep(POLL_MS);
                job = await getJSON(`/api/jobs/${started.job_id}`);
                showProgress(job);
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
