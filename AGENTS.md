# zudo-scope10 P0

This is the waveform-monitor project. Keep the five-oscillator project separate.
All electrical soldering must occur at a factory or contracted assembler, including prototypes, headers and wiring. Do not replace an unavailable assembly route with a home-solder instruction.

`design/circuit.json` and `catalog/components.json` own design/evidence; generated KiCad sheets and component MDX are outputs. `scripts/make_design.py` owns circuit construction. Change generators/source together.
No generic package or nominal envelope model is proof of exact fit. No listing is proof of allocated stock or order approval. Do not invent C-numbers, pin mappings, footprints, DRC/ERC or bench results.

Run `python3 scripts/validate.py` and `python3 scripts/analyze.py`. Native KiCad and target firmware builds are separate local gates. `manufacturing/release_guard.py` must refuse until all gates close with evidence.

The 10000 sample/s/channel P0 is a CV/LFO/low-audio development target. It is not a 20 kHz-bandwidth ten-channel instrument. All channels are sampled sequentially. Do not silently relabel time-link as phase synchronization.
