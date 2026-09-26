#ifndef ACQ_EPOCH_H
#define ACQ_EPOCH_H
/* Acquisition epoch: the shared time origin of the core1 mux stepper, its atomic startup
 * with the PWM slices, and the explicit core1 quiescence handshake used before a resync.
 * Portable (no RP2040 headers): acq_rp2040.c maps the hooks below onto the SDK and the
 * host model (tests/test_acq.c) maps them onto a simulated clock with injectable core0
 * preemption, so both run this exact code. firmware/ACQUISITION.md ("Startup and resync")
 * explains the ordering and the tick-to-enable bound.
 *
 * The includer defines, before including this header:
 *   ACQ_EPOCH_IRQ_SAVE()      disable core0 interrupts, return the previous state
 *   ACQ_EPOCH_IRQ_RESTORE(s)  restore that state
 *   ACQ_EPOCH_TICK()          read the free-running 1 us TIMER (low 32 bits)
 *   ACQ_EPOCH_DMB()           data memory barrier, also a compiler barrier
 *   ACQ_EPOCH_PWM_ENABLE()    start both PWM slices with one register write
 *   ACQ_EPOCH_PWM_DISABLE()   stop both PWM slices
 *   ACQ_EPOCH_SEV()           signal an event to the other core
 *   ACQ_EPOCH_WAIT()          one polling step while core0 waits for core1
 *   ACQ_EPOCH_STEP_IRQ_SET(b) core1 only: enable/disable its step IRQ and clear its pending bit */
#include "acq_engine.h"

#if !defined(ACQ_EPOCH_IRQ_SAVE) || !defined(ACQ_EPOCH_IRQ_RESTORE) || !defined(ACQ_EPOCH_TICK) \
    || !defined(ACQ_EPOCH_DMB) || !defined(ACQ_EPOCH_PWM_ENABLE) || !defined(ACQ_EPOCH_PWM_DISABLE) \
    || !defined(ACQ_EPOCH_SEV) || !defined(ACQ_EPOCH_WAIT) || !defined(ACQ_EPOCH_STEP_IRQ_SET)
#error "define every ACQ_EPOCH_* hook before including acq_epoch.h"
#endif

#define ACQ_EPOCH_ALWAYS_INLINE static inline __attribute__((always_inline))

typedef struct {
    /* Generation the step IRQ may run under; 0 = stopped. Written last on arm (after a
     * barrier), first on stop. The step IRQ reads it before any other epoch field. */
    volatile uint32_t armed;
    /* Time base, written by core0 only while no step IRQ can run (disarmed and core1
     * quiescent), then owned by the step IRQ, which extends it on every step. */
    volatile uint32_t last_raw;
    volatile uint64_t now_cycles;
    /* core0 -> core1 control request: (sequence << 1) | step-IRQ-enabled. */
    volatile uint32_t ctl_req;
    /* core1 -> core0: the last request core1 applied, from thread mode. */
    volatile uint32_t ctl_ack;
    uint32_t gen;     /* core0-owned: last generation issued */
    uint32_t ctl_seq; /* core0-owned */
} acq_epoch;

/* core0: ask core1 to enable or disable its step IRQ and wait until core1 has done so.
 * core1 applies the request from thread mode, where by construction no step handler is
 * executing on that core; after a disable is acknowledged no handler runs, and none can
 * start, until a later enable. This is the explicit quiescence point (no fixed delay). */
ACQ_EPOCH_ALWAYS_INLINE void acq_epoch_core1_request(acq_epoch *ep, bool step_irq_on) {
    ep->ctl_seq++;
    uint32_t req = (ep->ctl_seq << 1) | (step_irq_on ? 1u : 0u);
    ACQ_EPOCH_DMB();
    ep->ctl_req = req;
    ACQ_EPOCH_DMB();
    ACQ_EPOCH_SEV();
    while (ep->ctl_ack != req) ACQ_EPOCH_WAIT();
    ACQ_EPOCH_DMB();
}

