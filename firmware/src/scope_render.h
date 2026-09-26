#ifndef SCOPE_RENDER_H
#define SCOPE_RENDER_H
/* Ten-pane portrait renderer. Draws scope_core min/max history through display_port.h,
 * one small rectangle per call (one plot column, or a fill of at most
 * SCOPE_RENDER_FILL_MAX pixels): there is no framebuffer. Work is split into steps so the
 * acquisition drain loop keeps running between them.
 * Layout: 320 x 480 portrait, 2 columns x 5 rows of 160 x 96 panes, column-major so the
 * screen matches the physical control banks: pane i (CH i+1) sits in column i / 5, row
 * i % 5. CH1..CH5 fill the left column top to bottom, CH6..CH10 the right; CH6 is top right.
 * Inside a pane (offsets from the pane origin):
 *   y  1..10   label row, x 8..151: channel ID, range, window duration (reserved, not drawn yet)
 *   y 14..79   x 0..3 channel colour tag | x 8..151 plot, 144 x 66 (SCOPE_PLOT_W x SCOPE_PLOT_H)
 *   y 83..92   status row, x 8..151: interim RANGE boxes (+/-3, +/-5, +/-8 V, left to right),
 *              TIME bar, LINK and HOLD boxes; the HOLD/LINK/status text goes here later
 *   y 95       separator line across the pane
 * SCOPE_PLOT_W is independent of SCOPE_HISTORY_BINS. Interim mapping: the plot shows the
 * most recent SCOPE_PLOT_W bins of the chosen level, right-aligned, newest at the right.
 * LINK makes every pane use CH1's TIME window: a time-link of views, not phase sync. The
 * channels are still sampled sequentially. HOLD freezes the plots; status keeps updating. */
#include "scope_core.h"
#include <stdbool.h>
#include <stdint.h>

#define SCOPE_PANE_COLS 2u
#define SCOPE_PANE_ROWS 5u
#define SCOPE_PANE_W 160u
#define SCOPE_PANE_H 96u
#define SCOPE_TAG_X 0u
#define SCOPE_TAG_W 4u
#define SCOPE_PLOT_X 8u
#define SCOPE_PLOT_Y 14u
#define SCOPE_PLOT_W 144u
#define SCOPE_PLOT_H 66u
#define SCOPE_LABEL_Y 1u
#define SCOPE_LABEL_H 10u
#define SCOPE_STATUS_Y 83u
#define SCOPE_STATUS_H 10u
/* Interim status-row indicators, x offsets from the status rect origin. */
#define SCOPE_STATUS_BOX_Y 2u
#define SCOPE_STATUS_BOX_H 6u
#define SCOPE_STATUS_RANGE_W 12u
#define SCOPE_STATUS_RANGE_PITCH 14u
#define SCOPE_STATUS_BAR_X 44u
#define SCOPE_STATUS_BAR_W 64u
#define SCOPE_STATUS_LINK_X 116u
#define SCOPE_STATUS_HOLD_X 128u
#define SCOPE_STATUS_FLAG_W 8u
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
    uint16_t item;                          /* static, then PLOT_W columns, then status */
    bool static_done[SCOPE_CHANNELS];
    uint16_t nbins;                         /* <= SCOPE_PLOT_W most recent bins */
    scope_bin bins[SCOPE_PLOT_W];
    uint32_t rects_sent, rects_failed, passes;
} scope_render_state;

typedef struct { bool raw, stable, toggled; uint32_t since_ms; } scope_button;

scope_rect scope_pane_rect(unsigned pane);
scope_rect scope_pane_tag_rect(unsigned pane);
scope_rect scope_pane_plot_rect(unsigned pane);
/* Text row above the plot: channel ID, range and window duration. Reserved; not drawn yet. */
scope_rect scope_pane_label_rect(unsigned pane);
/* Row below the plot: interim indicators now, HOLD/LINK/status text later. */
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
