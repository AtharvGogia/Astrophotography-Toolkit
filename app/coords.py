"""Target coordinate lookup: bundled catalogs first, online Sesame resolver as a fallback."""
from astropy import units as u
from astropy.coordinates import SkyCoord, get_icrs_coordinates

from . import catalogs


def get_target_coords(data):
    """ICRS coordinates of the target, from custom RA/Dec or a name."""
    if data.get('ra') not in (None, '') and data.get('dec') not in (None, ''):
        return SkyCoord(ra=float(data['ra']) * u.degree, dec=float(data['dec']) * u.degree)
    name = (data.get('target_name') or '').strip()
    if not name:
        raise ValueError('No target name or coordinates given.')
    hit = catalogs.resolve(name.split(' · ')[0]) or catalogs.resolve(name)
    if hit:
        return SkyCoord(ra=hit.ra * u.degree, dec=hit.dec * u.degree)
    return get_icrs_coordinates(name)   # online (CDS Sesame)
