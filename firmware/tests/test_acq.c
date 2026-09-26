/* Host model of the acquisition engine: a cycle-level simulation of the PWM-paced ADC
 * starts, the phase-offset mux-step IRQ (with injectable latency and stalls), the mux
 * settle requirement and the DMA ring, driving the real acq_engine.c / scope_core.c.
 * This proves scheduling/bookkeeping logic only, not RP2040 timing. */
#include "acq_engine.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define GARBAGE_BASE 4032u

typedef struct {
    uint32_t latency, jitter, handler; /* cycles: nominal step -> IRQ entry, extra random, entry -> pin write */
    uint64_t stall_from, stall_until;  /* nominal steps in [from, until) coalesce into one IRQ at until */
    uint64_t drain_every;              /* drain after every N conversions */
    uint64_t pause_from, pause_until;  /* no draining for conversions in [from, until) */
    uint64_t err_at;                   /* conversion that carries the ADC ERR bit */
} sim_cfg;

typedef struct {
    uint64_t truth_bad;   /* conversions that really saw a wrong or unsettled address */
    uint64_t tp_rises;
    uint64_t tp_min_period, tp_max_period;
    uint64_t written;
} sim_out;

static acq_engine eng;
static scope_history hist[ACQ_CHANNELS];
static acq_engine eng2;
static scope_history hist2[ACQ_CHANNELS];

static uint16_t sig_code(unsigned ch, uint64_t frame) { return (uint16_t)(100u + (ch * 181u + frame * 13u) % 3000u); }
static uint16_t time_code(unsigned ch) { return (uint16_t)(200u + ch * 300u); }
static uint16_t range_code(unsigned ch) { static const uint16_t c[3] = {100, 2048, 4095}; return c[ch % 3u]; }
static int range_expect(unsigned ch) { return (int)(ch % 3u); }
static uint64_t meas(uint64_t t) { return t - t % ACQ_CYCLES_PER_US; } /* 1 us timer, floor */

static uint32_t rng_state = 12345u;
static uint32_t rnd(uint32_t n) {
    rng_state = rng_state * 1103515245u + 12345u;
    return n ? (rng_state >> 8) % (n + 1u) : 0u;
}

static uint64_t next_isr(const sim_cfg *c, uint64_t *k, bool *stall_fired) {
    for (;;) {
        uint64_t nom = ACQ_STEP_OFFSET_CYCLES + *k * ACQ_SLOT_CYCLES;
        (*k)++;
        if (nom >= c->stall_from && nom < c->stall_until) {
            if (!*stall_fired) { *stall_fired = true; return c->stall_until; }
            continue;
        }
        return nom + c->latency + rnd(c->jitter);
    }
}

static void run(acq_engine *e, const sim_cfg *c, uint64_t conversions, sim_out *o) {
    memset(o, 0, sizeof(*o));
    o->tp_min_period = UINT64_MAX;
    uint64_t k = 0, j = 0, last_rise = 0;
    bool stall_fired = false, tp = false;
    unsigned addr = e->step.driven_addr; /* pre-driven before the origin */
    uint64_t addr_at = 0;
    uint64_t t_isr = next_isr(c, &k, &stall_fired);
    /* Keep delivering step IRQs after the last conversion so the stepper judges the tail. */
    while (j < conversions || e->step.next < conversions) {
        uint64_t t_conv = acq_slot_start_cycles(j);
        if (t_isr < t_conv || j >= conversions) {
            uint64_t t_write = t_isr + c->handler;
            acq_step_result r = acq_step_plan(e, meas(t_isr));
            if (r.addr >= 0) { addr = (unsigned)r.addr; addr_at = t_write; }
            acq_step_commit(e, meas(t_write));
            if (r.frame_pulse && !tp && j < conversions) {
                if (o->tp_rises) {
                    uint64_t p = t_write - last_rise;
                    if (p < o->tp_min_period) o->tp_min_period = p;
                    if (p > o->tp_max_period) o->tp_max_period = p;
                }
                o->tp_rises++;
                last_rise = t_write;
            }
            tp = r.frame_pulse;
            t_isr = next_isr(c, &k, &stall_fired);
            continue;
        }
        acq_slot sl = acq_slot_at(&e->sched, j);
        uint64_t frame = j / ACQ_SLOTS_PER_FRAME;
        uint16_t code;
        if (addr == sl.mux_addr && addr_at + ACQ_SETTLE_CYCLES <= t_conv) {
            code = sl.kind == ACQ_KIND_SIGNAL ? sig_code(sl.channel, frame)
                 : sl.kind == ACQ_KIND_TIME ? time_code(sl.channel) : range_code(sl.channel);
        } else {
            code = (uint16_t)(GARBAGE_BASE + j % 64u);
            o->truth_bad++;
        }
        if (j == c->err_at) code |= ACQ_CODE_ERR_BIT;
        e->ring[(uint32_t)j & ACQ_RING_MASK] = code;
        j++;
        bool paused = j > c->pause_from && j <= c->pause_until;
        if (c->drain_every && j % c->drain_every == 0 && !paused) acq_drain(e, j, SIZE_MAX);
    }
    acq_drain(e, j, SIZE_MAX);
    o->written = j;
}

