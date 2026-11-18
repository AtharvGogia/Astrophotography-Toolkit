"""Night planning: twilight, when a target rises, peaks and sets, where to look, and the Moon.

All computations use astropy. Times go in and out as UTC (ISO strings or Unix milliseconds);
the browser shows them in the viewer's local time zone.

A "night" is the 24 hours from local noon on the chosen date to local noon the next day;
the browser sends that noon as `start` (UTC).
"""
import functools
import math
import warnings

import numpy as np
from astropy import units as u
from astropy.coordinates import (AltAz, EarthLocation, GeocentricTrueEcliptic, SkyCoord, get_body,
                                 get_sun)
from astropy.time import Time
from astropy.utils import iers

from . import catalogs

# Work offline: use the IERS data bundled with astropy instead of downloading updates.
# Beyond its range astropy falls back to mean polar motion: arcsecond-level, irrelevant here.
iers.conf.auto_download = False
iers.conf.auto_max_age = None
warnings.filterwarnings('ignore', message='.*polar motion.*')
warnings.filterwarnings('ignore', message='.*after IERS data is valid.*')
warnings.filterwarnings('ignore', category=u.UnitsWarning)

STEP_MIN = 5
SAMPLES = 24 * 60 // STEP_MIN + 1                  # 289 samples, noon to noon

# Sun altitude thresholds (degrees). Sunset/sunrise uses the standard -0.833° (refraction + radius).
TWILIGHT = {'sun': -0.833, 'civil': -6.0, 'nautical': -12.0, 'astronomical': -18.0}

COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def compass(az_deg):
    return COMPASS[int(((az_deg % 360) + 11.25) // 22.5) % 16]


def _ms(t):
    """astropy Time (scalar or array) -> Unix milliseconds (int or list)."""
    v = (t.unix * 1000).round()
    return int(v) if np.isscalar(v) or np.ndim(v) == 0 else v.astype(np.int64).tolist()


def _crossings(times, alt, threshold):
    """Times where `alt` crosses `threshold`, linearly interpolated: [(Time, 'up'|'down'), ...]."""
    a = alt - threshold
    # Count a sample that lands exactly on the threshold once, on the step that reaches it.
    idx = np.flatnonzero(((a[:-1] < 0) & (a[1:] >= 0)) | ((a[:-1] > 0) & (a[1:] <= 0)))
    out = []
    for i in idx:
        f = a[i] / (a[i] - a[i + 1]) if a[i] != a[i + 1] else 0.0
        t = times[i] + (times[i + 1] - times[i]) * f
        out.append((t, 'up' if a[i + 1] > a[i] else 'down'))
    return out


def _intervals(mask):
    """Index runs where mask is True: [(start, end_inclusive), ...]."""
    runs, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def moon_phase(t):
    """(illuminated fraction 0..1, waxing bool, phase name) for a Time, geocentric."""
    sun = get_sun(t)
    moon = get_body('moon', t)
    elong = sun.separation(moon).rad
    illum = (1 - math.cos(elong)) / 2
    lon_sun = sun.transform_to(GeocentricTrueEcliptic(equinox=t)).lon.deg
    lon_moon = moon.transform_to(GeocentricTrueEcliptic(equinox=t)).lon.deg
    waxing = ((lon_moon - lon_sun) % 360) < 180
    if illum < 0.03:
        name = 'New Moon'
    elif illum > 0.97:
        name = 'Full Moon'
    elif 0.45 <= illum <= 0.55:
        name = 'First Quarter' if waxing else 'Last Quarter'
    elif illum < 0.5:
        name = 'Waxing Crescent' if waxing else 'Waning Crescent'
    else:
        name = 'Waxing Gibbous' if waxing else 'Waning Gibbous'
    return float(illum), bool(waxing), name


@functools.lru_cache(maxsize=32)
def _night(lat, lon, start_iso):
    """Shared per-night data: sample times, Sun and Moon positions, twilight events."""
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
    t0 = Time(start_iso, scale='utc')
    times = t0 + np.arange(SAMPLES) * STEP_MIN * u.min
    frame = AltAz(obstime=times, location=loc)
    sun = get_sun(times).transform_to(frame)
    moon = get_body('moon', times, loc).transform_to(frame)
    sun_alt = sun.alt.deg
    events = {}
    for name, thr in TWILIGHT.items():
        for t, d in _crossings(times, sun_alt, thr):
            key = f'{name}_{"set" if d == "down" else "rise"}'
            events.setdefault(key, t)
    return loc, times, frame, sun_alt, moon


def _dark_mask(sun_alt):
    """Samples that are properly dark: astronomical night, or nautical if it never gets that dark."""
    astro = sun_alt <= TWILIGHT['astronomical']
    if astro.any():
        return astro, 'astronomical'
    return sun_alt <= TWILIGHT['nautical'], 'nautical'


def plan(lat, lon, start_iso, ra, dec, min_alt=30.0):
    loc, times, frame, sun_alt, moon = _night(round(lat, 4), round(lon, 4), start_iso)
    target = SkyCoord(ra * u.deg, dec * u.deg).transform_to(frame)
    alt, az = target.alt.deg, target.az.deg
    moon_alt = moon.alt.deg

    # Sun / twilight events in time order.
    sun_events = []
    for name, thr in TWILIGHT.items():
        for t, d in _crossings(times, sun_alt, thr):
            sun_events.append({'event': f'{name}_{"set" if d == "down" else "rise"}', 'time': _ms(t)})
    sun_events.sort(key=lambda e: e['time'])

    # Target: rise, set, highest point.
    rises = [(t, d) for t, d in _crossings(times, alt, 0.0)]
    i_max = int(np.argmax(alt))
    target_events = []
    for t, d in rises:
        a = SkyCoord(ra * u.deg, dec * u.deg).transform_to(AltAz(obstime=t, location=loc)).az.deg
        target_events.append({'event': 'rise' if d == 'up' else 'set', 'time': _ms(t),
                              'az': round(float(a), 1), 'direction': compass(a)})
    target_events.append({'event': 'highest', 'time': _ms(times[i_max]), 'alt': round(float(alt[i_max]), 1),
                          'az': round(float(az[i_max]), 1), 'direction': compass(az[i_max])})
    target_events.sort(key=lambda e: e['time'])

    # Theoretical best: meridian altitude.
    culmination = 90 - abs(lat - dec)
    always_up = (lat >= 0 and dec > 90 - lat) or (lat < 0 and dec < -90 - lat)
    never_up = (lat >= 0 and dec < lat - 90) or (lat < 0 and dec > 90 + lat)

    # Best window: dark and above the minimum altitude; prefer the longest run.
    dark, dark_kind = _dark_mask(sun_alt)
    good = dark & (alt >= min_alt)
    windows = []
    for s, e in _intervals(good):
        if e == s:
            continue                                   # a single 5-minute sample is not a window
        seg_moon = moon_alt[s:e + 1] > 0
        windows.append({'start': _ms(times[s]), 'end': _ms(times[e]),
                        'minutes': int((e - s) * STEP_MIN),
                        'peak_alt': round(float(alt[s:e + 1].max()), 1),
                        'moon_up_fraction': round(float(seg_moon.mean()), 2)})
    windows.sort(key=lambda w: -w['minutes'])

    # Moon.
    mid = times[len(times) // 2]
    illum, waxing, phase = moon_phase(mid)
    moon_events = [{'event': 'rise' if d == 'up' else 'set', 'time': _ms(t)}
                   for t, d in _crossings(times, moon_alt, 0.125)]   # ~ upper limb + refraction
    sep = float(SkyCoord(ra * u.deg, dec * u.deg).separation(get_body('moon', mid, loc)).deg)

    return {
        'times': _ms(times),
        'target_alt': np.round(alt, 2).tolist(),
        'target_az': np.round(az, 1).tolist(),
        'sun_alt': np.round(sun_alt, 2).tolist(),
        'moon_alt': np.round(moon_alt, 2).tolist(),
        'sun_events': sun_events,
        'target_events': target_events,
        'culmination': round(culmination, 1),
        'always_up': bool(always_up),
        'never_up': bool(never_up),
        'min_alt': min_alt,
        'dark_kind': dark_kind,
        'windows': windows,
        'moon': {'illumination': round(illum, 3), 'waxing': waxing, 'phase': phase,
                 'events': moon_events, 'separation': round(sep, 1)},
    }


def moon_cycle(start_iso, days=30):
    """Daily Moon phase for `days` days, plus the exact times of the next new/full Moon and quarters."""
    t0 = Time(start_iso, scale='utc')
    hourly = t0 + np.arange(days * 24 + 1) * u.hour
    sun = get_sun(hourly)
    moon = get_body('moon', hourly)
    lon_sun = sun.transform_to(GeocentricTrueEcliptic(equinox=hourly)).lon.deg
    lon_moon = moon.transform_to(GeocentricTrueEcliptic(equinox=hourly)).lon.deg
    # Phase angle in ecliptic longitude: 0 new, 90 first quarter, 180 full, 270 last quarter.
    phase = (lon_moon - lon_sun) % 360
    events = []
    for target, name in ((0, 'New Moon'), (90, 'First Quarter'), (180, 'Full Moon'), (270, 'Last Quarter')):
        d = ((phase - target + 180) % 360) - 180          # signed distance to the target angle
        idx = np.flatnonzero((d[:-1] < 0) & (d[1:] >= 0))
        for i in idx:
            f = -d[i] / (d[i + 1] - d[i])
            t = hourly[i] + (hourly[i + 1] - hourly[i]) * f
            events.append({'event': name, 'time': _ms(t)})
    events.sort(key=lambda e: e['time'])

    daily = []
    for k in range(days):
        i = k * 24
        illum = (1 - math.cos(math.radians(phase[i]))) / 2
        daily.append({'time': _ms(hourly[i]), 'illumination': round(illum, 3),
                      'waxing': bool(phase[i] < 180), 'phase_angle': round(float(phase[i]), 1)})
    return {'days': daily, 'events': events}


@functools.lru_cache(maxsize=16)
def tonight(lat, lon, start_iso, limit=10, min_alt=25.0):
    """Darkness and Moon for the night, and the best-placed showpiece objects."""
    loc, times, frame, sun_alt, moon = _night(round(lat, 4), round(lon, 4), start_iso)
    dark, dark_kind = _dark_mask(sun_alt)
    sun_events = {}
    for name, thr in TWILIGHT.items():
        for t, d in _crossings(times, sun_alt, thr):
            sun_events.setdefault(f'{name}_{"set" if d == "down" else "rise"}', _ms(t))
    mid = times[len(times) // 2]
    illum, waxing, phase = moon_phase(mid)
    moon_events = [{'event': 'rise' if d == 'up' else 'set', 'time': _ms(t)}
                   for t, d in _crossings(times, moon.alt.deg, 0.125)]

    picks = []
    if dark.any():
        idx = np.flatnonzero(dark)[::3]                    # every 15 min of darkness
        sub_times = times[idx]
        cands = [t for t in catalogs.targets()
                 if t.kind not in ('Star', 'Constellation') and t.featured and t.mag is not None and t.mag <= 8.5]
        sky = SkyCoord([c.ra for c in cands] * u.deg, [c.dec for c in cands] * u.deg)
        sub_frame = AltAz(obstime=sub_times[:, None], location=loc)
        altaz = sky[None, :].transform_to(sub_frame)
        alts = altaz.alt.deg                                # (times, targets)
        best_i = np.argmax(alts, axis=0)
        best_alt = alts[best_i, np.arange(len(cands))]
        for j, c in enumerate(cands):
            if best_alt[j] < min_alt:
                continue
            # Brighter and higher is better; a little bonus for large, photogenic objects.
            score = best_alt[j] - 4.0 * c.mag + min(10.0, (c.size or 0) / 6)
            picks.append({'name': c.name, 'kind': c.kind, 'constellation': c.con, 'mag': c.mag,
                          'ra': c.ra, 'dec': c.dec,
                          'best_alt': round(float(best_alt[j]), 1),
                          'best_time': _ms(sub_times[best_i[j]]),
                          'direction': compass(float(altaz.az.deg[best_i[j], j])),
                          'score': score})
        picks.sort(key=lambda p: -p['score'])
        for p in picks:
            p.pop('score')

    # If the chosen "noon" falls during this location's night (browser time zone far from the
    # observing site), darkness is split across both ends of the range: report the longest stretch.
    dark_runs = _intervals(dark)
    longest = max(dark_runs, key=lambda r: r[1] - r[0]) if dark_runs else None
    return {
        'dark_kind': dark_kind,
        'dark_start': _ms(times[longest[0]]) if longest else None,
        'dark_end': _ms(times[longest[1]]) if longest else None,
        'sun_events': sun_events,
        'moon': {'illumination': round(illum, 3), 'waxing': waxing, 'phase': phase, 'events': moon_events},
        'highlights': picks[:limit],
    }
