#!/usr/bin/env python3
"""Release guard for design/release-gates.json (#28/#39).

This is not automated engineering approval. It only checks that the manifest
is structurally complete, correctly typed, and that every gate it claims is
CLOSED points at evidence that actually resolves. A human still has to
independently review that evidence before approving a quote.

Exit-code contract (do not change without updating CI and validate.py):
  0 = structurally complete and every gate CLOSED with resolvable evidence.
      Never automated approval -- independent human review is still required.
  2 = intentional REFUSED: the manifest is well-formed but release is not
      (yet) warranted -- release_allowed is false, a gate is not CLOSED, or a
      gate's evidence does not resolve.
  3 = malformed manifest: invalid JSON, wrong top-level shape, wrong field
      types, or a gate id set that is not exactly G01-G10 with no duplicates.
  1 = uncaught error while running the guard itself. This must never be
      confused with 2 -- a crash is not a considered refusal.

Routes (#24/#43): --route selects which decision this run evaluates.
  production (default) -- unchanged #39 behavior: release_allowed plus every
    gate G01-G10 CLOSED with resolvable evidence. Never relaxed.
  prototype -- a separate decision under design/release-gates.json's
    decisions.prototype. It never reads or requires any gate's CLOSED
    status: #24's finding is that G01/G02/G03/G08's full closure needs bench
    work on the very factory-assembled prototype this route would authorize,
    so reusing gate CLOSED status here would keep the same cycle. Instead it
    checks decisions.prototype.allowed, a fixed list of standalone
    prerequisites (each with its own evidence_files, resolved the same way
    as a gate's), and an explicit human approval record (approver/date/
    revision) that is never auto-filled. Missing or unmet prerequisites, or
    a missing approval, each refuse with a specific message. This never
    authorizes fabrication and never substitutes for production's full gate
    set.
"""
from pathlib import Path
import argparse
import json
import sys

REQUIRED_GATE_IDS = {f'G{i:02d}' for i in range(1, 11)}
ALLOWED_STATUSES = {'OPEN', 'CLOSED'}
ROUTES = {'production', 'prototype'}

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / 'design/release-gates.json'


class ManifestError(Exception):
    """Raised for schema/type-level manifest problems (exit code 3)."""


def load_manifest(path):
    try:
        text = path.read_text()
    except OSError as e:
        raise ManifestError(f'cannot read manifest {path}: {e}') from e
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ManifestError(f'invalid JSON in {path}: {e}') from e
    if not isinstance(data, dict):
        raise ManifestError('manifest root must be a JSON object')
    return data


def _nonempty_str_list(value):
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def validate_release_allowed(data):
    """`release_allowed` must be a real JSON boolean -- a truthy string like
    "false" must not be accepted (this is the #28 case the old guard missed)."""
    if 'release_allowed' not in data:
        raise ManifestError("missing required key 'release_allowed'")
    value = data['release_allowed']
    if not isinstance(value, bool):
        raise ManifestError(
            f"'release_allowed' must be a JSON boolean, got {type(value).__name__}: {value!r}"
        )
    return value


def _resolve_local_paths(evidence_files, repo_root):
    """Every local evidence path must resolve to an existing file inside
    repo_root. Returns a list of human-readable problems, empty if all
    resolve."""
    problems = []
    root = repo_root.resolve()
    for rel in evidence_files:
        try:
            resolved = (repo_root / rel).resolve()
            resolved.relative_to(root)
        except (ValueError, OSError):
            problems.append(f'{rel} (escapes the repository root)')
            continue
        if not resolved.exists():
            problems.append(f'{rel} (does not exist)')
        elif resolved.is_dir():
            problems.append(f'{rel} (is a directory, not a file)')
        elif not resolved.is_file():
            problems.append(f'{rel} (not a regular file)')
    return problems


