#!/usr/bin/env python3
"""Regression fixture for #23/#31: scripts/validate.py must never mutate or
destroy the PCB/project it is asked to check, and a failing validation must
still leave the checkout untouched.

Runs entirely on throwaway temp copies of the repository (excluding .git,
node_modules, dist and __pycache__, same as validate.py's own isolation
copy); never reads or writes anything under the real checkout.
"""
from pathlib import Path
import json, shutil, subprocess, sys, tempfile, uuid

R = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns('.git', 'node_modules', 'dist', '__pycache__')


def make_fixture():
    tmp = Path(tempfile.mkdtemp(prefix='zs10-test-validate-'))
    shutil.copytree(R, tmp, dirs_exist_ok=True, ignore=IGNORE)
    return tmp


def run(fixture, script):
    return subprocess.run([sys.executable, str(fixture / script)], cwd=fixture, capture_output=True, text=True)


def inject_layout_sentinels(fixture):
    """Representative placement/routing text plus a developer project setting --
    exactly the kind of local work LOCAL-HANDOFF.md's G03 step asks for and that
    validate.py/make_design.py must never erase."""
    pcb = fixture / 'hardware/kicad/zudo-scope10-p0.kicad_pcb'
    text = pcb.read_text().rstrip()
    assert text.endswith(')'), 'unexpected kicad_pcb shape; fixture assumption stale'
    footprint = (
        ' (footprint "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm" (layer "F.Cu") '
        f'(uuid "{uuid.uuid4()}") (at 100 100) '
        '(property "Reference" "U1" (at 0 0 0)) (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))'
    )
    segment = f' (segment (start 100 100) (end 120 100) (width 0.25) (layer "F.Cu") (net 1) (uuid "{uuid.uuid4()}"))'
    text = text[:-1] + footprint + segment + '\n)\n'
    pcb.write_text(text)

    pro = fixture / 'hardware/kicad/zudo-scope10-p0.kicad_pro'
    data = json.loads(pro.read_text())
    data['sentinel_project_setting'] = 'local-placement-in-progress'
    pro.write_text(json.dumps(data, indent=2) + '\n')

    gates = fixture / 'design/release-gates.json'
    g = json.loads(gates.read_text())
    g['design_phase'] = 'layout'  # so the injected layout doesn't trip the pre-layout check
    gates.write_text(json.dumps(g, indent=2) + '\n')

    return pcb.read_bytes(), pro.read_bytes()


def test_survives_validate_and_regeneration():
    fixture = make_fixture()
    try:
        pcb_path = fixture / 'hardware/kicad/zudo-scope10-p0.kicad_pcb'
        pro_path = fixture / 'hardware/kicad/zudo-scope10-p0.kicad_pro'
        pcb_before, pro_before = inject_layout_sentinels(fixture)

        r = run(fixture, 'scripts/validate.py')
        assert pcb_path.read_bytes() == pcb_before, 'validate.py must not touch the PCB'
        assert pro_path.read_bytes() == pro_before, 'validate.py must not touch the KiCad project'
        assert r.returncode == 0, f'validate.py should PASS with design_phase=layout and no injected regressions:\n{r.stdout}{r.stderr}'

        for script in ('make_design.py', 'analyze.py', 'build_docs.py'):
            reg = run(fixture, 'scripts/' + script)
            assert reg.returncode == 0, f'{script} failed:\n{reg.stdout}{reg.stderr}'
        assert pcb_path.read_bytes() == pcb_before, 'ordinary regeneration must not erase placement/routing'
        assert pro_path.read_bytes() == pro_before, 'ordinary regeneration must not erase project settings'
        print('PASS: sentinel placement/routing/project settings survive validate.py and ordinary regeneration')
    finally:
        shutil.rmtree(fixture, ignore_errors=True)


def test_generated_mismatch_fails_without_destroying():
    fixture = make_fixture()
    try:
        bom = fixture / 'manufacturing/bom-planning.csv'
        corrupted = bom.read_bytes() + b'CORRUPTED,BY,TEST,ROW\n'
        bom.write_bytes(corrupted)

        r = run(fixture, 'scripts/validate.py')
        assert r.returncode != 0, 'validate.py must FAIL on a generated-output mismatch'
        assert 'Isolated regeneration matches checkout' in (r.stdout + r.stderr), 'FAIL output must name the mismatched check'
        assert bom.read_bytes() == corrupted, 'a FAILing validate.py must not rewrite the mismatched file'
        print('PASS: a deliberately corrupted generated file FAILs validate.py and is left corrupted, not silently repaired')
    finally:
        shutil.rmtree(fixture, ignore_errors=True)


if __name__ == '__main__':
    test_survives_validate_and_regeneration()
    test_generated_mismatch_fails_without_destroying()
    print('PASS: scripts/validate.py is non-destructive (#23/#31)')
