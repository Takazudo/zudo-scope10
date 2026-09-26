/* Host tests for the LCD path: lcd_bridge.c framing, run through a bit-level behavioural
 * model of the module's SPI -> 16-bit bridge (74HC4040 + 2 x 74HC4094 + inverter, module
 * schematic p1) into a minimal ILI9488 memory model, plus scope_render.c layout and drawing.
 * The models encode this repository's reading of the schematic and datasheet; they prove
 * framing and geometry logic only, not the physical module (G06 stays OPEN). */
#include "display_port.h"
#include "lcd_bridge.h"
#include "scope_render.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

/* ---- bridge model: one strobe (WRX rising edge) per completed 16-clock word ---- */
typedef struct {
    bool cs_low, dc, str;
    unsigned count;
    uint16_t shift, latch;
    unsigned strobes, cs_release_strobes;
} bridge_model;

/* ---- panel model ---- */
static uint16_t gram[LCD_HEIGHT][LCD_WIDTH];
typedef struct {
    uint8_t cmd, nparam, params[16];
    uint16_t xs, xe, ys, ye, x, y;
    uint8_t colmod, madctl;
    bool reset_asserted, was_reset;
    uint8_t log[512];
    unsigned nlog;
    uint32_t pixels;
    unsigned nonzero_high_byte; /* command/parameter words with D15..D8 != 0 */
} panel_model;

/* ---- recording bus ---- */
typedef struct {
    bridge_model br;
    panel_model p;
    uint8_t trace[256];
    bool trace_dc[256];
    unsigned ntrace, frames;
    uint32_t delay_total_ms, delay_after_slpout_ms, delay_after_reset_ms;
    bool in_frame;
} rig;

static rig R;

static void panel_write(panel_model *p, bool dc, uint16_t w) {
    if (!dc) {
        p->cmd = (uint8_t)w;
        p->nparam = 0;
        if (w >> 8) p->nonzero_high_byte++;
        if (p->nlog < sizeof p->log) p->log[p->nlog++] = p->cmd;
        if (p->cmd == LCD_CMD_RAMWR) { p->x = p->xs; p->y = p->ys; }
        return;
    }
    if (p->cmd == LCD_CMD_RAMWR) {
        assert(p->x < LCD_WIDTH && p->y < LCD_HEIGHT);
        gram[p->y][p->x] = w;
        p->pixels++;
        if (p->x++ == p->xe) { p->x = p->xs; p->y = p->y == p->ye ? p->ys : (uint16_t)(p->y + 1u); }
        return;
    }
    if (w >> 8) p->nonzero_high_byte++;
    if (p->nparam < sizeof p->params) p->params[p->nparam++] = (uint8_t)w;
    const uint8_t *q = p->params;
    if (p->cmd == LCD_CMD_CASET && p->nparam == 4) { p->xs = (uint16_t)(q[0] << 8 | q[1]); p->xe = (uint16_t)(q[2] << 8 | q[3]); }
    if (p->cmd == LCD_CMD_PASET && p->nparam == 4) { p->ys = (uint16_t)(q[0] << 8 | q[1]); p->ye = (uint16_t)(q[2] << 8 | q[3]); }
    if (p->cmd == LCD_CMD_COLMOD && p->nparam == 1) p->colmod = q[0];
    if (p->cmd == LCD_CMD_MADCTL && p->nparam == 1) p->madctl = q[0];
}

static void strobe(bool at_cs_release) {
    R.br.strobes++;
    if (at_cs_release) R.br.cs_release_strobes++;
    assert(!R.p.reset_asserted);
    panel_write(&R.p, R.br.dc, R.br.latch);
}

static void bridge_bit(int bit) {
    bridge_model *m = &R.br;
    m->shift = (uint16_t)((m->shift << 1) | (unsigned)bit); /* SCLK rise: 4094s shift */
    if (m->str) m->latch = m->shift;                          /* latch transparent */
    m->count = (m->count + 1u) & 0xFFFu;                      /* SCLK fall: 4040 counts */
    bool q3 = (m->count >> 3) & 1u;
    if (m->str && !q3) strobe(false);                         /* CLK/16 falls: WRX rises */
    if (!m->str && q3) m->latch = m->shift;
    m->str = q3;
}

static void bus_frame_begin(void *ctx, bool data) {
    (void)ctx;
    assert(!R.in_frame);
    R.br.dc = data;       /* D/C changes only while CS is high */
    R.br.cs_low = true;   /* 4040 leaves reset with count 0 */
    R.in_frame = true;
    R.frames++;
}
static void bus_write(void *ctx, const uint8_t *b, size_t n) {
    (void)ctx;
    assert(R.in_frame);
    for (size_t i = 0; i < n; i++) {
        if (R.ntrace < sizeof R.trace) { R.trace[R.ntrace] = b[i]; R.trace_dc[R.ntrace++] = R.br.dc; }
        for (int k = 7; k >= 0; k--) bridge_bit((b[i] >> k) & 1);
    }
}
static void bus_frame_end(void *ctx) {
    (void)ctx;
    assert(R.in_frame);
    if (R.br.str) strobe(true); /* MR resets the counter: CLK/16 falls as CSX goes high */
    R.br.count = 0;
    R.br.str = false;
    R.br.cs_low = false;
    R.in_frame = false;
}
static void bus_reset(void *ctx, bool asserted) {
    (void)ctx;
    R.p.reset_asserted = asserted;
    if (asserted) R.p.was_reset = true;
    if (!asserted) R.delay_after_reset_ms = 0;
}
static void bus_delay(void *ctx, uint32_t ms) {
    (void)ctx;
    R.delay_total_ms += ms;
    R.delay_after_reset_ms += ms;
    if (R.p.nlog && R.p.log[R.p.nlog - 1] == LCD_CMD_SLPOUT) R.delay_after_slpout_ms += ms;
}
static const lcd_bus bus = {NULL, bus_frame_begin, bus_write, bus_frame_end, bus_reset, bus_delay};

static void rig_reset(void) {
    memset(&R, 0, sizeof R);
    memset(gram, 0, sizeof gram);
}

static void test_word_and_command_framing(void) {
    uint8_t b[2];
    lcd_word_bytes(0xF81Fu, b);
    assert(b[0] == 0xF8 && b[1] == 0x1F); /* MSB first: D15 is the first bit clocked */

    rig_reset();
    const uint8_t p[4] = {0x01, 0x02, 0x03, 0x04};
    lcd_command(&bus, LCD_CMD_CASET, p, 4);
    static const uint8_t want[] = {0x00, 0x2A, 0x00, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00, 0x04};
    assert(R.ntrace == sizeof want && memcmp(R.trace, want, sizeof want) == 0);
    assert(!R.trace_dc[0] && !R.trace_dc[1]);
    for (unsigned i = 2; i < R.ntrace; i++) assert(R.trace_dc[i]);
    assert(R.frames == 2);
    assert(R.br.strobes == 5 && R.br.cs_release_strobes == 0); /* every write strobed with CS low */
    assert(R.p.xs == 0x0102 && R.p.xe == 0x0304 && R.p.nonzero_high_byte == 0);

    rig_reset();
    lcd_command(&bus, LCD_CMD_DISPON, NULL, 0);
    assert(R.frames == 1 && R.ntrace == 2 && R.br.strobes == 1 && R.p.log[0] == LCD_CMD_DISPON);
}

