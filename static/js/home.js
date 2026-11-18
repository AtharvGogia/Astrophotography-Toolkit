'use strict';

(() => {
    const $ = (id) => document.getElementById(id);
    const { fmtTime } = Astro;

    $('setLocationHome').addEventListener('click', () => ObserverLocation.open());
    window.addEventListener('location-changed', load);

    async function load() {
        const loc = ObserverLocation.get();
        $('tonightError').textContent = '';
        $('tonightNoLocation').hidden = !!loc;
        if (!loc) {
            $('tonightBody').hidden = true;
            return;
        }
        const start = Astro.nightStart();
        let data;
        try {
            const resp = await Astro.postJSON('/api/tonight', { lat: loc.lat, lon: loc.lon, start: Astro.utcIso(start) });
            data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Could not work out tonight.');
        } catch (err) {
            $('tonightError').textContent = err.message;
            return;
        }

        const illum = data.moon.illumination, pct = Math.round(illum * 100);
        $('homeWhere').textContent = `${ObserverLocation.format(loc)} · night of ${Astro.fmtDay(start.getTime())}`;
        // Prefer the exact twilight crossings (as listed in the timeline) over 5-minute samples.
        const ev = data.sun_events, kind = data.dark_kind === 'astronomical' ? 'astronomical' : 'nautical';
        const dStart = ev[`${kind}_set`] || data.dark_start, dEnd = ev[`${kind}_rise`] || data.dark_end;
        const darkRange = data.dark_start ? `${fmtTime(dStart)}–${fmtTime(dEnd)}` : null;
        const moonMatters = illum >= 0.3;
        const moonless = data.moonless_start ? `${fmtTime(data.moonless_start)}–${fmtTime(data.moonless_end)}` : null;
        const darkKind = data.dark_kind === 'astronomical' ? 'fully dark' : 'as dark as it gets (nautical twilight)';
        if (!darkRange) {
            $('darkLabel').textContent = 'Dark';
            $('darkLabel').dataset.sky = 'none';
            $('darkWindow').textContent = 'No dark sky';
            $('darkNote').textContent = 'The Sun stays too close to the horizon tonight.';
        } else if (moonMatters && moonless && moonless !== darkRange) {
            // The answer a beginner needs: when it is dark AND the Moon is out of the way.
            $('darkLabel').textContent = 'Dark and moonless';
            $('darkLabel').dataset.sky = 'moonless';
            $('darkWindow').textContent = moonless;
            $('darkNote').textContent = `The sky is ${darkKind} ${darkRange}; the ${pct}% Moon lights it until the window opens.`;
        } else if (moonMatters && !moonless) {
            $('darkLabel').textContent = 'Dark, but moonlit';
            $('darkLabel').dataset.sky = 'moonlit';
            $('darkWindow').textContent = darkRange;
            $('darkNote').textContent = `${darkKind[0].toUpperCase() + darkKind.slice(1)}, but the ${pct}% Moon is up all night.`;
        } else {
            $('darkLabel').textContent = moonMatters || illum < 0.05 ? 'Dark and moonless' : 'Dark';
            $('darkLabel').dataset.sky = moonMatters || illum < 0.05 ? 'moonless' : 'dark';
            $('darkWindow').textContent = darkRange;
            $('darkNote').textContent = moonMatters || illum < 0.05 ? `${darkKind[0].toUpperCase() + darkKind.slice(1)}, with no Moon in the sky.`
                : `${darkKind[0].toUpperCase() + darkKind.slice(1)}; the Moon is only ${pct}% lit.`;
        }

        // One timeline from sunset to sunrise. Moon events in daylight are summarised, not listed.
        const labels = { sun_set: 'Sunset', astronomical_set: 'Dark from', astronomical_rise: 'Dark until', sun_rise: 'Sunrise' };
        const rows = Object.entries(labels).filter(([k]) => data.sun_events[k]).map(([k, label]) => [label, data.sun_events[k]]);
        const t0 = data.sun_events.sun_set, t1 = data.sun_events.sun_rise;
        for (const e of data.moon.events) {
            if (!t0 || !t1 || (e.time > t0 && e.time < t1)) rows.push([e.event === 'rise' ? 'Moonrise' : 'Moonset', e.time]);
        }
        rows.sort((a, b) => a[1] - b[1]);
        const tbody = $('tonightTable').querySelector('tbody');
        tbody.innerHTML = '';
        for (const [label, t] of rows) {
            const tr = document.createElement('tr');
            const th = document.createElement('th'); th.textContent = label;
            const td = document.createElement('td'); td.textContent = fmtTime(t);
            tr.append(th, td);
            tbody.appendChild(tr);
        }

        Astro.motion.sweepMoon($('homeMoonGlyph'), data.moon.illumination, data.moon.waxing, 56);
        $('homeMoonPhase').textContent = `${data.moon.phase}, ${Math.round(data.moon.illumination * 100)}% lit`;
        $('homeMoonText').textContent = illum > 0.6
            ? 'A bright Moon washes out faint nebulae; clusters, double stars and the Moon itself are good targets.'
            : illum < 0.25 ? 'Little moonlight: a good night for faint nebulae and galaxies.'
            : 'Some moonlight: plan faint targets for when the Moon is down.';

        const body = $('highlightRows');
        body.innerHTML = '';
        if (!data.highlights.length) {
            body.innerHTML = '<tr><td colspan="3">Nothing from the showpiece list gets high enough while it is dark.</td></tr>';
        }
        for (const h of data.highlights) {
            const tr = document.createElement('tr');
            const a = document.createElement('a');
            const q = new URLSearchParams({ target: h.name, ra: h.ra, dec: h.dec, kind: h.kind });
            a.href = `/planner?${q}`;
            a.textContent = h.name;
            const sub = document.createElement('span');
            sub.className = 'sub';
            sub.textContent = `${h.kind} in ${h.constellation}`;
            const td1 = document.createElement('td'); td1.append(a, sub);
            const td2 = document.createElement('td'); td2.textContent = fmtTime(h.best_time);
            const td3 = document.createElement('td'); td3.textContent = `${Math.round(h.best_alt)}° ${h.direction}`;
            tr.append(td1, td2, td3);
            body.appendChild(tr);
        }
        $('tonightBody').hidden = false;
        Astro.motion.stagger($('tonightTable').querySelector('tbody').children, { step: 40, max: 240 });
        Astro.motion.stagger($('highlightRows').children, { step: 35, max: 350 });
    }

    load();
})();
