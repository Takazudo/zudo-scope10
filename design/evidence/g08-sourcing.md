# G08 desk evidence: sourcing candidates for specification-only BOM rows

Evidence only. No catalog, BOM or generator file is edited by this document. Every
row below stays in the state recorded in `catalog/components.json` /
`manufacturing/bom-planning.csv`; a listing here is a **candidate**, never an
allocation, order, or fit confirmation. All C-numbers below were read from a
fetched LCSC/JLCPCB page on **2026-09-26** (dates noted per entry); none is
invented. Where a page could not be fetched or no matching listing was found,
the row is left `OPEN` with the reason stated.

Machine-readable form: `design/evidence/g08-delta.json`. Every entry there
carries `"listing_not_allocation": true`.

## Method

- LCSC product-detail pages (`lcsc.com/product-detail/...`) fetched via
  WebFetch. These render server-side and returned real spec/stock data.
- JLCPCB `partdetail` pages (`jlcpcb.com/partdetail/...`) fetched via WebFetch
  render but do not expose live stock figures in the fetched markdown — LCSC's
  own product page was used for stock/status wherever both exist for the same
  C-number.
- `lcsc.com/search?...` search-results pages did **not** render usable content
  through WebFetch (the tool returned only the site footer/nav — the results
  grid is client-side rendered). No LCSC/JLC "search" or "list" API endpoint
  was reachable either; only direct `product-detail` / `partdetail` pages by
  known C-number worked. Candidate C-numbers were therefore identified via
  WebSearch (which surfaces LCSC product-detail URLs already indexed by
  search engines) and then **verified** by fetching each candidate's own LCSC
  page directly — no C-number below is taken from a search snippet alone.
- Basic/extended/preferred JLC assembly-tier labels were not exposed on any
  fetched LCSC or JLC page for any part in this pass; where the field below
  says "not stated on page", that is a fetch limitation, not a finding that
  the part lacks the tier.

## Known listings — recheck (2026-09-26)

| Catalog id | Current jlc_code | MPN | Source | Stock observed | Notes |
|---|---|---|---|---|---|
| tlv9064 | C388176 | TLV9064IDR | https://www.lcsc.com/product-detail/C388176.html | 8,213 | TI, SOIC-14. Basic/extended tier not stated on page. |
| mux | C179326 | 74HC4067PW,118 | https://www.lcsc.com/product-detail/C179326.html | 1,122 | Nexperia, TSSOP-24. |
| ldo | C404027 | TLV75533PDBVR | https://www.lcsc.com/product-detail/C404027.html | 138,170 | TI, SOT-23-5. |
| clamp | C40919 | BAV199,215 | https://www.lcsc.com/product-detail/C40919.html | 111,180 | Nexperia, SOT-23. |
| range | C6684954 | SS14MDP2 | https://www.lcsc.com/product-detail/C6684954.html | **0 — "Currently out of stock (notification option available)"** | NKK Switches, through-hole SP3T. Confirms the zero-stock condition already noted in the issue; unchanged. |
| pot | C7419101 | RK09L1140A5L | https://www.lcsc.com/product-detail/C7419101.html | 473 | ALPSALPINE, through-hole, ±20% tolerance per page (page shows 10kΩ/50mW/10V; the BOM's mechanical-spec note about shaft/bushing is unaffected by this recheck). |

All six pages fetched successfully; none was bot-blocked.

## Specification-only rows — candidates found

Each candidate below was confirmed by fetching its own LCSC product page.
"Meets spec" judges only the parameters stated in
`catalog/components.json`'s `facts` for that row (value, tolerance, tempco,
dielectric, voltage) — it is not a footprint, fit, or assembly-tier finding.

### Precision resistors (0603)

| Catalog id | Spec | Candidate MPN | Manufacturer | LCSC | Source URL | Stock | Meets spec |
|---|---|---|---|---|---|---|---|
| r1m | 1MΩ, 0.1%, 25ppm/°C | RT0603BRD071ML | YAGEO | C326730 | https://www.lcsc.com/product-detail/C326730.html | 8,540 | Yes — 1MΩ ±0.1%, ±25ppm/°C, 0603 confirmed on page. |
| r200k | 200kΩ, 0.1%, 25ppm/°C | RT0603BRD07200KL | YAGEO | C728585 | https://lcsc.com/product-detail/chip-resistor-surface-mount_yageo-rt0603brd07200kl_C728585.html | 248,120 | Yes — 200kΩ ±0.1%, ±25ppm/°C, 0603 confirmed on page. |
| r249k | 249kΩ, 0.1%, 25ppm/°C | — | — | — | — | — | **OPEN.** The YAGEO family member `RT0603BRD07249KL` exists per the manufacturer's own spec sheet (yageogroup.com), but no LCSC product-detail page for it was found via search or by probing the same URL pattern as the 1M/200k siblings. Not fetched, so not recorded as a candidate here. |

