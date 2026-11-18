"""Night planner: twilight, rise/transit/set, the Moon. Checked against geometry and known events."""
import datetime as dt

import pytest

from app import create_app, planner

GURUGRAM = (28.45, 77.02)
NOON_IST_18_NOV_2026 = '2026-11-18T06:30:00'      # local noon at UTC+5:30


def _utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)


def test_culmination_altitude_and_direction():
    p = planner.plan(*GURUGRAM, NOON_IST_18_NOV_2026, 83.82, -5.39, 30)   # M 42
    hi = next(e for e in p['target_events'] if e['event'] == 'highest')
    assert hi['alt'] == pytest.approx(90 - (28.45 + 5.39), abs=0.3)     # meridian altitude
    assert hi['direction'] == 'S'
    assert [e['event'] for e in p['target_events']] == ['rise', 'highest', 'set']
    assert p['windows'] and p['windows'][0]['peak_alt'] == pytest.approx(hi['alt'], abs=0.5)


def test_twilight_order_and_sunset_time():
    p = planner.plan(*GURUGRAM, NOON_IST_18_NOV_2026, 83.82, -5.39, 30)
    names = [e['event'] for e in p['sun_events']]
    assert names == ['sun_set', 'civil_set', 'nautical_set', 'astronomical_set',
                     'astronomical_rise', 'nautical_rise', 'civil_rise', 'sun_rise']
    sunset_ist = _utc(p['sun_events'][0]['time']) + dt.timedelta(hours=5, minutes=30)
    # Published sunset for Gurugram on 18 Nov 2026 is about 17:27 IST.
    assert sunset_ist.hour == 17 and 22 <= sunset_ist.minute <= 32


def test_circumpolar_and_never_rising():
    polaris = planner.plan(50.0, 0.0, '2026-01-15T12:00:00', 37.95, 89.26, 20)
    assert polaris['always_up'] and not polaris['never_up']
    assert all(a > 0 for a in polaris['target_alt'])
    southern = planner.plan(50.0, 0.0, '2026-01-15T12:00:00', 90.0, -70.0, 20)
    assert southern['never_up'] and not southern['windows']


def test_midnight_sun_has_no_dark_window():
    p = planner.plan(70.0, 20.0, '2026-06-21T11:00:00', 279.2, 38.8, 20)   # Vega, Arctic summer
    assert not p['windows']
    assert not any(e['event'] == 'sun_set' for e in p['sun_events'])


def test_full_moon_matches_known_date():
    # Full Moon of 25 January 2024 was at 17:54 UTC.
    cycle = planner.moon_cycle('2024-01-20T00:00:00', 10)
    full = next(e for e in cycle['events'] if e['event'] == 'Full Moon')
    assert abs((_utc(full['time']) - dt.datetime(2024, 1, 25, 17, 54, tzinfo=dt.timezone.utc)).total_seconds()) < 3600
    day_of_full = [d for d in cycle['days'] if _utc(d['time']).date() == dt.date(2024, 1, 25)][0]
    assert day_of_full['illumination'] > 0.98


def test_moon_phase_names():
    illum, waxing, name = planner.moon_phase(planner.Time('2024-01-25T17:54:00'))
    assert name == 'Full Moon' and illum > 0.99
    illum, waxing, name = planner.moon_phase(planner.Time('2024-01-18T03:53:00'))   # first quarter
    assert name == 'First Quarter' and waxing


def test_tonight_highlights_are_high_and_dark():
    t = planner.tonight(*GURUGRAM, NOON_IST_18_NOV_2026)
    assert t['dark_kind'] == 'astronomical' and t['dark_start'] < t['dark_end']
    assert t['highlights'] and all(h['best_alt'] >= 25 for h in t['highlights'])
    names = ' '.join(h['name'] for h in t['highlights'])
    assert 'Pleiades' in names or 'Andromeda' in names


def test_planner_api_validates_input():
    client = create_app(load_skymap=False).test_client()
    ok = client.post('/api/plan', json={'lat': 28.45, 'lon': 77.02, 'start': NOON_IST_18_NOV_2026,
                                        'target_name': 'M42', 'min_alt': 30})
    assert ok.status_code == 200 and ok.get_json()['culmination'] == pytest.approx(56.2, abs=0.2)
    for bad in [{'lat': 95, 'lon': 0}, {'lat': 0, 'lon': 'x'}, {'lat': 0, 'lon': 0, 'start': 'nope'},
                {'lat': 0, 'lon': 0, 'min_alt': 'nan'}]:
        payload = {'start': NOON_IST_18_NOV_2026, 'target_name': 'M42', **bad}
        assert client.post('/api/plan', json=payload).status_code == 400
    assert client.get('/api/moon?start=2026-11-18T00:00:00&days=30').status_code == 200
    assert client.get('/api/moon?start=2026-11-18T00:00:00&days=999').status_code == 400
    tonight = client.post('/api/tonight', json={'lat': 28.45, 'lon': 77.02, 'start': NOON_IST_18_NOV_2026})
    assert tonight.status_code == 200 and tonight.get_json()['highlights']


def test_crossing_exactly_on_a_sample_is_counted_once():
    times = planner.Time('2026-01-01T00:00:00') + planner.np.arange(5) * planner.u.min
    events = planner._crossings(times, planner.np.array([-2.0, -1.0, 0.0, 1.0, 2.0]), 0.0)
    assert [d for _, d in events] == ['up']
    assert abs((events[0][0] - times[2]).sec) < 1e-6


@pytest.mark.parametrize('body', [[], 123, 'text'])
def test_apis_reject_non_object_json(body):
    client = create_app(load_skymap=False).test_client()
    for url in ('/api/plan', '/api/tonight', '/api/skymap', '/api/resolve'):
        resp = client.post(url, json=body)
        assert resp.status_code in (400, 404, 503), (url, resp.status_code)
