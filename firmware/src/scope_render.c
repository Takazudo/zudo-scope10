#include "scope_render.h"
#include "display_port.h"
#include <string.h>

#define ITEM_STATIC 0u
#define ITEM_COL0 1u
#define ITEM_TEXT0 (ITEM_COL0 + SCOPE_PLOT_W)
#define ITEM_END (ITEM_TEXT0 + SCOPE_FIELD_COUNT)
#define CELLS_PER_CALL (SCOPE_RENDER_FILL_MAX / (SCOPE_CELL_W * SCOPE_CELL_H))

_Static_assert(SCOPE_PANE_COLS * SCOPE_PANE_ROWS == SCOPE_CHANNELS, "one pane per channel");
_Static_assert(SCOPE_PANE_COLS * SCOPE_PANE_W == SCOPE_DISPLAY_WIDTH, "two pane columns fill the width");
_Static_assert(SCOPE_PANE_ROWS * SCOPE_PANE_H == SCOPE_DISPLAY_HEIGHT, "five pane rows fill the height");
_Static_assert(SCOPE_TAG_X + SCOPE_TAG_W < SCOPE_PLOT_X, "tag and plot overlap");
_Static_assert(SCOPE_PLOT_X + SCOPE_PLOT_W <= SCOPE_PANE_W, "plot leaves its pane");
_Static_assert(SCOPE_LABEL_Y + SCOPE_LABEL_H < SCOPE_PLOT_Y, "label row and plot overlap");
_Static_assert(SCOPE_PLOT_Y + SCOPE_PLOT_H < SCOPE_STATUS_Y, "plot and status row overlap");
_Static_assert(SCOPE_STATUS_Y + SCOPE_STATUS_H < SCOPE_PANE_H - 1u, "status row hits separator");
_Static_assert(SCOPE_PLOT_W <= SCOPE_HISTORY_BINS, "history shorter than the plot");
_Static_assert(SCOPE_PLOT_H <= SCOPE_RENDER_FILL_MAX, "plot column exceeds one transfer");
_Static_assert(SCOPE_CELL_H == SCOPE_LABEL_H && SCOPE_CELL_H == SCOPE_STATUS_H, "text cells fill a text row");
_Static_assert(SCOPE_GLYPH_W < SCOPE_CELL_W && SCOPE_GLYPH_Y + SCOPE_GLYPH_H <= SCOPE_CELL_H, "glyph leaves its cell");
_Static_assert(CELLS_PER_CALL >= 1u, "one text cell exceeds one transfer");

/* Clean-room 5 x 7 glyphs drawn for this project (no third-party font data); bit 4 = left. */
static const struct { unsigned char c; uint8_t rows[SCOPE_GLYPH_H]; } font[] = {
    {' ', {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}},
    {'0', {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E}},
    {'1', {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E}},
    {'2', {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F}},
    {'3', {0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E}},
    {'4', {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02}},
    {'5', {0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E}},
    {'6', {0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E}},
    {'7', {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08}},
    {'8', {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E}},
    {'9', {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C}},
    {'.', {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C}},
    {'+', {0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00}},
    {'-', {0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00}},
    {(unsigned char)SCOPE_CHAR_PM, {0x04, 0x04, 0x1F, 0x04, 0x04, 0x00, 0x1F}},
    {'?', {0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04}},
    {'V', {0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04}},
    {'m', {0x00, 0x00, 0x1A, 0x15, 0x15, 0x11, 0x11}},
    {'s', {0x00, 0x00, 0x0E, 0x10, 0x0E, 0x01, 0x1E}},
    {'k', {0x10, 0x10, 0x12, 0x14, 0x18, 0x14, 0x12}},
    {'A', {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}},
    {'C', {0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E}},
    {'D', {0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C}},
    {'H', {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}},
    {'I', {0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E}},
    {'K', {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11}},
    {'L', {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F}},
    {'N', {0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11}},
    {'O', {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}},
    {'P', {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10}},
    {'S', {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E}},
    {'T', {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04}},
    {'U', {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}},
};

