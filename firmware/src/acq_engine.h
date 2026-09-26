#ifndef ACQ_ENGINE_H
#define ACQ_ENGINE_H
/* Portable 10 kS/s/channel acquisition scheduler + ring buffer (no RP2040 headers).
 * RP2040 register code lives in acq_rp2040.c; firmware/ACQUISITION.md explains the design.
 *
 * Nominal design budget. These are DESIGN numbers, not measurements; G05 stays OPEN.
 *   All ten signal channels are sampled SEQUENTIALLY through one 74HC4067 (U7) into
 *   ADC0. There is no simultaneous sampling and no phase synchronisation between
 *   channels: CH(n+1) is converted one slot (8.333 us) after CH(n).
 *
 *   clk_sys 120 MHz (exact from the 12 MHz crystal) so the frame divides evenly:
 *     frame  = 100 us = 12000 cycles  -> 10 000 samples/s per channel (nominal)
 *     slot   = frame / 12 = 1000 cycles = 8.333 us, uniform for every slot
 *     slots 0..9 : ADC0 signal, one per channel, in acq_schedule order
 *     slot  10   : ADC1 TIME  of channel (frame % 10) -> 1000 samples/s per knob
 *     slot  11   : ADC2 RANGE of channel (frame % 10) -> 1000 samples/s per switch
 *   Aggregate ADC load 120 kS/s (RP2040 ADC limit 500 kS/s).
 *
 *   Slot k timeline (cycles after conversion k-1 started, k = slot index):
 *     0      conversion k-1 starts: PWM slice wrap -> DMA writes ADC CS.START_ONCE
 *     240    conversion done (96 clk_adc cycles at 48 MHz = 2 us)
 *     300    mux-step IRQ (second PWM slice, phase offset) asks for address of slot k
 *     +<=240 IRQ latency + handler budget before the address pins are written
 *     +160   time-uncertainty margin (1 us timer + 40-cycle origin slack; the driven
 *            time is taken as an upper bound)
 *     +300   allocated settle: 74HC4067 + TLV9064 buffer + 100 R / 1 nF bucket
 *     1000   conversion k starts
 *   The ADC start instant never depends on CPU latency; only the settle margin does.
 *   A slot whose address was not provably settled in time is flagged "missed" and its
 *   sample never reaches history as real data. */
#include "scope_core.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ACQ_CHANNELS SCOPE_CHANNELS
#define ACQ_SYS_CLK_HZ 120000000u
#define ACQ_SAMPLES_PER_CH_S 10000u
#define ACQ_SLOTS_PER_FRAME 12u
#define ACQ_SLOT_TIME 10u
#define ACQ_SLOT_RANGE 11u
#define ACQ_FRAME_CYCLES (ACQ_SYS_CLK_HZ / ACQ_SAMPLES_PER_CH_S)
#define ACQ_SLOT_CYCLES (ACQ_FRAME_CYCLES / ACQ_SLOTS_PER_FRAME)
#define ACQ_CYCLES_PER_US (ACQ_SYS_CLK_HZ / 1000000u)
#define ACQ_ADC_CONV_CYCLES (2u * ACQ_CYCLES_PER_US)
#define ACQ_STEP_OFFSET_CYCLES 300u
/* The target measures time with the 1 us TIMER from an origin taken on a timer tick,
 * the PWM slices being enabled at most ORIGIN_SLACK cycles after that tick. The caller
 * passes (elapsed - slack) as a lower bound; the true time is below that + UNCERTAINTY. */
#define ACQ_ORIGIN_SLACK_CYCLES 40u
/* Worst-case cycles from the TIMER tick edge to the PWM enable in acq_epoch_start(),
 * derived from the source with Cortex-M0+ instruction timings (firmware/ACQUISITION.md,
 * "Tick-to-enable bound"). A count from the compiled target's disassembly is NOT_RUN. */
#define ACQ_TICK_TO_ENABLE_BOUND_CYCLES 27u
#define ACQ_TIME_UNCERTAINTY_CYCLES (ACQ_CYCLES_PER_US + ACQ_ORIGIN_SLACK_CYCLES)
#define ACQ_SETTLE_CYCLES 300u
#define ACQ_ISR_BUDGET_CYCLES (ACQ_SLOT_CYCLES - ACQ_STEP_OFFSET_CYCLES \
                               - ACQ_TIME_UNCERTAINTY_CYCLES - ACQ_SETTLE_CYCLES)
#define ACQ_RING_BITS 13u
#define ACQ_RING_LEN (1u << ACQ_RING_BITS)
#define ACQ_RING_MASK (ACQ_RING_LEN - 1u)
/* Backlog beyond RING_LEN - GUARD is treated as an overrun, leaving the DMA writer
 * GUARD samples (8.5 ms) of headroom while a drain batch is being processed. */
#define ACQ_RING_GUARD 1024u
#define ACQ_CODE_ERR_BIT 0x8000u
#define ACQ_CODE_MASK 0x0fffu

