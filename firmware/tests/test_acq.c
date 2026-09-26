/* Host model of the acquisition engine: a cycle-level simulation of the PWM-paced ADC
 * starts, the phase-offset mux-step IRQ (with injectable latency and stalls), the mux
 * settle requirement and the DMA ring, driving the real acq_engine.c / scope_core.c.
 * This proves scheduling/bookkeeping logic only, not RP2040 timing. */
#include "acq_engine.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Hooks for acq_epoch.h: a simulated core0 clock with injectable preemption (see the
 * startup model below). Each hook is an instruction boundary where a pending core0
 * interrupt is taken unless interrupts are masked. */
static uint32_t sim_irq_save(void);
static void sim_irq_restore(uint32_t s);
static uint32_t sim_tick(void);
static void sim_dmb(void);
static void sim_pwm_enable(void);
static void sim_pwm_disable(void);
static void sim_sev(void);
static void sim_wait(void);
static void sim_step_irq_set(bool on);
#define ACQ_EPOCH_IRQ_SAVE() sim_irq_save()
#define ACQ_EPOCH_IRQ_RESTORE(s) sim_irq_restore(s)
#define ACQ_EPOCH_TICK() sim_tick()
#define ACQ_EPOCH_DMB() sim_dmb()
#define ACQ_EPOCH_PWM_ENABLE() sim_pwm_enable()
#define ACQ_EPOCH_PWM_DISABLE() sim_pwm_disable()
#define ACQ_EPOCH_SEV() sim_sev()
#define ACQ_EPOCH_WAIT() sim_wait()
#define ACQ_EPOCH_STEP_IRQ_SET(on) sim_step_irq_set(on)
#include "acq_epoch.h"

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


/* ---- Startup / resync model -------------------------------------------------------
 * Distinguishes the PHYSICAL origin (the instant the PWM slices are enabled) from the
 * SOFTWARE origin (the TIMER tick captured into the epoch), as in the #18 reproduction.
 * core0 runs acq_epoch_start()/acq_epoch_stop() against a cycle clock; each hook is an
 * instruction boundary where an injected core0 interrupt (USB servicing, say) is taken
 * if interrupts are enabled. core1 is an event model: PWM step-slice wraps raise the IRQ
 * flag, the handler enters `latency` cycles later (acq_epoch_enter, plan) and writes the
 * pins / commits `handler` cycles after that; core1 thread mode runs
 * acq_epoch_core1_service() whenever no handler is executing. Every mux input carries a
 * distinct constant (100 + 100 * address), so a wrong-address sample is recognisable. */
#define NONE UINT64_MAX
#define MODEL_CONV 2400u /* 200 frames, below ACQ_RING_LEN: no ring wrap inside a run */
#define TICK_COST 9u     /* spin iteration: APB load + compare + taken branch */
#define STORE_COST 2u
#define DMB_COST 3u
#define APB_STORE_COST 6u

/* Where an injected core0 interrupt becomes pending, named by what has happened so far. */
typedef enum {
    P_NONE = 0,
    P_BEFORE_MASK,     /* before interrupts are disabled */
    P_IN_SPIN,         /* while waiting for the origin tick */
    P_AFTER_CAPTURE,   /* tick captured, epoch not yet armed */
    P_BEFORE_ENABLE,   /* armed (atomic) / captured (pre-fix), PWM not yet enabled */
    P_AFTER_ENABLE,    /* PWM running; the pre-fix code publishes only after this */
    P_AFTER_START,     /* start sequence complete */
    P_COUNT
} preempt_point;

typedef struct {
    uint64_t t;             /* core0 time, absolute cycles */
    uint32_t tick_phase;    /* TIMER edges at t = k * CYCLES_PER_US - phase */
    bool masked;
    preempt_point preempt_at;
    uint64_t preempt_len;
    bool preempt_pending;
    uint32_t last_tick, captured_raw;
    /* physical PWM */
    bool pwm_on;
    uint64_t t_pwm, k_next, intr_at, j_next;
    /* core1 */
    uint32_t latency, jitter, handler, lat_cur;
    bool irq_on, busy, legacy, first_step, on_core1;
    uint64_t c1_t, commit_t;
    int pend_addr;
    unsigned pins;
    uint64_t pins_at;
    /* results */
    uint64_t gated, stale, steps, waits;
    int64_t origin_delta_max;
    bool wrong[MODEL_CONV];
} world;

static world w;
static acq_epoch ep;

static uint32_t raw_at(uint64_t t) { return (uint32_t)((t + w.tick_phase) / ACQ_CYCLES_PER_US); }
static uint64_t edge_of(uint32_t raw) { return (uint64_t)raw * ACQ_CYCLES_PER_US - w.tick_phase; }