static sim_cfg base_cfg(void) {
    sim_cfg c;
    memset(&c, 0, sizeof c);
    c.handler = 60;
    c.drain_every = 97;
    c.err_at = UINT64_MAX;
    return c;
}

static void check_history_is_clean(const scope_history *h) {
    scope_bin b[SCOPE_HISTORY_BINS];
    for (unsigned c = 0; c < ACQ_CHANNELS; c++)
        for (unsigned lvl = 0; lvl < SCOPE_HISTORY_LEVELS; lvl++) {
            size_t n = scope_history_recent(&h[c], lvl, b, SCOPE_HISTORY_BINS);
            for (size_t i = 0; i < n; i++) assert(b[i].hi < GARBAGE_BASE);
        }
}

static void check_recent_matches(const acq_engine *e, const scope_history *h, uint64_t frames) {
    scope_bin b[SCOPE_HISTORY_BINS];
    for (unsigned c = 0; c < ACQ_CHANNELS; c++) {
        size_t n = scope_history_recent(&h[c], 0, b, SCOPE_HISTORY_BINS);
        assert(n == SCOPE_HISTORY_BINS);
        for (size_t i = 0; i < n; i++) {
            uint64_t f = frames - n + i;
            assert(b[i].lo == sig_code(c, f) && b[i].hi == sig_code(c, f));
        }
        assert(e->pushed[c] == frames);
    }
}

