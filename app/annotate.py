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
from astropy.wcs.utils import proj_plane_pixel_scales

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


def _polylines(x, y, max_jump, ok_step=None):
    """Split projected points into runs of finite, nearby points (each run becomes one polyline).

    ok_step[i] False means the step from point i-1 to i is not to be trusted: break there.
    """
    runs, seg = [], []
    for i, (xi, yi) in enumerate(zip(x, y)):
        if np.isfinite(xi) and np.isfinite(yi):
            if seg and (math.hypot(xi - seg[-1][0], yi - seg[-1][1]) > max_jump
                        or (ok_step is not None and not ok_step[i])):
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


def _steps_ok(ras, decs, x, y, deg_per_px, stretch=2.0):
    """Whether each step along a projected line has a believable length in pixels.

    Consecutive points are a known angle apart on the sky. A real lens (plus the gnomonic
    projection, which stretches up to about 1.5x at the corners of a 70° frame) maps that to
    roughly angle / pixel scale. A distortion polynomial pushed outside the stars it was fitted
    to can stretch or fold far beyond that; such steps would be drawn as long straight chords
    across the photo, so lines break there instead.
    """
    ra, dec = np.radians(ras), np.radians(decs)
    cos_d = (np.sin(dec[1:]) * np.sin(dec[:-1])
             + np.cos(dec[1:]) * np.cos(dec[:-1]) * np.cos(ra[1:] - ra[:-1]))
    expect = np.degrees(np.arccos(np.clip(cos_d, -1, 1))) / deg_per_px
    got = np.hypot(np.diff(x), np.diff(y))
    with np.errstate(invalid='ignore', divide='ignore'):
        ratio = got / expect
    good = ~((ratio > stretch) | (ratio < 1 / (2 * stretch)))
    good |= expect < 1.0                      # coincident points: nothing to judge
    return np.concatenate([[True], good])


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


_star_arrays = None


def _catalog_star_arrays():
    global _star_arrays
    if _star_arrays is None:
        rows = catalogs.load_stars()
        _star_arrays = (np.array([r['ra'] for r in rows]), np.array([r['dec'] for r in rows]),
                        np.array([r['mag'] for r in rows]))
    return _star_arrays


