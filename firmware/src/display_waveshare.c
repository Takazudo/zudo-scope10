/* display_port.h backend for the Waveshare Pico-ResTouch-LCD-3.5 (SKU 19907) on SPI1.
 * Built into scope10_acq only when SCOPE_ENABLE_LCD=1 (default off until G01 closes).
 * Framing, init table and clipping are portable and host-tested (lcd_bridge.c); this file
 * is only the RP2040 bus. The bridge is write-only, so success here means "the sequence was
 * transmitted", never "a panel answered": a blank screen is not by itself a firmware fault.
 * Design and bench checklist: firmware/LCD-BACKEND.md. G06 stays OPEN. */
#if !defined(SCOPE_ENABLE_LCD) || !SCOPE_ENABLE_LCD
#error "display_waveshare.c is only built with SCOPE_ENABLE_LCD=1"
#endif
#include "display_port.h"
#include "lcd_bridge.h"
#include "lcd_safe_pins.h"
#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"

#ifndef SCOPE_LCD_SPI_HZ
/* Conservative: the vendor wiki reports 60 MHz tested; 74HC counter/shift timing at 3.3 V
 * on this module is not characterised here. Raise only after the G06 bench check. */
#define SCOPE_LCD_SPI_HZ 15000000u
#endif

#define LCD_SPI spi1

static bool ready;

static void bus_frame_begin(void *ctx, bool data) {
    (void)ctx;
    gpio_put(LCD_PIN_DC, data); /* D/C only changes while CS is high */
    gpio_put(LCD_PIN_CS, false);
}
static void bus_write(void *ctx, const uint8_t *bytes, size_t n) {
    (void)ctx;
    spi_write_blocking(LCD_SPI, bytes, n); /* returns after the last bit has shifted out */
}
static void bus_frame_end(void *ctx) {
    (void)ctx;
    gpio_put(LCD_PIN_CS, true);
}
static void bus_reset(void *ctx, bool asserted) {
    (void)ctx;
    gpio_put(LCD_PIN_RST, !asserted);
}
static void bus_delay_ms(void *ctx, uint32_t ms) {
    (void)ctx;
    sleep_ms(ms);
}

static const lcd_bus bus = {NULL, bus_frame_begin, bus_write, bus_frame_end, bus_reset, bus_delay_ms};

bool scope_display_init(void) {
    lcd_safe_pins_apply(); /* backlight off (GP13 high, #41), all SPI1 slaves deselected, panel in reset */
    gpio_init(LCD_PIN_DC);
    gpio_set_dir(LCD_PIN_DC, GPIO_OUT);
    gpio_put(LCD_PIN_DC, true);
    spi_init(LCD_SPI, SCOPE_LCD_SPI_HZ);
    spi_set_format(LCD_SPI, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST); /* 4094 shifts on SCLK rise */
    gpio_set_function(LCD_PIN_SCK, GPIO_FUNC_SPI);
    gpio_set_function(LCD_PIN_MOSI, GPIO_FUNC_SPI);
    /* MISO (GP12) is left unassigned: nothing is read back through this bridge. */
    lcd_init_panel(&bus);
    ready = lcd_fill(&bus, 0, 0, SCOPE_DISPLAY_WIDTH, SCOPE_DISPLAY_HEIGHT, 0x0000u);
    return ready;
}

bool scope_display_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *rgb565) {
    return ready && lcd_blit(&bus, x, y, w, h, rgb565);
}

void scope_display_backlight(uint8_t percent) {
    /* On/off only: the module's backlight regulator (CAT1) is unidentified, so PWM dimming
     * on its EN pin is not assumed (any later PWM would be inverted too). Polarity is
     * inverted by the Q1 open-drain stage (#41, lcd_safe_pins.h): GP13 low = backlight ON,
     * GP13 high = OFF. GP13 stays driven; releasing it would also mean ON (R88 -> Q1 off). */
    gpio_put(LCD_PIN_BL, (ready && percent > 0u) ? LCD_BL_LEVEL_ON : LCD_BL_LEVEL_OFF);
}
