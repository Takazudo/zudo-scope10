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
 *   y  1..10   label row, x 8..151: channel ID (channel colour), range, UNCAL, window duration
 *   y 14..79   x 0..3 channel colour tag | x 8..151 plot, 144 x 66 (SCOPE_PLOT_W x SCOPE_PLOT_H)
 *   y 83..92   status row, x 8..151: signal token (VIEW CLIP / ADC SAT), LINK, HOLD
 *   y 95       separator line across the pane
 * Text rows are a grid of 24 cells of SCOPE_CELL_W x SCOPE_CELL_H; each glyph is 5 x 7 from
 * the in-repo font. A text field is redrawn only when its string or colour changes.
 * SCOPE_PLOT_W is independent of SCOPE_HISTORY_BINS. Each plot spans the requested TIME
 * window through scope_window_map() (scope_core.h: level choice, column mapping, tolerance,
 * partial history right-aligned with blank columns on the left), newest at the right.
 * The duration label and the plot both derive from scope_window_samples() of the same
 * effective TIME code, so the label names the interval the plot represents.
 * Vertical: each bin's raw lo/hi is converted to volts through the channel's calibration
 * (scope_calibration_effective: the nominal fallback when missing or invalid, shown as
 * UNCAL), then [-range, +range] (the RANGE switch's +-3/5/8 V software view scale) maps to
 * rows 0 .. 2 x ((SCOPE_PLOT_H - 1) / 2); the grid row is electrical zero (0 V) through the
 * same mapping. Beyond +-range the trace is pinned at the edge row in SCOPE_COLOUR_CLIP with
 * a background gap beside it. The RANGE label names the scale the plot is drawn at: it is
 * latched with the plot (so it freezes under HOLD), a deadband keeps the last valid range,
 * and before the switch ever decodes the startup scale +-8 V shows in the warning colour.
 * Signal token, per pane over the drawn window: ADC SAT when a raw lo or hi is at 0 or 4095
 * (ADC/input limit), else VIEW CLIP when converted volts exceed +-range (only the view
 * clips), else nothing. UNCAL has its own slot, so neither hides the other.
 * LINK makes every pane use CH1's TIME window: a time-link of views, not phase sync. The
 * channels are still sampled sequentially. HOLD freezes the plots; text keeps updating. */
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
#define SCOPE_GLYPH_W 5u
#define SCOPE_GLYPH_H 7u
#define SCOPE_CELL_W 6u
#define SCOPE_CELL_H 10u
#define SCOPE_GLYPH_Y 1u                     /* glyph top inside its cell */
#define SCOPE_TEXT_CELLS (SCOPE_PLOT_W / SCOPE_CELL_W)
#define SCOPE_FIELD_MAX 9u                   /* widest text field, in cells ("VIEW CLIP") */
#define SCOPE_WINDOW_LABEL_MAX 6u            /* window-duration field, in cells */
#define SCOPE_RANGE_STARTUP 2                /* +-8 V until the RANGE switch first decodes */
#define SCOPE_CHAR_PM '\xb1'                /* plus-minus sign (Latin-1 code) */
#define SCOPE_RENDER_FILL_MAX 128u
#define SCOPE_BUTTON_DEBOUNCE_MS 20u

#define SCOPE_RGB565(r, g, b) ((uint16_t)((((r) & 0xF8u) << 8) | (((g) & 0xFCu) << 3) | ((b) >> 3)))
#define SCOPE_COLOUR_BG 0x0000u
#define SCOPE_COLOUR_GRID SCOPE_RGB565(40, 40, 40)
#define SCOPE_COLOUR_SEPARATOR SCOPE_RGB565(96, 96, 96)
#define SCOPE_COLOUR_HOLD SCOPE_RGB565(255, 160, 0)
#define SCOPE_COLOUR_LINK SCOPE_RGB565(0, 200, 255)
#define SCOPE_COLOUR_TEXT SCOPE_RGB565(200, 200, 200)
#define SCOPE_COLOUR_WARN SCOPE_RGB565(255, 64, 64)
#define SCOPE_COLOUR_CLIP SCOPE_COLOUR_WARN   /* edge pixel of a trace pinned by VIEW CLIP */

typedef struct { uint16_t x, y, w, h; } scope_rect;

/* Per-channel status tokens, computed by the renderer (not by the caller). */
typedef enum {
    SCOPE_STATUS_NONE = 0,
    SCOPE_STATUS_UNCAL,      /* calibration missing/invalid: nominal fallback in use */
    SCOPE_STATUS_VIEW_CLIP,  /* converted volts beyond +-range: the view clips */
    SCOPE_STATUS_ADC_SAT     /* raw code 0 or 4095: ADC/input limit */
} scope_status_token;

/* Text fields of a pane; the render step draws one field per item. */
typedef enum {
    SCOPE_FIELD_ID,      /* label row: "01".."10", channel colour */
    SCOPE_FIELD_RANGE,   /* label row: "+-3V" / "+-5V" / "+-8V", the scale the plot is drawn at */
    SCOPE_FIELD_WINDOW,  /* label row, right-aligned: scope_render_window_label() */
    SCOPE_FIELD_CAL,     /* label row: "UNCAL" while the nominal fallback is in use */
    SCOPE_FIELD_TOKEN,   /* status row: "VIEW CLIP" / "ADC SAT" */
    SCOPE_FIELD_LINK,    /* status row: "LINK" while latched */
    SCOPE_FIELD_HOLD,    /* status row: "HOLD" while latched */
    SCOPE_FIELD_COUNT
} scope_text_field;

typedef struct {
    const scope_history *hist;              /* SCOPE_CHANNELS entries */
    uint16_t time_code[SCOPE_CHANNELS];     /* raw TIME knob codes */
    int8_t range[SCOPE_CHANNELS];           /* scope_range_update result: -1, 0, 1, 2 */
    scope_calibration cal[SCOPE_CHANNELS];  /* invalid (e.g. zeroed) = nominal fallback, UNCAL */
    uint32_t samples_per_s;                 /* per channel, nominal */
    bool hold, link;
} scope_render_input;

typedef struct {
    uint8_t pane;
    uint16_t item;                          /* static, then PLOT_W columns, then text fields */
    bool static_done[SCOPE_CHANNELS];
    scope_window window;                    /* current pane's mapping; columns before first_col blank */
    scope_bin cols[SCOPE_PLOT_W];
    scope_calibration cal;                  /* current pane's effective calibration */
    int8_t view_range[SCOPE_CHANNELS];      /* range index each plot is drawn at, latched per pane */
    bool range_known[SCOPE_CHANNELS];       /* a valid range has decoded at least once */
    uint8_t signal[SCOPE_CHANNELS];         /* NONE / VIEW_CLIP / ADC_SAT of the drawn window */
    struct {                                /* last drawn text per field; redraw on change only */
        char text[SCOPE_FIELD_MAX + 1u];
        uint16_t colour;
        bool drawn;
    } shown[SCOPE_CHANNELS][SCOPE_FIELD_COUNT];
    uint32_t text_rects;                    /* display calls spent on text */
    uint32_t rects_sent, rects_failed, passes;
} scope_render_state;

typedef struct { bool raw, stable, toggled; uint32_t since_ms; } scope_button;

scope_rect scope_pane_rect(unsigned pane);
scope_rect scope_pane_tag_rect(unsigned pane);
scope_rect scope_pane_plot_rect(unsigned pane);
/* Text row above the plot: channel ID, range and window duration. */
scope_rect scope_pane_label_rect(unsigned pane);
/* Text row below the plot: status token slot, LINK and HOLD. */
scope_rect scope_pane_status_rect(unsigned pane);
/* Screen rect of one text field (whole cells, inside the label or status row). */
scope_rect scope_pane_field_rect(unsigned pane, scope_text_field f);
scope_rect scope_pane_separator_rect(unsigned pane);
uint16_t scope_channel_colour(unsigned ch);
/* View half-scale in volts for a range index: 3 / 5 / 8; any other index gives the startup +-8 V. */
float scope_range_volts(int range);
/* Row inside a plot of height h: +range_v -> 0 (top), 0 V -> (h - 1) / 2, -range_v ->
 * 2 x ((h - 1) / 2); rounded symmetrically, so -v maps to the mirror row of +v; clamped. */
uint16_t scope_volts_to_row(float volts, float range_v, uint16_t h);
/* One plot column: background, the 0 V grid row, and the bin's lo..hi span converted
 * through cal and range_v; a span beyond +-range_v is pinned at the edge in
 * SCOPE_COLOUR_CLIP with a background gap. NULL = empty. */
void scope_render_column(const scope_bin *bin, scope_calibration cal, float range_v, uint16_t h, uint16_t colour,
                         uint16_t *out);
/* Signal token of n bins: ADC_SAT if any raw lo/hi is 0 or >= 4095, else VIEW_CLIP if any
 * converted lo/hi is beyond +-range_v, else NONE. */
scope_status_token scope_bins_status(const scope_bin *bins, unsigned n, scope_calibration cal, float range_v);
/* TIME code a pane uses: CH1's under LINK, its own otherwise. */
uint16_t scope_render_time_code(const scope_render_input *in, unsigned pane);
/* The one source of window-duration text: "2.0ms" .. "8.19s". It shows the window of
 * scope_window_samples(time_code, samples_per_s), the interval the plot represents (within
 * the scope_core.h coarse-bin tolerance); samples_per_s == 0 falls back to the raw TIME
 * duration. Writes at most SCOPE_WINDOW_LABEL_MAX characters plus NUL to out and returns the length. */
unsigned scope_render_window_label(uint16_t time_code, uint32_t samples_per_s, char out[SCOPE_WINDOW_LABEL_MAX + 1u]);
/* "UNCAL" / "VIEW CLIP" / "ADC SAT", or "" for SCOPE_STATUS_NONE and unknown values. */
const char *scope_status_token_text(unsigned token);
/* 5 x 7 glyph rows for c, bit 4 = leftmost column; NULL if the font has no such glyph. */
const uint8_t *scope_font_glyph(unsigned char c);
void scope_render_init(scope_render_state *s);
/* Issues display calls for up to max_items items; returns the number of display calls. */
unsigned scope_render_step(scope_render_state *s, const scope_render_input *in, unsigned max_items);
/* Debounced press-to-toggle for the active-low HOLD and LINK buttons. Returns the toggle. */
bool scope_button_update(scope_button *b, bool pressed, uint32_t now_ms);
#endif
