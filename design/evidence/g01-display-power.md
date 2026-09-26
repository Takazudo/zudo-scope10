# G01 desk evidence: Waveshare Pico-ResTouch-LCD-3.5 power path and straps

Status: **evidence_partial**. G01 stays OPEN. This is a desk reading of the manufacturer schematic, and nothing here comes from a physical module. Fitted parts, the strap population and the module revision still need a check on the received board.

## Sources read

| ID | Source | Retrieved (UTC) | SHA-256 |
|---|---|---|---|
| display-sch | `https://files.waveshare.com/upload/8/85/Pico-ResTouch-LCD-3.5_Sch.pdf` (2 pages, A4 landscape, PDF modDate 2021-05-14, no revision field) | 2026-09-26T09:58Z | `0547c5fd3dc4fce9e20941b756aa8e348ea47e4d24851e745a04a0c24a5f3b41` |
| display-code | `https://files.waveshare.com/upload/f/fc/Pico-ResTouch-LCD-X_X_Code.zip` (`C/lib/config/DEV_Config.h`) | 2026-09-26T09:58Z | `a489c0b03b274ede3eef5f6470d960da6aba4500f55522c5ac1068ed3f95779a` |
| display-wiki | `https://www.waveshare.com/wiki/Pico-ResTouch-LCD-3.5` (HTML; pin table and FAQ) | 2026-09-26 | `9b7bb24fb1f4db522e2bb0b26380a59b5aec8f70f4a3c30e95eec0210080877b` |
| pico-ds | `https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf` | 2026-09-26T09:58Z | `757ff485227493b9fcc0c2c96c4dea9de020e1d8b2b11e2aa4f9ee8b25aa89eb` |
| rp2040-ds | `https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf` | 2026-09-26 | `be56fbb75ba0ae9e26558a73c93ac3e75c2ad4e6878d3b6703de2a76d886ea8c` |
| rt9193-ds | `https://www.richtek.com/assets/product_file/RT9193/DS9193-18.pdf` (DS9193-18, June 2022) | 2026-09-26 | `600a0eef69bc2c3827f668e3b71d83b746738ee1bf7484f86483a7ca51686b8f` |

Each schematic page was rendered to PNG with PyMuPDF (MuPDF 1.28.2) at 200 dpi, and the areas that mattered were rendered again at 400–800 dpi. I read the images directly. The PNGs are **not committed**, because Waveshare's download terms do not clearly allow redistribution. They can be regenerated from the PDF above into the gitignored `reference/downloads/`.

Citation format: `Sch p1 <col><row>` uses the schematic frame grid (columns 1–4, rows A–D). The section titles are the ones printed on the sheet.

## Answers

### 5 V enters on VSYS (position 39); no diode or regulator at the entry

- The module's Pico footprint U5, position 39, carries net `VSYS` (Sch p1 2B–3C, "Pi pico (40P)"). The module uses `VSYS` for two things only: the input of U7 (RT9193-33, 3V3 LDO; Sch p1 4D "Power") and the input of CAT1 (backlight regulator; Sch p1 3A "LCD BACKLIGHT").
- The entry has **no diode, fuse or switch** on the module. VSYS goes straight to C10 1 µF, C9 10 µF, C14 100 nF, C15 100 nF and the regulator VIN pins (Sch p1 3A, 4D).
- Position 40 carries a net label `VBUS` drawn in the green style that this sheet uses for header-only labels. No other `VBUS` label appears anywhere on either page, so the module draws **nothing from VBUS** (Sch p1 3B).
- The wiki pin table agrees: "VCC — VSYS — Power input", with "Operating voltage: 5V".
- When stacked the way Waveshare intends, the Pico's own VSYS supplies the module. That VSYS is USB VBUS after the Pico's D1 Schottky (pico-ds §4.4–4.5, PDF p21). The carrier instead feeds display position 39 from `+5V_FUSED` = Pico VBUS (J21-1, position 40) → F1. The module therefore sees about one Schottky drop *more* than it would when stacked. USB VBUS nominally stays within RT9193's recommended VIN of 2.5–5.5 V (rt9193-ds p3, 6 V absolute maximum).