static void test_vendor_single_byte_command_relies_on_cs_release(void) {
    /* The vendor C driver's command framing: one byte with D/C low. On this bridge the only
     * strobe comes from CS going high, which is why lcd_bridge.c pads commands to 16 bits. */
    rig_reset();
    const uint8_t cmd = LCD_CMD_DISPON;
    bus_frame_begin(NULL, false);
    bus_write(NULL, &cmd, 1);
    assert(R.br.strobes == 0);
    bus_frame_end(NULL);
    assert(R.br.strobes == 1 && R.br.cs_release_strobes == 1 && R.p.log[0] == LCD_CMD_DISPON);
}

static void test_init_sequence(void) {
    rig_reset();
    lcd_init_panel(&bus);
    assert(R.p.was_reset && !R.p.reset_asserted);
    assert(R.p.colmod == LCD_COLMOD_16BPP); /* 16 bit/pixel RGB565 on the 16-bit bus */
    assert(R.p.madctl == 0x08);             /* MV = 0: portrait 320 x 480 */
    assert(R.br.cs_release_strobes == 0 && R.p.nonzero_high_byte == 0);
    int slpout = -1, dispon = -1, colmod = -1;
    for (unsigned i = 0; i < R.p.nlog; i++) {
        if (R.p.log[i] == LCD_CMD_SLPOUT) slpout = (int)i;
        if (R.p.log[i] == LCD_CMD_DISPON) dispon = (int)i;
        if (R.p.log[i] == LCD_CMD_COLMOD) colmod = (int)i;
        assert(R.p.log[i] != LCD_CMD_RAMWR);
    }
    assert(slpout == 0 && colmod > slpout && dispon == (int)R.p.nlog - 1);
    assert(R.delay_after_slpout_ms >= 5u); /* datasheet 5.2.13 minimum */
    for (size_t i = 0; i < lcd_init_table_len; i++)
        if (lcd_init_table[i].cmd == LCD_CMD_COLMOD) assert(lcd_init_table[i].param[0] != 0x66); /* no RGB666 */
}

static void test_clip(void) {
    lcd_clip_rect c;
    assert(!lcd_clip(0, 0, 0, 5, &c) && !lcd_clip(0, 0, 5, 0, &c));
    assert(!lcd_clip(LCD_WIDTH, 0, 1, 1, &c) && !lcd_clip(0, LCD_HEIGHT, 1, 1, &c));
    assert(!lcd_clip(0, 0, 1, 1, NULL));
    assert(lcd_clip(0, 0, LCD_WIDTH, LCD_HEIGHT, &c) && c.w == LCD_WIDTH && c.h == LCD_HEIGHT);
    assert(lcd_clip(310, 470, 20, 20, &c) && c.x == 310 && c.y == 470 && c.w == 10 && c.h == 10);
    assert(lcd_clip(300, 400, 65535, 65535, &c) && c.w == 20 && c.h == 80); /* no uint16 wrap */
    assert(lcd_clip(LCD_WIDTH - 1, LCD_HEIGHT - 1, 1, 1, &c) && c.w == 1 && c.h == 1);
}

static void test_blit_through_bridge(void) {
    rig_reset();
    static uint16_t src[20 * 20];
    for (unsigned i = 0; i < 20u * 20u; i++) src[i] = (uint16_t)(0x1000u + i);
    for (unsigned y = 460; y < LCD_HEIGHT; y++)
        for (unsigned x = 290; x < LCD_WIDTH; x++) gram[y][x] = 0xDEAD;
    assert(lcd_blit(&bus, 310, 470, 20, 20, src));
    assert(R.p.pixels == 100 && R.br.cs_release_strobes == 0);
    for (unsigned y = 460; y < LCD_HEIGHT; y++)
        for (unsigned x = 290; x < LCD_WIDTH; x++) {
            bool inside = x >= 310 && y >= 470;
            uint16_t want = inside ? (uint16_t)(0x1000u + (y - 470u) * 20u + (x - 310u)) : 0xDEAD;
            assert(gram[y][x] == want);
        }
    assert(!lcd_blit(&bus, 320, 0, 4, 4, src) && !lcd_blit(&bus, 0, 0, 4, 4, NULL));
    assert(!lcd_blit(NULL, 0, 0, 4, 4, src));

    rig_reset();
    assert(lcd_fill(&bus, 0, 0, LCD_WIDTH, LCD_HEIGHT, 0xF800u));
    assert(R.p.pixels == LCD_WIDTH * LCD_HEIGHT);
    assert(gram[0][0] == 0xF800u && gram[LCD_HEIGHT - 1][LCD_WIDTH - 1] == 0xF800u);
}

/* ---- display_port.h test double for the renderer: routes through lcd_blit and the models ---- */
static uint32_t rect_calls, rect_max_pixels, plot_calls;
static uint32_t text_calls; /* display calls landing in a label or status row */
static bool rect_inside(scope_rect in, scope_rect out) {
    return in.x >= out.x && in.y >= out.y && in.x + in.w <= out.x + out.w && in.y + in.h <= out.y + out.h;
}
static bool fake_ready = true;
bool scope_display_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *px) {
    rect_calls++;
    if ((uint32_t)w * h > rect_max_pixels) rect_max_pixels = (uint32_t)w * h;
    assert((uint32_t)x + w <= SCOPE_DISPLAY_WIDTH && (uint32_t)y + h <= SCOPE_DISPLAY_HEIGHT);
    for (unsigned p = 0; p < SCOPE_CHANNELS; p++) {
        scope_rect r = {x, y, w, h};
        if (rect_inside(r, scope_pane_plot_rect(p))) plot_calls++;
        if (rect_inside(r, scope_pane_label_rect(p)) || rect_inside(r, scope_pane_status_rect(p))) text_calls++;
    }
    return fake_ready && lcd_blit(&bus, x, y, w, h, px);
}
static bool rect_disjoint(scope_rect a, scope_rect b) {
    return a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y;
}

static bool rect_is(scope_rect r, uint16_t x, uint16_t y, uint16_t w, uint16_t h) {
    return r.x == x && r.y == y && r.w == w && r.h == h;
}

