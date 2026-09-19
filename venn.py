#!/usr/bin/env python3
"""Render a two-circle Venn diagram with one region highlighted, no text.

Geometry follows the source figure: two circles of equal radius stacked
vertically, with the centre separation equal to the radius (d = r), which is
what gives that particular lens shape.

Each region is built as a single closed path of true Bezier arcs rather than by
painting one shape over another, so the fill is exact, works on a transparent
background, and stays editable as one object in Illustrator or Inkscape.

    python3 venn.py                              # overlap filled red
    python3 venn.py --region top-only
    python3 venn.py --fill-color '#2A67AE' --region top-only
    python3 venn.py --hatch xx --fill-color none --hatch-color '#C1272D'
"""

from __future__ import annotations

import argparse
import math
import os

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from matplotlib.transforms import Affine2D  # noqa: E402

MM = 1.0 / 25.4

REGIONS = ("intersection", "top-only", "bottom-only", "top", "bottom", "union", "none")


def _arc(cx: float, cy: float, r: float, t1: float, t2: float):
    """Bezier vertices/codes for the arc of a circle from t1 to t2 degrees.

    Handles either direction: matplotlib only builds counter-clockwise arcs, so
    a clockwise sweep is built backwards and reversed.  Reversing works because
    a cubic path is a MOVETO followed by CURVE4 triples, and that structure is
    symmetric under reversal.
    """
    backwards = t2 < t1
    p = Path.arc(t2, t1) if backwards else Path.arc(t1, t2)
    verts = p.vertices[::-1] if backwards else p.vertices
    verts = Affine2D().scale(r).translate(cx, cy).transform(verts)
    codes = np.full(len(verts), Path.CURVE4, dtype=Path.code_type)
    codes[0] = Path.MOVETO
    return verts, codes


def _join(*arcs) -> Path:
    """Chain arcs into one closed path (each arc after the first continues it)."""
    verts, codes = [], []
    for i, (v, c) in enumerate(arcs):
        if i:
            c = c.copy()
            c[0] = Path.LINETO  # endpoints coincide, so this adds nothing visible
        verts.append(v)
        codes.append(c)
    verts = np.concatenate(verts)
    codes = np.concatenate(codes)
    verts = np.vstack([verts, verts[:1]])
    codes = np.concatenate([codes, [Path.CLOSEPOLY]])
    return Path(verts, codes)


def region_path(region: str, r: float, d: float) -> Path | None:
    """Closed path for one region of two circles of radius r, centres d apart.

    Circles are centred at (0, +d/2) (top) and (0, -d/2) (bottom); they cross at
    (+-h, 0).  ``a`` is the half-angle those crossings subtend at each centre.
    """
    if region == "none":
        return None
    h = math.sqrt(max(r * r - (d / 2) ** 2, 0.0))
    if h == 0.0:
        raise SystemExit("circles do not overlap; --separation must be < 2")
    a = math.degrees(math.atan2(d / 2, h))  # 30 deg when d == r
    ct, cb = d / 2, -d / 2                  # centre y of top / bottom circle

    if region == "top":
        return _join(_arc(0, ct, r, 0, 360))
    if region == "bottom":
        return _join(_arc(0, cb, r, 0, 360))
    if region == "intersection":
        # Bottom of the top circle, then top of the bottom circle.
        return _join(_arc(0, ct, r, 180 + a, 360 - a),
                     _arc(0, cb, r, a, 180 - a))
    if region == "top-only":
        # Top circle's arc outside the bottom circle, then the lens's upper edge
        # traced backwards so the overlap is carved out.
        return _join(_arc(0, ct, r, -a, 180 + a),
                     _arc(0, cb, r, 180 - a, a))
    if region == "bottom-only":
        return _join(_arc(0, cb, r, 180 - a, 360 + a),
                     _arc(0, ct, r, -a, a - 180))
    if region == "union":
        return _join(_arc(0, ct, r, -a, 180 + a),
                     _arc(0, cb, r, 180 - a, 360 + a))
    raise SystemExit(f"unknown region {region!r}; choose from {', '.join(REGIONS)}")


