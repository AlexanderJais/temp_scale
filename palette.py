"""Colour palettes for the thermal scale bar.

Each palette is a schedule of HSV control points over the *normalised* bar
position t in [0, 1] (0 = cold end, 1 = hot end).  Keeping the definition in
HSV makes the sweep smooth and easy to nudge: move a hue control point and the
whole band shifts without introducing muddy interpolation artefacts.

A palette can also be loaded from a CSV (pos,R,G,B), which is what
``extract_palette.py`` writes when you sample a LUT out of an original
screenshot.

Available:

``rainbow``
    Blue -> bright cyan -> green -> yellow -> red -> magenta, with a near-black
    navy cold end.  Reconstructed by eye from a screenshot.

``rainbow-hc``
    The FLIR-style high-contrast variant: blue and green are separated by a
    *dark teal node* instead of a bright cyan band, the cold ramp is much
    longer, and the hot end desaturates to white above magenta.  Measured
    directly off the colour bar in the source figure, so the hue schedule is
    the real thing; saturation and value are cleaned back up to a full gamut
    (the source was a compressed, downscaled screenshot sitting ~5% dim).
"""

from __future__ import annotations

import colorsys
import csv

import numpy as np

PALETTES: dict[str, dict[str, list[tuple[float, float]]]] = {
    "rainbow": {
        # Hue falls monotonically from 248 deg (blue) through 0 deg (red) and on
        # to -56 deg (== 304 deg, magenta), so the sweep never doubles back.
        # Spacing is deliberately uneven: wide blue band, narrow cyan.
        "hue": [
            (0.000, 248.0), (0.050, 240.0), (0.120, 227.0), (0.200, 216.0),
            (0.257, 208.0), (0.300, 192.0), (0.325, 175.0), (0.352, 135.0),
            (0.400, 118.0), (0.450, 96.0), (0.500, 78.0), (0.545, 62.0),
            (0.600, 48.0), (0.650, 38.0), (0.700, 20.0), (0.780, 0.0),
            (0.830, -8.0), (0.920, -37.0), (1.000, -56.0),
        ],
        "value": [
            (0.000, 0.20), (0.035, 0.55), (0.075, 0.88), (0.120, 1.00),
            (1.000, 1.00),
        ],
        "sat": [(0.000, 1.00), (0.930, 1.00), (1.000, 0.84)],
    },
    "rainbow-hc": {
        # Constant blue hue through the whole cold ramp, then a fast sweep
        # 240 -> 110 across the dark teal node, then a steady march to magenta.
        "hue": [
            (0.000, 241.0), (0.214, 240.0), (0.250, 233.0), (0.286, 217.0),
            (0.321, 173.0), (0.357, 128.0), (0.393, 113.0), (0.429, 110.0),
            (0.464, 95.0), (0.500, 76.0), (0.536, 58.0), (0.571, 45.0),
            (0.607, 33.0), (0.643, 23.0), (0.679, 12.0), (0.714, -1.0),
            (0.750, -5.0), (0.786, -14.0), (0.821, -26.0), (0.857, -40.0),
            (0.893, -57.0), (0.929, -62.0), (1.000, -62.0),
        ],
        # Long ramp out of black, then the dark teal node at t ~ 0.32, then flat.
        "value": [
            (0.000, 0.05), (0.050, 0.20), (0.100, 0.40), (0.150, 0.61),
            (0.180, 0.79), (0.220, 1.00), (0.250, 0.88), (0.286, 0.70),
            (0.321, 0.48), (0.357, 0.66), (0.393, 0.83), (0.429, 0.96),
            (0.464, 1.00), (1.000, 1.00),
        ],
        # Fully saturated until the white cap at the very top.
        "sat": [(0.000, 1.00), (0.930, 1.00), (0.964, 0.72), (1.000, 0.15)],
    },
}

DEFAULT_PALETTE = "rainbow-hc"
DEFAULT_LUT_SIZE = 2048


def list_palettes() -> list[str]:
    return list(PALETTES)


def _interp(stops, t):
    return np.interp(t, [s[0] for s in stops], [s[1] for s in stops])


def build_lut(name: str = DEFAULT_PALETTE, n: int = DEFAULT_LUT_SIZE) -> np.ndarray:
    """Return a named palette as an (n, 3) float array in [0, 1]."""
    try:
        spec = PALETTES[name]
    except KeyError:
        raise SystemExit(
            f"unknown palette {name!r}; choose from {', '.join(PALETTES)} "
            f"or give a path to a CSV") from None
    t = np.linspace(0.0, 1.0, n)
    hue = _interp(spec["hue"], t) / 360.0
    sat = _interp(spec["sat"], t)
    val = _interp(spec["value"], t)
    rgb = [colorsys.hsv_to_rgb(h % 1.0, s, v) for h, s, v in zip(hue, sat, val)]
    return np.asarray(rgb, dtype=float)


def load_lut_csv(path: str, n: int = DEFAULT_LUT_SIZE) -> np.ndarray:
    """Load a palette from a ``pos,R,G,B`` CSV and resample it to n entries.

    ``pos`` is the normalised bar position in [0, 1]; R/G/B are 0-255 ints.
    Rows may be in any order and need not be evenly spaced.
    """
    pos, cols = [], []
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].lstrip().startswith("#"):
                continue
            if row[0].strip().lower() in ("pos", "position", "t"):
                continue  # header
            pos.append(float(row[0]))
            cols.append([float(row[1]), float(row[2]), float(row[3])])
    if len(pos) < 2:
        raise ValueError(f"{path}: need at least two colour stops")

    pos = np.asarray(pos, dtype=float)
    cols = np.asarray(cols, dtype=float) / 255.0
    order = np.argsort(pos)
    pos, cols = pos[order], cols[order]

    t = np.linspace(0.0, 1.0, n)
    return np.stack([np.interp(t, pos, cols[:, c]) for c in range(3)], axis=1)


def save_lut_csv(path: str, lut: np.ndarray) -> None:
    """Write an (n, 3) float LUT as a ``pos,R,G,B`` CSV."""
    n = len(lut)
    rgb8 = np.clip(np.round(lut * 255.0), 0, 255).astype(int)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pos", "R", "G", "B"])
        for i in range(n):
            w.writerow([f"{i / (n - 1):.6f}", *rgb8[i]])


def get_lut(palette: str | None = None, n: int = DEFAULT_LUT_SIZE) -> np.ndarray:
    """Return a palette by name, or load one from a CSV path."""
    if palette in (None, ""):
        palette = DEFAULT_PALETTE
    if palette in PALETTES:
        return build_lut(palette, n)
    return load_lut_csv(palette, n)


def color_at(lut: np.ndarray, value: float, vmin: float, vmax: float) -> np.ndarray:
    """Colour of ``value`` degrees, using the same mapping the bar is drawn with."""
    t = (float(value) - vmin) / (vmax - vmin)
    t = min(max(t, 0.0), 1.0)
    return lut[int(round(t * (len(lut) - 1)))]
