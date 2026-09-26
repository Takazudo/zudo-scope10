#include "acq_engine.h"

/* The stepper runs in the mux-step IRQ; on the target it must not execute from flash
 * (an XIP cache miss would eat the settle budget). No divisions or 64-bit multiplies
 * are used on that path, so no libgcc helper is pulled in from flash either. */
#if defined(ACQ_IN_RAM) && ACQ_IN_RAM
#define ACQ_RAMFUNC __attribute__((section(".time_critical.acq_engine")))
#else
#define ACQ_RAMFUNC
#endif

void acq_schedule_default(acq_schedule *s) {
    if (!s) return;
    for (unsigned k = 0; k < ACQ_CHANNELS; k++) s->order[k] = (uint8_t)k;
}

bool acq_schedule_valid(const acq_schedule *s) {
    if (!s) return false;
    bool seen[ACQ_CHANNELS] = {false};
    for (unsigned k = 0; k < ACQ_CHANNELS; k++) {
        if (s->order[k] >= ACQ_CHANNELS || seen[s->order[k]]) return false;
        seen[s->order[k]] = true;
    }
    return true;
}

static inline __attribute__((always_inline)) acq_slot slot_for(const acq_schedule *s, unsigned sif, unsigned ctl) {
    acq_slot r;
    if (sif < ACQ_CHANNELS) {
        r.kind = ACQ_KIND_SIGNAL; r.adc_input = 0; r.channel = s->order[sif];
    } else {
        r.kind = sif == ACQ_SLOT_TIME ? ACQ_KIND_TIME : ACQ_KIND_RANGE;
        r.adc_input = (uint8_t)r.kind; r.channel = (uint8_t)ctl;
    }
    r.mux_addr = r.channel;
    return r;
}

acq_slot acq_slot_for(const acq_schedule *s, unsigned sif, unsigned ctl) {
    return slot_for(s, sif % ACQ_SLOTS_PER_FRAME, ctl % ACQ_CHANNELS);
}

acq_slot acq_slot_at(const acq_schedule *s, uint64_t conversion) {
    uint64_t frame = conversion / ACQ_SLOTS_PER_FRAME;
    return slot_for(s, (unsigned)(conversion % ACQ_SLOTS_PER_FRAME), (unsigned)(frame % ACQ_CHANNELS));
}

uint64_t acq_slot_start_cycles(uint64_t conversion) {
    return (conversion + 1u) * ACQ_SLOT_CYCLES;
}

static void stepper_reset(acq_engine *e) {
    acq_stepper *s = &e->step;
    s->next = 0;
    s->next_start = ACQ_SLOT_CYCLES;
    s->next_sif = 0;
    s->next_ctl = 0;
    /* The caller drives this address before the origin; SLOT_CYCLES >= SETTLE_CYCLES. */
    s->driven_addr = slot_for(&e->sched, 0, 0).mux_addr;
    s->pending_addr = s->driven_addr;
    s->driven_at = 0;
    e->evaluated = 0;
}

static void consumer_reset(acq_engine *e) {
    e->read = 0;
    e->read_sif = 0;
    e->read_ctl = 0;
    for (unsigned i = 0; i < ACQ_RING_LEN; i++) e->missed_tag[i] = 0;
}

bool acq_engine_init(acq_engine *e, const acq_schedule *s, scope_history *hist) {
    if (!e || !hist || !acq_schedule_valid(s)) return false;
    e->sched = *s;
    e->hist = hist;
    e->cnt = (acq_counters){0};
    e->read_frame_in_ms = 0;
    e->now_ms = 0;
    for (unsigned c = 0; c < ACQ_CHANNELS; c++) {
        scope_history_init(&hist[c]);
        e->have_last[c] = false;
        e->last_code[c] = 0;
        e->pushed[c] = 0;
        e->time_code[c] = 0;
        e->range_code[c] = 0;
        e->range[c] = (scope_range_state){-1, -1, 0};
    }
    for (unsigned i = 0; i < ACQ_RING_LEN; i++) e->ring[i] = 0;
    consumer_reset(e);
    stepper_reset(e);
    return true;
}

void acq_engine_resync(acq_engine *e) {
    if (!e) return;
    e->cnt.resyncs++;
    consumer_reset(e);
    stepper_reset(e);
}

static inline __attribute__((always_inline)) uint32_t missed_tag_of(uint64_t conversion) {
    return (uint32_t)(conversion >> ACQ_RING_BITS) + 1u;
}

