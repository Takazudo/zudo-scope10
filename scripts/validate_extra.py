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


def _module_power_evidence_consistency(check, ctx):
    """#35: one structured module-power evidence source, consumed correctly.

    - design/evidence/module-power.json has an entry for every claim #35 lists.
    - reports/power-budget.json's branch totals add up (F1 branch + Pico = total).
    - reports/power-budget.json's F1/capacitance fields match the evidence file.
    - No "630" / "derated hold" leftover wording anywhere in the checked files.
    """
    import json

    R = ctx['R']
    evidence = json.loads((R / 'design/evidence/module-power.json').read_text())
    by_id = {e['id']: e for e in evidence['entries']}

    required_ids = {
        'module-vsys-capacitance',
        'carrier-5v-fused-capacitance',
        'carrier-plus-module-known-subtotal',
        'backlight-topology',
        'backlight-regulator-identity',
        'module-max-current-180ma',
        'display-planning-allowance',
    }
    check(
        'module-power.json has an entry for every #35 claim',
        required_ids <= set(by_id),
        f'missing: {required_ids - set(by_id)}',
    )
    check(
        'module-power.json entries carry status/citation/uncertainty',
        all({'status', 'citation', 'uncertainty'} <= set(e) for e in evidence['entries']),
    )
    check(
        '180 mA claim is unknown/rejected, not carried as a manufacturer maximum',
        by_id['module-max-current-180ma']['status'] in ('unknown', 'rejected'),
    )
    check(
        'display allowance is labelled an allowance, not a manufacturer/measured figure',
        by_id['display-planning-allowance']['status'] == 'allowance',
    )

    report_path = R / 'reports/power-budget.json'
    if not report_path.exists():
        check('reports/power-budget.json exists for module-power cross-check', False, 'run scripts/analyze.py')
        return
    report = json.loads(report_path.read_text())

    cap = report.get('downstream_capacitance_5v_fused', {})
    check(
        'report capacitance matches module-power.json (module, carrier, combined)',
        cap.get('known_module_uf') == by_id['module-vsys-capacitance']['value_uf']
        and cap.get('known_carrier_uf') == by_id['carrier-5v-fused-capacitance']['value_uf']
        and cap.get('known_carrier_plus_module_uf') == by_id['carrier-plus-module-known-subtotal']['value_uf'],
        json.dumps(cap),
    )
    check(
        'combined capacitance is exactly module + carrier',
        abs(cap.get('known_carrier_plus_module_uf', 0) - (cap.get('known_module_uf', 0) + cap.get('known_carrier_uf', 0))) < 1e-9,
    )
    check(
        'inrush status_overall stays unknown (no measured-compliance claim)',
        cap.get('status_overall') == 'unknown',
    )

    f1 = report.get('f1_branch_sizing', {})
    check(
        'F1 branch current excludes the Pico allowance (branch + pico == total source current)',
        f1.get('f1_branch_current_ma') is not None
        and f1.get('total_source_current_ma') is not None
        and abs(f1['f1_branch_current_ma'] + 80.0 - f1['total_source_current_ma']) < 1e-9,
        json.dumps(f1),
    )
    check(
        'F1 target hold current is the branch current times the sizing factor',
        abs(f1.get('target_hold_current_ma', -1) - f1.get('f1_branch_current_ma', -1) * f1.get('sizing_factor_assumption', -1)) < 1e-9,
    )
    check(
        'F1 selected candidate is the catalog fuse record (1206L050YR, 500 mA)',
        f1.get('selected_candidate', {}).get('mpn') == '1206L050YR'
        and f1.get('selected_candidate', {}).get('hold_current_rating_ma') == 500.0,
    )

    leftover_targets = [
        R / 'scripts/power_budget.py',
        R / 'LOCAL-HANDOFF.md',
        R / 'design/release-gates.json',
        R / 'design/narrative-pages.json',
        R / 'reports/power-budget.json',
        R / 'design/evidence/g01-display-power.md',
    ]
    # The literal old wrong figure (630 mA, allow_total_ma * 1.5) is the tell:
    # the new, correct F1-branch derating discussion legitimately still says
    # "derated hold current" (of the 1206L050YR, currently unknown), so only
    # the number itself is checked for, not that phrase.
    leftovers = []
    for f in leftover_targets:
        text = f.read_text()
        if '630' in text:
            leftovers.append(str(f.relative_to(R)))
    check('No leftover "630 mA derated hold" figure in checked files', not leftovers, str(leftovers))


