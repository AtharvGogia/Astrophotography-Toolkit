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

    function set(loc) {
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
        $('locationDialog').showModal();
    }

    function wire() {
        render();
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
            set({ lat, lon, name: $('locName').value.trim().slice(0, 40) });
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
    else wire();

    return { get, set, format, open };
})();