/* Text field placement in cells: row 0 = label row, 1 = status row. */
static const struct { uint8_t row, col, width; bool right; } fields[SCOPE_FIELD_COUNT] = {
    [SCOPE_FIELD_ID] = {0, 0, 2, false},
    [SCOPE_FIELD_RANGE] = {0, 4, 3, false},
    [SCOPE_FIELD_WINDOW] = {0, SCOPE_TEXT_CELLS - SCOPE_FIELD_MAX, SCOPE_FIELD_MAX, true},
    [SCOPE_FIELD_TOKEN] = {1, 0, 5, false},
    [SCOPE_FIELD_LINK] = {1, 15, 4, false},
    [SCOPE_FIELD_HOLD] = {1, SCOPE_TEXT_CELLS - 4u, 4, false},
};
_Static_assert(SCOPE_TEXT_CELLS == 24u, "field table assumes a 24-cell text row");

static const uint16_t palette[SCOPE_CHANNELS] = {
    SCOPE_RGB565(255, 220, 0),   SCOPE_RGB565(0, 220, 255),  SCOPE_RGB565(255, 80, 200),
    SCOPE_RGB565(80, 255, 80),   SCOPE_RGB565(255, 120, 40), SCOPE_RGB565(150, 120, 255),
    SCOPE_RGB565(255, 255, 255), SCOPE_RGB565(0, 255, 170),  SCOPE_RGB565(255, 60, 60),
    SCOPE_RGB565(160, 200, 255),
};

static uint16_t pane_left(unsigned pane) { return (uint16_t)((pane / SCOPE_PANE_ROWS) * SCOPE_PANE_W); }
static uint16_t pane_top(unsigned pane) { return (uint16_t)((pane % SCOPE_PANE_ROWS) * SCOPE_PANE_H); }
static scope_rect in_pane(unsigned pane, uint16_t x, uint16_t y, uint16_t w, uint16_t h) {
    return (scope_rect){(uint16_t)(pane_left(pane) + x), (uint16_t)(pane_top(pane) + y), w, h};
}

scope_rect scope_pane_rect(unsigned pane) { return in_pane(pane, 0, 0, SCOPE_PANE_W, SCOPE_PANE_H); }
scope_rect scope_pane_tag_rect(unsigned pane) {
    return in_pane(pane, SCOPE_TAG_X, SCOPE_PLOT_Y, SCOPE_TAG_W, SCOPE_PLOT_H);
}
scope_rect scope_pane_plot_rect(unsigned pane) {
    return in_pane(pane, SCOPE_PLOT_X, SCOPE_PLOT_Y, SCOPE_PLOT_W, SCOPE_PLOT_H);
}
scope_rect scope_pane_label_rect(unsigned pane) {
    return in_pane(pane, SCOPE_PLOT_X, SCOPE_LABEL_Y, SCOPE_PLOT_W, SCOPE_LABEL_H);
}
scope_rect scope_pane_status_rect(unsigned pane) {
    return in_pane(pane, SCOPE_PLOT_X, SCOPE_STATUS_Y, SCOPE_PLOT_W, SCOPE_STATUS_H);
}
scope_rect scope_pane_field_rect(unsigned pane, scope_text_field f) {
    if ((unsigned)f >= SCOPE_FIELD_COUNT) return (scope_rect){0, 0, 0, 0};
    scope_rect row = fields[f].row ? scope_pane_status_rect(pane) : scope_pane_label_rect(pane);
    return (scope_rect){(uint16_t)(row.x + fields[f].col * SCOPE_CELL_W), row.y,
                        (uint16_t)(fields[f].width * SCOPE_CELL_W), SCOPE_CELL_H};
}
scope_rect scope_pane_separator_rect(unsigned pane) {
    return in_pane(pane, 0, (uint16_t)(SCOPE_PANE_H - 1u), SCOPE_PANE_W, 1);
}

uint16_t scope_channel_colour(unsigned ch) { return palette[ch % SCOPE_CHANNELS]; }

