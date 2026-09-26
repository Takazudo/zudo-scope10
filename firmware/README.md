# Firmware status

The portable core is host-tested. `scope10_diagnostic` is target source for a slow USB CSV input/control diagnostic with the LCD held dark. It is **not the complete monitor firmware**. No UF2, high-rate acquisition guarantee or working LCD backend is claimed.

Run `python3 scripts/test_firmware.py` from the repository root for host tests. Use `PICO_SDK_PATH` and the CMake instructions in the documentation for local target compilation. Integrate the exact Waveshare module driver behind `src/display_port.h`; retain its upstream license and validate its power/interface first.

Do not link an empty successful LCD stub, allocate a full RGB565 framebuffer, auto-zero connected inputs at boot, or suppress acquisition overruns.