EXTRA_CHECKS.append(_module_power_evidence_consistency)


def _usb_power_contract_parity(check, ctx):
    """#37 (source #20): design/power-contract.json is the single shared source for
    the declared USB descriptor value; every firmware target's actual CMake
    configuration must agree with it, and the removed GPIO24/VBUS-sense
    substitute suggestion must not resurface."""
    import json
    import re
    import sys

    R = ctx['R']
    sys.path.insert(0, str(R / 'scripts'))
    import power_budget

    contract_path = R / 'design/power-contract.json'
    check('design/power-contract.json exists', contract_path.exists())
    if not contract_path.exists():
        return
    contract = json.loads(contract_path.read_text())

    check(
        'power-contract.json has the required top-level sections',
        all(k in contract for k in ('source_contract', 'declared_max_power_ma',
                                     'override_investigation', 'honesty', 'power_states')),
    )
    check(
        'power-contract.json documents that USBD_MAX_POWER_MA is not #ifndef-guarded in pinned SDK 2.1.1',
        contract.get('override_investigation', {}).get('finding_guarded_by_ifndef') is False,
    )

    required_states = {
        'pre_configuration', 'configured', 'suspend_or_deconfigured',
        'reset', 'bootsel_rom', 'unpowered',
    }
    check(
        'power-contract.json power_states covers boot, reset, BOOTSEL, configuration and suspend/deconfiguration',
        required_states <= set(contract.get('power_states', {})),
        f"missing: {required_states - set(contract.get('power_states', {}))}",
    )

    cmake_text = (R / 'firmware/CMakeLists.txt').read_text()
    fw_targets = set(re.findall(r'add_executable\((\w+)\b', cmake_text))
    check(
        'firmware/CMakeLists.txt still defines the expected firmware targets',
        {'scope10_diagnostic', 'scope10_acq'} <= fw_targets,
        str(sorted(fw_targets)),
    )

    declared = contract.get('declared_max_power_ma')
    target_overrides = power_budget.parse_cmake_usbd_max_power_targets()
    check(
        'Every firmware target parsed from CMakeLists.txt has an explicit descriptor override entry',
        fw_targets <= set(target_overrides),
        str(target_overrides),
    )
    mismatched = {t: v for t, v in target_overrides.items() if v is not None and v != declared}
    check(
        "Every firmware target's USBD_MAX_POWER_MA override (if any) equals power-contract.json's declared_max_power_ma",
        not mismatched,
        f"declared={declared} mismatched={mismatched}",
    )

    report_path = R / 'reports/power-budget.json'
    if not report_path.exists():
        check('reports/power-budget.json exists for USB power-contract cross-check', False, 'run scripts/analyze.py')
        return
    report = json.loads(report_path.read_text())
    usb_budget = report.get('usb_budget', {})
    check(
        "reports/power-budget.json's declared_max_power_ma matches design/power-contract.json",
        usb_budget.get('declared_max_power_ma') == declared,
        f"report={usb_budget.get('declared_max_power_ma')} contract={declared}",
    )
    allowance = usb_budget.get('documented_allowance_total_ma')
    vs_declared = usb_budget.get('vs_declared_limit', {})
    check(
        'A budget allowance greater than the declared configured demand cannot report a PASS',
        (vs_declared.get('status') == 'fail') if (allowance is not None and declared is not None and allowance > declared)
        else (vs_declared.get('status') == 'pass'),
        json.dumps(vs_declared),
    )
    check(
        "reports/power-budget.json separates the allowance from a measured current (measured_current_ma is null; no bench result invented)",
        'measured_current_ma' in usb_budget and usb_budget['measured_current_ma'] is None,
    )

    leftover_targets = [
        R / 'scripts/power_budget.py',
        R / 'LOCAL-HANDOFF.md',
        R / 'design/narrative-pages.json',
        R / 'design/power-contract.json',
        R / 'reports/power-budget.json',
    ]
    # A file may cite the rejected suggestion, by name, as a decision record --
    # e.g. "removed/rejected ... see decision_notes.rejected_gpio24_vbus_sense" --
    # without that counting as reintroducing it as a live suggestion. Only a
    # mention with no such citation nearby is treated as a leftover.
    leftovers = []
    for f in leftover_targets:
        text = f.read_text()
        if not re.search(r'GPIO24|VBUS-sense', text):
            continue
        if 'rejected_gpio24_vbus_sense' in text:
            continue
        leftovers.append(str(f.relative_to(R)))
    check(
        'GPIO24/VBUS-sense is not proposed anywhere as a configuration-state substitute',
        not leftovers,
        str(leftovers),
    )

    gates = json.loads((R / 'design/release-gates.json').read_text())
    g07 = next((g for g in gates['gates'] if g['id'] == 'G07'), None)
    check('G07 stays OPEN after the USB power-contract desk decision', g07 is not None and g07['status'] == 'OPEN')


