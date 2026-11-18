"""Image analyzer API.

For now this proxies nova.astrometry.net. Phase 2 replaces it with the local
solver; the astrometry.net path is kept until then as a reference.
"""
import json

import requests
from flask import Blueprint, jsonify, request

from .. import jobs, settings

bp = Blueprint('analyzer', __name__, url_prefix='/api')

_session_key = None
_TIMEOUT = 60


def _astrometry_session():
    global _session_key
    if _session_key:
        return _session_key
    key = settings.load_api_key()
    if not key:
        raise RuntimeError('Astrometry.net API key not configured (set ASTROMETRY_API_KEY or config.py).')
    resp = requests.post(f'{settings.ASTROMETRY_API_URL}/login',
                         data={'request-json': json.dumps({'apikey': key})}, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get('status') != 'success':
        raise RuntimeError(f"Astrometry.net login failed: {data.get('errormessage')}")
    _session_key = data['session']
    return _session_key


@bp.post('/upload')
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image file in request.'}), 400
    try:
        session = _astrometry_session()
        file = request.files['image']
        resp = requests.post(f'{settings.ASTROMETRY_API_URL}/upload',
                             data={'request-json': json.dumps({'session': session, 'publicly_visible': 'n'})},
                             files={'file': (file.filename, file.read(), file.mimetype)}, timeout=300)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
    if data.get('status') != 'success':
        return jsonify({'error': data.get('errormessage', 'Upload failed')}), 500
    return jsonify({'sub_id': data['subid']})


@bp.get('/status/<int:sub_id>')
def get_status(sub_id):
    try:
        resp = requests.get(f'{settings.ASTROMETRY_API_URL}/submissions/{sub_id}', timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        job_id, status, annotated_url = None, 'pending', None
        if data.get('jobs') and data['jobs'][0] is not None:
            job_id = data['jobs'][0]
            info = requests.get(f'{settings.ASTROMETRY_API_URL}/jobs/{job_id}/info', timeout=_TIMEOUT)
            info.raise_for_status()
            status = info.json().get('status', 'unknown')
            if status == 'success':
                annotated_url = f'https://nova.astrometry.net/annotated_display/{job_id}'
        return jsonify({'status': status, 'job_id': job_id, 'annotated_image_url': annotated_url})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@bp.get('/results/<int:job_id>')
def get_results(job_id):
    try:
        resp = requests.get(f'{settings.ASTROMETRY_API_URL}/jobs/{job_id}/annotations', timeout=_TIMEOUT)
        resp.raise_for_status()
        return jsonify({'annotations': resp.json().get('annotations', [])})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@bp.get('/jobs/<job_id>')
def job_status(job_id):
    job = jobs.get(job_id)
    if job is None:
        return jsonify({'error': 'Unknown job.'}), 404
    return jsonify(job.to_dict())