uint16_t scope_code_to_row(uint16_t code, uint16_t h) {
    if (h < 2u) return 0;
    uint32_t c = code > 4095u ? 4095u : code;
    return (uint16_t)(((4095u - c) * (h - 1u) + 2047u) / 4095u);
}

void scope_render_column(const scope_bin *bin, uint16_t h, uint16_t colour, uint16_t *out) {
    for (uint16_t r = 0; r < h; r++) out[r] = SCOPE_COLOUR_BG;
    if (h) out[scope_code_to_row(2048u, h)] = SCOPE_COLOUR_GRID;
    if (!bin) return;
    uint16_t a = scope_code_to_row(bin->hi, h), b = scope_code_to_row(bin->lo, h);
    if (a > b) { uint16_t t = a; a = b; b = t; }
    for (uint16_t r = a; r <= b && r < h; r++) out[r] = colour;
}

unsigned scope_render_level(uint16_t time_code, uint32_t samples_per_s) {
    float samples = scope_time_seconds(time_code) * (float)samples_per_s + 0.5f;
    return scope_history_level_for_window((uint32_t)samples, SCOPE_PLOT_W);
}

unsigned scope_render_window_label(uint16_t time_code, uint32_t samples_per_s, char out[SCOPE_FIELD_MAX + 1u]) {
    (void)samples_per_s; /* the TIME sub derives the represented window from the rate */
    uint32_t us = (uint32_t)(scope_time_seconds(time_code) * 1e6f + 0.5f);
    unsigned n = 0;
    char d[8];
    unsigned nd = 0, point, value;
    const char *unit;
    if (us < 99950u) { value = (us + 50u) / 100u; point = 1; unit = "ms"; }          /* 2.0ms .. 99.9ms */
    else if (us < 999500u) { value = (us + 500u) / 1000u; point = 0; unit = "ms"; }  /* 100ms .. 999ms */
    else { value = (us + 5000u) / 10000u; point = 2; unit = "s"; }                     /* 1.00s .. 8.19s */
    do { d[nd++] = (char)('0' + value % 10u); value /= 10u; } while (value || nd <= point);
    while (nd && n < SCOPE_FIELD_MAX) {
        out[n++] = d[--nd];
        if (nd == point && point && n < SCOPE_FIELD_MAX) out[n++] = '.';
    }
    for (; *unit && n < SCOPE_FIELD_MAX; unit++) out[n++] = *unit;
    out[n] = '\0';
    return n;
}

const char *scope_status_token_text(unsigned token) {
    switch (token) {
    case SCOPE_STATUS_UNCAL: return "UNCAL";
    case SCOPE_STATUS_CLIP: return "CLIP";
    case SCOPE_STATUS_SAT: return "SAT";
    default: return "";
    }
}

const uint8_t *scope_font_glyph(unsigned char c) {
    for (unsigned i = 0; i < sizeof font / sizeof font[0]; i++)
        if (font[i].c == c) return font[i].rows;
    return NULL;
}

void scope_render_init(scope_render_state *s) {
    *s = (scope_render_state){0};
}

static void count(scope_render_state *s, bool ok) {
    if (ok) s->rects_sent++; else s->rects_failed++;
}

static unsigned fill(scope_render_state *s, scope_rect r, uint16_t colour) {
    static uint16_t solid[SCOPE_RENDER_FILL_MAX];
    for (unsigned i = 0; i < SCOPE_RENDER_FILL_MAX; i++) solid[i] = colour;
    unsigned calls = 0;
    for (uint16_t x = 0; x < r.w; x = (uint16_t)(x + SCOPE_RENDER_FILL_MAX)) {
        unsigned left = (unsigned)r.w - x;
        uint16_t w = (uint16_t)(left < SCOPE_RENDER_FILL_MAX ? left : SCOPE_RENDER_FILL_MAX);
        uint16_t rows = (uint16_t)(SCOPE_RENDER_FILL_MAX / w);
        for (uint16_t y = 0; y < r.h; y = (uint16_t)(y + rows)) {
            unsigned down = (unsigned)r.h - y;
            uint16_t h = (uint16_t)(down < rows ? down : rows);
            count(s, scope_display_rect((uint16_t)(r.x + x), (uint16_t)(r.y + y), w, h, solid));
            calls++;
        }
    }
    return calls;
}

