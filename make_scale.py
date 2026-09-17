#!/usr/bin/env python3
"""Render a thermal-camera temperature scale bar (colour bar + tick labels).

Designed to be dropped into a figure at small physical size, so the type is set
in Nimbus Sans Bold and sized generously relative to the bar.

The colour <-> temperature mapping is exact by construction: the gradient is
drawn into an axes whose y-limits *are* [vmin, vmax], and the ticks are placed
in those same data coordinates.  ``verify.py`` checks this against the rendered
pixels.

Examples
--------
    python3 make_scale.py                                   # defaults, both layouts
    python3 make_scale.py --range 15 45 --tick-step 5
    python3 make_scale.py --labels inside --font-pt 22 --transparent
    python3 make_scale.py --palette palettes/original.csv   # exact extracted LUT
"""

from __future__ import annotations

import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.ticker  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

import palette as pal  # noqa: E402

MM = 1.0 / 25.4          # mm -> inch
PT = 1.0 / 72.0          # pt -> inch
DIGIT_EM = 0.556         # Nimbus Sans advance width of a digit, in em
FONT_FAMILY = "Nimbus Sans"


def ensure_font() -> str:
    """Make sure Nimbus Sans is registered with matplotlib; fall back if absent."""
    names = {f.name for f in fm.fontManager.ttflist}
    if FONT_FAMILY in names:
        return FONT_FAMILY
    for d in ("/usr/share/fonts/opentype/urw-base35", "/usr/share/fonts/type1/urw-base35"):
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.startswith("NimbusSans") and fn.endswith((".otf", ".ttf")):
                    fm.fontManager.addfont(os.path.join(d, fn))
    if FONT_FAMILY in {f.name for f in fm.fontManager.ttflist}:
        return FONT_FAMILY
    print(f"warning: '{FONT_FAMILY}' not found; falling back to a generic sans "
          f"(install the fonts-urw-base35 package for the real thing)")
    return "DejaVu Sans"