def validate_gates(data, repo_root, required_ids=None):
    """Type/shape-checks every gate (raising ManifestError on schema
    violations) and returns a list of refusal reasons for gates that are
    well-formed but not actually closeable yet.

    `required_ids` (#24/#43 seam) is the set of gate ids whose non-CLOSED
    status actually blocks *this* route; it defaults to the full G01-G10
    production set, matching the original #39 behavior exactly. The
    structural check that the manifest names exactly G01-G10 (no more, no
    fewer, no duplicates) always applies regardless of route -- that is
    manifest well-formedness, not a route decision. Passing `required_ids=
    set()` (as the prototype route does) keeps every gate's type/evidence
    shape validated but never refuses on a gate simply being OPEN.
    """
    if required_ids is None:
        required_ids = REQUIRED_GATE_IDS
    if 'gates' not in data or not isinstance(data['gates'], list):
        raise ManifestError("'gates' must be a JSON list")
    gates = data['gates']

    seen_ids = []
    refusals = []
    for i, gate in enumerate(gates):
        if not isinstance(gate, dict):
            raise ManifestError(f'gate at index {i} is not a JSON object')

        gid = gate.get('id')
        if not isinstance(gid, str) or not gid.strip():
            raise ManifestError(f'gate at index {i} has no valid string id')
        seen_ids.append(gid)

        status = gate.get('status')
        if not isinstance(status, str) or status not in ALLOWED_STATUSES:
            raise ManifestError(
                f"gate {gid}: 'status' must be one of {sorted(ALLOWED_STATUSES)}, got {status!r}"
            )

        evidence_files = gate.get('evidence_files', [])
        if not _nonempty_str_list(evidence_files):
            raise ManifestError(f"gate {gid}: 'evidence_files' must be a list of non-empty strings")

        # Seam for external references: allowed only in this separate typed
        # field and, per #28/#39, never sufficient alone to close a gate --
        # the CLOSED check below never treats evidence_urls as a substitute
        # for a resolvable local evidence_files entry.
        evidence_urls = gate.get('evidence_urls', [])
        if not _nonempty_str_list(evidence_urls):
            raise ManifestError(f"gate {gid}: 'evidence_urls' must be a list of non-empty strings")

        # evidence_partial / evidence_partial_note (added by #31) are
        # informational only; tolerated in any shape and never validated
        # or relied on here.

        path_problems = _resolve_local_paths(evidence_files, repo_root)
        if status == 'CLOSED':
            if not evidence_files:
                refusals.append(f'{gid}: CLOSED but evidence_files is empty (evidence_urls alone never closes a gate)')
            if path_problems:
                refusals.append(f'{gid}: evidence_files does not resolve: {"; ".join(path_problems)}')
        else:
            if gid in required_ids:
                title = gate.get('title')
                title_suffix = f' ({title})' if isinstance(title, str) and title else ''
                refusals.append(f'{gid}{title_suffix}: status is {status!r}, not CLOSED')
            if path_problems:
                # A listed local path that cannot resolve is a manifest
                # problem worth refusing on even while the gate is OPEN,
                # independent of whether this route requires the gate CLOSED.
                refusals.append(f'{gid}: evidence_files does not resolve: {"; ".join(path_problems)}')

    duplicates = sorted({gid for gid in seen_ids if seen_ids.count(gid) > 1})
    if duplicates:
        raise ManifestError(f'duplicate gate ids: {duplicates}')

    id_set = set(seen_ids)
    missing = sorted(REQUIRED_GATE_IDS - id_set)
    unknown = sorted(id_set - REQUIRED_GATE_IDS)
    if missing:
        raise ManifestError(f'missing required gate ids: {missing}')
    if unknown:
        raise ManifestError(f'unknown gate ids (required set is exactly G01-G10): {unknown}')

    return refusals


