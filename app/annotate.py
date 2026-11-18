"""Label a plate-solved photo: named stars, deep-sky objects, constellation figures and names,
and an RA/Dec grid.

Everything is returned in full-resolution pixel coordinates (0-based, x right, y down),
so the browser can draw it as an SVG layer with viewBox="0 0 width height".
"""
import math
import warnings

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord, get_constellation

from . import catalogs

# Inverting a SIP model for sky positions well outside the frame may not converge; those
# positions are discarded anyway. Filtered once here (catch_warnings is not thread-safe).
warnings.filterwarnings('ignore', message=".*failed to converge to the requested accuracy.*")

# RA grid steps in degrees (1h = 15°) and Dec steps, coarsest first.
RA_STEPS = [30, 15, 7.5, 5, 2.5, 1.25, 0.5, 0.25]
DEC_STEPS = [30, 20, 10, 5, 2, 1, 0.5, 0.25]


def _frame(wcs, width, height):
    centre = wcs.pixel_to_world(width / 2, height / 2)
    corners = wcs.pixel_to_world(np.array([0, width, 0, width]), np.array([0, 0, height, height]))
    half_diag = float(np.nanmax(centre.separation(corners).deg))
    return centre, half_diag


def _project(wcs, ra, dec, width, height, centre, max_sep_deg, margin=0.0):
    """Pixel positions for sky positions, NaN where off the frame (or too far out for the SIP model)."""
    sky = SkyCoord(np.asarray(ra, dtype=float) * u.deg, np.asarray(dec, dtype=float) * u.deg)
    near = centre.separation(sky).deg < max_sep_deg
    x = np.full(len(sky), np.nan)
    y = np.full(len(sky), np.nan)
    if near.any():
        px, py = wcs.world_to_pixel(sky[near])
        x[near], y[near] = px, py
    m = margin * max(width, height)
    off = ~((x >= -m) & (x <= width + m) & (y >= -m) & (y <= height + m))
    x[off] = np.nan
    y[off] = np.nan
    return x, y


def _polylines(x, y, max_jump):
    """Split projected points into runs of finite, nearby points (each run becomes one polyline)."""
    runs, seg = [], []
    for xi, yi in zip(x, y):
        if np.isfinite(xi) and np.isfinite(yi):
            if seg and math.hypot(xi - seg[-1][0], yi - seg[-1][1]) > max_jump:
                if len(seg) > 1:
                    runs.append(seg)
                seg = []
            seg.append([round(float(xi), 1), round(float(yi), 1)])
        else:
            if len(seg) > 1:
                runs.append(seg)
            seg = []
    if len(seg) > 1:
        runs.append(seg)
    return runs


def _great_circle(ra1, dec1, ra2, dec2, n):
    """n points along the great circle between two sky positions (degrees)."""
    def vec(ra, dec):
        ra, dec = math.radians(ra), math.radians(dec)
        return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])
    a, b = vec(ra1, dec1), vec(ra2, dec2)
    omega = math.acos(max(-1.0, min(1.0, float(a @ b))))
    t = np.linspace(0, 1, n)[:, None]
    if omega < 1e-9:
        pts = np.repeat(a[None, :], n, axis=0)
    else:
        pts = (np.sin((1 - t) * omega) * a + np.sin(t * omega) * b) / math.sin(omega)
    ra = np.degrees(np.arctan2(pts[:, 1], pts[:, 0])) % 360
    dec = np.degrees(np.arcsin(np.clip(pts[:, 2], -1, 1)))
    return ra, dec


