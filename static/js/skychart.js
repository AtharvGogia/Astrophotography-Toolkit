'use strict';

/* All-sky chart: the whole sky above one place at one moment, as if lying on your back.
   The rim is the horizon, the centre is straight overhead, north at the top and east on the
   left (the mirror image of a map, because you are looking up). Azimuthal equidistant:
   distance from the centre is proportional to 90° minus altitude.

   SkyChart.horizontal(ra, dec, ms, lat, lon) -> {alt, az} is exported for testing. */
const SkyChart = (() => {
    const NS = 'http://www.w3.org/2000/svg';
    const D = Math.PI / 180;
    const SIZE = 600, C = SIZE / 2, R = 270;       // chart is SIZE×SIZE, horizon radius R

    const el = (name, attrs, text) => {
        const n = document.createElementNS(NS, name);
        for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
        if (text != null) n.textContent = text;
        return n;
    };

    // Local sidereal time in degrees (IAU 1982 GMST, good to a fraction of a second here).
    function lst(ms, lon) {
        const jd = ms / 86400000 + 2440587.5;
        return (((280.46061837 + 360.98564736629 * (jd - 2451545.0) + lon) % 360) + 360) % 360;
    }

    function horizontal(ra, dec, ms, lat, lon) {
        const h = (lst(ms, lon) - ra) * D, d = dec * D, p = lat * D;
        const sinAlt = Math.sin(p) * Math.sin(d) + Math.cos(p) * Math.cos(d) * Math.cos(h);
        const alt = Math.asin(Math.max(-1, Math.min(1, sinAlt)));
        const az = Math.atan2(-Math.cos(d) * Math.sin(h), Math.sin(d) * Math.cos(p) - Math.cos(d) * Math.cos(h) * Math.sin(p));
        return { alt: alt / D, az: ((az / D) % 360 + 360) % 360 };
    }

    // Chart position for an altitude/azimuth. Below the horizon it carries on outwards (clipped).
    function xy(alt, az) {
        const r = (90 - alt) / 90 * R;
        return [C - r * Math.sin(az * D), C - r * Math.cos(az * D)];
    }

    // Interpolated RA/Dec of a body at time ms from samples every few minutes.
    function bodyAt(samples, times, ms) {
        const f = (ms - times[0]) / (times[times.length - 1] - times[0]) * (times.length - 1);
        const i = Math.max(0, Math.min(times.length - 2, Math.floor(f)));
        const t = Math.max(0, Math.min(1, f - i));
        const [ra0, dec0] = samples[i], [ra1, dec1] = samples[i + 1];
        let dra = ra1 - ra0;
        if (dra > 180) dra -= 360;
        if (dra < -180) dra += 360;
        return [ra0 + dra * t, dec0 + (dec1 - dec0) * t];
    }

    const BODY_NAMES = { moon: 'Moon', mercury: 'Mercury', venus: 'Venus', mars: 'Mars', jupiter: 'Jupiter', saturn: 'Saturn', sun: 'Sun' };
    const COMPASS8 = [['N', 0], ['NE', 45], ['E', 90], ['SE', 135], ['S', 180], ['SW', 225], ['W', 270], ['NW', 315]];

    /* data: /api/skychart response. opts: {lat, lon, time (ms), sky: CSS class for the sky
       colour, target: {name, ra, dec} or null}. Returns {target: {alt, az}} for captions. */
    function render(svg, data, opts) {
        const { lat, lon, time } = opts;
        svg.innerHTML = '';
        svg.setAttribute('viewBox', `-34 -34 ${SIZE + 68} ${SIZE + 68}`);
        const hz = (ra, dec) => horizontal(ra, dec, time, lat, lon);

        const defs = el('defs');
        const clip = el('clipPath', { id: 'skyClip' });
        clip.appendChild(el('circle', { cx: C, cy: C, r: R }));
        const blur = el('filter', { id: 'mwBlur', x: '-20%', y: '-20%', width: '140%', height: '140%' });
        blur.appendChild(el('feGaussianBlur', { stdDeviation: 9 }));
        defs.append(clip, blur);
        svg.appendChild(defs);

        svg.appendChild(el('circle', { cx: C, cy: C, r: R, class: `sky-disc ${opts.sky || 'band-night'}` }));
        const sky = el('g', { 'clip-path': 'url(#skyClip)' });
        svg.appendChild(sky);

        // Altitude rings and the meridian.
        for (const a of [30, 60]) sky.appendChild(el('circle', { cx: C, cy: C, r: (90 - a) / 90 * R, class: 'sky-ring' }));
        sky.appendChild(el('line', { x1: C, y1: C - R, x2: C, y2: C + R, class: 'sky-ring' }));
        sky.appendChild(el('line', { x1: C - R, y1: C, x2: C + R, y2: C, class: 'sky-ring' }));

        // A run of sky points as polylines, broken where they dip well below the horizon.
        const runs = (pts) => {
            const out = [];
            let cur = [];
            for (const [ra, dec] of pts) {
                const h = hz(ra, dec);
                if (h.alt > -25) cur.push(xy(h.alt, h.az));
                else if (cur.length) { if (cur.length > 1) out.push(cur); cur = []; }
            }
            if (cur.length > 1) out.push(cur);
            return out.map((r) => r.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' '));
        };

        // Milky Way: a soft band along the galactic equator, brightest towards the centre.
        const mw = el('g', { class: 'sky-milkyway', filter: 'url(#mwBlur)' });
        for (const pts of runs(data.milky_way)) {
            mw.appendChild(el('polyline', { points: pts, class: 'mw-outer', 'stroke-width': 18 / 90 * R }));
            mw.appendChild(el('polyline', { points: pts, class: 'mw-inner', 'stroke-width': 7 / 90 * R }));
        }
        sky.appendChild(mw);

        const lines = el('g', { class: 'sky-figures' });
        for (const line of data.lines) for (const pts of runs(line)) lines.appendChild(el('polyline', { points: pts }));
        sky.appendChild(lines);

        const names = el('g', { class: 'sky-con-names' });
        for (const n of data.names) {
            const h = hz(n.ra, n.dec);
            if (h.alt < 8) continue;
            const [x, y] = xy(h.alt, h.az);
            names.appendChild(el('text', { x, y, 'text-anchor': 'middle' }, n.name.toUpperCase()));
        }
        sky.appendChild(names);

        const stars = el('g', { class: 'sky-stars' });
        const starNames = el('g', { class: 'sky-star-names' });
        for (const [ra, dec, mag, colour, name] of data.stars) {
            const h = hz(ra, dec);
            if (h.alt < -1) continue;
            const [x, y] = xy(h.alt, h.az);
            const c = el('circle', { cx: x.toFixed(1), cy: y.toFixed(1), r: Math.max(0.55, Math.min(3.6, 2.9 - 0.5 * mag)).toFixed(2), fill: colour });
            if (name) {
                c.appendChild(el('title', {}, `${name}, mag ${mag.toFixed(1)}`));
                if (h.alt > 3) starNames.appendChild(el('text', { x: x + 5, y: y - 4 }, name));
            }
            stars.appendChild(c);
        }
        sky.appendChild(stars);

        // Galactic centre (the bright core photographers chase).
        const gc = hz(...data.galactic_centre);
        if (gc.alt > 0) {
            const [x, y] = xy(gc.alt, gc.az);
            sky.appendChild(el('text', { x, y: y + 4, class: 'sky-gc', 'text-anchor': 'middle' }, 'Galactic core'));
        }

        // Sun, Moon and planets.
        const bodies = el('g', { class: 'sky-bodies' });
        for (const [key, samples] of Object.entries(data.bodies)) {
            const [ra, dec] = bodyAt(samples, data.body_times, time);
            const h = hz(ra, dec);
            if (h.alt < -1) continue;
            const [x, y] = xy(h.alt, h.az);
            const label = key === 'moon' ? `Moon ${Math.round(data.moon.illumination * 100)}%` : BODY_NAMES[key];
            const r = key === 'moon' || key === 'sun' ? 8 : 3.4;
            const dot = el('circle', { cx: x, cy: y, r, class: `body body-${key}` });
            dot.appendChild(el('title', {}, `${label}: ${Math.round(h.alt)}° up`));
            bodies.append(dot, el('text', { x: x + r + 4, y: y + 4 }, label));
        }

        // The target.
        const labels = [];
        let target = null;
        if (opts.target) {
            target = hz(opts.target.ra, opts.target.dec);
            if (target.alt > -1) {
                const [x, y] = xy(target.alt, target.az);
                const g = el('g', { class: 'sky-target' });
                g.append(el('circle', { cx: x, cy: y, r: 11 }),
                         el('line', { x1: x - 18, y1: y, x2: x - 13, y2: y }), el('line', { x1: x + 13, y1: y, x2: x + 18, y2: y }),
                         el('line', { x1: x, y1: y - 18, x2: x, y2: y - 13 }), el('line', { x1: x, y1: y + 13, x2: x, y2: y + 18 }),
                         el('text', { x: x + 20, y: y - 10 }, opts.target.name));
                labels.push(g);
            }
        }

        // Horizon and compass points (east on the left: we are looking up).
        svg.appendChild(el('circle', { cx: C, cy: C, r: R, class: 'sky-horizon' }));
        for (const [label, az] of COMPASS8) {
            const [x, y] = xy(-9, az);
            svg.appendChild(el('text', { x, y: y + 4, 'text-anchor': 'middle',
                                         class: label.length === 1 ? 'sky-compass major' : 'sky-compass' }, label));
        }
        // Labels go on top, unclipped, so names near the horizon aren't cut off.
        svg.append(starNames, bodies, ...labels);
        return { target };
    }

    return { render, horizontal };
})();

if (typeof module !== 'undefined') module.exports = SkyChart;
