#!/usr/bin/env python3
"""Native KiCad load, ERC summary and netlist parity against design/circuit.json.

Runs kicad-cli (KiCad 9) on the generated root schematic and PCB:
- `kicad-cli sch erc --format json` on the root sheet (full hierarchy);
- `kicad-cli sch export netlist --format kicadxml`, compared with design/circuit.json
  (instance refs, named nets, every pin->net mapping);
- `kicad-cli pcb drc --format json` only to prove the outline-only board loads.

Writes reports/kicad-check.json. ERC totals are recorded as found, not judged: ERC
cleanup is a separate topic. Skips cleanly (exit 0, no report written) when
kicad-cli is absent. Exit 1 when a file fails to load or parity fails.
"""
from collections import Counter, defaultdict
from pathlib import Path
import json, os, shutil, subprocess, sys, tempfile, xml.etree.ElementTree as ET

R = Path(__file__).resolve().parents[1]
KICAD = R / 'hardware/kicad'
ROOT_SCH = KICAD / 'zudo-scope10-p0.kicad_sch'
PCB = KICAD / 'zudo-scope10-p0.kicad_pcb'
REPORT = R / 'reports/kicad-check.json'
EXPECTED_SHEETS = 11
# KiCad names a single-pin net on a no-connect pin "unconnected-(REF-PINNAME-PadN)".
UNCONNECTED_PREFIX = 'unconnected-('


def find_cli():
    return os.environ.get('KICAD_CLI') or shutil.which('kicad-cli')


def run_cli(cli, args):
    r = subprocess.run([cli, *args], capture_output=True, text=True, timeout=600)
    return r.returncode, (r.stdout + r.stderr).strip()


def cli_version(cli):
    code, out = run_cli(cli, ['version'])
    return out.splitlines()[-1] if code == 0 and out else 'unknown'


def erc(cli, tmp):
    out = tmp / 'erc.json'
    code, log = run_cli(cli, ['sch', 'erc', '--format', 'json', '--severity-all', '-o', str(out), str(ROOT_SCH)])
    if not out.is_file():
        return {'loaded': False, 'exit_code': code, 'log': log}
    d = json.loads(out.read_text())
    violations = [v for s in d['sheets'] for v in s['violations']]
    by_type = Counter(v['type'] for v in violations)
    by_sev = Counter(v['severity'] for v in violations)
    by_both = Counter(f"{v['severity']}:{v['type']}" for v in violations)
    return {
        'loaded': True,
        'sheets': len(d['sheets']),
        'sheet_paths': [s['path'] for s in d['sheets']],
        'total': len(violations),
        'by_severity': dict(sorted(by_sev.items())),
        'by_type': dict(sorted(by_type.items())),
        'by_severity_and_type': dict(sorted(by_both.items())),
        'note': 'Recorded as found by kicad-cli; not cleaned. ERC cleanup is a separate topic.',
    }


def export_netlist(cli, tmp):
    out = tmp / 'netlist.xml'
    code, log = run_cli(cli, ['sch', 'export', 'netlist', '--format', 'kicadxml', '-o', str(out), str(ROOT_SCH)])
    if not out.is_file():
        return None, {'exit_code': code, 'log': log}
    return ET.parse(out), None


