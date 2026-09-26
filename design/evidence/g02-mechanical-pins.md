# G02 desk evidence: switch, jack, button and module pin/mechanical maps

Status: **evidence_partial**. G02 stays OPEN. Everything below was read from manufacturer drawings and CAD. None of it comes from a physical part, a fitted footprint or an assembled stack. "Real-part fit" is still a local gate.

| # | Item | Verdict |
|---|---|---|
| 1 | NKK SS14MDP2 (RANGE, SP3T) terminal map and mechanics | **RESOLVED** (pins, pitch, holes, heights). Panel direction of L/H is a layout decision. |
| 2 | SHOU HAN PJ-313 5JCJ jack: duplicated legs | **OPEN**: the drawing does not say which physical leg carries which contact. The hole pattern is RESOLVED. |
| 3 | XUNPU TS-1088-AR02016 button | **RESOLVED**: two terminals, no internally joined pairs. The existing footprint matches the drawing. |
| 4a | Waveshare Pico-ResTouch-LCD-3.5 outline, sockets, active area, holes and heights | **RESOLVED** from the Waveshare STEP and dimension drawing. The PCB drill diameter is **OPEN**. |
| 4b | Pico H header positions / header height | Positions **RESOLVED**. Header height **OPEN**: no Raspberry Pi source dimensions it. |
| 5 | 1x20 2.54 mm female/male strips | **OPEN**: no orderable part is selected. The stack constraints are listed below. |

## Sources read

| ID | Source | Retrieved (UTC) | SHA-256 | Committed? |
|---|---|---|---|---|
| range-cat | NKK Series SS catalogue PDF, pages H44–H48 (5 pp., InDesign, subject `20180111`). Downloaded from the Catalog PDF button on `https://www.nkkswitches.eu/products/Slides/Slides%20SS/SS14MDP2/`, i.e. `POST /user/pdf-precheck katamei=SS14MDP2` with the page's XSRF cookie, then `GET /user/pdf-download/SS14MDP2`. No login was needed. | 2026-09-26T10:00Z | `bd75fbd29c691ec3fcd443570714081c51ab03e47ffacecc763228121b122fb5` | no (NKK terms not reviewed) |
| range | NKK SS14MDP2 product page (HTML) | 2026-09-26T09:59Z | `530bb5f8cf2fc3f11ab077ce59e063370be33ab792be6d4dee0e92021cd1b80c` | no |
| jack | `reference/assets/jack/PJ-313-5JCJ.pdf` (retained; p1 is the drawing, pp2–6 the test spec) | in repo | `8c3be622655208735ec21158f79aba16f5b1ae0b6621efa6ea6e2e89ac0d7199` | already retained |
| jack-easyeda | EasyEDA/LCSC library footprint `AUDIO-TH_PJ-313_5JCJ`, `https://easyeda.com/api/products/C668607/components?version=6.4.19.5` (contributor "Xkcc"; **third-party, not the manufacturer**) | 2026-09-26T10:07Z | n/a (JSON API) | no |
| button | `reference/assets/button/TS-1088-AR02016.pdf` (retained; 1 page, raster, title `TS-1088-ARXXX`) | in repo | `368d4cc2c26b08cb63e1b67193f671d0860b6d3fb2e6b9f2696ffade401afc30` | already retained |
| display-cad | `https://files.waveshare.com/upload/e/e4/Pico-ResTouch-LCD-3_5.zip` (contains only `Pico-ResTouch-LCD-3_5.stp`, Creo 2022-09-14, one merged solid) | 2026-09-26T10:02Z | zip `3ac36201418be8a033f13303aad4dc06f11b1a9fe1f44042c57d23e331fbcaf5`; stp `f94fee5c475b1ea6bb0ad1380c8afacc3192be3ca467238edd0212df139de548` | no (Waveshare terms unclear) |
| display-size | Waveshare wiki image `Pico-ResTouch-LCD-3.5-details-size.jpg` (`https://www.waveshare.com/w/upload/0/0e/…`) | 2026-09-26T10:03Z | `f1f7c86aad75b6944e72ff14b878a6b773b0cabb2375c719d827b9a8758e95a1` | no |
| display-inter | Waveshare wiki image `Pico-ResTouch-LCD-3.5-details-inter.jpg` (`https://www.waveshare.com/w/upload/c/c9/…`) | 2026-09-26T10:03Z | `bddbc75e6e4ecc8085569dc9b9a9bb1345b81463186514d9cc3470958ac07857` | no |
| pico-ds | `https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf` (31 pp., modDate 2026-07-03) | 2026-09-26T10:01Z | `757ff485227493b9fcc0c2c96c4dea9de020e1d8b2b11e2aa4f9ee8b25aa89eb` | no |
| pico-step | `https://datasheets.raspberrypi.com/pico/Pico-R3-step.zip` (bare Pico R3; no header product inside) | 2026-09-26T10:02Z | n/a (checked for headers only) | no |