def constellation_lines(wcs, width, height, centre=None, half_diag=None):
    """Constellation stick figures projected into the image: [{'con': 'Ori', 'points': [[x, y], ...]}]."""
    if centre is None:
        centre, half_diag = _frame(wcs, width, height)
    reach = half_diag * 1.6
    out = []
    # Angular distance of every figure vertex from the frame centre, in one vectorised pass.
    c_ra, c_dec = math.radians(centre.ra.deg), math.radians(centre.dec.deg)

    def dist_deg(ra, dec):
        ra, dec = np.radians(ra), np.radians(dec)
        cos_d = math.sin(c_dec) * np.sin(dec) + math.cos(c_dec) * np.cos(dec) * np.cos(ra - c_ra)
        return np.degrees(np.arccos(np.clip(cos_d, -1, 1)))

    for abbr, lines in catalogs.constellation_lines():
        for line in lines:
            pts = np.asarray(line, dtype=float)
            vdist = dist_deg(pts[:, 0], pts[:, 1])
            ras, decs = [], []
            for k, ((ra1, dec1), (ra2, dec2)) in enumerate(zip(line[:-1], line[1:])):
                # Skip segments nowhere near the frame before doing any projection work.
                if min(vdist[k], vdist[k + 1]) > reach + 30:
                    ras.append(np.nan)
                    decs.append(np.nan)
                    continue
                r, d = _great_circle(ra1, dec1, ra2, dec2, 24)
                ras.extend(r)
                decs.extend(d)
            if not ras:
                continue
            ras, decs = np.asarray(ras), np.asarray(decs)
            ok = np.isfinite(ras)
            x = np.full(len(ras), np.nan)
            y = np.full(len(ras), np.nan)
            if ok.any():
                x[ok], y[ok] = _project(wcs, ras[ok], decs[ok], width, height, centre, reach, margin=0.15)
            for pts in _polylines(x, y, 0.3 * max(width, height)):
                out.append({'con': abbr, 'points': pts})
    return out


def _pick_step(span, steps, target_lines=5):
    for s in steps:
        if span / s >= target_lines:
            return s
    return steps[-1]


def _fmt_ra(deg):
    total = round((deg % 360) / 15 * 60)          # minutes of time
    h, m = divmod(total, 60)
    return f'{h % 24}h' if m == 0 else f'{h % 24}h{m:02d}m'


def _fmt_dec(deg):
    sign = '−' if deg < 0 else '+'
    a = abs(deg)
    return f'{sign}{a:g}°' if a == int(a) else f'{sign}{int(a)}°{round((a - int(a)) * 60):02d}′'


def _grid(wcs, width, height, centre, half_diag):
    # Sky extent of the frame, from a coarse pixel grid.
    gx, gy = np.meshgrid(np.linspace(0, width, 12), np.linspace(0, height, 9))
    sky = wcs.pixel_to_world(gx.ravel(), gy.ravel())
    decs = sky.dec.deg
    ras = ((sky.ra.deg - centre.ra.deg + 180) % 360) - 180   # unwrapped around the centre
    dec_lo, dec_hi = float(np.nanmin(decs)), float(np.nanmax(decs))
    north_in, south_in = (bool(np.isfinite(_project(wcs, [0.0], [p], width, height, centre, half_diag * 1.5)[0][0]))
                          for p in (90.0, -90.0))
    if north_in or south_in:
        dec_hi = 90.0 if north_in else dec_hi
        dec_lo = -90.0 if south_in else dec_lo
        ra_span = 360.0                                    # every meridian crosses the frame
    else:
        ra_lo, ra_hi = float(np.nanmin(ras)), float(np.nanmax(ras))
        ra_span = ra_hi - ra_lo

    cos_dec = max(0.15, math.cos(math.radians(centre.dec.deg)))
    dec_step = _pick_step(dec_hi - dec_lo, DEC_STEPS)
    ra_step = _pick_step(ra_span * cos_dec, RA_STEPS)

    lines = []
    n = 160
    jump = 0.25 * max(width, height)

    # Parallels (lines of constant Dec).
    if north_in or south_in:
        par_ra = np.linspace(0, 360, n * 2)
    else:
        par_ra = centre.ra.deg + np.linspace(ra_lo - 2 * ra_step, ra_hi + 2 * ra_step, n)
    for d in np.arange(math.floor(dec_lo / dec_step) * dec_step, dec_hi + dec_step / 2, dec_step):
        if abs(d) >= 90:
            continue
        x, y = _project(wcs, par_ra % 360, np.full(len(par_ra), d), width, height, centre, half_diag * 1.3, 0.02)
        for pts in _polylines(x, y, jump):
            lines.append({'kind': 'dec', 'label': _fmt_dec(float(d)), 'points': pts})

    # Meridians (lines of constant RA), each listed once even when the span wraps 360°.
    if north_in or south_in:
        meridians = np.arange(0, 360, ra_step)
    else:
        start = math.floor((centre.ra.deg + ra_lo) / ra_step) * ra_step
        meridians = np.arange(start, centre.ra.deg + ra_hi + ra_step, ra_step)
        meridians = np.unique(np.round(meridians % 360, 6))
    dd = np.linspace(max(-89.9, dec_lo - dec_step), min(89.9, dec_hi + dec_step), n)
    for r in meridians:
        x, y = _project(wcs, np.full(n, r % 360), dd, width, height, centre, half_diag * 1.3, 0.02)
        for pts in _polylines(x, y, jump):
            lines.append({'kind': 'ra', 'label': _fmt_ra(float(r)), 'points': pts})
    return lines


