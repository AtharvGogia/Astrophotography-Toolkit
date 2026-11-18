"""Plate solver tests: a synthetic star field with a known answer, plus the real samples if present."""
import io
import math
import os
import time

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
from PIL import Image

from app import annotate, catalogs, create_app, solver

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, 'Samples')


def synthetic_field(ra, dec, rotation_deg, width=3000, height=2000, fov_w=30.0, seed=0):
    """Render real catalog stars through a known TAN WCS (north-up at rotation 0, east left)."""
    scale = fov_w / width                                       # degrees per pixel (approx, TAN centre)
    th = math.radians(rotation_deg)
    w = WCS(naxis=2)
    w.wcs.crpix = [(width + 1) / 2, (height + 1) / 2]
    w.wcs.cd = scale * np.array([[-math.cos(th), -math.sin(th)], [math.sin(th), -math.cos(th)]])
    w.wcs.crval = [ra, dec]
    w.wcs.ctype = ['RA---TAN', 'DEC--TAN']

    stars = [s for s in catalogs.load_stars() if s['mag'] <= 7.5]
    sky = SkyCoord([s['ra'] for s in stars] * u.deg, [s['dec'] for s in stars] * u.deg)
    near = sky.separation(SkyCoord(ra * u.deg, dec * u.deg)).deg < fov_w
    px, py = w.world_to_pixel(sky[near])
    mag = np.array([s['mag'] for s in stars])[near]
    img = np.random.default_rng(seed).normal(0.05, 0.004, (height, width)).astype(np.float32)
    yy, xx = np.mgrid[-6:7, -6:7]
    psf = np.exp(-(xx ** 2 + yy ** 2) / (2 * 1.6 ** 2)).astype(np.float32)
    for x, y, m in zip(px, py, mag):
        xi, yi = int(round(x)), int(round(y))
        if 6 <= xi < width - 6 and 6 <= yi < height - 6:
            img[yi - 6:yi + 7, xi - 6:xi + 7] += psf * 0.9 * 10 ** (-0.4 * (m - 2))
    return np.clip(img, 0, 1), w


@pytest.mark.parametrize('ra, dec, rot', [(83.8, -5.4, 0), (310.0, 42.0, 37), (200.0, -60.0, 250)])
def test_synthetic_field_solves_accurately(ra, dec, rot):
    img, truth = synthetic_field(ra, dec, rot)
    sol = solver.solve(img)
    centre = SkyCoord(sol.ra * u.deg, sol.dec * u.deg)
    true_centre = truth.pixel_to_world(img.shape[1] / 2, img.shape[0] / 2)
    assert centre.separation(true_centre).arcmin < 1.0
    assert abs(((sol.rotation - rot) + 180) % 360 - 180) < 0.2
    # The synthetic WCS has 30°/3000 px at the centre; edge to edge a TAN projection spans
    # 2·atan(1500 · 0.01° in radians) = 29.35°.
    expected_fov = 2 * math.degrees(math.atan(1500 * math.radians(30.0 / 3000)))
    assert sol.fov_w == pytest.approx(expected_fov, rel=0.005)
    assert not sol.parity_flipped
    assert sol.rms_arcsec / sol.scale_arcsec < 1.0          # sub-pixel on clean synthetic data


def test_mirrored_field_is_reported_as_flipped():
    img, _ = synthetic_field(83.8, -5.4, 0)
    sol = solver.solve(np.ascontiguousarray(img[:, ::-1]))
    assert sol.parity_flipped


def test_blank_image_fails_cleanly():
    with pytest.raises(solver.SolveError):
        solver.solve(np.random.default_rng(3).normal(0.1, 0.01, (800, 1200)).astype(np.float32))


def test_annotations_label_orion():
    img, _ = synthetic_field(83.8, -5.4, 0)
    labels = annotate.annotate(solver.solve(img))
    names = {s['label'] for s in labels['stars']}
    # Frame is 30° × 20° centred on M 42: Rigel and the belt are in, Betelgeuse (Dec +7.4°) is just out.
    assert {'Rigel', 'Alnilam'} <= names and 'Betelgeuse' not in names
    assert any(d['label'].startswith('M 42') for d in labels['dsos'])
    assert labels['constellations'][0]['name'] == 'Orion'
    assert labels['grid']


