/* scope10_acq: RP2040 register side of the 10 kS/s/channel acquisition engine.
 * Scheduling, missed-slot judgement and the ring consumer are portable (acq_engine.[ch]);
 * the design and its budget are in firmware/ACQUISITION.md. All figures are NOMINAL
 * design values: no sample rate, jitter or settle time has been measured (G05 OPEN).
 * Channels are sampled sequentially through the mux, never simultaneously.
 * The LCD is held dark and unselected (lcd_safe_pins.c, from before main) unless the
 * target is configured with SCOPE_ENABLE_LCD=1; then core0 also runs the ten-pane
 * renderer between drain batches (firmware/LCD-BACKEND.md, G06 OPEN).
 *
 * Hardware use:
 *   PWM slice 0  slot timer, wrap every 1000 cycles; its DREQ paces DMA "start", which
 *                writes the next ADC CS word (EN | START_ONCE | AINSEL) from cs_table.
 *   DMA "reload" re-arms "start" at the end of every 12-word frame table.
 *   PWM slice 1  same period, 300 cycles later; its wrap IRQ runs on core1 only and
 *                steps the mux address (GP2..GP5) and the GP14 frame pulse.
 *   DMA "col A/B" ping-pong the ADC FIFO (DREQ_ADC) into the engine ring; core0 drains
 *                it into scope_core histories and prints counters over USB serial. */
#include "acq_engine.h"
#include "lcd_safe_pins.h"
#include "hardware/adc.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/irq.h"
#include "hardware/pwm.h"
#include "hardware/structs/timer.h"
#include "hardware/sync.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"
#include <stdio.h>
#if SCOPE_ENABLE_LCD
#include "display_port.h"
#include "scope_render.h"
#define RENDER_ITEMS_PER_PASS 4u
#define LCD_STATE "LCD ENABLED (SCOPE_ENABLE_LCD=1, unverified: G01/G06 OPEN)"
#else
#define LCD_STATE "LCD OFF"
#endif

#define PIN_HOLD_N 0u
#define PIN_LINK_N 1u
#define PIN_ADDR0 2u
#define ADDR_MASK (0x0fu << PIN_ADDR0)
#define PIN_MUX_DISABLE 7u
#define PIN_TIMING_TP 14u
#define SLOT_SLICE 0u
#define STEP_SLICE 1u
#define HALF (ACQ_RING_LEN / 2u)
#define DRAIN_BATCH 1024u
#define REPORT_INTERVAL_US 1000000u

static void core1_step_irq_set(bool on);
#define ACQ_EPOCH_IRQ_SAVE() save_and_disable_interrupts()
#define ACQ_EPOCH_IRQ_RESTORE(s) restore_interrupts(s)
#define ACQ_EPOCH_TICK() (timer_hw->timerawl)
#define ACQ_EPOCH_DMB() __dmb()
#define ACQ_EPOCH_PWM_ENABLE() pwm_set_mask_enabled((1u << SLOT_SLICE) | (1u << STEP_SLICE))
#define ACQ_EPOCH_PWM_DISABLE() pwm_set_mask_enabled(0u)
#define ACQ_EPOCH_SEV() __sev()
#define ACQ_EPOCH_WAIT() tight_loop_contents()
#define ACQ_EPOCH_STEP_IRQ_SET(on) core1_step_irq_set(on)
#include "acq_epoch.h"

static acq_engine eng;
static scope_history hist[ACQ_CHANNELS];
static uint32_t cs_table[ACQ_SLOTS_PER_FRAME];
static const uint32_t *cs_table_addr = cs_table;
static uint ch_start, ch_reload, ch_col[2];
static volatile uint32_t col_halves;
/* Time base and arm/quiesce handshake for the core1 stepper (acq_epoch.h). */
static acq_epoch epoch;

static void out(unsigned pin, bool high) {
    gpio_init(pin);
    gpio_set_dir(pin, GPIO_OUT);
    gpio_put(pin, high);
}

