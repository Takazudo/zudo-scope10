#!/usr/bin/env python3
"""Negative and positive tests for manufacturing/release_guard.py (#28/#39).

Covers the exit-code contract: 0 = structurally complete + resolvable
evidence (never automated approval), 2 = intentional REFUSED, 3 = malformed
manifest. Every fixture manifest here is synthetic and lives under a temp
directory; the checked-in design/release-gates.json is never mutated, and a
structurally-complete "gates closed" fixture is exercised only against fake
temp evidence files, never claimed as real engineering approval.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

R = Path(__file__).resolve().parents[1]
GUARD = R / 'manufacturing/release_guard.py'

REQUIRED_IDS = [f'G{i:02d}' for i in range(1, 11)]


def run_guard(manifest_path, route=None):
    cmd = [sys.executable, str(GUARD), '--manifest', str(manifest_path)]
    if route is not None:
        cmd += ['--route', route]
    return subprocess.run(cmd, capture_output=True, text=True)


def make_workdir():
    return Path(tempfile.mkdtemp(prefix='zs10-test-release-guard-'))


def write_manifest(workdir, data):
    """Manifest lives at <workdir>/design/release-gates.json so evidence
    paths relative to <workdir> match the real repo's convention."""
    design = workdir / 'design'
    design.mkdir(parents=True, exist_ok=True)
    path = design / 'release-gates.json'
    path.write_text(json.dumps(data))
    return path


def make_gate(gid, status='OPEN', evidence_files=None, **extra):
    gate = {'id': gid, 'title': f'{gid} title', 'status': status}
    if evidence_files is not None:
        gate['evidence_files'] = evidence_files
    gate.update(extra)
    return gate


def full_gate_set(**overrides_by_id):
    gates = [make_gate(gid) for gid in REQUIRED_IDS]
    for gate in gates:
        if gate['id'] in overrides_by_id:
            gate.update(overrides_by_id[gate['id']])
    return gates


PREREQ_IDS = [
    'reviewed_power_and_pin_design',
    'actual_footprint_mapping',
    'completed_layout_and_native_checks',
    'assembler_dfm_review',
    'controlled_bring_up_plan',
]


def make_prereq(pid, met=False, evidence_files=None, **extra):
    item = {'id': pid, 'description': f'{pid} description', 'met': met}
    if evidence_files is not None:
        item['evidence_files'] = evidence_files
    item.update(extra)
    return item


def full_prototype_prereqs(**overrides_by_id):
    prereqs = [make_prereq(pid) for pid in PREREQ_IDS]
    for item in prereqs:
        if item['id'] in overrides_by_id:
            item.update(overrides_by_id[item['id']])
    return prereqs


def make_prototype_decision(allowed=False, prereqs=None, approval=None):
    return {
        'allowed': allowed,
        'prerequisites': full_prototype_prereqs() if prereqs is None else prereqs,
        'approval': {'approved': False, 'approver': None, 'date': None, 'revision': None}
        if approval is None else approval,
    }


def base_manifest_with_decisions(prototype=None, release_allowed=False, gates=None):
    """A minimal well-formed manifest carrying both decisions blocks, for
    exercising --route prototype without disturbing the production-route
    fixtures above (which intentionally omit 'decisions' to prove the
    production route stays backward compatible with #39's schema)."""
    return {
        'release_allowed': release_allowed,
        'gates': full_gate_set() if gates is None else gates,
        'decisions': {
            'prototype': make_prototype_decision() if prototype is None else prototype,
            'production': {'required_gates': REQUIRED_IDS},
        },
    }


def expect(result, code, needle, label):
    assert result.returncode == code, (
        f'{label}: expected exit {code}, got {result.returncode}\n'
        f'stdout={result.stdout}\nstderr={result.stderr}'
    )
    combined = result.stdout + result.stderr
    assert needle in combined, f'{label}: expected {needle!r} in output, got: {combined}'
    print(f'PASS: {label}')


