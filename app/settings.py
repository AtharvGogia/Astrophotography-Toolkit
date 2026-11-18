"""Runtime settings, read from environment variables with sensible defaults."""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(PROJECT_ROOT, 'static')

SKYMAP_PATH = os.environ.get('SKYMAP_PATH', os.path.join(PROJECT_ROOT, 'composite_skymap_16k.png'))

# Longest side of rendered skymap previews. They are shown at a few hundred
# pixels, so rendering at full sensor resolution only wastes time.
SKYMAP_PREVIEW_MAX_PX = 1600

# Uploads larger than this are rejected (bytes).
MAX_UPLOAD_BYTES = int(os.environ.get('MAX_UPLOAD_MB', '300')) * 1024 * 1024
