"""Render real star fields from the bundled HYG catalog.

Positions, brightness (from visual magnitude) and colour (from the B-V index)
are the real values. The faint Milky Way glow is the smoothed density of the
catalog's own faint stars, so it follows the real galactic band.

Images use plate carrée (CAR): x is RA with east (increasing RA) to the left,
y is Dec with north up, matching the composite skymap convention in skymap.py.
"""
import math

import numpy as np
from scipy.ndimage import gaussian_filter, zoom

from . import catalogs

BACKGROUND = np.array([0x0c, 0x0e, 0x12], dtype=np.float32) / 255.0
SKY_BACKGROUND = np.array([0x13, 0x11, 0x0e], dtype=np.float32) / 255.0      # the site's night, a touch lifted


def bv_to_rgb(bv, saturation=0.55):
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
    return saturation * rgb + (1.0 - saturation)


def render_car(ra_left, ra_right, dec_top, dec_bottom, width, height, mag_limit=8.0, glow=0.10, gain=1.0,
               milky_way=0.0, saturation=0.55, background=None):
    """Render the sky between the given RA/Dec bounds (degrees) as float RGB (H, W, 3) in 0..1.

    ra_left > ra_right (east is left). The span may wrap through 0h, e.g. left=30, right=-90.
    milky_way > 0 adds a coloured model of the galactic glow and the bright emission nebulae
    (see _milky_way); saturation sets how strongly star colours show.
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
    colour = bv_to_rgb(ci, saturation)
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

    if milky_way > 0:
        # The glow is smooth, so compute it at a quarter of the size and scale it up.
        sw, sh = max(8, width // 4), max(4, height // 4)
        small = _milky_way(ra_left, span, dec_top, dec_bottom, sw, sh)
        img += milky_way * zoom(small, (height / sh, width / sw, 1), order=1, grid_mode=True, mode='grid-wrap')[:height, :width]

    img = np.arcsinh(img * 6.0 * gain) / np.arcsinh(6.0)  # gentle stretch, keeps bright stars from clipping hard
    bg = BACKGROUND if background is None else np.asarray(background, np.float32)
    return np.clip(bg + img * (1.0 - bg), 0, 1)


# Bright emission nebulae drawn as soft red-pink glows: (RA, Dec, radius in degrees, strength).
EMISSION = [
    (83.8, -5.4, 1.0, 1.0),      # Orion Nebula
    (85.5, -2.0, 4.0, 0.25),     # Barnard's Loop / Orion's belt region
    (270.9, -24.4, 0.6, 0.9),    # Lagoon
    (275.2, -16.2, 0.4, 0.5),    # Omega
    (274.7, -13.8, 0.4, 0.4),    # Eagle
    (314.7, 44.3, 1.3, 0.6),     # North America
    (324.7, 57.5, 1.6, 0.35),    # IC 1396
    (60.0, 36.4, 1.4, 0.35),     # California
    (98.0, 4.9, 0.7, 0.45),      # Rosette
    (161.3, -59.9, 1.4, 1.0),    # Carina
    (38.2, 61.5, 0.9, 0.3),      # Heart
    (43.0, 60.5, 0.9, 0.3),      # Soul
    (306.0, 40.5, 3.5, 0.25),    # Sadr region
    (262.0, -34.5, 2.0, 0.3),    # Cat's Paw / War and Peace area
    (246.5, -24.5, 2.5, 0.25),   # Rho Ophiuchi
]

_GAL = np.array([[-0.0548755604, -0.8734370902, -0.4838350155],    # ICRS -> galactic rotation
                 [0.4941094279, -0.4448296300, 0.7469822445],
                 [-0.8676661490, -0.1980763734, 0.4559837762]])


def _milky_way(ra_left, span, dec_top, dec_bottom, width, height):
    """A smooth, coloured model of the Milky Way's glow on the CAR grid (float RGB, unstretched).

    Not a photograph: a band along the galactic equator, wider and much brighter towards the
    centre in Sagittarius, warm at the core and cooler along the arms, with a dark dust lane,
    plus the brightest emission nebulae. It makes catalog-drawn previews read as a night sky.
    """
    ra = np.radians(ra_left - (np.arange(width) + 0.5) / width * span)
    dec = np.radians(dec_top - (np.arange(height) + 0.5) / height * (dec_top - dec_bottom))
    cd = np.cos(dec)[:, None]
    v = np.stack([cd * np.cos(ra)[None, :], cd * np.sin(ra)[None, :],
                  np.broadcast_to(np.sin(dec)[:, None], (height, width))], axis=-1)
    g = v @ _GAL.T
    b = np.degrees(np.arcsin(np.clip(g[..., 2], -1, 1)))
    lon = np.degrees(np.arctan2(g[..., 1], g[..., 0]))           # -180..180, 0 at the centre
    core = np.exp(-(lon / 55.0) ** 2)
    width_deg = 6.0 + 7.0 * core
    band = np.exp(-0.5 * (b / width_deg) ** 2) * (0.30 + 0.70 * core)
    bulge = 0.9 * np.exp(-(lon ** 2 + (1.4 * b) ** 2) / (2 * 11.0 ** 2))
    dust = 1.0 - 0.55 * np.exp(-0.5 * (b / 2.0) ** 2) * np.exp(-(lon / 70.0) ** 2)
    light = (band + bulge) * dust
    warm = np.array([1.0, 0.74, 0.42], np.float32)                 # core: old yellow stars
    cool = np.array([0.50, 0.52, 1.0], np.float32)                 # arms: bluer, younger, a little violet
    mix = np.clip(core + bulge, 0, 1)[..., None]
    rgb = light[..., None] * (mix * warm + (1 - mix) * cool) * 0.11

    # Emission nebulae: soft hydrogen-alpha pink.
    ha = np.zeros((height, width), np.float32)
    for nra, ndec, r, k in EMISSION:
        n = np.array([math.cos(math.radians(ndec)) * math.cos(math.radians(nra)),
                      math.cos(math.radians(ndec)) * math.sin(math.radians(nra)), math.sin(math.radians(ndec))])
        sep = np.degrees(np.arccos(np.clip(v @ n, -1, 1)))
        ha += k * np.exp(-0.5 * (sep / r) ** 2)
    rgb += ha[..., None] * np.array([1.0, 0.22, 0.38], np.float32) * 0.2
    return rgb.astype(np.float32)


def render_allsky(width=4096):
    """Full-sky CAR map with RA 0h at the centre (east left), as used by skymap.py."""
    height = width // 2
    return render_car(180.0, -180.0, 90.0, -90.0, width, height, mag_limit=8.0, glow=0.08,
                      milky_way=1.0, saturation=0.8, background=SKY_BACKGROUND)
