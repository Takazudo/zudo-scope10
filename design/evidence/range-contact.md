# RANGE switch (NKK SS14MDP2) contact-suitability evidence and qualification plan (#27, #38)

Status: **OPEN_REQUIRES_MANUFACTURER_CONFIRMATION_AND_QUALIFICATION**. This is a desk-evidence
record and a qualification plan, not a bench result. No contact-resistance measurement, cycling
run or environmental test has been performed. G02/G08 stay OPEN. Nothing here marks a bench or
aging result as PASS.

## Decision (#27 option 2, applied 2026-09-26)

Keep the already-selected NKK `SS14MDP2` (`catalog/components.json` record `range`). Do not invent
a substitute MPN, sourcing code, pin map or footprint. Require specific manufacturer confirmation
plus application-level qualification before the switch is approved for this exact circuit. A
maintained, break-before-make SP3T with manufacturer-supported dry-circuit (e.g. gold) contacts
remains a listed **OPEN alternative**, never a decision here -- any real substitute would need its
own exact pin map, footprint, actuator-height and factory-process review, none of which is done.

## 1. Contact material is silver, not gold

The NKK SS14MDP2 product page's General Specifications table states:

> Contact Finish: Silver Plating

Source: `range-contact-finish` (`catalog/sources.json`), re-fetched 2026-09-26.
<https://www.nkkswitches.eu/products/Slides/Slides%20SS/SS14MDP2/>

The switch's own ordering code confirms the same fact independently: `D`-`P`-**`2`** where NKK's
ordering chart (already recorded in `design/evidence/g02-mechanical-pins.md` §1, NKK H46) defines
option `2` as "Silver, 0.1 A @ 30 V DC".

## 2. Manufacturer dry-circuit guidance (NKK page Z33 / operating-range page)

NKK's Electrical Ratings document, printed page **Z33** ("Operating Range" section), states:

> Three contact materials are commonly used in NKK switches: gold, silver, and gold over silver.
>
> **Low Level ~ 0.4VA maximum @ 28V AC or DC maximum** -- Gold plated contacts are recommended for
> dry circuits, which are defined as very low energy. In circuits where the voltage is below 28
> volts DC and current is below 100 milliamps (dry circuits), no arc develops as the contacts open
> or close. So, the tarnish remains. Eventually without the arc, the contacts become so encrusted
> that the switch is unable to close the circuit due to the high contact resistance. The solution
> to this is plating the contacts with gold, which does not tarnish, thus assuring the full
> electrical life of the switch.
>
> **Power Level ~ 100mA to 10 amps @ 125V AC** -- Silver contacts are recommended for electrical
> levels above 0.4VA. Although silver tarnishes, it is a good conductor and this electrical energy
> is sufficient to break through the tarnish to give reliable performance. ... In circuits where
> the voltage is above about 12 volts DC and the current above .5 amps, an arc develops during
> opening or closing of the contacts. This arc keeps the oxidation cleaned off.

Source: `range-z33` (`catalog/sources.json`), fetched and read 2026-09-26. Retrieved as
`https://www.nkkswitches.eu/documents/products/support/electricalratings.pdf` (PDF page 3 of the
document, printed page Z33 in the NKK "Z Supplement"). The companion operating-range engineering
page restates the identical gold-for-dry-circuit recommendation (source `range-operating-range`,
`https://www.nkkswitches.eu/engineering/electrical.html`).

**Reading against this circuit:** the mechanism NKK describes for silver contacts to remain
reliable is arcing above roughly 12 VDC / 0.5 A, which cleans tarnish off the contact surface. This
sense circuit runs at 3.3 V logic level and never sustains current at all (see §3), so it never
produces the arc that silver contacts here would depend on. That places this application inside
NKK's own "Low Level ~ dry circuit" description, the case the manufacturer says gold contacts are
for -- not a confirmation that this specific part fails, but the specific, cited reason the
generic "approve signal-level switching" note in the catalog is replaced by an open qualification
requirement instead of a pass.

## 3. Steady and transient contact loads (this circuit, not a generic rating)

