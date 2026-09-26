# Acquisition engine (`scope10_acq`)

**Status: design, host-tested model and a target build only. Gate G05 ("Acquisition qualification") stays OPEN.** This file has no measured rate, jitter, settle time or cross-talk figure. Every number below is a nominal design value or an allocation, and each one is to be confirmed by the bench procedure at the end.

The engine is built for CV, LFO and low-audio monitoring. The target is 10 000 samples/s per channel. All ten channels are sampled **sequentially** through one 74HC4067 (U7) into one ADC input. Two channels are never sampled at the same instant. The TIME link changes viewing windows only. It is not phase synchronisation, and the engine does not provide phase synchronisation.

## Files

| File | Role |
|---|---|
| `src/acq_engine.[ch]` | Portable C for the schedule, the settle judgement for each slot ("missed slots"), the ring consumer and the counters. It feeds `scope_core` histories and has no RP2040 headers. |
| `src/acq_epoch.h` | Portable startup and resync protocol: the shared time origin, the atomic origin-capture/publication/PWM-enable sequence and the core1 quiescence handshake. The target and the host model run the same code through hook macros. |
| `src/acq_rp2040.c` | RP2040 register code (PWM, DMA, ADC FIFO, the core1 IRQ, USB serial counters) and `main` for `scope10_acq`. |
| `tests/test_acq.c` | Cycle-level host model that drives the real `acq_engine.c` and `scope_core.c`. It runs via `scripts/test_firmware.py`. |

The target `scope10_diagnostic` and `pico_diagnostic.c` are unchanged.

## Hardware contract used

These values come from `design/gpio.json` and `design/circuit.json`.

- **Mux address:** GP2 to GP5 (ADDR0 to ADDR3). The address is shared by U7 (signal), U8 (TIME) and U9 (RANGE).
- **Mux disable:** GP7. HIGH disconnects all three banks.
- **Timing test point:** GP14.
- **ADC inputs:** ADC0 (GP26) carries the signal, from U7 through a TLV9064 buffer and 100 Ω / 1 nF. ADC1 (GP27) carries TIME from U8 and ADC2 (GP28) carries RANGE from U9, each through the same kind of buffer and RC.
- **Channel to mux input:** CH(n+1) is on mux input Yn, so the address equals the 0-based channel. This matches `pico_diagnostic.c`, and the pin numbers in `catalog/components.json` (Y0 = pin 9 … Y9 = pin 22).

## Budget (nominal, per `acq_engine.h`)

| Item | Value | Basis |
|---|---|---|
| `clk_sys` | 120 MHz | Exact PLL setting from the 12 MHz crystal. It is checked at boot, and acquisition refuses to start otherwise. |
| Frame | 100 µs = 12 000 cycles | 10 000 frames/s, so each channel gets one signal sample per frame. |
| Slots per frame | 12 uniform slots of 1000 cycles (8.333 µs) | 10 signal slots, then TIME, then RANGE. |
| Aggregate ADC rate | 120 kS/s | The RP2040 ADC limit is 500 kS/s. |
| Conversion | 2 µs (96 `clk_adc` cycles at 48 MHz) | RP2040 datasheet. |
| Mux-step IRQ | 300 cycles (2.5 µs) after each conversion start | After the conversion ends, so the address never moves mid-conversion. |
| Time uncertainty | 160 cycles | 1 µs TIMER resolution plus 40 cycles of allowance for when the PWM is enabled relative to the origin tick. The startup path is bounded at 27 cycles (see "Tick-to-enable bound"). |
| Settle allocation | 300 cycles (2.5 µs) | See the next section. |
| IRQ latency + handler budget | 240 cycles (2.0 µs) | 1000 − 300 − 160 − 300. |
| Channel skew | CH1 → CH10 = 9 slots = 75 µs | Sequential sampling. The generated architecture page quotes 72 µs from the earlier 8 µs-slot sketch; this engine's figure is 75 µs. |
| TIME and RANGE scan | 1 kS/s per channel | Channel `frame % 10` in slots 10 and 11. |

`_Static_assert`s in `acq_engine.h` enforce the arithmetic: the frame is exact, the slots are uniform, the conversion ends before the step, and the budget is positive.

### Settle estimate (to be replaced by measurement)

The path after an address change is:

1. The 74HC4067 propagation from address to output, at the actual supply.
2. The TLV9064 unity-gain buffer. Its 10 MHz GBW is a nominal device property from the catalog record.
3. The 100 Ω / 1 nF bucket, with τ = 100 ns. Reaching ½ LSB at 12 bits needs ln(8192) ≈ 9 τ ≈ 0.9 µs.