def parity(netlist, circuit):
    parts = circuit['parts']
    exp_refs = {p['ref'] for p in parts}
    exp_pin = {(p['ref'], pin): net for p in parts for pin, net in p['pins'].items()}
    exp_nets = defaultdict(set)
    for key, net in exp_pin.items():
        if net:
            exp_nets[net].add(key)

    kc_refs = [c.attrib['ref'] for c in netlist.findall('./components/comp')]
    kc_nets = {n.attrib['name']: {(v.attrib['ref'], v.attrib['pin']) for v in n.findall('node')}
               for n in netlist.findall('./nets/net')}
    named = {k: v for k, v in kc_nets.items() if not k.startswith(UNCONNECTED_PREFIX)}
    unconnected = {k: v for k, v in kc_nets.items() if k.startswith(UNCONNECTED_PREFIX)}
    kc_pin = {node: name for name, nodes in kc_nets.items() for node in nodes}

    diffs = []
    dup_refs = sorted(r for r, n in Counter(kc_refs).items() if n > 1)
    if dup_refs:
        diffs.append({'kind': 'duplicate_kicad_ref', 'refs': dup_refs})
    for r in sorted(exp_refs - set(kc_refs)):
        diffs.append({'kind': 'ref_missing_in_kicad', 'ref': r})
    for r in sorted(set(kc_refs) - exp_refs):
        diffs.append({'kind': 'ref_extra_in_kicad', 'ref': r})
    for n in sorted(set(exp_nets) - set(named)):
        diffs.append({'kind': 'net_missing_in_kicad', 'net': n})
    for n in sorted(set(named) - set(exp_nets)):
        diffs.append({'kind': 'net_extra_in_kicad', 'net': n})
    for n in sorted(set(exp_nets) & set(named)):
        if exp_nets[n] != named[n]:
            diffs.append({'kind': 'net_members_differ', 'net': n,
                          'missing_in_kicad': sorted(map(list, exp_nets[n] - named[n])),
                          'extra_in_kicad': sorted(map(list, named[n] - exp_nets[n]))})
    for (ref, pin), net in sorted(exp_pin.items()):
        got = kc_pin.get((ref, pin))
        if net:
            ok = got == net
        else:
            ok = got is not None and got.startswith(UNCONNECTED_PREFIX) and len(kc_nets[got]) == 1
        if not ok:
            diffs.append({'kind': 'pin_net_mismatch', 'ref': ref, 'pin': pin, 'circuit_json': net, 'kicad': got})
    for ref, pin in sorted(set(kc_pin) - set(exp_pin)):
        diffs.append({'kind': 'pin_extra_in_kicad', 'ref': ref, 'pin': pin, 'kicad': kc_pin[(ref, pin)]})

    return {
        'result': 'PASS' if not diffs else 'FAIL',
        'instances': {'circuit_json': len(exp_refs), 'kicad': len(kc_refs)},
        'named_nets': {'circuit_json': len(exp_nets), 'kicad': len(named)},
        'pins_checked': len(exp_pin),
        'no_connect_pins': {'circuit_json_null': sum(1 for v in exp_pin.values() if not v),
                            'kicad_single_pin_unconnected_nets': len(unconnected)},
        'note': ('KiCad emits one "unconnected-(REF-PIN-PadN)" single-pin net per no-connect pin; '
                 'these are compared against null pins in design/circuit.json, not counted as named nets.'),
        'differences': diffs,
    }


def pcb_load(cli, tmp):
    out = tmp / 'drc.json'
    code, log = run_cli(cli, ['pcb', 'drc', '--format', 'json', '-o', str(out), str(PCB)])
    if not out.is_file():
        return {'loaded': False, 'exit_code': code, 'log': log}
    return {'loaded': True,
            'note': ('Load check only. The board is an outline study with no footprints or routing; '
                     'its DRC output is not layout evidence and is not recorded here.')}


def check(write_report=True):
    """Return (report dict or None when kicad-cli is absent, ok flag)."""
    cli = find_cli()
    if not cli:
        return None, True
    circuit = json.loads((R / 'design/circuit.json').read_text())
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        e = erc(cli, tmp)
        netlist, err = export_netlist(cli, tmp)
        p = parity(netlist, circuit) if netlist is not None else {'result': 'FAIL', 'netlist_export_error': err}
        b = pcb_load(cli, tmp)
    root_ok = e['loaded'] and e['sheets'] == EXPECTED_SHEETS
    ok = root_ok and b['loaded'] and p['result'] == 'PASS'
    report = {
        'result': 'PASS' if ok else 'FAIL',
        'scope': ('Native kicad-cli load + ERC totals + netlist parity. NOT a clean ERC, NOT DRC of a '
                  'placed/routed board, NOT layout or fabrication approval. Gate G03 stays OPEN.'),
        'kicad_cli_version': cli_version(cli),
        'root_schematic': {'file': str(ROOT_SCH.relative_to(R)), 'loaded': e['loaded'],
                           'sheets': e.get('sheets'), 'expected_sheets': EXPECTED_SHEETS},
        'pcb': {'file': str(PCB.relative_to(R)), **b},
        'erc': e,
        'netlist_parity': p,
    }
    if write_report:
        REPORT.write_text(json.dumps(report, indent=2) + '\n')
    return report, ok


def main():
    report, ok = check()
    if report is None:
        print('SKIP: kicad-cli not found (install KiCad 9 or set KICAD_CLI); native KiCad check not run.')
        return 0
    p = report['netlist_parity']
    print(f"{report['result']}: root loaded={report['root_schematic']['loaded']} "
          f"sheets={report['root_schematic']['sheets']} pcb loaded={report['pcb']['loaded']} "
          f"ERC total={report['erc'].get('total')} parity={p['result']}"
          + (f" instances={p['instances']['kicad']} nets={p['named_nets']['kicad']} differences={len(p['differences'])}"
             if 'instances' in p else ''))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
