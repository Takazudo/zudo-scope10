# LCD backend and ten-pane renderer

**Status: a clean-room backend, host-tested models, and target builds only. Gate G06 ("Firmware/display integration") stays OPEN.** Nothing here has been run on a module. The backend is **not compiled unless `scope10_acq` is configured with `-DSCOPE_ENABLE_LCD=1`**, and the default is off until G01 (the module's power path and straps) is physically verified. `scope10_diagnostic` and `pico_diagnostic.c` are unchanged.

The module is the Waveshare Pico-ResTouch-LCD-3.5 (SKU 19907): an ILI9488 panel (vendor wiki) behind a write-only SPI to 16-bit parallel bridge on SPI1. Pins: SCK GP10, MOSI GP11, DC GP8, CS GP9, backlight GP13, reset GP15. Touch CS GP16 and SD CS GP22 stay deselected. MISO GP12 is not used.

## Files

| File | Role |
|---|---|
| `src/display_port.h` | The unchanged contract, plus `SCOPE_DISPLAY_WIDTH/HEIGHT` and the meaning of a `false` return. |
| `src/lcd_bridge.[ch]` | Portable bridge framing, the init table, the address window, clipping, and blit/fill. No RP2040 headers. |
| `src/display_waveshare.c` | RP2040 SPI1/GPIO bus for `lcd_bridge` and the `display_port.h` implementation. It fails with `#error` unless `SCOPE_ENABLE_LCD=1`. |
| `src/scope_render.[ch]` | The ten-pane portrait renderer, which draws `scope_core` history in small rectangles. It also holds the debounced HOLD/LINK toggle. |
| `src/lcd_safe_pins.[ch]` | The "LCD dark, all SPI1 slaves deselected" pin state. It is applied from an SDK runtime-init hook before `main()`, in **both** flag states. |
| `tests/test_lcd.c` | Host tests, run by `scripts/test_firmware.py`. They include a bit-level model of the bridge and a minimal ILI9488 memory model. |

## Build

```sh
python3 scripts/test_firmware.py                             # host tests, includes test_lcd
PICO_SDK_PATH=... bash scripts/build_firmware.sh             # builds both flag states
cmake -S firmware -B firmware/build -DSCOPE_ENABLE_LCD=1     # manual LCD configuration
```

`build_firmware.sh` builds three UF2s and records each one's warning count in `reports/firmware-target-build.json`:

- `firmware/build/scope10_diagnostic.uf2`
- `firmware/build/scope10_acq.uf2`: LCD off, the default
- `firmware/build/lcd-enabled/scope10_acq.uf2`: `SCOPE_ENABLE_LCD=1`, reported as `scope10_acq+lcd`

Build-time knobs:

- `SCOPE_LCD_SPI_HZ` (default 15 MHz)
- `LCD_VENDOR_PANEL_TUNING` (default 1; see Licensing)

## Licensing decision: clean-room, nothing vendor-owned committed

The source is `https://files.waveshare.com/upload/f/fc/Pico-ResTouch-LCD-X_X_Code.zip`, SHA-256 `a489c0b03b274ede3eef5f6470d960da6aba4500f55522c5ac1068ed3f95779a`. It is the same archive as the `display-code` source in `design/evidence/g01-display-power.md`. It was retrieved on 2026-09-26 into the gitignored `reference/downloads/`.

**No licence covers the driver code.** The archive has no LICENSE file. The files that carry the 3.5-inch driver have no licence grant or copyright notice at all, only "Author: Waveshare team":

- `C/lib/lcd/LCD_Driver.c` (SHA-256 `4b837c51…`)
- `C/lib/config/DEV_Config.[ch]` (`f64da8ee…` for the `.c`)
- `Python/3inch5/main_3inch5.py` (`80fc3d6e…`)

**The licences that do appear cover other files:**

- `C/examples/lcd_test.c` and `main.h` carry an MIT-style permission text with no copyright line. It covers those example files only, and nothing from them is used.
- `C/lib/fatfs` is under ChaN's licence and the fonts are under STMicroelectronics' BSD-3. Neither is used.
- `Python/2inch8/nanoguilib` is MIT (Peter Hinch) and is for a different panel. It is not used.

**Decision:** the vendor code is not copied, ported or committed. The backend was written from:

- the ILI9488 datasheet V1.00 (2012-11-28): §4.7.5 16-bit MCU interface, §5.2.13 SLPOUT, §5.2.22–24 CASET/PASET/RAMWR, §5.2.30 MADCTL, §5.2.34 COLMOD, §5.3.7 DISCTRL, §13.4 reset timing. It was fetched from lcdwiki.com, SHA-256 `aeb23170…`, and is not committed.
- the module schematic (`display-sch` in the G01 evidence);
- a behavioural description of the vendor driver: which pins it uses, how it frames commands and parameters, and which registers it programs. The vendor code is cited as a reference, not reproduced.

**Facts taken from the vendor reference and the reason for each:**

- **Pin numbers.** They already agree with `design/gpio.json` and the G01 evidence.
- **Word layout.** Parameters and pixels go out as 16-bit words, MSB first.
- **Portrait scan setting:** MADCTL `0x08` (BGR = 1) with DISCTRL SS = 1. This orientation and colour order depend on how the glass is wired, which the IC datasheet cannot give.
- **INVON.**
- **Panel analogue tuning:** power control 3 `C2h`, VCOM `C5h`, frame rate `B1h`, gamma `E0h/E1h`. These are numerical parameters of this glass, not expressive code, and they cannot be derived from the IC datasheet.

**Reviewer decision:** whether these numeric facts are acceptable. Building with `LCD_VENDOR_PANEL_TUNING=0` leaves them out and keeps the datasheet defaults, so the image quality may differ.

`catalog/sources.json` is owned by the generator-integrator topic (#13) and was not edited. #13 may add a `display-code` note that points here.

## Bridge framing (derived from the module schematic, "LCD SPI ->16BIT", Sch p1 1A–2A)

- **U1 74HC4040:** `~CP` = SCLK, so it counts falling edges. `MR` = LCD_CS, so it is held reset while CS is high. `Q3` = `CLK/16`.
- **U2, U3 74HC4094:** `CP` = SCLK, so they shift on rising edges. U2 `DATA` = MOSI, and U2 `QS1` feeds U3 `DATA`. `STR` = `CLK/16`, so the latch is transparent while it is high. The outputs are D0–D7 (U2) and D8–D15 (U3). After 16 clocks, the first bit sent sits on D15.
- **U4, printed "74HC04D":** its input is `CLK/16` and its output is `LCD_CLK`, the panel's WRX. The symbol is drawn with 74HC164 pin names, so the inversion is inferred from the part label, not from the drawn symbol.

**What follows from these connections, with CS low:**

- WRX falls after the 8th clock, and rises (the panel latches) on the 16th falling edge.
- By then the latch holds the complete word.
- D/CX is sampled at that edge, so D/C is changed only while CS is high.
- SPI mode 0, 8-bit frames, MSB first.

**Framing used: every bus write is one whole 16-bit word.**

- A command goes out as `0x00cc` and each parameter as `0x00pp`. The ILI9488 reads commands and parameters on D7–D0, and D15–D8 are "don't care".
- A pixel goes out as one RGB565 word, with COLMOD `0x55`, meaning DBI = 101, 16 bit/pixel on the 16-bit bus (datasheet §4.7.5.1).
- There is no RGB666 path anywhere, and a host test asserts it.

**Deviation from the vendor C driver.** The vendor driver sends each command as a **single byte**. On this bridge an 8-clock frame completes only when CS goes high: MR resets the counter, so CLK/16 falls and WRX rises at the same moment the panel's CSX deasserts. That write therefore depends on propagation-delay ordering. `test_lcd.c` shows this in the bridge model: vendor-style command framing produces one CS-release strobe, while `lcd_bridge.c` produces none over the whole init, blit and render sequence.

## GP13 backlight: driven early, never released

- **The hazard (G01 evidence):** module R16 10k runs from VSYS (5 V) to `LCD_BL`, the backlight regulator's EN. With the carrier's R88 100k pull-down, an undriven GP13 settles near 4.5 V. That is above the RP2040 absolute maximum of IOVDD + 0.5 V, and it turns the backlight **on**.
- **The mitigation:** `lcd_safe_pins.c` registers `PICO_RUNTIME_INIT_FUNC_HW(lcd_safe_pins_apply, "00110")`, which drives GP13 low. It also sets LCD CS, touch CS and SD CS high and holds RST low.
  - The hook runs just after the SDK's `runtime_init_early_resets` (priority 00100), which releases IO_BANK0/PADS_BANK0 and does not reset them again.
  - It runs before clock setup (00500) and `main()`.
  - The pin order is value, then output enable, then function select, so the pin never floats or glitches.
  - `scope10_acq.elf.map` confirms the order: `.preinit_array.00100`, `.00101`, `.00110`, …, `.00500`.
  - The hook disassembles to register writes and `gpio_set_function` only, with no library calls, so it does not depend on the later runtime-init steps.
  - `main()` re-applies it without calling `gpio_init()`, because `gpio_init()` would briefly release the pin.
- **The window firmware cannot cover:** power-on reset, the boot ROM and boot2 up to the hook. Its duration is not measured. The R88 / R16 decision recorded in `design/evidence/g01-delta.json` remains the hardware answer.
- **Backlight on/off only.** `scope_display_backlight(p > 0)` drives GP13 high, and only after a successful init. The regulator (CAT1) is unidentified, so PWM dimming on its EN is not assumed.
- **Driven high is also an estimate.** With GP13 driven high, R16 sources roughly (5 − 3.3) V / 10 kΩ ≈ 0.17 mA into the pin while it is held at IOVDD. This is an estimate, not a measurement.

## Renderer

**Layout.** Portrait 320 × 480, with ten 160 × 96 panes in two columns of five. Numbering is column-major, to match the physical control banks: CH1–CH5 fill the left column top to bottom and CH6–CH10 the right, so CH6 is top right. `scripts/validate_extra.py` checks this numbering against the simulator (`doc/public/prototype/scope-ui.js`) and the panel study (`mechanical/panel-layout-study.json`). Each pane has five parts:

- a label row above the plot (`scope_pane_label_rect`, 144 × 10): the two-digit channel ID `01`…`10` in the channel colour, the debounced range `±3V` / `±5V` / `±8V` (`±?V` while the range is unknown, `range == -1`), and the window duration, right-aligned;
- a 4-px channel colour tag to the left of the plot;
- a 144 × 66 plot (`SCOPE_PLOT_W` × `SCOPE_PLOT_H`), independent of the 192-bin `SCOPE_HISTORY_BINS`. It spans the requested TIME window (see **Window**), with the newest sample at the right;
- a status row below the plot (`scope_pane_status_rect`, 144 × 10): a status-token slot for `UNCAL` / `CLIP` / `SAT` (set through `scope_render_input.status_token`; nothing sets it yet), then `LINK` and `HOLD`, each shown only while that mode is latched;
- a separator row.

**Text.** Both text rows are a grid of 24 cells, each 6 × 10 px. Glyphs are 5 × 7 from a clean-room font defined in `scope_render.c` as a `const` table: digits, `. + - ± ? V m s k` and the capitals needed for `HOLD LINK UNCAL CLIP SAT`. `scope_pane_field_rect()` gives each field's rect. Each field is one render item, drawn two cells (120 px) per `scope_display_rect` call. The last drawn string and colour of each field are cached per pane, and a field is redrawn only when either changes. A field whose transfer fails is retried on the next pass.

**Window.** Each pane spans the whole requested TIME window, independent of the storage level. `scope_window_map()` in `scope_core.c` does the mapping as a pure function, without pixels:

- **Window.** W = round(`scope_time_seconds(code)` × `samples_per_s`) samples (`scope_window_samples()`), from 20 samples (2 ms) to 81 920 samples (8.192 s) at 10 000 samples/s. The code is the pane's own, or CH1's under LINK (`scope_render_time_code()`), so independent and linked panes share one mapping.
- **Level.** The smallest history level L with 192 × 2^L ≥ W. Level 9 holds 98 304 samples, so the existing ten levels cover 8.192 s with no extra RAM.
- **Columns.** The pane takes the newest n = ceil((W − lag) / 2^L) level-L bins. Here lag is the samples still in lower levels' pending halves, which are not yet displayable. If n > 144, each column merges the min/max of its bin range, so an extreme anywhere in the window stays visible. If n < 144, each bin is repeated across several columns.
- **Tolerance.** The represented interval, counted in samples before the newest sample, is [lag, lag + n × 2^L). Each edge is within one coarse bin (2^L samples) of the requested [0, W): 0 ≤ lag < 2^L and W ≤ lag + n × 2^L < W + 2^L. One coarse bin is at most 512 samples, 51.2 ms at level 9.
- **Partial history.** The time axis always spans the full window. The retained bins sit right-aligned, and columns with no retained sample are left blank.

All duration text comes from `scope_render_window_label()` (`2.0ms` … `99.9ms`, `100ms` … `999ms`, `1.00s` … `8.19s`). It formats W / `samples_per_s`, the same W the plot maps, so the label names the represented interval within the tolerance above.

**HOLD and LINK.**

- HOLD freezes the plots, including a pass already part-way through a pane. The text keeps updating.
- LINK makes every pane use CH1's TIME window, and the duration text turns the LINK colour. This is a **time-link of views, not phase synchronisation**: channels are still sampled sequentially (see `ACQUISITION.md`).
- Both are press-to-toggle with 20 ms debounce, on the active-low GP0/GP1.

**Transfer size.**

- There is no framebuffer.
- A plot column is one 1 × 66 rectangle.
- Fills are split to at most 128 pixels per `scope_display_rect` call.
- `scope_render_step()` issues up to four items per pass of the `scope10_acq` main loop, between drain batches.

**Nominal transfer time at 15 MHz.** These figures come from bit counts only. They are not measured and exclude GPIO/CS overhead.

| Transfer | Size | Time |
|---|---|---|
| Plot column | 154 B | ≈ 82 µs |
| Text, one pane, every field changed (13 calls, 25 cells) | ≈ 3.3 KB | ≈ 1.8 ms |
| Text, unchanged | 0 | 0 |
| Full pass of ten panes | — | ≈ 0.13 s |
| Init | 1 + 120 + 120 + 20 ms of waits, plus a 307 200 B clear (≈ 164 ms) | ≈ 0.43 s |

Init runs before acquisition starts. The ring's overrun headroom is 7168 samples, about 60 ms, which is much longer than one render pass step. Overruns stay counted, never hidden.

**A failed rectangle is counted.** Every rectangle whose `scope_display_rect` returns `false` is counted in `rects_failed` and is never reported as drawn. `scope_display_init()` returning `true` means only that the sequence was **transmitted**. The bridge has no read path, so no panel presence or ID can be read back. The boot line says so: `lcd,init_sequence_sent=1 (no panel readback exists; not a display verification)`.

## Host test coverage (`tests/test_lcd.c`)

The tests cover:

- word serialisation (MSB first);
- exact command and parameter byte framing and D/C per byte;
- every write strobed with CS low under the bridge model;
- the CS-release dependency of vendor single-byte commands;
- init order (SLPOUT first, ≥ 5 ms wait, COLMOD `0x55`, MADCTL portrait, DISPON last, no RAMWR);
- clipping, including zero area, off-screen, exact fit and uint16 overflow;
- clipped blits landing at the right GRAM addresses with the source stride preserved;
- full-screen fill;
- explicit 2 × 5 column-major rectangles for CH1, CH5, CH6 and CH10 (pane, plot, label and status), plus in-bounds, pane and part disjointness;
- code-to-row monotonicity;
- column spans;
- window levels;
- a full render pass through blit → bridge model → GRAM, checking trace, tag and separator;
- the font (every glyph distinct and five columns wide) and `scope_render_window_label()` at both TIME endpoints and every code in between;
- text decoded back from GRAM against the font table: channel ID and channel colour on every pane, and range, duration and status token checked for CH1, CH6 and CH10, including range changes, `±?V` and both TIME endpoints;
- text call counts: 130 per pass when every field is new (13 per pane), 0 when nothing changed, and only the changed field redrawn otherwise;
- more history bins than plot columns: only the newest 144 bins are drawn, right-aligned;
- HOLD (no plot transfers, even when pressed mid-pane; `HOLD` shown);
- LINK (CH1 window and duration text on every pane, `LINK` shown, own window restored when LINK is released);
- counting of backend failures;
- button debounce.

These are models of this repository's reading of the schematic and datasheet. They are not evidence about the physical module.

## Local G06 procedure (after G01 is physically closed)

**A blank or wrong screen is not by itself a firmware fault.** Work through the G01 items first:

- R11 fitted;
- the H1–H6 jumpers in the SPI position;
- CAT1 identity;
- the module revision.

**Steps:**

1. Measure GP13 (`LCD_BL`) on an oscilloscope from power-on. Record the voltage and duration before the hook drives it low, and confirm that the backlight stays off until the `lcd,init_sequence_sent` line appears.
2. Flash `firmware/build/lcd-enabled/scope10_acq.uf2`. Record its SHA-256 from `reports/firmware-target-build.json`. Expect a black screen, then panes. CH1 is at the top and its tag is yellow; a blue CH1 tag means the BGR/colour order is wrong. The newest data is at the right.
3. Check the ten panes against known inputs, and each pane's RANGE box against its switch. Check the TIME bar and window against the knob. Check that HOLD freezes the plots, and that LINK applies CH1's window to every pane.
4. Watch the USB counters (`overrun_events`, `missed_slots`) with the LCD running and compare them with the LCD-off build.
5. If the screen stays blank, retry with a lower `SCOPE_LCD_SPI_HZ`, then with `LCD_VENDOR_PANEL_TUNING=0`. Record every result. Do not mark G06 closed from a partial pass.

## Open items

- **All of G06 on hardware:** display output, orientation and colour order, the ten panes, TIME/RANGE, controls, HOLD, LINK, and render/acquisition coexistence.
- **SPI rate:** the 15 MHz default is a conservative choice, not a measured limit. The vendor wiki reports 60 MHz tested.
- **GP13 before the hook:** the voltage during the uncovered pre-hook window, and whether R88 should change (G01 delta).
- **Reviewer decision** on the vendor panel-tuning values (see Licensing).
- **Documentation:** the generated firmware how-to (`design/narrative-pages.json` → `doc/`) still says that LCD integration remains open. That text is still true, but it does not yet point to this file.