def test_analyze_api_round_trip():
    app = create_app(load_skymap=False)
    client = app.test_client()
    img, _ = synthetic_field(83.8, -5.4, 0)
    buf = io.BytesIO()
    Image.fromarray((img * 255).astype(np.uint8)).save(buf, 'PNG')
    resp = client.post('/api/analyze', data={'image': (io.BytesIO(buf.getvalue()), 'orion.png')},
                       content_type='multipart/form-data')
    assert resp.status_code == 202
    job_id = resp.get_json()['job_id']
    for _ in range(300):
        job = client.get(f'/api/jobs/{job_id}').get_json()
        if job['state'] in ('done', 'failed'):
            break
        time.sleep(0.1)
    assert job['state'] == 'done', job['error']
    assert job['result']['solution']['ra'] == pytest.approx(83.8, abs=0.1)
    assert client.get(job['result']['preview']).mimetype == 'image/jpeg'


@pytest.mark.parametrize('bad', [{}, {'image': (io.BytesIO(b'x'), 'notes.txt')}])
def test_analyze_api_rejects_bad_uploads(bad):
    client = create_app(load_skymap=False).test_client()
    assert client.post('/api/analyze', data=bad, content_type='multipart/form-data').status_code == 400


def test_analyze_api_rejects_bad_hint():
    client = create_app(load_skymap=False).test_client()
    data = {'image': (io.BytesIO(b'x'), 'a.png'), 'fov_hint': 'nan'}
    assert client.post('/api/analyze', data=data, content_type='multipart/form-data').status_code == 400


@pytest.mark.skipif(not os.path.exists(os.path.join(SAMPLES, 'lagoon.png')), reason='no local sample')
def test_lagoon_sample():
    from app import imageio
    with open(os.path.join(SAMPLES, 'lagoon.png'), 'rb') as f:
        img = imageio.load(f.read(), 'lagoon.png')
    sol = solver.solve(img.mono)
    m8 = SkyCoord(270.92 * u.deg, -24.38 * u.deg)
    assert SkyCoord(sol.ra * u.deg, sol.dec * u.deg).separation(m8).deg < 1.0
    labels = annotate.annotate(sol)
    assert any(d['label'].startswith('M 8 ') for d in labels['dsos'])


def test_constellation_lines_pass_through_their_stars():
    img, truth = synthetic_field(83.8, -5.4, 0)
    sol = solver.solve(img)
    lines = annotate.annotate(sol)['lines']
    orion = [p for line in lines if line['con'] == 'Ori' for p in line['points']]
    assert orion
    # Rigel is a vertex of Orion's figure, so some line point must land on its pixel position.
    rx, ry = sol.wcs.world_to_pixel(SkyCoord(78.634 * u.deg, -8.202 * u.deg))
    assert min(math.hypot(x - rx, y - ry) for x, y in orion) < 3


def test_constellation_catalog_is_complete():
    abbrs = {abbr for abbr, _ in catalogs.constellation_lines()}
    assert len(abbrs) == 88


def test_overlay_marks_foreground_but_keeps_open_sky():
    img, _ = synthetic_field(83.8, -5.4, 0)
    sol = solver.solve(img)
    h, w = img.shape
    plain = annotate.annotate(sol, img)
    # Clear sky: nothing is marked as foreground.
    assert not plain['foreground']
    assert not any(line.get('fg') for line in plain['lines'])

    # Cover the lower 40% with a starless "hillside" (rough texture, no stars).
    ground = img.copy()
    rng = np.random.default_rng(5)
    ground[int(h * 0.6):] = rng.normal(0.08, 0.02, (h - int(h * 0.6), w)).astype(np.float32)
    covered = annotate.annotate(sol, ground)
    assert covered['foreground']
    sky_pts = np.array([p for line in covered['lines'] if not line.get('fg') for p in line['points']])
    fg_pts = np.array([p for line in covered['lines'] if line.get('fg') for p in line['points']])
    # Open-sky lines stay out of the hillside, and the hillside's lines are kept, marked.
    assert not ((sky_pts[:, 1] > h * 0.75) & (sky_pts[:, 1] < h)).any()
    assert len(fg_pts) and (fg_pts[:, 1] > h * 0.55).all()
    # Nothing is lost: sky and foreground parts together cover the plain drawing.
    n_plain = sum(len(line['points']) for line in plain['lines'])
    assert len(sky_pts) + len(fg_pts) >= n_plain
    top_plain = sum(1 for line in plain['lines'] for x, y in line['points'] if 0 <= y < h * 0.45)
    assert sum(1 for x, y in sky_pts if 0 <= y < h * 0.45) >= 0.9 * top_plain
    for s in covered['stars']:
        assert s.get('fg', False) == (s['y'] > h * 0.75) or h * 0.5 < s['y'] < h * 0.75
