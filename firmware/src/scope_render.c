#include "scope_render.h"
#include "display_port.h"

#define ITEM_STATIC 0u
#define ITEM_COL0 1u
#define ITEM_STATUS (ITEM_COL0 + SCOPE_PLOT_W)

_Static_assert(SCOPE_PANE_H * SCOPE_CHANNELS == SCOPE_DISPLAY_HEIGHT, "ten panes fill the height");
_Static_assert(SCOPE_TAG_X + SCOPE_TAG_W < SCOPE_PLOT_X, "tag and plot overlap");
_Static_assert(SCOPE_PLOT_X + SCOPE_PLOT_W < SCOPE_STATUS_X, "plot and status overlap");
_Static_assert(SCOPE_STATUS_X + SCOPE_STATUS_W <= SCOPE_DISPLAY_WIDTH, "status off-screen");
_Static_assert(SCOPE_PANE_MARGIN_TOP + SCOPE_PLOT_H < SCOPE_PANE_H - 1u, "plot hits separator");

static const uint16_t palette[SCOPE_CHANNELS] = {
    SCOPE_RGB565(255, 220, 0),   SCOPE_RGB565(0, 220, 255),  SCOPE_RGB565(255, 80, 200),
    SCOPE_RGB565(80, 255, 80),   SCOPE_RGB565(255, 120, 40), SCOPE_RGB565(150, 120, 255),
    SCOPE_RGB565(255, 255, 255), SCOPE_RGB565(0, 255, 170),  SCOPE_RGB565(255, 60, 60),
    SCOPE_RGB565(160, 200, 255),
};

static uint16_t pane_top(unsigned pane) { return (uint16_t)(pane * SCOPE_PANE_H); }

scope_rect scope_pane_rect(unsigned pane) {
    return (scope_rect){0, pane_top(pane), SCOPE_DISPLAY_WIDTH, SCOPE_PANE_H};
}
scope_rect scope_pane_tag_rect(unsigned pane) {
    return (scope_rect){SCOPE_TAG_X, (uint16_t)(pane_top(pane) + SCOPE_PANE_MARGIN_TOP), SCOPE_TAG_W, SCOPE_PLOT_H};
}
scope_rect scope_pane_plot_rect(unsigned pane) {
    return (scope_rect){SCOPE_PLOT_X, (uint16_t)(pane_top(pane) + SCOPE_PANE_MARGIN_TOP), SCOPE_PLOT_W, SCOPE_PLOT_H};
}
scope_rect scope_pane_status_rect(unsigned pane) {
    return (scope_rect){SCOPE_STATUS_X, (uint16_t)(pane_top(pane) + SCOPE_PANE_MARGIN_TOP), SCOPE_STATUS_W, SCOPE_PLOT_H};
}
scope_rect scope_pane_separator_rect(unsigned pane) {
    return (scope_rect){0, (uint16_t)(pane_top(pane) + SCOPE_PANE_H - 1u), SCOPE_DISPLAY_WIDTH, 1};
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

static unsigned draw_status(scope_render_state *s, const scope_render_input *in, unsigned pane) {
    scope_rect st = scope_pane_status_rect(pane);
    uint16_t colour = scope_channel_colour(pane);
    uint16_t tcode = in->link ? in->time_code[0] : in->time_code[pane];
    unsigned calls = 0;
    for (unsigned i = 0; i < 3u; i++) {
        scope_rect box = {(uint16_t)(st.x + 4u + i * 24u), (uint16_t)(st.y + 4u), 20, 12};
        calls += fill(s, box, in->range[pane] == (int8_t)i ? colour : SCOPE_COLOUR_DIM);
    }
    const uint16_t bar_w = 100u;
    uint16_t lit = (uint16_t)(1u + (uint32_t)(tcode > 4095u ? 4095u : tcode) * (bar_w - 1u) / 4095u);
    calls += fill(s, (scope_rect){(uint16_t)(st.x + 4u), (uint16_t)(st.y + 22u), lit, 8}, colour);
    if (lit < bar_w)
        calls += fill(s, (scope_rect){(uint16_t)(st.x + 4u + lit), (uint16_t)(st.y + 22u), (uint16_t)(bar_w - lit), 8},
                      SCOPE_COLOUR_DIM);
    calls += fill(s, (scope_rect){(uint16_t)(st.x + 4u), (uint16_t)(st.y + 34u), 8, 8},
                  in->link ? SCOPE_COLOUR_LINK : SCOPE_COLOUR_DIM);
    calls += fill(s, (scope_rect){(uint16_t)(st.x + 16u), (uint16_t)(st.y + 34u), 8, 8},
                  in->hold ? SCOPE_COLOUR_HOLD : SCOPE_COLOUR_DIM);
    return calls;
}

static unsigned draw_column(scope_render_state *s, unsigned pane, unsigned col) {
    uint16_t px[SCOPE_PLOT_H];
    unsigned first = SCOPE_PLOT_W - s->nbins;
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
                s->item = ITEM_STATUS;
                continue;
            }
            uint16_t tcode = in->link ? in->time_code[0] : in->time_code[pane];
            s->nbins = (uint16_t)scope_history_recent(&in->hist[pane], scope_render_level(tcode, in->samples_per_s),
                                                      s->bins, SCOPE_PLOT_W);
            s->item = ITEM_COL0;
        } else if (s->item < ITEM_STATUS) {
            calls += draw_column(s, pane, s->item - ITEM_COL0);
            s->item++;
        } else {
            calls += draw_status(s, in, pane);
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
