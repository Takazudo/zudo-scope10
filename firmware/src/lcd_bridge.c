#include "lcd_bridge.h"

#ifndef LCD_VENDOR_PANEL_TUNING
#define LCD_VENDOR_PANEL_TUNING 1
#endif

/* Datasheet references are ILI9488 datasheet V1.00 (2012-11-28) section numbers. */
const lcd_init_step lcd_init_table[] = {
    /* 5.2.13: wait >= 5 ms after SLPOUT; 120 ms leaves the charge pumps time to settle. */
    {LCD_CMD_SLPOUT, 0, {0}, 120},
    {LCD_CMD_COLMOD, 1, {LCD_COLMOD_16BPP}, 0},            /* 5.2.34 */
    /* 5.2.30 MADCTL: MY=MX=MV=0 (portrait 320 x 480), BGR=1. 5.3.7 DISCTRL: PT default,
     * SS=1 (source S960 -> S1), ISC=2, NL=0x3B (480 lines). BGR=1 with SS=1 is the
     * portrait scan this module's vendor example selects; colour order is a bench check. */
    {LCD_CMD_MADCTL, 1, {0x08}, 0},
    {LCD_CMD_DISCTRL, 3, {0x02, 0x22, 0x3B}, 0},
    {LCD_CMD_INVON, 0, {0}, 0}, /* this glass needs inversion on (vendor example does the same) */
#if LCD_VENDOR_PANEL_TUNING
    /* Panel-specific analogue values (power control 3, VCOM, frame rate, gamma) cannot be
     * derived from the IC datasheet; these numbers are the ones the vendor example programs
     * for this module (LCD_Driver.c, 3.5-inch branch). Reviewer decision, LCD-BACKEND.md. */
    {0xC2, 1, {0x33}, 0},
    {0xC5, 3, {0x00, 0x1E, 0x80}, 0},
    {0xB1, 1, {0xB0}, 0},
    {0xE0, 15, {0x00, 0x13, 0x18, 0x04, 0x0F, 0x06, 0x3A, 0x56, 0x4D, 0x03, 0x0A, 0x06, 0x30, 0x3E, 0x0F}, 0},
    {0xE1, 15, {0x00, 0x13, 0x18, 0x01, 0x11, 0x06, 0x38, 0x34, 0x4D, 0x06, 0x0D, 0x0B, 0x31, 0x37, 0x0F}, 0},
#endif
    {LCD_CMD_DISPON, 0, {0}, 20},
};
const size_t lcd_init_table_len = sizeof lcd_init_table / sizeof lcd_init_table[0];

void lcd_word_bytes(uint16_t word, uint8_t out[2]) {
    out[0] = (uint8_t)(word >> 8);
    out[1] = (uint8_t)word;
}

static void write_words8(const lcd_bus *b, const uint8_t *v, size_t n) {
    uint8_t buf[2u * 16u];
    while (n) {
        size_t k = n < 16u ? n : 16u;
        for (size_t i = 0; i < k; i++) lcd_word_bytes(v[i], &buf[2u * i]);
        b->write(b->ctx, buf, 2u * k);
        v += k;
        n -= k;
    }
}

void lcd_command(const lcd_bus *b, uint8_t cmd, const uint8_t *params, size_t n) {
    b->frame_begin(b->ctx, false);
    write_words8(b, &cmd, 1u);
    b->frame_end(b->ctx);
    if (!n) return;
    b->frame_begin(b->ctx, true);
    write_words8(b, params, n);
    b->frame_end(b->ctx);
}

void lcd_init_panel(const lcd_bus *b) {
    /* 13.4 Reset timing: RESX low >= 10 us; up to 120 ms before commands are accepted. */
    b->reset(b->ctx, true);
    b->delay_ms(b->ctx, 1u);
    b->reset(b->ctx, false);
    b->delay_ms(b->ctx, 120u);
    for (size_t i = 0; i < lcd_init_table_len; i++) {
        const lcd_init_step *s = &lcd_init_table[i];
        lcd_command(b, s->cmd, s->param, s->n);
        if (s->delay_ms) b->delay_ms(b->ctx, s->delay_ms);
    }
}

bool lcd_clip(uint16_t x, uint16_t y, uint16_t w, uint16_t h, lcd_clip_rect *out) {
    if (!out || !w || !h || x >= LCD_WIDTH || y >= LCD_HEIGHT) return false;
    uint32_t x1 = (uint32_t)x + w, y1 = (uint32_t)y + h;
    if (x1 > LCD_WIDTH) x1 = LCD_WIDTH;
    if (y1 > LCD_HEIGHT) y1 = LCD_HEIGHT;
    *out = (lcd_clip_rect){x, y, (uint16_t)(x1 - x), (uint16_t)(y1 - y)};
    return true;
}

void lcd_set_window(const lcd_bus *b, uint16_t x, uint16_t y, uint16_t w, uint16_t h) {
    if (!w || !h) return;
    uint16_t x1 = (uint16_t)(x + w - 1u), y1 = (uint16_t)(y + h - 1u);
    const uint8_t col[4] = {(uint8_t)(x >> 8), (uint8_t)x, (uint8_t)(x1 >> 8), (uint8_t)x1};
    const uint8_t row[4] = {(uint8_t)(y >> 8), (uint8_t)y, (uint8_t)(y1 >> 8), (uint8_t)y1};
    lcd_command(b, LCD_CMD_CASET, col, 4u);
    lcd_command(b, LCD_CMD_PASET, row, 4u);
}

static void stream(const lcd_bus *b, const uint16_t *px, size_t n, uint16_t fill) {
    uint8_t buf[2u * LCD_CHUNK_PIXELS];
    while (n) {
        size_t k = n < LCD_CHUNK_PIXELS ? n : LCD_CHUNK_PIXELS;
        for (size_t i = 0; i < k; i++) lcd_word_bytes(px ? px[i] : fill, &buf[2u * i]);
        b->write(b->ctx, buf, 2u * k);
        if (px) px += k;
        n -= k;
    }
}

static bool rect_write(const lcd_bus *b, uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                       const uint16_t *px, uint16_t fill) {
    lcd_clip_rect c;
    if (!b || !lcd_clip(x, y, w, h, &c)) return false;
    lcd_set_window(b, c.x, c.y, c.w, c.h);
    lcd_command(b, LCD_CMD_RAMWR, NULL, 0u);
    b->frame_begin(b->ctx, true);
    for (uint16_t r = 0; r < c.h; r++)
        stream(b, px ? px + (size_t)r * w : NULL, c.w, fill); /* source stride stays w */
    b->frame_end(b->ctx);
    return true;
}

bool lcd_blit(const lcd_bus *b, uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *px) {
    return px && rect_write(b, x, y, w, h, px, 0u);
}

bool lcd_fill(const lcd_bus *b, uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t rgb565) {
    return rect_write(b, x, y, w, h, NULL, rgb565);
}
