#!/usr/bin/env python3
"""Run simulation/input-channel.cir in ngspice and reconcile with scripts/analyze.py.

Scope: this drives ngspice against the SAME ideal-buffer netlist analyze.py
models analytically (EBUFFER voltage sources, gain=1, infinite headroom).
It is NOT a TLV9064 vendor-model run. A vendor PSpice/TINA model was looked
for (see `vendor_model` in the output) but is not committed here even if
found, because TI's model licences generally forbid redistribution; see
AGENTS.md / catalog licensing rule. This does not close G04.

ngspice's own .control block in the netlist only prints a single DC
operating point (VIN=0) plus an AC sweep. To get the DC transfer's gain and
zero from ngspice itself (not just re-typed from analyze.py), this script
does not hand-edit simulation/input-channel.cir; it copies the netlist into
a temp file and swaps in a control block that runs three `op` points
(VIN=-12, 0, +12) via `alter`, then the same AC sweep already present in the
source file (parameters extracted from it, not re-typed by hand).
"""
from pathlib import Path
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile

R = Path(__file__).resolve().parents[1]
NETLIST = R / "simulation" / "input-channel.cir"
OUT = R / "reports" / "spice.json"

DC_ENDPOINT_V = 12.0
TOLERANCE_PCT = 2.0


def ngspice_available():
    return shutil.which("ngspice") is not None


def build_wrapper(netlist_text: str) -> str:
    lines = netlist_text.splitlines()
    try:
        ctrl_start = next(i for i, l in enumerate(lines) if l.strip().lower() == ".control")
        ctrl_end = next(i for i, l in enumerate(lines) if l.strip().lower() == ".endc")
    except StopIteration:
        raise RuntimeError("simulation/input-channel.cir has no .control/.endc block")

    ac_line = next(
        (l for l in lines[ctrl_start:ctrl_end] if l.strip().lower().startswith("ac ")),
        None,
    )
    if ac_line is None:
        raise RuntimeError("no 'ac ...' line found in the source .control block")

    body = lines[:ctrl_start]
    tail = lines[ctrl_end + 1 :]

    control = [
        ".control",
        "op",
        "print v(bias) v(out)",
        f"alter VIN={DC_ENDPOINT_V}",
        "op",
        "print v(bias) v(out)",
        f"alter VIN=-{DC_ENDPOINT_V}",
        "op",
        "print v(bias) v(out)",
        "alter VIN=0",
        ac_line.strip(),
        "print frequency vdb(out)",
        "quit",
        ".endc",
    ]
    return "\n".join(body + control + tail) + "\n"


def parse_op_points(stdout: str):
    """Return the three v(out) values in the order they were printed."""
    outs = [float(m.group(1)) for m in re.finditer(r"v\(out\)\s*=\s*([-\d.eE+]+)", stdout)]
    if len(outs) != 3:
        raise RuntimeError(f"expected 3 op-point v(out) prints, got {len(outs)}: {outs}")
    return outs  # [VIN=0, VIN=+12, VIN=-12] in script order above


def parse_ac_table(stdout: str):
    """Return sorted (freq_hz, vdb_out) pairs from the 'print frequency vdb(out)' table."""
    rows = []
    for line in stdout.splitlines():
        m = re.match(r"^\s*\d+\t([-\d.eE+]+)\t([-\d.eE+]+)\s*$", line)
        if m:
            rows.append((float(m.group(1)), float(m.group(2))))
    if not rows:
        raise RuntimeError("no AC table rows parsed from ngspice output")
    rows.sort(key=lambda r: r[0])
    return rows


def find_corner_hz(rows, dc_gain_db, drop_db=20 * math.log10(math.sqrt(2))):
    """Interpolate (in log-frequency) the first crossing of dc_gain_db - drop_db."""
    threshold = dc_gain_db - drop_db
    for (f0, v0), (f1, v1) in zip(rows, rows[1:]):
        if v0 >= threshold >= v1:
            if v0 == v1:
                return f0
            frac = (threshold - v0) / (v1 - v0)
            log_f = math.log10(f0) + frac * (math.log10(f1) - math.log10(f0))
            return 10**log_f
    return None