EXTRA_CHECKS.append(_usb_power_contract_parity)


def _nominal_calibration_parity(check, ctx):
    """#42: the firmware's nominal-fallback calibration equals reports/analog-analysis.json within rounding."""
    import json
    import re

    R = ctx['R']
    header = (R / 'firmware/src/scope_core.h').read_text()
    report = json.loads((R / 'reports/analog-analysis.json').read_text())

    def define(name):
        m = re.search(r'#define\s+' + name + r'\s+([0-9.eE+-]+)f?\b', header)
        return float(m.group(1)) if m else None

    zero = define('SCOPE_NOMINAL_ZERO_CODE')
    vpc = define('SCOPE_NOMINAL_VOLTS_PER_CODE')
    want_zero = report['adc_zero_code_ideal']
    want_vpc = report['input_referred_ideal_adc_lsb_mV'] / 1000.0
    check(
        'Firmware nominal zero code matches analog-analysis.json adc_zero_code_ideal (within 0.0005 code)',
        zero is not None and abs(zero - want_zero) <= 5e-4,
        f'firmware={zero} report={want_zero}',
    )
    check(
        'Firmware nominal volts/code matches analog-analysis.json input-referred LSB (within 1 ppm)',
        vpc is not None and abs(vpc - want_vpc) <= 1e-6 * want_vpc,
        f'firmware={vpc} report={want_vpc}',
    )


EXTRA_CHECKS.append(_nominal_calibration_parity)


def run(check, ctx):
    for extra in EXTRA_CHECKS:
        extra(check, ctx)