ACQ_RAMFUNC acq_step_result acq_step_plan(acq_engine *e, uint64_t now) {
    acq_stepper *s = &e->step;
    /* Every conversion that has started since the last step ran with driven_addr. */
    while (s->next_start <= now) {
        uint8_t need = slot_for(&e->sched, s->next_sif, s->next_ctl).mux_addr;
        if (need != s->driven_addr || s->driven_at + ACQ_SETTLE_CYCLES > s->next_start) {
            e->missed_tag[(uint32_t)s->next & ACQ_RING_MASK] = missed_tag_of(s->next);
            e->cnt.missed_slots++;
        }
        s->next++;
        s->next_start += ACQ_SLOT_CYCLES;
        if (++s->next_sif == ACQ_SLOTS_PER_FRAME) {
            s->next_sif = 0;
            s->next_ctl = (uint8_t)(s->next_ctl + 1u == ACQ_CHANNELS ? 0u : s->next_ctl + 1u);
        }
    }
    e->evaluated = (uint32_t)s->next;
    s->pending_addr = slot_for(&e->sched, s->next_sif, s->next_ctl).mux_addr;
    acq_step_result r;
    r.addr = s->pending_addr != s->driven_addr ? (int8_t)s->pending_addr : (int8_t)-1;
    r.frame_pulse = s->next_sif == 0;
    return r;
}

ACQ_RAMFUNC void acq_step_commit(acq_engine *e, uint64_t now_after_write) {
    acq_stepper *s = &e->step;
    if (s->pending_addr == s->driven_addr) return;
    s->driven_addr = s->pending_addr;
    s->driven_at = now_after_write + ACQ_TIME_UNCERTAINTY_CYCLES;
}

static void consume_one(acq_engine *e, bool lost) {
    uint64_t i = e->read;
    uint16_t raw = e->ring[(uint32_t)i & ACQ_RING_MASK];
    bool missed = !lost && e->missed_tag[(uint32_t)i & ACQ_RING_MASK] == missed_tag_of(i);
    bool err = !lost && !missed && (raw & ACQ_CODE_ERR_BIT);
    if (err) e->cnt.conversion_errors++;
    bool bad = lost || missed || err;
    uint16_t code = (uint16_t)(raw & ACQ_CODE_MASK);
    acq_slot sl = slot_for(&e->sched, e->read_sif, e->read_ctl);
    unsigned ch = sl.channel;
    if (sl.kind == ACQ_KIND_SIGNAL) {
        if (!bad) {
            scope_history_push(&e->hist[ch], code);
            e->last_code[ch] = code;
            e->have_last[ch] = true;
            e->pushed[ch]++;
        } else if (e->have_last[ch]) {
            /* Keep the time axis uniform; the substitution is counted, never silent. */
            scope_history_push(&e->hist[ch], e->last_code[ch]);
            e->pushed[ch]++;
            e->cnt.held_samples++;
        }
    } else if (!bad && sl.kind == ACQ_KIND_TIME) {
        e->time_code[ch] = code;
    } else if (!bad) {
        e->range_code[ch] = code;
        scope_range_update(&e->range[ch], code, e->now_ms);
    }
    e->read++;
    if (++e->read_sif == ACQ_SLOTS_PER_FRAME) {
        e->read_sif = 0;
        e->cnt.frames++;
        e->read_ctl = (uint8_t)(e->read_ctl + 1u == ACQ_CHANNELS ? 0u : e->read_ctl + 1u);
        if (++e->read_frame_in_ms == 1000u / (ACQ_FRAME_CYCLES / ACQ_CYCLES_PER_US)) {
            e->read_frame_in_ms = 0;
            e->now_ms++;
        }
    }
}

size_t acq_drain(acq_engine *e, uint64_t written, size_t max_samples) {
    if (!e || written <= e->read) return 0;
    uint64_t backlog = written - e->read;
    if (backlog > ACQ_RING_LEN - ACQ_RING_GUARD) {
        uint64_t lost = backlog - (ACQ_RING_LEN - ACQ_RING_GUARD);
        e->cnt.overrun_events++;
        e->cnt.overrun_samples += (uint32_t)lost;
        for (uint64_t k = 0; k < lost; k++) consume_one(e, true);
    }
    int32_t judged = (int32_t)(e->evaluated - (uint32_t)e->read);
    if (judged <= 0) return 0;
    if (written - e->read > (uint64_t)judged) written = e->read + (uint64_t)judged;
    size_t n = 0;
    while (n < max_samples && e->read < written) {
        consume_one(e, false);
        n++;
    }
    return n;
}