static void __not_in_flash_func(on_mux_step)(void) {
    pwm_clear_irq(STEP_SLICE);
    if (!acq_epoch_enter(&epoch)) return; /* disarmed: leave engine and pins alone */
    acq_step_result r = acq_step_plan(&eng, acq_epoch_lower_bound(&epoch, timer_hw->timerawl));
    if (r.addr >= 0) gpio_put_masked(ADDR_MASK, (uint32_t)r.addr << PIN_ADDR0);
    gpio_put(PIN_TIMING_TP, r.frame_pulse);
    acq_step_commit(&eng, acq_epoch_lower_bound(&epoch, timer_hw->timerawl));
}

/* Runs on core1 in thread mode only (acq_epoch_core1_service), never inside the handler. */
static void core1_step_irq_set(bool on) {
    if (on) {
        irq_clear(PWM_IRQ_WRAP);
        irq_set_enabled(PWM_IRQ_WRAP, true);
    } else {
        irq_set_enabled(PWM_IRQ_WRAP, false);
        irq_clear(PWM_IRQ_WRAP);
    }
}

static void __not_in_flash_func(core1_main)(void) {
    irq_set_exclusive_handler(PWM_IRQ_WRAP, on_mux_step);
    irq_set_priority(PWM_IRQ_WRAP, PICO_HIGHEST_IRQ_PRIORITY);
    /* The step IRQ stays off until core0 requests it (acq_epoch_core1_request). */
    multicore_fifo_push_blocking(1u);
    for (;;) {
        acq_epoch_core1_service(&epoch);
        __wfe(); /* woken by core0's SEV and by every step IRQ */
    }
}

static void on_collector_done(void) {
    for (unsigned i = 0; i < 2u; i++) {
        if (!dma_channel_get_irq0_status(ch_col[i])) continue;
        dma_channel_acknowledge_irq0(ch_col[i]);
        dma_channel_set_write_addr(ch_col[i], &eng.ring[i * HALF], false);
        dma_channel_set_trans_count(ch_col[i], HALF, false);
        col_halves++;
    }
}

static uint64_t written_total(void) {
    uint32_t h1, h2, remaining;
    do {
        h1 = col_halves;
        remaining = dma_hw->ch[ch_col[h1 & 1u]].transfer_count;
        h2 = col_halves;
    } while (h1 != h2);
    return (uint64_t)h1 * HALF + (HALF - remaining);
}

/* RAM-resident so the interrupts-off tick-to-enable path never waits on XIP. */
static void __not_in_flash_func(start_timers)(void) {
    acq_epoch_start(&epoch);
}

static void acq_hw_stop(void) {
    acq_epoch_stop(&epoch); /* returns only once core1's step IRQ is confirmed off */
    pwm_clear_irq(STEP_SLICE);
    gpio_put(PIN_MUX_DISABLE, true);
    dma_channel_set_irq0_enabled(ch_col[0], false);
    dma_channel_set_irq0_enabled(ch_col[1], false);
    const uint all[4] = {ch_reload, ch_start, ch_col[0], ch_col[1]};
    for (unsigned i = 0; i < 4u; i++) dma_channel_abort(all[i]);
    dma_hw->ints0 = (1u << ch_col[0]) | (1u << ch_col[1]);
}

