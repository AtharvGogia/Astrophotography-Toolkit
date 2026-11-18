# Catalog data

The files in this folder are trimmed copies of two open catalogs, made with
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
