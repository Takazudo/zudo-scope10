# Firmware status

The portable core is host-tested. `scope10_diagnostic` is target source for a slow USB CSV input/control diagnostic with the LCD held dark. It is **not the complete monitor firmware**. No high-rate acquisition guarantee or working LCD is claimed. A clean-room LCD backend and ten-pane renderer exist but are compiled only with `-DSCOPE_ENABLE_LCD=1` and are not hardware-verified; see `LCD-BACKEND.md` (G06 OPEN).

Run `python3 scripts/test_firmware.py` from the repository root for host tests. Use `PICO_SDK_PATH` and the CMake instructions in the documentation for local target compilation. The Waveshare backend behind `src/display_port.h` is a clean-room implementation because the vendor driver carries no licence (`LCD-BACKEND.md`); validate the module power/interface (G01) before enabling it.

Do not link an empty successful LCD stub, allocate a full RGB565 framebuffer, auto-zero connected inputs at boot, or suppress acquisition overruns.
