# Validation status — P0 pre-layout

Rolled up by issue #16 on the merged base (all of #2–#15). Every check below was re-run in this
session on this tree; results and report paths are current as of this commit.

## Executed checks

- `python3 scripts/validate.py`: **79 structural checks passed**. 224 physical schematic
  instances, 134 named nets, module/contact maps, native-file S-expression structure, XML graph
  equivalence, 11-sheet inventory, source-file hashes, local HTML references and deterministic
  regeneration. (`markdown-it-py` absent in this container; `offline/*.html` regenerates in its
  fallback mode, which the check tolerates.)
- `python3 scripts/test_firmware.py`: the portable C core (including the real `acq_engine.c`,
  `scope_core.c`, `lcd_bridge.c`, `scope_render.c`) compiled under the host C compiler with
  warnings as errors and passed calibration, 4,096-point logarithmic time, range/debounce/
  timer-wrap, multiresolution-history, uniform-slot acquisition, ring wrap/overrun, injected-stall
  missed-slot accounting, channel-order invariance, and LCD bridge framing/clipping/pane-layout
  assertions. Ten-channel history: 77,800 bytes. Acquisition engine RAM: 49,496 bytes; IRQ budget
  240 cycles.
- `python3 scripts/analyze.py`: ideal DC transfer, passive filter response, restricted
  resistor/reference corner enumeration, simple fault-current bounds, acquisition timing budget
  and framebuffer/SPI arithmetic recomputed. `reports/analog-analysis.json`,
  `reports/filter-response.csv`.
- `python3 scripts/kicad_check.py`: **PASS** — kicad-cli 9.0.9 loads the root
  `hardware/kicad/zudo-scope10-p0.kicad_sch` (11-sheet hierarchy) and the outline-only
  `.kicad_pcb`. Hierarchy ERC total 0, 0 unexplained; outline-board DRC 0 errors/warnings/
  unconnected items; netlist parity PASS (224 instances / 134 nets, 0 differences).
  `reports/kicad-check.json`. This is not placement/routing or a final DRC of a populated board.
- `PICO_SDK_PATH=<pico-sdk 2.1.1> bash scripts/build_firmware.sh`: **PASS**, all three targets,
  arm-none-eabi-gcc 13.2.1, `-Wall -Wextra`, 0 warnings: `scope10_diagnostic` (67,584 B),
  `scope10_acq` (LCD off, 81,920 B), `scope10_acq+lcd` (`-DSCOPE_ENABLE_LCD=1`, 93,696 B).
  `reports/firmware-target-build.json`.
- `python3 scripts/run_spice.py`: **PASS**, ngspice 42 on the ideal-buffer netlist
  (`simulation/input-channel.cir`) matches `analyze.py`'s analytic model within a 2% tolerance
  (gain diff 1.8e-5%, zero diff 1.5e-5%, cascade-corner diff 0.06%). No vendor TLV9064 SPICE model
  is used or committed (no confirmed redistributable licence). `reports/spice.json`.
- `python3 scripts/make_panel_print.py`: **PASS**, regenerates `mechanical/print/panel-1to1.svg`
  and `.pdf` deterministically (via rsvg-convert).
- `cd doc && pnpm install && pnpm build`: **PASS**, 74 pages built (46 generated MDX +
  framework pages) via the real `@takazudo/zfb`/`@takazudo/zudo-doc` packages (not previously run
  in any container). `reports/doc-generation.json` records the Python codegen step only
  (`build_docs.py` cannot see the outcome of the `zfb build` step that runs after it, so its
  `native_zudo_doc_build` field stays `"NOT_RUN"` by construction — the native build's actual
  PASS is this line plus the browser-smoke check below). Non-fatal warnings only: one
  `@takazudo/zudo-doc-history-server` optional git-metadata plugin is absent (informational),
  and 13 pre-existing broken image links inside a vendored manufacturer HTML asset
  (`reference/assets/pot/manufacturer-page.html`), unrelated to this build.
- `python3 scripts/browser_smoke.py` (HTTP mode, Chromium via Playwright + Pillow): **PASS**, all
  6 checks including the offline catalogue, the ten-pane UI (time controls, radios, link-restore,
  HOLD freeze, no 390px overflow, no console errors), the GLB viewer, and the **built** zfb site
  in `doc/dist` served over HTTP (getting-started + components pages). No `not_run` entries;
  loopback navigation is not blocked in this container. `reports/browser-smoke.json`.

## Not executed / not established

