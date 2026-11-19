"""Build the trimmed catalogs shipped in app/catalogs/data/ from the raw downloads.

Raw inputs (not committed, see catalog_raw/ in .gitignore):
  catalog_raw/hyg/hygdata_v41.csv      HYG database v4.1, github.com/astronexus/HYG-Database
  catalog_raw/openngc/NGC.csv          OpenNGC, github.com/mattiaverga/OpenNGC
  catalog_raw/openngc/addendum.csv
  catalog_raw/geonames/cities5000.txt  GeoNames places with 5,000+ people (from cities5000.zip),
  catalog_raw/geonames/admin1CodesASCII.txt, countryInfo.txt   download.geonames.org/export/dump/

HYG and OpenNGC are CC BY-SA 4.0, GeoNames CC BY 4.0; the derived files keep those licences
(see app/catalogs/data/ATTRIBUTION.md). Each step runs only when its raw files are present.

Usage:  python scripts/build_catalogs.py [raw_dir]
"""
import csv
import gzip
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'catalog_raw')
OUT = os.path.join(ROOT, 'app', 'catalogs', 'data')

STAR_MAG_LIMIT = 8.0
DSO_MAG_LIMIT = 12.0
SKIP_DSO_TYPES = {'Dup', 'NonEx', '*', '**', 'Other', 'Nova'}


def sexagesimal_to_deg(value, hours):
    sign = -1 if value.strip().startswith('-') else 1
    parts = [float(p) for p in value.strip().lstrip('+-').split(':')]
    deg = parts[0] + parts[1] / 60 + (parts[2] if len(parts) > 2 else 0) / 3600
    return sign * deg * (15 if hours else 1)


def pretty_ngc(name):
    """'NGC0224' -> 'NGC 224', 'IC0001' -> 'IC 1'; other ids unchanged."""
    for prefix in ('NGC', 'IC'):
        if name.startswith(prefix) and name[len(prefix):len(prefix) + 4].isdigit():
            return f'{prefix} {int(name[len(prefix):len(prefix) + 4])}{name[len(prefix) + 4:]}'
    return name


def build_stars():
    src = os.path.join(RAW, 'hyg', 'hygdata_v41.csv')
    out = os.path.join(OUT, 'stars.csv')
    n = 0
    with open(src, encoding='utf-8') as f, open(out, 'w', newline='', encoding='utf-8') as g:
        w = csv.writer(g)
        w.writerow(['hip', 'hr', 'proper', 'bayer', 'flam', 'con', 'ra', 'dec', 'mag', 'ci'])
        for r in csv.DictReader(f):
            if r['proper'] == 'Sol' or not r['mag']:
                continue
            mag = float(r['mag'])
            if mag > STAR_MAG_LIMIT:
                continue
            w.writerow([r['hip'], r['hr'], r['proper'], r['bayer'], r['flam'], r['con'],
                        f"{float(r['ra']) * 15:.5f}", f"{float(r['dec']):.5f}", f'{mag:.2f}', r['ci']])
            n += 1
    print(f'stars.csv: {n} stars (mag <= {STAR_MAG_LIMIT})')


def build_dso():
    out = os.path.join(OUT, 'dso.csv')
    n = 0
    with open(out, 'w', newline='', encoding='utf-8') as g:
        w = csv.writer(g)
        w.writerow(['id', 'messier', 'common', 'type', 'ra', 'dec', 'con', 'maj', 'min', 'mag'])
        for fname in ('NGC.csv', 'addendum.csv'):
            with open(os.path.join(RAW, 'openngc', fname), encoding='utf-8') as f:
                for r in csv.DictReader(f, delimiter=';'):
                    if r['Type'] in SKIP_DSO_TYPES or not r['RA'] or not r['Dec']:
                        continue
                    mag = r['V-Mag'] or r['B-Mag']
                    messier = f"M {int(r['M'])}" if r['M'] else ''
                    common = r['Common names'].replace(',', '|')
                    if not (messier or common or (mag and float(mag) <= DSO_MAG_LIMIT)):
                        continue
                    w.writerow([pretty_ngc(r['Name']), messier, common, r['Type'],
                                f"{sexagesimal_to_deg(r['RA'], True):.5f}", f"{sexagesimal_to_deg(r['Dec'], False):.5f}",
                                r['Const'], r['MajAx'], r['MinAx'], mag])
                    n += 1
    print(f'dso.csv: {n} objects')


def _fold(text):
    """Accents folded, lowercase, letters and digits only: 'São Paulo' -> 'saopaulo'."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]', '', text)


def _fold_words(*texts):
    out = []
    for text in texts:
        for part in re.split(r'[\s\-/,.()]+', text):
            w = _fold(part)
            if w and w not in out:
                out.append(w)
    return out


def build_places():
    """places.csv.gz: display fields plus precomputed search keys, so the app loads it quickly.

    keys:  the whole name folded ("newyorkcity"), and its ASCII spelling if different
    words: each word of the name ("new york city")
    where: region and country, whole and by word, plus the region code where it is letters
           (US and some other countries use postal codes, e.g. "tx")
    """
    src = os.path.join(RAW, 'geonames')
    countries = {}
    with open(os.path.join(src, 'countryInfo.txt'), encoding='utf-8') as f:
        for line in f:
            if not line.startswith('#'):
                cols = line.rstrip('\n').split('\t')
                countries[cols[0]] = cols[4]
    regions = {}
    with open(os.path.join(src, 'admin1CodesASCII.txt'), encoding='utf-8') as f:
        for line in f:
            code, name, _ascii, _gid = line.rstrip('\n').split('\t')
            regions[code] = name
    out = os.path.join(OUT, 'places.csv.gz')
    n = 0
    with gzip.open(out, 'wt', newline='', encoding='utf-8', compresslevel=9) as g:
        w = csv.writer(g)
        w.writerow(['name', 'region', 'country', 'lat', 'lon', 'pop', 'tz', 'keys', 'words', 'where'])
        with open(os.path.join(src, 'cities5000.txt'), encoding='utf-8') as f:
            for line in f:
                c = line.rstrip('\n').split('\t')
                name, ascii_name, lat, lon, cc, admin1, pop, tz = c[1], c[2], c[4], c[5], c[8], c[10], c[14], c[17]
                if c[7] in ('PPLX', 'PPLH', 'PPLQ', 'PPLW'):     # districts of a city, historical or abandoned
                    continue
                region, country = regions.get(f'{cc}.{admin1}', ''), countries.get(cc, cc)
                keys = [k for k in dict.fromkeys((_fold(name), _fold(ascii_name))) if k]
                words = _fold_words(name, ascii_name)
                where = _fold_words(region, country)
                for whole in (_fold(region), _fold(country), admin1.lower() if admin1.isalpha() else '', cc.lower()):
                    if whole and whole not in where:
                        where.append(whole)
                w.writerow([name, region, country, f'{float(lat):.4f}', f'{float(lon):.4f}', int(pop or 0), tz,
                            ' '.join(keys), ' '.join(words), ' '.join(where)])
                n += 1
    print(f'places.csv.gz: {n} places, {os.path.getsize(out) / 1e6:.1f} MB')


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(os.path.join(RAW, 'hyg')):
        build_stars()
    if os.path.exists(os.path.join(RAW, 'openngc')):
        build_dso()
    if os.path.exists(os.path.join(RAW, 'geonames', 'cities5000.txt')):
        build_places()
