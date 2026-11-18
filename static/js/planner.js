'use strict';

(() => {
    const $ = (id) => document.getElementById(id);
    const NS = 'http://www.w3.org/2000/svg';
    const { fmtTime, fmtDay } = Astro;

    // ---- Location ------------------------------------------------------------------------
    function showLocation() {
        const loc = ObserverLocation.get();
        $('planLocation').textContent = loc ? ObserverLocation.format(loc) : 'No location set yet.';
        $('changeLocation').textContent = loc ? 'Change' : 'Set location';
    }
    showLocation();
    $('changeLocation').addEventListener('click', () => ObserverLocation.open());
    window.addEventListener('location-changed', () => {
        showLocation();
        if (!$('resultsBody').hidden) $('planForm').requestSubmit();
    });

    // ---- Target and date ------------------------------------------------------------------
    const search = TargetSearch.attach($('targetName'), $('targetList'), $('targetInfo'));
    const params = new URLSearchParams(location.search);
    let restored = null;
    if (params.get('target') && params.get('ra') && params.get('dec')) {
        restored = { name: params.get('target'), ra: Number(params.get('ra')), dec: Number(params.get('dec')),
                     kind: params.get('kind') || 'Object' };
    } else {
        try { restored = JSON.parse(localStorage.getItem('astro-target') || 'null'); } catch (e) { /* ignore */ }
    }
    if (restored) search.restore(restored);
    $('targetName').addEventListener('target-picked', (e) => {
        try { localStorage.setItem('astro-target', JSON.stringify(e.detail)); } catch (err) { /* ignore */ }
    });
    $('planDate').value = Astro.isoDate(Astro.nightStart());

    // ---- Chart ----------------------------------------------------------------------------
    const W = 800, H = 320, L = 40, R = 12, T = 14, B = 34;
    const ALT_MIN = -15, ALT_MAX = 90;
    const el = (name, attrs, text) => {
        const n = document.createElementNS(NS, name);
        for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
        if (text != null) n.textContent = text;
        return n;
    };

    function skyBand(sunAlt) {
        if (sunAlt > -0.833) return 'band-day';
        if (sunAlt > -6) return 'band-civil';
        if (sunAlt > -12) return 'band-nautical';
        if (sunAlt > -18) return 'band-astro';
        return 'band-night';
    }

    function drawChart(p) {
        const svg = $('altChart');
        svg.innerHTML = '';
        const t0 = p.times[0], t1 = p.times[p.times.length - 1];
        const x = (t) => L + (t - t0) / (t1 - t0) * (W - L - R);
        const y = (a) => T + (ALT_MAX - Math.max(ALT_MIN, Math.min(ALT_MAX, a))) / (ALT_MAX - ALT_MIN) * (H - T - B);

        // Sky shading by Sun altitude.
        let start = 0;
        for (let i = 1; i <= p.times.length; i++) {
            if (i === p.times.length || skyBand(p.sun_alt[i]) !== skyBand(p.sun_alt[start])) {
                const x0 = x(p.times[start]), x1 = x(p.times[Math.min(i, p.times.length - 1)]);
                svg.appendChild(el('rect', { x: x0, y: T, width: Math.max(0, x1 - x0), height: H - T - B,
                                             class: skyBand(p.sun_alt[start]) }));
                start = i;
            }
        }
        // Best window(s).
        for (const w of p.windows) {
            svg.appendChild(el('rect', { x: x(w.start), y: T, width: x(w.end) - x(w.start), height: H - T - B,
                                         class: 'band-window' }));
        }
        // Altitude grid.
        for (const a of [0, 30, 60, 90]) {
            svg.appendChild(el('line', { x1: L, x2: W - R, y1: y(a), y2: y(a), class: a === 0 ? 'horizon' : 'gridline' }));
            svg.appendChild(el('text', { x: L - 6, y: y(a) + 4, class: 'axis-label', 'text-anchor': 'end' }, `${a}°`));
        }
        svg.appendChild(el('line', { x1: L, x2: W - R, y1: y(p.min_alt), y2: y(p.min_alt), class: 'min-alt' }));
        svg.appendChild(el('text', { x: W - R - 4, y: y(p.min_alt) - 5, class: 'axis-label', 'text-anchor': 'end' },
                           `your minimum, ${p.min_alt}°`));
        // Hour ticks.
        const firstHour = Math.ceil(t0 / 3600000) * 3600000;
        for (let t = firstHour; t <= t1; t += 3600000) {
            const d = new Date(t);
            if (d.getHours() % 2) continue;
            svg.appendChild(el('line', { x1: x(t), x2: x(t), y1: H - B, y2: H - B + 4, class: 'tick' }));
            svg.appendChild(el('text', { x: x(t), y: H - B + 18, class: 'axis-label', 'text-anchor': 'middle' }, fmtTime(t)));
        }
        // Moon, then target on top.
        const pts = (alts) => p.times.map((t, i) => `${x(t).toFixed(1)},${y(alts[i]).toFixed(1)}`).join(' ');
        svg.appendChild(el('polyline', { points: pts(p.moon_alt), class: 'moon-line' }));
        svg.appendChild(el('polyline', { points: pts(p.target_alt), class: 'target-line' }));
        const hi = p.target_events.find((e) => e.event === 'highest');
        if (hi) {
            svg.appendChild(el('circle', { cx: x(hi.time), cy: y(hi.alt), r: 4, class: 'target-dot' }));
            svg.appendChild(el('text', { x: x(hi.time), y: y(hi.alt) - 9, class: 'peak-label', 'text-anchor': 'middle' },
                               `${Math.round(hi.alt)}° ${hi.direction}`));
        }
        // Now.
        const now = Date.now();
        if (now > t0 && now < t1) {
            svg.appendChild(el('line', { x1: x(now), x2: x(now), y1: T, y2: H - B, class: 'now-line' }));
            svg.appendChild(el('text', { x: x(now) + 4, y: T + 12, class: 'axis-label' }, 'now'));
        }
        // Hover read-out.
        const hit = el('rect', { x: L, y: T, width: W - L - R, height: H - T - B, class: 'chart-hit' });
        const cursor = el('line', { x1: 0, x2: 0, y1: T, y2: H - B, class: 'cursor-line', visibility: 'hidden' });
        svg.append(cursor, hit);
        const tip = $('chartTip');
        hit.addEventListener('mousemove', (e) => {
            const box = svg.getBoundingClientRect();
            const sx = (e.clientX - box.left) / box.width * W;
            const t = t0 + (sx - L) / (W - L - R) * (t1 - t0);
            const i = Math.max(0, Math.min(p.times.length - 1, Math.round((t - t0) / (t1 - t0) * (p.times.length - 1))));
            cursor.setAttribute('x1', x(p.times[i]));
            cursor.setAttribute('x2', x(p.times[i]));
            cursor.setAttribute('visibility', 'visible');
            const a = p.target_alt[i];
            tip.textContent = `${fmtTime(p.times[i])} · target ${a > 0 ? `${a.toFixed(0)}° high, ${compass(p.target_az[i])}` : 'below the horizon'}` +
                              ` · Moon ${p.moon_alt[i] > 0 ? `${p.moon_alt[i].toFixed(0)}°` : 'down'}`;
            tip.hidden = false;
            tip.style.left = `${Math.min(box.width - 260, Math.max(0, e.clientX - box.left + 12))}px`;
        });
        hit.addEventListener('mouseleave', () => { tip.hidden = true; cursor.setAttribute('visibility', 'hidden'); });
    }

    const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
    const compass = (az) => COMPASS[Math.floor((((az % 360) + 360) % 360 + 11.25) / 22.5) % 16];
    const DIRECTION_WORDS = { N: 'north', S: 'south', E: 'east', W: 'west' };
    const describeDir = (d) => (d.length === 1 ? DIRECTION_WORDS[d] : d);

    // ---- Text and tables ---------------------------------------------------------------------
    function render(p, name, loc) {
        $('planTitle').textContent = `${name} · ${ObserverLocation.format(loc)} · ${fmtDay(p.times[0])} night`;
        const rise = p.target_events.find((e) => e.event === 'rise');
        const set = p.target_events.find((e) => e.event === 'set');
        const hi = p.target_events.find((e) => e.event === 'highest');
        const best = p.windows[0];

        let summary;
        if (p.never_up) {
            summary = `${name} never rises from this latitude. Its highest possible altitude is ${p.culmination}°.`;
        } else if (!best) {
            summary = hi && hi.alt > 0
                ? `${name} gets up to ${hi.alt}° (looking ${describeDir(hi.direction)}), but not above ${p.min_alt}° while it is dark.`
                : `${name} stays below the horizon tonight.`;
        } else {
            const moonNote = best.moon_up_fraction > 0.5 ? ` The Moon (${Math.round(p.moon.illumination * 100)}% lit) is up for most of it.`
                : best.moon_up_fraction > 0 ? ' The Moon is up for part of it.' : ' The Moon is down the whole time.';
            summary = `Dark and above ${p.min_alt}° for ${Math.floor(best.minutes / 60)} h ${best.minutes % 60} min, ` +
                      `peaking at ${best.peak_alt}°.${moonNote}`;
        }
        $('bestWindow').textContent = best ? `${fmtTime(best.start)}–${fmtTime(best.end)}` : '—';
        $('planSummary').textContent = summary;

        const stats = [];
        if (p.always_up) stats.push(['Rises', 'Never sets']);
        else stats.push(['Rises', rise ? `${fmtTime(rise.time)} ${rise.direction}` : '—']);
        stats.push(['Highest', hi ? `${fmtTime(hi.time)}, ${Math.round(hi.alt)}° ${hi.direction}` : '—']);
        stats.push(['Sets', p.always_up ? '—' : set ? `${fmtTime(set.time)} ${set.direction}` : '—']);
        const dk = p.sun_events.find((e) => e.event === `${p.dark_kind}_set`);
        const dw = p.sun_events.find((e) => e.event === `${p.dark_kind}_rise`);
        // Only a dusk followed by a dawn makes a range; otherwise it is dark (or never dark) all along.
        const darkAll = !dk && !dw && p.sun_alt.every((a) => a <= (p.dark_kind === 'astronomical' ? -18 : -12));
        stats.push(['Dark', dk && dw && dk.time < dw.time ? `${fmtTime(dk.time)}–${fmtTime(dw.time)}`
                            : darkAll ? 'All night' : 'Not fully']);
        stats.push(['Moon', `${Math.round(p.moon.illumination * 100)}%, ${p.moon.separation}° away`]);
        const dl = $('eventStats');
        dl.innerHTML = '';
        for (const [k, v] of stats) {
            const div = document.createElement('div');
            const dt = document.createElement('dt'); dt.textContent = k;
            const dd = document.createElement('dd'); dd.textContent = v;
            div.append(dt, dd);
            dl.appendChild(div);
        }

        // Sun events.
        const labels = {
            sun_set: 'Sunset', civil_set: 'Civil dusk', nautical_set: 'Nautical dusk', astronomical_set: 'Astronomical dark',
            astronomical_rise: 'Astronomical dawn', nautical_rise: 'Nautical dawn', civil_rise: 'Civil dawn', sun_rise: 'Sunrise',
        };
        const tbody = $('sunTable').querySelector('tbody');
        tbody.innerHTML = '';
        const rows = [...p.sun_events.map((e) => [labels[e.event] || e.event, e.time]),
                      ...p.moon.events.map((e) => [e.event === 'rise' ? 'Moonrise' : 'Moonset', e.time])]
            .sort((a, b) => a[1] - b[1]);
        for (const [label, t] of rows) {
            const tr = document.createElement('tr');
            const th = document.createElement('th'); th.textContent = label;
            const td = document.createElement('td'); td.textContent = fmtTime(t);
            tr.append(th, td);
            tbody.appendChild(tr);
        }
        if (!rows.length) tbody.innerHTML = '<tr><th>The Sun does not set or rise in this window.</th><td></td></tr>';

        $('moonGlyph').innerHTML = Astro.moonSVG(p.moon.illumination, p.moon.waxing, 72);
        $('moonPhase').textContent = `${p.moon.phase}, ${Math.round(p.moon.illumination * 100)}% lit`;
        const mr = p.moon.events.find((e) => e.event === 'rise'), ms = p.moon.events.find((e) => e.event === 'set');
        $('moonText').textContent = `${mr ? `Rises ${fmtTime(mr.time)}` : 'No moonrise in this window'}` +
            `${ms ? `, sets ${fmtTime(ms.time)}` : ''}. ${p.moon.separation}° from your target.`;
        $('tzNote').textContent = `Times are in your computer's time zone (${Astro.timeZoneName()}).`;

        drawChart(p);
        $('resultsEmpty').hidden = true;
        $('resultsBody').hidden = false;
        $('nightDetail').hidden = false;
    }

    async function loadMoonCycle() {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        try {
            const resp = await fetch(`/api/moon?start=${encodeURIComponent(Astro.utcIso(today))}&days=30`);
            if (!resp.ok) return;
            const data = await resp.json();
            const strip = $('moonStrip');
            strip.innerHTML = '';
            const eventsByDay = {};
            for (const e of data.events) eventsByDay[new Date(e.time).toDateString()] = e.event;
            for (const d of data.days) {
                // Label each sample by the local date at midday, so a daylight-saving change
                // (a 23 or 25 hour day) can't shift it onto the neighbouring date.
                const date = new Date(d.time + 12 * 3600000);
                const cell = document.createElement('div');
                cell.className = 'moon-day';
                const ev = eventsByDay[date.toDateString()];
                if (ev) cell.classList.add('moon-day-event');
                cell.title = `${fmtDay(date.getTime())}: ${Math.round(d.illumination * 100)}% lit${ev ? ` (${ev})` : ''}`;
                cell.innerHTML = Astro.moonSVG(d.illumination, d.waxing, 26) +
                    `<span class="moon-date">${date.getDate()}</span>`;
                strip.appendChild(cell);
            }
            $('moonEvents').textContent = data.events.slice(0, 4)
                .map((e) => `${e.event}: ${fmtDay(e.time)} ${fmtTime(e.time)}`).join(' · ');
            $('moonCycle').hidden = false;
        } catch (e) { /* optional */ }
    }

    // ---- Submit ----------------------------------------------------------------------------
    $('planForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        $('formError').textContent = '';
        const loc = ObserverLocation.get();
        if (!loc) {
            $('formError').textContent = 'Set your location first.';
            ObserverLocation.open();
            return;
        }
        const name = $('targetName').value.trim();
        if (!name) {
            $('formError').textContent = 'Pick a target.';
            return;
        }
        const picked = search.selection();
        const target = picked ? { ra: picked.ra, dec: picked.dec } : { target_name: name };
        const start = Astro.nightStart($('planDate').value);
        const btn = $('planBtn');
        btn.disabled = true;
        btn.textContent = 'Working…';
        try {
            const resp = await Astro.postJSON('/api/plan', {
                ...target, lat: loc.lat, lon: loc.lon, start: Astro.utcIso(start), min_alt: Number($('minAlt').value) || 0,
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Planning failed.');
            render(data, name, loc);
        } catch (err) {
            $('formError').textContent = err.message;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Plan the night';
        }
    });

    loadMoonCycle();
    if (restored && ObserverLocation.get()) $('planForm').requestSubmit();
})();