static void test_layout(void) {
    /* 2 x 5 column-major: CH1..CH5 left column top to bottom, CH6..CH10 right column. */
    assert(rect_is(scope_pane_rect(0), 0, 0, 160, 96));      /* CH1: top left */
    assert(rect_is(scope_pane_rect(4), 0, 384, 160, 96));    /* CH5: bottom left */
    assert(rect_is(scope_pane_rect(5), 160, 0, 160, 96));    /* CH6: top of the right column */
    assert(rect_is(scope_pane_rect(9), 160, 384, 160, 96));  /* CH10: bottom right */
    assert(rect_is(scope_pane_plot_rect(0), 8, 14, 144, 66));
    assert(rect_is(scope_pane_plot_rect(4), 8, 398, 144, 66));
    assert(rect_is(scope_pane_plot_rect(5), 168, 14, 144, 66));
    assert(rect_is(scope_pane_plot_rect(9), 168, 398, 144, 66));
    assert(rect_is(scope_pane_label_rect(0), 8, 1, 144, 10));
    assert(rect_is(scope_pane_label_rect(5), 168, 1, 144, 10));
    assert(rect_is(scope_pane_status_rect(4), 8, 467, 144, 10));
    assert(rect_is(scope_pane_status_rect(9), 168, 467, 144, 10));
    assert(rect_is(scope_pane_tag_rect(5), 160, 14, 4, 66));
    assert(rect_is(scope_pane_separator_rect(9), 160, 479, 160, 1));
    assert(SCOPE_PLOT_W < SCOPE_HISTORY_BINS); /* plot width no longer tied to the history length */

    uint32_t area = 0;
    for (unsigned p = 0; p < SCOPE_CHANNELS; p++) {
        scope_rect pane = scope_pane_rect(p);
        assert(pane.x == (p / 5u) * 160u && pane.y == (p % 5u) * 96u);
        assert((uint32_t)pane.x + pane.w <= SCOPE_DISPLAY_WIDTH && (uint32_t)pane.y + pane.h <= SCOPE_DISPLAY_HEIGHT);
        area += (uint32_t)pane.w * pane.h;
        for (unsigned q = p + 1; q < SCOPE_CHANNELS; q++) assert(rect_disjoint(pane, scope_pane_rect(q)));
        scope_rect parts[5] = {scope_pane_tag_rect(p), scope_pane_plot_rect(p), scope_pane_label_rect(p),
                               scope_pane_status_rect(p), scope_pane_separator_rect(p)};
        for (unsigned i = 0; i < 5; i++) {
            assert(rect_inside(parts[i], pane));
            for (unsigned j = i + 1; j < 5; j++) assert(rect_disjoint(parts[i], parts[j]));
        }
        assert(parts[1].w == SCOPE_PLOT_W && parts[1].h == SCOPE_PLOT_H);
    }
    assert(area == (uint32_t)SCOPE_DISPLAY_WIDTH * SCOPE_DISPLAY_HEIGHT);
    /* Vertical mapping: +range top, 0 V centre, -range at 2 x half, mirror-symmetric. */
    const uint16_t half = (SCOPE_PLOT_H - 1u) / 2u;
    assert(half == 32u);
    assert(scope_volts_to_row(3.0f, 3.0f, SCOPE_PLOT_H) == 0 && scope_volts_to_row(-3.0f, 3.0f, SCOPE_PLOT_H) == 2u * half);
    assert(scope_volts_to_row(0.0f, 5.0f, SCOPE_PLOT_H) == half);
    assert(scope_volts_to_row(99.0f, 3.0f, SCOPE_PLOT_H) == 0 && scope_volts_to_row(-99.0f, 3.0f, SCOPE_PLOT_H) == 2u * half);
    assert(scope_volts_to_row(NAN, 3.0f, SCOPE_PLOT_H) == half && scope_volts_to_row(1.0f, 0.0f, SCOPE_PLOT_H) == half);
    for (int mv = -9000; mv <= 9000; mv += 7) {
        float v = (float)mv / 1000.0f;
        for (int r = 0; r < 3; r++) {
            float rv = scope_range_volts(r);
            uint16_t up = scope_volts_to_row(v, rv, SCOPE_PLOT_H), down = scope_volts_to_row(-v, rv, SCOPE_PLOT_H);
            assert(up + down == 2u * half);                                          /* mirror row */
            assert(scope_volts_to_row(v + 0.007f, rv, SCOPE_PLOT_H) <= up);          /* monotonic */
        }
    }
    assert(scope_range_volts(0) == 3.0f && scope_range_volts(1) == 5.0f && scope_range_volts(2) == 8.0f);
    assert(scope_range_volts(-1) == 8.0f); /* startup scale */
    scope_calibration unit = {0.01f, 2000.0f, true}; /* code 2000 = 0 V, 100 codes per volt */
    uint16_t col[SCOPE_PLOT_H];
    scope_bin b = {1800, 2200}; /* -2 V .. +2 V at +-8 V: rows 24 .. 40 */
    scope_render_column(&b, unit, 8.0f, SCOPE_PLOT_H, 0xFFFF, col);
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++) assert((col[r] == 0xFFFF) == (r >= 24u && r <= 40u));
    scope_render_column(NULL, unit, 8.0f, SCOPE_PLOT_H, 0xFFFF, col);
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++) assert(col[r] == (r == half ? SCOPE_COLOUR_GRID : SCOPE_COLOUR_BG));
    /* +6 V .. -6 V at +-3 V: pinned at both edges in the clip colour, a gap inside each marker. */
    b = (scope_bin){1400, 2600};
    scope_render_column(&b, unit, 3.0f, SCOPE_PLOT_H, 0xFFFF, col);
    assert(col[0] == SCOPE_COLOUR_CLIP && col[1] == SCOPE_COLOUR_BG && col[2] == 0xFFFF);
    assert(col[2u * half] == SCOPE_COLOUR_CLIP && col[2u * half - 1u] == SCOPE_COLOUR_BG && col[2u * half - 2u] == 0xFFFF);
    /* Signal token: ADC SAT from raw codes, VIEW CLIP from converted volts. */
    scope_bin six = {2600, 2600}, rail_hi = {2000, 4095}, rail_lo = {0, 2000};
    assert(scope_bins_status(&six, 1, unit, 3.0f) == SCOPE_STATUS_VIEW_CLIP);
    assert(scope_bins_status(&six, 1, unit, 8.0f) == SCOPE_STATUS_NONE);
    assert(scope_bins_status(&rail_hi, 1, unit, 8.0f) == SCOPE_STATUS_ADC_SAT);
    assert(scope_bins_status(&rail_lo, 1, unit, 8.0f) == SCOPE_STATUS_ADC_SAT);
    scope_bin both[2] = {{2600, 2600}, {2000, 4095}};
    assert(scope_bins_status(both, 2, unit, 3.0f) == SCOPE_STATUS_ADC_SAT); /* SAT outranks VIEW CLIP */
    assert(scope_bins_status(NULL, 0, unit, 3.0f) == SCOPE_STATUS_NONE);
}

/* Decodes one text cell from GRAM against the firmware font table; '#' = no glyph matches or
 * a pixel outside the glyph box is lit. *fg receives the lit-pixel colour (BG if blank). */
static char decode_cell(unsigned x, unsigned y, uint16_t *fg) {
    uint8_t rows[SCOPE_GLYPH_H] = {0};
    *fg = SCOPE_COLOUR_BG;
    for (unsigned r = 0; r < SCOPE_CELL_H; r++)
        for (unsigned b = 0; b < SCOPE_CELL_W; b++) {
            uint16_t v = gram[y + r][x + b];
            if (v == SCOPE_COLOUR_BG) continue;
            if (*fg != SCOPE_COLOUR_BG && v != *fg) return '#';
            *fg = v;
            if (b >= SCOPE_GLYPH_W || r < SCOPE_GLYPH_Y || r >= SCOPE_GLYPH_Y + SCOPE_GLYPH_H) return '#';
            rows[r - SCOPE_GLYPH_Y] |= (uint8_t)(0x10u >> b);
        }
    for (unsigned c = 1; c < 256; c++) {
        const uint8_t *g = scope_font_glyph((unsigned char)c);
        if (g && !memcmp(g, rows, SCOPE_GLYPH_H)) return (char)c;
    }
    return '#';
}