static void test_uniform_timing(void) {
    acq_schedule s;
    acq_schedule_default(&s);
    assert(ACQ_FRAME_CYCLES == 100u * ACQ_CYCLES_PER_US);
    assert(ACQ_ISR_BUDGET_CYCLES > 0);
    uint64_t last_sig[ACQ_CHANNELS], last_ctl[2][ACQ_CHANNELS];
    bool seen_sig[ACQ_CHANNELS] = {false}, seen_ctl[2][ACQ_CHANNELS] = {{false}};
    for (uint64_t j = 0; j < 12u * 200u; j++) {
        assert(acq_slot_start_cycles(j + 1) - acq_slot_start_cycles(j) == ACQ_SLOT_CYCLES);
        acq_slot sl = acq_slot_at(&s, j);
        uint64_t t = acq_slot_start_cycles(j);
        if (sl.kind == ACQ_KIND_SIGNAL) {
            assert(sl.adc_input == 0 && sl.mux_addr == sl.channel);
            if (seen_sig[sl.channel]) assert(t - last_sig[sl.channel] == ACQ_FRAME_CYCLES);
            seen_sig[sl.channel] = true; last_sig[sl.channel] = t;
        } else {
            unsigned w = sl.kind == ACQ_KIND_TIME ? 0u : 1u;
            assert(sl.adc_input == 1u + w);
            if (seen_ctl[w][sl.channel]) assert(t - last_ctl[w][sl.channel] == 10u * ACQ_FRAME_CYCLES);
            seen_ctl[w][sl.channel] = true; last_ctl[w][sl.channel] = t;
        }
    }
    /* Any IRQ latency + handler time inside the budget: no slot is missed, no bad sample. */
    sim_cfg c = base_cfg();
    c.latency = 0; c.jitter = ACQ_ISR_BUDGET_CYCLES - c.handler;
    sim_out o;
    assert(acq_engine_init(&eng, &s, hist));
    run(&eng, &c, 12u * 10000u, &o); /* 1 s nominal */
    assert(o.truth_bad == 0 && eng.cnt.missed_slots == 0 && eng.cnt.held_samples == 0);
    assert(eng.cnt.frames == 10000u && eng.cnt.overrun_events == 0);
    assert(o.tp_rises == 10000u);
    assert(o.tp_min_period >= ACQ_FRAME_CYCLES - c.jitter && o.tp_max_period <= ACQ_FRAME_CYCLES + c.jitter);
    check_recent_matches(&eng, hist, 10000u);
    for (unsigned ch = 0; ch < ACQ_CHANNELS; ch++) {
        assert(eng.time_code[ch] == time_code(ch));
        assert(eng.range[ch].stable == range_expect(ch));
    }
    /* The worst-case budget edge: latency exactly at the budget still passes. */
    c.jitter = 0; c.latency = ACQ_ISR_BUDGET_CYCLES - c.handler;
    assert(acq_engine_init(&eng, &s, hist));
    run(&eng, &c, 12u * 1000u, &o);
    assert(o.truth_bad == 0 && eng.cnt.missed_slots == 0);
    /* Consistently late IRQ: every unsettled slot is flagged, and nothing else. */
    c.latency = ACQ_ISR_BUDGET_CYCLES + 130u;
    assert(acq_engine_init(&eng, &s, hist));
    run(&eng, &c, 12u * 1000u, &o);
    assert(o.truth_bad > 0 && eng.cnt.missed_slots == o.truth_bad);
    check_history_is_clean(hist);
}

static void test_wraparound_and_overrun(void) {
    acq_schedule s;
    acq_schedule_default(&s);
    sim_cfg c = base_cfg();
    c.jitter = 150;
    sim_out o;
    uint64_t n = 5u * ACQ_RING_LEN + 7u * ACQ_SLOTS_PER_FRAME; /* ring index wraps 5 times */
    n -= n % ACQ_SLOTS_PER_FRAME;
    assert(acq_engine_init(&eng, &s, hist));
    run(&eng, &c, n, &o);
    assert(eng.read == n && eng.cnt.overrun_events == 0 && eng.cnt.missed_slots == 0);
    check_recent_matches(&eng, hist, n / ACQ_SLOTS_PER_FRAME);
    /* Consumer stalls for a full ring: one overrun, counted exactly, time axis kept. */
    c.pause_from = 1000; c.pause_until = 1000 + ACQ_RING_LEN;
    assert(acq_engine_init(&eng, &s, hist));
    run(&eng, &c, n, &o);
    uint64_t resume = c.pause_until + (c.drain_every - c.pause_until % c.drain_every) % c.drain_every;
    if (resume == c.pause_until) resume += c.drain_every;
    /* The drain right after conversion j-1 can consume only 0..j-2: j-1 is not judged yet. */
    uint64_t last_drain = (c.pause_from / c.drain_every) * c.drain_every - 1u;
    uint64_t expect_lost = (resume - last_drain) - (ACQ_RING_LEN - ACQ_RING_GUARD);
    assert(eng.cnt.overrun_events == 1 && eng.cnt.overrun_samples == expect_lost);
    assert(eng.cnt.held_samples > 0 && eng.cnt.held_samples <= expect_lost);
    assert(eng.read == n);
    check_recent_matches(&eng, hist, n / ACQ_SLOTS_PER_FRAME);
    check_history_is_clean(hist);
}

