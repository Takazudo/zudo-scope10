# Start here

**All local (hardware, GUI, ordering) work now has a single numbered procedure:
[`LOCAL-HANDOFF.md`](LOCAL-HANDOFF.md).** It starts with Step 0 (create the missing `main`
branch, fetch vendor files, set up tooling) and covers G01–G10 plus the assembler review and the
factory-assembled prototype. This section stays as a short orientation.

1. Read the offline catalogue (`index.html`) and operate the synthetic ten-pane UI.
2. Open `doc/src/content/docs/architecture/power-and-module-interface.mdx`: G01 must be resolved before committing the display header nets. See `LOCAL-HANDOFF.md`'s G01 section for the pending R88 backlight-default decision.
3. Review `catalog/components.json`, `design/connections.csv` and `manufacturing/bom-planning.csv`. Desk work resolved the range switch's C/M numeric pins and several supplier identities (`design/evidence/g02-mechanical-pins.md`, `design/evidence/g08-sourcing.md`); L/H pin orientation, the jack's duplicate-leg map, and a few sourcing rows remain OPEN — see `LOCAL-HANDOFF.md`.
4. Open `hardware/kicad/zudo-scope10-p0.kicad_pro`. The schematic sheets are generated review output; the PCB starts **outline-only**, not finished PCBA data. `scripts/kicad_check.py` confirms native load, 0 unexplained hierarchy ERC and exact netlist parity — that is not placement, routing or a final DRC. `.kicad_pro`/`.kicad_pcb` are yours once created: `scripts/make_design.py` only writes them when missing or with `--init-kicad`, and `scripts/validate.py` regenerates in an isolated temp copy rather than in this checkout, so your placement/routing is never overwritten (#23/#31; see `LOCAL-HANDOFF.md`'s G03 section).
5. Complete the exact footprints, placement, native ERC/DRC and assembler review locally. The full GPIO/header map and repeated circuit are already specified to support that work.
6. Arrange a completely soldered prototype, including all through-hole controls and both module socket/header pairs, **at a factory or contracted assembler — never at home.** A USB-programmable Pico H avoids a soldered debug header there too.
7. Bring up using the conservative diagnostic firmware and the acceptance worksheet; implement and measure the high-rate engine and real LCD backend before claiming the final monitor works. The high-rate acquisition engine and the clean-room LCD backend are already implemented and build clean against the real Pico SDK (`firmware/ACQUISITION.md`, `firmware/LCD-BACKEND.md`); they still need bench measurement and real-hardware bring-up, not implementation.

## What is deliberately different from the previous suggestion

The first carrier uses a documented $19.99-class Waveshare module and headered Pico H rather than an unverified low-price raw LCD/RP2040 layout. Ten controls are retained. The initial acquisition target is 10 ksample/s per channel for CV/LFO and low audio, **not a ten-channel 20 kHz oscilloscope**. The choice can be cost-reduced after actual measurements.

## Known user-visible limitation

The selected unswitched input jack and passive bias network show roughly +1.66 V on an unplugged input. Do not implement automatic startup zeroing. A qualified switched-jack alternative is an explicit later design change.

## Evidence and build status

Read `VALIDATION.md` and `reports/validation.json` for actual checks. Model files are original only where labeled. Native KiCad load/hierarchy-ERC/outline-DRC, the zudo-doc npm build, Pico target compilation (all firmware targets, LCD flag on and off) and the HTTP browser smoke are now RUN and PASS in a cloud container — see `VALIDATION.md`'s "Executed checks" table. Real KiCad placement/routing/final-DRC and every hardware/bench/assembly/ordering step are not claimed here; `LOCAL-HANDOFF.md` gives the numbered local procedure for each one. `python3 scripts/fetch_sources.py --execute` retrieves the gitignored manufacturer binaries.
