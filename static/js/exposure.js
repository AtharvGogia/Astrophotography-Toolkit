'use strict';

(() => {
    const $ = (id) => document.getElementById(id);
    const FIELDS = ['latitude', 'longitude', 'cameraPreset', 'focalLength', 'aperture', 'pixelPitch',
                    'rotation', 'sensorWidth', 'sensorHeight', 'targetName', 'customRA', 'customDec'];

    const num = (id) => { const v = $(id).value.trim(); return v === '' ? NaN : Number(v); };
    const fmtS = (t) => `${t.toFixed(1)} s`;
    const fmtDeg = (d, digits = 1) => `${d < 0 ? '−' : '+'}${Math.abs(d).toFixed(digits)}°`;

    Astro.restoreFields(FIELDS);
    const search = TargetSearch.attach($('targetName'), $('targetList'), $('targetInfo'));
    try { search.restore(JSON.parse(localStorage.getItem('astro-target') || 'null')); } catch (e) { /* ignore */ }
    $('targetName').addEventListener('target-picked', (e) => {
        try { localStorage.setItem('astro-target', JSON.stringify(e.detail)); } catch (err) { /* ignore */ }
    });
    Astro.loadCameraPresets($('cameraPreset'), (cam) => {
        $('sensorWidth').value = cam.widthPx;
        $('sensorHeight').value = cam.heightPx;
        $('pixelPitch').value = cam.pitchUm;
    }).then(() => Astro.restoreFields(['cameraPreset']));

    let skyUrl = null;

    $('exposureForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        $('formError').textContent = '';

        const F = num('focalLength'), N = num('aperture'), p = num('pixelPitch');
        const wPx = num('sensorWidth'), hPx = num('sensorHeight');
        const rotation = Number.isNaN(num('rotation')) ? 0 : num('rotation');
        const name = $('targetName').value.trim();
        const ra = num('customRA'), dec = num('customDec');
        const haveCoords = !Number.isNaN(ra) && !Number.isNaN(dec);

        const missing = [];
        if (!(F > 0)) missing.push('focal length');
        if (!(N > 0)) missing.push('aperture');
        if (!(p > 0)) missing.push('pixel pitch');
        if (!(wPx > 0) || !(hPx > 0)) missing.push('sensor size');
        if (!name && !haveCoords) missing.push('a target');
        if (missing.length) {
            $('formError').textContent = `Please enter ${missing.join(', ')}.`;
            return;
        }
        Astro.saveFields(FIELDS);

        // Coordinates typed by hand win; then a picked suggestion; then a free-text name lookup.
        const picked = search.selection();
        let target, centerDec;
        if (haveCoords) {
            target = { ra, dec };
            centerDec = dec;
        } else if (picked) {
            target = { ra: picked.ra, dec: picked.dec };
            centerDec = picked.dec;
        } else {
            target = { target_name: name };
            const btn = $('calculateBtn');
            btn.disabled = true;
            btn.textContent = 'Looking up…';
            try {
                const resp = await Astro.postJSON('/api/resolve', target);
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.error || 'Could not find the target.');
                centerDec = data.dec;
            } catch (err) {
                $('formError').textContent = `Couldn't find “${name}”. Try picking a suggestion, or enter coordinates.`;
                return;
            } finally {
                btn.disabled = false;
                btn.textContent = 'Calculate';
            }
        }

        // ---- Numbers --------------------------------------------------------
        const wMm = p * wPx / 1000, hMm = p * hPx / 1000;
        let minT = Infinity, minIdx = 0, cellsHtml = '';
        let i = 0;
        for (const row of [1, 0, -1]) {               // top, middle, bottom
            for (const col of [-1, 0, 1]) {           // left, centre, right
                const d = Astro.sensorPointDec(centerDec, col * wMm / 3, row * hMm / 3, F, rotation);
                const t = Astro.npfTime(N, F, p, d);
                if (t < minT) { minT = t; minIdx = i; }
                cellsHtml += `<div data-i="${i}"><b>${fmtS(t)}</b><span>δ ${fmtDeg(d)}</span></div>`;
                i++;
            }
        }
        $('sensorGrid').innerHTML = cellsHtml;
        $('sensorGrid').children[minIdx].classList.add('limit');

        $('targetLabel').textContent = haveCoords ? `RA ${ra}°, Dec ${dec}°` : name;
        $('resWhole').textContent = minT.toFixed(1);
        $('resCentre').textContent = fmtS(Astro.npfTime(N, F, p, centerDec));
        $('resSimple').textContent = fmtS(Astro.npfSimple(N, F, p));
        $('res500').textContent = fmtS(Astro.rule500(F, Math.hypot(wMm, hMm)));
        $('resFov').textContent = `${Astro.fovDeg(wMm, F).toFixed(1)}° × ${Astro.fovDeg(hMm, F).toFixed(1)}°`;
        $('resDec').textContent = fmtDeg(centerDec, 2);
        $('sensor').style.aspectRatio = `${wPx} / ${hPx}`;
        $('resultsEmpty').hidden = true;
        $('resultsBody').hidden = false;

        // ---- Sky preview (slow, loads in the background) -----------------------
        const img = $('skyImage');
        img.hidden = true;
        $('skyStatus').textContent = 'Rendering the sky behind your sensor…';
        const skyPayload = { ...target, focal_length: F, sensor_width_px: wPx, sensor_height_px: hPx,
                             pixel_pitch: p, rotation_deg: rotation };
        Astro.loadSkyLines($('skyLines'), skyPayload);
        try {
            const resp = await Astro.postJSON('/api/skymap', skyPayload);
            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                throw new Error(data.error || 'Sky preview failed.');
            }
            if (skyUrl) URL.revokeObjectURL(skyUrl);
            skyUrl = URL.createObjectURL(await resp.blob());
            img.src = skyUrl;
            img.hidden = false;
            $('skyStatus').textContent = '';
        } catch (err) {
            $('skyStatus').textContent = err.message;
        }
    });
})();
