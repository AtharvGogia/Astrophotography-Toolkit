"""Star detection with sep (Source Extractor as a library).

Large astrophotos are binned down before detection: stars stay easy to find,
nebulosity is smoothed out, and sep runs in well under a second. Positions are
mapped back to full-resolution pixels.
"""
from dataclasses import dataclass

import numpy as np
import sep

sep.set_extract_pixstack(2_000_000)
sep.set_sub_object_limit(4096)


@dataclass
class Stars:
    """Detected stars in full-resolution pixel coordinates (0-based, x right, y down), brightest first."""
    x: np.ndarray
    y: np.ndarray
    flux: np.ndarray
    fwhm: np.ndarray        # full width at half maximum, full-res pixels (approximate, from sep's a/b)
    elongation: np.ndarray  # a / b (1 = round)
    theta: np.ndarray       # position angle of the major axis, radians
    binning: int

    def __len__(self):
        return len(self.x)

    def centered(self, width, height, n=None):
        """(N, 3) array of x, y relative to the image centre plus flux, as tetra3rs expects."""
        s = slice(None, n)
        return np.column_stack([self.x[s] - width / 2, self.y[s] - height / 2, self.flux[s]])


def _bin(data, k):
    if k == 1:
        return np.ascontiguousarray(data, dtype=np.float32)
    h, w = data.shape
    h2, w2 = h // k * k, w // k * k
    return np.ascontiguousarray(data[:h2, :w2].reshape(h2 // k, k, w2 // k, k).mean(axis=(1, 3)), dtype=np.float32)


def detect(mono, target_px=2000, threshold=6.0, max_stars=600):
    """Find stars in a 2D float image. target_px is the long side after binning."""
    h, w = mono.shape
    k = max(1, int(np.ceil(max(h, w) / target_px)))
    data = _bin(mono, k)

    bkg = sep.Background(data, bw=32, bh=32, fw=3, fh=3)
    sub = data - bkg
    objs = sep.extract(sub, threshold, err=bkg.globalrms, minarea=3, deblend_cont=1.0, clean=False)
    if len(objs) == 0:
        return Stars(*(np.zeros(0) for _ in range(6)), binning=k)

    # Keep compact, roughly round blobs that don't touch the edge: drops nebula knots,
    # satellite trails and stars cut off by the frame.
    a, b = objs['a'], np.maximum(objs['b'], 1e-6)
    keep = ((objs['flag'] & 0x04) == 0) & (b / np.maximum(a, 1e-6) > 0.5) & (objs['npix'] < 400)
    objs, a, b = objs[keep], a[keep], b[keep]
    order = np.argsort(-objs['flux'])[:max_stars]
    objs, a, b = objs[order], a[order], b[order]

    return Stars(
        x=(objs['x'] + 0.5) * k - 0.5,
        y=(objs['y'] + 0.5) * k - 0.5,
        flux=objs['flux'].astype(np.float64),
        fwhm=2.0 * np.sqrt(np.log(2) * (a ** 2 + b ** 2)) * k,
        elongation=a / b,
        theta=objs['theta'].astype(np.float64),
        binning=k,
    )
