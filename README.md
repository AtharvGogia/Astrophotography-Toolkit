# Astrophotography Toolkit

A small web app for night-sky photographers, run locally on your own computer.

- **Home**: tonight at a glance for your location: when it gets dark, the Moon, and the showpiece
  objects that are best placed tonight.
- **Planner**: whether a target clears the horizon on a given night, when it rises, peaks and sets,
  which way to look, the best dark window above your chosen altitude, twilight times, and the Moon's
  phase, rise and set, plus a 30-night Moon calendar with the next new and full Moons.
- **Exposure**: the longest shutter time before stars trail, using Frédéric Michaud's NPF
  rule. It also shows a 3 × 3 map of how the limit changes across your sensor, drawn over the
  sky your camera will see.
- **Framing**: your camera frame outlined on the real sky around a target, with field of view,
  pixel scale and rotation.
- **Analyzer**: open a photo to find exactly where it points and what is in it. It plate-solves
  the photo on your computer (no internet, no account), draws the constellation figures and labels
  named stars, nebulae, clusters and galaxies, with an optional RA/Dec grid.

Your observing location is set once from the header ("Use my current location" asks the browser, or
type coordinates). It is stored only in your browser. Times are shown in your computer's time zone.
Target names autocomplete as you type, from built-in star and deep-sky catalogs (works offline).
A red low-light mode keeps your eyes dark-adapted at the telescope.

## Setup

Needs Python 3.10 or newer.

```bash
pip install -r requirements.txt
python -m app
```

Then open <http://127.0.0.1:5000>. (`python backend.py` also still works.)

The first start builds the plate-solving index (a few seconds, about 30 MB in
`app/solver/cache/`); later starts just load it.

### Optional

- **Skymap image.** Sky previews are drawn from the built-in star catalog. If you put a
  `composite_skymap_16k.png` (an all-sky plate carrée image, RA 0h at the centre) in the project
  folder, or point `SKYMAP_PATH` at one, it is used instead; that is useful for a map with
  constellation art. The original one is in this
  [Google Drive folder](https://drive.google.com/drive/folders/1rrDNBE-_NzLOH3oTllvlRFs0W_YL9cPu?usp=sharing).
- **RAW files.** `pip install rawpy` adds CR2/NEF/ARW/… support to the image loader.
- `FLASK_DEBUG=1` runs the server in debug mode (off by default).

## Project layout

```
app/                Flask app (python -m app)
  routes/           pages, calculator API, analyzer API
  catalogs/         star and deep-sky catalogs, name search
  solver/           plate solver: star detection (sep), pattern matching (tetra3rs),
                    lens-distortion fit (TAN-SIP)
  annotate.py       labels for a solved photo: stars, deep-sky objects, constellations, grid
  planner.py        twilight, rise/transit/set, best window, Moon phase and cycle (astropy)
  skymap.py         sky previews (reprojection to your camera's view)
  starfield.py      draws real star fields from the catalog
  imageio.py        loads JPG/PNG/TIFF, FITS and RAW photos
  templates/        HTML pages
static/             CSS, JavaScript, camera presets, images
scripts/            build_catalogs.py, render_masthead.py
tests/              pytest suite: pip install -r requirements-dev.txt, then pytest
```

## Catalog data

Star data comes from the [HYG Database](https://github.com/astronexus/HYG-Database) by David Nash,
and deep-sky data from [OpenNGC](https://github.com/mattiaverga/OpenNGC) by Mattia Verga, both
CC BY-SA 4.0. Constellation figures are from [d3-celestial](https://github.com/ofrohn/d3-celestial)
by Olaf Frohn (BSD 3-Clause). See `app/catalogs/data/ATTRIBUTION.md`. To rebuild the trimmed copies, download the
originals into `catalog_raw/hyg/` and `catalog_raw/openngc/`, then run
`python scripts/build_catalogs.py`.

Plate solving uses [tetra3rs](https://github.com/ssmichael1/tetra3rs) (MIT) and its bundled star
catalog from ESA's Gaia DR3 mission, with Hipparcos for the brightest stars. Star detection uses
[sep](https://github.com/kbarbary/sep), the library version of Source Extractor.

## Plate solver: what to expect

- **Fields of view from about 10° to 90°**: camera lenses from roughly 15 mm to 135 mm on full
  frame. Typical solve time is 1–3 s. Telescope fields under 10° need a much larger star index
  (over 1 GB), so they aren't supported yet.
- **Accuracy:** sub-pixel on clean frames, and 1–3 px on typical processed photos. Very wide or
  strongly distorted lenses are looser (about 10 px on a 6000 px, 68° frame), which still puts
  labels in the right place.
- If you enter your camera and focal length, the solver tries that field of view first.

Made by Atharv Gogia & Kunal Krishna.