def build(args) -> dict:
    r = args.radius_mm
    d = args.separation * r
    path = region_path(args.region, r, d)

    # Bounding box of the two circles, plus room for the stroke.
    half_w = r + args.stroke_mm
    half_h = r + d / 2 + args.stroke_mm
    pad = args.margin_mm
    fig_w, fig_h = 2 * (half_w + pad), 2 * (half_h + pad)
    if args.horizontal:
        fig_w, fig_h = fig_h, fig_w

    fig = Figure(figsize=(fig_w * MM, fig_h * MM), dpi=args.dpi)
    if not args.transparent:
        fig.patch.set_facecolor(args.background)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_aspect("equal")
    ax.axis("off")
    if args.transparent:
        ax.patch.set_alpha(0.0)

    rot = Affine2D().rotate_deg(-90) if args.horizontal else Affine2D()
    tf = rot + ax.transData

    if path is not None:
        fill = None if args.fill_color.lower() == "none" else args.fill_color
        ax.add_patch(PathPatch(
            path, transform=tf, facecolor=fill or "none", edgecolor="none",
            alpha=args.alpha, zorder=1, linewidth=0.0))
        if args.hatch:
            # matplotlib draws hatching in the patch's edge colour, so the hatch
            # rides on its own zero-width patch to keep it independent of the
            # fill and of the circle outlines.
            hp = PathPatch(path, transform=tf, facecolor="none",
                           edgecolor=args.hatch_color, hatch=args.hatch,
                           linewidth=0.0, zorder=2)
            ax.add_patch(hp)

    lw_pt = args.stroke_mm / 25.4 * 72.0
    for cy in (d / 2, -d / 2):
        ax.add_patch(PathPatch(
            _join(_arc(0, cy, r, 0, 360)), transform=tf, facecolor="none",
            edgecolor=args.stroke_color, linewidth=lw_pt, zorder=3))

    lim_w, lim_h = half_w + pad, half_h + pad
    if args.horizontal:
        ax.set_xlim(-lim_h, lim_h)
        ax.set_ylim(-lim_w, lim_w)
    else:
        ax.set_xlim(-lim_w, lim_w)
        ax.set_ylim(-lim_h, lim_h)

    base = args.out
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["svg.fonttype"] = "path"
    written = []
    for ext in args.formats:
        p = f"{base}.{ext}"
        fig.savefig(p, dpi=args.dpi, transparent=args.transparent,
                    facecolor="none" if args.transparent else args.background)
        written.append(p)
    return {"figure_mm": (round(fig_w, 3), round(fig_h, 3)), "outputs": written}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", choices=REGIONS, default="intersection",
                   help="which region to fill (default: intersection, i.e. the "
                        "overlap)")
    p.add_argument("--fill-color", default="#C1272D",
                   help="fill colour, or 'none' for hatch-only (default: red)")
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--hatch", default="",
                   help="matplotlib hatch, e.g. 'xx' for the crosshatch used in "
                        "the source figure; empty for a solid fill")
    p.add_argument("--hatch-color", default="#1E1E1E")
    p.add_argument("--radius-mm", type=float, default=20.0)
    p.add_argument("--separation", type=float, default=1.0,
                   help="centre separation as a multiple of the radius; the "
                        "source figure uses 1.0 (default: 1.0)")
    p.add_argument("--stroke-mm", type=float, default=0.5)
    p.add_argument("--stroke-color", default="#1E1E1E")
    p.add_argument("--margin-mm", type=float, default=0.5)
    p.add_argument("--horizontal", action="store_true",
                   help="lay the circles side by side instead of stacked")
    p.add_argument("--background", default="white")
    p.add_argument("--transparent", action="store_true")
    p.add_argument("--dpi", type=int, default=600)
    p.add_argument("--formats", nargs="+", default=["png", "pdf", "svg"])
    p.add_argument("--out", default="out/venn")
    return p.parse_args(argv)


if __name__ == "__main__":
    a = parse_args()
    m = build(a)
    print(f"{m['figure_mm'][0]} x {m['figure_mm'][1]} mm")
    print("wrote: " + ", ".join(m["outputs"]))
