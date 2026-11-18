"""Turn a tetra3rs attitude into an astropy WCS, then refine it with lens distortion (SIP).

tetra3rs gives a pinhole (pure TAN) solution, which is good near the centre of the frame.
Wide camera lenses bend the edges by many pixels, so we match the detected stars to
catalog stars across the whole frame and fit a TAN-SIP WCS, tightening the match radius
as the fit improves.
"""
import warnings

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.wcs.utils import fit_wcs_from_points
from scipy.spatial import cKDTree

# Inverting a SIP model for catalog stars far outside the frame may not converge; those stars are
# discarded anyway. Filtered once here, because warnings.catch_warnings is not thread-safe.
warnings.filterwarnings('ignore', message=".*failed to converge to the requested accuracy.*")


def _fit(det_xy, sky, degree, fallback):
    """fit_wcs_from_points, or `fallback` if the points are degenerate (too few, collinear)."""
    try:
        return fit_wcs_from_points(det_xy, sky, proj_point='center', projection='TAN', sip_degree=degree)
    except (ValueError, np.linalg.LinAlgError):
        return fallback


def initial_wcs(result, width, height):
    """Pure TAN WCS reproducing the tetra3rs solution (fitted to a grid of its pixel->sky mappings)."""
    gx, gy = np.meshgrid(np.linspace(-0.45, 0.45, 9) * width, np.linspace(-0.45, 0.45, 7) * height)
    gx, gy = gx.ravel(), gy.ravel()
    ra, dec = result.pixel_to_world(gx, gy)
    ok = np.isfinite(ra) & np.isfinite(dec)
    sky = SkyCoord(ra[ok] * u.deg, dec[ok] * u.deg)
    return fit_wcs_from_points((gx[ok] + width / 2, gy[ok] + height / 2), sky, proj_point='center', projection='TAN')


def _catalog_in_field(db, wcs, width, height, max_stars=1500):
    center = wcs.pixel_to_world(width / 2, height / 2)
    corners = wcs.pixel_to_world(np.array([0, width, 0, width]), np.array([0, 0, height, height]))
    radius = float(np.nanmax(center.separation(corners).deg)) * 1.05
    if not np.isfinite(radius):
        radius = 45.0
    stars = db.cone_search(center.ra.deg, center.dec.deg, min(radius, 89.0))
    stars = sorted(stars, key=lambda s: s.magnitude)[:max_stars]
    ra = np.array([s.ra_deg for s in stars])
    dec = np.array([s.dec_deg for s in stars])
    mag = np.array([s.magnitude for s in stars])
    return ra, dec, mag


def _rms_arcsec(wcs, det, cra, cdec, det_i, cat_i):
    fitted = wcs.pixel_to_world(det[det_i, 0], det[det_i, 1])
    sep_arcsec = fitted.separation(SkyCoord(cra[cat_i] * u.deg, cdec[cat_i] * u.deg)).arcsec
    return float(np.sqrt(np.mean(sep_arcsec ** 2)))


def refine(wcs, stars, db, width, height, sip_degree=3):
    """Return (wcs, info) after iterative catalog matching and a TAN-SIP fit.

    The fit starts in the middle of the frame, where the pinhole solution is already good,
    and grows outwards in steps; each step's fit predicts the next ring well enough to match it.
    """
    cra, cdec, cmag = _catalog_in_field(db, wcs, width, height)
    det = np.column_stack([stars.x, stars.y])
    tree = cKDTree(det)
    diag = float(np.hypot(width, height))
    centre = np.array([width / 2, height / 2])
    det_r = np.hypot(det[:, 0] - centre[0], det[:, 1] - centre[1]) / (diag / 2)
    cat_sky = SkyCoord(cra * u.deg, cdec * u.deg)
    matched = None
    start_wcs = wcs

    # (fraction of the half-diagonal to use, match radius as a fraction of the diagonal)
    steps = [(0.45, 0.010), (0.65, 0.008), (0.85, 0.006), (1.0, 0.005), (1.0, 0.003), (1.0, 0.003)]
    for frac, rad_frac in steps:
        radius = rad_frac * diag
        px, py = wcs.world_to_pixel(cat_sky)
        cat_r = np.hypot(px - centre[0], py - centre[1]) / (diag / 2)
        inside = (np.isfinite(px) & np.isfinite(py) & (px > -5) & (px < width + 5) & (py > -5)
                  & (py < height + 5) & (cat_r <= frac))
        dist, idx = tree.query(np.column_stack([px, py])[inside], distance_upper_bound=radius)
        good = np.isfinite(dist)
        cat_i = np.flatnonzero(inside)[good]
        det_i = idx[good]
        # One catalog star per detection: keep the closest pair.
        order = np.argsort(dist[good])
        _, first = np.unique(det_i[order], return_index=True)
        sel = order[first]
        cat_i, det_i = cat_i[sel], det_i[sel]
        if len(cat_i) < 12:
            continue
        # Polynomial order follows how much of the frame (and how many stars) we have.
        spread = float(det_r[det_i].max()) if len(det_i) else 0
        degree = sip_degree if (len(cat_i) >= 60 and spread > 0.6) else (2 if len(cat_i) >= 25 else None)
        wcs = _fit((det[det_i, 0], det[det_i, 1]), cat_sky[cat_i], degree, wcs)
        matched = (det_i, cat_i)

    if matched is None:
        return start_wcs, {'matched': 0, 'rms_arcsec': None, 'sip_degree': None, 'matches': []}

    # Final passes: in dense Milky Way fields a loose radius picks up chance neighbours, which drag
    # the fit and inflate the error. Tighten to a few times the scatter of the good matches and clip.
    for _ in range(3):
        det_i, cat_i = matched
        px, py = wcs.world_to_pixel(cat_sky[cat_i])
        resid = np.hypot(px - det[det_i, 0], py - det[det_i, 1])
        sigma = 1.4826 * np.nanmedian(resid)                   # robust standard deviation
        if not np.isfinite(sigma):
            break
        radius = float(np.clip(3.0 * sigma, 2.0 * stars.binning, 0.003 * diag))
        px, py = wcs.world_to_pixel(cat_sky)
        inside = np.isfinite(px) & np.isfinite(py) & (px > 0) & (px < width) & (py > 0) & (py < height)
        dist, idx = tree.query(np.column_stack([px, py])[inside], distance_upper_bound=radius)
        good = np.isfinite(dist)
        cat_new, det_new = np.flatnonzero(inside)[good], idx[good]
        order = np.argsort(dist[good])
        _, first = np.unique(det_new[order], return_index=True)
        cat_new, det_new = cat_new[order[first]], det_new[order[first]]
        if len(cat_new) < 12:
            break
        spread = float(det_r[det_new].max())
        degree = sip_degree if (len(cat_new) >= 60 and spread > 0.6) else (2 if len(cat_new) >= 25 else None)
        wcs = _fit((det[det_new, 0], det[det_new, 1]), cat_sky[cat_new], degree, wcs)
        matched = (det_new, cat_new)

    det_i, cat_i = matched
    info = {
        'matched': int(len(det_i)),
        'rms_arcsec': _rms_arcsec(wcs, det, cra, cdec, det_i, cat_i),
        'sip_degree': int(wcs.sip.a_order) if wcs.sip is not None else None,
        'matches': [(float(det[d, 0]), float(det[d, 1]), float(cra[c]), float(cdec[c]), float(cmag[c]))
                    for d, c in zip(det_i, cat_i)],
    }
    return wcs, info
