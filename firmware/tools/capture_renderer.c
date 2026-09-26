/* Host-only capture of the real scope_render/scope_core renderer (#44 / #26 part 3).
 *
 * Links the unmodified scope_core.c and scope_render.c against a recording
 * display_port.h backend that paints into a 320x480 RGB565 array -- there is no such
 * array anywhere in firmware/src or the target build (AGENTS.md: "No 307,200-byte full
 * framebuffer is added"; this one lives only in this host tool, same as test_lcd.c's
 * `gram`). It feeds ten deterministic, distinct per-channel waveforms (sine, square,
 * ramp) at varied TIME codes and RANGE settings, one channel with an invalid
 * calibration (UNCAL), one whose converted volts exceed its selected range without
 * hitting the ADC rails (VIEW CLIP), and one whose raw codes are driven to the 0/4095
 * rails (ADC SAT); a second pass then sets HOLD and LINK. It writes the final
 * framebuffer as a raw RGB565 dump (little-endian per pixel, row-major) to the path
 * given on argv[1]. scripts/capture_renderer.py compiles and runs this, then encodes
 * that dump into reports/renderer-capture.png with a small stdlib-only PNG writer.
 *
 * This is a host tool only: it is not part of firmware/CMakeLists.txt, proves nothing
 * about the physical display (G06 stays OPEN), and is not built for the target.
 */
#include "display_port.h"
#include "scope_render.h"
#include <math.h>
#include <stdio.h>

/* Local pi constant: -std=c11 -pedantic does not reliably expose M_PI (a glibc
 * extension gated by feature-test macros), so this file defines its own. */
#define CAPTURE_PI 3.14159265358979323846f

static uint16_t FB[SCOPE_DISPLAY_HEIGHT][SCOPE_DISPLAY_WIDTH];

bool scope_display_init(void) { return true; }
void scope_display_backlight(uint8_t percent) { (void)percent; }
bool scope_display_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *rgb565) {
    if (!rgb565) return false;
    if ((uint32_t)x + w > SCOPE_DISPLAY_WIDTH || (uint32_t)y + h > SCOPE_DISPLAY_HEIGHT) return false;
    for (uint16_t r = 0; r < h; r++)
        for (uint16_t c = 0; c < w; c++) FB[y + r][x + c] = rgb565[(unsigned)r * w + c];
    return true;
}

static scope_history H[SCOPE_CHANNELS];

static uint16_t clamp12(float v) {
    if (v < 0.0f) return 0;
    if (v > 4095.0f) return 4095;
    return (uint16_t)(v + 0.5f);
}

/* One channel's deterministic raw-code sequence. `n` samples are pushed so every
 * channel's own TIME window (below) is fully covered, not a partial/right-aligned one.
 * `period` (samples per waveform cycle) is scaled to that channel's own window, so the
 * plot shows a handful of recognizable cycles instead of aliasing many cycles' min/max
 * into a single solid-filled column. Sine channels are drawn at +-3V (RANGE 0), square
 * at +-5V (RANGE 1), ramp at +-8V (RANGE 2) -- see the range[] assignment in main(),
 * which uses the same ch%3. */
