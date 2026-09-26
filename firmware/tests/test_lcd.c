/* Host tests for the LCD path: lcd_bridge.c framing, run through a bit-level behavioural
 * model of the module's SPI -> 16-bit bridge (74HC4040 + 2 x 74HC4094 + inverter, module
 * schematic p1) into a minimal ILI9488 memory model, plus scope_render.c layout and drawing.
 * The models encode this repository's reading of the schematic and datasheet; they prove
 * framing and geometry logic only, not the physical module (G06 stays OPEN). */
#include "display_port.h"
#include "lcd_bridge.h"
#include "scope_render.h"
#include <assert.h>
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
static bool fake_ready = true;
bool scope_display_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *px) {
    rect_calls++;
    if ((uint32_t)w * h > rect_max_pixels) rect_max_pixels = (uint32_t)w * h;
    assert((uint32_t)x + w <= SCOPE_DISPLAY_WIDTH && (uint32_t)y + h <= SCOPE_DISPLAY_HEIGHT);
    if (x >= SCOPE_PLOT_X && x < SCOPE_PLOT_X + SCOPE_PLOT_W) plot_calls++;
    return fake_ready && lcd_blit(&bus, x, y, w, h, px);
}

static bool rect_inside(scope_rect in, scope_rect out) {
    return in.x >= out.x && in.y >= out.y && in.x + in.w <= out.x + out.w && in.y + in.h <= out.y + out.h;
}
static bool rect_disjoint(scope_rect a, scope_rect b) {
    return a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y;
}

static void test_layout(void) {
    unsigned covered = 0;
    for (unsigned p = 0; p < SCOPE_CHANNELS; p++) {
        scope_rect pane = scope_pane_rect(p);
        assert(pane.y == covered && pane.w == SCOPE_DISPLAY_WIDTH);
        covered += pane.h;
        scope_rect parts[4] = {scope_pane_tag_rect(p), scope_pane_plot_rect(p), scope_pane_status_rect(p),
                               scope_pane_separator_rect(p)};
        for (unsigned i = 0; i < 4; i++) {
            assert(rect_inside(parts[i], pane));
            for (unsigned j = i + 1; j < 4; j++) assert(rect_disjoint(parts[i], parts[j]));
        }
        assert(parts[1].w == SCOPE_HISTORY_BINS);
    }
    assert(covered == SCOPE_DISPLAY_HEIGHT);
    assert(scope_code_to_row(4095, SCOPE_PLOT_H) == 0 && scope_code_to_row(0, SCOPE_PLOT_H) == SCOPE_PLOT_H - 1);
    assert(scope_code_to_row(65535, SCOPE_PLOT_H) == 0);
    for (unsigned c = 1; c < 4096; c++)
        assert(scope_code_to_row((uint16_t)c, SCOPE_PLOT_H) <= scope_code_to_row((uint16_t)(c - 1), SCOPE_PLOT_H));
    uint16_t col[SCOPE_PLOT_H];
    scope_bin b = {1000, 3000};
    scope_render_column(&b, SCOPE_PLOT_H, 0xFFFF, col);
    unsigned lit = 0;
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++) lit += col[r] == 0xFFFF;
    assert(lit == (unsigned)(scope_code_to_row(1000, SCOPE_PLOT_H) - scope_code_to_row(3000, SCOPE_PLOT_H) + 1));
    scope_render_column(NULL, SCOPE_PLOT_H, 0xFFFF, col);
    for (unsigned r = 0; r < SCOPE_PLOT_H; r++) assert(col[r] != 0xFFFF);
    assert(scope_render_level(0, 10000) == 0);    /* 2 ms = 20 samples over 192 columns */
    assert(scope_render_level(4095, 10000) == 8); /* 8.192 s = 81920 samples: 256/column */
}

static scope_history H[SCOPE_CHANNELS];

