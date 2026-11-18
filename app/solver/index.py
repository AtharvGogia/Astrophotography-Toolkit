"""The star-pattern index used for plate solving.

Built with tetra3rs from its bundled Gaia DR3 catalog (gaia-catalog package) and
cached on disk the first time it is needed (a few seconds, ~30 MB, not committed).
"""
import os
import threading
import time
from importlib import metadata

import tetra3rs

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')

# Field-of-view band the index covers. Wide-field camera lenses: about 14 mm to 135 mm
# on full frame. Narrower (telescope) fields need a much larger index; see README.
MIN_FOV_DEG = 10.0
MAX_FOV_DEG = 90.0

_db = None
_lock = threading.Lock()


def index_path():
    # The on-disk format can change between tetra3rs releases, so the version is part of the name.
    try:
        ver = metadata.version('tetra3rs')
    except metadata.PackageNotFoundError:
        ver = 'unknown'
    return os.path.join(CACHE_DIR, f'wide_{MIN_FOV_DEG:g}-{MAX_FOV_DEG:g}_tetra3rs-{ver}.bin')


def get():
    """The solver database, loading or building it on first use. Thread-safe."""
    global _db
    with _lock:
        if _db is not None:
            return _db
        path = index_path()
        if os.path.exists(path):
            try:
                _db = tetra3rs.SolverDatabase.load_from_file(path)
                return _db
            except (OSError, ValueError) as exc:
                print(f'Solver index at {path} is unreadable ({exc}); rebuilding.')
        t0 = time.perf_counter()
        print('Building the plate-solving index (one-time, a few seconds)…')
        db = tetra3rs.SolverDatabase.generate_from_gaia(max_fov_deg=MAX_FOV_DEG, min_fov_deg=MIN_FOV_DEG)
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = path + '.tmp'
        db.save_to_file(tmp)
        os.replace(tmp, path)
        print(f'Solver index built in {time.perf_counter() - t0:.1f}s: {db.num_stars} stars, {db.num_patterns} patterns.')
        _db = db
        return _db
