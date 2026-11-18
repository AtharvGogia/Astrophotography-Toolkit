"""Exposure/framing API: target lookup and sky previews."""
import io
import math
import traceback

from flask import Blueprint, jsonify, request, send_file
from PIL import Image

from .. import annotate, catalogs, skymap
from ..coords import get_target_coords

bp = Blueprint('calculator', __name__, url_prefix='/api')


@bp.get('/targets')
def search_targets():
    """Suggestions for the target box: ?q=lagoon -> [{name, kind, ra, dec, constellation, mag}]."""
    q = request.args.get('q', '')[:60]
    try:
        limit = max(1, min(int(request.args.get('limit', 8)), 20))
    except ValueError:
        limit = 8
    return jsonify([t.to_dict() for t in catalogs.search(q, limit)])


@bp.post('/resolve')
@bp.post('/get_declination')   # original name, kept for compatibility
def resolve_target():
    data = request.get_json(silent=True) or {}
    try:
        coords = get_target_coords(data)
    except Exception as exc:
        return jsonify({'error': f'Could not find coordinates. {exc}'}), 404
    return jsonify({'ra': coords.ra.degree, 'dec': coords.dec.degree, 'declination': coords.dec.degree})


def _camera_request():
    """Parse and validate the camera/target payload shared by the sky-preview endpoints.

    Returns (params, None) or (None, error_response).
    """
    data = request.get_json(silent=True) or {}
    try:
        focal = float(data['focal_length'])
        width = int(data['sensor_width_px'])
        height = int(data['sensor_height_px'])
        pitch = float(data['pixel_pitch'])
        rotation = float(data.get('rotation_deg') or 0.0)
        context = float(data.get('context') or 1.0)
    except (KeyError, TypeError, ValueError):
        return None, (jsonify({'error': 'Missing or invalid camera parameters.'}), 400)
    if not all(math.isfinite(v) for v in (focal, pitch, rotation, context))             or min(focal, width, height, pitch) <= 0 or not 1.0 <= context <= 4.0             or max(width, height) > 100_000:
        return None, (jsonify({'error': 'Camera parameters must be positive; context must be 1-4.'}), 400)
    try:
        coords = get_target_coords(data)
    except Exception as exc:
        return None, (jsonify({'error': f'Could not find coordinates. {exc}'}), 404)
    return (coords, focal, pitch, width, height, rotation, context), None


@bp.post('/skymap')
@bp.post('/get_skymap_crop')   # original name, kept for compatibility
def skymap_crop():
    if not skymap.is_loaded():
        return jsonify({'error': 'The sky map is still being prepared. Try again in a few seconds.'}), 503
    params, error = _camera_request()
    if error:
        return error
    try:
        rgb = skymap.render(*params)
    except Exception:
        traceback.print_exc()
        return jsonify({'error': 'Sky preview failed. Check the server log.'}), 500

    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, 'PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@bp.post('/skylines')
def sky_lines():
    """Constellation figures in the pixel coordinates of the matching /api/skymap image."""
    params, error = _camera_request()
    if error:
        return error
    wcs, out_w, out_h = skymap.preview_wcs(*params)
    return jsonify({'width': out_w, 'height': out_h,
                    'lines': annotate.constellation_lines(wcs, out_w, out_h)})
