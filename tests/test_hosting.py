"""Hosted-mode behaviour (Cloud Run settings): solve in the request, keep nothing, limits, health check."""
import io

import numpy as np
import pytest
from PIL import Image

from app import create_app, jobs, ratelimit, settings
from tests.test_solver import synthetic_field


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setattr(settings, 'SYNC_JOBS', True)
    monkeypatch.setattr(settings, 'HOSTED', True)
    monkeypatch.setattr(settings, 'ANALYZE_PER_10_MIN', 2)
    monkeypatch.setattr(settings, 'MAX_UPLOAD_MB', 1)
    monkeypatch.setattr(settings, 'MAX_UPLOAD_BYTES', 1024 * 1024)
    ratelimit._hits.clear()
    app = create_app(load_skymap=False)
    return app.test_client()


def _png(img):
    buf = io.BytesIO()
    Image.fromarray((img * 255).astype(np.uint8)).save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def test_sync_mode_returns_result_inline_and_keeps_nothing(hosted):
    img, _ = synthetic_field(83.8, -5.4, 0, width=1500, height=1000)
    resp = hosted.post('/api/analyze', data={'image': (io.BytesIO(_png(img)), 'orion.png')},
                       content_type='multipart/form-data', headers={'X-Forwarded-For': '203.0.113.5'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['job']['state'] == 'done', body['job']['error']
    assert body['job']['result']['preview'].startswith('data:image/jpeg;base64,')
    assert jobs.get(body['job_id']) is None                     # discarded after answering


def test_rate_limit_per_visitor(hosted):
    def bad():                                                  # rejected early, but still counted
        return {'image': (io.BytesIO(b'x'), 'notes.txt')}
    codes = [hosted.post('/api/analyze', data=bad(), content_type='multipart/form-data',
                         headers={'X-Forwarded-For': '198.51.100.7'}).status_code for _ in range(3)]
    assert codes[:2] == [400, 400] and codes[2] == 429
    other = hosted.post('/api/analyze', data=bad(), content_type='multipart/form-data',
                        headers={'X-Forwarded-For': '198.51.100.8'})
    assert other.status_code == 400                             # a different visitor is unaffected


def test_upload_limit_returns_json_413(hosted):
    big = io.BytesIO(b'0' * (2 * 1024 * 1024))
    resp = hosted.post('/api/analyze', data={'image': (big, 'big.png')}, content_type='multipart/form-data',
                       headers={'X-Forwarded-For': '192.0.2.9'})
    assert resp.status_code == 413 and 'MB' in resp.get_json()['error']


def test_hosted_wording_and_health(hosted):
    page = hosted.get('/analyzer').data.decode()
    assert "solved on this site's server" in page and 'nothing is uploaded anywhere' not in page
    assert 'data-max-upload-mb="1"' in page
    assert hosted.get('/healthz').get_json()['ok'] is True
