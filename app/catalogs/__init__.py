"""Bundled star / deep-sky catalogs: loading, name search and offline name lookup.

Data: app/catalogs/data/*.csv (HYG and OpenNGC, CC BY-SA 4.0, see ATTRIBUTION.md).
"""
import csv
import math
import os
import re
import threading
from dataclasses import dataclass, field

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

CONSTELLATIONS = {
    'And': 'Andromeda', 'Ant': 'Antlia', 'Aps': 'Apus', 'Aqr': 'Aquarius', 'Aql': 'Aquila', 'Ara': 'Ara',
    'Ari': 'Aries', 'Aur': 'Auriga', 'Boo': 'Boötes', 'Cae': 'Caelum', 'Cam': 'Camelopardalis',
    'Cnc': 'Cancer', 'CVn': 'Canes Venatici', 'CMa': 'Canis Major', 'CMi': 'Canis Minor',
    'Cap': 'Capricornus', 'Car': 'Carina', 'Cas': 'Cassiopeia', 'Cen': 'Centaurus', 'Cep': 'Cepheus',
    'Cet': 'Cetus', 'Cha': 'Chamaeleon', 'Cir': 'Circinus', 'Col': 'Columba', 'Com': 'Coma Berenices',
    'CrA': 'Corona Australis', 'CrB': 'Corona Borealis', 'Crv': 'Corvus', 'Crt': 'Crater', 'Cru': 'Crux',
    'Cyg': 'Cygnus', 'Del': 'Delphinus', 'Dor': 'Dorado', 'Dra': 'Draco', 'Equ': 'Equuleus',
    'Eri': 'Eridanus', 'For': 'Fornax', 'Gem': 'Gemini', 'Gru': 'Grus', 'Her': 'Hercules',
    'Hor': 'Horologium', 'Hya': 'Hydra', 'Hyi': 'Hydrus', 'Ind': 'Indus', 'Lac': 'Lacerta', 'Leo': 'Leo',
    'LMi': 'Leo Minor', 'Lep': 'Lepus', 'Lib': 'Libra', 'Lup': 'Lupus', 'Lyn': 'Lynx', 'Lyr': 'Lyra',
    'Men': 'Mensa', 'Mic': 'Microscopium', 'Mon': 'Monoceros', 'Mus': 'Musca', 'Nor': 'Norma',
    'Oct': 'Octans', 'Oph': 'Ophiuchus', 'Ori': 'Orion', 'Pav': 'Pavo', 'Peg': 'Pegasus', 'Per': 'Perseus',
    'Phe': 'Phoenix', 'Pic': 'Pictor', 'Psc': 'Pisces', 'PsA': 'Piscis Austrinus', 'Pup': 'Puppis',
    'Pyx': 'Pyxis', 'Ret': 'Reticulum', 'Sge': 'Sagitta', 'Sgr': 'Sagittarius', 'Sco': 'Scorpius',
    'Scl': 'Sculptor', 'Sct': 'Scutum', 'Ser': 'Serpens', 'Sex': 'Sextans', 'Tau': 'Taurus',
    'Tel': 'Telescopium', 'Tri': 'Triangulum', 'TrA': 'Triangulum Australe', 'Tuc': 'Tucana',
    'UMa': 'Ursa Major', 'UMi': 'Ursa Minor', 'Vel': 'Vela', 'Vir': 'Virgo', 'Vol': 'Volans',
    'Vul': 'Vulpecula',
}

GREEK = {
    'Alp': ('α', 'alpha'), 'Bet': ('β', 'beta'), 'Gam': ('γ', 'gamma'), 'Del': ('δ', 'delta'),
    'Eps': ('ε', 'epsilon'), 'Zet': ('ζ', 'zeta'), 'Eta': ('η', 'eta'), 'The': ('θ', 'theta'),
    'Iot': ('ι', 'iota'), 'Kap': ('κ', 'kappa'), 'Lam': ('λ', 'lambda'), 'Mu': ('μ', 'mu'),
    'Nu': ('ν', 'nu'), 'Xi': ('ξ', 'xi'), 'Omi': ('ο', 'omicron'), 'Pi': ('π', 'pi'), 'Rho': ('ρ', 'rho'),
    'Sig': ('σ', 'sigma'), 'Tau': ('τ', 'tau'), 'Ups': ('υ', 'upsilon'), 'Phi': ('φ', 'phi'),
    'Chi': ('χ', 'chi'), 'Psi': ('ψ', 'psi'), 'Ome': ('ω', 'omega'),
}

DSO_TYPES = {
    'G': 'Galaxy', 'GPair': 'Galaxy pair', 'GTrpl': 'Galaxy triplet', 'GGroup': 'Galaxy group',
    'OCl': 'Open cluster', 'GCl': 'Globular cluster', 'Cl+N': 'Cluster with nebula', '*Ass': 'Stellar association',
    'Neb': 'Nebula', 'EmN': 'Emission nebula', 'RfN': 'Reflection nebula', 'HII': 'HII region',
    'PN': 'Planetary nebula', 'SNR': 'Supernova remnant', 'DrkN': 'Dark nebula', 'Cl': 'Cluster',
    'Ast': 'Asterism', 'Gxy': 'Galaxy',
}


def _norm(text):
    """Lowercase, strip accents/spaces/punctuation: 'M 8' -> 'm8', 'Boötes' -> 'bootes'."""
    text = text.lower().replace('ö', 'o').replace('é', 'e')
    return re.sub(r'[^a-z0-9α-ω]', '', text)