PDF pages were rendered to PNG with PyMuPDF 1.28.2 (MuPDF): whole pages at 150–200 dpi, and the areas that mattered again at 500–1200 dpi. I read the images directly. The STEP was parsed as text (ADVANCED_FACE / PLANE / CYLINDRICAL_SURFACE / VERTEX_POINT). Its edges were drawn as top (XY) and front (XZ) views and looked at, and they agree with the Waveshare dimension image. The rendered PNGs are not committed. Rerun the URLs above into the gitignored `reference/downloads/` to regenerate them.

Citation shorthand: `NKK H46` means the catalogue page number printed on the page (PDF page = H − 43). `Jack p1 <col><row>` uses the drawing's frame grid (columns 1–16, rows A–H). `Btn p1 <col><row>` uses the XUNPU frame grid (columns 1–15, rows A–J).

## 1. SS14MDP2: common is terminal 3; throws are 1 / 2 / 4

- **Circuit table** (NKK H46, "Poles & Circuits", row SS14M, SP3T ON-ON-ON):

  | Slide position | Connected terminals |
  |---|---|
  | Right | 3-4 |
  | Center | 3-2 |
  | Left | 3-1 |

  The schematic beside the table labels **3 (COM)** and draws terminals in the order 4, 3, 2, 1. The page notes "ON-OFF-ON circuit can be created by not connecting terminal 2", which confirms that 2 is the centre throw. NKK H46 also warns: **"Terminal numbers are not actually on switch."** Orientation on the PCB therefore comes from the asymmetric pitch (below), not from a marking.
- **Terminal layout, spacing code D (inch), 3-On models** (NKK H47, "Terminal Spacing" D, right column): one straight row of 4 terminals. Pitch is **2.54** for 1–2 and 2–3, then **5.08** for 3–4. The recommended PCB hole is **(0.8) Dia Typ**. The terminal section is (0.4) × (0.6) Typ. The isometric view gives the terminal projection as **(3.4)**, but H48 gives **(3.0)**. This conflict is recorded, not resolved; plan for 3.0–3.4 mm. The "D" code is also confirmed by the ordering chart (NKK H46: `D` = Inch .100″ × .100″; `P` = Top Actuated; `2` = Silver, 0.1 A @ 30 V DC).
- **Body and actuator** (NKK H48, "3-On Circuit • Top Actuated", SS14MDP2 views):
  - body length **(15.8)**, width **(4.0)**, height above the seating plane **(4.5)**;
  - terminal length below the body **(3.0)** (H47 isometric shows (3.4)), terminal section (0.4) × (0.6);
  - actuator (1.2) across × (1.5) along travel, standing **(2.0)** above the body top;
  - travel **(2.0) Typ** per step.
  - Derived: the actuator top sits about **6.5 mm** above the PCB (4.5 + 2.0). All values are in parentheses on the drawing, so they are reference dimensions without tolerances.
