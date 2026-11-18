"""Build the trimmed catalogs shipped in app/catalogs/data/ from the raw downloads.

Raw inputs (not committed, see catalog_raw/ in .gitignore):
  catalog_raw/hyg/hygdata_v41.csv      HYG database v4.1, github.com/astronexus/HYG-Database
  catalog_raw/openngc/NGC.csv          OpenNGC, github.com/mattiaverga/OpenNGC
  catalog_raw/openngc/addendum.csv

Both are CC BY-SA 4.0; the derived files are too (see app/catalogs/data/ATTRIBUTION.md).

Usage:  python scripts/build_catalogs.py [raw_dir]
"""
import csv
import os
import sys

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


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    build_stars()
    build_dso()