@dataclass
class Target:
    name: str            # display name, e.g. "M 8 · Lagoon Nebula"
    kind: str            # "Nebula", "Star", "Constellation", ...
    ra: float            # degrees, J2000
    dec: float
    con: str = ''        # constellation full name
    mag: float = None
    rank: float = 0.0    # lower = more prominent
    keys: list = field(default_factory=list)
    words: set = field(default_factory=set)

    def __post_init__(self):
        # Individual words of the display name, for "starts a word" matches ("neb" -> Lagoon Nebula).
        self.words = {_norm(w) for w in re.split(r'[\s·()/-]+', self.name) if _norm(w)}

    def to_dict(self):
        return {'name': self.name, 'kind': self.kind, 'ra': round(self.ra, 5), 'dec': round(self.dec, 5),
                'constellation': self.con, 'mag': self.mag}


_targets = None
_stars = None
_lock = threading.Lock()


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_stars():
    """All stars (mag <= 8) as dict rows with float ra/dec/mag/ci."""
    global _stars
    if _stars is None:
        rows = []
        with open(os.path.join(DATA_DIR, 'stars.csv'), encoding='utf-8') as f:
            for r in csv.DictReader(f):
                r['ra'], r['dec'], r['mag'] = float(r['ra']), float(r['dec']), float(r['mag'])
                r['ci'] = _float(r['ci'])
                rows.append(r)
        _stars = rows
    return _stars


def _build_targets():
    targets = []
    stars = load_stars()

    # Stars: proper names, plus Bayer designations for naked-eye stars.
    con_pos = {}
    for s in stars:
        con = s['con']
        if s['mag'] <= 6.5 and con:
            con_pos.setdefault(con, []).append((s['ra'], s['dec'], s['mag']))
        if not (s['proper'] or (s['bayer'] and s['mag'] <= 6.0)):
            continue
        con_full = CONSTELLATIONS.get(con, con)
        keys, bayer_label = [], ''
        if s['bayer']:
            base, _, suffix = s['bayer'].partition('-')
            sym, word = GREEK.get(base, (base, base))
            bayer_label = f'{sym}{("¹²³⁴⁵⁶⁷⁸⁹"[int(suffix) - 1]) if suffix.isdigit() and 0 < int(suffix) < 10 else ""} {con}'
            keys += [_norm(f'{sym}{suffix}{con}'), _norm(f'{word}{suffix}{con}'), _norm(f'{base}{suffix}{con}'),
                     _norm(f'{word} {con_full}')]
        if s['proper']:
            keys.insert(0, _norm(s['proper']))
            name = f"{s['proper']} · {bayer_label}" if bayer_label else s['proper']
        else:
            name = bayer_label
        if s['hip']:
            keys.append(f"hip{s['hip']}")
        targets.append(Target(name, 'Star', s['ra'], s['dec'], con_full, s['mag'],
                              rank=s['mag'] - (3 if s['proper'] else 0), keys=keys))

    # Deep-sky objects.
    with open(os.path.join(DATA_DIR, 'dso.csv'), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            commons = [c for c in r['common'].split('|') if c]
            ids = [x for x in (r['messier'], r['id']) if x]
            label = ' · '.join([ids[0]] + commons[:1]) if commons else ' · '.join(ids)
            keys = [_norm(x) for x in ids + commons]
            mag = _float(r['mag'])
            rank = (-10 if r['messier'] else -5 if commons else 0) + (mag if mag is not None else 12)
            targets.append(Target(label, DSO_TYPES.get(r['type'], r['type']), float(r['ra']), float(r['dec']),
                                  CONSTELLATIONS.get(r['con'], r['con']), mag, rank, keys))

    # Constellations: centre = brightness-weighted mean of their naked-eye stars.
    for abbr, pts in con_pos.items():
        w = [10 ** (-0.4 * m) for _, _, m in pts]
        x = sum(wi * math.cos(math.radians(d)) * math.cos(math.radians(r)) for wi, (r, d, _) in zip(w, pts))
        y = sum(wi * math.cos(math.radians(d)) * math.sin(math.radians(r)) for wi, (r, d, _) in zip(w, pts))
        z = sum(wi * math.sin(math.radians(d)) for wi, (r, d, _) in zip(w, pts))
        ra = math.degrees(math.atan2(y, x)) % 360
        dec = math.degrees(math.atan2(z, math.hypot(x, y)))
        full = CONSTELLATIONS.get(abbr, abbr)
        targets.append(Target(full, 'Constellation', ra, dec, full, None, rank=-20,
                              keys=[_norm(full), _norm(abbr)]))
    return targets


def targets():
    global _targets
    with _lock:
        if _targets is None:
            _targets = _build_targets()
    return _targets


def search(query, limit=8):
    """Name search for the target box: exact > prefix > word prefix > all words, then prominence."""
    q = _norm(query)
    if not q:
        return []
    raw_words = [_norm(w) for w in query.split() if _norm(w)]
    scored = []
    for t in targets():
        if q in t.keys:
            best = 0
        elif any(k.startswith(q) for k in t.keys):
            best = 1
        elif any(w.startswith(q) for w in t.words):
            best = 2
        elif len(raw_words) > 1 and all(any(w.startswith(r) for w in t.words) or any(k.startswith(r) for k in t.keys)
                                        for r in raw_words):
            best = 3
        else:
            best = None
        if best is not None:
            scored.append((best, t.rank, t.name, t))
    scored.sort(key=lambda s: s[:3])
    return [s[3] for s in scored[:limit]]


def resolve(name):
    """Exact (normalised) name match in the bundled catalogs, or None."""
    q = _norm(name)
    if not q:
        return None
    hits = [t for t in targets() if q in t.keys]
    return min(hits, key=lambda t: t.rank) if hits else None