def fmt_label(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def default_ticks(vmin: float, vmax: float, step: float) -> list[float]:
    """Multiples of ``step`` lying inside [vmin, vmax], with a small edge inset.

    The inset keeps a label from colliding with the frame when a tick lands
    within half a line-height of either end.
    """
    first = np.ceil(vmin / step) * step
    out = []
    v = first
    while v <= vmax + 1e-9:
        out.append(float(round(v, 10)))
        v += step
    return out


def text_color_for(rgb: np.ndarray) -> tuple[str, str]:
    """Pick (text, halo) colours that stay legible on ``rgb``.

    Uses relative luminance (ITU-R BT.709) rather than a naive mean, so the
    yellow/green part of the ramp is correctly treated as 'bright'.
    """
    lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    return ("black", "white") if lum > 0.55 else ("white", "black")


def build(args) -> dict:
    family = ensure_font()
    lut = pal.get_lut(args.palette)
    cmap = ListedColormap(lut)

    vmin, vmax = args.range
    if vmax <= vmin:
        raise SystemExit("--range needs vmin < vmax")
    ticks = args.ticks if args.ticks else default_ticks(vmin, vmax, args.tick_step)

    outside = args.labels == "outside"
    fg = args.frame_color

    if not outside:
        # A label centred on the bar's very top or bottom would be sliced in
        # half by the frame, so drop ticks that cannot fit. Outside labels sit
        # clear of the bar and are left alone.
        cap_mm = args.font_pt / 72.0 * 25.4 * 0.72
        halo_mm = args.halo_lw / 72.0 * 25.4
        pad_deg = ((cap_mm + halo_mm) / 2.0 + 0.3) / args.height_mm * (vmax - vmin)
        keep = [t for t in ticks if vmin + pad_deg <= t <= vmax - pad_deg]
        if len(keep) < len(ticks):
            dropped = ", ".join(f"{t:g}" for t in ticks if t not in keep)
            print(f"note: dropped tick(s) {dropped} - too close to the ends of "
                  f"the bar to label from the inside (use --labels outside, a "
                  f"smaller --font-pt, or a wider --range)")
        ticks = keep
    if not ticks:
        raise SystemExit("no ticks left to draw; check --range / --tick-step")

    labels = [fmt_label(t, args.decimals) for t in ticks]

    # --- geometry, all in mm -------------------------------------------------
    bar_h = args.height_mm
    label_w_mm = DIGIT_EM * args.font_pt * max(len(s) for s in labels) / 72.0 * 25.4
    tick_len_mm = args.tick_len_mm
    pad_mm = args.label_pad_mm

    if args.bar_width_mm is not None:
        bar_w = args.bar_width_mm
    elif outside:
        bar_w = max(6.0, bar_h * 0.115)
    else:
        bar_w = label_w_mm + 2.0 * (tick_len_mm + pad_mm) + 1.6

    # Header box holding the unit, e.g. "degC".
    head_h = args.font_pt / 72.0 * 25.4 * 1.85 if args.unit else 0.0
    head_gap = 1.6 if args.unit else 0.0

    margin = args.margin_mm
    right_extra = (tick_len_mm + pad_mm + label_w_mm) if outside else 0.0
    # Half a label's height can overhang the bar top/bottom in outside mode.
    v_over = (args.font_pt / 72.0 * 25.4 * 0.5) if outside else 0.0

    fig_w = margin + bar_w + right_extra + margin
    fig_h = margin + v_over + bar_h + head_gap + head_h + v_over + margin

    fig = Figure(figsize=(fig_w * MM, fig_h * MM), dpi=args.dpi)
    if not args.transparent:
        fig.patch.set_facecolor(args.background)

    bar_left = margin / fig_w
    bar_bottom = (margin + v_over) / fig_h
    bar_wf = bar_w / fig_w
    bar_hf = bar_h / fig_h

    ax = fig.add_axes([bar_left, bar_bottom, bar_wf, bar_hf])

    # --- gradient ------------------------------------------------------------
    # One column, many rows, mapped straight onto the temperature axis.  Because
    # extent's y range is exactly (vmin, vmax), row <-> temperature registration
    # is exact regardless of output size or dpi.
    grad = np.linspace(vmin, vmax, len(lut)).reshape(-1, 1)
    ax.imshow(grad, aspect="auto", origin="lower", cmap=cmap,
              vmin=vmin, vmax=vmax, extent=(0.0, 1.0, vmin, vmax),
              interpolation="bilinear", rasterized=True)

    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(vmin, vmax)
    ax.set_xticks([])
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_linewidth(args.frame_lw)
        s.set_edgecolor(fg)
        s.set_zorder(5)

    tick_frac = tick_len_mm / bar_w  # tick length as a fraction of bar width

    # Column (as a fraction of bar width) that verify.py can sample to read the
    # gradient back out: clear of the tick dashes on the left and of the label
    # glyphs plus their halo in the middle.
    if outside:
        sample_x_frac = 0.5
    else:
        text_half_mm = label_w_mm / 2.0 + args.halo_lw / 72.0 * 25.4 / 2.0
        gap_lo, gap_hi = tick_len_mm, bar_w / 2.0 - text_half_mm
        if gap_hi - gap_lo < 0.25:
            print(f"warning: only {max(gap_hi - gap_lo, 0):.2f} mm of clear bar "
                  f"between the ticks and the labels; consider a wider "
                  f"--bar-width-mm or a smaller --font-pt")
            gap_lo, gap_hi = 0.0, bar_w
        sample_x_frac = (gap_lo + gap_hi) / 2.0 / bar_w

    if outside:
        # Outside labels sit on the page, not on the gradient, so 'auto'
        # contrast has nothing to adapt to: use the frame colour.
        lab_c = fg if args.label_color == "auto" else args.label_color
        ax.yaxis.tick_right()
        ax.set_yticks(ticks)
        ax.set_yticklabels(labels)
        ax.tick_params(axis="y", which="major", direction="out",
                       length=tick_len_mm / 25.4 * 72.0, width=args.tick_lw,
                       color=fg, labelcolor=lab_c,
                       labelsize=args.font_pt,
                       pad=pad_mm / 25.4 * 72.0, zorder=6)
        for lab in ax.get_yticklabels():
            lab.set_fontfamily(family)
            lab.set_fontweight(args.font_weight)
        ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    else:
        ax.set_yticks([])
        halo_lw = args.halo_lw
        for t, s in zip(ticks, labels):
            # Dashes biting in from both edges, as on the original.
            ax.plot([0.0, tick_frac], [t, t], color=fg, lw=args.tick_lw,
                    solid_capstyle="butt", zorder=6, clip_on=False)
            ax.plot([1.0 - tick_frac, 1.0], [t, t], color=fg, lw=args.tick_lw,
                    solid_capstyle="butt", zorder=6, clip_on=False)
            col = pal.color_at(lut, t, vmin, vmax)
            txt_c, halo_c = text_color_for(col)
            if args.label_color != "auto":
                txt_c = args.label_color
            txt = ax.text(0.5, t, s, ha="center", va="center",
                          fontfamily=family, fontweight=args.font_weight,
                          fontsize=args.font_pt, color=txt_c, zorder=7)
            if halo_lw > 0:
                txt.set_path_effects([pe.withStroke(linewidth=halo_lw,
                                                   foreground=halo_c),
                                      pe.Normal()])

    # --- unit header ---------------------------------------------------------
    if args.unit:
        hax = fig.add_axes([bar_left,
                            (margin + v_over + bar_h + head_gap) / fig_h,
                            bar_wf, head_h / fig_h])
        hax.set_xticks([])
        hax.set_yticks([])
        hax.set_facecolor("none" if args.transparent else args.background)
        for s in hax.spines.values():
            s.set_linewidth(args.frame_lw)
            s.set_edgecolor(fg)
        hax.text(0.5, 0.5, args.unit, ha="center", va="center",
                 fontfamily=family, fontweight=args.font_weight,
                 fontsize=args.font_pt, color=args.unit_color)

    # --- write ---------------------------------------------------------------
    base = args.out
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    matplotlib.rcParams["pdf.fonttype"] = 42   # embed TrueType, keep text real
    matplotlib.rcParams["ps.fonttype"] = 42
    matplotlib.rcParams["svg.fonttype"] = "path"  # no font dependency downstream

    written = []
    for ext in args.formats:
        path = f"{base}.{ext}"
        fig.savefig(path, dpi=args.dpi, transparent=args.transparent,
                    facecolor="none" if args.transparent else args.background)
        written.append(path)

    # Sidecar: everything verify.py needs to check the rendered pixels.
    w_px, h_px = fig_w * MM * args.dpi, fig_h * MM * args.dpi
    meta = {
        "vmin": vmin, "vmax": vmax, "ticks": ticks, "labels": labels,
        "palette": args.palette or "rainbow",
        "dpi": args.dpi, "figure_mm": [round(fig_w, 4), round(fig_h, 4)],
        "sample_x_frac": round(sample_x_frac, 6),
        "frame_lw_px": round(args.frame_lw / 72.0 * args.dpi, 3),
        "figure_px": [round(w_px, 3), round(h_px, 3)],
        # Pixel bbox of the coloured bar, top-left origin (image convention).
        "bar_bbox_px": [
            bar_left * w_px,
            (1.0 - (bar_bottom + bar_hf)) * h_px,
            (bar_left + bar_wf) * w_px,
            (1.0 - bar_bottom) * h_px,
        ],
        "outputs": written,
    }
    with open(f"{base}.json", "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--range", nargs=2, type=float, metavar=("VMIN", "VMAX"),
                   default=[18.6, 39.6],
                   help="temperature range spanned by the bar (default: 18.6 39.6)")
    p.add_argument("--ticks", nargs="*", type=float, default=None,
                   help="explicit tick temperatures (overrides --tick-step)")
    p.add_argument("--tick-step", type=float, default=2.0,
                   help="spacing of automatic ticks (default: 2)")
    p.add_argument("--decimals", type=int, default=0,
                   help="decimal places on tick labels (default: 0)")
    p.add_argument("--unit", default="°C",
                   help="text for the header box; empty string to omit")
    p.add_argument("--labels", choices=["inside", "outside"], default="inside",
                   help="labels over the gradient (as on the original) or "
                        "beside it (default: inside)")
    p.add_argument("--font-pt", type=float, default=18.0,
                   help="label/unit font size in points (default: 18)")
    p.add_argument("--font-weight", default="bold", help="default: bold")
    p.add_argument("--height-mm", type=float, default=90.0,
                   help="height of the coloured bar (default: 90)")
    p.add_argument("--bar-width-mm", type=float, default=None,
                   help="width of the coloured bar (default: fitted to the labels)")
    p.add_argument("--margin-mm", type=float, default=1.2)
    p.add_argument("--tick-len-mm", type=float, default=1.5)
    p.add_argument("--label-pad-mm", type=float, default=1.0)
    p.add_argument("--tick-lw", type=float, default=1.4)
    p.add_argument("--frame-lw", type=float, default=1.1)
    p.add_argument("--frame-color", default="#1A1A1A")
    p.add_argument("--label-color", default="auto",
                   help="'auto' picks black or white per tick for contrast")
    p.add_argument("--unit-color", default="#1A1A1A")
    p.add_argument("--halo-lw", type=float, default=2.6,
                   help="contrast outline behind inside labels; 0 disables")
    p.add_argument("--background", default="white")
    p.add_argument("--transparent", action="store_true")
    p.add_argument("--palette", default=None,
                   help="CSV palette (pos,R,G,B); omit for the built-in rainbow")
    p.add_argument("--dpi", type=int, default=600)
    p.add_argument("--formats", nargs="+", default=["png", "pdf", "svg"])
    p.add_argument("--out", default="out/temp_scale",
                   help="output basename, without extension")
    return p.parse_args(argv)


if __name__ == "__main__":
    a = parse_args()
    m = build(a)
    print(f"{m['figure_mm'][0]:.1f} x {m['figure_mm'][1]:.1f} mm @ {m['dpi']} dpi "
          f"({m['figure_px'][0]:.0f} x {m['figure_px'][1]:.0f} px)")
    print("wrote: " + ", ".join(m["outputs"]))