def test_reproduced_case_release_allowed_true_no_gates():
    workdir = make_workdir()
    try:
        manifest = write_manifest(workdir, {'release_allowed': True, 'gates': []})
        r = run_guard(manifest)
        expect(r, 3, 'MALFORMED', 'release_allowed:true with empty gates is malformed (missing G01-G10), never exit 0')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_reproduced_case_only_g01_closed_nonexistent_evidence():
    workdir = make_workdir()
    try:
        gates = [make_gate('G01', status='CLOSED', evidence_files=['does-not-exist.pdf'])]
        manifest = write_manifest(workdir, {'release_allowed': True, 'gates': gates})
        r = run_guard(manifest)
        expect(r, 3, 'MALFORMED', 'only G01 present is malformed (missing G02-G10)')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_reproduced_case_all_ten_closed_nonexistent_evidence():
    workdir = make_workdir()
    try:
        gates = full_gate_set(**{
            gid: {'status': 'CLOSED', 'evidence_files': ['does-not-exist.pdf']}
            for gid in REQUIRED_IDS
        })
        manifest = write_manifest(workdir, {'release_allowed': True, 'gates': gates})
        r = run_guard(manifest)
        expect(r, 2, 'does not exist', 'all ten CLOSED with a nonexistent evidence file must REFUSE, not pass')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_reproduced_case_release_allowed_truthy_string():
    workdir = make_workdir()
    try:
        manifest = write_manifest(workdir, {'release_allowed': 'false', 'gates': []})
        r = run_guard(manifest)
        expect(r, 3, 'MALFORMED', "the string 'false' must not be accepted as a JSON boolean")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_duplicate_ids():
    workdir = make_workdir()
    try:
        gates = full_gate_set()
        gates.append(make_gate('G01'))  # duplicate
        manifest = write_manifest(workdir, {'release_allowed': False, 'gates': gates})
        r = run_guard(manifest)
        expect(r, 3, 'duplicate gate ids', 'duplicate gate ids must be malformed')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_unknown_ids():
    workdir = make_workdir()
    try:
        gates = full_gate_set()
        gates.append(make_gate('G11'))
        manifest = write_manifest(workdir, {'release_allowed': False, 'gates': gates})
        r = run_guard(manifest)
        expect(r, 3, 'unknown gate ids', 'unknown gate ids must be malformed')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_wrong_type_status():
    workdir = make_workdir()
    try:
        gates = full_gate_set(G01={'status': 1})
        manifest = write_manifest(workdir, {'release_allowed': False, 'gates': gates})
        r = run_guard(manifest)
        expect(r, 3, 'MALFORMED', 'a non-string status must be malformed')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_evidence_path_is_a_directory():
    workdir = make_workdir()
    try:
        (workdir / 'a-directory').mkdir()
        gates = full_gate_set(G01={'status': 'CLOSED', 'evidence_files': ['a-directory']})
        manifest = write_manifest(workdir, {'release_allowed': True, 'gates': gates})
        r = run_guard(manifest)
        expect(r, 2, 'is a directory', 'a directory listed as evidence must REFUSE, not pass')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_evidence_path_escaping_repo_root():
    workdir = make_workdir()
    try:
        gates = full_gate_set(G01={'status': 'CLOSED', 'evidence_files': ['../outside.txt']})
        manifest = write_manifest(workdir, {'release_allowed': True, 'gates': gates})
        r = run_guard(manifest)
        expect(r, 2, 'escapes the repository root', 'an evidence path escaping the repo root must REFUSE')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_malformed_json():
    workdir = make_workdir()
    try:
        design = workdir / 'design'
        design.mkdir(parents=True)
        manifest = design / 'release-gates.json'
        manifest.write_text('{not valid json')
        r = run_guard(manifest)
        expect(r, 3, 'MALFORMED', 'unparseable JSON must be exit 3')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_evidence_urls_alone_never_closes_a_gate():
    workdir = make_workdir()
    try:
        gates = full_gate_set(G01={'status': 'CLOSED', 'evidence_files': [], 'evidence_urls': ['https://example.com/report']})
        manifest = write_manifest(workdir, {'release_allowed': True, 'gates': gates})
        r = run_guard(manifest)
        expect(r, 2, 'evidence_urls alone never closes a gate', 'a URL reference alone must not close a gate')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_structurally_complete_synthetic_fixture_exits_zero():
    """A synthetic fixture only -- never the real manifest -- with real temp
    evidence files. Exit 0 must still name that this is not automated
    engineering approval."""
    workdir = make_workdir()
    try:
        evidence_dir = workdir / 'design/evidence'
        evidence_dir.mkdir(parents=True)
        overrides = {}
        for gid in REQUIRED_IDS:
            evidence_path = evidence_dir / f'{gid.lower()}-evidence.md'
            evidence_path.write_text(f'synthetic evidence for {gid}\n')
            overrides[gid] = {
                'status': 'CLOSED',
                'evidence_files': [f'design/evidence/{gid.lower()}-evidence.md'],
            }
        gates = full_gate_set(**overrides)
        manifest = write_manifest(workdir, {'release_allowed': True, 'gates': gates})
        r = run_guard(manifest)
        expect(r, 0, 'NOT automated engineering approval', 'a structurally complete synthetic fixture must exit 0 and still require human review')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_real_manifest_refuses_with_exit_2():
    """The checked-in manifest itself: CI and validate.py rely on this
    staying exit 2, not merely nonzero."""
    r = run_guard(R / 'design/release-gates.json')
    expect(r, 2, 'REFUSED', 'the real checked-in manifest must refuse with exit 2')


