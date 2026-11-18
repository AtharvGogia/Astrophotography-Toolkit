"""Render static/img/masthead.jpg: the real sky around Orion, from the bundled HYG catalog.

Covers RA 4h20m to 9h40m-ish (east to the left) and Dec −12° to +16°: Orion, Taurus's
Aldebaran and Hyades, Monoceros, Canis Minor (Procyon) and the winter Milky Way.

Usage:  python scripts/render_masthead.py
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.starfield import render_car  # noqa: E402

W, H = 2400, 520
DEG_PER_PX = 0.054
CENTER_RA, CENTER_DEC = 92.0, 2.5

half_w, half_h = W * DEG_PER_PX / 2, H * DEG_PER_PX / 2
img = render_car(CENTER_RA + half_w, CENTER_RA - half_w, CENTER_DEC + half_h, CENTER_DEC - half_h,
                 W, H, mag_limit=8.0, glow=0.07, gain=1.0)
out = os.path.join(ROOT, 'static', 'img', 'masthead.jpg')
Image.fromarray((img * 255).astype(np.uint8)).save(out, quality=88, optimize=True)
print(f'wrote {out}: RA {CENTER_RA - half_w:.1f}..{CENTER_RA + half_w:.1f}, Dec {CENTER_DEC - half_h:.1f}..{CENTER_DEC + half_h:.1f}')
