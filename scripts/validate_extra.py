#!/usr/bin/env python3
"""Extension hook for scripts/validate.py.

Later topics add checks here so they never need to touch validate.py's
structural checks or their ordering. Each entry in EXTRA_CHECKS is a callable
`fn(check, ctx)`:
- `check(name, value, detail='')` is the same recorder validate.py's own checks
  use; calling it appends to the shared report and fails the run on a falsy
  value, exactly like a built-in check.
- `ctx` is a dict with the objects validate.py already parsed, so a hook needs
  no re-parsing: `R` (project root Path), `cat` (component records list),
  `byid` (records keyed by id), `circuit` (design/circuit.json contents),
  `parts` (circuit['parts']), `pby` (parts keyed by ref).
"""


def kicad_native_parity(check, ctx):
    # Native KiCad load + netlist parity; only runs where kicad-cli is installed.
    import kicad_check
    report, ok = kicad_check.check(write_report=False)
    if report is None:
        print('SKIP: kicad-cli not found; native KiCad load/netlist parity not run.')
        return
    p = report['netlist_parity']
    check('KiCad root sheet, PCB load and netlist parity with circuit.json', ok,
          f"sheets={report['root_schematic']['sheets']} pcb_loaded={report['pcb']['loaded']} "
          f"parity={p['result']} differences={len(p.get('differences', []))}")


def _spice_check(check, ctx):
    """#7: ngspice run of simulation/input-channel.cir, reconciled with analyze.py.

    Self-contained: skips entirely (no check recorded, so it cannot fail a
    run on a machine without ngspice) when the `ngspice` binary is not on
    PATH. When present, re-runs scripts/run_spice.py (which regenerates
    reports/spice.json) and checks its own reconciliation verdict: either the
    ngspice numbers are within 2% of analyze.py's, or spice.json carries a
    non-empty explanation for the mismatch.
    """
    import shutil

    if shutil.which("ngspice") is None:
        return
    import importlib.util
    import json

    R = ctx["R"]
    spec = importlib.util.spec_from_file_location("run_spice", R / "scripts" / "run_spice.py")
    run_spice = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_spice)
    run_spice.main()
    spice = json.loads((R / "reports" / "spice.json").read_text())
    comparison = spice.get("comparison", {})
    check(
        "ngspice run reconciled with analyze.py (#7)",
        bool(comparison.get("within_tolerance")) or bool(comparison.get("explanation")),
        json.dumps(comparison),
    )


EXTRA_CHECKS = [kicad_native_parity, _spice_check]


def _check_panel_print(check, ctx):
    """G09 panel print sheet: deterministic regeneration; sizes match the JSON."""
    import json
    import re
    import sys

    R = ctx["R"]
    sys.path.insert(0, str(R / "scripts"))
    import make_panel_print as mpp

    data = json.loads((R / "mechanical/panel-layout-study.json").read_text())
    geo = mpp.load_geometry()
    svg_a = mpp.render_svg(geo)
    svg_b = mpp.render_svg(mpp.load_geometry())
    check("Panel print SVG regenerates byte-identical", svg_a == svg_b)

    def rect_size(svg, elem_id):
        m = re.search(rf'id="{elem_id}"[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"', svg)
        return (float(m.group(1)), float(m.group(2))) if m else None

    mod = rect_size(svg_a, "module-envelope")
    check(
        "Panel print LCD module envelope matches panel-layout-study.json",
        mod is not None and list(mod) == list(data["module_envelope_mm"]),
        detail=str(mod),
    )
    active = rect_size(svg_a, "active-area")
    check(
        "Panel print active-area rectangle matches panel-layout-study.json",
        active is not None and list(active) == list(data["screen_active_mm"]),
        detail=str(active),
    )
    outline = rect_size(svg_a, "panel-outline")
    check(
        "Panel print outline matches mechanical/envelope-study.scad panel size",
        outline is not None and outline == (geo["scad"]["panel_w"], geo["scad"]["panel_h"]),
        detail=str(outline),
    )


EXTRA_CHECKS.append(_check_panel_print)


def run(check, ctx):
    for extra in EXTRA_CHECKS:
        extra(check, ctx)
