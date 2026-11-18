"""All-sky map loading, camera WCS construction and reprojection."""
import math
import threading
import time

import numpy as np
from astropy.wcs import WCS
from PIL import Image
from reproject import reproject_interp

from . import settings

Image.MAX_IMAGE_PIXELS = None

_input_data = None   # (3, H, W) uint8
_input_wcs = None


def _set_map(rgb_uint8):
    """Install an all-sky CAR map: (H, W, 3) uint8, RA 0h at the centre, east left, north up."""
    global _input_data, _input_wcs
    h, w = rgb_uint8.shape[:2]
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [(w + 1) / 2, (h + 1) / 2]
    wcs.wcs.cdelt = np.array([-360. / w, -180. / h])
    wcs.wcs.crval = [0, 0]
    wcs.wcs.ctype = ["RA---CAR", "DEC--CAR"]
    _input_wcs = wcs
    _input_data = np.moveaxis(rgb_uint8, -1, 0)


def _render_catalog_map():
    from .starfield import render_allsky
    t0 = time.perf_counter()
    rgb = (render_allsky(4096) * 255).astype(np.uint8)
    _set_map(rgb)
    print(f"Rendered all-sky map from the star catalog in {time.perf_counter() - t0:.1f}s")


def load(path=None, background=True):
    """Load the all-sky map used for sky previews.

    Uses the composite skymap image if present (it may include constellation art);
    otherwise renders a real star map from the bundled HYG catalog.
    """
    path = path or settings.SKYMAP_PATH
    try:
        image = Image.open(path).convert('RGB')
    except FileNotFoundError:
        print(f"No skymap image at '{path}'; rendering one from the star catalog.")
        if background:
            threading.Thread(target=_render_catalog_map, daemon=True).start()
        else:
            _render_catalog_map()
        return True
    except Exception as exc:  # corrupt file etc.
        print(f"Could not load skymap '{path}': {exc}")
        return False
    _set_map(np.asarray(image))
    print(f"Skymap loaded: {path} ({image.width}x{image.height})")
    return True


def is_loaded():
    return _input_data is not None


def build_sensor_wcs(coords, focal_length_mm, pixel_pitch_um, width_px, height_px, rotation_deg=0.0):
    """Gnomonic (TAN) WCS for a camera sensor, as numpy rows (row 0 = top).

    rotation_deg is the position angle of the image's "up" direction measured
    from north through east; at 0 the image is north-up, east-left.
    The TAN plate scale at the centre is exactly pixel_pitch / focal_length rad.
    """
    scale_deg = math.degrees((pixel_pitch_um / 1000.0) / focal_length_mm)
    th = math.radians(rotation_deg)
    w = WCS(naxis=2)
    w.wcs.crpix = [(width_px + 1) / 2, (height_px + 1) / 2]
    # Pixel axis 1 = column (right), axis 2 = row (down in the PNG).
    w.wcs.cd = scale_deg * np.array([[-math.cos(th), -math.sin(th)],
                                     [math.sin(th), -math.cos(th)]])
    w.wcs.crval = [coords.ra.degree, coords.dec.degree]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return w


def preview_wcs(coords, focal_length_mm, pixel_pitch_um, width_px, height_px, rotation_deg=0.0, context=1.0):
    """WCS and size of the preview image for a sensor (downscaled, same field; wider by `context`)."""
    # Shrinking the output by `factor` and growing the pitch by `factor` keeps the field.
    factor = max(1.0, max(width_px, height_px) / settings.SKYMAP_PREVIEW_MAX_PX)
    out_w = max(1, round(width_px / factor))
    out_h = max(1, round(height_px / factor))
    wcs = build_sensor_wcs(coords, focal_length_mm, pixel_pitch_um * factor * context, out_w, out_h, rotation_deg)
    return wcs, out_w, out_h


def render(coords, focal_length_mm, pixel_pitch_um, width_px, height_px, rotation_deg=0.0, context=1.0):
    """Render the sky seen by the sensor as an RGB uint8 array (preview-sized).

    context > 1 widens the field around the sensor by that factor (the sensor
    footprint is then the central 1/context of the image), for framing views.
    """
    if not is_loaded():
        raise RuntimeError('Skymap is not loaded.')
    wcs, out_w, out_h = preview_wcs(coords, focal_length_mm, pixel_pitch_um, width_px, height_px, rotation_deg, context)

    t0 = time.perf_counter()
    data, _ = reproject_interp((_input_data, _input_wcs), wcs, shape_out=(out_h, out_w))
    rgb = np.nan_to_num(np.moveaxis(data, 0, -1)).clip(0, 255).astype(np.uint8)
    print(f"Rendered {out_w}x{out_h} sky preview in {time.perf_counter() - t0:.2f}s")
    return rgb
