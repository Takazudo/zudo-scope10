#ifndef LCD_SAFE_PINS_H
#define LCD_SAFE_PINS_H
/* Waveshare Pico-ResTouch-LCD-3.5 control pins on SPI1 (design/gpio.json; the vendor
 * DEV_Config.h uses the same numbers) and the "LCD dark, all slaves deselected" state.
 *
 * GP13 LCD_BL must always be DRIVEN. The module has R16 10k from VSYS (5 V) to LCD_BL, the
 * backlight regulator's EN (design/evidence/g01-display-power.md). Against the carrier's
 * R88 100k pull-down an undriven GP13 settles near 4.5 V: above the RP2040 IOVDD + 0.5 V
 * absolute maximum, and with the backlight ON. lcd_safe_pins.c therefore drives it low from
 * a runtime-init hook right after the SDK's early peripheral reset, before clock setup and
 * main(). Reset and the boot ROM/boot2 window before that hook cannot be covered by firmware. */
#define LCD_PIN_DC 8u
#define LCD_PIN_CS 9u
#define LCD_PIN_SCK 10u
#define LCD_PIN_MOSI 11u
#define LCD_PIN_BL 13u
#define LCD_PIN_RST 15u
#define LCD_PIN_TP_CS 16u
#define LCD_PIN_SD_CS 22u

/* BL low, LCD/touch/SD chip selects high, panel held in reset. Glitch-free, idempotent. */
void lcd_safe_pins_apply(void);
#endif