Actual sense path per `scripts/make_design.py` (~lines 47-49), one instance per channel (`SWn`
COMMON -> `Rn+2` (1 kOhm) -> `Cn+2` (100 nF) -> mux input `RANGE`):

```text
Initial capacitor current, full 0 <-> 3.3 V throw:  3.3 V / 1 kOhm = 3.3 mA
RC time constant:                                    1 kOhm x 100 nF = 100 us
```

- The 3.3 mA figure is the *initial*, instantaneous transient at the moment of a full-swing throw
  (e.g. GND throw to the +3V3A throw). It decays exponentially with tau = 100 us toward the
  steady-state current, which is leakage/input-bias current into the downstream mux/buffer --
  on the order of nanoamps to low microamps for a CMOS mux/op-amp input, not milliamps.
- The centre throw (`THROW_CENTER` / `RANGE_MID`) is fed by the R40/R41 10 kOhm/10 kOhm divider
  (`scripts/make_design.py`), adding roughly 5 kOhm of source impedance on that throw; this
  lowers the available transient current further, it does not add a continuous load.
- **There is no continuous wetting current.** Once the RC transient settles (a few hundred
  microseconds after a throw), the switch contact carries only the mux/buffer's leakage/bias
  current until the next throw.
- The manufacturer's **100 mA / 30 V rating is a maximum electrical rating**, i.e. an upper bound
  on what the switch can survive. It says nothing about performance in a circuit that runs at a
  small fraction of a milliamp in steady state and a single-digit-milliamp transient once per
  throw -- the low-energy regime NKK's own dry-circuit guidance addresses separately from the
  maximum rating.

## 4. What is NOT concluded here

- This is not a finding that SS14MDP2 will fail in service. It is an evidence-based reliability
  qualification risk (per #27's classification), not an observed field failure or proof every
  sample fails.
- No substitution is made. The part, pin map, footprint and factory-process assumptions in
  `catalog/components.json` and `scripts/make_design.py` are unchanged by this record.
- No bench, cycling, or environmental result exists yet. Every check below is a plan, not a
  measurement.

## 5. Qualification plan (concrete, not yet executed)

1. **Manufacturer confirmation.** Request NKK's written confirmation that SS14MDP2 (silver,
   `D`-`P`-`2`) is acceptable for this exact load: ~3.3 mA initial transient decaying with a 100 us
   RC time constant to leakage/bias current, 3.3 V logic-level throws, no continuous wetting
   current, indoor bench/consumer environment.
2. **Contact-resistance measurement at the actual load.** Measure contact resistance through the
   switch under the real 1 kOhm/100 nF sense path (or an equivalent bench load reproducing the same
   transient/steady-state profile), not a generic continuity check, both when new and after aging
   below.
3. **Cycling/durability run.** Cycle a sample through its positions under the same real load for a
   defined number of operations (count TBD with the assembler/NKK's guidance) and re-measure
   contact resistance to detect any dry-circuit tarnish buildup NKK's guidance predicts.
4. **Environmental/cleaning exposure check.** Expose sample switches to the factory's actual
   flux/wash process (`design/evidence/g02-mechanical-pins.md` and NKK H44 cleaning notes) and
   re-check contact resistance, since flux residue and cleaning chemistry can compound tarnish
   effects on unwetted silver contacts.
5. Only after 1-4 return real evidence does `catalog/components.json`'s
   `application_suitability_status` move off `OPEN_REQUIRES_MANUFACTURER_CONFIRMATION_AND_QUALIFICATION`,
   and only then can G02/G08 close this item in `design/release-gates.json`.

## Acceptance-matrix tracking

`manufacturing/acceptance-results.csv` carries a `RANGE_CONTACT_QUALIFICATION` row with
`result=NOT_RUN`, per the width/format rules `#32` established (`scripts/validate_extra.py`'s
`_acceptance_csv` check). It moves to `PASS`/`FAIL`/`BLOCKED` only once §5 above is actually run,
with `evidence_file`, `operator` and `date` populated per that check's requirements.