/* Draws cells of text (unknown characters as blanks), CELLS_PER_CALL cells per display call. */
static unsigned draw_text(scope_render_state *s, uint16_t x, uint16_t y, const char *text, unsigned ncells,
                          uint16_t colour, bool *ok) {
    uint16_t px[CELLS_PER_CALL * SCOPE_CELL_W * SCOPE_CELL_H];
    unsigned calls = 0;
    for (unsigned c0 = 0; c0 < ncells; c0 += CELLS_PER_CALL) {
        unsigned n = ncells - c0 < CELLS_PER_CALL ? ncells - c0 : CELLS_PER_CALL;
        uint16_t w = (uint16_t)(n * SCOPE_CELL_W);
        for (unsigned i = 0; i < (unsigned)w * SCOPE_CELL_H; i++) px[i] = SCOPE_COLOUR_BG;
        for (unsigned k = 0; k < n; k++) {
            const uint8_t *g = scope_font_glyph((unsigned char)text[c0 + k]);
            if (!g) continue;
            for (unsigned r = 0; r < SCOPE_GLYPH_H; r++)
                for (unsigned b = 0; b < SCOPE_GLYPH_W; b++)
                    if (g[r] & (0x10u >> b)) px[(SCOPE_GLYPH_Y + r) * w + k * SCOPE_CELL_W + b] = colour;
        }
        bool sent = scope_display_rect((uint16_t)(x + c0 * SCOPE_CELL_W), y, w, SCOPE_CELL_H, px);
        count(s, sent);
        if (!sent) *ok = false;
        calls++;
    }
    return calls;
}

static void field_content(const scope_render_input *in, unsigned pane, scope_text_field f, char *raw,
                          uint16_t *colour) {
    static const char range_digit[3] = {'3', '5', '8'};
    *colour = SCOPE_COLOUR_TEXT;
    raw[0] = '\0';
    switch (f) {
    case SCOPE_FIELD_ID:
        raw[0] = (char)('0' + (pane + 1u) / 10u);
        raw[1] = (char)('0' + (pane + 1u) % 10u);
        raw[2] = '\0';
        *colour = scope_channel_colour(pane);
        break;
    case SCOPE_FIELD_RANGE: {
        int r = in->range[pane];
        raw[0] = SCOPE_CHAR_PM;
        raw[1] = r >= 0 && r < 3 ? range_digit[r] : '?';
        raw[2] = 'V';
        raw[3] = '\0';
        break;
    }
    case SCOPE_FIELD_WINDOW:
        scope_render_window_label(in->link ? in->time_code[0] : in->time_code[pane], in->samples_per_s, raw);
        if (in->link) *colour = SCOPE_COLOUR_LINK; /* the window comes from CH1's TIME */
        break;
    case SCOPE_FIELD_TOKEN: {
        const char *t = scope_status_token_text(in->status_token[pane]);
        unsigned i = 0;
        for (; t[i] && i < SCOPE_FIELD_MAX; i++) raw[i] = t[i];
        raw[i] = '\0';
        *colour = SCOPE_COLOUR_WARN;
        break;
    }
    case SCOPE_FIELD_LINK:
        if (in->link) { raw[0] = 'L'; raw[1] = 'I'; raw[2] = 'N'; raw[3] = 'K'; raw[4] = '\0'; }
        *colour = SCOPE_COLOUR_LINK;
        break;
    case SCOPE_FIELD_HOLD:
        if (in->hold) { raw[0] = 'H'; raw[1] = 'O'; raw[2] = 'L'; raw[3] = 'D'; raw[4] = '\0'; }
        *colour = SCOPE_COLOUR_HOLD;
        break;
    default:
        break;
    }
}

