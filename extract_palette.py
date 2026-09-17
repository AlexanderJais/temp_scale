#!/usr/bin/env python3
"""Pull the exact colour LUT out of an original scale-bar screenshot.

The built-in palette in ``palette.py`` is a close reconstruction.  If you still
have the original image, run this to recover the real LUT byte-for-byte and
hand the CSV to ``make_scale.py --palette``.

    python3 extract_palette.py original.png -o palettes/original.csv
    python3 extract_palette.py original.png --bbox 12,110,54,545 --range 18.6 39.6

The colour bar is located automatically: the widest block of columns that are
mostly vivid pixels, then the tallest run of vivid rows inside it, extended
downwards through any near-black cold tail.  If the guess is wrong, pass
``--bbox`` with the interior of the bar (excluding the frame) and it is used
verbatim.  Rows dominated by tick dashes or overlaid labels are detected as
saturation outliers and filled in from their neighbours.
"""

from __future__ import annotations

import argparse
import colorsys

import numpy as np
from PIL import Image

import palette as pal


def _hsv(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (saturation, value) for an (..., 3) float array in [0, 1]."""
    mx = arr.max(axis=-1)
    mn = arr.min(axis=-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    return sat, mx


def _extent(score: np.ndarray, thresh: float) -> tuple[int, int]:
    """First and last (exclusive) index whose score clears ``thresh``."""
    idx = np.flatnonzero(score >= thresh)
    if idx.size == 0:
        raise SystemExit("could not locate the colour bar; pass --bbox explicitly")
    return int(idx[0]), int(idx[-1]) + 1


def locate_bar(rgb: np.ndarray) -> tuple[int, int, int, int]:
    """Bounding box of the colour bar's interior.

    Uses the extent of vivid pixels rather than their longest unbroken run:
    labels drawn over the gradient punch holes in both the row and the column
    profiles, and on a bar with large type those holes can outnumber the gaps
    between them.
    """
    sat, val = _hsv(rgb)
    vivid = (sat > 0.55) & (val > 0.20)

    col_score = vivid.sum(axis=0).astype(float)
    if col_score.max() == 0:
        raise SystemExit("no saturated colours found; pass --bbox explicitly")
    x0, x1 = _extent(col_score, 0.25 * col_score.max())

    row_frac = vivid[:, x0:x1].mean(axis=1)
    y0, y1 = _extent(row_frac, 0.25)

    # Extend through the dark, low-saturation cold tail beyond the vivid band.
    h = rgb.shape[0]
    def dark_blue(y):
        med = np.median(rgb[y, x0:x1], axis=0)
        return med.max() < 0.45 and med[2] >= med[0] and med[2] >= med[1]

    while y1 < h and dark_blue(y1):
        y1 += 1
    while y0 > 0 and dark_blue(y0 - 1):
        y0 -= 1
    return x0, y0, x1, y1


def _median_filter(rows: np.ndarray, k: int) -> np.ndarray:
    """Running median over the row axis, used only to spot outliers."""
    k = max(3, k | 1)
    pad = k // 2
    padded = np.pad(rows, ((pad, pad), (0, 0)), mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(padded, k, axis=0)
    return np.median(win, axis=-1)


def sample_rows(rgb: np.ndarray, box, inset: int) -> np.ndarray:
    """One colour per row of the bar, ignoring anything drawn on top of it."""
    x0, y0, x1, y1 = box
    strip = rgb[y0:y1, x0 + inset:x1 - inset]
    if strip.size == 0:
        raise SystemExit(f"empty sampling strip for bbox {box} with inset {inset}")

    # Tick dashes, glyphs and their halos are black, white or grey, so they have
    # near-zero saturation while the gradient is strongly saturated all the way
    # down to its dark navy end.  Dropping the near-greys leaves only gradient
    # pixels to take the median of, even on rows the labels mostly cover.
    sat, _ = _hsv(strip)
    keep = sat > 0.40
    enough = keep.sum(axis=1) >= max(3, int(0.15 * strip.shape[1]))

    rows = np.empty((strip.shape[0], 3), dtype=float)
    for i in range(strip.shape[0]):
        sel = strip[i][keep[i]] if enough[i] else strip[i]
        rows[i] = np.median(sel, axis=0)

    # Backstop: rows still far from the local trend (a fully covered row, a
    # gridline) get filled in from their neighbours.
    span = max(9, len(rows) // 40)
    dev = np.abs(rows - _median_filter(rows, span)).max(axis=1)
    bad = (dev > 0.16) | ~enough
    bad[0] = bad[-1] = False
    if bad.any() and (~bad).sum() > 1:
        idx = np.arange(len(rows))
        for c in range(3):
            rows[bad, c] = np.interp(idx[bad], idx[~bad], rows[~bad, c])
        print(f"repaired {int(bad.sum())} row(s) obscured by labels or ticks")
    return np.clip(rows, 0.0, 1.0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image")
    p.add_argument("-o", "--out", default="palettes/original.csv")
    p.add_argument("--bbox", default=None,
                   help="x0,y0,x1,y1 interior of the bar, excluding the frame")
    p.add_argument("--inset", type=int, default=2,
                   help="pixels to trim from each side before sampling")
    p.add_argument("--n", type=int, default=pal.DEFAULT_LUT_SIZE,
                   help="entries in the written LUT")
    p.add_argument("--range", nargs=2, type=float, metavar=("VMIN", "VMAX"),
                   default=None, help="if given, print the colour at each tick")
    p.add_argument("--tick-step", type=float, default=2.0)
    p.add_argument("--cold-at", choices=["bottom", "top"], default="bottom")
    a = p.parse_args()

    img = np.asarray(Image.open(a.image).convert("RGB"), dtype=float) / 255.0
    box = tuple(int(v) for v in a.bbox.split(",")) if a.bbox else locate_bar(img)
    print(f"bar bbox (x0,y0,x1,y1) = {box}  -> {box[2]-box[0]} x {box[3]-box[1]} px")

    rows = sample_rows(img, box, a.inset)
    if a.cold_at == "bottom":
        rows = rows[::-1]  # index 0 becomes the cold end

    src = np.linspace(0.0, 1.0, len(rows))
    dst = np.linspace(0.0, 1.0, a.n)
    lut = np.stack([np.interp(dst, src, rows[:, c]) for c in range(3)], axis=1)
    lut = np.clip(lut, 0.0, 1.0)

    pal.save_lut_csv(a.out, lut)
    print(f"wrote {a.out} ({a.n} entries)")

    if a.range:
        vmin, vmax = a.range
        print(f"\n{'T':>7}  colour")
        v = np.ceil(vmin / a.tick_step) * a.tick_step
        while v <= vmax + 1e-9:
            c = pal.color_at(lut, v, vmin, vmax) * 255.0
            print(f"{v:7.1f}  #%02X%02X%02X" % tuple(int(round(x)) for x in c))
            v += a.tick_step
    print(f"\nnow run:  python3 make_scale.py --palette {a.out}")


if __name__ == "__main__":
    main()
