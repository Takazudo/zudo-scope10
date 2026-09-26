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

Starts empty: no sub-issue has added a check yet.
"""

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


EXTRA_CHECKS = [_spice_check]


def run(check, ctx):
    for extra in EXTRA_CHECKS:
        extra(check, ctx)
