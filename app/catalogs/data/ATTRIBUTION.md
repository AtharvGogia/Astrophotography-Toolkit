# Catalog data

## Stars and deep-sky objects (CC BY-SA 4.0)

`stars.csv` and `dso.csv` are trimmed copies of two open catalogs, made with
`scripts/build_catalogs.py`. Both sources, and these derived files, are licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

- `stars.csv`: stars brighter than magnitude 8 from the **HYG Database v4.1**
  by David Nash (astronexus), <https://github.com/astronexus/HYG-Database>.
  Columns kept: HIP and HR numbers, proper name, Bayer/Flamsteed designation,
  constellation, RA/Dec (J2000, degrees), visual magnitude and B−V colour index.
- `dso.csv`: NGC/IC/Messier objects that have a Messier number, a common name or are
  brighter than magnitude 12, from **OpenNGC** by Mattia Verga,
  <https://github.com/mattiaverga/OpenNGC>.

Changes made: rows filtered by magnitude and type, columns removed, coordinates converted
to decimal degrees, NGC/IC identifiers reformatted (`NGC0224` → `NGC 224`).

## Constellation figures (BSD 3-Clause)

`constellation_lines.json` is the constellation stick-figure file from **d3-celestial** by
Olaf Frohn, <https://github.com/ofrohn/d3-celestial> (`data/constellations.lines.json`),
copied unchanged. It is under the BSD 3-Clause licence; the full licence text is in
`LICENSE-d3-celestial.txt`.