static void c1_run_until(uint64_t t) {
    for (;;) {
        uint64_t t_wrap = w.pwm_on ? w.t_pwm + ACQ_STEP_OFFSET_CYCLES + w.k_next * ACQ_SLOT_CYCLES : NONE;
        uint64_t t_entry = NONE;
        if (w.intr_at != NONE && w.irq_on && !w.busy) {
            t_entry = w.intr_at + w.lat_cur;
            if (t_entry < w.c1_t) t_entry = w.c1_t;
        }
        uint64_t t_commit = w.busy ? w.commit_t : NONE;
        uint64_t t_conv = w.pwm_on && w.j_next < MODEL_CONV ? w.t_pwm + acq_slot_start_cycles(w.j_next) : NONE;
        uint64_t tn = t_wrap < t_entry ? t_wrap : t_entry;
        if (t_commit < tn) tn = t_commit;
        if (t_conv < tn) tn = t_conv;
        if (tn == NONE || tn > t) break;
        w.c1_t = tn;
        if (tn == t_conv) { /* ADC conversion: samples whatever the mux passes right now */
            uint64_t j = w.j_next++;
            acq_slot sl = acq_slot_at(&eng.sched, j);
            w.wrong[j] = w.pins != sl.mux_addr || w.pins_at + ACQ_SETTLE_CYCLES > tn;
            eng.ring[(uint32_t)j & ACQ_RING_MASK] = (uint16_t)(100u + 100u * w.pins);
        } else if (tn == t_commit) {
            if (w.pend_addr >= 0) { w.pins = (unsigned)w.pend_addr; w.pins_at = tn; }
            acq_step_commit(&eng, acq_epoch_lower_bound(&ep, raw_at(tn)));
            w.busy = false;
        } else if (tn == t_wrap) {
            if (w.intr_at == NONE) { w.intr_at = t_wrap; w.lat_cur = w.latency + rnd(w.jitter); }
            w.k_next++;
        } else {
            w.intr_at = NONE; /* pwm_clear_irq at handler entry */
            w.on_core1 = true;
            bool armed = w.legacy || acq_epoch_enter(&ep);
            w.on_core1 = false;
            if (!armed) { w.gated++; continue; }
            if (w.first_step) {
                if (ep.now_cycles != 0u || ep.last_raw != w.captured_raw) w.stale++;
                w.first_step = false;
            }
            w.steps++;
            w.pend_addr = acq_step_plan(&eng, acq_epoch_lower_bound(&ep, raw_at(tn))).addr;
            w.busy = true;
            w.commit_t = tn + w.handler;
        }
    }
    if (!w.busy) {
        w.on_core1 = true;
        acq_epoch_core1_service(&ep);
        w.on_core1 = false;
    }
}

/* Barrier/event hooks executed by core1 code cost core0 nothing. */
static void boundary(uint64_t cost, preempt_point here) {
    if (w.on_core1) return;
    if (here != P_NONE && here == w.preempt_at) { w.preempt_pending = true; w.preempt_at = P_NONE; }
    if (w.preempt_pending && !w.masked) {
        w.preempt_pending = false;
        w.t += w.preempt_len;
        c1_run_until(w.t);
    }
    w.t += cost;
    c1_run_until(w.t);
}

static uint32_t sim_irq_save(void) { boundary(1, P_BEFORE_MASK); uint32_t s = w.masked; w.masked = true; return s; }
static void sim_irq_restore(uint32_t s) { boundary(1, P_AFTER_ENABLE); w.masked = s != 0u; boundary(0, P_NONE); }
static uint32_t sim_tick(void) {
    boundary(0, P_IN_SPIN);
    w.last_tick = raw_at(w.t + TICK_COST);
    w.t += TICK_COST;
    return w.last_tick;
}
static void sim_dmb(void) { boundary(STORE_COST + DMB_COST, P_AFTER_CAPTURE); }
static void sim_sev(void) { boundary(1, P_NONE); }
static void sim_wait(void) { w.waits++; boundary(4, P_NONE); }
static void sim_pwm_enable(void) {
    boundary(STORE_COST, P_BEFORE_ENABLE); /* the store to `armed` just before */
    w.t += APB_STORE_COST;
    w.pwm_on = true;
    w.t_pwm = w.t;
    w.k_next = 0;
    w.j_next = 0;
    w.first_step = true;
    w.captured_raw = w.last_tick;
    int64_t d = (int64_t)(w.t_pwm - edge_of(w.captured_raw));
    if (d > w.origin_delta_max) w.origin_delta_max = d;
    c1_run_until(w.t);
}
static void sim_pwm_disable(void) { boundary(APB_STORE_COST, P_NONE); w.pwm_on = false; }
static void sim_step_irq_set(bool on) { w.irq_on = on; }