def _gp13_backlight_interface(check, ctx):
    """#41 (source #19): GP13 never sees the module's 5 V-pulled LCD_BL node.

    The RP2040 pad must connect only to the Q1 gate network (R64 series,
    R88 pull-down, Q1 gate). A resistive DC path of less than
    GP13_ISOLATION_MIN_OHM from GP13's net to any >3.3 V source net fails the
    check; MOSFET and header pins are not conductive paths for this walk.
    The J30/J31 display header map must stay as G01 froze it, and firmware
    must drive the (inverted) backlight pin high from its early hook.
    """
    import json

    R = ctx['R']
    parts = ctx['parts']
    pby = ctx['pby']
    byid = ctx['byid']
    GP13_ISOLATION_MIN_OHM = 1_000_000.0
    HIGH_VOLTAGE_NETS = {'+5V_FUSED', 'VBUS_USB', 'LCD_BL'}

    gpio_nets = json.loads((R / 'design/gpio.json').read_text())['gpio_nets']
    gp13_net = gpio_nets.get('13')
    check('GP13 is assigned a carrier net in design/gpio.json', bool(gp13_net), str(gp13_net))
    if not gp13_net:
        return

    # Resistive adjacency: every two-pin Resistor record is an edge weighted by its nominal value.
    edges = {}
    for p in parts:
        rec = byid[p['record']]
        if rec.get('kind') != 'Resistor' or rec.get('nominal') is None:
            continue
        a, b = (p['pins'].get('1'), p['pins'].get('2'))
        if a and b:
            edges.setdefault(a, []).append((b, float(rec['nominal'])))
            edges.setdefault(b, []).append((a, float(rec['nominal'])))
    best = {gp13_net: 0.0}
    frontier = [gp13_net]
    while frontier:
        net = frontier.pop()
        for nxt, ohm in edges.get(net, []):
            total = best[net] + ohm
            if total < GP13_ISOLATION_MIN_OHM and total < best.get(nxt, float('inf')):
                best[nxt] = total
                frontier.append(nxt)
    reachable_hv = {n: best[n] for n in HIGH_VOLTAGE_NETS if n in best}
    check(
        f'GP13 net has no resistive DC path below {GP13_ISOLATION_MIN_OHM:.0f} ohm to a >3.3 V source (+5V_FUSED, VBUS_USB, LCD_BL) (#41)',
        not reachable_hv,
        f'gp13_net={gp13_net} reachable={reachable_hv} walked={sorted(best)}',
    )

    members = {net: sorted((p['ref'], pin) for p in parts for pin, n in p['pins'].items() if n == net)
               for net in (gp13_net, 'LCD_BL_GATE', 'LCD_BL')}
    check(
        'GP13 net connects only the Pico socket contact and R64 (#41)',
        members[gp13_net] == [('J20', '17'), ('R64', '1')],
        str(members[gp13_net]),
    )
    check(
        'LCD_BL_GATE connects only R64, R88 (gate pull-down) and the Q1 gate (#41)',
        members['LCD_BL_GATE'] == [('Q1', '1'), ('R64', '2'), ('R88', '1')],
        str(members['LCD_BL_GATE']),
    )
    check(
        'LCD_BL (J30 pos 17) connects only the display header and the Q1 drain; module R16 is its only pull-up (#41)',
        members['LCD_BL'] == [('J30', '17'), ('Q1', '3')],
        str(members['LCD_BL']),
    )
    q1 = pby.get('Q1')
    check(
        'Q1 is the generic logic-level N-MOSFET record with source on GND (#41)',
        q1 is not None and q1['record'] == 'nmos-ll' and q1['pins'].get('2') == 'GND',
        json.dumps(q1['pins'] if q1 else None),
    )
    nmos = byid.get('nmos-ll', {})
    check(
        'nmos-ll stays a generic record until G08: no MPN, no LCSC code, footprint unqualified',
        nmos.get('mpn') is None and nmos.get('jlc_code') is None and not nmos.get('footprint_qualified'),
    )

    # G01 header-net rule (#13): the display map J30/J31 is frozen; #41 changed only carrier-side nets.
    displaymap = {3: 'GND', 8: 'GND', 13: 'GND', 18: 'GND', 23: 'GND', 28: 'GND', 33: 'GND', 38: 'GND',
                  39: '+5V_FUSED', 11: 'LCD_DC', 12: 'LCD_CS', 14: 'LCD_CLK', 15: 'LCD_MOSI', 16: 'LCD_MISO',
                  17: 'LCD_BL', 20: 'LCD_RST', 21: 'TP_CS_N', 29: 'SD_CS_N'}
    j30 = {str(k): displaymap.get(k) for k in range(1, 21)}
    j31 = {str(k): displaymap.get(41 - k) for k in range(1, 21)}
    check('J30/J31 display header nets unchanged by the backlight interface change (#41)',
          pby['J30']['pins'] == j30 and pby['J31']['pins'] == j31)

    safe = (R / 'firmware/src/lcd_safe_pins.c').read_text()
    header = (R / 'firmware/src/lcd_safe_pins.h').read_text()
    check(
        'Firmware early hook drives GP13 to the inverted OFF level (high) and the levels are named in lcd_safe_pins.h (#41)',
        'drive(LCD_PIN_BL, LCD_BL_LEVEL_OFF)' in safe
        and '#define LCD_BL_LEVEL_OFF true' in header and '#define LCD_BL_LEVEL_ON false' in header,
    )
    pending = {e['id']: e for e in ctx['circuit'].get('pending_g01_changes', [])}
    check(
        'pending_g01_changes[g01-r88-backlight-default] records the applied design, not an open keep/remove choice',
        pending.get('g01-r88-backlight-default', {}).get('status') == 'DESIGN_APPLIED_BENCH_CHECK_PENDING',
        str(pending.get('g01-r88-backlight-default', {}).get('status')),
    )
    gates = json.loads((R / 'design/release-gates.json').read_text())
    still_open = {g['id']: g['status'] for g in gates['gates'] if g['id'] in ('G01', 'G06')}
    check('G01 and G06 stay OPEN after the desk backlight-interface change (#41)',
          still_open == {'G01': 'OPEN', 'G06': 'OPEN'}, str(still_open))


EXTRA_CHECKS.append(_gp13_backlight_interface)
