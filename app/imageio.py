"""Load astrophotos (JPG/PNG/TIFF, FITS, camera RAW) into float32 arrays.

Every loader returns a LoadedImage with:
  mono    float32 (H, W) luminance, scaled to 0..1, for detection/solving
  preview uint8 (h, w, 3) display image, longest side <= PREVIEW_MAX_PX
  scale   preview pixels per full-resolution pixel
"""
import io
import os
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
PREVIEW_MAX_PX = 2048

RASTER_EXT = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
FITS_EXT = {'.fit', '.fits', '.fts'}
RAW_EXT = {'.cr2', '.cr3', '.nef', '.arw', '.raf', '.orf', '.rw2', '.dng', '.pef'}
SUPPORTED_EXT = RASTER_EXT | FITS_EXT | RAW_EXT


@dataclass
class LoadedImage:
    mono: np.ndarray
    preview: np.ndarray
    scale: float
    meta: dict = field(default_factory=dict)

    @property
    def shape(self):
        return self.mono.shape


def load(data: bytes, filename: str) -> LoadedImage:
    ext = os.path.splitext(filename.lower())[1]
    if ext in FITS_EXT:
        rgb = _load_fits(data)
    elif ext in RAW_EXT:
        rgb = _load_raw(data)
    elif ext in RASTER_EXT:
        rgb = _load_raster(data)
    else:
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXT))}")
    return _finish(rgb)


def _load_raster(data):
    img = Image.open(io.BytesIO(data))
    arr = np.asarray(img)
    if arr.dtype == np.uint8:
        arr = arr.astype(np.float32) / 255.0
    elif arr.dtype == np.uint16:
        arr = arr.astype(np.float32) / 65535.0
    else:
        arr = np.asarray(img.convert('RGB'), dtype=np.float32) / 255.0
    if arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[..., :3]
    return arr


def _load_fits(data):
    from astropy.io import fits
    with fits.open(io.BytesIO(data)) as hdul:
        hdu = next((h for h in hdul if getattr(h, 'data', None) is not None and h.data.ndim >= 2), None)
        if hdu is None:
            raise ValueError('FITS file has no image data.')
        arr = np.asarray(hdu.data, dtype=np.float32)
    if arr.ndim == 3:            # (C, H, W) -> (H, W, C)
        arr = np.moveaxis(arr[:3], 0, -1)
    arr = np.nan_to_num(arr)
    lo, hi = np.percentile(arr, [0.01, 99.99])
    return np.clip((arr - lo) / max(hi - lo, 1e-12), 0, 1)


def _load_raw(data):
    try:
        import rawpy
    except ImportError as exc:
        raise ValueError('RAW files need the rawpy package: pip install rawpy') from exc
    with rawpy.imread(io.BytesIO(data)) as raw:
        rgb = raw.postprocess(half_size=True, no_auto_bright=True, gamma=(1, 1), output_bps=16, use_camera_wb=True)
    return rgb.astype(np.float32) / 65535.0


def _finish(arr):
    mono = arr if arr.ndim == 2 else arr[..., :3].mean(axis=2)
    mono = mono.astype(np.float32)
    rgb = arr if arr.ndim == 3 else np.repeat(arr[..., None], 3, axis=2)
    h, w = mono.shape
    scale = min(1.0, PREVIEW_MAX_PX / max(h, w))
    # Simple display stretch for linear data so faint stars are visible.
    disp = rgb if rgb.max() > 0.2 else np.sqrt(rgb / max(rgb.max(), 1e-6))
    img = Image.fromarray((np.clip(disp, 0, 1) * 255).astype(np.uint8))
    if scale < 1.0:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return LoadedImage(mono=mono, preview=np.asarray(img), scale=scale, meta={'width': w, 'height': h})
