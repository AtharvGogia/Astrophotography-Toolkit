"""Runtime settings, read from environment variables with sensible defaults.

Defaults suit running on your own computer. The Docker image (Cloud Run) sets HOSTED=1 and friends.
"""
import os


def _flag(name, default=False):
    return os.environ.get(name, '1' if default else '0').strip().lower() in ('1', 'true', 'yes', 'on')


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(PROJECT_ROOT, 'static')

SKYMAP_PATH = os.environ.get('SKYMAP_PATH', os.path.join(PROJECT_ROOT, 'composite_skymap_16k.png'))

# Longest side of rendered skymap previews. They are shown at a few hundred
# pixels, so rendering at full sensor resolution only wastes time.
SKYMAP_PREVIEW_MAX_PX = 1600

# Running as a public website rather than on the user's own computer: changes privacy wording.
HOSTED = _flag('HOSTED')

# Solve photos inside the upload request instead of a background thread. Needed on Cloud Run,
# which only gives a container CPU while it is handling a request.
SYNC_JOBS = _flag('SYNC_JOBS')

# Load the catalogs, solver index and sky map before serving, instead of in background threads.
WARMUP_SYNC = _flag('WARMUP_SYNC')

# Uploads larger than this are rejected (megabytes). Cloud Run caps requests at 32 MiB.
MAX_UPLOAD_MB = int(os.environ.get('MAX_UPLOAD_MB', '300'))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# Photo analyses allowed per visitor (IP) per 10 minutes; 0 = no limit.
ANALYZE_PER_10_MIN = int(os.environ.get('ANALYZE_PER_10_MIN', '0'))

# The site's public address (e.g. https://astro.atharvgogia.in), for link previews and the
# canonical URL. Empty: use the address the request came in on.
PUBLIC_URL = os.environ.get('PUBLIC_URL', '').rstrip('/')
