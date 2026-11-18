"""Runtime settings, read from environment variables with sensible defaults."""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(PROJECT_ROOT, 'static')

SKYMAP_PATH = os.environ.get('SKYMAP_PATH', os.path.join(PROJECT_ROOT, 'composite_skymap_16k.png'))

# Longest side of rendered skymap previews. They are shown at a few hundred
# pixels, so rendering at full sensor resolution only wastes time.
SKYMAP_PREVIEW_MAX_PX = 1600

# Uploads larger than this are rejected (bytes).
MAX_UPLOAD_BYTES = int(os.environ.get('MAX_UPLOAD_MB', '200')) * 1024 * 1024

ASTROMETRY_API_URL = 'http://nova.astrometry.net/api'


def load_api_key():
    """Astrometry.net key: ASTROMETRY_API_KEY env var, else config.py in the project root."""
    key = os.environ.get('ASTROMETRY_API_KEY')
    if key:
        return key
    try:
        from config import API_KEY  # gitignored, project root
    except ImportError:
        return None
    return None if API_KEY in (None, '', 'YOUR_API_KEY_HERE') else API_KEY
