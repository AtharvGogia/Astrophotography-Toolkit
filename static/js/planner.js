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
        loadMoonCycle();                        // the strip's dates follow the site's time zone
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
    let W = 800;
    const H = 320, L = 40, R = 12, T = 14, B = 34;
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

    function drawChart(p, animate = false) {
        const svg = $('altChart');
        svg.innerHTML = '';
        // Wider drawing area on wide screens, so the chart keeps a sensible height and text size.
        $('nightDetail').hidden = false;     // measure the chart at its real width
        W = Math.round(Math.max(520, Math.min(1500, svg.clientWidth || 800)));
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
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
        const moonBright = p.moon.illumination >= 0.3;
        for (const w of p.windows) {
            svg.appendChild(el('rect', { x: x(w.start), y: T, width: x(w.end) - x(w.start), height: H - T - B,
                                         class: moonBright ? 'band-window moonlit' : 'band-window' }));
        }
        if (moonBright) {
            for (const w of p.moonless_windows || []) {
                svg.appendChild(el('rect', { x: x(w.start), y: T, width: x(w.end) - x(w.start), height: H - T - B,
                                             class: 'band-window' }));
            }
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
        const firstQuarter = Math.ceil(t0 / 900000) * 900000;
        for (let t = firstQuarter; t <= t1; t += 900000) {
            const z = Astro.zoned(t);
            if (z.min !== 0 || z.h % 2) continue;
            svg.appendChild(el('line', { x1: x(t), x2: x(t), y1: H - B, y2: H - B + 4, class: 'tick' }));
            svg.appendChild(el('text', { x: x(t), y: H - B + 18, class: 'axis-label', 'text-anchor': 'middle' }, fmtTime(t)));
        }
        // Moon, then target on top.
        const pts = (alts) => p.times.map((t, i) => `${x(t).toFixed(1)},${y(alts[i]).toFixed(1)}`).join(' ');
        // The two curves are revealed left to right through a clip that widens when a plan loads.
        const clip = el('clipPath', { id: 'altReveal' });
        const clipRect = el('rect', { x: L, y: 0, width: W - L - R + 2, height: H });
        clip.appendChild(clipRect);
        svg.appendChild(el('defs', {})).appendChild(clip);
        const curves = el('g', { 'clip-path': 'url(#altReveal)' });
        curves.append(el('polyline', { points: pts(p.moon_alt), class: 'moon-line' }),
                      el('polyline', { points: pts(p.target_alt), class: 'target-line' }));
        svg.appendChild(curves);
        const peak = [];
        const hi = p.target_events.find((e) => e.event === 'highest');
        if (hi) {
            peak.push(el('circle', { cx: x(hi.time), cy: y(hi.alt), r: 4, class: 'target-dot' }),
                      el('text', { x: x(hi.time), y: y(hi.alt) - 9, class: 'peak-label', 'text-anchor': 'middle' },
                         `${Math.round(hi.alt)}° ${hi.direction}`));
            svg.append(...peak);
        }
        if (animate && !Astro.motion.still()) {
            clipRect.style.transformOrigin = `${L}px 0px`;
            clipRect.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }],
                             { duration: 900, easing: Astro.motion.EASE });
            for (const n of peak) n.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, delay: 650, fill: 'backwards' });
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
        const skyMark = el('line', { x1: 0, x2: 0, y1: T, y2: H - B, class: 'sky-time-line', visibility: 'hidden' });
        svg.append(skyMark, cursor, hit);
        chartX = x;
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
        hit.addEventListener('click', (e) => {
            const box = svg.getBoundingClientRect();
            const t = t0 + ((e.clientX - box.left) / box.width * W - L) / (W - L - R) * (t1 - t0);
            setSkyTime(t, true);
        });
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
        // A Moon over ~30% lit brightens the sky enough to matter for the Milky Way and nebulae.
        const moonBright = p.moon.illumination >= 0.3;
        const moonless = (p.moonless_windows || [])[0];
        const moonInWay = moonBright && best && best.moon_up_fraction > 0;
        const lead = moonInWay && moonless ? moonless : best;
        const dur = (m) => `${Math.floor(m / 60)} h ${m % 60} min`;

        let summary;
        if (p.never_up) {
            summary = `${name} never rises from this latitude. Its highest possible altitude is ${p.culmination}°.`;
        } else if (!best) {
            summary = hi && hi.alt > 0
                ? `${name} gets up to ${hi.alt}° (looking ${describeDir(hi.direction)}), but not above ${p.min_alt}° while it is dark.`
                : `${name} stays below the horizon tonight.`;
        } else if (moonInWay && moonless) {
            summary = `${dur(moonless.minutes)} dark, moonless and above ${p.min_alt}°. ` +
                      `With the ${Math.round(p.moon.illumination * 100)}% Moon up: ${fmtTime(best.start)}–${fmtTime(best.end)}, fine for bright stars and trails.`;
        } else if (moonInWay) {
            summary = `${dur(best.minutes)} dark and above ${p.min_alt}°, but the ${Math.round(p.moon.illumination * 100)}% Moon is up throughout. ` +
                      `For the Milky Way or faint nebulae, pick an underlined night below.`;
        } else {
            const moonNote = best.moon_up_fraction > 0 ? ` The Moon is up for part of it, but only ${Math.round(p.moon.illumination * 100)}% lit.`
                : ' The Moon is down the whole time.';
            summary = `${dur(best.minutes)} dark and above ${p.min_alt}°, peaking at ${Math.round(best.peak_alt)}°.${moonNote}`;
        }
        $('bestWindowLabel').textContent = moonInWay && moonless ? 'Best moonless window'
            : moonInWay ? 'Best window, moonlit' : 'Best window';
        $('bestWindowLabel').dataset.sky = !best ? 'none' : moonInWay && !moonless ? 'moonlit'
            : (moonInWay && moonless) || best.moon_up_fraction === 0 ? 'moonless' : 'dark';
        $('bestWindow').textContent = lead ? `${fmtTime(lead.start)}–${fmtTime(lead.end)}` : '—';
        $('planSummary').textContent = summary;

        const stats = [];
        if (p.always_up) stats.push(['Rises', 'Never sets']);
        else stats.push(['Rises', rise ? `${fmtTime(rise.time)} ${rise.direction}` : '—']);
        stats.push(['Highest', hi ? `${fmtTime(hi.time)}, ${Math.round(hi.alt)}° ${hi.direction}` : '—']);
        stats.push(['Sets', p.always_up ? '—' : set ? `${fmtTime(set.time)} ${set.direction}` : '—']);
        stats.push(['Moon', `${Math.round(p.moon.illumination * 100)}% lit, ${Math.round(p.moon.separation)}° away`]);
        const dl = $('eventStats');
        dl.innerHTML = '';
        for (const [k, v] of stats) {
            const div = document.createElement('div');
            const dt = document.createElement('dt'); dt.textContent = k;
            const dd = document.createElement('dd'); dd.textContent = v;
            div.append(dt, dd);
            dl.appendChild(div);
        }

        // One short timeline from sunset to sunrise: when it gets dark and what the Moon does.
        // (The twilight steps in between are shown as shading on the altitude chart.)
        const ev = (name) => (p.sun_events.find((e) => e.event === name) || {}).time;
        const kind = p.dark_kind;
        const t0 = ev('sun_set'), t1 = ev('sun_rise');
        const rows = [['Sunset', t0], ['Dark from', ev(`${kind}_set`)], ['Dark until', ev(`${kind}_rise`)], ['Sunrise', t1]]
            .filter(([, t]) => t);
        for (const e of p.moon.events) {
            if (!t0 || !t1 || (e.time > t0 && e.time < t1)) rows.push([e.event === 'rise' ? 'Moonrise' : 'Moonset', e.time]);
        }
        rows.sort((a, b) => a[1] - b[1]);
        const tbody = $('sunTable').querySelector('tbody');
        tbody.innerHTML = '';
        for (const [label, t] of rows) {
            const tr = document.createElement('tr');
            const th = document.createElement('th'); th.textContent = label;
            const td = document.createElement('td'); td.textContent = fmtTime(t);
            tr.append(th, td);
            tbody.appendChild(tr);
        }
        if (!rows.length) tbody.innerHTML = '<tr><th>The Sun does not set or rise in this window.</th><td></td></tr>';

        Astro.motion.sweepMoon($('moonGlyph'), p.moon.illumination, p.moon.waxing, 72);
        Astro.motion.stagger(tbody.children, { step: 40, max: 240 });
        $('moonPhase').textContent = `${p.moon.phase}, ${Math.round(p.moon.illumination * 100)}% lit`;
        const mr = p.moon.events.find((e) => e.event === 'rise'), ms = p.moon.events.find((e) => e.event === 'set');
        $('moonText').textContent = `${mr ? `Rises ${fmtTime(mr.time)}` : 'No moonrise in this window'}` +
            `${ms ? `, sets ${fmtTime(ms.time)}` : ''}. ${p.moon.separation}° from your target.`;
        $('tzNote').textContent = Astro.siteZone()
            ? `Times are local to the observing site (${Astro.siteZone()}).`
            : `Times are in your computer's time zone (${Astro.deviceZone()}).`;

        drawChart(p, true);
        lastPlan = { p, name, loc };
        const panel = document.querySelector('.answer-panel');
        if (panel) { panel.classList.remove('fresh'); void panel.offsetWidth; panel.classList.add('fresh'); }
        setupSky(p, name, loc);
        $('resultsEmpty').hidden = true;
        $('resultsBody').hidden = false;
        $('nightDetail').hidden = false;
        Astro.revealOnPhone(document.querySelector('.results'), $('planForm'));
    }

    // ---- Sky chart ---------------------------------------------------------------------------
    let lastPlan = null, sky = null;          // sky: {data, key, p, name, loc, t0, t1}

    function sunAltAt(p, t) {
        const i = Math.max(0, Math.min(p.times.length - 1, Math.round((t - p.times[0]) / (p.times[1] - p.times[0]))));
        return p.sun_alt[i];
    }

    let chartX = null;
    const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function drawSky() {
        if (!sky || !sky.data) return;
        const t = Number($('skySlider').value);
        // The same moment, marked on the altitude chart.
        const mark = document.querySelector('#altChart .sky-time-line');
        if (mark && chartX) {
            mark.setAttribute('x1', chartX(t));
            mark.setAttribute('x2', chartX(t));
            mark.setAttribute('visibility', 'visible');
        }
        $('skySlider').setAttribute('aria-valuetext', fmtTime(t));
        const { p, name, loc } = sky;
        const res = SkyChart.render($('skyChart'), sky.data, {
            lat: loc.lat, lon: loc.lon, time: t, sky: skyBand(sunAltAt(p, t)),
            target: p.target ? { name, ra: p.target.ra, dec: p.target.dec } : null,
        });
        $('skyTime').textContent = fmtTime(t);
        const h = res.target;
        $('skyWhere').textContent = !h ? '' : h.alt > 0
            ? `${name}: ${Math.round(h.alt)}° up, towards ${compass(h.az)} (azimuth ${Math.round(h.az)}°)`
            : `${name} is below the horizon.`;
    }

    // ---- Motion: the night passing --------------------------------------------------------
    // One frame loop drives both the short turn-in when a plan loads and the "Play the night"
    // time-lapse. Anything the user does with the slider stops it.
    let anim = null;
    const easeOut = (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x));

    function stopAnim() {
        if (anim) cancelAnimationFrame(anim.raf);
        anim = null;
        const btn = $('skyPlay');
        btn.setAttribute('aria-pressed', 'false');
        btn.textContent = 'Play the night';
    }

    function runAnim(from, to, ms, ease, onEnd) {
        stopAnim();
        if (document.hidden) {          // no frames run in a background tab: just show the end
            $('skySlider').value = String(to);
            drawSky();
            if (onEnd) onEnd();
            return;
        }
        const start = performance.now();
        let last = 0;
        const me = {};
        const frame = (now) => {
            if (anim !== me) return;           // stopped or replaced: a queued frame must not land
            const k = Math.min(1, (now - start) / ms);
            // About 30 redraws a second is plenty for a sky this slow, and keeps phones cool.
            if (now - last > 32 || k === 1) {
                last = now;
                $('skySlider').value = String(from + (to - from) * ease(k));
                drawSky();
            }
            if (k < 1) me.raf = requestAnimationFrame(frame);
            else { anim = null; if (onEnd) onEnd(); }
        };
        anim = me;
        me.raf = requestAnimationFrame(frame);
    }

    function playNight() {
        if (!sky || !sky.data) return;
        const btn = $('skyPlay');
        if (anim && anim.playing) { stopAnim(); return; }
        let from = Number($('skySlider').value);
        if (from >= sky.t1 - 60000) from = sky.t0;           // at the end: start again from sunset
        btn.setAttribute('aria-pressed', 'true');
        btn.textContent = 'Pause';
        if (reduceMotion()) {
            // No continuous spinning: step through the night half an hour at a time.
            stopAnim();
            btn.setAttribute('aria-pressed', 'true');
            btn.textContent = 'Pause';
            let t = from;
            const step = () => {
                t = Math.min(sky.t1, t + 30 * 60000);
                $('skySlider').value = String(t);
                drawSky();
                if (t < sky.t1) anim = { raf: 0, playing: true, timer: setTimeout(step, 600) };
                else stopAnim();
            };
            anim = { raf: 0, playing: true, timer: setTimeout(step, 300) };
            return;
        }
        // About an hour of sky per second.
        const ms = Math.max(1500, (sky.t1 - from) / 3600000 * 1000);
        runAnim(from, sky.t1, ms, (x) => x, () => stopAnim());
        if (!anim) return;
        anim.playing = true;
        btn.setAttribute('aria-pressed', 'true');
        btn.textContent = 'Pause';
    }

    const stopEverything = () => {
        if (anim && anim.timer) clearTimeout(anim.timer);
        stopAnim();
    };
    $('skyPlay').addEventListener('click', () => {
        if (anim && anim.playing) { stopEverything(); return; }
        playNight();
    });
    document.addEventListener('visibilitychange', () => { if (document.hidden) stopEverything(); });

    function setSkyTime(t, scroll) {
        if (!sky) return;
        stopEverything();
        $('skySlider').value = String(Math.max(sky.t0, Math.min(sky.t1, t)));
        drawSky();
        if (scroll) $('skyPanel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    async function setupSky(p, name, loc) {
        // Slider from sunset to sunrise (or the whole window if the Sun doesn't set).
        const ss = p.sun_events.find((e) => e.event === 'sun_set');
        const sr = [...p.sun_events].reverse().find((e) => e.event === 'sun_rise');
        const t0 = ss ? ss.time : p.times[0], t1 = sr && sr.time > t0 ? sr.time : p.times[p.times.length - 1];
        const slider = $('skySlider');
        slider.min = String(t0);
        slider.max = String(t1);
        slider.step = String(5 * 60000);
        $('skyFrom').textContent = fmtTime(t0);
        $('skyTo').textContent = fmtTime(t1);
        // Start at now if it is tonight, else at the start of the best window, else the target's peak.
        const now = Date.now();
        const best = p.windows[0], hi = p.target_events.find((e) => e.event === 'highest');
        const start = now > t0 && now < t1 ? now : best ? best.start : hi && hi.time > t0 && hi.time < t1 ? hi.time : (t0 + t1) / 2;

        const key = `${p.times[0]}|${loc.lat}|${loc.lon}`;
        const prev = sky && sky.key === key ? sky.data : null;
        sky = { data: prev, key, p, name, loc, t0, t1 };
        slider.value = String(start);
        if (!prev) {
            try {
                const q = new URLSearchParams({ lat: loc.lat, lon: loc.lon, start: Astro.utcIso(new Date(p.times[0])) });
                const resp = await fetch(`/api/skychart?${q}`);
                if (!resp.ok) throw new Error();
                const data = await resp.json();
                if (sky.key !== key) return;            // a newer plan replaced this one
                sky.data = data;
                Astro.saved.put('sky', { key, data });
            } catch (e) {
                if (sky.key !== key) return;            // a newer plan replaced this one
                const keep = Astro.saved.get('sky');
                if (keep && keep.data.key === key) {
                    sky.data = keep.data.data;          // offline: the chart saved with this plan
                } else {
                    $('skyPanel').hidden = true;
                    return;
                }
            }
        }
        $('skyPanel').hidden = false;
        // Draw the planned moment straight away, so the chart is never blank. Then, if the page
        // is on screen, the sky turns quickly into that moment so it reads as time passing.
        drawSky();
        if (!reduceMotion() && !document.hidden) {
            runAnim(Math.max(sky.t0, start - 3 * 3600000), start, 900, easeOut);
        }
    }

    $('skySlider').addEventListener('input', () => { stopEverything(); drawSky(); });
    let resizeTimer = null;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => { if (lastPlan) drawChart(lastPlan.p); }, 150);
    });

    function markPlannedNight() {
        for (const c of document.querySelectorAll('.moon-day')) {
            const on = c.dataset.date === $('planDate').value;
            c.classList.toggle('moon-day-planned', on);
            if (on) c.setAttribute('aria-current', 'date'); else c.removeAttribute('aria-current');
        }
    }
    $('planDate').addEventListener('change', markPlannedNight);

    async function loadMoonCycle() {
        const now = Astro.zoned(Date.now());
        const today = new Date(Astro.zonedToMs(now.y, now.m, now.d, 0));   // midnight at the site
        try {
            let data;
            try {
                const resp = await fetch(`/api/moon?start=${encodeURIComponent(Astro.utcIso(today))}&days=30`);
                if (!resp.ok) return;
                data = await resp.json();
                Astro.saved.put('moon', data);
            } catch (err) {
                const keep = Astro.saved.get('moon');
                if (!keep) return;
                data = keep.data;                       // offline: the last 30 nights saved
            }
            const strip = $('moonStrip');
            strip.innerHTML = '';
            const eventsByDay = {};
            for (const e of data.events) eventsByDay[Astro.isoDate(new Date(e.time))] = e.event;
            for (const d of data.days) {
                // Label each sample by the local date at midday, so a daylight-saving change
                // (a 23 or 25 hour day) can't shift it onto the neighbouring date.
                const date = new Date(d.time + 12 * 3600000);
                const cell = document.createElement('button');
                cell.type = 'button';
                cell.className = 'moon-day';
                cell.dataset.date = Astro.isoDate(date);
                if (d.illumination < 0.3) cell.classList.add('moon-day-dark');
                cell.addEventListener('click', () => {
                    $('planDate').value = cell.dataset.date;
                    if (ObserverLocation.get() && $('targetName').value.trim()) $('planForm').requestSubmit();
                    else $('planDate').focus();
                    markPlannedNight();
                    $('planForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
                });
                const ev = eventsByDay[Astro.isoDate(date)];
                if (ev) cell.classList.add('moon-day-event');
                const label = `${fmtDay(date.getTime())}: Moon ${Math.round(d.illumination * 100)}% lit${ev ? `, ${ev}` : ''}` +
                              `${d.illumination < 0.3 ? ', a dark night' : ''}. Plan this night`;
                cell.title = label;
                cell.setAttribute('aria-label', label);
                cell.innerHTML = Astro.moonSVG(d.illumination, d.waxing, 26) +
                    `<span class="moon-date">${Astro.zoned(date.getTime()).d}</span>`;
                strip.appendChild(cell);
            }
            $('moonEvents').textContent = data.events.slice(0, 4)
                .map((e) => `${e.event}: ${fmtDay(e.time)} ${fmtTime(e.time)}`).join(' · ');
            $('moonCycle').hidden = false;
            Astro.motion.stagger(strip.children, { step: 12, max: 360, ms: 260 });
            markPlannedNight();
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
        let shown = null;
        try {
            const resp = await Astro.postJSON('/api/plan', {
                ...target, lat: loc.lat, lon: loc.lon, start: Astro.utcIso(start), min_alt: Number($('minAlt').value) || 0,
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Planning failed.');
            Astro.offlineNote($('offlineNote'), null);
            Astro.saved.put('plan', { data, name, loc });
            shown = [data, name, loc];
        } catch (err) {
            const keep = Astro.saved.get('plan');
            if (Astro.isOffline(err) && keep) {
                Astro.offlineNote($('offlineNote'), keep.at, `plan for ${keep.data.name}`);
                shown = [keep.data.data, keep.data.name, keep.data.loc];
            } else {
                $('formError').textContent = err.message;
            }
        }
        // Drawn outside the request's try, so a drawing bug shows as an error, not as "offline".
        try {
            if (shown) render(...shown);
        } catch (err) {
            $('formError').textContent = 'The plan could not be drawn: ' + err.message;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Plan the night';
        }
    });

    loadMoonCycle();
    if (restored && ObserverLocation.get()) $('planForm').requestSubmit();
})();