The buffer's slew and linear settle for a full-scale step, plus the mux propagation, are not characterised here. The 2.5 µs allocation assumes that they add less than about 1.6 µs to the RC term. **This is an assumption, and G05 must measure it.** If the measured settle exceeds the allocation, first shift `ACQ_STEP_OFFSET_CYCLES` down toward the 240-cycle conversion end, then reduce the IRQ budget. The frame itself does not change.

The earlier architecture note sketched a throw-away conversion before each kept one. This engine converts once per slot, because ADC0's input selection stays fixed during all ten signal slots. Only the external mux moves, and the 1 nF bucket supplies the ADC's sampling charge. If the bench shows a memory effect from the previous channel, move to 24 half-slots with a discarded conversion. That keeps the frame.

## How the timing stays uniform

- **ADC start instants are hardware-timed.**
  - PWM slice 0 wraps every 1000 cycles.
  - Its DREQ paces DMA channel "start", which writes the next word of a 12-entry table into `ADC_CS` (`EN | START_ONCE | AINSEL`).
  - A chained "reload" DMA channel re-arms "start" at the end of each table.
  - No CPU instruction lies between the timer wrap and the start of a conversion.
  - The only expected start jitter is DMA arbitration plus synchronisation into the 48 MHz `clk_adc` domain. It has not been measured.
- **Results are collected by DMA.** Two channels, "col A" and "col B", ping-pong the ADC FIFO (`DREQ_ADC`, `ERR` flag in bit 15) into an 8192-sample ring. Each conversion index maps to a fixed slot, `index % 12`.
- **The mux address is stepped by an IRQ on core1.**
  - PWM slice 1 runs at the same period, 300 cycles behind slice 0.
  - Its wrap IRQ is the only interrupt enabled on core1. The handler and the stepper run from RAM, with no flash execution and no libgcc helpers.
  - The handler plans the next address, writes GP2 to GP5 and GP14, then commits the time it wrote them.
  - IRQ latency affects only the settle margin, never the sample instant.
- **Missed-slot judgement.**
  - Each step measures time as a lower bound: the extended 1 µs TIMER minus the origin slack.
  - Every conversion that started since the previous step is judged against the address actually driven at that moment. That driven time is taken as an upper bound.
  - A conversion is **missed** if the address was wrong or had less than the settle allocation.
  - This judgement is conservative. The host model checks that the flagged set is exactly the set of slots that really saw a wrong or unsettled address, both when the IRQ is steadily late and when it stalls for 3 or 25 slots.
- **Consumer.**
  - Core0 drains only conversions that the stepper has already judged.
  - It pushes signal codes into the `scope_core` histories and runs the TIME and RANGE debounce.
  - A missed slot, an ADC `ERR` word or an overrun-lost signal sample is replaced by that channel's last valid code. This keeps the time axis uniform, and each replacement is counted in `held_samples`. Raw garbage never enters history.

## Startup and resync

