#!/usr/bin/env python3
"""G07 power/USB budget: calculation-only, not measured. See reports/power-budget.json.

Every current figure below is either (a) taken from a manufacturer datasheet
downloaded during this pass (cited by URL) or (b) an existing design
allowance already recorded in doc/src/content/docs/architecture/power-and-
module-interface.mdx (cited as such, not as a measurement). Nothing here is
a bench result. G07 stays OPEN regardless of this script's output.
"""
from pathlib import Path
import json
import re

R = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Cited inputs. Each figure carries its source and the exact test condition
# the datasheet states, so a reader can see where a number stops applying.
# ---------------------------------------------------------------------------

CITATIONS = {
    "pico-ds": {
        "title": "Raspberry Pi Pico Datasheet",
        "url": "https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf",
        "retrieved_local": "reference/downloads/pico-datasheet.pdf (gitignored, not committed)",
    },
    "tlv9064-ds": {
        "title": "TI TLV9064 datasheet (SLOS...): quad RRIO amplifier",
        "url": "https://www.ti.com/lit/ds/symlink/tlv9064.pdf",
        "retrieved_local": "reference/downloads/tlv9064.pdf (gitignored, not committed)",
    },
    "74hc4067-ds": {
        "title": "Nexperia 74HC4067/74HCT4067 datasheet, Rev. 10 (25 Jul 2024)",
        "url": "https://assets.nexperia.com/documents/data-sheet/74HC_HCT4067.pdf",
        "retrieved_local": "reference/downloads/74hc4067.pdf (gitignored, not committed)",
    },
    "tlv755p-ds": {
        "title": "TI TLV755P 500 mA low-IQ LDO datasheet",
        "url": "https://www.ti.com/lit/ds/symlink/tlv755p.pdf",
        "retrieved_local": "reference/downloads/tlv755p.pdf (gitignored, not committed)",
    },
    "ref33-ds": {
        "title": "TI REF33xx family datasheet (covers REF3330)",
        "url": "https://www.ti.com/lit/ds/symlink/ref33.pdf",
        "retrieved_local": "reference/downloads/ref3330.pdf (gitignored, not committed)",
    },
    "waveshare-sch": {
        "title": "Waveshare Pico-ResTouch-LCD-3.5 module schematic",
        "url": "https://files.waveshare.com/upload/8/85/Pico-ResTouch-LCD-3.5_Sch.pdf",
        "retrieved_local": "reference/downloads/waveshare-sch.pdf (gitignored, not committed)",
    },
    "waveshare-wiki": {
        "title": "Waveshare Pico-ResTouch-LCD-3.5 wiki page",
        "url": "https://www.waveshare.com/wiki/Pico-ResTouch-LCD-3.5",
        "retrieved_local": None,
    },
    "power-mdx": {
        "title": "Project architecture doc: power-and-module-interface.mdx (design allowances, not measured)",
        "url": "doc/src/content/docs/architecture/power-and-module-interface.mdx",
        "retrieved_local": None,
    },
    "circuit-json": {
        "title": "design/circuit.json (owns the design; component counts and capacitor values below are read from it)",
        "url": "design/circuit.json",
        "retrieved_local": None,
    },
    "module-power-json": {
        "title": "design/evidence/module-power.json (structured module-power evidence: capacitance, backlight topology, the 180 mA claim, verified-schematic/allowance/unknown/rejected status per item)",
        "url": "design/evidence/module-power.json",
        "retrieved_local": None,
    },
    "fuse-catalog": {
        "title": "catalog/components.json record id=fuse (F1 candidate: Littelfuse 1206L050YR, LCSC C163512)",
        "url": "catalog/components.json",
        "retrieved_local": None,
    },
    "power-contract-json": {
        "title": "design/power-contract.json (shared USB source contract, declared descriptor value, override "
        "investigation and per-state power behaviour, consumed by this script and scripts/validate_extra.py "
        "so they cannot disagree)",
        "url": "design/power-contract.json",
        "retrieved_local": None,
    },
    "usb2-default-port": {
        "title": "USB 2.0 default-port current limits (100 mA before configuration, 500 mA once configured with bMaxPower granted) and the "
        "no-inrush-limiting-circuit bulk-capacitance guidance (commonly cited as <=10 uF equivalent at a hot attach), as stated in issue #8",
        "url": "https://github.com/Takazudo/zudo-scope10/issues/8",
        "retrieved_local": None,
    },
}


