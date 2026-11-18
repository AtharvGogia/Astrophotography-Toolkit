"""Data for the all-sky chart on the planner page.

The browser turns RA/Dec into altitude/azimuth itself for whatever time the slider picks, so the
fixed sky (stars, constellation figures, the Milky Way) is sent once, and the Sun, Moon and
planets are sent as positions through the night for the browser to interpolate.

Positions are J2000 / ICRS. Precession since 2000 shifts the sky by about 0.4° in 2026, which is
invisible on a whole-sky chart.
"""
import functools
import math

import numpy as np
from astropy import units as u
from astropy.coordinates import EarthLocation, SkyCoord, get_body, get_sun
from astropy.time import Time

from . import catalogs
from .planner import moon_phase
from .starfield import bv_to_rgb

STAR_MAG_LIMIT = 5.0          # what a reasonably dark site shows to the naked eye
NAMED_STAR_MAG = 1.6          # label stars brighter than this
LINE_STEP_DEG = 2.5           # spacing of points along constellation lines (they curve on the chart)
BODY_STEP_MIN = 20
BODIES = ['moon', 'mercury', 'venus', 'mars', 'jupiter', 'saturn']


def _unit(ra, dec):
    ra, dec = np.radians(ra), np.radians(dec)
    return np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)], axis=-1)


def _radec(v):
    v = v / np.linalg.norm(v, axis=-1, keepdims=True)
    return np.degrees(np.arctan2(v[..., 1], v[..., 0])) % 360, np.degrees(np.arcsin(np.clip(v[..., 2], -1, 1)))


def _densify(line):
    """Points along a constellation line every LINE_STEP_DEG on the sphere."""
    out = []
    for (ra1, dec1), (ra2, dec2) in zip(line[:-1], line[1:]):
        a, b = _unit(ra1, dec1), _unit(ra2, dec2)
        omega = math.acos(max(-1.0, min(1.0, float(a @ b))))
        n = max(1, int(math.ceil(math.degrees(omega) / LINE_STEP_DEG)))
        t = np.linspace(0, 1, n + 1)[:-1, None]
        if omega < 1e-9:
            pts = np.repeat(a[None, :], len(t), axis=0)
        else:
            pts = (np.sin((1 - t) * omega) * a + np.sin(t * omega) * b) / math.sin(omega)
        r, d = _radec(pts)
        out.extend(zip(r, d))
    out.append(tuple(line[-1]))
    return [[round(float(r), 2), round(float(d), 2)] for r, d in out]


@functools.lru_cache(maxsize=1)
def fixed_sky():
    """Stars, constellation figures and names, and the Milky Way's centre line (cached)."""
    stars = [s for s in catalogs.load_stars() if s['mag'] <= STAR_MAG_LIMIT]
    stars.sort(key=lambda s: s['mag'])
    colours = bv_to_rgb(np.array([s['ci'] if s['ci'] is not None else np.nan for s in stars], dtype=float))
    star_rows = []
    for s, c in zip(stars, colours):
        row = [round(s['ra'], 3), round(s['dec'], 3), round(s['mag'], 2),
               '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c)]
        if s['proper'] and s['mag'] <= NAMED_STAR_MAG:
            row.append(s['proper'])
        star_rows.append(row)

    lines, names = [], []
    for abbr, figure in catalogs.constellation_lines():
        verts = [p for line in figure for p in line]
        for line in figure:
            if len(line) > 1:
                lines.append(_densify(line))
        # Name at the mean direction of the figure's vertices.
        ra, dec = _radec(_unit(np.array([p[0] for p in verts]), np.array([p[1] for p in verts])).mean(axis=0))
        names.append({'name': catalogs.CONSTELLATIONS.get(abbr, abbr), 'ra': round(float(ra), 2),
                      'dec': round(float(dec), 2)})

    gal = SkyCoord(l=np.arange(0, 361, 2) * u.deg, b=np.zeros(181) * u.deg, frame='galactic').icrs
    centre = SkyCoord(l=0 * u.deg, b=0 * u.deg, frame='galactic').icrs
    return {
        'stars': star_rows,
        'lines': lines,
        'names': names,
        'milky_way': [[round(float(r), 2), round(float(d), 2)] for r, d in zip(gal.ra.deg, gal.dec.deg)],
        'galactic_centre': [round(float(centre.ra.deg), 2), round(float(centre.dec.deg), 2)],
    }


def sky_chart(lat, lon, start_iso):
    """Fixed sky plus Sun, Moon and planet positions every BODY_STEP_MIN over the 24 h from start."""
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
    t0 = Time(start_iso, scale='utc')
    times = t0 + np.arange(0, 24 * 60 + 1, BODY_STEP_MIN) * u.min
    bodies = {}
    for name in BODIES:
        c = get_body(name, times, loc)            # topocentric for the Moon (parallax up to 1°)
        bodies[name] = [[round(float(r), 3), round(float(d), 3)] for r, d in zip(c.ra.deg, c.dec.deg)]
    sun = get_sun(times)
    bodies['sun'] = [[round(float(r), 3), round(float(d), 3)] for r, d in zip(sun.ra.deg, sun.dec.deg)]
    illum, waxing, phase = moon_phase(times[len(times) // 2])
    return {
        **fixed_sky(),
        'body_times': ((times.unix * 1000).round().astype(np.int64)).tolist(),
        'bodies': bodies,
        'moon': {'illumination': round(illum, 3), 'waxing': waxing, 'phase': phase},
    }
