"""Place search for the location box: GeoNames cities and towns with 5,000+ people, offline.

"tucson" -> Tucson, Arizona, United States. A comma narrows by region or country:
"paris, france", "paris, tx". Places whose name starts with the query come first, then places
with a word that does; within each, bigger places first, and an exact name counts as ten times
its size, so a small town called exactly what you typed still beats a mid-sized near-match.
"""
import bisect
import csv
import gzip
import os
import re
import threading
import unicodedata

from . import DATA_DIR

_lock = threading.Lock()
_index = None

# Common short forms people type for countries.
COUNTRY_ALIASES = {'usa': 'unitedstates', 'america': 'unitedstates', 'uk': 'unitedkingdom',
                   'england': 'unitedkingdom', 'britain': 'unitedkingdom', 'uae': 'unitedarabemirates'}


def _fold(text):
    """Accents folded, lowercase, letters and digits only: 'São Paulo' -> 'saopaulo'."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]', '', text)


class Place:
    __slots__ = ('name', 'region', 'country', 'lat', 'lon', 'pop', 'tz', 'keys', 'where')

    def to_dict(self):
        label = ', '.join(x for x in (self.name, self.region, self.country) if x)
        return {'name': self.name, 'region': self.region, 'country': self.country, 'label': label,
                'lat': self.lat, 'lon': self.lon, 'tz': self.tz, 'population': self.pop}


def _load():
    places, names, words = [], [], []
    with gzip.open(os.path.join(DATA_DIR, 'places.csv.gz'), 'rt', encoding='utf-8') as f:
        for i, r in enumerate(csv.DictReader(f)):
            p = Place()
            p.name, p.region, p.country, p.tz = r['name'], r['region'], r['country'], r['tz']
            p.lat, p.lon, p.pop = float(r['lat']), float(r['lon']), int(r['pop'])
            p.keys = r['keys'].split()
            p.where = r['where'].split()
            places.append(p)
            names.extend((k, i) for k in p.keys)
            words.extend((w, i) for w in r['words'].split())
    names.sort()
    words.sort()
    return places, names, words


def _index_ready():
    global _index
    with _lock:
        if _index is None:
            _index = _load()
    return _index


def _prefixed(pairs, q):
    """Indexes of entries whose key starts with q (pairs sorted by key)."""
    start = bisect.bisect_left(pairs, (q,))
    out = []
    for key, i in pairs[start:]:
        if not key.startswith(q):
            break
        out.append(i)
    return out


def search(query, limit=8):
    name_part, _, where_part = query.partition(',')
    q = _fold(name_part)
    if not q:
        return []
    where = _fold(where_part)
    where = COUNTRY_ALIASES.get(where, where)
    places, names, words = _index_ready()

    def ok(p):
        return not where or any(w.startswith(where) for w in p.where)

    def weight(p):
        return -(p.pop * 10 if q in p.keys else p.pop)

    first = {i for i in _prefixed(names, q) if ok(places[i])}
    second = set() if len(q) < 3 else {i for i in _prefixed(words, q) if ok(places[i])} - first
    ranked = sorted((places[i] for i in first), key=weight) + sorted((places[i] for i in second), key=weight)
    return ranked[:limit]


def warm():
    _index_ready()