def validate_prototype_decision(data, repo_root):
    """#24/#43: the engineering-prototype route's own decision, entirely
    separate from the G01-G10 production gate set (see the route docstring
    above for why it must not reuse gate CLOSED status). Raises ManifestError
    for schema problems (exit 3) and returns a list of refusal reasons for a
    well-formed but not-yet-authorized prototype decision (exit 2).
    """
    decisions = data.get('decisions')
    if not isinstance(decisions, dict):
        raise ManifestError("missing required key 'decisions' for --route prototype")
    proto = decisions.get('prototype')
    if not isinstance(proto, dict):
        raise ManifestError("missing required key 'decisions.prototype' for --route prototype")

    allowed = proto.get('allowed')
    if not isinstance(allowed, bool):
        raise ManifestError("'decisions.prototype.allowed' must be a JSON boolean")

    prereqs = proto.get('prerequisites')
    if not isinstance(prereqs, list) or not prereqs:
        raise ManifestError("'decisions.prototype.prerequisites' must be a non-empty JSON list")

    refusals = []
    seen_ids = []
    for i, item in enumerate(prereqs):
        if not isinstance(item, dict):
            raise ManifestError(f'decisions.prototype.prerequisites[{i}] is not a JSON object')

        pid = item.get('id')
        if not isinstance(pid, str) or not pid.strip():
            raise ManifestError(f'decisions.prototype.prerequisites[{i}] has no valid string id')
        seen_ids.append(pid)

        met = item.get('met')
        if not isinstance(met, bool):
            raise ManifestError(f"prototype prerequisite {pid}: 'met' must be a JSON boolean")

        evidence_files = item.get('evidence_files', [])
        if not _nonempty_str_list(evidence_files):
            raise ManifestError(f"prototype prerequisite {pid}: 'evidence_files' must be a list of non-empty strings")

        path_problems = _resolve_local_paths(evidence_files, repo_root)
        if met:
            if not evidence_files:
                refusals.append(f'prototype prerequisite {pid}: met is true but evidence_files is empty')
            if path_problems:
                refusals.append(f'prototype prerequisite {pid}: evidence_files does not resolve: {"; ".join(path_problems)}')
        else:
            desc = item.get('description')
            desc_suffix = f' ({desc})' if isinstance(desc, str) and desc else ''
            refusals.append(f'prototype prerequisite {pid}{desc_suffix}: not met')
            if path_problems:
                refusals.append(f'prototype prerequisite {pid}: evidence_files does not resolve: {"; ".join(path_problems)}')

    duplicates = sorted({pid for pid in seen_ids if seen_ids.count(pid) > 1})
    if duplicates:
        raise ManifestError(f'duplicate prototype prerequisite ids: {duplicates}')

    if not allowed:
        refusals = ['decisions.prototype.allowed is false'] + refusals

    approval = proto.get('approval')
    if not isinstance(approval, dict):
        raise ManifestError("'decisions.prototype.approval' must be a JSON object")
    approved = approval.get('approved')
    if not isinstance(approved, bool):
        raise ManifestError("decisions.prototype.approval.approved must be a JSON boolean")
    if not approved:
        refusals.append(
            'prototype approval: approved is false -- an explicit human approval record '
            '(approver/date/revision) is required and is never auto-filled'
        )
    else:
        for field in ('approver', 'date', 'revision'):
            value = approval.get(field)
            if not isinstance(value, str) or not value.strip():
                refusals.append(
                    f'prototype approval: approved is true but {field!r} is missing or empty -- '
                    'this record must be filled by a human, never auto-filled'
                )

    return refusals


def run_guard(manifest_path, route='production'):
    """Returns (exit_code, message). manifest_path's grandparent directory is
    treated as the repo root that local evidence_files paths are relative to
    (matching design/release-gates.json's own two-levels-deep convention)."""
    if route not in ROUTES:
        return 3, f'MALFORMED: unknown --route {route!r}, expected one of {sorted(ROUTES)}'

    repo_root = manifest_path.resolve().parent.parent
    try:
        data = load_manifest(manifest_path)
        if route == 'production':
            # Unchanged #39 behavior: release_allowed plus every gate
            # G01-G10 CLOSED with resolvable evidence. Never relaxed by the
            # existence of the prototype route.
            release_allowed = validate_release_allowed(data)
            refusals = validate_gates(data, repo_root)
            if not release_allowed:
                refusals = ['release_allowed is false'] + refusals
        else:
            # prototype: structural completeness of the full gate set is
            # still required (a manifest missing/duplicating gate ids is
            # malformed regardless of route), but no gate's CLOSED status is
            # part of this route's refusal -- see validate_prototype_decision.
            validate_gates(data, repo_root, required_ids=set())
            refusals = validate_prototype_decision(data, repo_root)
    except ManifestError as e:
        return 3, f'MALFORMED: {e}'

    if refusals:
        lines = ['REFUSED: no order files may be generated from this manifest.']
        lines += [f'  - {r}' for r in refusals]
        return 2, '\n'.join(lines)

    if route == 'production':
        return 0, (
            'Gates structurally complete; every gate CLOSED with resolvable evidence.\n'
            'This is NOT automated engineering approval -- independent human review of '
            'every gate is still required before approving a quote.'
        )
    return 0, (
        'Prototype decision structurally complete: every prerequisite met with resolvable '
        'evidence and an explicit human approval record present.\n'
        'This is NOT automated engineering approval and does not authorize production release '
        '-- independent human review is still required, and production still needs every '
        'G01-G10 gate CLOSED with reviewed evidence.'
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST,
                         help='path to the release-gates manifest (default: design/release-gates.json)')
    parser.add_argument('--route', choices=sorted(ROUTES), default='production',
                         help='which decision to evaluate: production (default, unchanged #39 '
                              'full-gate behavior) or prototype (#24/#43 separate decision)')
    args = parser.parse_args(argv)

    try:
        code, message = run_guard(args.manifest, route=args.route)
    except Exception as e:  # pragma: no cover -- defensive: never let a crash look like a considered refusal (exit 2)
        print(f'ERROR: release_guard.py crashed: {e}', file=sys.stderr)
        return 1

    print(message, file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == '__main__':
    sys.exit(main())
