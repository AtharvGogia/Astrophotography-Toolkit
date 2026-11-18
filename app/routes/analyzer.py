"""Image analyzer API: plate-solve an uploaded photo and label what is in it.

POST /api/analyze            multipart: image (file), optional fov_hint (degrees)
                             -> {job_id}, plus {job} with the finished result when SYNC_JOBS is on
GET  /api/jobs/<id>          state, progress, message, result
GET  /api/jobs/<id>/preview  JPEG preview of the uploaded photo
"""
import base64
import io
import math

from flask import Blueprint, Response, jsonify, request
from PIL import Image

from .. import annotate, imageio, jobs, ratelimit, settings, solver

bp = Blueprint('analyzer', __name__, url_prefix='/api')


def _run(job, data, filename, fov_hint):
    job.update(0.02, 'Reading the photo…')
    img = imageio.load(data, filename)
    buf = io.BytesIO()
    Image.fromarray(img.preview).save(buf, 'JPEG', quality=88)
    job.files['preview'] = (buf.getvalue(), 'image/jpeg')

    solution = solver.solve(img.mono, fov_hint=fov_hint, progress=job.update)
    job.update(0.9, 'Labelling stars and objects…')
    labels = annotate.annotate(solution, img.mono)
    if settings.SYNC_JOBS:
        # Stateless hosting: send the preview inline so no second request has to reach this instance.
        preview = 'data:image/jpeg;base64,' + base64.b64encode(job.files['preview'][0]).decode('ascii')
    else:
        preview = f'/api/jobs/{job.id}/preview'
    return {'solution': solution.to_dict(), 'annotations': labels, 'preview': preview, 'filename': filename}


@bp.post('/analyze')
def analyze():
    if not ratelimit.allow(('analyze', ratelimit.client_ip()), settings.ANALYZE_PER_10_MIN):
        return jsonify({'error': 'Too many photos in a short time. Please wait a few minutes and try again.'}), 429
    file = request.files.get('image')
    if file is None or not file.filename:
        return jsonify({'error': 'No photo in the request.'}), 400
    ext = ('.' + file.filename.rsplit('.', 1)[-1].lower()) if '.' in file.filename else ''
    if ext not in imageio.SUPPORTED_EXT:
        return jsonify({'error': f"Unsupported file type '{ext or file.filename}'."}), 400
    fov_hint = None
    raw_hint = request.form.get('fov_hint', '').strip()
    if raw_hint:
        try:
            fov_hint = float(raw_hint)
        except ValueError:
            return jsonify({'error': 'fov_hint must be a number of degrees.'}), 400
        if not math.isfinite(fov_hint) or not 0.1 <= fov_hint <= 180:
            return jsonify({'error': 'fov_hint must be between 0.1 and 180 degrees.'}), 400
    data = file.read()
    job = jobs.submit(_run, data, file.filename, fov_hint, sync=settings.SYNC_JOBS)
    if settings.SYNC_JOBS:
        body = {'job_id': job.id, 'job': job.to_dict()}
        jobs.discard(job.id)          # nothing about the photo is kept once the answer is sent
        return jsonify(body), 200
    return jsonify({'job_id': job.id}), 202


@bp.get('/jobs/<job_id>')
def job_status(job_id):
    job = jobs.get(job_id)
    if job is None:
        return jsonify({'error': 'Unknown or expired job.'}), 404
    return jsonify(job.to_dict())


@bp.get('/jobs/<job_id>/preview')
def job_preview(job_id):
    job = jobs.get(job_id)
    if job is None or 'preview' not in job.files:
        return jsonify({'error': 'No preview for this job.'}), 404
    body, mimetype = job.files['preview']
    return Response(body, mimetype=mimetype, headers={'Cache-Control': 'private, max-age=3600'})
