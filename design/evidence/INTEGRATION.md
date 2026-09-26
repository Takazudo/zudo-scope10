# Generator integration (#13): applied evidence deltas, candidate footprints

Applies the deltas written by #3 (`g01-delta.json`), #6 (`g02-delta.json`) and #9
(`g08-delta.json`) to `scripts/make_design.py` and `catalog/*.json`. This is the only
topic that edits those files (epic #1 file-ownership rules); #4/#11 already own the
ERC-clean generator and ran before this topic.

## Summary

**24 of 30 records have a candidate footprint with citation; the rest are OPEN with reason** (see table below). `footprint_qualified` is `false` on every record (unchanged) and no footprint was placed on `.kicad_pcb`, which stays outline-only.

All checks pass after regeneration: `validate.py` (72/72 checks, 224 instances / 134 nets — unchanged from before this topic), `scripts/kicad_check.py` (root ERC 0 unexplained, PCB DRC 0 errors, netlist parity PASS with 0 differences), `test_firmware.py` and `analyze.py`.

G01, G02 and G08 all stay OPEN. No J30/J31 header net was changed.

## Footprint coverage (acceptance line detail)

| Record | Footprint candidate | Reason if OPEN |
|---|---|---|
| tlv9064, mux, ldo, ref, clamp | assigned (verified SOIC-14 / TSSOP-24 / SOT-23-5 / SOT-23-3 / SOT-23 packages) | — |
| button | assigned (`ZudoScope10:SW_XUNPU_TS1088_AR02016_REVIEW`, pad-for-pad per drawing) | — |
| socket20, header20 | assigned (1x20, 2.54 mm, by pitch/count per pico-h/display pin maps) | mechanical stack (mating length, insulator height) stays OPEN |
| r1m…c10u, testpoint (SMD passives) | assigned (0603/0805 per value) | — |
| range | **OPEN** | G02 (#6) resolved the numeric terminal map (C->3, M->2 vendor facts; L->1/H->4 OPEN pending layout orientation) but explicitly left pad geometry/drawn footprint unresolved ("still needs a drawn footprint and real-part fit check") |
| jack | **OPEN** | G02 (#6): 5 physical legs vs 3 logical contacts; leg-to-node map unresolved (drawing table internally inconsistent, third-party footprint contradicts the manufacturer drawing) |
| pot | **OPEN** | unchanged from before this topic: no delta resolves an exact footprint; open question already asks to verify physical terminals first |
| fuse | **OPEN** | G08 (#9) gave a candidate MPN/JLC code (exact spec match, no margin) but no footprint evidence was supplied; still `SPECIFICATION_ONLY` |
| pico-h, display | **OPEN** | external plug-in modules, not placed on the carrier PCB itself (their carrier-side footprints are `socket20`/`header20`, which are assigned) |

## G01 — pending proposal only, header nets unchanged

Per the G01 header-net rule, no J30/J31 net assignment was changed in `scripts/make_design.py` or `design/circuit.json`. The three `g01-delta.json` entries were applied as follows:

| g01-delta entry | Applied as | Citation |
|---|---|---|
| `set_notes` on `parts[ref=J30].notes` | Applied verbatim to J30's generator note (no net change) | Waveshare schematic p1, U5 header / jumpers H1-H6 / Power R11-R15 / LCD BACKLIGHT R16 |
| `set_notes` on `parts[ref=J31].notes` | Applied verbatim to J31's generator note (no net change) | Waveshare schematic p1, Power block U7 RT9193-33 / U5 pos 35-40 |
| `review_decision` on `parts[ref=R88]` | Recorded as `pending_g01_changes` entry `g01-r88-backlight-default` in `design/circuit.json` metadata, **not applied** to R88's value/net; also written up in the power MDX narrative source (`design/narrative-pages.json` → `architecture/power-and-module-interface.mdx`) | Waveshare schematic p1 LCD BACKLIGHT (3A) R16 10K VSYS->LCD_BL/CAT1 EN; RP2040 datasheet §5.5.3.1 Table 622 (PDF p615) |

Extra finding recorded per manager instruction: module R16 (10k, VSYS→LCD_BL) overrides the carrier's R88 (100k, LCD_BL→GND) — the backlight defaults **on**, not off, and the node (~4.5 V) exceeds the RP2040 GPIO absolute maximum (IOVDD+0.5 V) by a small, unmeasured margin. No component value was changed; this is a decision for G01/G06 after the physical module check (see `LOCAL-HANDOFF.md`, #16).

*Update (#41, source #19):* that decision was taken as a design change, not a measurement: GP13 now drives a carrier-side open-drain N-MOSFET (Q1) whose drain is `LCD_BL`, with R88 repurposed as the gate pull-down; the J30/J31 header nets are still unchanged. See `design/evidence/backlight-interface.md`.

`validate.py`'s hard-coded pin-39/GP3/GP5/GP14 checks keep passing unchanged (unaffected by this topic).

## G02 — pin maps and facts added to the catalog

All 14 `g02-delta.json` change entries carry a citation and were applied:

| Target | Applied as |
|---|---|
| `records[id=range].pins` | Catalog pins replaced with numeric terminals `1`/`2`/`3`/`4` (was logical `C`/`L`/`M`/`H`) |
| `parts[record=range]` remap | `scripts/make_design.py`'s `add()` calls for `SW1..SW10` now emit numeric pins via a `RANGE_PIN` map (`C:3, M:2, L:1, H:4`); net graph unchanged (same nets, new pin keys) |
| `records[id=range].facts` / `.open_questions` | Vendor-fact terminal spacing/body/actuator dimensions added; L/H direction marked explicitly OPEN pending layout orientation |
| `records[id=jack].facts` / `.open_questions` | Slot/post/body dimensions and the leg-to-node inconsistency added |
| `parts[record=jack].notes` (`keep_open`) | Already satisfied — the generator's existing jack note text matches the delta's value verbatim; no generator change needed |
| `records[id=button].facts` / `.open_questions` | Variant-code, terminal and pad dimensions added; open questions narrowed to real-part fit only |
| `records[id=display].facts` / `.open_questions` | STEP-derived outline, mounting-hole pitch, socket-row and active-area dimensions added; open questions narrowed (STEP is no longer missing) |
| `records[id=pico-h].facts` / `.open_questions` | Board/hole dimensions and physical pin-1 numbering added; header-height gap noted as still open |
| `records[id=header20].facts` | Mating-length ceiling and display-underside offset added |
| `records[id=socket20].facts` | Pico H clearance inequality added |

## G08 — mpn/jlc_code applied only where cited

`known_listings_recheck` entries (`tlv9064`, `mux`, `ldo`, `clamp`, `range`, `pot`) already had an `mpn`/`jlc_code`; #9 only re-confirmed stock, so no catalog change was needed for these six.

`specification_only_candidates` — applied `mpn`/`jlc_code` (plus a fact citing the LCSC URL, `date_checked` and `listing_not_allocation: true`) for every entry that had a source URL and a checked date; skipped the three with no located citation:

| catalog_id | Result | Note |
|---|---|---|
| r1m, r200k, r4k7, r10k, r100k, r100, r1k, r33, c10n, c1n, c100n | **Applied** | meets_spec: true |
| c470p | **Applied, flagged** | candidate's tolerance (±10%) is looser than the design's 5% max — recorded as an explicit open question, not silently accepted |
| c1u | **Applied, flagged** | nominal/dielectric/voltage confirmed; DC-bias derating not checked |
| c10u | **Applied, flagged** | not wired to any BOM reference; derating not checked |
| fuse | **Applied, flagged** | exact spec match, zero margin above the stated minimums |
| ref | **Applied** | `jlc_code` was previously `null`; set to `C140329` (exact MPN match confirmed by fetch) |
| r249k | **Skipped** | no LCSC/JLC page found or fetched for this value; catalog left `null` |
| socket20, header20 | **Skipped** | only 2x20 dual-row parts were found; no 1x20 single-row page fetched, and mating height is undefined regardless |

`identity_state`/`fit_state` were left unchanged for every G08 record (still `SPECIFICATION_ONLY` / `PROPOSED_NOT_ASSEMBLED`); `factory_order_approved` stays `false` everywhere, matching the AGENTS.md invariant that a listing is not an order.

## Other integrator-owned fixes

- `scripts/fetch_sources.py` now downloads into the gitignored `reference/downloads/` (was the tracked `reference/downloaded/`) and writes its local fetch log to `reference/downloads/source-fetch-local.json` (was the tracked `reports/source-fetch-local.json`).