static void test_renderer(void) {
    rig_reset();
    lcd_init_panel(&bus);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        scope_history_init(&H[ch]);
        for (unsigned i = 0; i < 100; i++) scope_history_push(&H[ch], (uint16_t)(400u * ch + 10u));
    }
    scope_render_input in = {.hist = H, .samples_per_s = 10000, .hold = false, .link = false};
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) { in.time_code[ch] = 0; in.range[ch] = (int8_t)(ch % 3u); }
    in.range[9] = -1;
    scope_render_state s;
    scope_render_init(&s);
    rect_calls = rect_max_pixels = 0;
    unsigned guard = 0;
    while (s.passes == 0 && guard++ < 10000) scope_render_step(&s, &in, 4);
    assert(s.passes == 1 && s.rects_failed == 0 && s.rects_sent == rect_calls);
    assert(rect_max_pixels <= SCOPE_RENDER_FILL_MAX && rect_max_pixels >= SCOPE_PLOT_H);
    assert(R.br.cs_release_strobes == 0);
    for (unsigned ch = 0; ch < SCOPE_CHANNELS; ch++) {
        scope_rect p = scope_pane_plot_rect(ch);
        uint16_t colour = scope_channel_colour(ch);
        uint16_t row = scope_code_to_row((uint16_t)(400u * ch + 10u), SCOPE_PLOT_H);
        /* level 0 holds 100 bins, right-aligned: columns 92..191 carry the trace */
        assert(gram[p.y + row][p.x + SCOPE_PLOT_W - 1u] == colour);
        assert(gram[p.y + row][p.x + SCOPE_PLOT_W - 100u] == colour);
        assert(gram[p.y + row][p.x + SCOPE_PLOT_W - 101u] != colour);
        scope_rect tag = scope_pane_tag_rect(ch);
        assert(gram[tag.y][tag.x] == colour);
        scope_rect st = scope_pane_status_rect(ch);
        for (unsigned i = 0; i < 3; i++) {
            uint16_t box = gram[st.y + 4u][st.x + 4u + i * 24u];
            assert(box == (in.range[ch] == (int8_t)i ? colour : SCOPE_COLOUR_DIM));
        }
        assert(gram[st.y + 34u][st.x + 4u] == SCOPE_COLOUR_DIM && gram[st.y + 34u][st.x + 16u] == SCOPE_COLOUR_DIM);
        assert(gram[scope_pane_separator_rect(ch).y][0] == SCOPE_COLOUR_SEPARATOR);
    }

    /* HOLD: plots frozen (no plot-area transfers), status still updates and shows HOLD. */
    in.hold = true;
    plot_calls = 0;
    unsigned start = s.passes;
    while (s.passes == start) scope_render_step(&s, &in, 4);
    assert(plot_calls == 0);
    scope_rect st0 = scope_pane_status_rect(0);
    assert(gram[st0.y + 34u][st0.x + 16u] == SCOPE_COLOUR_HOLD);

    /* LINK: every pane takes CH1's TIME window (and TIME bar). */
    in.hold = false;
    in.link = true;
    in.time_code[0] = 4095;
    in.time_code[5] = 0;
    start = s.passes;
    while (s.passes == start) scope_render_step(&s, &in, 4);
    scope_rect st5 = scope_pane_status_rect(5);
    assert(gram[st5.y + 22u][st5.x + 4u + 99u] == scope_channel_colour(5)); /* full bar from CH1 */
    assert(gram[st5.y + 34u][st5.x + 4u] == SCOPE_COLOUR_LINK);

    /* A failing backend is counted, never reported as drawn. */
    fake_ready = false;
    uint32_t failed = s.rects_failed;
    scope_render_step(&s, &in, 4);
    assert(s.rects_failed > failed);
    fake_ready = true;
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
    test_renderer();
    test_buttons();
    puts("LCD bridge framing, clipping, pane layout and renderer host tests passed (models only; G06 OPEN)");
    return 0;
}
