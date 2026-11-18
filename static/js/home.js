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

        $('tonightTitle').textContent = `Tonight · ${ObserverLocation.format(loc)}`;
        if (data.dark_start) {
            $('darkWindow').textContent = `${fmtTime(data.dark_start)}–${fmtTime(data.dark_end)}`;
            $('darkNote').textContent = data.dark_kind === 'astronomical'
                ? 'fully dark (astronomical night)'
                : 'as dark as it gets tonight (nautical twilight; the Sun stays too close below the horizon)';
        } else {
            $('darkWindow').textContent = 'No dark sky';
            $('darkNote').textContent = 'The Sun stays too close to the horizon tonight.';
        }

        const labels = { sun_set: 'Sunset', astronomical_set: 'Dark from', astronomical_rise: 'Dark until', sun_rise: 'Sunrise' };
        const rows = Object.entries(labels).filter(([k]) => data.sun_events[k]).map(([k, label]) => [label, data.sun_events[k]]);
        for (const e of data.moon.events) rows.push([e.event === 'rise' ? 'Moonrise' : 'Moonset', e.time]);
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

        $('homeMoonGlyph').innerHTML = Astro.moonSVG(data.moon.illumination, data.moon.waxing, 56);
        $('homeMoonPhase').textContent = `${data.moon.phase}, ${Math.round(data.moon.illumination * 100)}% lit`;
        $('homeMoonText').textContent = data.moon.illumination > 0.6
            ? 'A bright Moon washes out faint nebulae; clusters, double stars and the Moon itself are good targets.'
            : data.moon.illumination < 0.25 ? 'Little moonlight: a good night for faint nebulae and galaxies.'
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
    }

    load();
})();
