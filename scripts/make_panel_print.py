#!/usr/bin/env python3
"""Generate the G09 1:1 printable panel review sheet.

Reads mechanical/panel-layout-study.json (control positions, LCD module and
active-area sizes) and mechanical/envelope-study.scad (panel sheet size, LCD
module offset, pot bushing radius, and the shared jack/range-switch envelope
box) so that no dimension here is invented separately from those two files.
The HOLD/LINK button positions are lifted from the existing
doc/public/assets/panel-study.svg for the same reason.

Output: mechanical/print/panel-1to1.svg, drawn at exact 1:1 physical scale in
mm on an A3 sheet, plus mechanical/print/panel-1to1.pdf when rsvg-convert or
cairosvg is available. This is a REVIEW artifact only: it does not close G09
and is not proof of fit (see AGENTS.md).
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

R = Path(__file__).resolve().parents[1]
JSON_PATH = R / "mechanical/panel-layout-study.json"
SCAD_PATH = R / "mechanical/envelope-study.scad"
STUDY_SVG_PATH = R / "doc/public/assets/panel-study.svg"
OUT_DIR = R / "mechanical/print"
SVG_OUT = OUT_DIR / "panel-1to1.svg"
PDF_OUT = OUT_DIR / "panel-1to1.pdf"

# ISO/IEC 7810 ID-1 card, used as a pocket-checkable scale reference.
CREDIT_CARD_MM = (85.60, 53.98)

# A3 landscape. The 250x180mm panel plus rulers/card/labels does not fit an
# A4 sheet without overlapping the panel; A3 leaves them clear margin room.
PAGE_W, PAGE_H = 420.0, 297.0


def fnum(x):
    """Deterministic, compact float formatting (no trailing zeros)."""
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def load_scad_geometry(scad_text):
    cube_re = re.compile(r"(?:translate\(\[([^\]]+)\]\))?cube\(\[([^\]]+)\]\)")
    cubes = cube_re.findall(scad_text)
    if len(cubes) < 3:
        raise ValueError("envelope-study.scad: expected 3 cube() calls (panel, module, switch/jack body)")

    def nums(s):
        return [float(x) for x in s.split(",")]

    panel_w, panel_h, _ = nums(cubes[0][1])
    mod_ox, mod_oy, _ = nums(cubes[1][0])
    mod_w, mod_h, _ = nums(cubes[1][1])
    body_w, body_h, _ = nums(cubes[2][1])
    m = re.search(r"cylinder\(h=[\d.]+,r=([\d.]+)\)", scad_text)
    if not m:
        raise ValueError("envelope-study.scad: pot cylinder radius not found")
    pot_r = float(m.group(1))
    return {
        "panel_w": panel_w,
        "panel_h": panel_h,
        "mod_ox": mod_ox,
        "mod_oy": mod_oy,
        "mod_w": mod_w,
        "mod_h": mod_h,
        "body_w": body_w,
        "body_h": body_h,
        "pot_r": pot_r,
    }


def load_button_centres(study_svg_text):
    """HOLD/LINK button envelope centres, reused from the existing study SVG."""
    matches = re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="3" fill="#be5f3c"/>', study_svg_text)
    if len(matches) != 2:
        raise ValueError("doc/public/assets/panel-study.svg: expected exactly 2 HOLD/LINK marker circles")
    return [(float(cx), float(cy)) for cx, cy in matches]


def load_geometry():
    data = json.loads(JSON_PATH.read_text())
    scad = load_scad_geometry(SCAD_PATH.read_text())
    if list(data["module_envelope_mm"]) != [scad["mod_w"], scad["mod_h"]]:
        raise ValueError("panel-layout-study.json module_envelope_mm disagrees with envelope-study.scad")
    hold_xy, link_xy = load_button_centres(STUDY_SVG_PATH.read_text())
    return {
        "data": data,
        "scad": scad,
        "hold_xy": hold_xy,
        "link_xy": link_xy,
    }


def ruler(x, y, length_mm, label):
    """A horizontal ruler with 10mm major ticks and 5mm minor ticks."""
    parts = [f'<g id="ruler-{label.replace(" ", "-")}">']
    parts.append(
        f'<line x1="{fnum(x)}" y1="{fnum(y)}" x2="{fnum(x + length_mm)}" y2="{fnum(y)}" '
        f'stroke="#183535" stroke-width="0.3"/>'
    )
    mm = 0.0
    while mm <= length_mm + 1e-6:
        major = abs(mm % 10) < 1e-6
        tick_h = 4.0 if major else 2.0
        parts.append(
            f'<line x1="{fnum(x + mm)}" y1="{fnum(y)}" x2="{fnum(x + mm)}" y2="{fnum(y - tick_h)}" '
            f'stroke="#183535" stroke-width="{"0.3" if major else "0.15"}"/>'
        )
        if major:
            parts.append(
                f'<text x="{fnum(x + mm)}" y="{fnum(y - 5.2)}" font-size="2.2" '
                f'font-family="DejaVu Sans,sans-serif" fill="#183535" text-anchor="middle">{int(round(mm))}</text>'
            )
        mm += 5.0
    parts.append(
        f'<text x="{fnum(x)}" y="{fnum(y + 6.5)}" font-size="3" font-family="DejaVu Sans,sans-serif" '
        f'fill="#183535" text-anchor="start">{label} SCALE CHECK — must measure exactly {int(length_mm)} mm</text>'
    )
    parts.append("</g>")
    return "\n".join(parts)


def render_svg(geo):
    d = geo["data"]
    s = geo["scad"]
    panel_w, panel_h = s["panel_w"], s["panel_h"]
    px0 = (PAGE_W - panel_w) / 2.0
    py0 = (PAGE_H - panel_h) / 2.0
    active_w, active_h = d["screen_active_mm"]
    mod_w, mod_h = s["mod_w"], s["mod_h"]
    active_x = px0 + s["mod_ox"] + (mod_w - active_w) / 2.0
    active_y = py0 + s["mod_oy"] + (mod_h - active_h) / 2.0
    body_w, body_h, pot_r = s["body_w"], s["body_h"], s["pot_r"]

    g = []
    g.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fnum(PAGE_W)}mm" height="{fnum(PAGE_H)}mm" '
        f'viewBox="0 0 {fnum(PAGE_W)} {fnum(PAGE_H)}">'
    )
    g.append(f'<rect width="{fnum(PAGE_W)}" height="{fnum(PAGE_H)}" fill="#ffffff"/>')

    # Page-corner registration marks.
    for cx, cy in [(6, 6), (PAGE_W - 6, 6), (PAGE_W - 6, PAGE_H - 6), (6, PAGE_H - 6)]:
        g.append(
            f'<g stroke="#183535" stroke-width="0.25">'
            f'<line x1="{fnum(cx - 4)}" y1="{fnum(cy)}" x2="{fnum(cx + 4)}" y2="{fnum(cy)}"/>'
            f'<line x1="{fnum(cx)}" y1="{fnum(cy - 4)}" x2="{fnum(cx)}" y2="{fnum(cy + 4)}"/>'
            f"</g>"
        )

    # Title block (top margin, above the panel outline).
    g.append(
        f'<text x="{fnum(px0)}" y="14" font-size="6" font-family="DejaVu Sans,sans-serif" '
        f'fill="#183535" text-anchor="start" font-weight="bold">ZUDO / SCOPE 10 — G09 PANEL PRINT SHEET</text>'
    )
    g.append(
        f'<text x="{fnum(px0)}" y="22" font-size="3.4" font-family="DejaVu Sans,sans-serif" '
        f'fill="#be5f3c" text-anchor="start" font-weight="bold">PRINT AT 100% / DO NOT SCALE</text>'
    )
    g.append(
        f'<text x="{fnum(px0)}" y="28" font-size="3.4" font-family="DejaVu Sans,sans-serif" '
        f'fill="#be5f3c" text-anchor="start" font-weight="bold">REVIEW ONLY — NOT FABRICATION</text>'
    )
    g.append(
        f'<text x="{fnum(PAGE_W - px0)}" y="36" font-size="3" font-family="DejaVu Sans,sans-serif" '
        f'fill="#617673" text-anchor="end">Generated by scripts/make_panel_print.py from mechanical/panel-layout-study.json</text>'
    )
    g.append(
        f'<text x="{fnum(PAGE_W - px0)}" y="42" font-size="3" font-family="DejaVu Sans,sans-serif" '
        f'fill="#617673" text-anchor="end">Sheet: A3 landscape {fnum(PAGE_W)} x {fnum(PAGE_H)} mm. '
        f'Panel outline: {fnum(panel_w)} x {fnum(panel_h)} mm at 1:1.</text>'
    )
    g.append(
        f'<text x="{fnum(PAGE_W - px0)}" y="48" font-size="3" font-family="DejaVu Sans,sans-serif" '
        f'fill="#617673" text-anchor="end">Nominal ergonomic envelopes only — not exact parts, not a drill drawing.</text>'
    )

    # Panel outline.
    g.append(
        f'<rect id="panel-outline" x="{fnum(px0)}" y="{fnum(py0)}" width="{fnum(panel_w)}" height="{fnum(panel_h)}" '
        f'fill="none" stroke="#183535" stroke-width="0.4" stroke-dasharray="2,1"/>'
    )
    g.append(
        f'<text x="{fnum(px0)}" y="{fnum(py0 - 2)}" font-size="3" font-family="DejaVu Sans,sans-serif" '
        f'fill="#183535" text-anchor="start">PANEL OUTLINE {fnum(panel_w)} x {fnum(panel_h)} mm '
        f'(nominal envelope, not exact fit)</text>'
    )

    # LCD module envelope and active-area rectangle.
    mx = px0 + s["mod_ox"]
    my = py0 + s["mod_oy"]
    g.append(
        f'<rect id="module-envelope" x="{fnum(mx)}" y="{fnum(my)}" width="{fnum(mod_w)}" height="{fnum(mod_h)}" '
        f'fill="none" stroke="#617673" stroke-width="0.3" stroke-dasharray="1,1"/>'
    )
    g.append(
        f'<text x="{fnum(mx)}" y="{fnum(my - 1.2)}" font-size="2.4" font-family="DejaVu Sans,sans-serif" '
        f'fill="#617673" text-anchor="start">LCD MODULE ENVELOPE {fnum(mod_w)} x {fnum(mod_h)} mm</text>'
    )
    g.append(
        f'<rect id="active-area" x="{fnum(active_x)}" y="{fnum(active_y)}" width="{fnum(active_w)}" height="{fnum(active_h)}" '
        f'fill="none" stroke="#183535" stroke-width="0.35"/>'
    )
    g.append(
        f'<text x="{fnum(active_x + active_w / 2)}" y="{fnum(active_y + active_h / 2)}" font-size="2.4" '
        f'font-family="DejaVu Sans,sans-serif" fill="#183535" text-anchor="middle">ACTIVE AREA {fnum(active_w)} x {fnum(active_h)} mm</text>'
    )
    g.append(
        f'<text x="{fnum(active_x + active_w / 2)}" y="{fnum(active_y + active_h / 2 + 3.2)}" font-size="2" '
        f'font-family="DejaVu Sans,sans-serif" fill="#be5f3c" text-anchor="middle">centring: {d["active_centring"]}</text>'
    )

    # Per-channel controls.
    for ch in d["channels"]:
        n = ch["channel"]
        px, py = ch["pot_axis_mm"]
        px, py = px0 + px, py0 + py
        rx, ry = ch["range_envelope_centre_mm"]
        rx, ry = px0 + rx, py0 + ry
        jx, jy = ch["jack_envelope_centre_mm"]
        jx, jy = px0 + jx, py0 + jy

        g.append(
            f'<g id="channel-{n}">'
            f'<circle cx="{fnum(px)}" cy="{fnum(py)}" r="{fnum(pot_r)}" fill="none" stroke="#183535" stroke-width="0.3"/>'
            f'<circle cx="{fnum(px)}" cy="{fnum(py)}" r="{fnum(pot_r * 0.85)}" fill="none" stroke="#748582" stroke-width="0.2"/>'
            f'<text x="{fnum(px)}" y="{fnum(py + pot_r + 3.4)}" font-size="2.4" font-family="DejaVu Sans,sans-serif" '
            f'fill="#183535" text-anchor="middle">CH{n:02d} TIME</text>'
            f'<rect x="{fnum(rx - body_w / 2)}" y="{fnum(ry - body_h / 2)}" width="{fnum(body_w)}" height="{fnum(body_h)}" '
            f'rx="1" fill="none" stroke="#617673" stroke-width="0.25"/>'
            f'<text x="{fnum(rx)}" y="{fnum(ry - body_h / 2 - 1.2)}" font-size="2" font-family="DejaVu Sans,sans-serif" '
            f'fill="#617673" text-anchor="middle">RANGE</text>'
            f'<rect x="{fnum(jx - body_w / 2)}" y="{fnum(jy - body_h / 2)}" width="{fnum(body_w)}" height="{fnum(body_h)}" '
            f'rx="1" fill="none" stroke="#617673" stroke-width="0.25"/>'
            f'<text x="{fnum(jx)}" y="{fnum(jy - body_h / 2 - 1.2)}" font-size="2" font-family="DejaVu Sans,sans-serif" '
            f'fill="#617673" text-anchor="middle">JACK</text>'
            f"</g>"
        )

    # HOLD/LINK buttons, positions reused from the existing panel study SVG.
    for label, (bx, by) in [("HOLD", geo["hold_xy"]), ("LINK", geo["link_xy"])]:
        g.append(
            f'<circle cx="{fnum(px0 + bx)}" cy="{fnum(py0 + by)}" r="3" fill="none" stroke="#be5f3c" stroke-width="0.3"/>'
        )
        g.append(
            f'<text x="{fnum(px0 + bx)}" y="{fnum(py0 + by + 6.5)}" font-size="2.4" font-family="DejaVu Sans,sans-serif" '
            f'fill="#183535" text-anchor="middle">{label}</text>'
        )

    # Bottom margin: scale-check rulers and a credit-card reference box, laid
    # out side by side (not stacked) so they fit the margin below the panel.
    bottom_y = py0 + panel_h + 22
    g.append(ruler(px0, bottom_y, 100.0, "100 mm"))
    g.append(ruler(px0 + 130, bottom_y, 50.0, "50 mm"))

    card_x = px0 + 210
    card_y = py0 + panel_h + 3
    card_w, card_h = CREDIT_CARD_MM
    g.append(
        f'<rect id="credit-card-reference" x="{fnum(card_x)}" y="{fnum(card_y)}" width="{fnum(card_w)}" height="{fnum(card_h)}" '
        f'rx="3" fill="none" stroke="#183535" stroke-width="0.35"/>'
    )
    g.append(
        f'<text x="{fnum(card_x + card_w / 2)}" y="{fnum(card_y + card_h / 2)}" font-size="2.6" '
        f'font-family="DejaVu Sans,sans-serif" fill="#183535" text-anchor="middle">ISO/IEC 7810 ID-1 CARD</text>'
    )
    g.append(
        f'<text x="{fnum(card_x + card_w / 2)}" y="{fnum(card_y + card_h / 2 + 4)}" font-size="2.6" '
        f'font-family="DejaVu Sans,sans-serif" fill="#183535" text-anchor="middle">{fnum(card_w)} x {fnum(card_h)} mm — lay a real card here</text>'
    )

    g.append("</svg>")
    return "\n".join(g) + "\n"


def convert_pdf(svg_path, pdf_path):
    """Best-effort SVG->PDF via rsvg-convert or cairosvg. Never fatal."""
    if shutil.which("rsvg-convert"):
        subprocess.run(
            ["rsvg-convert", "-f", "pdf", "-o", str(pdf_path), str(svg_path)],
            check=True,
        )
        return "rsvg-convert"
    try:
        import cairosvg  # noqa: PLC0415

        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
        return "cairosvg"
    except Exception:
        return None


def main():
    geo = load_geometry()
    svg_text = render_svg(geo)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SVG_OUT.write_text(svg_text)
    converter = convert_pdf(SVG_OUT, PDF_OUT)
    if converter:
        print(f"Wrote {SVG_OUT} and {PDF_OUT} (PDF via {converter})")
    else:
        print(
            f"Wrote {SVG_OUT}. No SVG->PDF converter found (install python cairosvg "
            f"or the librsvg2-bin rsvg-convert CLI) — see mechanical/print/README.md."
        )


if __name__ == "__main__":
    sys.exit(main())
