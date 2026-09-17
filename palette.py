"""Colour palettes for the thermal scale bar.

The default palette ("rainbow") reproduces the classic thermal-camera rainbow
LUT: near-black navy at the cold end, sweeping blue -> cyan -> green -> yellow
-> orange -> red -> magenta at the hot end.

It is defined as a schedule of HSV control points over the *normalised* bar
position t in [0, 1] (0 = cold end, 1 = hot end).  Keeping the definition in
HSV makes the sweep smooth and easy to nudge: move a hue control point and the
whole band shifts without introducing muddy interpolation artefacts.

A palette can also be loaded from CSV (pos,R,G,B), which is what
``extract_palette.py`` writes when you sample the LUT out of an original
screenshot.  That path is byte-exact; this one is a close reconstruction.
"""

from __future__ import annotations

import colorsys
import csv

import numpy as np

# (position, hue in degrees).  Hue decreases monotonically from 248 deg (blue)
# through 0 deg (red) and on to -56 deg (== 304 deg, magenta), so the sweep
# never doubles back.  Spacing is deliberately uneven: the blue band is wide
# and the cyan band is narrow, matching the source scale.
HUE_STOPS = [
    (0.000, 248.0),
    (0.050, 240.0),
    (0.120, 227.0),
    (0.200, 216.0),
    (0.257, 208.0),
    (0.300, 192.0),
    (0.325, 175.0),
    (0.352, 135.0),
    (0.400, 118.0),
    (0.450, 96.0),
    (0.500, 78.0),
    (0.545, 62.0),
    (0.600, 48.0),
    (0.650, 38.0),
    (0.700, 20.0),
    (0.780, 0.0),
    (0.830, -8.0),
    (0.920, -37.0),
    (1.000, -56.0),
]

# Value ramps up from near-black over the bottom ~12% of the bar.
VALUE_STOPS = [
    (0.000, 0.20),
    (0.035, 0.55),
    (0.075, 0.88),
    (0.120, 1.00),
    (1.000, 1.00),
]

# Fully saturated except for a slight lift into pink at the very top.
SAT_STOPS = [
    (0.000, 1.00),
    (0.930, 1.00),
    (1.000, 0.84),
]

DEFAULT_LUT_SIZE = 2048


def _interp(stops, t):
    xs = [s[0] for s in stops]
    ys = [s[1] for s in stops]
    return np.interp(t, xs, ys)


def build_lut(n: int = DEFAULT_LUT_SIZE) -> np.ndarray:
    """Return the default palette as an (n, 3) float array in [0, 1]."""
    t = np.linspace(0.0, 1.0, n)
    hue = _interp(HUE_STOPS, t) / 360.0
    sat = _interp(SAT_STOPS, t)
    val = _interp(VALUE_STOPS, t)
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
    """Return the built-in palette, or one loaded from a CSV path."""
    if palette in (None, "", "rainbow"):
        return build_lut(n)
    return load_lut_csv(palette, n)


def color_at(lut: np.ndarray, value: float, vmin: float, vmax: float) -> np.ndarray:
    """Colour of ``value`` degrees, using the same mapping the bar is drawn with."""
    t = (float(value) - vmin) / (vmax - vmin)
    t = min(max(t, 0.0), 1.0)
    return lut[int(round(t * (len(lut) - 1)))]
