# G09 panel print sheet

`panel-1to1.svg` (and `panel-1to1.pdf` when a converter was available) is a
1:1 physical-scale review sheet generated from `mechanical/panel-layout-study.json`
and `mechanical/envelope-study.scad` by `scripts/make_panel_print.py`. It is
**desk output, not the panel drawing**: every control shown is a nominal
ergonomic envelope, not an exact part, footprint or drill drawing (see the
package `AGENTS.md`). It exists to let a human run gate **G09 ("Physical
review")** locally; it never closes G09 by itself.

Regenerate after any change to the two source files:

```sh
python3 scripts/make_panel_print.py
```

The script re-derives every dimension from those sources (panel size, LCD
module offset, pot bushing radius, and the shared jack/range-switch envelope
box from the `.scad`; control positions and LCD sizes from the `.json`) and
writes deterministically — running it twice produces byte-identical output.

## Local procedure (do this with the printed sheet, not on screen)

1. **Print `panel-1to1.pdf`** (or `panel-1to1.svg` from a browser) on A3
   paper at **100% / actual size**. Explicitly disable any printer or PDF
   viewer "fit to page" / "shrink to fit" option — that is exactly the
   scaling error this sheet exists to catch.
2. **Measure the two scale-check rulers** with a ruler or tape: the sheet
   marks a 100 mm and a 50 mm bar. If either does not measure exactly, the
   print was scaled — reprint before trusting anything else on the sheet.
3. **Lay a real ID-1 card** (a credit card, 85.60 x 53.98 mm) inside the
   printed credit-card outline as a second, pocket-checkable scale
   reference. It should sit flush inside the outline.
4. **Place the real parts** (LCD module, pots, range switches, jacks) on top
   of their printed envelopes. Confirm each part's body fits inside its
   drawn envelope and its mounting/shaft point lands inside the printed
   circle or box; note any part that does not fit the nominal envelope
   (expected for at least the jacks/switches, whose exact bodies are not yet
   in the catalog).
5. **Check screen readability at arm's length**: hold or tape the sheet at
   the print's arm's-length viewing distance and confirm the printed
   "ACTIVE AREA" rectangle text/labels are legible at the size shown — this
   is a proxy for whether the real LCD's active area will read from that
   distance, not a substitute for viewing the actual module.
6. **Check control and cable clearance**: for each channel, confirm there is
   room between the pot knob, the range switch and the jack envelope for a
   hand to turn the pot and for a plugged cable to sit without fouling the
   neighbouring control. Note any channel that looks tight.
7. **Record the outcome** as desk evidence (for example under
   `design/evidence/`) — what measured correctly, what did not fit, and
   what remains to check with real hardware. Recording evidence here does
   not close G09: `manufacturing/release_guard.py` keeps it OPEN pending
   sign-off (`G10`).

## G09 evidence checklist

- [ ] Printed at verified 100% scale (both rulers measured exactly).
- [ ] Real ID-1 card matches the printed card outline.
- [ ] LCD module and active-area envelopes checked against the real module.
- [ ] Each pot/range/jack envelope checked against the real part (or noted
      as not yet fitting, with why).
- [ ] Screen readability at arm's length assessed.
- [ ] Control/cable clearance assessed per channel.
- [ ] Findings recorded as desk evidence; G09 left OPEN.

## If no SVG-to-PDF converter is available

`scripts/make_panel_print.py` uses `rsvg-convert` (Debian/Ubuntu package
`librsvg2-bin`) or, if that is absent, the `cairosvg` Python package, to
produce `panel-1to1.pdf`. If neither is installed, the script still writes
`panel-1to1.svg` and prints a note instead of failing. `panel-1to1.svg` opens
and prints directly from any modern browser at 1:1 scale as long as "fit to
page" is turned off, so the PDF is a convenience, not a requirement.
