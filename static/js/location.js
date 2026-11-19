// Observing location: one setting shared by every page, stored in this browser only.
// Pages read it with ObserverLocation.get() and listen for the 'location-changed' event.
'use strict';

const ObserverLocation = (() => {
    const KEY = 'astro-location';
    const $ = (id) => document.getElementById(id);

    function get() {
        try {
            const v = JSON.parse(localStorage.getItem(KEY) || 'null');
            if (v && Number.isFinite(v.lat) && Number.isFinite(v.lon)) return v;
        } catch (e) { /* storage blocked or corrupt */ }
        return null;
    }

    function format(loc) {
        if (!loc) return 'Set location';
        const coords = `${Math.abs(loc.lat).toFixed(2)}°${loc.lat >= 0 ? 'N' : 'S'}, ` +
                       `${Math.abs(loc.lon).toFixed(2)}°${loc.lon >= 0 ? 'E' : 'W'}`;
        return loc.name ? `${loc.name} (${coords})` : coords;
    }

    // The time zone at the site (e.g. "America/Phoenix"), so times show as they will there.
    // Gives up after a few seconds so a dead field connection never holds up saving.
    async function lookUpZone(loc) {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 4000);
        try {
            const resp = await fetch(`/api/timezone?lat=${loc.lat}&lon=${loc.lon}`, { signal: ctrl.signal });
            if (resp.ok) return (await resp.json()).tz || null;
        } catch (e) { /* offline or too slow: fall back to this device's zone */ }
        finally { clearTimeout(t); }
        return null;
    }

    let saveSeq = 0;
    async function set(loc) {
        const mine = ++saveSeq;
        const tz = loc.tz || await lookUpZone(loc);
        if (mine !== saveSeq) return;          // a newer location was saved while this one looked up its zone
        loc = tz ? { ...loc, tz } : { ...loc };
        if (!tz) delete loc.tz;
        try { localStorage.setItem(KEY, JSON.stringify(loc)); } catch (e) { /* ignore */ }
        render();
        window.dispatchEvent(new CustomEvent('location-changed', { detail: loc }));
    }

    function render() {
        const btn = $('locationButton');
        if (!btn) return;
        const loc = get();
        // Short label in the header: the name if there is one, else the coordinates.
        btn.textContent = !loc ? 'Set location' : loc.name || format({ lat: loc.lat, lon: loc.lon });
        btn.title = loc ? `Observing from ${format(loc)}. Click to change.` : 'Where you are observing from';
        btn.classList.toggle('unset', !loc);
    }

    function open() {
        const loc = get();
        $('locName').value = loc?.name || '';
        $('locLat').value = loc ? loc.lat : '';
        $('locLon').value = loc ? loc.lon : '';
        $('locError').textContent = '';
        $('locateStatus').textContent = '';
        $('locSearch').value = '';
        closeList();
        picked = null;
        $('locationDialog').showModal();
    }

    // Town and city search (GeoNames, served by /api/places). Picking one fills the fields below
    // and keeps its time zone, so saving needs no second lookup.
    let picked = null, results = [], active = -1, seq = 0, timer = 0;

    function closeList() {
        clearTimeout(timer);
        seq++;                                 // a search still on its way must not reopen the list
        const list = $('locList');
        list.hidden = true;
        list.innerHTML = '';
        $('locSearch').setAttribute('aria-expanded', 'false');
        $('locSearch').removeAttribute('aria-activedescendant');
        results = [];
        active = -1;
    }

    function renderList(message) {
        const list = $('locList'), input = $('locSearch');
        list.innerHTML = '';
        if (message) {
            const li = document.createElement('li');
            li.className = 'combo-empty';
            li.textContent = message;
            list.append(li);
        }
        results.forEach((p, i) => {
            const li = document.createElement('li');
            li.id = `locOpt${i}`;
            li.setAttribute('role', 'option');
            li.setAttribute('aria-selected', String(i === active));
            const name = document.createElement('span');
            name.className = 'opt-name';
            name.textContent = p.name;
            const meta = document.createElement('span');
            meta.className = 'opt-meta';
            meta.textContent = [p.region, p.country].filter(Boolean).join(', ');
            li.append(name, meta);
            li.addEventListener('mousedown', (e) => { e.preventDefault(); pick(i); });
            list.append(li);
        });
        list.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        if (active >= 0) input.setAttribute('aria-activedescendant', `locOpt${active}`);
        else input.removeAttribute('aria-activedescendant');
    }

    async function search() {
        const q = $('locSearch').value.trim();
        const mine = ++seq;
        if (!q) { closeList(); return; }
        try {
            const resp = await fetch(`/api/places?q=${encodeURIComponent(q)}&limit=8`);
            const found = resp.ok ? await resp.json() : [];
            if (mine !== seq) return;
            results = found;
            active = results.length ? 0 : -1;
            renderList(results.length ? '' : 'No town or city by that name. Enter coordinates below.');
        } catch (e) {
            if (mine !== seq) return;
            results = [];
            active = -1;
            renderList('Search needs a connection. Enter coordinates below instead.');
        }
    }

    function pick(i) {
        const p = results[i];
        if (!p) return;
        picked = { lat: p.lat, lon: p.lon, tz: p.tz };
        $('locName').value = p.name.slice(0, 40);
        $('locLat').value = p.lat;
        $('locLon').value = p.lon;
        $('locSearch').value = p.label;
        $('locError').textContent = '';
        $('locateStatus').textContent = '';
        closeList();
        $('locSave').focus();
    }

    function wire() {
        render();
        // A location saved before time zones were kept: look its zone up once.
        const saved = get();
        if (saved && !saved.tz) {
            lookUpZone(saved).then((tz) => {
                const now = get();             // only if the location was not changed meanwhile
                if (tz && now && now.lat === saved.lat && now.lon === saved.lon && !now.tz) set({ ...now, tz });
            });
        }
        const dialog = $('locationDialog');
        if (!dialog) return;
        $('locationButton').addEventListener('click', open);
        $('locCancel').addEventListener('click', () => dialog.close());

        $('locateMe').addEventListener('click', () => {
            if (!navigator.geolocation) {
                $('locateStatus').textContent = 'This browser cannot share its location. Enter it below instead.';
                return;
            }
            $('locateStatus').textContent = 'Asking your browser for your location…';
            navigator.geolocation.getCurrentPosition((pos) => {
                $('locLat').value = pos.coords.latitude.toFixed(4);
                $('locLon').value = pos.coords.longitude.toFixed(4);
                $('locateStatus').textContent = `Found it (accurate to about ${Math.round(pos.coords.accuracy)} m). Press Save.`;
            }, (err) => {
                $('locateStatus').textContent = err.code === err.PERMISSION_DENIED
                    ? 'Location permission was declined. Enter your coordinates below instead.'
                    : 'Could not get your location. Enter your coordinates below instead.';
            }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
        });

        $('locationForm').addEventListener('submit', (e) => {
            const lat = Number($('locLat').value), lon = Number($('locLon').value);
            const okLat = $('locLat').value.trim() !== '' && lat >= -90 && lat <= 90;
            const okLon = $('locLon').value.trim() !== '' && lon >= -180 && lon <= 180;
            if (!okLat || !okLon) {
                e.preventDefault();
                $('locError').textContent = 'Latitude must be between −90 and 90, longitude between −180 and 180.';
                return;
            }
            const loc = { lat, lon, name: $('locName').value.trim().slice(0, 40) };
            // Keep the picked place's zone only if its coordinates were not edited afterwards.
            if (picked && picked.lat === lat && picked.lon === lon) loc.tz = picked.tz;
            set(loc);
        });

        const input = $('locSearch');
        input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, 120); });
        input.addEventListener('keydown', (e) => {
            const open = !$('locList').hidden && results.length;
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                if (!open) return;
                e.preventDefault();
                const step = e.key === 'ArrowDown' ? 1 : -1;
                active = (active + step + results.length) % results.length;
                renderList();
                $(`locOpt${active}`)?.scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'Enter') {
                // Enter picks a suggestion; it never submits the form from the search box.
                e.preventDefault();
                if (open && active >= 0) pick(active);
            } else if (e.key === 'Escape') {
                if (!$('locList').hidden) {
                    e.preventDefault();      // close the list, not the dialog
                    e.stopPropagation();
                }
                closeList();                 // and cancel a search still on its way
            }
        });
        input.addEventListener('blur', () => setTimeout(closeList, 100));
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
    else wire();

    return { get, set, format, open };
})();
