# zudo-scope10 — P0 pre-layout handoff

Ten DC-coupled inputs, one portrait 3.5-inch LCD, ten TIME pots and ten RANGE switches.
All soldering is assigned to factory assembly. Pico H and Waveshare SKU 19907 are preassembled plug-in modules.

**This is the waveform-monitor project, not the LED lamp or the five-oscillator instrument.**

**NOT FOR FABRICATION.** The PCB contains only an outline. Native KiCad review, exact physical footprints, display power/driver integration, fast acquisition and hardware qualification remain open.

Start with [START_HERE.md](START_HERE.md). The entry point `index.html` opens the offline catalogue and UI simulator. Run:

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
| `firmware/` | Host-tested portable core, Pico diagnostic source, LCD adapter contract |
| `reference/` | Retained original ALPS/button/jack assets with provenance |
| `mechanical/` | Ergonomic panel and nominal envelopes, not manufacturing CAD |
| `manufacturing/` | Planning BOM, RFQ, acceptance worksheet, blocking release guard |
| `reports/` | Reproducible analytical and validation reports, not bench measurements |

No Gerber or placement file is emitted. Do not order the outline-only board. No online repo, vendor account or purchase was modified.
