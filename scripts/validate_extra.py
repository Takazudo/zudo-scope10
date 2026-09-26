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
    reports/spice.json) and checks its own reconciliation verdict: the
    ngspice numbers must be within 2% of analyze.py's. spice.json's
    `explanation` is a fixed methodology note, never a mismatch waiver.
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
        bool(comparison.get("within_tolerance")),
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


def _acceptance_csv(check, ctx):
    """#29/#32: manufacturing/acceptance-results.csv has no column shift, and
    every row is still NOT_RUN because no physical measurement has been
    performed yet. Allowed `result` values, per LOCAL-HANDOFF.md's bench
    section (around lines 151-156): NOT_RUN, PASS, FAIL, BLOCKED.
    """
    import csv

    R = ctx['R']
    ALLOWED_RESULTS = {'NOT_RUN', 'PASS', 'FAIL', 'BLOCKED'}
    path = R / 'manufacturing/acceptance-results.csv'
    with path.open(newline='') as f:
        reader = csv.DictReader(f)
        header_width = len(reader.fieldnames)
        rows = list(reader)

    check(
        'acceptance-results.csv rows match header width (no unnamed/None field)',
        all(None not in row and len(row) == header_width for row in rows),
    )
    check(
        'acceptance-results.csv result values are all allowed',
        all(row.get('result') in ALLOWED_RESULTS for row in rows),
        detail=str(sorted({row.get('result') for row in rows})),
    )
    check(
        'acceptance-results.csv PASS/FAIL rows cite evidence, operator and date',
        all(
            (row.get('evidence_file') and (R / row['evidence_file']).exists()
             and row.get('operator') and row.get('date'))
            for row in rows if row.get('result') in ('PASS', 'FAIL')
        ),
    )
    # No physical measurement has been performed yet (see LOCAL-HANDOFF.md's
    # G04 bench section). Once a real bench result lands, this assertion must
    # be deliberately updated alongside evidence from G04/G05/G07.
    check(
        'acceptance-results.csv: every row is still NOT_RUN (no physical measurement performed)',
        all(row.get('result') == 'NOT_RUN' for row in rows),
    )


EXTRA_CHECKS.append(_acceptance_csv)


def _firmware_pane_rects(R):
    """Pane rects from the real scope_render.c, compiled for the host with a stub display port."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    cc = shutil.which('cc') or shutil.which('gcc')
    if not cc:
        return None, 'a host C compiler is required to read the firmware pane rects'
    src = R / 'firmware/src'
    probe = (
        '#include "scope_render.h"\n#include "display_port.h"\n#include <stdio.h>\n'
        'bool scope_display_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *px)'
        '{(void)x;(void)y;(void)w;(void)h;(void)px;return true;}\n'
        'int main(void){for(unsigned p=0;p<SCOPE_CHANNELS;p++){scope_rect r=scope_pane_rect(p);'
        'printf("%u %u %u %u\\n",r.x,r.y,r.w,r.h);}return 0;}\n'
    )
    with tempfile.TemporaryDirectory() as t:
        c = Path(t) / 'probe.c'
        exe = Path(t) / 'probe'
        c.write_text(probe)
        build = subprocess.run([cc, '-std=c11', '-I' + str(src), str(c), str(src / 'scope_render.c'),
                                str(src / 'scope_core.c'), '-lm', '-o', str(exe)], capture_output=True, text=True)
        if build.returncode:
            return None, build.stderr.strip()
        out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout
    return [tuple(int(v) for v in line.split()) for line in out.splitlines()], ''


def _rows_by_bank(xy):
    """{channel: (bank, row)}: bank 0 = left, 1 = right; row = top-to-bottom rank within the bank."""
    xs = sorted({x for x, _ in xy.values()})
    if len(xs) != 2:
        return None
    out = {}
    for bank, bx in enumerate(xs):
        members = sorted((y, ch) for ch, (x, y) in xy.items() if x == bx)
        if len({y for y, _ in members}) != len(members):
            return None  # two channels share a row: no top-to-bottom order to compare
        for row, (_, ch) in enumerate(members):
            out[ch] = (bank, row)
    return out


def _pane_numbering_parity(check, ctx):
    """#26/#34: firmware panes, simulator panes and physical control banks share one numbering.

    Column-major: CH1..CH5 are the left bank / left pane column top to bottom, CH6..CH10 the
    right. A contradiction in any source fails the check; the firmware is never adapted to it.
    """
    import json
    import re

    R = ctx['R']
    want = {ch: ((ch - 1) // 5, (ch - 1) % 5) for ch in range(1, 11)}
    details = []

    rects, err = _firmware_pane_rects(R)
    fw = _rows_by_bank({i + 1: (r[0], r[1]) for i, r in enumerate(rects)}) if rects else None
    details.append(f'firmware={fw if fw else err}')

    js = (R / 'doc/public/prototype/scope-ui.js').read_text()
    m = re.search(r'x=\(i<(\d+)\?(\d+):(\d+)\),y=\(i%(\d+)\)\*(\d+)', js)
    bank_dom = re.search(r"querySelector\(i<(\d+)\?'#left':'#right'\)", js)
    sim = None
    if m and bank_dom:
        split, x0, x1, mod, h = map(int, m.groups())
        sim = _rows_by_bank({i + 1: (x0 if i < split else x1, (i % mod) * h) for i in range(10)})
        dom = {i + 1: 0 if i < int(bank_dom.group(1)) else 1 for i in range(10)}
        if sim and any(sim[ch][0] != dom[ch] for ch in dom):
            sim = None
            details.append('simulator pane column disagrees with its control-bank DOM placement')
    details.append(f'simulator={sim}')

    panel = json.loads((R / 'mechanical/panel-layout-study.json').read_text())
    keys = ('jack_envelope_centre_mm', 'pot_axis_mm', 'range_envelope_centre_mm')
    by_ch = {c['channel']: c for c in panel['channels']}
    phys = None
    if sorted(by_ch) == list(range(1, 11)):
        mid = sum(by_ch[ch]['pot_axis_mm'][0] for ch in by_ch) / 10.0
        sides = {ch: {c[k][0] < mid for k in keys} for ch, c in by_ch.items()}
        if all(len(v) == 1 for v in sides.values()):
            # SVG / panel-study y grows downward, so ascending y is top to bottom.
            phys = _rows_by_bank({ch: (0 if sides[ch] == {True} else 1, c['pot_axis_mm'][1]) for ch, c in by_ch.items()})
        else:
            details.append('a channel has jack/pot/RANGE envelopes on both sides of the panel')
    details.append(f'panel={phys}')

    check('Pane numbering parity: firmware panes, simulator and panel control banks are column-major '
          '(CH1-5 left, CH6-10 right, same top-to-bottom order)',
          fw == want and sim == want and phys == want, '; '.join(details))


EXTRA_CHECKS.append(_pane_numbering_parity)


def run(check, ctx):
    for extra in EXTRA_CHECKS:
        extra(check, ctx)