def sky_support(solution, mono, n_stars=150, k_nearest=6, min_found_share=0.5, snr=8.0):
    """Where in the photo there is open sky, as a function (x, y) -> bool array, or None.

    Foreground (mountains, trees, buildings) hides the stars behind it, so constellation lines
    and labels drawn across it are meaningless. For the brightest catalog stars in the frame,
    this looks at the photo itself: is there a clear point of light where the star should be?
    In open sky nearly all of them show; behind the foreground almost none do. A point counts
    as sky when most of the k_nearest bright catalog stars around it were seen.

    Returns None (nothing is hidden) when there is no image or too few bright stars to judge.
    """
    if mono is None:
        return None
    w, h, wcs = solution.width, solution.height, solution.wcs
    ra, dec, mag = _catalog_star_arrays()
    centre, half_diag = _frame(wcs, w, h)
    cx, cy = _project(wcs, ra, dec, w, h, centre, half_diag * 1.05)
    on = np.flatnonzero(np.isfinite(cx))
    if len(on) < 10:
        return None
    on = on[np.argsort(mag[on])][:n_stars]
    sx, sy = cx[on], cy[on]

    # Work on a binned copy about 1500 px across; that is plenty to see bright stars.
    img = np.asarray(mono, dtype=np.float32)
    k = max(1, int(np.ceil(max(img.shape) / 1500)))
    H, W = img.shape[0] // k * k, img.shape[1] // k * k
    small = img[:H, :W].reshape(H // k, k, W // k, k).mean(axis=(1, 3))
    fx, fy = img.shape[1] / w, img.shape[0] / h          # solution pixels -> image pixels
    r = max(2, int(math.ceil(0.006 * max(w, h) * fx / k)))  # allows for the fit's error
    R = 4 * r
    seen = np.zeros(len(on), dtype=bool)
    for i, (x, y) in enumerate(zip(sx * fx / k, sy * fy / k)):
        xi, yi = int(x), int(y)
        win = small[max(0, yi - R):yi + R + 1, max(0, xi - R):xi + R + 1]
        core = small[max(0, yi - r):yi + r + 1, max(0, xi - r):xi + r + 1]
        if win.size < 9 or core.size == 0:
            continue
        med = float(np.median(win))
        noise = float(np.median(np.abs(win - med))) * 1.4826 + 1e-6
        peak = float(core.max())
        # A clear point of light; or, in busy star fields like the Milky Way core where the
        # noise estimate is high, a fainter one that is still the brightest thing around.
        level = (peak - med) / noise
        seen[i] = level > snr or (level > snr / 2 and peak >= float(win.max()))

    from scipy.spatial import cKDTree
    tree = cKDTree(np.column_stack([sx, sy]))
    kq = min(k_nearest, len(on))
    inset = 0.02 * max(w, h)

    def visible(x, y):
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        out = np.zeros(x.shape, dtype=bool)
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.any():
            # Points beyond the border are judged by the sky just inside it.
            q = np.column_stack([np.clip(x[ok], inset, w - inset), np.clip(y[ok], inset, h - inset)])
            _, idx = tree.query(q, k=kq)
            idx = idx.reshape(len(q), -1)
            out[ok] = seen[idx].mean(axis=1) >= min_found_share
        return out
    visible.stars = (sx, sy, seen)
    return visible


def constellation_lines(wcs, width, height, centre=None, half_diag=None, visible=None):
    """Constellation stick figures projected into the image: [{'con': 'Ori', 'points': [[x, y], ...]}].

    visible (from sky_support) splits lines where the photo shows no stars, e.g. over the
    foreground; those parts are returned with 'fg': True so the page can hide them.
    """
    if centre is None:
        centre, half_diag = _frame(wcs, width, height)
    reach = half_diag * 1.6
    deg_per_px = float(np.mean(proj_plane_pixel_scales(wcs.celestial)))
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
            for pts in _polylines(x, y, 0.3 * max(width, height), _steps_ok(ras, decs, x, y, deg_per_px)):
                out.extend(_split_by_sky(abbr, pts, visible))
    return out


def _split_by_sky(abbr, pts, visible):
    """Split one polyline into open-sky and foreground runs that meet at the boundary."""
    if visible is None:
        return [{'con': abbr, 'points': pts}]
    arr = np.asarray(pts)
    sky = visible(arr[:, 0], arr[:, 1])
    runs, start = [], 0
    for i in range(1, len(pts) + 1):
        if i == len(pts) or sky[i] != sky[start]:
            end = min(i + 1, len(pts))          # share the boundary point so runs join up
            if end - start > 1:
                run = {'con': abbr, 'points': pts[start:end]}
                if not sky[start]:
                    run['fg'] = True
                runs.append(run)
            start = i
    return runs


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


def annotate(solution, mono=None):
    """mono: the photo (any size, same framing) used to hide overlays over the foreground."""
    wcs, width, height = solution.wcs, solution.width, solution.height
    centre, half_diag = _frame(wcs, width, height)
    fov = max(solution.fov_w, solution.fov_h)
    visible = sky_support(solution, mono)

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
        ok = np.isfinite(x)
        sky = np.ones(len(x), dtype=bool) if visible is None else visible(x, y)
        return [(t, float(xi), float(yi), bool(s)) for t, xi, yi, k, s in zip(items, x, y, ok, sky) if k]

    def fg(on_sky):
        return {} if on_sky else {'fg': True}

    scale_deg_per_px = max(solution.scale_arcsec, 1e-6) / 3600.0
    out_stars = [{'x': round(x, 1), 'y': round(y, 1), 'label': t.name.split(' · ')[0], 'full': t.name,
                  'mag': t.mag, 'constellation': t.con, **fg(sk)}
                 for t, x, y, sk in sorted(place(stars), key=lambda p: p[0].mag)]
    out_dsos = [{'x': round(x, 1), 'y': round(y, 1), 'label': t.name, 'kind': t.kind, 'mag': t.mag,
                 'constellation': t.con,
                 'r': round(max(6.0, (t.size or 0) / 60 / 2 / scale_deg_per_px), 1), **fg(sk)}
                for t, x, y, sk in sorted(place(dsos), key=lambda p: p[0].rank)]

    # Constellations: which ones the frame covers, labelled at the middle of their part of the frame.
    gx, gy = np.meshgrid(np.linspace(0.04, 0.96, 18) * width, np.linspace(0.04, 0.96, 12) * height)
    gx, gy = gx.ravel(), gy.ravel()
    on_sky = np.ones(len(gx), dtype=bool) if visible is None else visible(gx, gy)
    sky = wcs.pixel_to_world(gx, gy)
    ok = np.isfinite(sky.ra.deg) & np.isfinite(sky.dec.deg)
    gx, gy, on_sky = gx[ok], gy[ok], on_sky[ok]
    # astropy spells one name "Ophiucus"; use the IAU spelling.
    names = np.asarray([n.replace('Ophiucus', 'Ophiuchus') for n in get_constellation(sky[ok])]) if ok.any() else np.array([])
    out_cons = []
    for name in dict.fromkeys(names):
        sel = names == name
        if sel.sum() < 3:
            continue
        # Label a constellation in the middle of its open-sky part; one that lies entirely
        # behind the foreground is labelled there and marked as foreground.
        open_sel = sel & on_sky
        use, is_fg = (open_sel, False) if open_sel.sum() >= 3 else (sel, True)
        out_cons.append({'name': str(name), 'x': round(float(gx[use].mean()), 1),
                         'y': round(float(gy[use].mean()), 1), 'share': round(float(sel.mean()), 3),
                         **fg(not is_fg)})
    out_cons.sort(key=lambda c: -c['share'])
    lines = constellation_lines(wcs, width, height, centre, half_diag, visible)

    return {
        'width': width, 'height': height,
        'foreground': visible is not None and bool(
            any(l.get('fg') for l in lines) or any(o.get('fg') for o in out_stars + out_dsos + out_cons)),
        'stars': out_stars,
        'dsos': out_dsos,
        'constellations': out_cons,
        'lines': lines,
        'grid': _grid(wcs, width, height, centre, half_diag),
    }
