# zudo-scope10 — P0 pre-layout handoff

Ten DC-coupled inputs, one portrait 3.5-inch LCD, ten TIME pots and ten RANGE switches.
All soldering is assigned to factory assembly. Pico H and Waveshare SKU 19907 are preassembled plug-in modules.

**This is the waveform-monitor project, not the LED lamp or the five-oscillator instrument.**

**NOT FOR FABRICATION.** The PCB contains only an outline. Native KiCad *placement/routing*, exact physical footprints, display power strap resolution, bench-measured acquisition/protection/power qualification, sourcing, assembly and release approval remain open — every one of the ten release gates (G01–G10) in `design/release-gates.json` stays OPEN, each with partial desk evidence.

Start with [START_HERE.md](START_HERE.md) for orientation, or go straight to **[LOCAL-HANDOFF.md](LOCAL-HANDOFF.md)** for the numbered local procedure covering every gate plus the assembler review and the factory-assembled prototype (no home soldering). The entry point `index.html` opens the offline catalogue and UI simulator. Run:

```sh
python3 scripts/validate.py
python3 scripts/test_firmware.py
python3 scripts/serve.py
```

Browse `http://127.0.0.1:8000/`.

| Directory | Purpose |
|---|---|
| `design/` | Requirements, circuit pin/net graph, GPIO, narratives, release gates |
| `hardware/kicad/` | Eleven generated native schematic drafts, netlist, outline-only PCB |
| `hardware/libraries/` | Embedded review symbol library and one drawing-derived button footprint |
| `catalog/` | Component and source evidence; unknown identities are explicit |
| `doc/` | zudo-doc configuration, generated MDX and public previews |
| `firmware/` | Host-tested portable core, diagnostic + 10 kS/s/ch acquisition targets, clean-room LCD backend — all build clean against the real Pico SDK (no hardware bring-up yet) |
| `reference/` | Retained original ALPS/button/jack assets with provenance |
| `mechanical/` | Ergonomic panel and nominal envelopes, not manufacturing CAD |
| `manufacturing/` | Planning BOM, RFQ, acceptance worksheet, blocking release guard |
| `reports/` | Reproducible analytical and validation reports, not bench measurements |

No Gerber or placement file is emitted. Do not order the outline-only board. No online repo, vendor account or purchase was modified.