static void acq_hw_start(void) {
    adc_fifo_drain();
    adc_hw->fcs = adc_hw->fcs | ADC_FCS_OVER_BITS | ADC_FCS_UNDER_BITS; /* write-1-to-clear */

    col_halves = 0;
    for (unsigned i = 0; i < 2u; i++) {
        dma_channel_config c = dma_channel_get_default_config(ch_col[i]);
        channel_config_set_transfer_data_size(&c, DMA_SIZE_16);
        channel_config_set_read_increment(&c, false);
        channel_config_set_write_increment(&c, true);
        channel_config_set_dreq(&c, DREQ_ADC);
        channel_config_set_chain_to(&c, ch_col[i ^ 1u]);
        dma_channel_configure(ch_col[i], &c, &eng.ring[i * HALF], &adc_hw->fifo, HALF, i == 0u);
        dma_channel_acknowledge_irq0(ch_col[i]);
        dma_channel_set_irq0_enabled(ch_col[i], true);
    }

    dma_channel_config rc = dma_channel_get_default_config(ch_reload);
    channel_config_set_transfer_data_size(&rc, DMA_SIZE_32);
    channel_config_set_read_increment(&rc, false);
    channel_config_set_write_increment(&rc, false);
    dma_channel_configure(ch_reload, &rc, &dma_hw->ch[ch_start].al3_read_addr_trig,
                          &cs_table_addr, 1u, false);

    dma_channel_config sc = dma_channel_get_default_config(ch_start);
    channel_config_set_transfer_data_size(&sc, DMA_SIZE_32);
    channel_config_set_read_increment(&sc, true);
    channel_config_set_write_increment(&sc, false);
    channel_config_set_dreq(&sc, pwm_get_dreq(SLOT_SLICE));
    channel_config_set_chain_to(&sc, ch_reload);
    dma_channel_configure(ch_start, &sc, &adc_hw->cs, cs_table, ACQ_SLOTS_PER_FRAME, true);

    pwm_set_counter(SLOT_SLICE, 0u);
    pwm_set_counter(STEP_SLICE, ACQ_SLOT_CYCLES - ACQ_STEP_OFFSET_CYCLES);
    pwm_clear_irq(STEP_SLICE);
    pwm_set_irq_enabled(STEP_SLICE, true);

    /* Slot 0's address is driven and settled before the origin (see stepper_reset). */
    gpio_put_masked(ADDR_MASK, (uint32_t)eng.step.driven_addr << PIN_ADDR0);
    gpio_put(PIN_MUX_DISABLE, false);
    busy_wait_us(10);
    acq_epoch_core1_request(&epoch, true); /* after pwm_clear_irq, so nothing stale pends */
    start_timers();
}

static void acq_hw_init(void) {
    adc_init();
    for (unsigned p = 26; p <= 28; p++) adc_gpio_init(p);
    adc_fifo_setup(true, true, 1, true, false); /* FIFO + DREQ, ERR flag in bit 15 */
    for (unsigned sif = 0; sif < ACQ_SLOTS_PER_FRAME; sif++) {
        acq_slot sl = acq_slot_for(&eng.sched, sif, 0);
        cs_table[sif] = ADC_CS_EN_BITS | ADC_CS_START_ONCE_BITS
                      | ((uint32_t)sl.adc_input << ADC_CS_AINSEL_LSB);
    }
    pwm_config pc = pwm_get_default_config();
    pwm_config_set_clkdiv_int(&pc, 1);
    pwm_config_set_wrap(&pc, ACQ_SLOT_CYCLES - 1u);
    pwm_init(SLOT_SLICE, &pc, false);
    pwm_init(STEP_SLICE, &pc, false);
    ch_start = (uint)dma_claim_unused_channel(true);
    ch_reload = (uint)dma_claim_unused_channel(true);
    ch_col[0] = (uint)dma_claim_unused_channel(true);
    ch_col[1] = (uint)dma_claim_unused_channel(true);
    irq_set_exclusive_handler(DMA_IRQ_0, on_collector_done);
    irq_set_enabled(DMA_IRQ_0, true);
}

/* hold_pressed/link_pressed are the raw (active-low) button pins, not the renderer's
 * latched HOLD/LINK modes that the display shows. */
static void report_line(unsigned line) {
    const acq_counters *c = &eng.cnt;
    if (line == 0u) {
        printf("acq,uptime_ms=%lu,frames=%lu,missed_slots=%lu,overrun_events=%lu,overrun_samples=%lu,"
               "fifo_errors=%lu,conversion_errors=%lu,held_samples=%lu,resyncs=%lu,hold_pressed=%u,link_pressed=%u\n",
               (unsigned long)to_ms_since_boot(get_absolute_time()), (unsigned long)c->frames,
               (unsigned long)c->missed_slots, (unsigned long)c->overrun_events,
               (unsigned long)c->overrun_samples, (unsigned long)c->fifo_errors,
               (unsigned long)c->conversion_errors, (unsigned long)c->held_samples,
               (unsigned long)c->resyncs, (unsigned)!gpio_get(PIN_HOLD_N), (unsigned)!gpio_get(PIN_LINK_N));
        return;
    }
    unsigned ch = line - 1u;
    printf("ch,%u,last_code=%u,time_code=%u,range_code=%u,range=%d,pushed=%lu\n", ch + 1u,
           eng.last_code[ch], eng.time_code[ch], eng.range_code[ch], eng.range[ch].stable,
           (unsigned long)eng.pushed[ch]);
}