The core1 stepper judges every slot against a software time origin: a 1 µs TIMER tick captured by core0. The ADC and the mux run from the physical origin: the instant the PWM slices are enabled. The two must be at most `ACQ_ORIGIN_SLACK_CYCLES` (40 cycles) apart. If the software origin were earlier than that, the stepper would move the mux early and judge the samples against its own wrong timeline. Wrong-channel samples would then reach history with no missed-slot flag. A host model of the earlier start sequence, preempted for 1200 cycles between capture and enable, accepted 2160 of 2400 samples from the wrong address with `missed_slots` = 0 (issue #18).

**Atomic start (`acq_epoch_start`).** Origin capture, publication of the whole epoch and PWM enable form one operation that core0 interrupts cannot split. The code is RAM-resident (`__not_in_flash_func(start_timers)`, everything inlined), so it never waits on XIP.

1. Disable core0 interrupts (`save_and_disable_interrupts`).
2. Write the fields that do not depend on the tick: `now_cycles` = 0 and the new generation number.
3. Spin to a TIMER tick edge and store it in `last_raw`. This is the software origin.
4. `__dmb()`, then store the generation in `armed`. A step handler that reads a non-zero `armed` also sees every field written before it. A handler that ran earlier saw `armed` = 0 and touched nothing.
5. Enable both PWM slices with one register write. This is the physical origin. Then restore interrupts.

The first step IRQ follows 300 cycles after step 5. Any core0 interrupt that becomes pending during the sequence is taken after step 5. It then delays only core0, never the origin.

**Stop and resync (`acq_epoch_stop`).** A resync no longer relies on a fixed delay.

1. Stop both PWM slices, then set `armed` = 0 and issue a barrier.
2. Ask core1 to disable its step IRQ and wait for its acknowledgement. Core1 handles the request in thread mode (its `__wfe` idle loop, woken by core0's `SEV`), where by construction no step handler is executing on that core. Core1 disables the IRQ and clears its pending bit, then acknowledges. After this, no handler is running and none can start.
3. Only then does core0 clear the PWM flag, abort DMA and reset the stepper and consumer state (`acq_engine_resync`).
4. Restart: clear the PWM IRQ flag, pre-drive slot 0's address and let it settle for 10 µs, ask core1 to enable its step IRQ (it clears the pending bit first), then run the same atomic start.

The step handler returns at once while `armed` = 0. This is a second guard for a handler that enters after the disarm.

### Tick-to-enable bound

`ACQ_TICK_TO_ENABLE_BOUND_CYCLES` = 27 cycles, and a `_Static_assert` keeps it within the 40-cycle slack. **Method:** a count from the source, using Cortex-M0+ instruction timings (ARM Cortex-M0+ TRM) and conservative RP2040 bus assumptions. Interrupts are off and the code is in RAM. No DMA channel is moving data at that point, because PWM is stopped and the ADC is idle.

| Step | Cycles |
|---|---|
| The tick edge falls anywhere in the spin iteration that observes it. That iteration is an APB load (≤ 6 assumed), a compare (1) and a taken branch (2). | ≤ 9 |
| Loop exit (branch not taken) | 1 |
| `STR last_raw` (SRAM) | 2 |
| `DMB` | 3 |
| `STR armed` (the generation is already in a register) | 2 |
| `STR` to `PWM EN` (APB write, ≤ 6 assumed) | ≤ 6 |
| Subtotal | ≤ 23 |
| Allowance: two literal-pool base reloads if the compiler rematerialises addresses (2 × 2) | 4 |
| **Bound** | **27** |

**Target verification: NOT_RUN.** No ARM toolchain was available where this was written. To verify, find `start_timers` in `firmware/build/scope10_acq.dis` (written by `pico_add_extra_outputs`) and count the instructions from the `ldr` that reads `TIMERAWL` and exits the spin loop up to the `str` to `PWM_EN`. If the count is above 27 cycles, raise the constant. If it is above 40, also raise `ACQ_ORIGIN_SLACK_CYCLES` and re-run the host tests. G05 must still measure the real value on the bench.

## Counters (USB serial, once per second)

```
acq,uptime_ms=…,frames=…,missed_slots=…,overrun_events=…,overrun_samples=…,fifo_errors=…,conversion_errors=…,held_samples=…,resyncs=…,hold_pressed=…,link_pressed=…
ch,<1..10>,last_code=…,time_code=…,range_code=…,range=…,pushed=…
```

- `missed_slots`: slots converted without a provably settled, correct address.
- `overrun_events` and `overrun_samples`: the consumer fell more than 7168 samples (about 60 ms) behind the DMA writer.
- `fifo_errors`: ADC FIFO overflow or underflow. Slot alignment is lost, so the engine stops, clears, restarts at a new origin and counts a `resync`. It does not fill the gap.
- `conversion_errors`: an ADC `ERR` bit in a FIFO word.
- `hold_pressed` and `link_pressed`: the raw HOLD and LINK button pins (1 = held down right now). These are not the HOLD and LINK modes. The renderer latches those modes from debounced presses, and the display shows the latched modes.

Every report line is printed on its own drain pass. The USB stdout timeout is limited to 2 ms, so a stalled host produces counted overruns instead of silent loss.

GP14 goes high once per frame, at the step that addresses slot 0. It stays high for one slot. Its rising edge marks when the step IRQ ran, including latency, so it can be measured on a bench scope. It does not mark the ADC start itself.

## Host tests (`python3 scripts/test_firmware.py`)

`test_acq.c` simulates the following at cycle level: PWM-paced conversion starts, the phase-offset step IRQ with injectable latency, jitter and stalls, a true settle requirement, a 1 µs floor-quantised timer, and DMA ring writes. It covers these cases:

- **Uniform slot timing.**
  - Adjacent slots are 1000 cycles apart and each channel's samples are exactly 100 µs apart. TIME and RANGE revisit a channel every 1 ms.
  - With any IRQ latency plus handler time up to the 240-cycle budget, over 1 s nominal, no slot is missed, there are 10 000 frames and 10 000 GP14 pulses, and the time and range decoding is correct.
- **Wrap-around.** The ring index wraps five times with every history sample correct.
- **Overrun.** A consumer stall of one full ring produces exactly one overrun, with the exact lost count. The histories stay time-aligned and all channels have equal push counts.
- **Missed-slot accounting under an injected stall.**
  - A 3.5-slot IRQ stall gives exactly 3 missed and 3 held samples.
  - A 25-slot stall across a frame boundary and both control slots gives engine count = true count.
  - One ADC `ERR` word is counted and held.
  - A steadily late IRQ gives engine count = true count.
- **Channel-order invariance.** A permuted signal-slot order yields byte-identical histories and control state. An invalid order is rejected.
- **Startup preemption.** The model separates the physical origin (PWM enable) from the software origin (captured tick). It feeds each mux input a distinct constant, so a wrong-address sample is recognisable. It runs `acq_epoch_start` with a core0 interrupt injected at each point: before masking, in the tick spin, between capture and arming, between arming and enable, between enable and the old publication point, and after the start. Interrupt lengths are 1, 1.2 and 25 slots, and core1 entry latency runs from 0 to 160 cycles. That gives 72 scenarios. Each one has zero wrong or accepted wrong-address samples, zero steps on an incomplete epoch, zero missed slots, and a tick-to-enable time within the 27-cycle bound. Negative controls run the old sequence in the same model. Preempted before enable, it accepts 2160 of 2400 wrong-address samples with `missed_slots` = 0. Preempted after enable, core1 steps on an unpublished epoch.
- **Repeated stop, resync and restart.** There are 24 cycles. Each stop is issued while a core1 step handler is mid-flight. The stop must wait until that handler has finished, and core1 must confirm that the step IRQ is off, before the reset. Later IRQ flags must not reach the stepper. Each restart is preempted at a different point. There are zero accepted wrong-address samples, and a disarmed handler returns without touching the engine.
- **`scope_core` integration.** The last 192 level-0 bins of every channel equal the expected per-frame codes. No garbage code reaches any history level.

These tests prove the scheduling and bookkeeping logic on a host. They do not prove RP2040 timing.

## G05 local procedure (hardware only; not done)

Run this on an assembled, G01/G06-cleared board, flashed with `firmware/build/scope10_acq.uf2` from `scripts/build_firmware.sh`. Record the board serial, the firmware SHA-256 from `reports/firmware-target-build.json`, the instruments and the temperature.

1. **Cadence.**
   - Scope GP14. Measure its period (nominal 100.000 µs) and its peak-to-peak edge jitter over at least 10⁶ frames.
   - Also probe ADDR0 (GP2), which toggles on most slot steps, to see the per-slot step latency distribution.
   - Confirm that the worst-case latency stays inside the 2.0 µs budget. Confirm that `missed_slots` stays 0 over a 10-minute run with USB serial attached and being read.
2. **Mux settle.**
   - Drive CH1 with −FS and CH2 with +FS (DC, through the normal input path).
   - Probe ADC0/TP20 against GP2 edges. Measure the time until the step stays within ½ LSB (about 0.4 mV at the ADC pin).
   - Repeat for the worst adjacent pair and for the TIME and RANGE banks (TP21 and TP22).
   - Compare with the 2.5 µs allocation. If it exceeds the allocation, retune `ACQ_STEP_OFFSET_CYCLES` or the settle constant, and re-run the host tests.
3. **ADC start alignment.** With a fast edge applied to one channel, confirm that the recorded sample index jumps in the slot the schedule predicts. The engine assumes a start within DMA/sync latency of the PWM wrap.
4. **Cross-talk.**
   - Apply a full-scale sine at 1 kHz and 4 kHz to one channel, with all other inputs terminated.
   - Record the per-channel codes from the serial counters (or a debug stream) and report the adjacent-slot and worst-case coupling in dB.
   - Repeat with the aggressor on each slot's predecessor.
5. **Alias response.**
   - Sweep 1 kHz to 20 kHz on one channel.
   - Confirm the analog anti-alias attenuation (`reports/analog-analysis.json` `filter_amplitude`) against the aliased amplitude the engine records above the 5 kHz Nyquist frequency.
   - Record where aliases fold, and state that the P0 target is CV/LFO/low audio, not a 20 kHz instrument.
6. **Counters under stress.**
   - Pause the USB host reader and confirm that `overrun_events` increments and nothing is silently dropped.
   - Confirm that `fifo_errors` and `resyncs` stay 0 in normal operation.

G05 closes only with this evidence recorded against the release gate. Desk work in this repository cannot close it.