_Static_assert(ACQ_FRAME_CYCLES * ACQ_SAMPLES_PER_CH_S == ACQ_SYS_CLK_HZ, "frame must be exact");
_Static_assert(ACQ_SLOT_CYCLES * ACQ_SLOTS_PER_FRAME == ACQ_FRAME_CYCLES, "slots must be uniform");
_Static_assert(ACQ_SLOTS_PER_FRAME == ACQ_CHANNELS + 2, "10 signal + TIME + RANGE");
_Static_assert(ACQ_ADC_CONV_CYCLES < ACQ_STEP_OFFSET_CYCLES, "mux must not move mid-conversion");
_Static_assert(ACQ_STEP_OFFSET_CYCLES + ACQ_TIME_UNCERTAINTY_CYCLES + ACQ_SETTLE_CYCLES
               < ACQ_SLOT_CYCLES, "slot has no IRQ latency budget left");
_Static_assert(ACQ_RING_GUARD < ACQ_RING_LEN / 2, "guard too large");
_Static_assert(ACQ_TICK_TO_ENABLE_BOUND_CYCLES <= ACQ_ORIGIN_SLACK_CYCLES,
               "startup path exceeds the origin slack the time bounds assume");

typedef enum { ACQ_KIND_SIGNAL = 0, ACQ_KIND_TIME = 1, ACQ_KIND_RANGE = 2 } acq_kind;

typedef struct {
    uint8_t kind;      /* acq_kind */
    uint8_t adc_input; /* 0 = ADC0 signal, 1 = ADC1 TIME, 2 = ADC2 RANGE */
    uint8_t channel;   /* 0-based front-panel channel (CH1 = 0) */
    uint8_t mux_addr;  /* 74HC4067 address; CH(n+1) on Yn, as in pico_diagnostic.c */
} acq_slot;

/* order[k] = channel converted in signal slot k. Must be a permutation of 0..9. */
typedef struct { uint8_t order[ACQ_CHANNELS]; } acq_schedule;

typedef struct {
    uint32_t frames;            /* complete frames consumed */
    uint32_t missed_slots;      /* slots converted without a provably settled address */
    uint32_t overrun_events;    /* consumer fell behind the DMA writer */
    uint32_t overrun_samples;   /* samples lost to those overruns */
    uint32_t fifo_errors;       /* ADC FIFO over/underflow (target only) */
    uint32_t conversion_errors; /* ADC ERR bit set in a FIFO word */
    uint32_t held_samples;      /* signal samples replaced by the channel's last valid code */
    uint32_t resyncs;           /* stream restarts after loss of slot alignment */
} acq_counters;

typedef struct {
    uint64_t next;       /* first conversion not yet known to have started */
    uint64_t next_start; /* its start time, cycles since engine origin */
    uint64_t driven_at;  /* upper bound on when the current address was driven */
    uint8_t next_sif;    /* slot-in-frame of `next` */
    uint8_t next_ctl;    /* control channel of the frame containing `next` */
    uint8_t driven_addr;
    uint8_t pending_addr;
} acq_stepper;

typedef struct {
    int8_t addr;      /* address to drive now, or -1 to leave the pins unchanged */
    bool frame_pulse; /* level for the GP14 timing test point (high for the slot-0 step) */
} acq_step_result;

typedef struct {
    /* Written by the DMA collector (target) or the model. Index = conversion number. */
    volatile uint16_t ring[ACQ_RING_LEN];
    /* missed_tag[i & MASK] == (i >> RING_BITS) + 1 marks conversion i as missed.
     * Written only by the stepper; the tag makes stale marks harmless without clearing. */
    volatile uint32_t missed_tag[ACQ_RING_LEN];
    acq_schedule sched;
    acq_stepper step;
    /* Low 32 bits of step.next, published by the stepper (possibly on the other core).
     * The consumer never reads a conversion the stepper has not yet judged. */
    volatile uint32_t evaluated;
    acq_counters cnt;
    /* consumer state */
    uint64_t read;
    uint8_t read_sif, read_ctl, read_frame_in_ms;
    uint32_t now_ms;
    scope_history *hist; /* ACQ_CHANNELS entries, caller-owned */
    bool have_last[ACQ_CHANNELS];
    uint16_t last_code[ACQ_CHANNELS];
    uint32_t pushed[ACQ_CHANNELS];
    uint16_t time_code[ACQ_CHANNELS];
    uint16_t range_code[ACQ_CHANNELS];
    scope_range_state range[ACQ_CHANNELS];
} acq_engine;

void acq_schedule_default(acq_schedule *s);
bool acq_schedule_valid(const acq_schedule *s);
acq_slot acq_slot_for(const acq_schedule *s, unsigned slot_in_frame, unsigned control_channel);
acq_slot acq_slot_at(const acq_schedule *s, uint64_t conversion);
uint64_t acq_slot_start_cycles(uint64_t conversion);

bool acq_engine_init(acq_engine *e, const acq_schedule *s, scope_history *hist);
/* After a hardware restart (stream alignment lost): time origin and indices restart at 0;
 * histories and last codes are kept, the gap is counted in cnt.resyncs, not filled. */
void acq_engine_resync(acq_engine *e);

/* Mux-step interrupt, two phases. `now` is a LOWER bound on cycles since the origin;
 * the caller drives r.addr (if >= 0) then calls commit with a fresh lower-bound time. */
acq_step_result acq_step_plan(acq_engine *e, uint64_t now);
void acq_step_commit(acq_engine *e, uint64_t now_after_write);

/* Consume up to max_samples of the `written` conversions produced so far, but only those
 * the stepper has already judged (a sample can land before its missed flag would). */
size_t acq_drain(acq_engine *e, uint64_t written, size_t max_samples);
#endif