### General-purpose resistors (0603, 1%)

| Catalog id | Spec | Candidate MPN | Manufacturer | LCSC | Source URL | Stock | Meets spec |
|---|---|---|---|---|---|---|---|
| r4k7 | 4.7kΩ, 1% | HoLTT0603-1/10W-4.7K-1% | Milliohm | C2904521 | https://www.lcsc.com/product-detail/C2904521.html | 820 | Yes — 4.7kΩ ±1%, 0603 confirmed on page. |
| r10k | 10kΩ, 1% | 0603WAF1002T5E | UNI-ROYAL | C25804 | https://www.lcsc.com/product-detail/C25804.html | **0 — "Out of Stock" ("Notify Me")** | Value/tolerance/package match; stock is currently zero. |
| r100k | 100kΩ, 1% | 0603WAF1003T5E | UNI-ROYAL | C25803 | https://www.lcsc.com/product-detail/C25803.html | 17,040,200 | Yes. |
| r100 | 100Ω, 1% | 0603 ±1% 100Ω | VO | C2889384 | https://www.lcsc.com/product-detail/Chip-Resistor-Surface-Mount_VO_C2889384.html | **0 — "Not available now"** | Value/tolerance/package match; stock is currently zero. |
| r1k | 1kΩ, 1% | 0603WAF1001T5E | UNI-ROYAL | C21190 | https://www.lcsc.com/product-detail/C21190.html | 7,514,000 | Yes. |
| r33 | 33Ω, 1% | RC0603FR-0733RL | YAGEO | C108661 | https://www.lcsc.com/product-detail/C108661.html | 85,500 | Yes. (A UNI-ROYAL "0603WAF3300T5E" / C23138 found in the same search is **330Ω, not 33Ω** — confirmed by fetch and rejected as a false match; not included as a candidate.) |

### Capacitors (0603 C0G / 0603 X7R / 0805)

| Catalog id | Spec | Candidate MPN | Manufacturer | LCSC | Source URL | Stock | Meets spec |
|---|---|---|---|---|---|---|---|
| c470p | 470pF, C0G, 5%, ≥25V | 06035A471KAT2A | Kyocera AVX | C597169 | https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_kyocera-avx-06035a471kat2a_C597169.html | 240 | Yes — 470pF, C0G, ±10% (tighter spec than needed's 5% max — page states 10%, so tolerance is actually looser than the design's "5%"; flagged), 50V, 0603. **Tolerance mismatch: page is ±10%, design calls for 5%.** Candidate, not a confirmed match on tolerance. |
| c10n | 10nF, C0G, 5%, ≥25V | GRM1885C1H103JA01D | muRata | C85973 | https://www.lcsc.com/product-detail/Multilayer-Ceramic-Capacitors-MLCC-SMD-SMT_Murata-Electronics-GRM1885C1H103JA01D_C85973.html | 98,960 | Yes — 10nF, C0G, ±5%, 50V, 0603 confirmed on page. |
| c1n | 1nF, C0G, 5%, ≥25V | CC0603FRNPO9BN102 | YAGEO | C309468 | https://www.lcsc.com/product-detail/C309468.html | 483,500 | Yes — 1nF, NP0 (=C0G), 50V, 0603 confirmed on page. Page states ±1% tolerance (tighter than the design's 5% requirement, so it satisfies it). |
| c100n | 100nF, X7R, ≥16V | CC0603KRX7R9BB104 | YAGEO | C14663 | https://www.lcsc.com/product-detail/C14663.html | 8,686,600 | Yes — 100nF, X7R, 50V ≥16V, 0603 confirmed on page. |
| c1u | 1µF, X7R, ≥10V | CC0805KKX7R8BB105 | YAGEO | C91186 | https://www.lcsc.com/product-detail/Multilayer-Ceramic-Capacitors-MLCC-SMD-SMT_1uF-105-10-25V_C91186.html | 880 | Yes on nominal/dielectric/voltage (1µF, X7R, 25V≥10V, 0805). The design's "effective >0.47µF" derated-capacitance requirement was **not checked** — no fetched page gave a DC-bias derating curve. |
| c10u | 10µF, X5R/X7R, ≥10V | CL21A106KAYNNNE | Samsung Electro-Mechanics | C15850 | https://www.lcsc.com/product-detail/C15850.html | 1,507,260 | Yes on nominal/dielectric/voltage (10µF, X5R, 25V≥10V, 0805). This catalog id (`c10u`) has an empty `source_ids` list in `catalog/components.json` — it is not currently wired to any BOM reference — recorded here for completeness since it is `identity_state: SPECIFICATION_ONLY`. Effective-capacitance derating not checked (same limitation as c1u). |

