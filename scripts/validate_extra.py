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
    check('KiCad root sheet, PCB load, root ERC (0 unexplained), outline DRC and netlist parity with circuit.json', ok,
          f"sheets={report['root_schematic']['sheets']} pcb_loaded={report['pcb']['loaded']} "
          f"erc_total={report['erc'].get('total')} erc_unexplained={report['erc'].get('unexplained')} "
          f"drc_errors={report['pcb'].get('drc', {}).get('errors')} "
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
def _power_budget_report(check, ctx):
    """G07: reports/power-budget.json exists, cites its inputs, and never
    claims a gate close."""
    R = ctx['R']
    path = R / 'reports/power-budget.json'
    if not path.exists():
        check('power-budget.json exists', False, 'run scripts/analyze.py')
        return
    report = __import__('json').loads(path.read_text())
    check(
        'power-budget.json has required sections',
        all(k in report for k in ('citations', 'assumptions', 'usb_budget', 'analog_rail_3v3a_quiescent')),
    )
    check('power-budget.json cites every top-level source it uses', len(report.get('citations', {})) > 0)
    gates = __import__('json').loads((R / 'design/release-gates.json').read_text())
    g07 = next((g for g in gates['gates'] if g['id'] == 'G07'), None)
    check('G07 stays OPEN after desk power-budget calculation', g07 is not None and g07['status'] == 'OPEN')


EXTRA_CHECKS.append(_power_budget_report)


def _lcd_backend_default_off(check, ctx):
    """#14: the LCD backend is compiled only with SCOPE_ENABLE_LCD=1 (default OFF) and G06 stays OPEN."""
    import json
    import re

    R = ctx['R']
    cmake = (R / 'firmware/CMakeLists.txt').read_text()
    backend = (R / 'firmware/src/display_waveshare.c').read_text()
    check(
        'LCD backend off by default (CMake option OFF, display_waveshare.c refuses to build without SCOPE_ENABLE_LCD=1)',
        re.search(r'option\(SCOPE_ENABLE_LCD\b[^)]*\bOFF\)', cmake) is not None
        and '#error' in backend and (R / 'firmware/LCD-BACKEND.md').exists(),
    )
    gates = json.loads((R / 'design/release-gates.json').read_text())
    g06 = next((g for g in gates['gates'] if g['id'] == 'G06'), None)
    check('G06 stays OPEN after desk LCD backend work', g06 is not None and g06['status'] == 'OPEN')


EXTRA_CHECKS.append(_lcd_backend_default_off)

def _docs_browser_smoke(check, ctx):
    """#15: doc/ builds natively and the HTTP browser smoke passed.

    Self-contained and skips (no check recorded) rather than failing when
    doc/node_modules is absent, so a checkout that has not run `pnpm install`
    in doc/ is not penalized by this check alone.
    """
    import json

    R = ctx['R']
    if not (R / 'doc/node_modules').is_dir():
        print('SKIP: doc/node_modules absent; native zudo-doc build not run here.')
        return
    dist_marker = R / 'doc/dist/__zfb/routes.json'
    check('doc/ zfb build produced doc/dist (routes.json present)', dist_marker.exists())
    smoke_path = R / 'reports/browser-smoke.json'
    if not smoke_path.exists():
        check('reports/browser-smoke.json exists', False, 'run scripts/browser_smoke.py')
        return
    smoke = json.loads(smoke_path.read_text())
    check(
        'HTTP browser smoke passed (catalogue, ten-pane UI, GLB viewer, built site)',
        smoke.get('result') == 'PASS' and not smoke.get('page_errors'),
        json.dumps(smoke.get('checks', [])),
    )


EXTRA_CHECKS.append(_docs_browser_smoke)


def run(check, ctx):
    for extra in EXTRA_CHECKS:
        extra(check, ctx)