def annotate(solution):
    wcs, width, height = solution.wcs, solution.width, solution.height
    centre, half_diag = _frame(wcs, width, height)
    fov = max(solution.fov_w, solution.fov_h)

    # How deep to label depends on how much sky the photo covers.
    star_mag = 2.5 if fov > 45 else 3.5 if fov > 20 else 5.0 if fov > 8 else 6.5
    dso_mag = 6.0 if fov > 45 else 8.0 if fov > 20 else 10.0 if fov > 8 else 12.0

    targets = catalogs.targets()
    stars = [t for t in targets if t.kind == 'Star' and t.mag is not None and t.mag <= star_mag]
    dsos = [t for t in targets if t.kind not in ('Star', 'Constellation')
            and (t.featured or (t.mag is not None and t.mag <= dso_mag))]
    if fov > 45:      # very wide: only well-known objects, or the frame fills with labels
        dsos = [t for t in dsos if t.featured and (t.mag is None or t.mag <= dso_mag + 1)]

    def place(items):
        if not items:
            return []
        x, y = _project(wcs, [t.ra for t in items], [t.dec for t in items], width, height, centre, half_diag * 1.05)
        return [(t, float(xi), float(yi)) for t, xi, yi in zip(items, x, y) if np.isfinite(xi)]

    scale_deg_per_px = max(solution.scale_arcsec, 1e-6) / 3600.0
    out_stars = [{'x': round(x, 1), 'y': round(y, 1), 'label': t.name.split(' · ')[0], 'full': t.name,
                  'mag': t.mag, 'constellation': t.con}
                 for t, x, y in sorted(place(stars), key=lambda p: p[0].mag)]
    out_dsos = [{'x': round(x, 1), 'y': round(y, 1), 'label': t.name, 'kind': t.kind, 'mag': t.mag,
                 'constellation': t.con,
                 'r': round(max(6.0, (t.size or 0) / 60 / 2 / scale_deg_per_px), 1)}
                for t, x, y in sorted(place(dsos), key=lambda p: p[0].rank)]

    # Constellations: which ones the frame covers, labelled at the middle of their part of the frame.
    gx, gy = np.meshgrid(np.linspace(0.04, 0.96, 18) * width, np.linspace(0.04, 0.96, 12) * height)
    gx, gy = gx.ravel(), gy.ravel()
    sky = wcs.pixel_to_world(gx, gy)
    ok = np.isfinite(sky.ra.deg) & np.isfinite(sky.dec.deg)
    gx, gy = gx[ok], gy[ok]
    # astropy spells one name "Ophiucus"; use the IAU spelling.
    names = np.asarray([n.replace('Ophiucus', 'Ophiuchus') for n in get_constellation(sky[ok])]) if ok.any() else np.array([])
    out_cons = []
    for name in dict.fromkeys(names):
        sel = names == name
        if sel.sum() >= 3:
            out_cons.append({'name': str(name), 'x': round(float(gx[sel].mean()), 1),
                             'y': round(float(gy[sel].mean()), 1), 'share': round(float(sel.mean()), 3)})
    out_cons.sort(key=lambda c: -c['share'])

    return {
        'width': width, 'height': height,
        'stars': out_stars,
        'dsos': out_dsos,
        'constellations': out_cons,
        'lines': constellation_lines(wcs, width, height, centre, half_diag),
        'grid': _grid(wcs, width, height, centre, half_diag),
    }
