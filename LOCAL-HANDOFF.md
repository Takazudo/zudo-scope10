# Local handoff — everything that cannot close in a cloud container

Written by issue #16 after re-running every check on the merged base (#2–#15). Read
`VALIDATION.md` and `design/release-gates.json` first for what was already confirmed by desk
work; this file is only the remaining, numbered, local procedure for each gate. No step here
grants CLOSED status by itself — a human closes a gate in `design/release-gates.json` after doing
the step and recording real evidence.

All ten gates (G01–G10) stay OPEN. `python3 manufacturing/release_guard.py` must keep exiting
nonzero until every gate is genuinely closed with real evidence.

## Step 0 — set up the local environment and the missing `main` branch

1. **Create `main`.** This repository has no `main` branch. Create it from the pristine import
   commit and open a PR from the branch carrying this epic's work into it:
   ```sh
   git fetch origin
   git branch main 0c89556                       # pristine import, SHA256SUMS.txt verifies
   git push origin main
   gh pr create --base main --head claude/peaceful-heisenberg-emylp5 \
     --title "P0 desk gates: close every gate reachable without hardware" \
     --body "See issue #1 (epic) and #16 (confirm/roll-up)."
   ```
   Substitute the actual head branch name if it differs from
   `claude/peaceful-heisenberg-emylp5` in your checkout — check `git branch -a` and the epic
   issue (#1) for the current branch carrying the merged work.
2. **Fetch the gitignored vendor files** (Waveshare schematic/CAD/example code, Pico datasheet,
   pico-sdk):
   ```sh
   python3 scripts/fetch_sources.py --execute
   ```
   These land under `reference/downloads/` (gitignored) and are required for G01/G02/G06 local
   review below.
3. **Toolchain**, if not already present: KiCad 9 (the `kicad/kicad-9.0-releases` PPA — **not**
   distro KiCad 7, which cannot read these v8-format files), `arm-none-eabi-gcc` + CMake + Ninja,
   Node 22 + pnpm, `ngspice`.
4. **Browser smoke test dependencies** (used by `scripts/browser_smoke.py`, needed for G09/general
   re-verification, not a gate by itself):
   ```sh
   python3 -m pip install playwright pillow
   python3 -m playwright install chromium
   ```
5. **Docs**: `cd doc && pnpm install && pnpm build`.
6. Re-run the full check suite once locally to confirm the environment matches this session:
   `validate.py`, `test_firmware.py`, `analyze.py`, `kicad_check.py`, `build_firmware.sh` (both
   LCD flags), `run_spice.py`, `make_panel_print.py`, the doc build, `browser_smoke.py`. All
   should PASS exactly as recorded in `VALIDATION.md`.

## G01 — display power/straps and module revision (START_HERE step 2)

Header nets to the display (J30/J31) are committed only after this gate is resolved.

1. Physically inspect the received Waveshare Pico-ResTouch-LCD-3.5 (SKU 19907): read its silked
   revision marking and check which of its own strap resistors/jumpers (H1–H6, R11–R16 per the
   manufacturer schematic) are actually fitted on your unit.
2. Confirm the desk finding in `design/circuit.json`'s `pending_g01_changes[id=
   g01-r88-backlight-default]` and `design/evidence/g01-display-power.md`: module R16 (10k,
   VSYS→LCD_BL) pulls the backlight-enable node toward the module's ~5 V VSYS rail, overriding
   carrier R88 (100k, LCD_BL→GND). With GP13 left high-impedance, the node sits near an estimated
   4.5 V — above the RP2040 GPIO absolute maximum (IOVDD+0.5 V) — and the backlight defaults ON,
   not off. Firmware (`firmware/src/lcd_safe_pins.c` / the SDK init hook) now drives GP13 low
   early, but the power-on / boot-ROM window before that init hook runs is unmeasured. **Bench
   measure the actual GP13 node voltage and the backlight state during that window** on a real
   unit before trusting the firmware mitigation.
3. Decide, and apply exactly one of:
   - **Keep R88** and accept the documented default-on/clamp behaviour (update
     `design/evidence/g01-display-power.md` and this gate with the measured clamp current and the
     accepted risk);
   - **Remove R88** (requires a generator change in `scripts/make_design.py` +
     `catalog/components.json`, regenerate, and re-run the full check suite — this is the only
     kind of change the epic's file-ownership rule restricts to the generator owner, so if you are
     not that person, hand this specific edit back rather than hand-editing outputs); or
   - **Accept and document** as-is with no component change, recording the measured margin.
   Whichever you choose, update `pending_g01_changes[id=g01-r88-backlight-default].status` from
   `OPEN_PENDING_PHYSICAL_CHECK` to a resolved status and cite the actual measurement.
4. Confirm GP2 stays on the on-module PSRAM CS/CE (module position 4) and is left open on the
   carrier — this is already correct in `design/circuit.json` (J30 notes) and must **not** be
   repurposed for the mux address line on the real header.
5. Only after this is resolved, commit the display header nets and consider the display power
   design final.

## G02 — mechanical parts and footprint/pad mapping

`design/evidence/g02-mechanical-pins.md` records every vendor-drawing fact already found; this
step is the real-part check the desk work could not do.

1. **Range switch (NKK SS14MDP2):** C→3 and M→2 are vendor-drawing facts (already applied to
   `catalog/components.json`). L→1 and H→4 were applied by #13 but are **OPEN pending panel
   orientation** — confirm against the actual panel layout (which physical throw position reads
   as low vs. high once mounted) before trusting the schematic-to-panel sense.
2. **Range switch contact suitability (#27/#38):** SS14MDP2 is a silver-contact part
   (`catalog/components.json`'s `range.contact_material`) used in a near-zero-current dry sense
   circuit; NKK's own page Z33 guidance recommends gold contacts for that regime
   (`design/evidence/range-contact.md`). Concrete decision step before this switch is approved for
   the application: (a) request NKK's written confirmation for this exact load (3.3 mA initial
   transient, 100 µs RC decay to leakage/bias current, no continuous wetting current); (b) measure
   contact resistance at the actual load, not a generic continuity check; (c) run a cycling/
   durability check under that same load; (d) run an environmental/cleaning-exposure check against
   the factory's actual flux/wash process. Record results against
   `manufacturing/acceptance-results.csv`'s `RANGE_CONTACT_QUALIFICATION` row and update
   `catalog/components.json`'s `application_suitability_status` only once real evidence exists. Not
   substituted under the decided option (#27 option 2); a manufacturer-supported dry-circuit part
   remains a listed OPEN alternative only.
3. **Jack (SHOU HAN PJ-313 5JCJ):** the leg→contact map is OPEN — the manufacturer drawing does
   not say which physical leg carries which of the 3 logical contacts across its 5 physical legs.
   Get continuity with an ohmmeter on a sample part (no soldering needed), or get written
   confirmation from SHOU HAN/LCSC, before wiring any leg to a specific node.
4. **Waveshare module:** mounting-hole drill diameter and the under-board standoff thread/bore
   need a caliper check on the received module (STEP gives Ø4.30 through-hole, Ø5.5×4.0 mm
   standoff with Ø2.5 bore, but no thread spec).
5. **Pico H:** header height is undefined by any Raspberry Pi source; measure a physical unit.
6. **1×20 2.54 mm strips (J20/J21/J30/J31 mating hardware):** no orderable part is selected yet.
   Once the Pico H header height and the module's standoff height are both measured, compute the
   stack: `design/evidence/g02-mechanical-pins.md` §5 shows the module's own standoffs likely fall
   short of the carrier by `h_ins + 5.0 mm`, meaning **extra spacers (or longer standoffs) will be
   needed** — budget for them in the mechanical BOM.
7. Confirm button (XUNPU TS1088) foot dimensions against a real part; the drawn footprint
   candidate is provisional.
8. Update `catalog/components.json`'s `fit_state`/`identity_state` fields and
   `design/release-gates.json`'s G02 entry once each item above is actually checked.

## G03 — native KiCad validation (finish placement, routing, DRC/ERC)

Desk work already confirms: kicad-cli 9.0.9 loads the root 11-sheet hierarchy and outline-only
PCB; hierarchy ERC is 0 unexplained; outline-board DRC is 0 errors; netlist parity is exact
(224 instances / 134 nets, 0 differences). None of that is placement or routing.

**Ownership (#23/#31): your placement/routing work is safe.** `hardware/kicad/zudo-scope10-p0
.kicad_pro` and `.kicad_pcb` are developer-owned once they exist. `scripts/make_design.py`
only (re)writes them when they are missing, or when explicitly run with `--init-kicad`; an
ordinary run leaves them untouched. `python3 scripts/validate.py` never runs the generators
against this checkout at all — it regenerates everything in a throwaway temp copy and compares
there, so neither a passing nor a failing validation run can touch your PCB/project. Everything
else under `hardware/kicad/` (native schematic sheets, the netlist, `sym-lib-table`) plus
`design/circuit.json`/`gpio.json`/`connections.csv` and `manufacturing/bom-planning.csv` stay
generator-owned and are rewritten on every run — do not hand-edit those.

1. Open `hardware/kicad/zudo-scope10-p0.kicad_pro` in the KiCad 9 GUI. (First time only: if it
   does not exist yet, run `python3 scripts/make_design.py --init-kicad` once to create it and
   the empty-outline PCB.)
2. Assign real footprints for every part still marked OPEN in
   `design/evidence/INTEGRATION.md`'s footprint-coverage table (range, jack, pot, fuse; pico-h/
   display are external modules, not carrier footprints) — only after their real-part fit is
   confirmed under G02.
3. Place all components and route the board (currently outline-only, no copper). Save; it stays
   exactly as saved through any later `make_design.py`/`analyze.py`/`build_docs.py` or
   `validate.py` run.
4. Run the final DRC and ERC on the placed/routed board (not the outline board this session's
   `kicad_check.py` DRC covered) and a schematic-vs-PCB parity check.
5. When real placement/routing exists, set `design/release-gates.json`'s `design_phase` to
   `"layout"` (and later `"qualification"`) so `scripts/validate.py`'s outline-only and
   footprint/factory-approval checks stop assuming pre-layout emptiness and instead require a
   review evidence reference on any record that flips `footprint_qualified` or
   `factory_order_approved` true. This never closes a gate or sets `release_allowed` by itself.
6. Only after this passes clean does G03 become a candidate for CLOSED.

## Assembler review (START_HERE step 5)

1. Save the final KiCad revision after G01–G03 are resolved.
2. Send it to the contracted assembler for a DFM (design-for-manufacture) review. Do not order
   parts or fabrication before this review returns.
3. Record the assembler's findings and resolve them before ordering.

## Factory-assembled prototype (START_HERE step 6) — no home soldering

Per the package `AGENTS.md` and epic invariants: **all electrical soldering, for prototypes too,
happens at a factory or contracted assembler.** This includes every through-hole control (pots,
switches, jacks, buttons) and both module socket/header pairs. The Pico H and the Waveshare module
are pre-assembled plug-in modules that a factory (or the end user, unpowered, into an
already-populated board) plugs in — never a soldering task for the user.

1. Use `manufacturing/RFQ.md` as the basis for a real RFQ once G01–G03 and G08 are resolved enough
   to quote.
2. Order a **completely factory/assembler-soldered** prototype. Reject any assembler proposal that
   defers any soldering, wire link, or header installation to the customer.
3. Receive the assembled board; do not solder anything to it yourself.

## G04, G05, G07 — bench procedures

Desk evidence for all three is recorded (`reports/spice.json`, `reports/analog-analysis.json`,
`firmware/ACQUISITION.md`, `reports/power-budget.json`); none of it is a bench measurement.

`manufacturing/acceptance-results.csv`'s `result` column holds one of four values: `NOT_RUN`
(no measurement attempted yet, the state of every row today), `PASS`, `FAIL`, or `BLOCKED`
(attempted but could not be completed, e.g. missing fixture). `scripts/validate_extra.py`
enforces this set, plus that any `PASS`/`FAIL` row has a nonempty, on-disk `evidence_file`
along with `operator` and `date`.

1. **G04 (input/protection):** using `manufacturing/acceptance-results.csv` as the recording
   template, test powered/unpowered faults, leakage, open-input bias (expect ≈+1.66 V on an
   unplugged input — this is a known, accepted P0 limitation, not a fault), multi-channel
   injection, recovery and loading, per the procedure already narrated in
   `design/narrative-pages.json` → the qualification how-to page. Use a current-limited, low-voltage
   fixture on the same ground before stepping up toward the ±24 V test target.
2. **G05 (acquisition):** flash `firmware/build/scope10_acq.uf2` (LCD off) or use a logic
   analyzer/oscilloscope on GP14 (the timing test point) to measure actual mux settling, real
   sample cadence, missed-slot counters and channel skew against the nominal budget in
   `firmware/ACQUISITION.md`. Also resolve the documented 72 µs vs. 75 µs skew figure mismatch
   between `firmware/ACQUISITION.md` (accurate, 75 µs) and the generated architecture narrative /
   `reports/analog-analysis.json` (stale, 72 µs, from a pre-#12 sketch) — update
   `design/narrative-pages.json`'s "Intended later high-rate schedule" section to describe the
   engine as implemented (not as an unimplemented target) and correct `scripts/analyze.py`'s
   hardcoded `maximum_sequential_channel_skew_us` value, then regenerate `reports/analog-
   analysis.json` and the docs.
3. **G07 (power/USB):** measure backlight/inrush current, Pico current and analog-rail current
   separately (no display / dark display / bright display), and confirm the USB source contract.
   `reports/power-budget.json` flags `vs_unconfigured_limit: fail_or_unknown` — there is no power
   gate tying `+5V_FUSED` to USB enumeration state. F1 carries only the display+analog branch
   (340 mA allowance; see `f1_branch_sizing` in the report), and its 1.5x-derated target of 510 mA
   sits 10 mA above the selected `1206L050YR` candidate's 500 mA nominal (25C) hold rating, with no
   manufacturer temperature-derating curve retained to confirm the part's actual derated hold
   current at operating temperature. Decide whether a soft-start/power-gate (e.g. VBUS-sense before
   enabling the downstream load) is needed, and measure backlight current and module-side VBUS bulk
   capacitance, both currently unknown.

## G06 — firmware/display integration

1. Confirm G01 is resolved first — do not enable `SCOPE_ENABLE_LCD` on real hardware before that.
2. Flash `firmware/build/lcd-enabled/scope10_acq.uf2` (built this session, 0 warnings) to a real
   Pico H wired to a real Waveshare module.
3. Verify all ten panes render, TIME/RANGE controls respond, and HOLD/LINK behave as specified in
   `design/narrative-pages.json`'s controls-and-UI narrative.
4. `firmware/LCD-BACKEND.md` and `firmware/ACQUISITION.md` are the generated firmware how-tos for
   this — confirm the generated docs (`doc/src/content/docs/how-to/*` after `pnpm build`) still
   point at them; if the docs generator is changed later, keep that link (regenerate via
   `design/narrative-pages.json` + `python3 scripts/build_docs.py`, never hand-edit the MDX).
5. The backend is clean-room but uses a few vendor panel-tuning numbers (gamma/VCOM/frame-rate/
   scan/inversion) cited in `firmware/LCD-BACKEND.md`. `LCD_VENDOR_PANEL_TUNING=0` at build time
   excludes them if you decide not to use vendor-derived tuning values — this decision is yours to
   make; the default build in this session's report used them (`LCD_VENDOR_PANEL_TUNING` was not
   set to 0). SPI is conservatively clocked at 15 MHz; raise it locally only after measuring real
   margin on hardware.

## G08 — exact sourcing and factory route

1. Resolve the 3 still-OPEN specification-only rows: `r249k`, `socket20`, `header20` (no LCSC/JLC
   page was located for any of them in this container — search again, or source a 1×20 single-row
   strip from another distributor).
2. Re-verify the 4 applied-but-flagged candidates before ordering: `c470p` (10% tolerance vs. the
   design's 5% max), `c1u`/`c10u` (DC-bias derating not checked), `fuse` (exact spec match, zero
   margin above minimums).
3. Get the assembler's quote using `manufacturing/RFQ.md`; confirm stock/lead-time at quotation
   time (a listing is not allocated stock).
4. Confirm the external module/socket/knob supply chain (genuine Pico H, genuine Waveshare
   SKU 19907) and their exact header orientation with the assembler.
5. **Range switch contact suitability (#27/#38):** same concrete decision step as G02 item 2 above
   — request NKK's written confirmation for the actual 3.3 mA / 100 µs-decay dry-circuit load, then
   run the contact-resistance, cycling/durability and environmental/cleaning-exposure checks
   (`design/evidence/range-contact.md`) — must close before this switch is included in a factory
   order. Zero stock at C6684954 (item 1's sibling concern) is a separate, still-OPEN sourcing
   question; resolving stock does not resolve contact suitability, and resolving suitability does
   not resolve stock.

## G09 — physical review

1. Print `mechanical/print/panel-1to1.pdf` at 100% scale (verify your PDF viewer/printer are not
   auto-scaling).
2. Follow `mechanical/print/README.md` for the review procedure: check real screen readability,
   control spacing, and cable clearance against the print.
3. Accept or reject the mechanical stack (including the G02 spacer/standoff findings above).

## G10 — release approval

1. Do not generate BOM/CPL/Gerbers until G01–G09 are genuinely resolved above.
2. When ready, generate them only from the final saved KiCad revision (after G03's placement,
   routing and final DRC/ERC).
3. Explicitly record release approval in `design/release-gates.json` (`release_allowed: true` and
   every gate `status: "CLOSED"` with real `evidence_files`) only once a human has reviewed the
   real evidence for every gate. `manufacturing/release_guard.py` enforces this refusal until then.

### `manufacturing/release_guard.py` exit-code contract (#28/#39)

The guard is structured as testable functions (`scripts/test_release_guard.py`) with a fixed
contract that CI and `scripts/validate.py` both assert on:

- **`0`** — the manifest is structurally complete (exactly gates G01–G10, unique IDs, correctly
  typed fields) and every gate is `CLOSED` with `evidence_files` that resolve to real files inside
  the repo. This is never automated engineering approval — the guard's own success message says so,
  and a human must still independently review every gate's evidence before a quote is approved.
- **`2`** — intentional REFUSED: the manifest is well-formed but release is not warranted yet
  (`release_allowed` is `false`, a gate is not `CLOSED`, or a `CLOSED` gate's evidence does not
  resolve — missing, a directory, or escaping the repo root). CI and `validate.py` assert exactly
  this exit code for the checked-in manifest, not merely "nonzero".
- **`3`** — malformed manifest: invalid JSON, wrong top-level shape, a non-boolean
  `release_allowed`, an invalid `status`, wrongly-typed `evidence_files`/`evidence_urls`, or a gate
  ID set that is not exactly G01–G10 (duplicates, missing, or unknown IDs).
- **`1`** — the guard itself crashed. This must never be confused with `2`: a crash is not a
  considered refusal.

`evidence_urls` is the typed field for external references; per the contract it is never sufficient
on its own to close a gate. `evidence_partial`/`evidence_partial_note` (added by #31) stay
informational only and are not schema-validated.

Seam for #24 (prototype/production routes): `validate_gates()` currently hardcodes the single
full-release G01–G10 required-ID set. A route-aware caller should compute its own required ID set
(and, if the prototype/production schemas define it, bind evidence to a specific design revision)
and pass it into that function rather than duplicating the validation logic.