- **Centre alignment** (NKK H48 bottom and side views): the centre mark passes through terminal 3, and the actuator centreline (centre position) is in line with terminal 3. In the bottom view an unnumbered empty cavity sits between terminals 3 and 4. This alignment is read from the centre marks and is not a toleranced dimension.
- **Mounting pegs: none.** The bottom view (NKK H48) shows four oval standoff bosses at the corners of the body. No PCB peg or hole is called out anywhere on H44–H48. The only board holes are the four terminal holes.
- **Proposed logical-to-numeric map** (delta `range`): C → **3**, M → **2**, L → **1**, H → **4**. C = 3 and M = 2 are vendor facts. L = 1 / H = 4 follows NKK's Left/Right naming, but which way is "left" on the panel depends on how layout rotates the part. Layout must confirm this against the printed panel legend before the footprint is released.

## 2. PJ-313 5JCJ: hole pattern resolved, but which legs are duplicated is OPEN

**Resolved, from the drawing:**

- **It is a through-hole part.** The land-pattern view is titled 印制板开孔尺寸(±0.1) ("PCB hole/opening dimensions, ±0.1") with 显示为底面 ("shown as bottom face") (Jack p1 14B). The side view shows round-ended pin tails (Jack p1 2D–5E). The front view dimensions the tails as **3.2** below the body (Jack p1 7D). The five filled rectangles in the lower view are **slot openings**, not SMD pads. They measure **1.5 (along the jack axis) × 1.0** on the render: 1.51 × 0.99 mm against the 3.2 mm dimension. The callout reads "(6-1.X1.5)" (Jack p1 9G). The count "6" disagrees with the **5** slots drawn, and "1." is missing a digit. I read it as a drawing typo and take the size from the drawn geometry.
- **Slot positions** (Jack p1 5F–9G). The origin is the body shoulder where the Ø5 nose begins, which sits 2.5 mm behind the nose tip:
  - near row, 3 slots: x = 1.8, 5.0, 8.5 (dimension chain 1.8 / 3.2 / 3.5, then 3.1 to the rear face);
  - far row, 2 slots at x = 1.8 and 8.5 (vertically aligned with the near row's first and third slots);
  - row-to-row pitch **5.8** (the body is 6 wide, dimension "6").
  - The chain 2.5 + 1.8 + 3.2 + 3.5 + 3.1 = 14.1 disagrees by 0.1 with the side view's 2.5 + 11.5 = 14.0 (Jack p1 3C–6C). This is noted, not resolved.
- **Locating posts:** 2 × **Ø1** on the part (bottom view "2-φ1", Jack p1 15C). The board holes are **2 × Ø1.3** (Jack p1 8E–9E). They sit midway between the rows at x = **2.3** and **8.3** (2.3 + 6), so the posts are 6.0 apart. The drawing does not state plating for the post holes or the slots, so the plating choice is OPEN for the footprint author.
- **Body:** 11.5 long + 2.5 nose, 6 wide, 5 high. The nose is Ø5 OD with a **Ø3.6** opening (Jack p1 7C–8D). Weight 0.2 g, scale 5:1, sheet dated 2016-06-17, revision A (title block).
- **Three electrical nodes only:** the contact schematic 触点示意图 (Jack p1 16E–16F) shows contact **1** tied to the sleeve bar, **2** as a V spring and **3** as a ^ spring. There is no normally-closed switch contact. The drawing does not name tip or ring; reading 2 = ring and 3 = tip follows the symbol convention, not a printed label.

**OPEN: which physical leg belongs to which node.**

- The parts table (Jack p1 11F–16G, columns 序号 / 名称 / 数量 / 零件图号 / 对应端子号) lists:

  | Item | Part | Qty | Drawing no. | 对应端子号 (terminal no.) |
  |---|---|---|---|---|
  | ① | 1号触片 (contact 1) | 1 | PJ-313D-01 | 1 |
  | ② | 2号触片 (contact 2) | **2** | PJ-313D-02 | **2-3** |
  | ③ | 3号触片 (contact 3) | 1 | PJ-313D-03 | 4 |
  | ④ | 基座 (PPA base) | 1 | PJ-313D-03 | 5 |

- The table is internally inconsistent:
  - item ④, the plastic base, is given terminal "5";
  - ③ and ④ share drawing number PJ-313D-03;
  - terminal numbers 1–5 are **not written on any view**, so no slot can be tied to a number.
- The side view labels ①, ② and ③ only on the near row (Jack p1 2C–5C). Nothing labels the two far-row legs.
- The EasyEDA library footprint for C668607 numbers the pads **1, 3, 2** on the near row and **1, 2** on the far row. That would make the two outer columns the duplicated nodes. But that footprint is a third-party model. It also disagrees with the manufacturer drawing:
  - it uses round Ø0.8 holes, not 1.0 × 1.5 slots;
  - its row pitch is 6.3, not 5.8;
  - its post holes are Ø1.7, not Ø1.3;
  - its first post sits 0.7 behind the first column, not 0.5.
  So it **cannot be adopted as evidence**. It only shows that one plausible reading exists.
- **Resolution path:** get continuity on a sample leg by leg (a local bench check with an ohmmeter; no soldering), or get written confirmation from SHOU HAN or LCSC. Until then, tie every leg to its node only after that check. The `design/circuit.json` note "duplicated pad mapping is OPEN" stays accurate.

## 3. TS-1088-AR02016: two terminals, footprint matches the drawing

- **Part code** (Btn p1 7D–11F, ordering boxes):
  - `A` = stainless-steel dome (弹片 A:不锈钢);
  - `R` = no locating post (定位柱 R:无柱; `C` = with post);
  - `020` = **H 2.0 mm** (高度 020:2.0H);
  - `16` = **160 gf** operating force (力度 16:160g).
  - The exact variant therefore has **no board peg** and an actuator top **2.0 mm** above the seating plane. H is the dimension from the base to the actuator top in the side view (Btn p1 6B–7B; H table 1.8/2.0/2.5 at Btn p1 5D–6E).
- **Terminals:** exactly two, **①** on the left and **②** on the right in the top view (Btn p1 2D–4F). The circuit diagram is a single normally-open contact ①–② (Btn p1 5I–6I). With only two feet, **no pins are internally connected in pairs**. BOM item C 弹片 qty 2 (Btn p1 11H) is the two-layer dome, not a terminal.
- **Body:** 3.90 × 3.00. The terminals span 5.00 overall, and each terminal is 1.30 wide (Btn p1 2D–4E). Body height is 1.50, and the actuator is Ø1.80 (Btn p1 2B–4B).
- **Recommended land pattern** (PCB.焊接图, Btn p1 8H–9I): outside span **5.50**, inside gap **3.40**, pad height **2.00**. That gives a pad width of (5.50 − 3.40)/2 = **1.05** and pad centres at **±2.225**.
- **Footprint check:** `hardware/libraries/ZudoScope10.pretty/SW_XUNPU_TS1088_AR02016_REVIEW.kicad_mod` has pad 1 at (−2.225, 0) and pad 2 at (+2.225, 0), both SMD rect 1.05 × 2.0. The Fab outline is ±1.95 × ±1.5 (= 3.9 × 3.0). **Pads and body match the drawing exactly.** Pad 1 on the left matches ① on the left in the top view. The part is a symmetric two-terminal NO switch, so rotating it by 180° does not change the circuit. The courtyard (±3.0 × ±1.75) clears the pads by 0.25 mm. It needs no change for this gate. What remains is local fit and panel access (cap/actuator reach through the panel at H = 2.0).

## 4a. Waveshare module geometry, from the vendor STEP

**Frame used below:** the STEP's own coordinates, viewed from the **LCD side (+Z)**:

- the board spans x ∈ [−86.0, 0], y ∈ [0, 57.2];
- edge **E** (x = 0) is the edge nearer the header rows; edge **W** (x = −86) is the far edge;
- edge **N** (y = 57.2) is the header pin-1 end; edge **S** is y = 0;
- the Waveshare back-view photo (display-size / display-inter) is this frame mirrored left–right.

- **Outline:** 86.00 × 57.20 (display-size; STEP bbox). Corners have **R1.0** (four r = 1.000 cylinders, STEP). Edge N has two 1.0 mm-deep recesses: one for the RUN button at 38.64–47.62 from E, and one for the µSD socket at 61.06–76.95 from E (display-size dimension chain; the STEP outline shows the same notches).
- **PCB thickness 1.6** (STEP planes z = −0.411 and +1.189).
- **Mounting holes:** 4 holes at **4.10 / 4.10** from each corner, spaced **77.80 × 49.00** (display-size). The STEP centres at (−4.0996 / −81.8996, 4.0986 / 53.0956) agree. **Drill diameter OPEN:** the dimension image does not give it. The STEP has a Ø4.30 cylinder through the board and, under the board, a **Ø5.5 × 4.0 mm standoff with a Ø2.5 bore** on each hole. The Waveshare photo shows pillars at the holes. The standoff thread and hole size need a caliper check on the received module.
- **Header sockets** (female, on the side opposite the LCD):

  | Row | Pico pins | Distance from edge E | y of first pin | y of last pin |
  |---|---|---|---|---|
  | A | **1–20** | **10.45** | pin 1: 55.58 (**1.62 from N**) | pin 20: 7.32 (7.32 from S) |
  | B | **21–40** | **28.25** | pin 40: 55.58 | pin 21: 7.32 |

  - Pitch 2.54; row spacing is 17.80 in the STEP (17.78 nominal, pico-ds Fig. 3). Pin-cavity squares at 2.54 steps (STEP faces z = −1.411).
  - Pin identity comes from the Waveshare pin image: pins 1–20 on the outer row with pin 1 at the "USB" end, and pins 40/21 on the inner row (display-inter, rows labelled GP0 = 1 … GP15 = 20, VBUS = 40 … GP16 = 21). The image puts the pin-1 end at the RUN / µSD edge, which is edge N.
  - This matches the carrier data: J30 / J20 strip pin 1 = Pico position 1, and J31 / J21 strip pin 1 = Pico position 40 (`design/circuit.json`, J21 pin 1 `VBUS_USB`, J31 pin 2 `+5V_FUSED` = position 39).
- **Socket housing:** 2.5 wide × 51.3 long (y 5.80–57.10). It extends **9.0 mm** below the display PCB's bottom face (z −0.411 → −9.411). The modelled cavity floor is **8.0 mm** above the socket face (z −1.411). The model is simplified, so treat the 8.0 mm as indicative, not as the contact engagement spec.
- **LCD active area:** STEP face 73.44 × 48.96 at z = 6.339. That matches the catalogue's 48.96 × 73.44 and 480 × 320 px. Its edges sit **3.60 from E, 8.96 from W, 3.97 from N, 4.27 from S** (corners (−77.04, 4.27) to (−3.60, 53.23)). The active area is **not centred** on the board: it is shifted 2.68 mm toward E. Glass top outline 82.6 × 54.1 (x −84.0 … −1.4, y 1.7 … 55.8); panel frame 83.0 × 54.5 (z 3.189–5.389).
- **Heights, measured from the display PCB:**

  | Side | Feature | Height | Source (STEP z) |
  |---|---|---|---|
  | LCD face (above PCB top, z = 1.189) | glass top | **5.2** | z = 6.389 |
  | Back (below PCB bottom, z = −0.411) | header sockets | **9.0** | to z = −9.411 |
  | Back | standoffs | 4.0 | to z = −4.411 |
  | Back | RUN tact switch | 3.5 | z = −3.911, at edge N, x −46.6 … −39.6 |
  | Back | µSD socket | 2.1 | z = −2.511 |
  | Back | FPC connector | 2.3 | z = −2.711 |

  Overall module thickness without the Pico is **15.8 mm** (1.6 + 5.2 + 9.0).

## 4b. Pico H: positions resolved, header height OPEN

- **Board:** 51 × 21 × 1.0 mm. Pins sit on a 2.54 grid in two rows **17.78** apart, spanning **48.26** between the first and last pin of a row. Pin centres are **1.37** from each short edge ((51 − 48.26)/2), and the rows are inset (21 − 17.78)/2 = 1.61 from the long edges. There are 4 × Ø2.1 (± 0.05) mounting holes, 11.4 apart across the board, with the USB-end pair centred 2.0 from that edge and the opposite pair 2.4 from the far edge (Figure 3). The 1.37 edge distance is arithmetic, not a printed dimension. The micro-USB connector overhangs the top (pin-1) edge by **1.3 (typ)** (pico-ds §2 p6 text + Figure 3).
- **Numbering:** pin 1 is at top-left next to USB, pins 1–20 run down the left, and pin 40 is at top-right next to USB (pico-ds Figure 4, p7). This is the physical order `catalog/components.json` `pico-h.pins` already uses.
- **Pico H orderable:** SC0917 (pico-ds Appendix A Table 6, p24).
- **Header height OPEN:** the Pico datasheet does not dimension the factory header on Pico H, and the product brief only gives 21 × 51 mm. `Pico-R3-step.zip` contains a bare Pico with no header parts. The Pico H mating length and insulator height must come from a measured unit or a Raspberry Pi mechanical drawing, if one exists.

## 5. 1x20 2.54 mm strips: orderable not selected; stack constraints

No part is selected; this remains `SPECIFICATION_ONLY` in the catalogue. The facts above fix these constraints for layout and RFQ:

- **Display side (J30/J31, male on the carrier, mating into the module's female sockets):**
  - Mating pin length above the insulator must be **≤ 8.0 mm** (modelled socket cavity) and at least the socket vendor's minimum engagement (unknown; Waveshare does not publish the socket part).
  - If the socket face rests on the male insulator, the display PCB bottom sits at **h_ins + 9.0 mm** above the carrier.
  - The module's own 4.0 mm standoffs then fall short of the carrier by **h_ins + 5.0 mm**. Mechanical support needs added spacers of that length, or longer standoffs. It must not rest on solder joints or pins.
  - Nothing else on the module back hangs lower than the sockets (the tallest is the 3.5 mm RUN switch), so the sockets set the gap.
- **Pico side (J20/J21, female on the carrier, receiving the Pico H):**
  - The socket height and the Pico H header height (OPEN) together set the Pico's clearance.
  - Leave 1.3 mm beyond the pin-1 edge for the USB overhang, plus plug access.
- **If the Pico sits under the display:** the display gap (h_ins + 9.0) must exceed the carrier socket height + Pico H seated height + Pico top-side parts (USB connector included). Otherwise the modules must sit side by side. With both heights still unknown, this decides the placement and must be checked at layout.
- **Height classes to RFQ:** female strips by insulator height; male strips by insulator height and mating length. Pick exact MPNs whose drawings give these three numbers, then re-run the inequalities. Do not treat "2.54 mm 1x20" as a fit.

## What stays OPEN for G02

- PJ-313 5JCJ: which physical leg belongs to which contact node (sample continuity or vendor confirmation). The slot-count typo "(6-…)" and the 0.1 mm length-chain mismatch also need the vendor or a sample.
- SS14MDP2: the panel-side orientation of L/H (layout decision). Stock at C6684954 was zero; that is tracked in G08, not here.
- Waveshare: the mounting-hole drill diameter and standoff thread (caliper on the module), and the socket part's engagement spec.
- Pico H: header insulator height and pin length.
- 1x20 strips: exact orderables and the resulting stack. Real-part fit of every item above (local gate).