### Regulator and straps: 3V3 is generated on the module; no contention under the carrier wiring

- **U7 RT9193-33** (Sch p1 4D): pin 1 VIN = VSYS, pin 2 GND, pin 3 EN = `VCC_EN`, pin 4 BP = C12 22 nF, pin 5 VOUT = module `3V3` with C11 1 µF. RT9193 is a 300 mA LDO with 220 mV typical dropout at 300 mA (rt9193-ds p1, p3).
- **Enable straps** (Sch p1 4D, lower half), with values as printed on the schematic:
  - R11 **0R**, from `VSYS` to `VCC_EN` (fitted per schematic: EN follows VSYS)
  - R12 **NC**, from `3V3_EN` (position 37) to `VCC_EN`
  - R14 **NC**, from `GPIO14` (position 19) to `VCC_EN`
  - R13 **100K**, from `VCC_EN` to GND
- **3V3 source strap:** R15 **NC**, from `Pico3V3` (position 36) to module `3V3`. With R15 not fitted, the module's `3V3` rail (74HC4040/4094/04, XPT2046, TF slot, PSRAM, LCD FPC pins 6/7/12) comes **only from U7**. It is not taken from the Pico header.
- Page 2 (board silkscreen, mirrored) shows these straps grouped under the labels "VSYS / 3V3 / GP14" next to R11–R15 (Sch p2, upper centre). The schematic values are design intent only. Which parts are actually fitted is **UNRESOLVED** until the physical module is checked.
- **Contention verdict: none under the carrier's proposed wiring, whichever strap variant is fitted.** J31 leaves positions 36 (`Pico3V3`) and 37 (`3V3_EN`) unconnected, and J30 leaves position 19 (`GPIO14`) unconnected. Even if R15, R12 or R14 were fitted, none of them could tie U7's output or its EN to the Pico's 3V3 or 3V3_EN.
  - If R12 or R14 were fitted *together with* R11 0R, a directly stacked Pico would have VSYS tied to its 3V3_EN, or to GP14. The carrier's isolation of those positions prevents that.
- **Failure mode the carrier creates:** a module strapped with R11 removed and only R12 or R14 fitted would have EN held low by R13 on the carrier, because positions 37 and 19 are open. The module 3V3 would never start and the display would stay blank. The physical check must confirm R11 is fitted.

### Other supply pins: 3V3_EN and ADC_VREF

- **3V3_EN (position 37):** reaches the module only through R12 (NC) to `VCC_EN` (Sch p1 4D). With R12 not fitted, the module does not use it. It is safe to leave open on the carrier.
- **ADC_VREF (position 35):** header-only green label. No other `ADC_VREF` label appears on either page, so the module does not use it (Sch p1 3B).
- **3V3 (position 36):** net `Pico3V3`. It reaches the module only through R15 (NC) (Sch p1 4D).
- **VBUS (position 40):** not used (see the 5 V entry above).
- The Pico datasheet confirms what these pins are on the Pico side: 3V3_EN is pulled up to VSYS through 100 kΩ, and ADC_VREF is the filtered 3.3 V (pico-ds PDF p9).

### Spare-position nets: conflicts on GP2, GP5 and GP14 are all avoided because those positions are open

The carrier uses GP2–GP5 for the mux address and GP14 for the timing test point. Module net on each display position (Sch p1 2B–3C, U5), and what the carrier's J30/J31 does with it:

| Pos | GPIO | Module net | Module use | Carrier (J30/J31) | Conflict if connected |
|---|---|---|---|---|---|
| 1, 2 | GP0, GP1 | GPIO0/1 (green) | none | open | — |
| 4 | **GP2** | **SRAM_CS** | U8 ESP-PSRAM64H CE, R20 10K pull-up to module 3V3 (Sch p1 3D) | open | **Yes.** Mux ADDR0 would select the PSRAM, which then drives the shared MISO (U8 SIO1 = `MISO`, GP12) during LCD/touch/SD transfers. With position 4 open, R20 keeps the PSRAM deselected. |
| 5 | **GP3** | GPIO3 (green) | none | open | none found |
| 6 | GP4 | GPIO4 (green) | none | open | none found |
| 7 | **GP5** | **SDIO_CLK** | H6 pin 1, a 3-way solder jumper selecting the TF-card clock between SDIO_CLK and SCLK (Sch p1 2D–3D; silkscreen legend "A SPI / B SDIO", Sch p2 right) | open | **Strap-dependent.** In the SDIO jumper position, mux ADDR3 would clock the TF card. In the SPI position it has no load. |
| 9, 10 | GP6, GP7 | GPIO6/7 (green) | none | open | none found (carrier GP7 = MUX_DISABLE stays Pico-only) |
| 17 | GP13 | LCD_BL | CAT1 EN, **R16 10K pull-up to VSYS** (Sch p1 3A) | connected (R64 33 Ω, R88 100k to GND) | see the backlight finding below |
| 19 | **GP14** | **GPIO14** | R14 (NC) to `VCC_EN` (Sch p1 4D) | open | **Strap-dependent.** With R14 and R11 both fitted, GP14 would be tied to VSYS (5 V). With R14 NC it has no load. |
| 22 | GP17 | TP_IRQ | XPT2046 PENIRQ, R2 100K pull-up to 3V3 (Sch p1 1B–2C) | open | none. Touch firmware must poll, because the IRQ is not routed. |
| 24–27 | GP18–21 | SDIO_CMD/D0/D1/D2 | H1/H2/H3/H5 jumpers (Sch p1 2D–3D) | open | none. In the SDIO jumper position the TF card would be unusable on the carrier. |
| 29 | GP22 | SDIO_D3/SD_CS | TF slot CD/D3 | SD_CS_N | intended |
| 30 | RUN | RUN | K1 push button to GND (Sch p1 3B) | open | none. The module's reset button does nothing on the carrier. |
| 31, 32, 34 | GP26–28 | GPIO26/27/28 (green) | none | open | none (carrier ADC inputs stay Pico-only) |

Two further observations:

- The vendor C driver (`DEV_Config.h`) uses GP8 DC, GP9 CS, GP10 CLK, GP11 MOSI, GP12 MISO, GP13 BL, GP15 RST, GP16 TP_CS, GP17 TP_IRQ and GP22 SD_CS on `spi1`. It never references GP2, GP5 or GP14, and it matches the carrier's signal contract.
- The wiki pin table lists SDIO_CLK = GP5 but does not mention SRAM_CS/GP2 or the GP14 strap. **The schematic, not the wiki, is the authority for those.**

### Backlight pull-up to VSYS defeats the carrier pull-down on LCD_BL (GP13)

R16 10K runs from `VSYS` to `LCD_BL`, which is the CAT1 EN pin (Sch p1 3A, confirmed on an 800 dpi crop). On the carrier, `VSYS` = `+5V_FUSED`, and `LCD_BL` also carries R88 100k to GND. Whenever GP13 is high-impedance (reset, boot ROM, before firmware drives the pin):

- The node settles near 5 V × 100k / 110k ≈ 4.5 V. That is above RP2040's absolute maximum pin voltage of IOVDD + 0.5 V (rp2040-ds §5.5.3.1, Table 622, PDF p615). The pin's protection structure conducts at roughly (4.5 V − ~3.8 V) / 9.1 kΩ, which is below 0.1 mA. This is an estimate, not a measurement.
- The backlight is **on** by default, not off. The carrier doc's statement "LCD backlight has a pull-down" does not give a backlight-off default with this module.

The same R16-to-VSYS arrangement exists when the Pico is stacked on the module as Waveshare intends, so this is vendor design behaviour, not a carrier error. It is listed here as a decision for G01/G06 (see the delta), with no net change proposed.

### Current and inrush figures for G07