/* The field's text from GRAM with the padding spaces trimmed; asserts one colour throughout. */
static const char *field_text(unsigned pane, scope_text_field f, uint16_t *colour) {
    static char buf[SCOPE_TEXT_CELLS + 1];
    scope_rect r = scope_pane_field_rect(pane, f);
    unsigned n = 0;
    *colour = SCOPE_COLOUR_BG;
    for (unsigned x = r.x; x < r.x + r.w; x += SCOPE_CELL_W) {
        uint16_t fg;
        buf[n++] = decode_cell(x, r.y, &fg);
        if (fg != SCOPE_COLOUR_BG) {
            assert(*colour == SCOPE_COLOUR_BG || *colour == fg);
            *colour = fg;
        }
    }
    buf[n] = '\0';
    while (n && buf[n - 1] == ' ') buf[--n] = '\0';
    char *t = buf;
    while (*t == ' ') t++;
    return t;
}

static bool field_is(unsigned pane, scope_text_field f, const char *want, uint16_t colour) {
    uint16_t got;
    const char *t = field_text(pane, f, &got);
    if (strcmp(t, want) != 0) {
        fprintf(stderr, "pane %u field %d: got \"%s\", want \"%s\"\n", pane, (int)f, t, want);
        return false;
    }
    return !*want || got == colour;
}

static void test_font_and_labels(void) {
    /* Every glyph distinct (so decoding is unambiguous) and inside 5 columns. */
    const char *set = "0123456789.+-?VmskACDEHIKLNOPSTUW \xb1";
    for (const char *a = set; *a; a++) {
        const uint8_t *ga = scope_font_glyph((unsigned char)*a);
        assert(ga);
        for (unsigned r = 0; r < SCOPE_GLYPH_H; r++) assert(ga[r] < 0x20u);
        for (const char *b = a + 1; *b; b++) assert(memcmp(ga, scope_font_glyph((unsigned char)*b), SCOPE_GLYPH_H));
    }
    assert(!scope_font_glyph('Z') && !scope_font_glyph('\0'));
    char out[SCOPE_WINDOW_LABEL_MAX + 1];
    assert(scope_render_window_label(0, 10000, out) == 5 && !strcmp(out, "2.0ms"));
    assert(scope_render_window_label(4095, 10000, out) == 5 && !strcmp(out, "8.19s"));
    assert(scope_render_window_label(65535, 10000, out) == 5 && !strcmp(out, "8.19s"));
    unsigned n_ms = 0, n_s = 0;
    for (unsigned c = 0; c < 4096; c++) {
        unsigned n = scope_render_window_label((uint16_t)c, 10000, out);
        assert(n == strlen(out) && n >= 5 && n <= SCOPE_WINDOW_LABEL_MAX);
        for (unsigned i = 0; i < n; i++) assert(scope_font_glyph((unsigned char)out[i]));
        if (!strcmp(out + n - 2, "ms")) n_ms++; else { assert(out[n - 1] == 's'); n_s++; }
    }
    assert(n_ms && n_s);
    assert(!strcmp(scope_status_token_text(SCOPE_STATUS_UNCAL), "UNCAL"));
    assert(!strcmp(scope_status_token_text(SCOPE_STATUS_VIEW_CLIP), "VIEW CLIP"));
    assert(!strcmp(scope_status_token_text(SCOPE_STATUS_ADC_SAT), "ADC SAT"));
    for (unsigned t = SCOPE_STATUS_UNCAL; t <= SCOPE_STATUS_ADC_SAT; t++)
        for (const char *c = scope_status_token_text(t); *c; c++) assert(scope_font_glyph((unsigned char)*c));
    assert(!strcmp(scope_status_token_text(SCOPE_STATUS_NONE), "") && !strcmp(scope_status_token_text(99), ""));
    /* Fields sit on whole cells inside their row, disjoint from each other. */
    for (unsigned p = 0; p < SCOPE_CHANNELS; p++)
        for (unsigned f = 0; f < SCOPE_FIELD_COUNT; f++) {
            scope_rect r = scope_pane_field_rect(p, (scope_text_field)f);
            scope_rect row = f < SCOPE_FIELD_TOKEN ? scope_pane_label_rect(p) : scope_pane_status_rect(p);
            assert(rect_inside(r, row) && r.h == SCOPE_CELL_H && r.w % SCOPE_CELL_W == 0 && (r.x - row.x) % SCOPE_CELL_W == 0);
            for (unsigned g = f + 1; g < SCOPE_FIELD_COUNT; g++)
                assert(rect_disjoint(r, scope_pane_field_rect(p, (scope_text_field)g)));
        }
    assert(scope_pane_field_rect(0, SCOPE_FIELD_COUNT).w == 0);
    assert(scope_pane_field_rect(0, SCOPE_FIELD_CAL).w >= 5u * SCOPE_CELL_W);   /* "UNCAL" fits */
    assert(scope_pane_field_rect(0, SCOPE_FIELD_TOKEN).w >= 9u * SCOPE_CELL_W); /* "VIEW CLIP" fits */
}

/* One item per step so the pass ends exactly at its boundary, with nothing of the next begun. */
static unsigned render_pass(scope_render_state *s, const scope_render_input *in) {
    unsigned start = s->passes, guard = 0;
    text_calls = 0;
    while (s->passes == start && guard++ < 10000) scope_render_step(s, in, 1);
    assert(s->passes == start + 1u);
    return text_calls;
}

static scope_history H[SCOPE_CHANNELS];

/* Nominal-transfer code of a small per-channel input, -1.45 V (CH1) .. +1.45 V (CH10). */
static uint16_t renderer_code(unsigned ch) { return (uint16_t)(1678u + 40u * ch); }

