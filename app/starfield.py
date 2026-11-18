"""Render real star fields from the bundled HYG catalog.

Positions, brightness (from visual magnitude) and colour (from the B-V index)
are the real values. The faint Milky Way glow is the smoothed density of the
catalog's own faint stars, so it follows the real galactic band.

Images use plate carrée (CAR): x is RA with east (increasing RA) to the left,
y is Dec with north up, matching the composite skymap convention in skymap.py.
"""
import numpy as np
from scipy.ndimage import gaussian_filter

from . import catalogs

BACKGROUND = np.array([0x0c, 0x0e, 0x12], dtype=np.float32) / 255.0


def bv_to_rgb(bv):
    """Approximate star colour for a B-V index (Ballesteros temperature, then a blackbody fit)."""
    bv = np.clip(np.nan_to_num(bv, nan=0.65), -0.4, 2.0)
    t = 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))
    t100 = t / 100.0
    r = np.where(t100 <= 66, 255.0, 329.698727446 * np.power(np.maximum(t100 - 60, 1e-6), -0.1332047592))
    g = np.where(t100 <= 66, 99.4708025861 * np.log(t100) - 161.1195681661,
                 288.1221695283 * np.power(np.maximum(t100 - 60, 1e-6), -0.0755148492))
    b = np.where(t100 >= 66, 255.0, np.where(t100 <= 19, 0.0, 138.5177312231 * np.log(np.maximum(t100 - 10, 1e-6)) - 305.0447927307))
    rgb = np.clip(np.stack([r, g, b], axis=-1), 0, 255) / 255.0
    # Desaturate: real stars look much whiter than their blackbody colour to the eye and camera.
    return 0.55 * rgb + 0.45


def render_car(ra_left, ra_right, dec_top, dec_bottom, width, height, mag_limit=8.0, glow=0.10, gain=1.0):
    """Render the sky between the given RA/Dec bounds (degrees) as float RGB (H, W, 3) in 0..1.

    ra_left > ra_right (east is left). The span may wrap through 0h, e.g. left=30, right=-90.
    """
    stars = catalogs.load_stars()
    ra = np.array([s['ra'] for s in stars])
    dec = np.array([s['dec'] for s in stars])
    mag = np.array([s['mag'] for s in stars])
    ci = np.array([np.nan if s['ci'] is None else s['ci'] for s in stars])

    span = ra_left - ra_right
    dra = (ra_left - ra) % 360.0                      # degrees west of the left edge
    x = dra / span * width
    y = (dec_top - dec) / (dec_top - dec_bottom) * height
    keep = (dra <= span) & (y >= -2) & (y < height + 2) & (mag <= mag_limit)
    x, y, mag, ci = x[keep], y[keep], mag[keep], ci[keep]

    # Photographic response: brightness grows more slowly than true flux, so faint stars stay
    # visible next to bright ones (like a stretched astrophoto). mag 1 -> 1.0, mag 6 -> ~0.06.
    flux = np.power(10.0, -0.4 * (mag - 1.0)) ** 0.6
    colour = bv_to_rgb(ci)
    px_per_deg = width / span

    img = np.zeros((height, width, 3), np.float32)
    # Brighter stars get wider images, as they do in a real photo. Render in a few size bands.
    for lo, hi, sigma in ((-2, 1.5, 2.6), (1.5, 3.0, 1.7), (3.0, 4.5, 1.15), (4.5, 6.0, 0.85), (6.0, 99, 0.65)):
        sel = (mag >= lo) & (mag < hi)
        if not sel.any():
            continue
        layer = np.zeros_like(img)
        xi = np.clip(np.round(x[sel]).astype(int), 0, width - 1)
        yi = np.clip(np.round(y[sel]).astype(int), 0, height - 1)
        np.add.at(layer, (yi, xi), (flux[sel][:, None] * colour[sel]).astype(np.float32))
        s = sigma * max(1.0, px_per_deg / 20.0) ** 0.5
        # Normalise so a star's peak brightness (not its total light) follows `flux`.
        img += gaussian_filter(layer, (s, s, 0)) * (2 * np.pi * s * s)

    if glow > 0:
        faint = (mag > 6.0)
        dens = np.zeros((height, width), np.float32)
        np.add.at(dens, (np.clip(np.round(y[faint]).astype(int), 0, height - 1),
                         np.clip(np.round(x[faint]).astype(int), 0, width - 1)), 1.0)
        # Smooth over ~4° so it shows the broad galactic band, not counting noise.
        dens = gaussian_filter(dens, max(6.0, px_per_deg * 4.0), mode='wrap')
        if dens.max() > 0:
            dens = np.clip(dens / np.percentile(dens, 99.8) - 0.3, 0, None) ** 1.5
        img += glow * dens[..., None] * np.array([1.0, 0.92, 0.80], np.float32)

    img = np.arcsinh(img * 6.0 * gain) / np.arcsinh(6.0)  # gentle stretch, keeps bright stars from clipping hard
    return np.clip(BACKGROUND + img * (1.0 - BACKGROUND), 0, 1)


def render_allsky(width=4096):
    """Full-sky CAR map with RA 0h at the centre (east left), as used by skymap.py."""
    height = width // 2
    return render_car(180.0, -180.0, 90.0, -90.0, width, height, mag_limit=8.0, glow=0.08)
