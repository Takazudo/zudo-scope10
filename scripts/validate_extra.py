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


EXTRA_CHECKS = [_power_budget_report]


def run(check, ctx):
    for extra in EXTRA_CHECKS:
        extra(check, ctx)
