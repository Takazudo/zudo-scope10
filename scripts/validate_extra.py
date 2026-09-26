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


EXTRA_CHECKS = [kicad_native_parity]


def run(check, ctx):
    for extra in EXTRA_CHECKS:
        extra(check, ctx)
