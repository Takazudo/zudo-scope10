#ifndef SCOPE_RENDER_H
#define SCOPE_RENDER_H
/* Ten-pane portrait renderer. Draws scope_core min/max history through display_port.h,
 * one small rectangle per call (one plot column, or a fill of at most
 * SCOPE_RENDER_FILL_MAX pixels): there is no framebuffer. Work is split into steps so the
 * acquisition drain loop keeps running between them. Layout (320 x 480, per pane of 48 rows):
 *   x 0..9 channel colour tag | x 14..205 plot, 192 columns = SCOPE_HISTORY_BINS | x 212..319
 *   status: three RANGE boxes (+/-3, +/-5, +/-8 V, left to right), a TIME bar, LINK and HOLD
 *   boxes. Row 47 of each pane is a separator line.
 * LINK makes every pane use CH1's TIME window: a time-link of views, not phase sync. The
 * channels are still sampled sequentially. HOLD freezes the plots; status keeps updating. */
#include "scope_core.h"
#include <stdbool.h>
#include <stdint.h>

#define SCOPE_PANE_H 48u
#define SCOPE_PANE_MARGIN_TOP 2u
#define SCOPE_TAG_X 0u
#define SCOPE_TAG_W 10u
#define SCOPE_PLOT_X 14u
#define SCOPE_PLOT_W SCOPE_HISTORY_BINS
#define SCOPE_PLOT_H 44u
#define SCOPE_STATUS_X 212u
#define SCOPE_STATUS_W 108u
#define SCOPE_RENDER_FILL_MAX 128u
#define SCOPE_BUTTON_DEBOUNCE_MS 20u

#define SCOPE_RGB565(r, g, b) ((uint16_t)((((r) & 0xF8u) << 8) | (((g) & 0xFCu) << 3) | ((b) >> 3)))
#define SCOPE_COLOUR_BG 0x0000u
#define SCOPE_COLOUR_GRID SCOPE_RGB565(40, 40, 40)
#define SCOPE_COLOUR_DIM SCOPE_RGB565(56, 56, 56)
#define SCOPE_COLOUR_SEPARATOR SCOPE_RGB565(96, 96, 96)
#define SCOPE_COLOUR_HOLD SCOPE_RGB565(255, 160, 0)
#define SCOPE_COLOUR_LINK SCOPE_RGB565(0, 200, 255)

typedef struct { uint16_t x, y, w, h; } scope_rect;

typedef struct {
    const scope_history *hist;              /* SCOPE_CHANNELS entries */
    uint16_t time_code[SCOPE_CHANNELS];     /* raw TIME knob codes */
    int8_t range[SCOPE_CHANNELS];           /* scope_range_update result: -1, 0, 1, 2 */
    uint32_t samples_per_s;                 /* per channel, nominal */
    bool hold, link;
} scope_render_input;

typedef struct {
    uint8_t pane;
    uint16_t item;                          /* 0..PLOT_W-1 columns, then status, then static */
    bool static_done[SCOPE_CHANNELS];
    uint16_t nbins;
    scope_bin bins[SCOPE_HISTORY_BINS];
    uint32_t rects_sent, rects_failed, passes;
} scope_render_state;

typedef struct { bool raw, stable, toggled; uint32_t since_ms; } scope_button;

scope_rect scope_pane_rect(unsigned pane);
scope_rect scope_pane_tag_rect(unsigned pane);
scope_rect scope_pane_plot_rect(unsigned pane);
scope_rect scope_pane_status_rect(unsigned pane);
scope_rect scope_pane_separator_rect(unsigned pane);
uint16_t scope_channel_colour(unsigned ch);
/* Row inside a plot of height h for a 12-bit code: 4095 -> 0 (top), 0 -> h - 1. */
uint16_t scope_code_to_row(uint16_t code, uint16_t h);
/* One plot column: background, mid-scale grid row, and the bin's lo..hi span. NULL = empty. */
void scope_render_column(const scope_bin *bin, uint16_t h, uint16_t colour, uint16_t *out);
unsigned scope_render_level(uint16_t time_code, uint32_t samples_per_s);
void scope_render_init(scope_render_state *s);
/* Issues display calls for up to max_items items; returns the number of display calls. */
unsigned scope_render_step(scope_render_state *s, const scope_render_input *in, unsigned max_items);
/* Debounced press-to-toggle for the active-low HOLD and LINK buttons. Returns the toggle. */
bool scope_button_update(scope_button *b, bool pressed, uint32_t now_ms);
#endif
