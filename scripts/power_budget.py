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
    "usb2-default-port": {
        "title": "USB 2.0 default-port current limits (100 mA before configuration, 500 mA once configured with bMaxPower granted) and the "
        "no-inrush-limiting-circuit bulk-capacitance guidance (commonly cited as <=10 uF equivalent at a hot attach), as stated in issue #8",
        "url": "https://github.com/Takazudo/zudo-scope10/issues/8",
        "retrieved_local": None,
    },
}


def load_circuit():
    return json.loads((R / "design/circuit.json").read_text())


def count_records(parts, record):
    return sum(1 for p in parts if p.get("record") == record)


def cap_farads_on_net(parts, record_prefix, net, value_map):
    """Sum capacitor values (in farads) for parts whose 'record' starts with
    record_prefix and that have `net` on either pin 1 or pin 2."""
    total = 0.0
    hits = []
    for p in parts:
        rec = p.get("record", "")
        if not rec.startswith(record_prefix):
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

    # --- Waveshare backlight/module current: checked, not found as a citable
    # text figure. A WebFetch summary once reported "5V 180mA" attributed to
    # an FAQ image; the two FAQ images at that URL were downloaded and
    # visually inspected here and contain unrelated screenshots (file
    # browser windows), not a current spec. That claim is rejected rather
    # than reported. ---
    waveshare_module_current_ma = None
    waveshare_current_check_note = (
        "Checked https://www.waveshare.com/wiki/Pico-ResTouch-LCD-3.5 (raw HTML) and "
        "https://www.waveshare.com/pico-restouch-lcd-3.5.htm (raw HTML): no textual mA/current "
        "figure found. A prior automated fetch reported '5V 180mA' from an FAQ image on the wiki "
        "page; both FAQ images (Pico-ResTouch-LCD-3.5-faq.png, -faq2.png) were downloaded and "
        "visually inspected in this pass and show unrelated file-browser screenshots, not a power "
        "figure. That claim is REJECTED, not used. The 300 mA display allowance therefore remains "
        "an allowance with no manufacturer current citation found."
    )

    # --- Waveshare schematic findings (text-extracted; layout order in a
    # PDF text stream does not guarantee correct pin-to-net association, so
    # these are reported as schematic observations, not confirmed facts). ---
    waveshare_schematic_notes = [
        "Backlight LED anode (net LED-A) is fed from VSYS through three parallel resistors "
        "silkscreened '2R' (R17/R18/R19, ~2 ohm each if read correctly) -- a resistor-limited "
        "backlight drive, not a dedicated LED driver IC. LED count, forward voltage and hence "
        "backlight current are NOT recoverable from text extraction alone; G01 already flags this "
        "module's power strapping as requiring visual/physical verification.",
        "The module carries its own onboard 3.3V LDO (U7, marked 'RT9193-33') taking VSYS as "
        "input, with a 1uF capacitor (C11) shown near it; several 100nF ceramics (C1/C2/C7/C8/"
        "C14/C16/C17/C18) appear near VSYS/3V3/LED-A nets. Exact pin association of each part "
        "could not be confirmed from text-only PDF extraction (no page-image render tool was "
        "available in this environment). Reported as an observation, not a bill-of-materials fact.",
    ]

    # --- Downstream capacitance directly on +5V_FUSED, read from design/circuit.json ---
    c30_farads, c30_refs = cap_farads_on_net(parts, "c", "+5V_FUSED", parse_farads)
    carrier_5v_cap_uf = c30_farads * 1e6

    inrush_guidance_uf = 10.0  # per issue text: "≤10 µF equivalent at attach"
    known_downstream_cap_uf = carrier_5v_cap_uf  # carrier-side only; module/Pico-side VBUS/VSYS bulk caps are unknown (see notes)
    inrush_known_status = "pass" if known_downstream_cap_uf <= inrush_guidance_uf else "fail"
    inrush_overall_status = "unknown"  # Pico onboard VBUS/VSYS bulk capacitance not found in the datasheet text, and the module's exact net assignment is unconfirmed (see waveshare_schematic_notes)

    # --- USB 2.0 default-port budget check ---
    usb_unconfigured_limit_ma = 100.0
    usb_configured_limit_ma = 500.0

    total_allowance_vs_configured = "pass" if allow_total_ma <= usb_configured_limit_ma else "fail"
    configured_margin_ma = usb_configured_limit_ma - allow_total_ma

    # The backlight (resistor-driven straight off VSYS/+5V_FUSED, per the
    # schematic note above) and the carrier's own analog rail power up as
    # soon as +5V_FUSED is present -- there is no firmware-controlled power
    # gate on either path recorded in design/circuit.json. That current can
    # therefore start flowing before USB enumeration/configuration
    # completes, when the port is still bound by the 100 mA unconfigured
    # limit. This is a genuine, calculation-only risk, not a measurement.
    unconfigured_risk_status = "fail_or_unknown"
    unconfigured_risk_note = (
        "No firmware/hardware power gate on +5V_FUSED->display/analog was found in "
        "design/circuit.json (F1 passes +5V_FUSED to both the display header and U10/U11 "
        "unconditionally). If backlight+analog current at attach exceeds 100 mA before the "
        "host completes enumeration and grants the configured 500 mA, that violates the USB "
        "2.0 default-port unconfigured limit. Whether it actually does depends on the display's "
        "un-cited backlight current and is UNKNOWN; if it is close to the 300 mA allowance, it "
        "very likely does. This is a design risk to resolve (soft-start/power-gate sequencing "
        "tied to USB enumeration state, e.g. GPIO24 VBUS-sense, or Pico VBUS-present detection "
        "before enabling F1's downstream load), not something this calculation can pass or fail "
        "outright."
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

    # --- PPTC (F1) hold/trip requirement, parametrized (part is TBD) ---
    pptc_derating_factor = 1.5  # ASSUMPTION: common PPTC application margin so normal load never nuisance-trips; not sourced from a specific vendor datasheet since F1's part is TBD
    pptc_ihold_min_ma = allow_total_ma * pptc_derating_factor
    pptc_vs_usb_configured_tension = pptc_ihold_min_ma > usb_configured_limit_ma

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
            "PPTC (F1) hold-current derating factor of 1.5x is a common application margin, not "
            "sourced from a specific vendor datasheet, because F1's exact part is still TBD (see "
            "design/circuit.json note on F1: 'Protection component identity pending').",
            "Waveshare module backlight/total current has no citable manufacturer figure found in "
            "this pass (see waveshare_current_check_note); the 300 mA display allowance is carried "
            "forward from the architecture doc unverified.",
            "Downstream capacitance for the USB inrush check only sums the carrier-side capacitor(s) "
            "on +5V_FUSED found in design/circuit.json (C30, 1uF). The Waveshare module's and Pico's "
            "own onboard VBUS/VSYS-side bulk capacitance are not established here (see "
            "waveshare_schematic_notes and pico_notes) -- the inrush verdict is PASS only for the "
            "known figure, UNKNOWN overall.",
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
            "known_carrier_side_uf": round(known_downstream_cap_uf, 3),
            "known_carrier_side_refs": c30_refs,
            "citation": "circuit-json",
            "inrush_guidance_uf": inrush_guidance_uf,
            "status_known_figure_only": inrush_known_status,
            "status_overall": inrush_overall_status,
            "overall_status_reason": "Module- and Pico-side VBUS/VSYS bulk capacitance are not established (see waveshare_schematic_notes and pico_notes).",
        },
        "usb_budget": {
            "documented_allowance_total_ma": allow_total_ma,
            "allowance_citation": "power-mdx",
            "unconfigured_limit_ma": usb_unconfigured_limit_ma,
            "configured_limit_ma": usb_configured_limit_ma,
            "vs_configured_limit": {
                "status": total_allowance_vs_configured,
                "margin_ma": configured_margin_ma,
            },
            "vs_unconfigured_limit": {
                "status": unconfigured_risk_status,
                "note": unconfigured_risk_note,
            },
        },
        "pptc_f1_requirement": {
            "part_status": "TBD (design/circuit.json: 'Protection component identity pending; not an inrush/load-switch substitute')",
            "derating_factor_assumption": pptc_derating_factor,
            "worst_case_load_used_ma": allow_total_ma,
            "min_hold_current_ma": pptc_ihold_min_ma,
            "tension_with_usb_configured_limit": pptc_vs_usb_configured_tension,
            "tension_note": "A hold current of derating_factor x the 420 mA design allowance ("
            + str(pptc_ihold_min_ma)
            + " mA) exceeds the 500 mA USB configured-port limit's usual safety margin. Either the "
            "420 mA system allowance needs to come down (most likely by getting a real display "
            "current figure), or F1 must be selected nearer the USB limit itself with a smaller "
            "derating margin -- a choice that belongs to whoever selects F1, not to this script.",
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
