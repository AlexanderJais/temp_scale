#!/usr/bin/env python3
"""Check that the rendered bar's pixels really do encode the stated temperatures.

Reads the sidecar JSON written by ``make_scale.py``, samples the output PNG at
the pixel row each tick temperature should land on, and compares that pixel to
the palette colour for the same temperature.  Anything above a pixel or two of
error means the gradient and the ticks have drifted apart.

    python3 verify.py out/temp_scale
"""

from __future__ import annotations

import json
import sys

import numpy as np
from PIL import Image

import palette as pal


def hexs(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(round(float(c))) for c in rgb)


def main(base: str, tol: float = 6.0) -> int:
    with open(f"{base}.json") as fh:
        meta = json.load(fh)

    img = np.asarray(Image.open(f"{base}.png").convert("RGB"), dtype=float)
    x0, y0, x1, y1 = meta["bar_bbox_px"]
    vmin, vmax = meta["vmin"], meta["vmax"]
    lut = pal.get_lut(None if meta["palette"] == "rainbow" else meta["palette"])

    # make_scale.py works out which column is clear of the tick dashes and the
    # label glyphs; sample a small window around it and take the median so a
    # stray antialiased edge pixel cannot skew the result.
    frac = meta.get("sample_x_frac", 0.5)
    col = int(round(x0 + frac * (x1 - x0)))
    col = max(int(x0) + 2, min(col, int(x1) - 2))

    print(f"bar rows {y0:.1f}..{y1:.1f} px, sampling column x={col}")
    print(f"{'T':>7}  {'rendered':>9}  {'palette':>9}  {'dR,dG,dB':>14}")
    print("-" * 46)

    worst = 0.0
    for t in meta["ticks"]:
        # y1 is the bottom (vmin) row, y0 the top (vmax) row.
        frac = (t - vmin) / (vmax - vmin)
        y = y1 - frac * (y1 - y0)
        # Half the frame's stroke falls inside the bar; stay clear of it.
        inset = int(np.ceil(meta.get("frame_lw_px", 2.0) / 2.0)) + 1
        row = int(round(min(max(y, y0 + inset), y1 - inset)))
        got = np.median(img[row, col - 1:col + 2], axis=0)
        want = pal.color_at(lut, t, vmin, vmax) * 255.0
        d = got - want
        worst = max(worst, float(np.abs(d).max()))
        print(f"{t:7.1f}  {hexs(got):>9}  {hexs(want):>9}  "
              f"{d[0]:+5.0f},{d[1]:+4.0f},{d[2]:+4.0f}")

    print("-" * 46)
    ok = worst <= tol
    print(f"max per-channel error: {worst:.1f}/255  ->  {'OK' if ok else 'FAIL'} "
          f"(tolerance {tol:.0f})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "out/temp_scale"))