/* The pre-fix start_timers(): interrupts enabled, PWM enabled before publication. */
static void legacy_start(void) {
    uint32_t r0 = ACQ_EPOCH_TICK(), r;
    while ((r = ACQ_EPOCH_TICK()) == r0) {
    }
    ACQ_EPOCH_PWM_ENABLE();
    boundary(STORE_COST, P_AFTER_ENABLE);
    ep.last_raw = r;
    ep.now_cycles = 0u;
    ACQ_EPOCH_DMB();
}

typedef struct { uint64_t wrong, accepted_wrong; } model_out;

/* Adapter bring-up for one run (acq_hw_start order): clear the step IRQ flag, drive slot
 * 0's address and let it settle, have core1 enable its IRQ, then the atomic start. */
static void model_start(bool legacy, preempt_point preempt_at, uint64_t preempt_len) {
    w.intr_at = NONE;
    w.pins = eng.step.driven_addr;
    w.pins_at = w.t;
    w.t += 10u * ACQ_CYCLES_PER_US;
    w.legacy = legacy;
    if (!legacy) acq_epoch_core1_request(&ep, true);
    else w.irq_on = true;
    w.preempt_at = preempt_at;
    w.preempt_len = preempt_len;
    w.preempt_pending = false;
    if (legacy) legacy_start(); else acq_epoch_start(&ep);
    boundary(0, P_AFTER_START);
    assert(w.preempt_at == P_NONE && !w.preempt_pending); /* the injection really happened */
}

static void model_acquire(model_out *o) {
    memset(o, 0, sizeof *o);
    while (w.j_next < MODEL_CONV || eng.step.next < MODEL_CONV) {
        w.t += 97u * ACQ_SLOT_CYCLES;
        c1_run_until(w.t);
        acq_drain(&eng, w.j_next, SIZE_MAX);
    }
    acq_drain(&eng, MODEL_CONV, SIZE_MAX);
    for (uint64_t j = 0; j < MODEL_CONV; j++) {
        if (!w.wrong[j]) continue;
        o->wrong++;
        if (eng.missed_tag[j] != (uint32_t)(j >> ACQ_RING_BITS) + 1u) o->accepted_wrong++;
    }
}

/* Every history bin of every channel holds that channel's own constant. */
static bool model_history_clean(void) {
    scope_bin b[SCOPE_HISTORY_BINS];
    for (unsigned c = 0; c < ACQ_CHANNELS; c++)
        for (unsigned lvl = 0; lvl < SCOPE_HISTORY_LEVELS; lvl++) {
            size_t n = scope_history_recent(&hist[c], lvl, b, SCOPE_HISTORY_BINS);
            for (size_t i = 0; i < n; i++)
                if (b[i].lo != 100u + 100u * c || b[i].hi != 100u + 100u * c) return false;
        }
    return true;
}

static void model_boot(uint32_t latency, uint32_t handler, uint32_t tick_phase) {
    acq_schedule s;
    acq_schedule_default(&s);
    assert(acq_engine_init(&eng, &s, hist));
    memset(&w, 0, sizeof w);
    memset(&ep, 0, sizeof ep);
    w.t = 1000000u + tick_phase * 7u; /* arbitrary non-zero TIMER value and phase */
    w.tick_phase = tick_phase;
    w.latency = latency;
    w.handler = handler;
    w.intr_at = NONE;
    w.preempt_at = P_NONE;
}

/* Preemption injected at every point of the start sequence (before masking, in the tick
 * spin, between capture and arming, between arming and enable, between enable and the
 * pre-fix publication point, after the start), of one slot, 1.2 slots and 25 slots, with
 * 0..160 cycles of core1 IRQ-entry latency and varied TIMER phase. */