/* core1 thread mode (idle loop): apply a pending control request, then acknowledge it. */
ACQ_EPOCH_ALWAYS_INLINE void acq_epoch_core1_service(acq_epoch *ep) {
    uint32_t req = ep->ctl_req;
    if (req == ep->ctl_ack) return;
    ACQ_EPOCH_DMB();
    ACQ_EPOCH_STEP_IRQ_SET((req & 1u) != 0u);
    ACQ_EPOCH_DMB();
    ep->ctl_ack = req;
    ACQ_EPOCH_SEV();
}

/* core0: stop the slices, disarm, then wait for core1 to confirm that its step IRQ is
 * off. Only after this returns may the stepper/consumer state be reset. */
ACQ_EPOCH_ALWAYS_INLINE void acq_epoch_stop(acq_epoch *ep) {
    ACQ_EPOCH_PWM_DISABLE();
    ep->armed = 0u;
    ACQ_EPOCH_DMB();
    acq_epoch_core1_request(ep, false);
}

/* core0: origin capture, complete epoch publication and PWM enable as one operation that
 * core0 interrupts cannot split. The caller has already reset the engine, cleared the
 * PWM IRQ flag, pre-driven slot 0's address and had core1 enable its step IRQ
 * (acq_epoch_core1_request(ep, true)); the slices are stopped, so no step IRQ can occur
 * until the enable below.
 *
 * Ordering, chosen to be correct even if a step handler were already executing:
 *   1. interrupts off (nothing on core0 can run between steps 2 and 5);
 *   2. write every tick-independent field (now_cycles, the new generation);
 *   3. spin to a TIMER tick edge and record it (last_raw) -- the software origin;
 *   4. DMB, then armed = generation: any handler that sees `armed` sees every field;
 *      a handler that ran earlier saw armed == 0 and touched nothing;
 *   5. enable both PWM slices -- the physical origin -- then restore interrupts.
 * The step IRQ can first fire ACQ_STEP_OFFSET_CYCLES after step 5, long after step 4.
 * Tick-to-enable = one spin iteration + last_raw store + DMB + armed store + PWM write;
 * it must stay within ACQ_ORIGIN_SLACK_CYCLES (ACQ_TICK_TO_ENABLE_BOUND_CYCLES is the
 * bound derived in firmware/ACQUISITION.md). */
ACQ_EPOCH_ALWAYS_INLINE void acq_epoch_start(acq_epoch *ep) {
    uint32_t irq = ACQ_EPOCH_IRQ_SAVE();
    uint32_t gen = ep->gen + 1u;
    if (gen == 0u) gen = 1u;
    ep->gen = gen;
    ep->now_cycles = 0u;
    uint32_t r0 = ACQ_EPOCH_TICK(), r;
    while ((r = ACQ_EPOCH_TICK()) == r0) {
    }
    ep->last_raw = r;
    ACQ_EPOCH_DMB();
    ep->armed = gen;
    ACQ_EPOCH_PWM_ENABLE();
    ACQ_EPOCH_IRQ_RESTORE(irq);
}

/* Step IRQ entry: false = disarmed, the handler must not touch the engine or the epoch.
 * The barrier orders the `armed` read before every later epoch/engine read. */
ACQ_EPOCH_ALWAYS_INLINE bool acq_epoch_enter(const acq_epoch *ep) {
    uint32_t armed = ep->armed;
    ACQ_EPOCH_DMB();
    return armed != 0u;
}

/* Step IRQ: lower bound on cycles since the physical origin, from a fresh TIMER read. */
ACQ_EPOCH_ALWAYS_INLINE uint64_t acq_epoch_lower_bound(acq_epoch *ep, uint32_t raw) {
    uint64_t t = ep->now_cycles + (uint64_t)((raw - ep->last_raw) * ACQ_CYCLES_PER_US);
    ep->now_cycles = t;
    ep->last_raw = raw;
    return t > ACQ_ORIGIN_SLACK_CYCLES ? t - ACQ_ORIGIN_SLACK_CYCLES : 0u;
}
#endif
