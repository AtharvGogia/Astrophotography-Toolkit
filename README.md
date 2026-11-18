# Astrophotography Toolkit

A small web app for night-sky photographers, run locally on your own computer.

- **Exposure**: the longest shutter time before stars trail, using Frédéric Michaud's NPF
  rule. It also shows a 3 × 3 map of how the limit changes across your sensor, drawn over the
  sky your camera will see.
- **Framing**: your camera frame outlined on the real sky around a target, with field of view,
  pixel scale and rotation.
- **Analyzer**: upload a photo to find where it points and what is in it. It currently uses
  astrometry.net; a built-in solver is in progress.

Target names autocomplete as you type, from built-in star and deep-sky catalogs (works offline).
A red low-light mode keeps your eyes dark-adapted at the telescope.

## Setup

Needs Python 3.10 or newer.

```bash
pip install -r requirements.txt
python -m app
```

Then open <http://127.0.0.1:5000>. (`python backend.py` also still works.)

### Optional

- **Analyzer key.** The analyzer needs a free API key from
  [nova.astrometry.net](https://nova.astrometry.net/) (log in, then *My profile*). Either set the
  `ASTROMETRY_API_KEY` environment variable or copy `config.example.py` to `config.py` and paste
  the key there. `config.py` is gitignored: never commit your key.
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
CC BY-SA 4.0. See `app/catalogs/data/ATTRIBUTION.md`. To rebuild the trimmed copies, download the
originals into `catalog_raw/hyg/` and `catalog_raw/openngc/`, then run
`python scripts/build_catalogs.py`.

Made by Atharv Gogia & Kunal Krishna.
