# Start here

1. Read the offline catalogue (`index.html`) and operate the synthetic ten-pane UI.
2. Open `doc/src/content/docs/architecture/power-and-module-interface.mdx`: G01 must be resolved before committing the display header nets.
3. Review `catalog/components.json`, `design/connections.csv` and `manufacturing/bom-planning.csv`. Range-switch numeric pins, jack duplicate legs and several supplier identities remain unresolved.
4. Open `hardware/kicad/zudo-scope10-p0.kicad_pro`. These are generated review schematics and an **outline-only** board, not finished PCBA data.
5. Complete the exact footprints, placement, native ERC/DRC and assembler review locally. The full GPIO/header map and repeated circuit are already specified to support that work.
6. Arrange a completely soldered prototype, including all through-hole controls and both module socket/header pairs. A USB-programmable Pico H avoids a soldered debug header at home.
7. Bring up using the conservative diagnostic firmware and the acceptance worksheet; implement and measure the high-rate engine and real LCD backend before claiming the final monitor works.

## What is deliberately different from the previous suggestion

The first carrier uses a documented $19.99-class Waveshare module and headered Pico H rather than an unverified low-price raw LCD/RP2040 layout. Ten controls are retained. The initial acquisition target is 10 ksample/s per channel for CV/LFO and low audio, **not a ten-channel 20 kHz oscilloscope**. The choice can be cost-reduced after actual measurements.

## Known user-visible limitation

The selected unswitched input jack and passive bias network show roughly +1.66 V on an unplugged input. Do not implement automatic startup zeroing. A qualified switched-jack alternative is an explicit later design change.

## Evidence and build status

Read `VALIDATION.md` and `reports/validation.json` for actual checks. Model files are original only where labeled. Native KiCad ERC/DRC, the zudo-doc npm build, Pico target compilation and all hardware tests are not claimed here. Missing manufacturer binaries have local retrieval instructions.