- **Module maximum: REJECTED, not a citable figure.** "5V 180mA" was reported by an earlier automated fetch summary of a wiki FAQ image; both FAQ images at that URL were downloaded and visually inspected in a later pass and show unrelated file-browser screenshots, not a power spec, and no textual mA/current figure was found on either wiki page. This claim is rejected, not carried as a manufacturer maximum. See `design/evidence/module-power.json` (`module-max-current-180ma`, status `rejected`) — that file is the single source of truth for this claim so `scripts/power_budget.py` and this document cannot disagree. The carrier's 300 mA planning allowance (`display-planning-allowance`, status `allowance`) is independent of the rejected claim.
- **Module 3V3 rail:** RT9193 limit of 300 mA (rt9193-ds p1).
- **Backlight:** CAT1 (5-pin regulator: VIN, GND, EN, BYP, VOUT) feeds `LED-A` (FPC pin 33). The three LED cathode returns, FPC pins 34/35/36, each go to GND through R17/R18/R19 **2R** (Sch p1 3A, 4A–C "LCD"). Recorded structurally in `design/evidence/module-power.json` (`backlight-topology`, status `verified-schematic`).
  - **UNRESOLVED:** CAT1's part number and output voltage are not printed, and the LED forward voltage is unknown. The backlight current cannot be derived from the schematic.
- **Bulk capacitance on VSYS (inrush-relevant):** C9 10 µF + C10 1 µF + C14 100 nF + C15 100 nF ≈ **11.2 µF** (Sch p1 3A, 4D). Recorded in `design/evidence/module-power.json` (`module-vsys-capacitance`, status `verified-schematic`); combined with carrier C30 (1 µF, on `+5V_FUSED`) that gives a **12.2 µF** known carrier+module nominal subtotal (`carrier-plus-module-known-subtotal`) — a known-figure subtotal against the informal ≤10 µF inrush guidance, not a claim of measured inrush compliance. Pico-side bulk capacitance is still unknown, so overall inrush status stays UNKNOWN and G07 stays OPEN.
- **Other module capacitors:**
  - On 3V3: C11 1 µF plus 100 nF decouplers C1, C2, C7, C8, C18, C19, C20, C21.
  - On LED-A: C17 100 nF.
  - C16 100 nF on CAT1's BYP pin, C12 22 nF on U7's BP pin.
  - Capacitance inside the LCD panel FPC is not shown and is **UNRESOLVED**.

### Pico VBUS→VSYS cross-check: the proposal stays within limits

- Pico VBUS is the micro-USB 5 V. VSYS = VBUS − D1 Schottky drop, with an allowed range of 1.8–5.5 V (pico-ds PDF p9, p12, p21).
- The carrier leaves Pico VSYS (J21-2, position 39) unconnected and takes `VBUS_USB` from Pico position 40 (J21-1). Display current therefore flows through the Pico's micro-USB connector and VBUS trace but **not** through D1. Nothing on the display side can back-feed Pico VSYS.
- The display's position 39 is a separate net on the carrier. The limit that applies to it is RT9193's VIN (≤ 5.5 V recommended, 6 V absolute maximum), which USB 5 V meets. CAT1's input limit is unknown, because its part is unidentified.
- The current rating of the Pico's VBUS pin and trace for the added display load is not stated in pico-ds. It remains a G07 item.

## Verdict: keep the current netlist proposal

Keep position 39 fed from `+5V_FUSED`, and keep positions 35, 36, 37 and 40 isolated. Also keep positions 4, 7, 19, 22, 24–27 and 30 open: the schematic shows that each one either conflicts with the carrier's use of the same GPIO or depends on a strap. `design/evidence/g01-delta.json` proposes no net or pin edits. It proposes documentation notes and one flagged review decision (R88 / LCD_BL).

## Open questions only the physical module can answer

1. Module revision marking: silkscreen or label version, and whether it matches this 2021-05-14 schematic.
2. Fitted straps: R11 = 0R fitted; R12, R14, R15 not fitted; R13 = 100K.
3. Position of solder jumpers H1–H6, SPI (A) versus SDIO (B). The carrier needs SPI.
4. Whether U8 (PSRAM) is fitted, and the R20 value.
5. CAT1 part marking, which gives the backlight regulator identity and output voltage, and from those the backlight current.
6. Which SD pull-up option is fitted: R6/R10 "NC/10K", R7/R8/R9 "4K7/NC".
7. Measured VSYS current at power-up and in steady state (bench, G07). No figure here is a measurement.