int main(void) {
    out(PIN_MUX_DISABLE, true); /* all mux banks disconnected until acquisition starts */
    for (unsigned p = PIN_ADDR0; p < PIN_ADDR0 + 4u; p++) out(p, false);
    lcd_safe_pins_apply(); /* already applied by the runtime-init hook; kept explicit */
    out(PIN_TIMING_TP, false);
    for (unsigned p = PIN_HOLD_N; p <= PIN_LINK_N; p++) { gpio_init(p); gpio_set_dir(p, GPIO_IN); gpio_pull_up(p); }

    bool clock_ok = set_sys_clock_khz(ACQ_SYS_CLK_HZ / 1000u, false);
    stdio_init_all();
    sleep_ms(1500);
    puts("scope10_acq P0 / " LCD_STATE " / UNCALIBRATED / no fault-voltage testing authorized");
    puts("Nominal design: 10000 S/s per channel, 10 channels sampled SEQUENTIALLY (not simultaneous); "
         "rate, settle and jitter NOT measured (G05 OPEN)");
    if (!clock_ok || clock_get_hz(clk_sys) != ACQ_SYS_CLK_HZ) {
        printf("ERROR: clk_sys %lu Hz, engine requires %lu Hz; acquisition not started\n",
               (unsigned long)clock_get_hz(clk_sys), (unsigned long)ACQ_SYS_CLK_HZ);
        for (;;) sleep_ms(1000);
    }

    acq_schedule sched;
    acq_schedule_default(&sched);
    acq_engine_init(&eng, &sched, hist);
    acq_hw_init();
#if SCOPE_ENABLE_LCD
    /* Before acquisition starts: panel reset, init and the full-screen clear block core0 for about 0.4 s. */
    static scope_render_state rs;
    static scope_button hold_btn, link_btn;
    scope_render_init(&rs);
    bool lcd_ok = scope_display_init();
    if (lcd_ok) scope_display_backlight(100);
    printf("lcd,init_sequence_sent=%u (no panel readback exists; not a display verification)\n",
           (unsigned)lcd_ok);
#endif
    multicore_launch_core1(core1_main);
    (void)multicore_fifo_pop_blocking();
    acq_hw_start();

    uint64_t next_report = time_us_64() + REPORT_INTERVAL_US;
    unsigned report = ACQ_CHANNELS + 1u; /* idle */
    for (;;) {
        if (adc_hw->fcs & (ADC_FCS_OVER_BITS | ADC_FCS_UNDER_BITS)) {
            /* A dropped or phantom FIFO word breaks slot alignment: count, restart, resync. */
            eng.cnt.fifo_errors++;
            acq_hw_stop();
            acq_engine_resync(&eng);
            acq_hw_start();
            continue;
        }
        acq_drain(&eng, written_total(), DRAIN_BATCH);
        if (report <= ACQ_CHANNELS) {
            report_line(report++); /* one short line per pass keeps drain latency low */
        } else if (time_us_64() >= next_report) {
            next_report += REPORT_INTERVAL_US;
            report = 0;
        }
#if SCOPE_ENABLE_LCD
        if (lcd_ok) {
            uint32_t now_ms = to_ms_since_boot(get_absolute_time());
            scope_render_input in = {
                .hist = hist,
                .samples_per_s = ACQ_SAMPLES_PER_CH_S,
                .hold = scope_button_update(&hold_btn, !gpio_get(PIN_HOLD_N), now_ms),
                .link = scope_button_update(&link_btn, !gpio_get(PIN_LINK_N), now_ms),
            };
            for (unsigned ch = 0; ch < ACQ_CHANNELS; ch++) {
                in.time_code[ch] = eng.time_code[ch];
                in.range[ch] = (int8_t)eng.range[ch].stable;
            }
            scope_render_step(&rs, &in, RENDER_ITEMS_PER_PASS);
        }
#endif
    }
}
