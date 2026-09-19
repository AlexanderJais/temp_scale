# Thermal temperature scale bar

Recreates a thermal-camera rainbow scale bar as a clean vector/raster graphic,
set in **Nimbus Sans Bold** at a size that stays readable when the bar is
inserted small into a figure.

![scale bar](out/temp_scale.png)

## Quick start

```bash
pip install matplotlib numpy pillow
sudo apt-get install fonts-urw-base35        # provides Nimbus Sans

python3 make_scale.py                        # -> out/temp_scale.{png,pdf,svg,json}
python3 verify.py out/temp_scale             # check colours against temperatures
```

Defaults: `rainbow-hc` palette, labels beside the bar, range 18.8–39.9 °C,
ticks every 2 °C, bar 90 mm tall, 14 pt labels, 600 dpi. That is a
20.7 × 108.1 mm graphic — scale it to whatever the final figure needs; the PDF
and SVG are vector, so it stays sharp.

## The two layouts

| `--labels outside` (default) | `--labels inside` |
|---|---|
| Numbers beside the bar on the page background. Keeps the bar slim and gives the crispest result when the graphic is shrunk. | Faithful to the original: numbers sit on the gradient, tick dashes bite in from both edges. Each label is automatically black or white depending on the luminance underneath it, with a contrasting outline so it survives being shrunk. |

```bash
python3 make_scale.py --labels inside --out out/temp_scale_inside
```

14 pt stays comfortably readable down to roughly a 40 mm tall insert; below
that, or if the bar sits on a busy background, bump `--font-pt` back up.

## Palettes

| name | |
|---|---|
| `rainbow-hc` (default) | The FLIR-style high-contrast rainbow. Blue and green are separated by a **dark teal node** rather than a bright cyan band, the cold ramp out of black is long (the bottom fifth of the bar), and the hot end desaturates through magenta to white. |
| `rainbow` | Blue → bright **cyan** → green → yellow → red → magenta, with a near-black navy cold end and no white cap. Shorter cold ramp. |

They look similar as thumbnails and are easy to mix up. The tell is the
24–26 °C region: bright cyan means `rainbow`, dark teal means `rainbow-hc`.

`rainbow-hc` was measured directly off the colour bar in the source figure:
the tick dashes were located by fitting a periodic model, which fixes the
temperature axis, then one colour per pixel row was sampled and converted to an
HSV schedule. The hue schedule is therefore the real thing (≤4° from the source
at every tick). Saturation and value are cleaned back up to a full gamut,
because the source was a compressed, downscaled screenshot sitting about 5%
dim — `#E70610` where the LUT plainly intends `#FF0000`.

`rainbow` is an earlier reconstruction matched by eye, not measured.

Both are defined in `palette.py` as HSV control points over normalised bar
position, and dumped to `palettes/*.csv` as `pos,R,G,B` if you'd rather read or
edit numbers.

If you have an original image and want its LUT rather than either of these:

```bash
python3 extract_palette.py original.png -o palettes/original.csv --range 18.8 39.9
python3 make_scale.py --palette palettes/original.csv
```

`extract_palette.py` finds the bar, samples one colour per row, and ignores the
tick dashes and overlaid labels by discarding near-grey pixels before taking
each row's median. Pass `--bbox x0,y0,x1,y1` if the automatic hunt guesses
wrong — worth doing whenever the bar is embedded in a larger figure, since
other panels are colourful too.

## Colours really do match temperatures

The gradient is drawn into an axes whose y-limits *are* `[vmin, vmax]`, and the
ticks are placed in those same data coordinates — so registration is exact at
any size or dpi, with no hand-tuned offsets to drift.

`make_scale.py` writes a sidecar `.json` recording the bar's pixel box and the
range. `verify.py` reads it back, samples the rendered PNG at the row each tick
should land on, and compares with the palette:

```
      T   rendered    palette        dR,dG,dB
   20.0    #010039    #01003A     +0,  +0,  -1
   ...
   38.0    #FF00FB    #FF00FC     +0,  +0,  -1
max per-channel error: 2.9/255  ->  OK (tolerance 6)
```

The residual ~3/255 is LUT interpolation, not misalignment.

Colour at each tick of the default palette and range:

| T (°C) | colour |
|---:|:---|
| 18.8 | `#00000D` |
| 20 | `#01003A` |
| 22 | `#01009E` |
| 24 | `#0018E4` |
| 26 | `#009544` |
| 28 | `#36F700` |
| 30 | `#FDFF00` |
| 32 | `#FF7600` |
| 34 | `#FF0007` |
| 36 | `#FF0066` |
| 38 | `#FF00FC` |
| 39.9 | `#FED9FF` |

## Options worth knowing

| flag | default | |
|---|---|---|
| `--range VMIN VMAX` | `18.8 39.9` | temperature span of the bar |
| `--palette` | `rainbow-hc` | palette name, or a CSV of `pos,R,G,B` |
| `--tick-step` / `--ticks` | `2` | automatic spacing, or explicit values |
| `--decimals` | `0` | decimal places on labels |
| `--font-pt` | `14` | label and unit size |
| `--height-mm` | `90` | height of the coloured bar |
| `--bar-width-mm` | fitted | defaults to whatever the labels need |
| `--labels` | `outside` | `outside` or `inside` |
| `--unit` | `°C` | header box text; `--unit ""` to omit |
| `--transparent` | off | no background, for overlaying on an image |
| `--halo-lw` | `2.6` | outline behind inside labels only; `0` disables |
| `--dpi` | `600` | raster resolution |
| `--formats` | `png pdf svg` | |
| `--out` | `out/temp_scale` | basename, no extension |

`--range` is the one to check first: 18.8–39.9 °C is what the source bar's tick
spacing works out to, so set it to your own scene's actual min/max.

## Files

```
make_scale.py       renderer (CLI)
palette.py          palette definitions, CSV load/save
extract_palette.py  recover a LUT from an original screenshot
verify.py           check rendered pixels against the palette

palettes/           each built-in palette as pos,R,G,B numbers
out/temp_scale.*            default: rainbow-hc, outside labels
out/temp_scale_inside.*     same palette, labels on the gradient
out/temp_scale_rainbow.*    the earlier `rainbow` palette, 18.6-39.6 °C
```