| Domain | Status and reason |
|---|---|
| KiCad GUI footprint placement, PCB routing, final DRC/ERC on a populated board | NOT RUN: needs a local KiCad GUI session (G03). Native load + hierarchy ERC + outline DRC + netlist parity are RUN and PASS (above); that is not placement or routing. |
| Actual footprints / real-part fit for range, jack, pot, fuse, pico-h, display, socket20/header20 mating | NOT RUN: needs the physical parts (G02). Vendor-drawing facts and 24/30 candidate footprints are RUN and recorded; see `design/evidence/g02-mechanical-pins.md` and `design/evidence/INTEGRATION.md`. |
| G01 physical module revision/strap check and the pending R88 backlight-default decision | NOT RUN: needs the physical Waveshare module (G01). Desk evidence and the pending proposal are RUN and recorded; see `design/evidence/g01-display-power.md` and `design/circuit.json`'s `pending_g01_changes`. |
| SPICE with the vendor TLV9064 model; powered/unpowered fault, leakage, injection, recovery bench tests | NOT RUN: no confirmed redistributable TLV9064 SPICE model, and all of this needs bench equipment (G04). The ideal-buffer ngspice run is RUN and PASSES against the analytic model (above). |
| Acquisition bench measurement: mux settling, real sample cadence, missed-slot counters on hardware, alias response, cross-talk | NOT RUN: needs bench equipment (G05). The host-tested cycle-level model of the real engine is RUN and PASSES (above); it is a model, not a measurement. |
| Real LCD bring-up: ten panes, time/range, controls, HOLD, LINK on the actual display | NOT RUN: needs the physical display and G01 resolved first (G06). The clean-room backend builds clean against the real SDK with `SCOPE_ENABLE_LCD=1` (RUN, above); nothing was flashed or observed. |
| Power/USB bench measurement: backlight/inrush current, Pico + analog rail, USB enumeration sequencing | NOT RUN: needs bench equipment and a power gate design decision (G07). Desk arithmetic is RUN; it flags `vs_unconfigured_limit: fail_or_unknown` — see `reports/power-budget.json`. |
| Sourcing: stock allocation, quote, factory acceptance of the BOM | NOT RUN: no parts reserved or ordered (G08). mpn/jlc_code candidates for cited specification-only rows are RUN and applied (11 of 14; 3 stay OPEN: r249k, socket20, header20) — see `design/evidence/g08-sourcing.md`. |
| Physical panel print review: readability, control/cable clearance, stack acceptance | NOT RUN: needs a physical print and the real parts (G09). The deterministic 1:1 print-sheet generator is RUN and PASSES (above). |
| Assembler DFM review of the saved KiCad revision | NOT RUN: needs a local session with an assembler (`LOCAL-HANDOFF.md` step "Assembler review"). |
| Factory-assembled prototype order (no home soldering) | NOT RUN: needs a local ordering decision (`LOCAL-HANDOFF.md` step "Factory-assembled prototype"). |
| Release approval / BOM/CPL/Gerber export | NOT RUN: `manufacturing/release_guard.py` refuses while any gate is OPEN (G10, RUN and confirmed refusing, below). No export exists. |
| Physical fit, thermal/current, immunity, accuracy | NOT TESTED. No assembled hardware exists for this project. |

## Known unreconciled figure (documentation, not a gate)

`firmware/ACQUISITION.md` documents the acquisition engine's real budget: 9 slots of 8.333 µs
each between CH1 and CH10, i.e. a **75 µs** channel skew. `reports/analog-analysis.json` and the
generated architecture narrative (`design/narrative-pages.json` → `doc/.../architecture/
acquisition.mdx`) still quote **72 µs**, a figure from an earlier 8 µs-slot sketch that predates
the #12 engine; `firmware/ACQUISITION.md` already states this discrepancy in its own budget
table. Reconciling the narrative source is not a one-line fix: the surrounding paragraph frames
the schedule as an "intended", unimplemented target, which is no longer accurate now that #12
shipped the real engine, so a proper fix means rewriting that paragraph's framing, not just
swapping a number. Left for local follow-up; see `LOCAL-HANDOFF.md`.

## Release status

**BLOCKED.** All ten release gates remain OPEN, each with an `evidence_partial` list in
`design/release-gates.json`. `python3 manufacturing/release_guard.py` exits nonzero (confirmed
this session) by design. No Gerber, drill package, CPL or approval document is included. A
passing desk/structural/host/native-tooling check cannot close a hardware, GUI-routing, bench,
sourcing or assembly gate.

See the machine-readable `reports/validation.json`, `reports/firmware-host-tests.json`,
`reports/firmware-target-build.json`, `reports/kicad-check.json`, `reports/spice.json`,
`reports/browser-smoke.json`, `reports/doc-generation.json`, `reports/power-budget.json`,
`reports/analog-analysis.json` and `design/release-gates.json`. Test reports describe only their
stated scope. `LOCAL-HANDOFF.md` gives the numbered local procedure for everything above marked
NOT RUN.