def analytic_cascade_corner_hz(f1, f2):
    """Bisect the -3 dB point of the two-pole cascade analyze.py's response() models.

    Reimplemented here (not imported from analyze.py, which this issue does
    not modify) from the same textbook formula: |H(f)| =
    1 / sqrt((1+(f/f1)^2)(1+(f/f2)^2)).
    """

    def response(f):
        return 1 / math.sqrt((1 + (f / f1) ** 2) * (1 + (f / f2) ** 2))

    target = 1 / math.sqrt(2)
    lo, hi = 1.0, 1_000_000.0
    if response(lo) < target:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if response(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def pct_diff(a, b):
    if b == 0:
        return float("inf") if a != 0 else 0.0
    return abs(a - b) / abs(b) * 100


def try_vendor_model():
    """Report whether a redistributable TI TLV9064 SPICE model was found/run.

    We do not fetch or commit vendor models here: TI's PSpice/TINA model
    licences are not confirmed redistributable (AGENTS.md licensing rule),
    and this environment's outbound proxy is scoped to the sites already
    verified in the issue text, not TI's model-download portal. This is
    reported honestly as "not attempted" rather than faking a fetch.
    """
    return {
        "attempted": False,
        "ran": False,
        "note": (
            "Not attempted: no redistributable TLV9064 PSpice/TINA model licence "
            "was confirmed, so none is fetched or committed per AGENTS.md licensing "
            "rules. The ideal-buffer run above is the only ngspice run this script "
            "performs."
        ),
    }


def main():
    if not ngspice_available():
        print("ngspice not found on PATH; skip (validate_extra check will also skip).")
        return 0

    version_out = subprocess.run(
        ["ngspice", "-v"], capture_output=True, text=True, check=False
    ).stdout
    version_line = next(
        (l.strip() for l in version_out.splitlines() if "ngspice-" in l), ""
    )

    netlist_text = NETLIST.read_text()
    wrapper_text = build_wrapper(netlist_text)

    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_path = Path(tmpdir) / "input-channel-wrapper.cir"
        wrapper_path.write_text(wrapper_text)
        proc = subprocess.run(
            ["ngspice", "-b", str(wrapper_path)],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"ngspice exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}")

    stdout = proc.stdout
    out_zero, out_plus, out_minus = parse_op_points(stdout)
    ac_rows = parse_ac_table(stdout)

    spice_gain = (out_plus - out_minus) / (2 * DC_ENDPOINT_V)
    spice_zero = out_zero
    spice_dc_gain_db = ac_rows[0][1]  # AC sweep starts at 1 Hz, well below both poles
    spice_corner_hz = find_corner_hz(ac_rows, spice_dc_gain_db)

    analysis = json.loads((R / "reports" / "analog-analysis.json").read_text())
    py_gain = analysis["gain_v_per_v"]
    py_zero = analysis["zero_input_adc_v"]
    f1, f2 = analysis["filter_poles_hz"]
    py_cascade_corner_hz = analytic_cascade_corner_hz(f1, f2)

    gain_diff_pct = pct_diff(spice_gain, py_gain)
    zero_diff_pct = pct_diff(spice_zero, py_zero)
    corner_vs_poles_diff_pct = (
        pct_diff(spice_corner_hz, min(f1, f2)) if spice_corner_hz else None
    )
    corner_vs_cascade_diff_pct = (
        pct_diff(spice_corner_hz, py_cascade_corner_hz)
        if spice_corner_hz and py_cascade_corner_hz
        else None
    )

    within_tolerance = (
        gain_diff_pct <= TOLERANCE_PCT
        and zero_diff_pct <= TOLERANCE_PCT
        and corner_vs_cascade_diff_pct is not None
        and corner_vs_cascade_diff_pct <= TOLERANCE_PCT
    )

    report = {
        "scope": (
            "ngspice run of the SAME ideal-buffer netlist analyze.py models "
            "analytically (simulation/input-channel.cir: EBUFFER gain=1, no "
            "op-amp slew/bandwidth/offset, no ADC, no diode/PCB parasitics). "
            "This is NOT a TLV9064 vendor-model run and does not close G04; "
            "see AGENTS.md invariants."
        ),
        "netlist": "simulation/input-channel.cir",
        "ngspice_version": version_line,
        "dc_endpoint_volts": DC_ENDPOINT_V,
        "ngspice": {
            "v_out_at_vin_0": out_zero,
            "v_out_at_vin_plus": out_plus,
            "v_out_at_vin_minus": out_minus,
            "gain_v_per_v": spice_gain,
            "zero_input_adc_v": spice_zero,
            "dc_gain_db": spice_dc_gain_db,
            "minus_3db_corner_hz": spice_corner_hz,
        },
        "analyze_py": {
            "gain_v_per_v": py_gain,
            "zero_input_adc_v": py_zero,
            "filter_poles_hz": [f1, f2],
            "cascade_minus_3db_corner_hz_reimplemented": py_cascade_corner_hz,
        },
        "comparison": {
            "gain_pct_diff": gain_diff_pct,
            "zero_pct_diff": zero_diff_pct,
            "corner_vs_single_pole_pct_diff": corner_vs_poles_diff_pct,
            "corner_vs_two_pole_cascade_pct_diff": corner_vs_cascade_diff_pct,
            "tolerance_pct": TOLERANCE_PCT,
            "within_tolerance": within_tolerance,
            "explanation": (
                "analyze.py's filter_poles_hz lists each RC stage's own pole "
                "frequency (~3392 Hz and ~3386 Hz), not the -3 dB point of the "
                "two of them cascaded; two near-equal single-pole stages in "
                "series cross -3 dB at about 0.64x a single stage's pole, so "
                "comparing ngspice's simulated corner directly against "
                "filter_poles_hz would show a large, expected difference. "
                "This script instead re-derives the cascade's own -3 dB point "
                "from analyze.py's published poles using the same textbook "
                "two-pole formula (reimplemented here, analyze.py itself is "
                "not imported or modified) and compares ngspice against that."
            ),
        },
        "vendor_model": try_vendor_model(),
    }

    OUT.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["comparison"]["within_tolerance"] else 1


if __name__ == "__main__":
    code = main()
    if OUT.exists():
        print(OUT.read_text())
    sys.exit(code)
