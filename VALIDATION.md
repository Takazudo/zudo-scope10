# Validation status — P0 pre-layout

## Executed checks

- `python3 scripts/validate.py`: **66 structural checks passed**. The component IDs, all 224 physical schematic instances, 134 named nets, module/contact maps, native-file S-expression structure, XML graph equivalence, 11-sheet inventory, source-file hashes, local HTML references and deterministic regeneration were checked.
- `python3 scripts/test_firmware.py`: the portable C code compiled under the host C compiler with warnings treated as errors and passed calibration, 4,096-point logarithmic time, range/debounce/timer-wrap and multiresolution-history assertions. Ten-channel history uses **77,800 bytes** on the tested host ABI.
- `python3 scripts/browser_smoke.py`: local HTML/JavaScript were injected directly into Chromium for DOM/canvas tests. Catalogue search, ten time controls, thirty radio choices, linked-time restoration, HOLD pixel stability and 390px no-horizontal-overflow checks passed. Screenshots are retained in `reports/`.
- Original SVG drawings were rendered to PNG and visually inspected. CadQuery exported a separate nominal envelope STEP/STL. These are concept/ergonomic assets, not populated-board CAD.
- `scripts/analyze.py`: ideal DC transfer, passive filter response, restricted resistor/reference corner enumeration, simple fault-current bounds, acquisition timing budget and framebuffer/SPI arithmetic were recomputed.

## Not executed / not established

| Domain | Status and reason |
|---|---|
| Native KiCad loading/ERC/DRC | NOT RUN: KiCad executable unavailable. S-expression syntax is not native semantic acceptance. |
| Actual footprints and PCB routing | NOT COMPLETE. The board is outline-only; jack/switch/module interfaces remain open. |
| Native zudo-doc install/build | NOT RUN: framework packages were not downloaded. Native source and official bootstrap instructions supplied. |
| ARM/Pico target compilation | NOT RUN: ARM toolchain/Pico SDK unavailable. No UF2 included. |
| Actual Waveshare LCD backend | NOT INTEGRATED. Exact vendor driver and power/header revision require local review. |
| 10 ksample/s/channel engine | TARGET ONLY. Delivered diagnostic is intentionally slow and leaves the LCD dark. |
| HTTP-loaded browser viewer | NOT RUN: loopback navigation returned ERR_BLOCKED_BY_ADMINISTRATOR. Browser policy was not changed. |
| Standalone Three.js ESM/GLB viewer | NOT RUN in browser; original GLB and local vendor modules are included. |
| SPICE using vendor models | NOT RUN. Included ngspice file uses ideal buffers only. |
| Physical fit, thermal/current, immunity, accuracy | NOT TESTED. No assembled hardware exists for this project. |
| JLC sourcing/DFM/assembly acceptance | NOT REQUESTED. No parts were reserved or ordered. |

## Release status

**BLOCKED.** All ten release gates remain OPEN. `python3 manufacturing/release_guard.py` exits nonzero by design. No Gerber, drill package, CPL or approval document is included. The fact that a local structural test passes cannot close a hardware/assembly gate.

See the machine-readable `reports/validation.json`, `reports/firmware-host-tests.json`, `reports/browser-smoke.json`, `reports/analog-analysis.json` and `design/release-gates.json`. Test reports describe only their stated scope.