static void fill_history(unsigned ch, uint32_t n, uint32_t period) {
    scope_history_init(&H[ch]);
    if (period < 4u) period = 4u;
    for (uint32_t i = 0; i < n; i++) {
        uint16_t code;
        switch (ch) {
        case 0: /* sine, normal, invalid calibration below: UNCAL */
            code = clamp12(SCOPE_NOMINAL_ZERO_CODE + 250.0f * sinf(2.0f * CAPTURE_PI * (float)i / (float)period));
            break;
        case 1: /* square, normal, +-5V */
            code = ((i / (period / 2u)) % 2u) ? 2258u : 1458u; /* +-3.23 V about the nominal zero */
            break;
        case 2: /* ramp, normal, +-8V */
            code = (uint16_t)(1158u + (i % period) * 700u / period); /* 1158..1858: -5.65..0 V */
            break;
        case 3: /* sine, amplitude ~4.0 V at +-3V RANGE: VIEW CLIP (raw stays off the rails) */
            code = clamp12(SCOPE_NOMINAL_ZERO_CODE + 496.0f * sinf(2.0f * CAPTURE_PI * (float)i / (float)period));
            break;
        case 4: /* square, normal, +-5V */
            code = ((i / (period / 2u)) % 2u) ? 2208u : 1508u; /* +-2.82 V */
            break;
        case 5: /* ramp, normal, +-8V */
            code = (uint16_t)(1358u + (i % period) * 1000u / period); /* 1358..2358: -4.03..+4.03 V */
            break;
        case 6: /* sine, amplitude occasionally past the ADC rails: ADC SAT */
            code = clamp12(SCOPE_NOMINAL_ZERO_CODE + 2500.0f * sinf(2.0f * CAPTURE_PI * (float)i / (float)period));
            break;
        case 7: /* square, normal, +-5V */
            code = ((i / (period / 2u)) % 2u) ? 2158u : 1558u; /* +-2.42 V */
            break;
        case 8: /* ramp, normal, +-8V */
            code = (uint16_t)(958u + (i % period) * 900u / period); /* 958..1858: -7.26..0 V */
            break;
        default: /* case 9: sine, normal, +-3V */
            code = clamp12(SCOPE_NOMINAL_ZERO_CODE + 300.0f * sinf(2.0f * CAPTURE_PI * (float)i / (float)period));
            break;
        }
        scope_history_push(&H[ch], code);
    }
}

static void run_pass(scope_render_state *s, const scope_render_input *in) {
    unsigned start = s->passes, guard = 0;
    while (s->passes == start && guard++ < 2000000u) scope_render_step(s, in, 8);
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s <out.raw>\n", argv[0]); return 2; }

    /* Ten distinct TIME codes, 28 ms .. 3.0 s, so the printed windows differ pane to
     * pane; none is pushed to the 2 ms / 8.19 s extremes, which (combined with a
     * period tied to the window, below) would leave too few or too many samples per
     * cycle for a legible plot at this pane size. Channel 1 (index 0) drives the LINK'd
     * window shown by every pane once the second pass below sets LINK. */
    static const uint16_t time_codes[SCOPE_CHANNELS] = {1600, 1300, 1900, 1450, 2200, 2600, 1750, 3000, 2050, 3600};

    uint32_t max_window = scope_window_samples(4095u, 10000u);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        uint32_t window = scope_window_samples(time_codes[ch], 10000u);
        /* A period of window/6 shows the same ~6 cycles regardless of the window's
         * absolute size, so every pane looks equally legible. */
        fill_history(ch, max_window + 200u, window / 6u);
    }

    scope_render_input in = {0};
    in.hist = H;
    in.samples_per_s = 10000u;
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        in.time_code[ch] = time_codes[ch];
        in.range[ch] = (int8_t)(ch % 3u); /* sine->0 (+-3V), square->1 (+-5V), ramp->2 (+-8V) */
        in.cal[ch] = ch == 0
            ? (scope_calibration){0}       /* invalid: nominal fallback shown as UNCAL */
            : (scope_calibration){SCOPE_NOMINAL_VOLTS_PER_CODE, SCOPE_NOMINAL_ZERO_CODE, true};
    }

    scope_render_state s;
    scope_render_init(&s);
    run_pass(&s, &in); /* first full pass: every plot and label drawn */

    in.hold = true;
    in.link = true;
    run_pass(&s, &in); /* second pass: HOLD freezes the plots, HOLD/LINK labels drawn */

    FILE *f = fopen(argv[1], "wb");
    if (!f) { fprintf(stderr, "cannot open %s\n", argv[1]); return 1; }
    for (unsigned y = 0; y < SCOPE_DISPLAY_HEIGHT; y++)
        for (unsigned x = 0; x < SCOPE_DISPLAY_WIDTH; x++) {
            uint16_t v = FB[y][x];
            uint8_t bytes[2] = {(uint8_t)(v & 0xFFu), (uint8_t)((v >> 8) & 0xFFu)};
            if (fwrite(bytes, 1, 2, f) != 2) { fclose(f); return 1; }
        }
    fclose(f);
    return 0;
}
