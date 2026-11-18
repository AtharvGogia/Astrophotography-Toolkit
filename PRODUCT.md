# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Beginner to intermediate night-sky photographers: hobbyists with a DSLR or mirrorless camera and a
wide or standard lens (roughly 15–135 mm on full frame), learning astrophotography. They want
straight answers: when it gets dark, whether their target will be up and where to point, how long
they can expose before stars trail, what their lens will frame, and what is in a photo they took.
They should not need to know the jargon (NPF, plate solving, twilight types) to get those answers,
but the numbers must be right.

## Product Purpose

A set of tools for planning and reading night-sky photographs:

- **Home**: tonight at a glance for the observer's location: when it gets dark, the Moon, and the
  showpiece objects best placed tonight.
- **Planner**: whether a target clears the horizon on a chosen night, when it rises, peaks and
  sets, which way to look, the best dark window above a chosen altitude, twilight times, the Moon,
  a 30-night Moon calendar, and an all-sky chart of the sky at any time of the night.
- **Exposure**: the longest shutter time before stars trail (Michaud's NPF rule), with a 3 × 3 map
  across the sensor drawn over the sky the camera will see.
- **Framing**: the camera frame outlined on the real sky around a target.
- **Analyzer**: upload a photo; it is plate-solved and annotated with constellation figures, named
  stars, deep-sky objects and an optional RA/Dec grid, with overlays limited to the starry part of
  the frame.

Success: a beginner plans a shoot, goes out, and comes back with sharp, well-framed photos of the
target they meant to shoot, and can identify what they captured.

## Positioning

Everything is computed in-house from real catalogs: plate solving and annotation run on the
toolkit's own server or computer (no astrometry.net, no account), and star fields, sky previews and
the sky chart are drawn from the bundled star and deep-sky catalogs. Calculations use the full
formulas (full NPF rule, astropy positions), not rules of thumb.

## Operating Context

- Used in two settings: planning at a desk beforehand, and checking at night in the field on a
  phone or laptop beside the camera. The red low-light mode exists for the field and must keep
  working for every feature.
- Offered both as a free public website (Google Cloud Run, scales to zero) and as an app people can
  run locally (`python -m app`). Neither needs an account.
- The observing location is set once (browser geolocation or typed coordinates) and stored only in
  the browser. Times show in the viewer's time zone.
- Hosted mode: uploads are processed in memory and discarded after the answer; uploads up to 30 MB
  (larger JPG/PNG files are shrunk in the browser first); 20 analyses per visitor per 10 minutes.

## Capabilities and Constraints

- Stack: Flask (Python) with Jinja templates and plain JavaScript and CSS; astropy, reproject,
  sep and tetra3rs. No front-end framework or build step.
- Plate solver handles fields of view from about 10° to 90° (camera lenses). Telescope fields under
  10° are not supported yet (they need a star index over 1 GB).
- Accuracy: sub-pixel on clean frames, 1–3 px on typical processed photos, looser on very wide or
  distorted lenses.
- Image input: JPG, PNG, TIFF, FITS; RAW (CR2, NEF, ARW and others) when the optional rawpy package
  is installed.
- Target search works offline from the bundled catalogs; other names fall back to an online lookup
  (CDS Sesame).
- Undecided: a frame-quality page (ranking sub-frames by sharpness, trailing and tilt), a narrow-field
  index for telescopes, and showing times in the observing site's time zone.

## Brand Commitments

- Name: Astrophotography Toolkit.
- Made by Atharv Gogia and Kunal Krishna; the credit stays in the footer and README.
- Palette chosen by the user ("Dark sky reserve"): night #100E0B, panel #221D17, moonless #4E6B57,
  action #D98B52 (copper), light #E6DCCB, bright #F6EFE2. It replaced two earlier palettes.
- A red low-light mode for dark adaptation is part of the product.
- Catalog attribution must stay visible: HYG Database and OpenNGC (CC BY-SA 4.0), d3-celestial
  constellation figures (BSD 3-Clause), tetra3rs (MIT) with Gaia DR3 / Hipparcos data.

## Evidence on Hand

- Sample photos for testing the analyzer in `Samples/` (gitignored, not for publishing).
- Verified results: planner times checked against real sunset and Moon-phase data; solver results
  on the samples are documented in README.md.
- No testimonials, user counts, press or reviews exist. Do not invent them.

## Product Principles

1. Answers before jargon: lead with the plain answer (a time, a direction, a number of seconds),
   and keep the technical detail available underneath.
2. Correct over approximate: use the full formulas and real catalog data, and say where a result
   is an estimate or out of range.
3. Works in the dark: every screen has to be usable in the red low-light mode, at night, on a
   phone.
4. Private and account-free: nothing needs signing in; locations stay in the browser and uploaded
   photos are not kept.
5. One screen per task on desktop: a tool's inputs and its result should fit without scrolling in
   most cases.

## Accessibility & Inclusion

- Low-light mode: dim, red-only interface for dark-adapted eyes.
- Must work on phones in the field as well as on desktop.
- No formal standard has been set; aim for readable contrast in both modes and full keyboard use of
  forms and the target search.
