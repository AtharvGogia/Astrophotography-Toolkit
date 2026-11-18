"""Build the slow-to-make data files ahead of time (used by the Dockerfile).

- the plate-solving index (app/solver/cache/, ~30 MB, from tetra3rs's bundled Gaia catalog)
- an all-sky star map rendered from the HYG catalog, for the Exposure/Framing previews

Usage:  python scripts/prebuild.py [skymap_output_path]
"""
import os
import sys
import time

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.solver import index  # noqa: E402
from app.starfield import render_allsky  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'data', 'skymap.png')

t0 = time.perf_counter()
index.get()
print(f'Solver index ready ({index.index_path()}) in {time.perf_counter() - t0:.1f}s')

t0 = time.perf_counter()
os.makedirs(os.path.dirname(out), exist_ok=True)
Image.fromarray((render_allsky(4096) * 255).astype(np.uint8)).save(out, optimize=True)
print(f'Sky map written to {out} ({os.path.getsize(out) / 1e6:.1f} MB) in {time.perf_counter() - t0:.1f}s')