static void test_renderer(void) {
    rig_reset();
    lcd_init_panel(&bus);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        scope_history_init(&H[ch]);
        for (unsigned i = 0; i < 100; i++) scope_history_push(&H[ch], renderer_code(ch));
    }
    scope_render_input in = {.hist = H, .samples_per_s = 10000, .hold = false, .link = false};
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) { in.time_code[ch] = 0; in.range[ch] = (int8_t)(ch % 3u); }
    in.range[9] = -1;
    scope_render_state s;
    scope_render_init(&s);
    rect_calls = rect_max_pixels = text_calls = 0;
    unsigned guard = 0;
    while (s.passes == 0 && guard++ < 10000) scope_render_step(&s, &in, 4);
    assert(s.passes == 1 && s.rects_failed == 0 && s.rects_sent == rect_calls);
    assert(rect_max_pixels <= SCOPE_RENDER_FILL_MAX && rect_max_pixels >= SCOPE_PLOT_H);
    assert(R.br.cs_release_strobes == 0);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        scope_rect p = scope_pane_plot_rect(ch);
        uint16_t colour = scope_channel_colour(ch);
        float v = scope_code_to_volts(renderer_code(ch), scope_calibration_nominal());
        uint16_t row = scope_volts_to_row(v, scope_range_volts(ch == 9 ? SCOPE_RANGE_STARTUP : (int)(ch % 3u)), SCOPE_PLOT_H);
        /* 2 ms = 20 samples, all held (100 pushed): stretched over every column */
        for (unsigned col = 0; col < SCOPE_PLOT_W; col++) assert(gram[p.y + row][p.x + col] == colour);
        scope_rect tag = scope_pane_tag_rect(ch);
        assert(gram[tag.y][tag.x] == colour);
        scope_rect sep = scope_pane_separator_rect(ch);
        assert(gram[sep.y][sep.x] == SCOPE_COLOUR_SEPARATOR && gram[sep.y][sep.x + sep.w - 1u] == SCOPE_COLOUR_SEPARATOR);
        char id[3] = {(char)('0' + (ch + 1u) / 10u), (char)('0' + (ch + 1u) % 10u), 0};
        assert(field_is(ch, SCOPE_FIELD_ID, id, colour)); /* channel colour identity */
        assert(field_is(ch, SCOPE_FIELD_WINDOW, "2.0ms", SCOPE_COLOUR_TEXT));
        assert(field_is(ch, SCOPE_FIELD_TOKEN, "", 0) && field_is(ch, SCOPE_FIELD_LINK, "", 0));
        assert(field_is(ch, SCOPE_FIELD_CAL, "UNCAL", SCOPE_COLOUR_WARN)); /* zeroed cal: nominal fallback */
        assert(field_is(ch, SCOPE_FIELD_HOLD, "", 0));
    }
    assert(field_is(0, SCOPE_FIELD_RANGE, "\xb1" "3V", SCOPE_COLOUR_TEXT));
    assert(field_is(5, SCOPE_FIELD_RANGE, "\xb1" "8V", SCOPE_COLOUR_TEXT));
    /* range == -1 before any valid decode: drawn at the startup +-8 V, named in the warning colour. */
    assert(field_is(9, SCOPE_FIELD_RANGE, "\xb1" "8V", SCOPE_COLOUR_WARN));
    assert(s.text_rects == text_calls);
    /* Worst case, every field dirty: ID 1 + RANGE 2 + WINDOW 3 + CAL 3 + TOKEN 5 + LINK 2 + HOLD 2 calls. */
    const unsigned text_worst_per_pass = 18u * SCOPE_CHANNELS;
    assert(text_calls == text_worst_per_pass);
    printf("renderer: first pass %u display calls, %u of them text (worst case)\n", (unsigned)rect_calls,
           (unsigned)text_calls);

    /* Unchanged content: no text is redrawn. */
    assert(render_pass(&s, &in) == 0);

    /* Range change on CH1 only: exactly its RANGE field (2 calls) is redrawn. */
    in.range[0] = 2;
    assert(render_pass(&s, &in) == 2);
    assert(field_is(0, SCOPE_FIELD_RANGE, "\xb1" "8V", SCOPE_COLOUR_TEXT));
    in.range[9] = 1;
    assert(render_pass(&s, &in) == 2);
    assert(field_is(9, SCOPE_FIELD_RANGE, "\xb1" "5V", SCOPE_COLOUR_TEXT));

    /* TIME endpoint: CH10 at full scale. */
    in.time_code[9] = 4095;
    assert(render_pass(&s, &in) == 3);
    assert(field_is(9, SCOPE_FIELD_WINDOW, "8.19s", SCOPE_COLOUR_TEXT));
    assert(field_is(5, SCOPE_FIELD_WINDOW, "2.0ms", SCOPE_COLOUR_TEXT));

    /* A valid calibration on CH6 clears exactly its UNCAL field (3 calls); zeroing it restores UNCAL. */
    in.cal[5] = (scope_calibration){0.008f, 1858.0f, true};
    assert(render_pass(&s, &in) == 3);
    assert(field_is(5, SCOPE_FIELD_CAL, "", 0) && field_is(4, SCOPE_FIELD_CAL, "UNCAL", SCOPE_COLOUR_WARN));
    in.cal[5] = (scope_calibration){0};
    assert(render_pass(&s, &in) == 3);
    assert(field_is(5, SCOPE_FIELD_CAL, "UNCAL", SCOPE_COLOUR_WARN));

    /* HOLD: plots frozen (no plot-area transfers, even when pressed mid-pane), text still
     * updates and shows HOLD. */
    scope_render_step(&s, &in, 10);
    assert(s.item > 1u && s.item < 1u + SCOPE_PLOT_W); /* inside CH1's plot columns */
    in.hold = true;
    in.range[5] = 0;
    plot_calls = 0;
    render_pass(&s, &in);
    assert(plot_calls == 0);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) assert(field_is(ch, SCOPE_FIELD_HOLD, "HOLD", SCOPE_COLOUR_HOLD));
    /* The RANGE label names the frozen plot's scale, so it waits for the plot. */
    assert(field_is(5, SCOPE_FIELD_RANGE, "\xb1" "8V", SCOPE_COLOUR_TEXT));

    /* LINK: every pane takes CH1's TIME window, and its label says so. */
    in.hold = false;
    in.link = true;
    in.time_code[0] = 4095;
    in.time_code[5] = 0;
    render_pass(&s, &in);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        assert(field_is(ch, SCOPE_FIELD_LINK, "LINK", SCOPE_COLOUR_LINK));
        assert(field_is(ch, SCOPE_FIELD_HOLD, "", 0));
        assert(field_is(ch, SCOPE_FIELD_WINDOW, "8.19s", SCOPE_COLOUR_LINK));
    }
    assert(field_is(5, SCOPE_FIELD_RANGE, "\xb1" "3V", SCOPE_COLOUR_TEXT)); /* plot redrawn after HOLD */
    in.link = false;
    render_pass(&s, &in);
    assert(field_is(5, SCOPE_FIELD_WINDOW, "2.0ms", SCOPE_COLOUR_TEXT) && field_is(5, SCOPE_FIELD_LINK, "", 0));
    assert(field_is(0, SCOPE_FIELD_WINDOW, "8.19s", SCOPE_COLOUR_TEXT));

    /* #21 reproduction 1: raw values 0..999 at TIME code 0 (2 ms = 20 samples). Only the
     * newest 20 samples, 980..999, are represented; the older 980 are excluded. */
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        in.time_code[ch] = 0;
        in.range[ch] = 2; /* +-8 V: the newest codes, 980..999, are about -7 V under the nominal transfer */
        scope_history_init(&H[ch]);
        for (unsigned i = 0; i < 1000; i++) scope_history_push(&H[ch], (uint16_t)i);
    }
    scope_bin cols[SCOPE_PLOT_W];
    scope_window w = scope_window_map(&H[0], scope_window_samples(0, 10000), SCOPE_PLOT_W, cols);
    assert(w.window == 20 && w.level == 0 && w.lag == 0 && w.bins == 20 && w.avail == 20 && w.first_col == 0);
    uint16_t lo = 0xFFFF, hi = 0;
    for (unsigned col = 0; col < SCOPE_PLOT_W; col++) {
        if (cols[col].lo < lo) lo = cols[col].lo;
        if (cols[col].hi > hi) hi = cols[col].hi;
    }
    assert(lo == 980 && hi == 999);
    assert(cols[0].lo == 980 && cols[SCOPE_PLOT_W - 1u].hi == 999); /* oldest left, newest right */
    render_pass(&s, &in);
    scope_calibration nominal = scope_calibration_nominal();
    uint16_t top = scope_volts_to_row(scope_code_to_volts(999, nominal), 8.0f, SCOPE_PLOT_H);
    uint16_t bottom = scope_volts_to_row(scope_code_to_volts(980, nominal), 8.0f, SCOPE_PLOT_H);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        scope_rect p = scope_pane_plot_rect(ch);
        for (unsigned col = 0; col < SCOPE_PLOT_W; col++)
            for (unsigned r = 0; r < SCOPE_PLOT_H; r++) {
                if (gram[p.y + r][p.x + col] == scope_channel_colour(ch)) assert(r >= top && r <= bottom);
                assert(gram[p.y + r][p.x + col] != SCOPE_COLOUR_CLIP); /* older, lower codes excluded */
            }
        assert(field_is(ch, SCOPE_FIELD_TOKEN, "", 0)); /* code 0, the oldest sample, is not in the window */
    }

    /* A failing backend is counted, never reported as drawn. */
    fake_ready = false;
    uint32_t failed = s.rects_failed;
    scope_render_step(&s, &in, 4);
    assert(s.rects_failed > failed);
    fake_ready = true;
}

