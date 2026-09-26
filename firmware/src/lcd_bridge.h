#ifndef LCD_BRIDGE_H
#define LCD_BRIDGE_H
/* Portable framing for the Waveshare Pico-ResTouch-LCD-3.5 (SKU 19907) SPI-to-16-bit
 * bridge in front of its ILI9488. No RP2040 headers: display_waveshare.c supplies the bus.
 * Clean-room: written from the ILI9488 datasheet V1.00 and the module schematic; the
 * vendor example code (no licence) is cited as a reference only. See firmware/LCD-BACKEND.md.
 *
 * Bridge (module schematic p1 "LCD SPI ->16BIT"): U1 74HC4040 counts SCLK falling edges and
 * is held reset while LCD_CS is high; its Q3 is CLK/16. U2/U3 74HC4094 shift MOSI on SCLK
 * rising edges (U2 QS1 -> U3 DATA) and latch while CLK/16 is high; LCD_CLK (panel WRX) is
 * CLK/16 inverted by U4. So every 16 clocks with CS low emit one 16-bit bus write, the first
 * bit sent landing on D15, with D/CX as set before CS fell.
 *
 * Framing used here: EVERY bus write is a whole 16-bit word, MSB first, so the WRX rising
 * edge happens on the 16th clock while CS is still low. Commands go out as 0x00cc (the panel
 * reads commands and parameters on D7..D0, D15..D8 are "don't care"), parameters as 0x00pp,
 * pixels as one RGB565 word each (COLMOD DBI = 101, 16 bit/pixel on the 16-bit bus).
 * The vendor C driver sends commands as a single byte; on this bridge that write is only
 * strobed by CS going high, i.e. at the same instant the panel's CSX deasserts. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define LCD_WIDTH 320u  /* portrait */
#define LCD_HEIGHT 480u
#define LCD_CHUNK_PIXELS 32u /* bytes staged per bus write call = 2 * this */

#define LCD_CMD_SLPOUT 0x11u
#define LCD_CMD_INVON 0x21u
#define LCD_CMD_DISPON 0x29u
#define LCD_CMD_CASET 0x2Au
#define LCD_CMD_PASET 0x2Bu
#define LCD_CMD_RAMWR 0x2Cu
#define LCD_CMD_MADCTL 0x36u
#define LCD_CMD_COLMOD 0x3Au
#define LCD_CMD_DISCTRL 0xB6u
#define LCD_COLMOD_16BPP 0x55u /* DPI[2:0] = DBI[2:0] = 101: 16 bits/pixel */

typedef struct {
    void *ctx;
    void (*frame_begin)(void *ctx, bool data); /* drive D/C (data -> high), then CS low */
    void (*write)(void *ctx, const uint8_t *bytes, size_t n); /* MSB-first, blocking */
    void (*frame_end)(void *ctx);              /* wait for the last bit, then CS high */
    void (*reset)(void *ctx, bool asserted);   /* panel RESX: asserted = driven low */
    void (*delay_ms)(void *ctx, uint32_t ms);
} lcd_bus;

typedef struct {
    uint8_t cmd;
    uint8_t n;          /* parameter count */
    uint8_t param[15];
    uint16_t delay_ms;  /* wait after the command */
} lcd_init_step;

/* Coordinates are unsigned, so clipping only trims the right and bottom edges. */
typedef struct { uint16_t x, y, w, h; } lcd_clip_rect;

extern const lcd_init_step lcd_init_table[];
extern const size_t lcd_init_table_len;

void lcd_word_bytes(uint16_t word, uint8_t out[2]);
void lcd_command(const lcd_bus *b, uint8_t cmd, const uint8_t *params, size_t n);
void lcd_init_panel(const lcd_bus *b);
/* Clip (x, y, w, h) against LCD_WIDTH x LCD_HEIGHT. False when nothing is visible. */
bool lcd_clip(uint16_t x, uint16_t y, uint16_t w, uint16_t h, lcd_clip_rect *out);
void lcd_set_window(const lcd_bus *b, uint16_t x, uint16_t y, uint16_t w, uint16_t h);
/* Row-major w*h RGB565 source; the visible part is streamed in one RAMWR data frame. */
bool lcd_blit(const lcd_bus *b, uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *px);
bool lcd_fill(const lcd_bus *b, uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t rgb565);
#endif
