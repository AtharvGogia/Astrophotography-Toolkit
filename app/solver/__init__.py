"""Local plate solver: star detection (sep) + pattern matching (tetra3rs) + SIP refinement.

    result = solver.solve(mono_image)              # lost in space
    result = solver.solve(mono_image, fov_hint=25)  # faster with a rough field of view
"""
import math
import time
from dataclasses import dataclass, field

import numpy as np
import tetra3rs

from . import detect as _detect
from . import index, refine as _refine

# Detection is tried at a few binning levels: different photos (star size, nebulosity,
# noise) solve best at different scales, and each attempt takes well under a second.
DETECT_SIZES = (2000, 1400, 1000, 2800)
BLIND_FOV_GUESSES = (20, 40, 60, 80)


class SolveError(Exception):
    pass


@dataclass
class Solution:
    wcs: object                 # astropy WCS (TAN-SIP), full-resolution 0-based pixels
    width: int
    height: int
    ra: float                   # field centre, degrees
    dec: float
    fov_w: float                # degrees
    fov_h: float
    rotation: float             # position angle of the image's up direction, east of north, degrees
    scale_arcsec: float         # arcseconds per pixel at the centre
    parity_flipped: bool
    matched: int
    rms_arcsec: float
    seconds: float
    stars: object = field(repr=False, default=None)
    matches: list = field(repr=False, default_factory=list)

    def to_dict(self):
        return {
            'ra': self.ra, 'dec': self.dec, 'fov_w': self.fov_w, 'fov_h': self.fov_h,
            'rotation': self.rotation, 'scale_arcsec': self.scale_arcsec,
            'parity_flipped': self.parity_flipped, 'matched': self.matched,
            'rms_arcsec': self.rms_arcsec, 'seconds': self.seconds,
            'width': self.width, 'height': self.height,
            'stars_detected': len(self.stars) if self.stars is not None else 0,
        }


# Allowed range of the fitted pixel scale relative to the plain gnomonic projection, anywhere
# in the frame. Real camera lenses stay well inside this.
MIN_WARP, MAX_WARP = 0.8, 1.2


def _warp(wcs, width, height):
    """Smallest and largest local pixel scale of a TAN-SIP fit relative to its plain TAN part."""
    if wcs.sip is None:
        return 1.0, 1.0
    gx, gy = np.meshgrid(np.linspace(0, width, 25), np.linspace(0, height, 15))
    gx, gy = gx.ravel(), gy.ravel()
    tan = wcs.deepcopy()
    tan.sip = None
    ratios = []
    for dx, dy in ((1, 0), (0, 1)):
        fit = wcs.pixel_to_world(gx, gy).separation(wcs.pixel_to_world(gx + dx, gy + dy)).deg
        plain = tan.pixel_to_world(gx, gy).separation(tan.pixel_to_world(gx + dx, gy + dy)).deg
        ratios.append(fit / plain)
    r = np.concatenate(ratios)
    r = r[np.isfinite(r)]
    return (float(r.min()), float(r.max())) if len(r) else (0.0, np.inf)


def _measure(wcs, width, height):
    cx, cy = width / 2, height / 2
    c = wcs.pixel_to_world(cx, cy)
    up = wcs.pixel_to_world(cx, cy - 10)          # 10 px towards the top of the image
    right = wcs.pixel_to_world(cx + 10, cy)
    rotation = c.position_angle(up).deg % 360
    pa_right = c.position_angle(right).deg
    # For a normal (non-mirrored) image, "right" is 90° clockwise from "up" on the sky, i.e. PA(up) - 90.
    flipped = abs(((pa_right - (rotation - 90)) + 180) % 360 - 180) > 90
    scale = c.separation(right).arcsec / 10
    left, rgt = wcs.pixel_to_world(0, cy), wcs.pixel_to_world(width, cy)
    top, bot = wcs.pixel_to_world(cx, 0), wcs.pixel_to_world(cx, height)
    return (float(c.ra.deg), float(c.dec.deg), float(left.separation(rgt).deg), float(top.separation(bot).deg),
            float(rotation), float(scale), bool(flipped))


def solve(mono, fov_hint=None, progress=None, timeout_s=30):
    """Plate-solve a 2D float image. Raises SolveError if no solution is found."""
    t0 = time.perf_counter()
    report = progress or (lambda frac, msg: None)
    h, w = mono.shape
    report(0.05, 'Loading the star index…')
    db = index.get()

    guesses = [(g, g * 0.5) for g in BLIND_FOV_GUESSES]
    if fov_hint and fov_hint > 0:
        # Try the hint first (fast), then fall back to a blind search in case the photo was cropped.
        guesses.insert(0, (float(fov_hint), max(2.0, fov_hint * 0.25)))

    result, stars = None, None
    for i, size in enumerate(DETECT_SIZES):
        report(0.1 + 0.5 * i / len(DETECT_SIZES), 'Finding stars…' if i == 0 else 'Trying again at a different scale…')
        stars = _detect.detect(mono, target_px=size)
        if len(stars) < 8:
            continue
        cents = stars.centered(w, h, n=200)
        for fov, err in guesses:
            if time.perf_counter() - t0 > timeout_s:
                break
            r = db.solve_from_centroids(cents, fov_estimate_deg=fov, fov_max_error_deg=err,
                                        image_width=w, image_height=h, solve_timeout_ms=3000)
            if isinstance(r, tetra3rs.SolveResult):
                result = r
                break
        if result is not None or time.perf_counter() - t0 > timeout_s:
            break

    if result is None:
        found = len(stars) if stars is not None else 0
        raise SolveError(
            f'Could not match the star pattern ({found} stars found). This solver handles fields of view '
            f'from about {index.MIN_FOV_DEG:g}° to {index.MAX_FOV_DEG:g}° (camera lenses, not telescopes); '
            'very processed or starless images may not solve either.')

    report(0.7, 'Pattern matched. Fitting lens distortion…')
    base = _refine.initial_wcs(result, w, h)
    # Very wide lenses distort more than a cubic can follow at the corners.
    # A fit that bends the pixel scale far more than any real lens is chasing too few stars
    # (often because foreground covers part of the frame); step down to a gentler polynomial.
    first = 4 if result.fov_deg > 45 else 3
    for degree in range(first, 1, -1):
        wcs, info = _refine.refine(base, stars, db, w, h, sip_degree=degree)
        lo, hi = _warp(wcs, w, h)
        if info['rms_arcsec'] is None or (lo >= MIN_WARP and hi <= MAX_WARP):
            break
    else:
        wcs, info = base, {'matched': None, 'rms_arcsec': None, 'matches': []}
    rms = info['rms_arcsec']
    if rms is None or not math.isfinite(rms) or rms > max(float(result.rmse_arcsec), 1.0) * 1.5:
        # Refinement made things worse (sparse or odd image): keep the pinhole solution.
        wcs, info = base, {'matched': int(result.num_matches), 'rms_arcsec': float(result.rmse_arcsec), 'matches': []}
    ra, dec, fov_w, fov_h, rot, scale, flipped = _measure(wcs, w, h)
    rms = info['rms_arcsec'] if info['rms_arcsec'] is not None else float(result.rmse_arcsec)
    return Solution(wcs=wcs, width=w, height=h, ra=ra, dec=dec, fov_w=fov_w, fov_h=fov_h, rotation=rot,
                    scale_arcsec=scale, parity_flipped=flipped, matched=info['matched'] or int(result.num_matches),
                    rms_arcsec=float(rms), seconds=time.perf_counter() - t0, stars=stars,
                    matches=info.get('matches', []))