def load_circuit():
    return json.loads((R / "design/circuit.json").read_text())


def load_module_power_evidence():
    return json.loads((R / "design/evidence/module-power.json").read_text())


def load_catalog():
    return json.loads((R / "catalog/components.json").read_text())["records"]


def load_power_contract():
    return json.loads((R / "design/power-contract.json").read_text())


def parse_cmake_usbd_max_power_targets():
    """#37: per-target USBD_MAX_POWER_MA overrides actually present in
    firmware/CMakeLists.txt, keyed by add_executable() target name. A target
    with no override found relies on the pico_stdio_usb SDK default (see
    design/power-contract.json's override_investigation) -- that is recorded
    as override_ma=None, not treated as a parse failure."""
    text = (R / "firmware/CMakeLists.txt").read_text()
    targets = re.findall(r"add_executable\((\w+)\b", text)
    overrides = {}
    for target in targets:
        # Look for USBD_MAX_POWER_MA=<value> anywhere in a
        # target_compile_definitions(<target> ...) call for this target.
        m = re.search(
            rf"target_compile_definitions\(\s*{re.escape(target)}\b[^)]*\)",
            text,
            re.DOTALL,
        )
        value = None
        if m:
            dm = re.search(r"USBD_MAX_POWER_MA=(\d+)", m.group(0))
            if dm:
                value = int(dm.group(1))
        overrides[target] = value
    return overrides


def evidence_entry(evidence, entry_id):
    return next(e for e in evidence["entries"] if e["id"] == entry_id)


def check_model_circuit_parity(parts, evidence):
    """Explicit model-to-circuit parity checks (issue #35): C30 is on
    +5V_FUSED, F1 sits between VBUS_USB and +5V_FUSED, and the evidence
    file's carrier-capacitance figure matches what design/circuit.json
    actually instantiates. Raises if the model and the evidence disagree."""
    f1 = next(p for p in parts if p["ref"] == "F1")
    f1_nets = set(f1["pins"].values())
    if f1_nets != {"VBUS_USB", "+5V_FUSED"}:
        raise AssertionError(f"F1 parity check failed: expected nets {{VBUS_USB, +5V_FUSED}}, found {f1_nets}")

    c30 = next(p for p in parts if p["ref"] == "C30")
    if "+5V_FUSED" not in c30["pins"].values():
        raise AssertionError(f"C30 parity check failed: expected +5V_FUSED on a pin, found {c30['pins']}")

    computed_farads, _ = cap_farads_on_net(parts, "c", "+5V_FUSED", parse_farads)
    computed_uf = computed_farads * 1e6
    carrier_ev = evidence_entry(evidence, "carrier-5v-fused-capacitance")
    if abs(computed_uf - carrier_ev["value_uf"]) > 1e-9:
        raise AssertionError(
            f"module-power.json carrier-5v-fused-capacitance ({carrier_ev['value_uf']} uF) does not match "
            f"design/circuit.json's +5V_FUSED capacitance ({computed_uf} uF)"
        )


def count_records(parts, record):
    return sum(1 for p in parts if p.get("record") == record)


def cap_farads_on_net(parts, record_prefix, net, value_map):
    """Sum capacitor values (in farads) for parts whose 'record' starts with
    record_prefix and that have `net` on either pin 1 or pin 2."""
    total = 0.0
    hits = []
    for p in parts:
        rec = p.get("record", "")
        # capacitor records in this project are named e.g. "c1u", "c100n" --
        # require a digit right after the prefix so a record like "clamp"
        # (the BAV199 diode) never matches.
        if not (rec.startswith(record_prefix) and len(rec) > len(record_prefix) and rec[len(record_prefix)].isdigit()):
            continue
        pins = p.get("pins", {})
        if net in (pins.get("1"), pins.get("2")):
            f = value_map(p.get("value", ""))
            if f is not None:
                total += f
                hits.append(p["ref"])
    return total, hits