/* Label text back to samples: *half = half a unit of its last digit, in samples. */
static uint32_t label_samples(const char *label, uint32_t sps, uint32_t *half) {
    unsigned n = (unsigned)strlen(label), digits = 0, point = 0;
    bool seconds = label[n - 2] != 'm';
    uint64_t v = 0;
    for (const char *c = label; (*c >= '0' && *c <= '9') || *c == '.'; c++) {
        if (*c == '.') { point = 1; continue; }
        v = v * 10u + (unsigned)(*c - '0');
        digits += point;
    }
    uint64_t unit_us = seconds ? 1000000u : 1000u;
    for (unsigned i = 0; i < digits; i++) unit_us /= 10u;
    *half = (uint32_t)((unit_us * sps / 2u + 999999u) / 1000000u);
    return (uint32_t)((v * unit_us * sps + 500000u) / 1000000u);
}

/* Represented interval of a plan, in samples before the newest pushed sample: [lag, oldest). */
static uint32_t oldest_edge(scope_window w) { return w.lag + ((uint32_t)w.bins << w.level); }

static void test_time_window(void) {
    static scope_history hist;
    scope_bin cols[SCOPE_PLOT_W];
    char label[SCOPE_WINDOW_LABEL_MAX + 1];

    /* Endpoint and intermediate codes, with the newest bins at every stage of completion:
     * each edge of the represented interval lies within one coarse bin (2^L samples). */
    static const uint16_t codes[] = {0, 1, 300, 800, 1454, 1455, 2000, 2400, 2730, 3000, 3300, 3700, 4000, 4094, 4095};
    static const uint32_t extra[] = {0, 1, 255, 256, 511, 777};
    for (unsigned e = 0; e < sizeof extra / sizeof extra[0]; e++) {
        scope_history_init(&hist);
        for (uint32_t i = 0; i < SCOPE_WINDOW_MAX_SAMPLES + extra[e]; i++) scope_history_push(&hist, 2048);
        for (unsigned k = 0; k < sizeof codes / sizeof codes[0]; k++) {
            uint32_t want = scope_window_samples(codes[k], 10000);
            scope_window w = scope_window_map(&hist, want, SCOPE_PLOT_W, cols);
            uint32_t coarse = (uint32_t)1 << w.level;
            assert(w.window == want && ((uint32_t)SCOPE_HISTORY_BINS << w.level) >= want);
            assert(w.level == 0 || ((uint32_t)SCOPE_HISTORY_BINS << (w.level - 1u)) < want); /* smallest level */
            assert(w.lag == (SCOPE_WINDOW_MAX_SAMPLES + extra[e]) % coarse && w.lag < coarse);
            assert(oldest_edge(w) >= want && oldest_edge(w) < want + coarse);
            assert(w.avail == w.bins && w.first_col == 0);
        }
    }
    scope_history_init(&hist);
    for (uint32_t i = 0; i < SCOPE_WINDOW_MAX_SAMPLES; i++) scope_history_push(&hist, 2048);
    scope_window w0 = scope_window_map(&hist, scope_window_samples(0, 10000), SCOPE_PLOT_W, cols);
    scope_window w1 = scope_window_map(&hist, scope_window_samples(4095, 10000), SCOPE_PLOT_W, cols);
    assert(w0.level == 0 && w0.bins == 20 && oldest_edge(w0) == 20);           /* 2 ms exactly */
    assert(w1.level == 9 && w1.bins == 160 && oldest_edge(w1) == 81920);       /* 8.192 s exactly */

    /* No dead zone: the represented duration never shrinks as the knob turns and changes
     * within a short run of codes everywhere; the #21 renderer held one window for 1455.
     * The longest runs sit at 2 ms, where one sample is ~25 codes. The label agrees with the
     * represented interval: within a coarse bin plus the label's own rounding. */
    uint32_t prev = 0, run = 0, max_run = 0;
    for (unsigned c = 0; c < 4096; c++) {
        scope_window w = scope_window_map(&hist, scope_window_samples((uint16_t)c, 10000), SCOPE_PLOT_W, cols);
        uint32_t span = oldest_edge(w), half;
        assert(span >= prev);
        run = span == prev ? run + 1u : 1u;
        if (run > max_run) max_run = run;
        prev = span;
        scope_render_window_label((uint16_t)c, 10000, label);
        uint32_t shown = label_samples(label, 10000, &half);
        uint32_t d_req = shown > w.window ? shown - w.window : w.window - shown;
        uint32_t d_rep = shown > span ? shown - span : span - shown;
        assert(d_req <= half && d_rep <= ((uint32_t)1 << w.level) + half);
    }
    assert(max_run <= 32u);
    printf("time window: longest run of codes with one represented interval %u\n", (unsigned)max_run);

    /* Partial history: 30 samples at 8.192 s keep the full-pane time axis. The held data
     * sits right-aligned and the time not yet recorded stays blank on the left. */
    scope_history_init(&hist);
    for (unsigned i = 0; i < 30; i++) scope_history_push(&hist, 3000);
    scope_window wp = scope_window_map(&hist, 81920, SCOPE_PLOT_W, cols);
    assert(wp.level == 9 && wp.avail == 0 && wp.first_col == SCOPE_PLOT_W); /* no complete 512-sample bin yet */
    for (unsigned i = 30; i < 512u * 16u; i++) scope_history_push(&hist, 3000);
    wp = scope_window_map(&hist, 81920, SCOPE_PLOT_W, cols);
    assert(wp.avail == 16 && wp.bins == 160 && wp.first_col == SCOPE_PLOT_W - 14u); /* 16 of 160 bins: 14.4 columns */
    for (unsigned c = wp.first_col; c < SCOPE_PLOT_W; c++) assert(cols[c].lo == 3000 && cols[c].hi == 3000);

    /* #21 reproduction 2: 98 304 samples at baseline 1858 with one full-scale impulse at
     * index 28 304, about 7 s old. At TIME 4095 (8.192 s) it is in the plot. */
    rig_reset();
    lcd_init_panel(&bus);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) scope_history_init(&H[ch]);
    for (uint32_t i = 0; i < 98304u; i++) scope_history_push(&H[0], i == 28304u ? 4095u : 1858u);
    scope_window wi = scope_window_map(&H[0], scope_window_samples(4095, 10000), SCOPE_PLOT_W, cols);
    unsigned impulse_cols = 0, impulse_col = 0;
    for (unsigned c = wi.first_col; c < SCOPE_PLOT_W; c++)
        if (cols[c].hi == 4095) { impulse_cols++; impulse_col = c; }
    uint32_t age = 98303u - 28304u; /* 69 999 samples before the newest */
    unsigned expect = (unsigned)((uint64_t)(oldest_edge(wi) - 1u - age) * SCOPE_PLOT_W / oldest_edge(wi));
    assert(wi.first_col == 0 && impulse_cols == 1 && impulse_col + 1u >= expect && impulse_col <= expect + 1u);
    scope_render_input in = {.hist = H, .samples_per_s = 10000};
    in.time_code[0] = 4095;
    scope_render_state s;
    scope_render_init(&s);
    render_pass(&s, &in);
    scope_rect p = scope_pane_plot_rect(0);
    /* range 0 (+-3 V): the full-scale impulse is pinned at the top edge, reported as an ADC limit. */
    assert(gram[p.y][p.x + impulse_col] == SCOPE_COLOUR_CLIP && gram[p.y + 2][p.x + impulse_col] == scope_channel_colour(0));
    assert(field_is(0, SCOPE_FIELD_TOKEN, "ADC SAT", SCOPE_COLOUR_WARN));
    assert(field_is(0, SCOPE_FIELD_WINDOW, "8.19s", SCOPE_COLOUR_TEXT));

    /* LINK uses the same mapping: CH6 linked to CH1 at 4095 draws exactly what CH6 draws at
     * its own 4095. */
    for (uint32_t i = 0; i < 98304u; i++) scope_history_push(&H[5], (uint16_t)(i * 7u % 4096u));
    static uint16_t own[SCOPE_PLOT_H][SCOPE_PLOT_W];
    scope_rect p6 = scope_pane_plot_rect(5);
    in.time_code[5] = 4095;
    render_pass(&s, &in);
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++)
        for (unsigned c = 0; c < SCOPE_PLOT_W; c++) own[r][c] = gram[p6.y + r][p6.x + c];
    in.time_code[5] = 0;
    render_pass(&s, &in);
    bool differs = false; /* its own 2 ms shows other samples */
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++)
        for (unsigned c = 0; c < SCOPE_PLOT_W; c++) differs |= gram[p6.y + r][p6.x + c] != own[r][c];
    assert(differs);
    in.link = true;
    render_pass(&s, &in);
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++)
        for (unsigned c = 0; c < SCOPE_PLOT_W; c++) assert(gram[p6.y + r][p6.x + c] == own[r][c]);
    assert(scope_render_time_code(&in, 5) == 4095);
    assert(field_is(5, SCOPE_FIELD_WINDOW, "8.19s", SCOPE_COLOUR_LINK));
}