static void test_startup_preemption(void) {
    static const uint64_t lens[] = {ACQ_SLOT_CYCLES, 1200u, 25u * ACQ_SLOT_CYCLES};
    static const uint32_t lats[] = {0u, 40u, 100u, 160u};
    unsigned scenarios = 0;
    int64_t delta_max = 0;
    for (unsigned li = 0; li < 4u; li++)
        for (unsigned pi = 0; pi < 3u; pi++)
            for (unsigned at = P_BEFORE_MASK; at < P_COUNT; at++) {
                model_boot(lats[li], 60u, (at * 37u + li * 11u + pi * 5u) % ACQ_CYCLES_PER_US);
                model_start(false, (preempt_point)at, lens[pi]);
                model_out o;
                model_acquire(&o);
                assert(o.wrong == 0 && o.accepted_wrong == 0 && w.stale == 0);
                assert(eng.cnt.missed_slots == 0 && eng.cnt.held_samples == 0);
                assert(w.origin_delta_max >= 0 && w.origin_delta_max <= (int64_t)ACQ_TICK_TO_ENABLE_BOUND_CYCLES);
                assert(model_history_clean());
                if (w.origin_delta_max > delta_max) delta_max = w.origin_delta_max;
                scenarios++;
            }
    /* Negative controls on the pre-fix sequence, proving the model sees both races.
     * Preempted between capture and enable: software origin 1200 cycles early,
     * wrong-address samples accepted with no missed flag. */
    model_boot(0u, 60u, 0u);
    model_start(true, P_BEFORE_ENABLE, 1200u);
    model_out before;
    model_acquire(&before);
    assert(before.accepted_wrong > 0 && eng.cnt.missed_slots == 0 && !model_history_clean());
    /* Preempted between enable and publication: core1 steps on an unpublished epoch. */
    model_boot(0u, 60u, 0u);
    model_start(true, P_AFTER_ENABLE, 1200u);
    model_out between;
    model_acquire(&between);
    assert(w.stale > 0);
    printf("startup: %u preempted atomic starts, 0 wrong/0 accepted-wrong/0 stale, tick-to-enable <= %lld"
           " cycles (model; bound %u, slack %u). Pre-fix negative controls: preempt-before-enable"
           " accepted-wrong=%llu/%u missed=0; preempt-after-enable stale-epoch steps=%llu.\n",
           scenarios, (long long)delta_max, ACQ_TICK_TO_ENABLE_BOUND_CYCLES, ACQ_ORIGIN_SLACK_CYCLES,
           (unsigned long long)before.accepted_wrong, MODEL_CONV, (unsigned long long)w.stale);
}

/* Repeated stop / resync / restart, each stop issued while a core1 step handler is
 * mid-flight (entered, pins not yet written), each restart preempted at a different
 * boundary. The stop must not return until core1 confirms quiescence. */
static void test_resync_cycles(void) {
    model_boot(40u, 150u, 13u);
    model_start(false, P_NONE, 0u);
    unsigned cycles = 0;
    for (unsigned n = 0; n < 24u; n++) {
        model_out o;
        model_acquire(&o);
        assert(o.accepted_wrong == 0 && o.wrong == 0 && w.stale == 0);
        while (!w.busy) { w.t++; c1_run_until(w.t); } /* core1 is inside the handler now */
        uint64_t waits = w.waits;
        acq_epoch_stop(&ep);
        /* core0 had to wait: the handler finished (pins written, commit done) before the
         * acknowledgement, and the step IRQ is off, so the reset below cannot race it. */
        assert(w.waits > waits && !w.busy && !w.irq_on && ep.armed == 0u);
        /* Anything the stopped slices still raise can no longer reach the stepper. */
        uint64_t steps = w.steps;
        w.intr_at = w.t;
        c1_run_until(w.t + 5u * ACQ_SLOT_CYCLES);
        assert(w.steps == steps);
        w.t += 5u * ACQ_SLOT_CYCLES;
        acq_engine_resync(&eng);
        model_start(false, (preempt_point)(n % P_COUNT), n % 2u ? 1200u : 25u * ACQ_SLOT_CYCLES);
        cycles++;
    }
    model_out o;
    model_acquire(&o);
    assert(o.accepted_wrong == 0 && o.wrong == 0 && w.stale == 0);
    assert(eng.cnt.resyncs == cycles && eng.cnt.missed_slots == 0 && model_history_clean());
    assert(w.origin_delta_max <= (int64_t)ACQ_TICK_TO_ENABLE_BOUND_CYCLES);
    /* A disarmed epoch gates a handler that does get in (e.g. a flag raised just before
     * the stop): it returns without touching the engine. */
    uint64_t gated = w.gated;
    acq_epoch_stop(&ep);
    w.irq_on = true;
    w.intr_at = w.t;
    c1_run_until(w.t + ACQ_SLOT_CYCLES);
    assert(w.gated == gated + 1u);
    printf("resync: %u stop/resync/restart cycles, each stop with core1 mid-handler; 0 accepted"
           " wrong-address samples, disarmed handler gated.\n", cycles);
}

int main(void) {
    test_uniform_timing();
    test_wraparound_and_overrun();
    test_injected_stall();
    test_channel_order_invariance();
    test_startup_preemption();
    test_resync_cycles();
    printf("PASS: acq uniform slots (%u cycles, frame %u cycles @ %u MHz nominal), ring wrap/overrun,"
           " injected-stall missed-slot accounting, channel-order invariance, scope_core history.\n",
           ACQ_SLOT_CYCLES, ACQ_FRAME_CYCLES, ACQ_SYS_CLK_HZ / 1000000u);
    printf("Acquisition engine RAM (ring + missed tags + state): %zu bytes; IRQ budget %u cycles.\n",
           sizeof(acq_engine), (unsigned)ACQ_ISR_BUDGET_CYCLES);
    return 0;
}
