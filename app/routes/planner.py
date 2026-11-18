"""Planner API: target visibility through the night, tonight's summary, and the Moon's cycle."""
import math

from astropy.time import Time
from flask import Blueprint, jsonify, request

from .. import planner
from ..coords import get_target_coords

bp = Blueprint('planner', __name__, url_prefix='/api')


def _num(data, key, lo, hi, default=None):
    v = data.get(key, default)
    if v is None or v == '':
        raise ValueError(f'{key} is required.')
    v = float(v)
    if not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError(f'{key} must be between {lo} and {hi}.')
    return v


def _start(value):
    """ISO time of the night's start (local noon, sent by the browser in UTC)."""
    if not value:
        raise ValueError('start is required.')
    t = Time(str(value).replace('Z', ''), format='isot', scale='utc')
    if not 1900 <= t.datetime.year <= 2100:
        raise ValueError('Date must be between 1900 and 2100.')
    return t.isot


@bp.post('/plan')
def plan():
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    try:
        lat = _num(data, 'lat', -90, 90)
        lon = _num(data, 'lon', -180, 180)
        min_alt = _num(data, 'min_alt', -10, 80, default=30)
        start = _start(data.get('start'))
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    try:
        coords = get_target_coords(data)
    except Exception as exc:
        return jsonify({'error': f'Could not find the target. {exc}'}), 404
    return jsonify(planner.plan(lat, lon, start, coords.ra.deg, coords.dec.deg, min_alt))


@bp.post('/tonight')
def tonight():
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    try:
        lat = _num(data, 'lat', -90, 90)
        lon = _num(data, 'lon', -180, 180)
        start = _start(data.get('start'))
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(planner.tonight(round(lat, 2), round(lon, 2), start))


@bp.get('/moon')
def moon():
    try:
        start = _start(request.args.get('start'))
        days = int(_num(request.args, 'days', 1, 60, default=30))
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(planner.moon_cycle(start, days))