static void test_injected_stall(void) {
    acq_schedule s;
    acq_schedule_default(&s);
    sim_cfg c = base_cfg();
    /* Steps 41..43 are swallowed; one late IRQ at 43801 cycles. Slots 41 and 42 convert
     * with slot 40's address and slot 43 cannot settle: exactly three missed slots. */
    c.stall_from = ACQ_STEP_OFFSET_CYCLES + 40u * ACQ_SLOT_CYCLES + 1u;
    c.stall_until = c.stall_from + 3u * ACQ_SLOT_CYCLES + ACQ_SLOT_CYCLES / 2u;
    sim_out o;
    assert(acq_engine_init(&eng, &s, hist));
    run(&eng, &c, 12u * 500u, &o);
    assert(o.truth_bad == 3 && eng.cnt.missed_slots == 3 && eng.cnt.held_samples == 3);
    for (unsigned ch = 1; ch < ACQ_CHANNELS; ch++) assert(eng.pushed[ch] == eng.pushed[0]);
    assert(eng.pushed[0] == 500u);
    check_history_is_clean(hist);
    /* A long stall (25 slots) spanning a frame boundary and both control slots. */
    c.stall_from = ACQ_STEP_OFFSET_CYCLES + 100u * ACQ_SLOT_CYCLES + 1u;
    c.stall_until = c.stall_from + 25u * ACQ_SLOT_CYCLES;
    assert(acq_engine_init(&eng, &s, hist));
    run(&eng, &c, 12u * 500u, &o);
    assert(o.truth_bad > 20 && eng.cnt.missed_slots == o.truth_bad);
    check_history_is_clean(hist);
    /* ADC ERR bit on one signal conversion: counted and held, not pushed as data. */
    c = base_cfg();
    c.err_at = 12u * 30u + 4u;
    assert(acq_engine_init(&eng, &s, hist));
    run(&eng, &c, 12u * 100u, &o);
    assert(eng.cnt.conversion_errors == 1 && eng.cnt.held_samples == 1 && eng.cnt.missed_slots == 0);
}

static void test_channel_order_invariance(void) {
    acq_schedule a, b = {{7, 2, 9, 0, 5, 1, 8, 3, 6, 4}}, bad = {{0, 1, 2, 3, 4, 5, 6, 7, 8, 8}};
    acq_schedule_default(&a);
    assert(acq_schedule_valid(&b) && !acq_schedule_valid(&bad));
    assert(!acq_engine_init(&eng2, &bad, hist2));
    sim_cfg c = base_cfg();
    c.jitter = ACQ_ISR_BUDGET_CYCLES - c.handler;
    sim_out oa, ob;
    rng_state = 99u;
    assert(acq_engine_init(&eng, &a, hist));
    run(&eng, &c, 12u * 3000u, &oa);
    rng_state = 99u;
    assert(acq_engine_init(&eng2, &b, hist2));
    run(&eng2, &c, 12u * 3000u, &ob);
    assert(eng.cnt.missed_slots == 0 && eng2.cnt.missed_slots == 0);
    for (unsigned ch = 0; ch < ACQ_CHANNELS; ch++) {
        assert(memcmp(&hist[ch], &hist2[ch], sizeof(scope_history)) == 0);
        assert(eng.time_code[ch] == eng2.time_code[ch] && eng.range[ch].stable == eng2.range[ch].stable);
    }
    check_recent_matches(&eng2, hist2, 3000u);
    /* Resync keeps histories and counts the discontinuity. */
    uint32_t pushed = eng2.pushed[3];
    acq_engine_resync(&eng2);
    assert(eng2.cnt.resyncs == 1 && eng2.read == 0 && eng2.step.next == 0 && eng2.pushed[3] == pushed);
}

int main(void) {
    test_uniform_timing();
    test_wraparound_and_overrun();
    test_injected_stall();
    test_channel_order_invariance();
    printf("PASS: acq uniform slots (%u cycles, frame %u cycles @ %u MHz nominal), ring wrap/overrun,"
           " injected-stall missed-slot accounting, channel-order invariance, scope_core history.\n",
           ACQ_SLOT_CYCLES, ACQ_FRAME_CYCLES, ACQ_SYS_CLK_HZ / 1000000u);
    printf("Acquisition engine RAM (ring + missed tags + state): %zu bytes; IRQ budget %u cycles.\n",
           sizeof(acq_engine), (unsigned)ACQ_ISR_BUDGET_CYCLES);
    return 0;
}