### Fuse, reference, connectors

| Catalog id | Spec | Candidate MPN | Manufacturer | LCSC | Source URL | Stock | Meets spec |
|---|---|---|---|---|---|---|---|
| fuse | 1206 PPTC, ≥500mA hold, ≥6V | 1206L050YR | Littelfuse | C163512 | https://lcsc.com/product-detail/Resettable-Fuses_Littelfuse-1206L050YR_C163512.html | 21,130 | Yes — 1206 package, 500mA hold, 6V rating confirmed on page. This is an exact hold-current/voltage match, not margin above spec; confirm against the design's actual inrush budget (out of scope here — see #8's G07 desk evidence) before treating it as sized correctly. |
| ref | REF3330AIDBZR (mpn known, jlc_code null) | REF3330AIDBZR | Texas Instruments | C140329 | https://www.lcsc.com/product-detail/C140329.html | 5,102 | Yes — exact MPN match confirmed by fetch (page states REF3330AIDBZR, TI, SOT-23, 3V, ±0.15%, 30ppm/°C max, matching the catalog's family specification facts). This resolves the catalog's existing note "LCSC C140329 found; JLC direct listing was not verified" — it is now verified against LCSC (not against a JLCPCB partdetail page specifically; JLCPCB mirrors LCSC stock for most parts but this was not independently fetched from jlcpcb.com for C140329). |
| socket20 | 1×20 female socket, 2.54mm, height TBD | — | — | — | — | — | **OPEN.** LCSC/JLC searches (via WebSearch and by probing likely product-detail URLs) returned only 2×20 (40-pin, dual-row) female header parts under the "2.54-2*20" naming family. No single-row 1×20 female socket page was found and fetched. Height is explicitly undefined in the design (`catalog/components.json`), so even a located candidate could not be confirmed against spec without that dimension. |
| header20 | 1×20 male header, 2.54mm, height TBD | — | — | — | — | — | **OPEN**, same reason as `socket20`: only 2×20 dual-row male headers were found; no confirmed 1×20 single-row page fetched, and height is undefined in the design regardless. |

## Fetch failures / access notes

- No page in this pass returned bot-protection/CAPTCHA/403 content — every
  `lcsc.com/product-detail/...` and the one `jlcpcb.com/partdetail/...` URL
  tried rendered real product data through WebFetch.
- The one confirmed failure mode was **`lcsc.com/search?...`**: it returns the
  static site shell (footer/nav) with no results grid, because the results
  are populated client-side by JavaScript that WebFetch's markdown conversion
  does not execute. No JLC/LCSC JSON search/autocomplete API endpoint was
  found that returns useful data over a plain GET (none was tried against an
  authenticated-looking endpoint, per the "no accounts/carts/orders" rule).
- Consequence: candidates were found by combining WebSearch (to locate
  plausible LCSC product-detail URLs already indexed by external search
  engines) with a direct WebFetch of each resulting URL to confirm the
  content. Rows where this two-step process produced no matching page
  (r249k, socket20, header20) are left `OPEN` rather than guessed.

## Summary

- 6 of 6 known listings rechecked; all reachable; `range` (SS14MDP2 /
  C6684954) reconfirmed at zero stock.
- 16 of 19 specification-only rows now have at least one cited, fetch-verified
  candidate (some with caveats noted above: `c470p` tolerance looser than
  spec, `c1u`/`c10u` effective-capacitance derating unchecked, `r10k`/`r100`
  candidates at zero stock, `fuse` sized exactly at spec with no margin
  checked).
- 3 rows stay `OPEN` with a stated reason: `r249k` (no LCSC page found for the
  known-to-exist YAGEO family member), `socket20`, `header20` (no confirmed
  1×20 single-row page found; height also undefined in the design either
  way).
- Gate G08 remains OPEN. Nothing here is an allocation, an order, a footprint
  qualification, or a factory-route decision — see `catalog/components.json`'s
  own `factory_order_approved: false` / `footprint_qualified: false` flags,
  which this evidence does not touch.
