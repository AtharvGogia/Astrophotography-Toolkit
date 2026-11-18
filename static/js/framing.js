'use strict';

(() => {
    const $ = (id) => document.getElementById(id);
    const FIELDS = ['cameraPreset', 'focalLength', 'pixelPitch', 'rotation', 'sensorWidth', 'sensorHeight',
                    'targetName', 'customRA', 'customDec'];
    const num = (id) => { const v = $(id).value.trim(); return v === '' ? NaN : Number(v); };

    // The preview shows more sky than the frame: up to 2x, but never so wide that the
    // gnomonic projection stretches badly (half-diagonal kept under ~70° from the centre).
    const MAX_TAN = Math.tan(70 * Math.PI / 180);
    const contextFactor = (halfDiagMm, F) => Math.max(1, Math.min(2, MAX_TAN / (halfDiagMm / F)));

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

    $('framingForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        $('formError').textContent = '';

        const F = num('focalLength'), p = num('pixelPitch');
        const wPx = num('sensorWidth'), hPx = num('sensorHeight');
        const rotation = Number.isNaN(num('rotation')) ? 0 : num('rotation');
        const name = $('targetName').value.trim();
        const ra = num('customRA'), dec = num('customDec');
        const haveCoords = !Number.isNaN(ra) && !Number.isNaN(dec);

        const missing = [];
        if (!(F > 0)) missing.push('focal length');
        if (!(p > 0)) missing.push('pixel pitch');
        if (!(wPx > 0) || !(hPx > 0)) missing.push('sensor size');
        if (!name && !haveCoords) missing.push('a target');
        if (missing.length) {
            $('formError').textContent = `Please enter ${missing.join(', ')}.`;
            return;
        }
        Astro.saveFields(FIELDS);

        // Same priority as the Exposure page: typed coordinates, then a picked suggestion, then a lookup.
        const picked = search.selection();
        let center;
        const btn = $('previewBtn');
        if (haveCoords) center = { ra, dec };
        else if (picked) center = { ra: picked.ra, dec: picked.dec };
        else {
            btn.disabled = true;
            try {
                const resp = await Astro.postJSON('/api/resolve', { target_name: name });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.error);
                center = { ra: data.ra, dec: data.dec };
            } catch (err) {
                $('formError').textContent = `Couldn't find “${name}”. Try picking a suggestion, or enter coordinates.`;
                return;
            } finally {
                btn.disabled = false;
            }
        }

        // ---- Numbers ----------------------------------------------------------------
        const wMm = p * wPx / 1000, hMm = p * hPx / 1000, dMm = Math.hypot(wMm, hMm);
        $('targetLabel').textContent = haveCoords ? `RA ${ra}°, Dec ${dec}°` : name;
        $('resFov').textContent = `${Astro.fovDeg(wMm, F).toFixed(2)}° × ${Astro.fovDeg(hMm, F).toFixed(2)}°`;
        $('resDiag').textContent = `${Astro.fovDeg(dMm, F).toFixed(2)}°`;
        $('resScale').textContent = `${(206.265 * p / F).toFixed(2)}″/px`;
        $('resRA').textContent = TargetSearch.fmtRA(((center.ra % 360) + 360) % 360);
        $('resDec').textContent = TargetSearch.fmtDec(center.dec);
        $('resultsEmpty').hidden = true;
        $('resultsBody').hidden = false;

        // ---- Frame outline over a wider, north-up view --------------------------------
        const ctx = contextFactor(dMm / 2, F);
        const view = $('framingView');
        view.style.aspectRatio = `${wPx} / ${hPx}`;
        const box = $('fovOutline');
        box.style.width = `${100 / ctx}%`;
        box.style.height = `${100 / ctx}%`;
        // Position angle is measured from north through east; with east on the left that is
        // an anticlockwise turn on screen, so CSS gets the negative angle.
        box.style.transform = `translate(-50%, -50%) rotate(${-rotation}deg)`;
        box.hidden = ctx <= 1.001;     // no room for context: the whole view is the frame
        $('framingCaption').textContent = ctx > 1.001
            ? `The outline is your frame; the view shows ${ctx.toFixed(1)}× more sky around it. North is up, east is left.`
            : 'This lens is too wide to show extra sky around the frame; the whole view is your frame. North is up, east is left.';

        const img = $('skyImage');
        img.hidden = true;
        $('skyStatus').textContent = 'Drawing the sky…';
        try {
            const resp = await Astro.postJSON('/api/skymap', {
                ra: center.ra, dec: center.dec, focal_length: F, sensor_width_px: wPx, sensor_height_px: hPx,
                pixel_pitch: p, rotation_deg: 0, context: ctx,
            });
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