def test_production_route_matches_default_on_real_manifest():
    """--route production must behave identically to the default (#39
    backward compatibility): same exit code and REFUSED framing."""
    r = run_guard(R / 'design/release-gates.json', route='production')
    expect(r, 2, 'REFUSED', '--route production must refuse the real manifest, same as the default route')


def test_prototype_route_refuses_on_real_manifest():
    """The checked-in manifest's decisions.prototype is still all-unmet: the
    prototype route must also refuse the real manifest with exit 2 (#24/#43
    acceptance: 'the current empty-outline package remains blocked for both
    routes')."""
    r = run_guard(R / 'design/release-gates.json', route='prototype')
    expect(r, 2, 'REFUSED', 'the real checked-in manifest must refuse --route prototype')


def test_prototype_route_never_reads_gate_closed_status():
    """#24's whole point: a prototype decision must not be blocked by G01/
    G02/G03/G08 (or any other gate) being OPEN -- only by its own
    prerequisites/approval. A manifest with every gate OPEN but every
    prototype prerequisite met and approved must pass structurally."""
    workdir = make_workdir()
    try:
        evidence_dir = workdir / 'design/evidence'
        evidence_dir.mkdir(parents=True)
        overrides = {}
        for pid in PREREQ_IDS:
            evidence_path = evidence_dir / f'{pid}.md'
            evidence_path.write_text(f'synthetic evidence for {pid}\n')
            overrides[pid] = {'met': True, 'evidence_files': [f'design/evidence/{pid}.md']}
        manifest = write_manifest(workdir, base_manifest_with_decisions(
            gates=full_gate_set(),  # every gate OPEN
            prototype=make_prototype_decision(
                allowed=True,
                prereqs=full_prototype_prereqs(**overrides),
                approval={'approved': True, 'approver': 'J. Reviewer', 'date': '2026-09-26', 'revision': 'rev-a'},
            ),
        ))
        r = run_guard(manifest, route='prototype')
        expect(r, 0, 'NOT automated engineering approval', 'a structurally complete synthetic prototype decision must exit 0 even with every gate OPEN')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_prototype_route_blocks_on_missing_prerequisite():
    workdir = make_workdir()
    try:
        evidence_dir = workdir / 'design/evidence'
        evidence_dir.mkdir(parents=True)
        overrides = {}
        for pid in PREREQ_IDS:
            evidence_path = evidence_dir / f'{pid}.md'
            evidence_path.write_text(f'synthetic evidence for {pid}\n')
            overrides[pid] = {'met': True, 'evidence_files': [f'design/evidence/{pid}.md']}
        # Leave one prerequisite unmet.
        overrides['assembler_dfm_review'] = {'met': False, 'evidence_files': []}
        manifest = write_manifest(workdir, base_manifest_with_decisions(
            prototype=make_prototype_decision(
                allowed=True,
                prereqs=full_prototype_prereqs(**overrides),
                approval={'approved': True, 'approver': 'J. Reviewer', 'date': '2026-09-26', 'revision': 'rev-a'},
            ),
        ))
        r = run_guard(manifest, route='prototype')
        expect(r, 2, 'assembler_dfm_review', 'a single missing prototype prerequisite must block export by name')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_prototype_route_blocks_on_missing_approval():
    workdir = make_workdir()
    try:
        evidence_dir = workdir / 'design/evidence'
        evidence_dir.mkdir(parents=True)
        overrides = {}
        for pid in PREREQ_IDS:
            evidence_path = evidence_dir / f'{pid}.md'
            evidence_path.write_text(f'synthetic evidence for {pid}\n')
            overrides[pid] = {'met': True, 'evidence_files': [f'design/evidence/{pid}.md']}
        manifest = write_manifest(workdir, base_manifest_with_decisions(
            prototype=make_prototype_decision(
                allowed=True,
                prereqs=full_prototype_prereqs(**overrides),
                approval={'approved': False, 'approver': None, 'date': None, 'revision': None},
            ),
        ))
        r = run_guard(manifest, route='prototype')
        expect(r, 2, 'never auto-filled', 'a missing approval must block prototype export even with every prerequisite met')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_prototype_route_blocks_on_approved_but_incomplete_record():
    """approved=true with a missing approver/date/revision must still
    refuse -- approved alone is not the human record the issue requires."""
    workdir = make_workdir()
    try:
        evidence_dir = workdir / 'design/evidence'
        evidence_dir.mkdir(parents=True)
        overrides = {}
        for pid in PREREQ_IDS:
            evidence_path = evidence_dir / f'{pid}.md'
            evidence_path.write_text(f'synthetic evidence for {pid}\n')
            overrides[pid] = {'met': True, 'evidence_files': [f'design/evidence/{pid}.md']}
        manifest = write_manifest(workdir, base_manifest_with_decisions(
            prototype=make_prototype_decision(
                allowed=True,
                prereqs=full_prototype_prereqs(**overrides),
                approval={'approved': True, 'approver': '', 'date': None, 'revision': None},
            ),
        ))
        r = run_guard(manifest, route='prototype')
        expect(r, 2, "'approver'", 'approved=true with missing approver/date/revision fields must still refuse')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_prototype_route_blocks_when_allowed_is_false():
    workdir = make_workdir()
    try:
        evidence_dir = workdir / 'design/evidence'
        evidence_dir.mkdir(parents=True)
        overrides = {}
        for pid in PREREQ_IDS:
            evidence_path = evidence_dir / f'{pid}.md'
            evidence_path.write_text(f'synthetic evidence for {pid}\n')
            overrides[pid] = {'met': True, 'evidence_files': [f'design/evidence/{pid}.md']}
        manifest = write_manifest(workdir, base_manifest_with_decisions(
            prototype=make_prototype_decision(
                allowed=False,
                prereqs=full_prototype_prereqs(**overrides),
                approval={'approved': True, 'approver': 'J. Reviewer', 'date': '2026-09-26', 'revision': 'rev-a'},
            ),
        ))
        r = run_guard(manifest, route='prototype')
        expect(r, 2, 'decisions.prototype.allowed is false', 'allowed=false must block prototype export even when every prerequisite and the approval are otherwise complete')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_prototype_route_missing_decisions_key_is_malformed():
    workdir = make_workdir()
    try:
        manifest = write_manifest(workdir, {'release_allowed': False, 'gates': full_gate_set()})
        r = run_guard(manifest, route='prototype')
        expect(r, 3, 'MALFORMED', "--route prototype on a manifest with no 'decisions' key must be malformed, not silently pass or refuse")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_prototype_route_duplicate_prerequisite_ids_is_malformed():
    workdir = make_workdir()
    try:
        prereqs = full_prototype_prereqs()
        prereqs.append(make_prereq('reviewed_power_and_pin_design'))  # duplicate
        manifest = write_manifest(workdir, base_manifest_with_decisions(
            prototype=make_prototype_decision(prereqs=prereqs),
        ))
        r = run_guard(manifest, route='prototype')
        expect(r, 3, 'duplicate prototype prerequisite ids', 'duplicate prototype prerequisite ids must be malformed')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_prototype_route_evidence_path_escaping_repo_root():
    workdir = make_workdir()
    try:
        overrides = {'reviewed_power_and_pin_design': {'met': True, 'evidence_files': ['../outside.txt']}}
        manifest = write_manifest(workdir, base_manifest_with_decisions(
            prototype=make_prototype_decision(prereqs=full_prototype_prereqs(**overrides)),
        ))
        r = run_guard(manifest, route='prototype')
        expect(r, 2, 'escapes the repository root', 'a prototype prerequisite evidence path escaping the repo root must REFUSE')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_invalid_route_is_malformed():
    workdir = make_workdir()
    try:
        manifest = write_manifest(workdir, {'release_allowed': False, 'gates': full_gate_set()})
        r = subprocess.run(
            [sys.executable, str(GUARD), '--manifest', str(manifest), '--route', 'bogus'],
            capture_output=True, text=True,
        )
        # Argument parsing rejects an unlisted --route choice as malformed (exit 3), never
        # with exit 2, which the exit-code contract reserves for a considered refusal.
        assert r.returncode == 3, f'expected an unknown --route to exit 3 (MALFORMED), got {r.returncode}\n{r.stderr}'
        print('PASS: an unknown --route value is rejected by argument parsing')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    test_reproduced_case_release_allowed_true_no_gates()
    test_reproduced_case_only_g01_closed_nonexistent_evidence()
    test_reproduced_case_all_ten_closed_nonexistent_evidence()
    test_reproduced_case_release_allowed_truthy_string()
    test_duplicate_ids()
    test_unknown_ids()
    test_wrong_type_status()
    test_evidence_path_is_a_directory()
    test_evidence_path_escaping_repo_root()
    test_malformed_json()
    test_evidence_urls_alone_never_closes_a_gate()
    test_structurally_complete_synthetic_fixture_exits_zero()
    test_real_manifest_refuses_with_exit_2()
    test_production_route_matches_default_on_real_manifest()
    test_prototype_route_refuses_on_real_manifest()
    test_prototype_route_never_reads_gate_closed_status()
    test_prototype_route_blocks_on_missing_prerequisite()
    test_prototype_route_blocks_on_missing_approval()
    test_prototype_route_blocks_on_approved_but_incomplete_record()
    test_prototype_route_blocks_when_allowed_is_false()
    test_prototype_route_missing_decisions_key_is_malformed()
    test_prototype_route_duplicate_prerequisite_ids_is_malformed()
    test_prototype_route_evidence_path_escaping_repo_root()
    test_invalid_route_is_malformed()
    print('PASS: manufacturing/release_guard.py exit-code contract holds (#28/#39/#24/#43)')