/* ---- #42: calibrated +-3/5/8 V vertical mapping, judged on actual plot pixels ---- */
static uint16_t plot_img[SCOPE_CHANNELS][SCOPE_PLOT_H][SCOPE_PLOT_W];

static void fill_flat(unsigned ch, uint16_t code) {
    scope_history_init(&H[ch]);
    for (unsigned i = 0; i < 100; i++) scope_history_push(&H[ch], code);
}

static void grab_plots(void) {
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        scope_rect p = scope_pane_plot_rect(ch);
        for (unsigned r = 0; r < SCOPE_PLOT_H; r++)
            for (unsigned c = 0; c < SCOPE_PLOT_W; c++) plot_img[ch][r][c] = gram[p.y + r][p.x + c];
    }
}

/* Whole-plot check: every column holds exactly the expected column pixels. */
static bool plot_is(unsigned ch, const uint16_t want[SCOPE_PLOT_H]) {
    for (unsigned c = 0; c < SCOPE_PLOT_W; c++)
        for (unsigned r = 0; r < SCOPE_PLOT_H; r++)
            if (plot_img[ch][r][c] != want[r]) {
                fprintf(stderr, "pane %u col %u row %u: got %04x want %04x\n", ch, c, r, plot_img[ch][r][c], want[r]);
                return false;
            }
    return true;
}

/* Expected column: background, 0 V grid at row 32, trace rows [a, b] in the channel colour. */
static void expect_column(uint16_t out[SCOPE_PLOT_H], unsigned ch, unsigned a, unsigned b) {
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++) out[r] = r == 32u ? SCOPE_COLOUR_GRID : SCOPE_COLOUR_BG;
    for (unsigned r = a; r <= b; r++) out[r] = scope_channel_colour(ch);
}