def parse_farads(value):
    v = value.strip().lower()
    try:
        if v.endswith("uf"):
            return float(v[:-2]) * 1e-6
        if v.endswith("nf"):
            return float(v[:-2]) * 1e-9
        if v.endswith("pf"):
            return float(v[:-2]) * 1e-12
    except ValueError:
        return None
    return None


def main():
    circuit = load_circuit()
    parts = circuit["parts"]
    module_power = load_module_power_evidence()
    catalog = load_catalog()
    power_contract = load_power_contract()

    check_model_circuit_parity(parts, module_power)

    n_tlv9064 = count_records(parts, "tlv9064")  # quad amplifiers, 4 amps each
    n_mux = count_records(parts, "mux")
    n_amps = n_tlv9064 * 4

    # --- TLV9064: IQ per amplifier, VS = 5.5V, IO = 0mA (datasheet table 6.6) ---
    # Note: spec condition is VS=5.5V; this rail runs at 3.3V (+3V3A), so the
    # datasheet's own "IQ vs supply voltage" curve implies the real 3.3V IQ is
    # somewhat lower. Using the 5.5V-spec number is a conservative (upper
    # bound) stand-in, not a 3.3V-specific datasheet figure.
    tlv9064_iq_typ_ua = 538.0
    tlv9064_iq_max_ua = 750.0  # 25C limit
    tlv9064_iq_max_hot_ua = 800.0  # -40C..125C limit

    analog_amps_typ_ua = n_amps * tlv9064_iq_typ_ua
    analog_amps_max_ua = n_amps * tlv9064_iq_max_ua
    analog_amps_max_hot_ua = n_amps * tlv9064_iq_max_hot_ua

    # --- 74HC4067: static ICC, VCC=4.5-5.5V (closest bracket to this rail's
    # 3.3V; the mux datasheet's 3.3V-range static-ICC spec is not broken out
    # separately, and VCC=3.3V is inside the device's rated 2.0-10.0V supply
    # range but below the 4.5-5.5V test condition used here). ---
    # No typical value is published for static ICC, only MAX at each temperature bracket.
    mux_icc_max_25c_ua = 8.0
    mux_icc_max_85c_ua = 80.0

    mux_typ_ua = n_mux * mux_icc_max_25c_ua  # use the 25C MAX as the "typical" stand-in; no typ value is published
    mux_worst_ua = n_mux * mux_icc_max_85c_ua

    # --- REF3330: IQ, VIN=5V, ILOAD=0mA (Section 6.5) ---
    ref_iq_typ_ua = 3.9
    ref_iq_max_25c_ua = 5.0
    ref_iq_max_85c_ua = 6.5

    # --- TLV75533PDBVR: ground current, TJ=25C, IOUT=0mA ---
    ldo_ignd_typ_ua = 25.0
    ldo_ignd_max_25c_ua = 31.0
    # -40C..85C max is not separately broken out beyond the 25C max in the
    # extracted table; treat 31 uA as the worst-case stand-in pending a full
    # datasheet table read across temperature.
    ldo_ignd_worst_ua = 31.0
    ldo_dropout_max_mv_at_500ma_3v3 = 238.0  # datasheet headline spec

    analog_rail_typ_ua = analog_amps_typ_ua + mux_typ_ua + ref_iq_typ_ua
    analog_rail_worst_ua = analog_amps_max_hot_ua + mux_worst_ua + ref_iq_max_85c_ua

    analog_rail_typ_ma = analog_rail_typ_ua / 1000.0
    analog_rail_worst_ma = analog_rail_worst_ua / 1000.0

    # --- Fused-5V-side quiescent draw of U10/U11's own bias (IGND is the
    # regulator's own current, drawn from +5V_FUSED in addition to whatever
    # it passes through to +3V3A). Negligible next to the amplifiers, but
    # included for completeness. ---
    ldo_own_current_typ_ma = ldo_ignd_typ_ua / 1000.0
    ldo_own_current_worst_ma = ldo_ignd_worst_ua / 1000.0

    # --- Pico datasheet current brackets (no scenario in the datasheet
    # matches this project's firmware -- ADC free-running + SPI display +
    # buttons, no VGA/audio/SD). Two cited reference points bound plausible
    # current, they do not predict it. ---
    pico_datasheet_bracket = {
        "bootsel_idle_mean_ma_by_temp": {"-25C": 9.4, "25C": 8.7, "85C": 9.0},
        "bootsel_active_mean_ma_by_temp": {"-25C": 10.5, "25C": 9.9, "85C": 10.1},
        "popcorn_vga_avg_mean_ma_by_temp": {"-25C": 85.6, "25C": 86.5, "85C": 88.0},
        "popcorn_vga_max_mean_ma_by_temp": {"-25C": 91.6, "25C": 91.6, "85C": 92.8},
        "note": (
            "Popcorn/VGA benchmark drives a VGA+SD+I2S board this project does not have; "
            "BOOTSEL is USB-idle/active with no ADC/SPI-display/GPIO activity. Neither "
            "scenario is this project's firmware. Cited only to bracket plausibility of "
            "the existing 80 mA Pico allowance, which is itself an allowance, not a "
            "datasheet or measured figure."
        ),
    }
    pico_3v3_pin_recommended_max_ma = 300.0  # datasheet: "recommended to keep the load on this pin less than 300 mA"
    pico_vbus_nominal_v = "5 V +/-10%"
    pico_vsys_range_v = "1.8 V to 5.5 V"

    # --- Existing design allowances (not measured, not datasheet) ---
    allow_display_ma = 300.0
    allow_pico_ma = 80.0
    allow_analog_ma = 40.0
    allow_total_ma = allow_display_ma + allow_pico_ma + allow_analog_ma

    # --- Waveshare module current and backlight topology: sourced from the
    # single structured evidence file (design/evidence/module-power.json),
    # which carries one status per claim so the g01 markdown, this script and
    # the docs cannot disagree. ---
    module_max_current_ev = evidence_entry(module_power, "module-max-current-180ma")
    backlight_topology_ev = evidence_entry(module_power, "backlight-topology")
    backlight_regulator_ev = evidence_entry(module_power, "backlight-regulator-identity")
    display_allowance_ev = evidence_entry(module_power, "display-planning-allowance")

    waveshare_module_current_ma = None  # the only claimed figure (180 mA) is status=rejected; not used in any calculation
    waveshare_current_check_note = (
        f"module-power.json[{module_max_current_ev['id']}]: status={module_max_current_ev['status']}. "
        + module_max_current_ev["uncertainty"]
        + f" The {display_allowance_ev['value_ma']} mA display allowance ({display_allowance_ev['id']}, "
        f"status={display_allowance_ev['status']}) is independent of the rejected claim."
    )

    waveshare_schematic_notes = [
        f"Backlight topology (module-power.json[{backlight_topology_ev['id']}], status={backlight_topology_ev['status']}): "
        + backlight_topology_ev["claim"]
        + ". " + backlight_topology_ev["uncertainty"],
        f"Backlight regulator identity (module-power.json[{backlight_regulator_ev['id']}], status={backlight_regulator_ev['status']}): "
        + backlight_regulator_ev["uncertainty"],
        "The module carries its own onboard 3.3V LDO (U7, marked 'RT9193-33') taking VSYS as "
        "input, with a 1uF capacitor (C11) shown near it; several 100nF ceramics (C1/C2/C7/C8/"
        "C14/C16/C17/C18) appear near VSYS/3V3/LED-A nets. Reported as an observation from the "
        "schematic image, not a bill-of-materials fact -- fitted parts still need a physical check.",
    ]

    # --- Downstream capacitance on the fused 5V path: module VSYS caps and
    # carrier C30, both from design/evidence/module-power.json (module figure
    # is schematic-verified; carrier figure is cross-checked against
    # design/circuit.json by check_model_circuit_parity above). ---
    module_cap_ev = evidence_entry(module_power, "module-vsys-capacitance")
    carrier_cap_ev = evidence_entry(module_power, "carrier-5v-fused-capacitance")
    combined_cap_ev = evidence_entry(module_power, "carrier-plus-module-known-subtotal")

    known_module_cap_uf = module_cap_ev["value_uf"]
    known_carrier_cap_uf = carrier_cap_ev["value_uf"]
    known_downstream_cap_uf = combined_cap_ev["value_uf"]  # carrier + module; Pico-side bulk caps are unknown (see notes)

    inrush_guidance_uf = 10.0  # per issue text: "≤10 µF equivalent at attach"
    inrush_known_status = "exceeds_guidance_figure" if known_downstream_cap_uf > inrush_guidance_uf else "within_guidance_figure"
    inrush_overall_status = "unknown"  # Pico onboard VBUS/VSYS bulk capacitance not found in the datasheet text; this known-figure comparison is not a measured inrush compliance claim

    # --- USB source contract / declared descriptor budget check (#37, source #20) ---
    # design/power-contract.json is the single shared source for the declared
    # descriptor value and the supported-source contract text; this script
    # must not carry its own separate constant for either.
    usb_unconfigured_limit_ma = 100.0
    declared_max_power_ma = power_contract["declared_max_power_ma"]
    cmake_target_overrides = parse_cmake_usbd_max_power_targets()
    cmake_override_values = {v for v in cmake_target_overrides.values() if v is not None}
    cmake_parity_with_contract = cmake_override_values <= {declared_max_power_ma}

    total_allowance_vs_declared = "pass" if allow_total_ma <= declared_max_power_ma else "fail"
    declared_margin_ma = declared_max_power_ma - allow_total_ma

    # The backlight (CAT1 regulator fed straight from VSYS/+5V_FUSED, per the
    # schematic note above) and the carrier's own analog rail power up as
    # soon as +5V_FUSED is present -- there is no firmware-controlled power
    # gate on either path recorded in design/circuit.json. That current is
    # therefore unconditional (design/power-contract.json's honesty section),
    # not staged with USB enumeration/configuration state at all. This is a
    # genuine, calculation-only risk, not a measurement.
    unconfigured_risk_status = "fail_or_unknown"
    unconfigured_risk_note = (
        "No firmware/hardware power gate on +5V_FUSED->display/analog was found in "
        "design/circuit.json (F1 passes +5V_FUSED to both the display header and U10/U11 "
        "unconditionally). If backlight+analog current at attach exceeds 100 mA before the "
        "host completes enumeration and grants any configured allowance, that violates the USB "
        "2.0 default-port unconfigured limit on an ordinary host port. Whether it actually does "
        "depends on the display's un-cited backlight current and is UNKNOWN; if it is close to "
        "the 300 mA allowance, it very likely does. Only a source meeting design/power-"
        "contract.json's source_contract (>=500 mA at 5 V from attach, not established by VBUS "
        "presence alone) is supported; see that file's honesty and decision_notes sections for "
        "why VBUS presence is not treated as a substitute for real USB configuration state, and "
        "for the recorded future configuration-gated load-switch option."
    )

    # --- LDO dissipation, typical and worst case ---
    def ldo_dissipation_mw(vin, vout, iout_ma, ignd_ma):
        # P = (Vin - Vout) * Iout + Vin * Ignd (per REF33xx datasheet's own
        # PD formula shape, Section 8.3; applied here to the TLV75533 LDO).
        return (vin - vout) * iout_ma + vin * ignd_ma

    ldo_vin_nominal_v = 5.0
    ldo_vout_v = 3.3
    ldo_dissip_typ_mw = ldo_dissipation_mw(ldo_vin_nominal_v, ldo_vout_v, allow_analog_ma, ldo_own_current_typ_ma)
    ldo_dissip_worst_mw = ldo_dissipation_mw(ldo_vin_nominal_v, ldo_vout_v, allow_analog_ma, ldo_own_current_worst_ma)

    # --- F1 branch sizing (issue #35 item 3): F1 sits between VBUS_USB and
    # +5V_FUSED and carries display+analog only -- Pico's own supply branches
    # upstream of F1 (scripts/make_design.py J20/J21 vs F1/J30/J31), so F1
    # must be sized from its own branch current, not the total USB allowance.
    # Fields kept separate per the issue: total source current, F1-branch
    # current, the assumed sizing factor/target, and the selected candidate's
    # actual rating. A PPTC is not a precision USB current limiter. ---
    total_source_current_ma = allow_total_ma  # 420 mA: display + pico + analog: the whole carrier's USB draw
    f1_branch_current_ma = allow_display_ma + allow_analog_ma  # 340 mA: only what actually crosses F1 (display + analog); Pico is upstream of F1
    f1_sizing_factor_assumption = 1.5  # ASSUMPTION: common PPTC application margin so normal load never nuisance-trips; not sourced from a specific vendor datasheet
    f1_target_hold_current_ma = f1_branch_current_ma * f1_sizing_factor_assumption  # 510 mA

    fuse_catalog_record = next((r for r in catalog if r["id"] == "fuse"), None)
    f1_candidate_mpn = fuse_catalog_record["mpn"] if fuse_catalog_record else None
    f1_candidate_hold_current_ma = 500.0  # Littelfuse 1206L050YR proposed 500 mA hold, per catalog/components.json record id=fuse
    f1_candidate_derating_note = (
        "No manufacturer temperature-derating curve for the 1206L050YR was retained in this pass "
        "(catalog/components.json's fuse record cites the LCSC/JLC listing only, not a datasheet PDF). "
        "Actual derated hold current at the carrier's operating temperature is UNKNOWN; do not assume "
        "500 mA nominal holds at temperature. A PPTC is not a precision USB current limiter."
    )
    f1_vs_candidate_margin_ma = f1_candidate_hold_current_ma - f1_target_hold_current_ma  # -10 mA: candidate sits just under the naive 1.5x target
    f1_vs_candidate_note = (
        f"The {f1_sizing_factor_assumption}x-derated target of {f1_target_hold_current_ma} mA is "
        f"{abs(f1_vs_candidate_margin_ma)} mA {'above' if f1_vs_candidate_margin_ma < 0 else 'below'} the "
        f"candidate's 500 mA nominal (25C, undetermined temperature) hold rating. This is a nominal-vs-"
        "nominal comparison, not a qualified fit: whoever selects/confirms F1 must reconcile the sizing "
        "margin against the part's actual temperature-derated hold current once that curve is retained."
    )

    report = {
        "basis": "CALCULATION-ONLY, NOT MEASURED. Every input cites a manufacturer datasheet, the "
        "project's own circuit.json, or the existing (non-measured) architecture doc allowance. "
        "No bench, ERC/DRC or thermal result is claimed or implied. G07 stays OPEN.",
        "citations": CITATIONS,
        "assumptions": [
            "TLV9064 IQ is specified at VS=5.5V (datasheet Table 6.6); this project's analog rail "
            "runs at 3.3V, so the real per-amplifier IQ is likely lower than used here. Using the "
            "5.5V-spec number is a deliberately conservative stand-in, not a 3.3V-specific figure.",
            "74HC4067 static ICC is specified at VCC=4.5V-5.5V; this project runs the mux at 3.3V "
            "(inside the device's 2.0-10.0V rated range but below the tested bracket). The 4.5-5.5V "
            "figures are used as the closest available bracket, not a 3.3V-specific figure.",
            "TLV75533 ground current's -40C to 85C maximum was not separately broken out in the "
            "extracted table beyond the 25C max (31 uA); 31 uA is used as a worst-case stand-in "
            "pending a full re-read of that datasheet table.",
            "F1's hold-current sizing factor of 1.5x is a common PPTC application margin, not sourced "
            "from a specific vendor datasheet. It is applied to the F1 branch's own 340 mA "
            "(display+analog) current, not the 420 mA total USB allowance, because F1 sits between "
            "VBUS_USB and +5V_FUSED and does not carry Pico's own supply branch (scripts/make_design.py).",
            "The 1206L050YR candidate's actual temperature-derated hold current is unknown (no "
            "manufacturer curve retained in this pass); its 500 mA figure is the datasheet-style "
            "nominal rating from the catalog listing, not a derated value.",
            "Waveshare module backlight/total current has no citable manufacturer figure found in "
            "this pass (see waveshare_current_check_note); the 300 mA display allowance is carried "
            "forward from the architecture doc unverified.",
            "Downstream capacitance for the USB inrush check sums the verified-schematic module VSYS "
            "capacitance and the carrier's own C30 on +5V_FUSED, both from design/evidence/"
            "module-power.json. Pico's own onboard VBUS/VSYS-side bulk capacitance is not established "
            "here (see pico_notes) -- the known-figure comparison against the informal 10 uF guidance "
            "is not a measured inrush compliance claim, and the overall status stays UNKNOWN.",
            "Pico datasheet has no scenario matching this project's firmware; the BOOTSEL and "
            "Popcorn/VGA figures are cited only as a plausibility bracket around the existing 80 mA "
            "allowance, not a substitute measurement.",
        ],
        "component_counts": {
            "tlv9064_packages": n_tlv9064,
            "op_amp_channels_used": n_amps,
            "mux_74hc4067_packages": n_mux,
            "source": "design/circuit.json parts[] counted by 'record' field",
        },
        "analog_rail_3v3a_quiescent": {
            "basis": "datasheet quiescent/static currents only -- excludes any op-amp output drive "
            "current into a load, which is not modeled here",
            "op_amps_ua": {"typ": analog_amps_typ_ua, "max_25c": analog_amps_max_ua, "max_hot": analog_amps_max_hot_ua, "citation": "tlv9064-ds"},
            "mux_ua": {"max_25c_all_devices": mux_typ_ua, "max_85c_all_devices": mux_worst_ua, "citation": "74hc4067-ds"},
            "reference_ua": {"typ": ref_iq_typ_ua, "max_25c": ref_iq_max_25c_ua, "max_85c": ref_iq_max_85c_ua, "citation": "ref33-ds"},
            "typical_total_ma": round(analog_rail_typ_ma, 3),
            "worst_case_total_ma": round(analog_rail_worst_ma, 3),
            "fits_within_40ma_allowance": analog_rail_worst_ma <= allow_analog_ma,
            "headroom_note": "Quiescent-only totals sit well inside the existing 40 mA carrier allowance; "
            "the remaining headroom covers op-amp output drive current, which this calculation does not model.",
        },
        "ldo_tlv75533": {
            "own_ground_current_ma": {"typ": round(ldo_own_current_typ_ma, 4), "worst": round(ldo_own_current_worst_ma, 4), "citation": "tlv755p-ds"},
            "dropout_max_mv_at_500ma_3v3out": ldo_dropout_max_mv_at_500ma_3v3,
            "dissipation_mw": {
                "formula": "(Vin - Vout) * Iout + Vin * Ignd, per REF33xx datasheet Section 8.3 PD formula shape",
                "vin_v": ldo_vin_nominal_v,
                "vout_v": ldo_vout_v,
                "iout_ma_used": allow_analog_ma,
                "typical": round(ldo_dissip_typ_mw, 2),
                "worst_case": round(ldo_dissip_worst_mw, 2),
            },
        },
        "pico_datasheet_bracket": pico_datasheet_bracket,
        "pico_notes": [
            "Pico VBUS: nominal " + pico_vbus_nominal_v + "; VSYS operating range " + pico_vsys_range_v + " (datasheet Section 3.1/electrical spec).",
            "Datasheet recommends keeping external load on the 3V3 pin under " + str(pico_3v3_pin_recommended_max_ma) + " mA; not directly applicable here since this carrier does not load Pico's 3V3 pin, but cited for completeness.",
            "No VBUS or VSYS input-capacitance figure was found anywhere in the datasheet text (checked). Pico's own onboard bulk capacitance on VBUS/VSYS is therefore UNKNOWN in this pass; the Pico schematic PDF (separate from the datasheet) was not fetched.",
        ],
        "waveshare_module": {
            "current_ma": waveshare_module_current_ma,
            "current_check_note": waveshare_current_check_note,
            "schematic_notes": waveshare_schematic_notes,
        },
        "downstream_capacitance_5v_fused": {
            "known_module_uf": known_module_cap_uf,
            "known_carrier_uf": known_carrier_cap_uf,
            "known_carrier_plus_module_uf": round(known_downstream_cap_uf, 3),
            "citation": "module-power-json",
            "evidence_status": {
                "module": module_cap_ev["status"],
                "carrier": carrier_cap_ev["status"],
                "combined_subtotal": combined_cap_ev["status"],
            },
            "inrush_guidance_uf": inrush_guidance_uf,
            "status_known_figure_only": inrush_known_status,
            "status_overall": inrush_overall_status,
            "overall_status_reason": combined_cap_ev["uncertainty"],
            "not_a_measured_inrush_compliance_claim": True,
        },
        "usb_budget": {
            "basis": "Allowances (design/narrative-pages.json planning figures) vs. the declared USB "
            "descriptor value (design/power-contract.json). Neither is a measurement: "
            "measured_current_ma is None until a bench measurement is recorded (G07 stays OPEN).",
            "documented_allowance_total_ma": allow_total_ma,
            "allowance_citation": "power-mdx",
            "measured_current_ma": None,
            "measured_current_note": "No physical current measurement has been performed. G07 stays OPEN.",
            "unconfigured_limit_ma": usb_unconfigured_limit_ma,
            "declared_max_power_ma": declared_max_power_ma,
            "declared_max_power_citation": "power-contract-json",
            "target_descriptor_inspection": "NOT_RUN (requires ARM build + descriptor dump)",
            "cmake_target_overrides": cmake_target_overrides,
            "cmake_parity_with_contract": cmake_parity_with_contract,
            "vs_declared_limit": {
                "status": total_allowance_vs_declared,
                "margin_ma": declared_margin_ma,
                "note": "A budget allowance greater than power-contract.json's declared_max_power_ma "
                "cannot report 'pass' here -- see design/power-contract.json's override_investigation "
                "for why declared_max_power_ma is currently the unmodified SDK default rather than a "
                "value matching the source contract.",
            },
            "vs_unconfigured_limit": {
                "status": unconfigured_risk_status,
                "note": unconfigured_risk_note,
            },
            "source_contract": power_contract["source_contract"]["requirement"],
        },
        "f1_branch_sizing": {
            "note": "F1 sits between VBUS_USB and +5V_FUSED (design/circuit.json parts[ref=F1]) and "
            "carries display+analog only; Pico's own supply branches upstream of F1 "
            "(scripts/make_design.py). A PPTC is not a precision USB current limiter.",
            "total_source_current_ma": total_source_current_ma,
            "total_source_current_citation": "power-mdx",
            "f1_branch_current_ma": f1_branch_current_ma,
            "f1_branch_current_note": "display allowance (" + str(allow_display_ma) + " mA) + analog allowance (" + str(allow_analog_ma) + " mA); excludes the Pico allowance (" + str(allow_pico_ma) + " mA), which does not cross F1.",
            "sizing_factor_assumption": f1_sizing_factor_assumption,
            "target_hold_current_ma": f1_target_hold_current_ma,
            "selected_candidate": {
                "mpn": f1_candidate_mpn,
                "citation": "fuse-catalog",
                "hold_current_rating_ma": f1_candidate_hold_current_ma,
                "rating_basis": "manufacturer nominal (25C, no temperature curve retained)",
                "derating_from_temperature_curve_ma": None,
                "derating_note": f1_candidate_derating_note,
            },
            "target_vs_candidate_margin_ma": f1_vs_candidate_margin_ma,
            "target_vs_candidate_note": f1_vs_candidate_note,
        },
    }

    (R / "reports/power-budget.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    out = main()
    print(json.dumps({
        "analog_rail_3v3a_quiescent": out["analog_rail_3v3a_quiescent"],
        "usb_budget": out["usb_budget"],
        "downstream_capacitance_5v_fused": out["downstream_capacitance_5v_fused"],
    }, indent=2))
