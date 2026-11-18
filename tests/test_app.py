import io
import os
import time

import numpy as np
import pytest
from PIL import Image

from app import catalogs, create_app, imageio, jobs, skymap
from app.starfield import bv_to_rgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _marker_map():
    """Tiny all-sky CAR map with three markers: red at (RA 10, Dec 20), green 5° north, blue 5° east."""
    w, h = 3600, 1800
    img = np.zeros((h, w, 3), np.uint8)

    def put(ra, dec, ch):
        x = int(round(w / 2 - ra * w / 360)) % w
        y = int(round(h / 2 - dec * h / 180))
        img[y - 6:y + 7, x - 6:x + 7, ch] = 255

    put(10, 20, 0)
    put(10, 25, 1)
    put(15, 20, 2)
    return img


@pytest.fixture(scope='module')
def client():
    app = create_app(load_skymap=False)
    skymap._set_map(_marker_map())
    return app.test_client()


def _centroid(img, ch):
    ys, xs = np.nonzero(img[..., ch] > 128)
    return xs.mean(), ys.mean()


# ---- Pages and security ------------------------------------------------------------

@pytest.mark.parametrize('path', ['/', '/planner', '/exposure', '/framing', '/analyzer'])
def test_pages_render(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert b'Astrophotography Toolkit' in resp.data


def test_home_and_planner_pages(client):
    home = client.get('/')
    assert home.status_code == 200 and b'Tonight' in home.data
    planner = client.get('/planner')
    assert planner.status_code == 200 and b'Night planner' in planner.data


@pytest.mark.parametrize('path', ['/config.py', '/backend.py', '/app/settings.py', '/static/../config.py',
                                  '/Instructions.txt', '/catalog_raw/hyg/hygdata_v41.csv'])
def test_source_and_config_not_served(client, path):
    assert client.get(path).status_code == 404


def test_static_assets_served(client):
    assert client.get('/static/css/site.css').status_code == 200
    assert client.get('/static/data/cameras.json').status_code == 200


# ---- Target search and lookup ---------------------------------------------------------

@pytest.mark.parametrize('query, expected', [
    ('lagoon', 'M 8 · Lagoon Nebula'),
    ('m31', 'M 31 · Andromeda Galaxy'),
    ('vega', 'Vega · α Lyr'),
    ('alpha lyr', 'Vega · α Lyr'),
    ('ngc 7000', 'NGC 7000 · North America Nebula'),
    ('pleia', 'M 45 · Pleiades'),
    ('orion', 'Orion'),
])
def test_target_search_top_hit(client, query, expected):
    data = client.get('/api/targets', query_string={'q': query}).get_json()
    assert data and data[0]['name'] == expected


def test_target_search_has_no_cross_word_matches():
    # 'lag' must not match "Umbrella Galaxy" via 'umbrel-la-g-alaxy'
    names = [t.name for t in catalogs.search('lag', 10)]
    assert names == ['M 8 · Lagoon Nebula']


def test_resolve_offline_from_catalog(client):
    data = client.post('/api/resolve', json={'target_name': 'M31'}).get_json()
    assert data['ra'] == pytest.approx(10.68, abs=0.01)
    assert data['dec'] == pytest.approx(41.27, abs=0.01)


def test_resolve_accepts_suggestion_label(client):
    data = client.post('/api/resolve', json={'target_name': 'M 8 · Lagoon Nebula'}).get_json()
    assert data['dec'] == pytest.approx(-24.38, abs=0.01)


def test_resolve_custom_coordinates(client):
    data = client.post('/api/resolve', json={'ra': 10, 'dec': 20}).get_json()
    assert (data['ra'], data['dec']) == (10.0, 20.0)


# ---- Sky preview geometry ----------------------------------------------------------

def _render(client, **extra):
    payload = dict(ra=10, dec=20, focal_length=50, sensor_width_px=6000, sensor_height_px=4000, pixel_pitch=3.76)
    payload.update(extra)
    resp = client.post('/api/skymap', json=payload)
    assert resp.status_code == 200, resp.get_json()
    return np.asarray(Image.open(io.BytesIO(resp.data)))


def test_preview_is_downscaled(client):
    img = _render(client)
    assert img.shape == (1067, 1600, 3)


def test_preview_is_north_up_east_left(client):
    img = _render(client)
    cx, cy = _centroid(img, 0)
    nx, ny = _centroid(img, 1)
    ex, ey = _centroid(img, 2)
    # Target at the centre. The marker map has 0.1° pixels (≈ 6 preview px), so allow a few px.
    assert abs(cx - 800) < 5 and abs(cy - 533) < 5
    assert ny < cy - 100 and abs(nx - cx) < 5              # north is up
    assert ex < cx - 100 and abs(ey - cy) < 10             # east is left


def test_preview_scale_matches_tan_projection(client):
    img = _render(client)
    _, cy = _centroid(img, 0)
    _, ny = _centroid(img, 1)
    # 5° north at 3.76 µm × 3.75 (downscale) / 50 mm per pixel, gnomonic: tan(5°)·F/pitch
    expected = np.tan(np.radians(5)) * 50 / (3.76e-3 * 3.75)
    assert abs((cy - ny) - expected) < 2


def test_preview_rotation_puts_east_at_top(client):
    img = _render(client, rotation_deg=90)
    cx, cy = _centroid(img, 0)
    ex, ey = _centroid(img, 2)
    nx, ny = _centroid(img, 1)
    assert ey < cy - 100        # east is up
    assert nx > cx + 100        # north is right


def test_preview_context_widens_field(client):
    img = _render(client, context=2)
    cx, cy = _centroid(img, 0)
    _, ny = _centroid(img, 1)
    plain = _render(client)
    _, pcy = _centroid(plain, 0)
    _, pny = _centroid(plain, 1)
    assert (cy - ny) == pytest.approx((pcy - pny) / 2, abs=2)


@pytest.mark.parametrize('bad', [{'focal_length': 0}, {'pixel_pitch': -1}, {'context': 9}, {'sensor_width_px': 'x'}])
def test_preview_rejects_bad_input(client, bad):
    payload = dict(ra=10, dec=20, focal_length=50, sensor_width_px=6000, sensor_height_px=4000, pixel_pitch=3.76)
    payload.update(bad)
    assert client.post('/api/skymap', json=payload).status_code == 400


# ---- Star colours, image loading, jobs ------------------------------------------------

def test_star_colours_follow_bv_index():
    blue, red = bv_to_rgb(np.array([-0.3, 1.8]))
    assert blue[2] > blue[0]     # hot star: more blue than red
    assert red[0] > red[2]       # cool star: more red than blue


def test_imageio_png_and_fits(tmp_path):
    arr = (np.random.default_rng(0).random((300, 400, 3)) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, 'PNG')
    img = imageio.load(buf.getvalue(), 'test.png')
    assert img.mono.shape == (300, 400) and img.mono.dtype == np.float32
    assert 0 <= img.mono.min() and img.mono.max() <= 1

    from astropy.io import fits
    data = np.random.default_rng(1).normal(1000, 50, (120, 160)).astype(np.float32)
    fbuf = io.BytesIO()
    fits.PrimaryHDU(data).writeto(fbuf)
    fimg = imageio.load(fbuf.getvalue(), 'test.fits')
    assert fimg.mono.shape == (120, 160)
    assert 0 <= fimg.mono.min() and fimg.mono.max() <= 1


def test_imageio_rejects_unknown_type():
    with pytest.raises(ValueError):
        imageio.load(b'abc', 'notes.txt')


def test_jobs_run_in_background():
    job = jobs.submit(lambda j, x: (j.update(0.5, 'halfway'), x * 2)[1], 21)
    for _ in range(100):
        if job.state in ('done', 'failed'):
            break
        time.sleep(0.02)
    assert job.state == 'done' and job.result == 42


@pytest.mark.skipif(not os.path.isdir(os.path.join(ROOT, 'Samples')), reason='no local Samples/ folder')
def test_samples_load():
    folder = os.path.join(ROOT, 'Samples')
    files = [f for f in os.listdir(folder) if os.path.splitext(f.lower())[1] in imageio.SUPPORTED_EXT]
    assert files
    for name in files:
        with open(os.path.join(folder, name), 'rb') as f:
            img = imageio.load(f.read(), name)
        assert img.mono.ndim == 2 and max(img.preview.shape[:2]) <= imageio.PREVIEW_MAX_PX


@pytest.mark.parametrize('bad', ['nan', 'inf', '-inf'])
def test_preview_rejects_non_finite_numbers(client, bad):
    payload = dict(ra=10, dec=20, focal_length=bad, sensor_width_px=6000, sensor_height_px=4000, pixel_pitch=3.76)
    assert client.post('/api/skymap', json=payload).status_code == 400


def test_blank_coordinates_fall_back_to_name(client):
    data = client.post('/api/resolve', json={'target_name': 'M31', 'ra': '', 'dec': ''}).get_json()
    assert data['dec'] == pytest.approx(41.27, abs=0.01)


def test_skylines_match_preview_geometry(client):
    payload = dict(ra=83.8, dec=-5.4, focal_length=35, sensor_width_px=6000, sensor_height_px=4000, pixel_pitch=5.93)
    data = client.post('/api/skylines', json=payload).get_json()
    assert (data['width'], data['height']) == (1600, 1067)
    assert any(line['con'] == 'Ori' for line in data['lines'])
    assert client.post('/api/skylines', json={**payload, 'focal_length': 'nan'}).status_code == 400