/* One text field: pad to the field width, then redraw only if string or colour changed. */
static unsigned draw_field(scope_render_state *s, const scope_render_input *in, unsigned pane, scope_text_field f) {
    char raw[SCOPE_FIELD_MAX + 1u], text[SCOPE_FIELD_MAX + 1u];
    uint16_t colour;
    field_content(in, pane, f, raw, &colour);
    unsigned width = fields[f].width, len = 0;
    while (raw[len] && len < width) len++;
    unsigned lead = fields[f].right ? width - len : 0;
    for (unsigned i = 0; i < width; i++) text[i] = i >= lead && i - lead < len ? raw[i - lead] : ' ';
    text[width] = '\0';
    if (s->shown[pane][f].drawn && s->shown[pane][f].colour == colour && !strcmp(s->shown[pane][f].text, text))
        return 0;
    scope_rect r = scope_pane_field_rect(pane, f);
    bool ok = true;
    unsigned calls = draw_text(s, r.x, r.y, text, width, colour, &ok);
    s->text_rects += calls;
    memcpy(s->shown[pane][f].text, text, width + 1u);
    s->shown[pane][f].colour = colour;
    s->shown[pane][f].drawn = ok; /* a failed transfer is retried on the next pass */
    return calls;
}

static unsigned draw_column(scope_render_state *s, unsigned pane, unsigned col) {
    uint16_t px[SCOPE_PLOT_H];
    unsigned nbins = s->nbins < SCOPE_PLOT_W ? s->nbins : SCOPE_PLOT_W;
    unsigned first = SCOPE_PLOT_W - nbins;
    const scope_bin *bin = col >= first ? &s->bins[col - first] : NULL;
    scope_rect p = scope_pane_plot_rect(pane);
    scope_render_column(bin, SCOPE_PLOT_H, scope_channel_colour(pane), px);
    count(s, scope_display_rect((uint16_t)(p.x + col), p.y, 1, SCOPE_PLOT_H, px));
    return 1;
}

unsigned scope_render_step(scope_render_state *s, const scope_render_input *in, unsigned max_items) {
    unsigned calls = 0;
    if (!s || !in || !in->hist) return 0;
    for (unsigned n = 0; n < max_items; n++) {
        unsigned pane = s->pane;
        if (s->item == ITEM_STATIC) {
            if (!s->static_done[pane]) {
                calls += fill(s, scope_pane_tag_rect(pane), scope_channel_colour(pane));
                calls += fill(s, scope_pane_separator_rect(pane), SCOPE_COLOUR_SEPARATOR);
                s->static_done[pane] = true;
            }
            if (in->hold) {
                s->item = ITEM_TEXT0;
                continue;
            }
            uint16_t tcode = in->link ? in->time_code[0] : in->time_code[pane];
            s->nbins = (uint16_t)scope_history_recent(&in->hist[pane], scope_render_level(tcode, in->samples_per_s),
                                                      s->bins, SCOPE_PLOT_W);
            s->item = ITEM_COL0;
        } else if (s->item < ITEM_TEXT0) {
            if (in->hold) { /* HOLD mid-pane: freeze now, leave the rest of the plot as drawn */
                s->item = ITEM_TEXT0;
                continue;
            }
            calls += draw_column(s, pane, s->item - ITEM_COL0);
            s->item++;
        } else {
            calls += draw_field(s, in, pane, (scope_text_field)(s->item - ITEM_TEXT0));
            if (++s->item < ITEM_END) continue;
            s->item = ITEM_STATIC;
            if (++s->pane == SCOPE_CHANNELS) {
                s->pane = 0;
                s->passes++;
            }
        }
    }
    return calls;
}

bool scope_button_update(scope_button *b, bool pressed, uint32_t now_ms) {
    if (pressed != b->raw) {
        b->raw = pressed;
        b->since_ms = now_ms;
    } else if (b->raw != b->stable && (uint32_t)(now_ms - b->since_ms) >= SCOPE_BUTTON_DEBOUNCE_MS) {
        b->stable = b->raw;
        if (b->stable) b->toggled = !b->toggled;
    }
    return b->toggled;
}