static void test_vertical_mapping(void) {
    rig_reset();
    lcd_init_panel(&bus);
    scope_render_input in = {.hist = H, .samples_per_s = 10000};
    scope_render_state s;
    scope_render_init(&s);
    uint16_t want[SCOPE_PLOT_H];
    const scope_calibration nominal = scope_calibration_nominal();

    /* Fixed +3 V through the nominal transfer: code 2230 (2230 - 1858.378) x 8.0696 mV = 2.999 V.
     * CH1 at +-3 V, CH2 at +-5 V, CH3 at +-8 V; all channels calibrated = false (nominal). */
    const uint16_t plus3 = 2230;
    assert(fabsf(scope_code_to_volts(plus3, nominal) - 3.0f) < 0.005f);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) { fill_flat(ch, plus3); in.range[ch] = (int8_t)(ch % 3u); }
    render_pass(&s, &in);
    grab_plots();
    expect_column(want, 0, 0, 0);   /* +-3 V: positive edge */
    assert(plot_is(0, want));
    expect_column(want, 1, 13, 13); /* +-5 V: 3/5 x 32 = 19.2 rows above zero */
    assert(plot_is(1, want));
    expect_column(want, 2, 20, 20); /* +-8 V: 3/8 of the 32-row positive half = 12 rows above zero */
    assert(plot_is(2, want));
    for (unsigned ch = 0; ch < 3; ch++) {
        assert(field_is(ch, SCOPE_FIELD_TOKEN, "", 0));  /* 2.999 V does not exceed +-3 V */
        assert(field_is(ch, SCOPE_FIELD_CAL, "UNCAL", SCOPE_COLOUR_WARN));
    }
    /* Same samples, only the range differs: the whole plot buffers differ (#22 saw zero change). */
    assert(memcmp(plot_img[0], plot_img[1], sizeof plot_img[0]) && memcmp(plot_img[0], plot_img[2], sizeof plot_img[0]));
    /* Switching CH1's range redraws its own plot at the new scale (same pane, same samples). */
    in.range[0] = 2;
    render_pass(&s, &in);
    grab_plots();
    expect_column(want, 0, 20, 20);
    assert(plot_is(0, want));

    /* Symmetry and electrical zero, exact fixture: 100 codes per volt, zero at code 2000. */
    const scope_calibration unit = {0.01f, 2000.0f, true};
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) in.cal[ch] = unit;
    fill_flat(0, 2300); in.range[0] = 2;  /* +3 V at +-8 V: row 20 */
    fill_flat(1, 1700); in.range[1] = 2;  /* -3 V at +-8 V: mirror row 44 */
    fill_flat(2, 2000); in.range[2] = 0;  /* electrical zero: on the zero line */
    fill_flat(3, 1700); in.range[3] = 0;  /* -3 V at +-3 V: negative edge, row 64 */
    render_pass(&s, &in);
    grab_plots();
    expect_column(want, 0, 20, 20); assert(plot_is(0, want));
    expect_column(want, 1, 44, 44); assert(plot_is(1, want));
    expect_column(want, 2, 32, 32); assert(plot_is(2, want));
    expect_column(want, 3, 64, 64); assert(plot_is(3, want));
    assert(field_is(0, SCOPE_FIELD_CAL, "", 0) && field_is(3, SCOPE_FIELD_TOKEN, "", 0));
    /* Nominal zero code 1858 is 3 mV below 0 V: it too sits on the zero line. */
    in.cal[2] = (scope_calibration){0};
    fill_flat(2, 1858);
    render_pass(&s, &in);
    grab_plots();
    expect_column(want, 2, 32, 32); assert(plot_is(2, want));

    /* Ten deliberately different calibrations (distinct zero and gain), each channel fed the
     * code its own fixture reads as +2.0 V; at +-5 V that is 12.8 -> 13 rows above zero (row 19)
     * on every channel. The same codes through the nominal transfer land elsewhere. */
    unsigned nominal_rows_differ = 0;
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        in.cal[ch] = (scope_calibration){0.0055f + 0.0006f * (float)ch, 1400.0f + 30.0f * (float)ch, true};
        uint16_t code = (uint16_t)(in.cal[ch].zero_code + 2.0f / in.cal[ch].volts_per_code + 0.5f);
        fill_flat(ch, code);
        in.range[ch] = 1;
        nominal_rows_differ += scope_volts_to_row(scope_code_to_volts(code, nominal), 5.0f, SCOPE_PLOT_H) != 19u;
    }
    render_pass(&s, &in);
    grab_plots();
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        expect_column(want, ch, 19, 19);
        assert(plot_is(ch, want));
        assert(field_is(ch, SCOPE_FIELD_CAL, "", 0));
    }
    assert(nominal_rows_differ == SCOPE_CHANNELS);

    /* Missing / invalid calibration: UNCAL and exactly the nominal mapping, never the fixture. */
    const scope_calibration bad[4] = {
        {0.0f, 0.0f, false},        /* missing (zeroed) */
        {NAN, 2000.0f, true},       /* non-finite gain */
        {-0.01f, 2000.0f, true},    /* negative gain */
        {0.01f, 2000.0f, false},    /* plausible numbers, not calibrated */
    };
    for (unsigned k = 0; k < 4; k++) {
        in.cal[k] = bad[k];
        fill_flat(k, plus3);
        in.range[k] = 2;
    }
    render_pass(&s, &in);
    grab_plots();
    for (unsigned k = 0; k < 4; k++) {
        expect_column(want, k, 20, 20); /* nominal +3 V at +-8 V; the 0.01 V/code numbers would give row 23 */
        assert(plot_is(k, want));
        assert(field_is(k, SCOPE_FIELD_CAL, "UNCAL", SCOPE_COLOUR_WARN));
    }

    /* VIEW CLIP vs ADC SAT (nominal transfer). +6 V at +-3 V: the view clips, the ADC does not. */
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) in.cal[ch] = (scope_calibration){0};
    const uint16_t plus6 = 2602; /* (2602 - 1858.378) x 8.0696 mV = 6.001 V */
    fill_flat(0, plus6); in.range[0] = 0;
    fill_flat(1, plus6); in.range[1] = 2;  /* same input at +-8 V: inside the view */
    fill_flat(2, 4095);  in.range[2] = 2;  /* raw ADC rail */
    fill_flat(3, 0);     in.range[3] = 2;  /* raw ADC floor */
    fill_flat(4, 1115);  in.range[4] = 0;  /* -6.0 V at +-3 V */
    render_pass(&s, &in);
    grab_plots();
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++) want[r] = r == 32u ? SCOPE_COLOUR_GRID : SCOPE_COLOUR_BG;
    want[0] = SCOPE_COLOUR_CLIP;
    assert(plot_is(0, want));                                    /* pinned at the edge, clip colour */
    assert(field_is(0, SCOPE_FIELD_TOKEN, "VIEW CLIP", SCOPE_COLOUR_WARN));
    expect_column(want, 1, 8, 8);                                /* 6/8 x 32 = 24 rows above zero */
    assert(plot_is(1, want));
    assert(field_is(1, SCOPE_FIELD_TOKEN, "", 0));
    assert(field_is(2, SCOPE_FIELD_TOKEN, "ADC SAT", SCOPE_COLOUR_WARN));
    assert(field_is(3, SCOPE_FIELD_TOKEN, "ADC SAT", SCOPE_COLOUR_WARN));
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++) want[r] = r == 32u ? SCOPE_COLOUR_GRID : SCOPE_COLOUR_BG;
    want[64] = SCOPE_COLOUR_CLIP;
    assert(plot_is(4, want));
    assert(field_is(4, SCOPE_FIELD_TOKEN, "VIEW CLIP", SCOPE_COLOUR_WARN));
    /* Back inside the view: the token clears. */
    fill_flat(0, plus3);
    render_pass(&s, &in);
    assert(field_is(0, SCOPE_FIELD_TOKEN, "", 0));

    /* Deadband (-1) keeps the last valid scale; the label keeps naming it. */
    fill_flat(0, plus3);
    in.range[0] = 0;
    render_pass(&s, &in);
    in.range[0] = -1;
    render_pass(&s, &in);
    grab_plots();
    expect_column(want, 0, 0, 0);
    assert(plot_is(0, want));
    assert(field_is(0, SCOPE_FIELD_RANGE, "\xb1" "3V", SCOPE_COLOUR_TEXT));
    printf("vertical mapping: +3 V -> row 0 at +-3 V, row 13 at +-5 V, row 20 at +-8 V (zero row 32)\n");
}

static void test_buttons(void) {
    scope_button b = {0};
    assert(!scope_button_update(&b, true, 0));
    assert(!scope_button_update(&b, true, 19));
    assert(scope_button_update(&b, true, 20));    /* debounced press toggles on */
    assert(scope_button_update(&b, true, 500));   /* holding does not re-toggle */
    assert(scope_button_update(&b, false, 510));
    assert(scope_button_update(&b, true, 515));   /* 5 ms bounce: ignored */
    assert(scope_button_update(&b, false, 520));
    assert(scope_button_update(&b, false, 545));
    assert(scope_button_update(&b, true, 600));
    assert(!scope_button_update(&b, true, 620));  /* second press toggles off */
}

int main(void) {
    test_word_and_command_framing();
    test_vendor_single_byte_command_relies_on_cs_release();
    test_init_sequence();
    test_clip();
    test_blit_through_bridge();
    test_layout();
    test_font_and_labels();
    test_renderer();
    test_time_window();
    test_vertical_mapping();
    test_buttons();
    puts("LCD bridge framing, clipping, pane layout and renderer host tests passed (models only; G06 OPEN)");
    return 0;
}
