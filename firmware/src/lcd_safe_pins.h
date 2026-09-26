#ifndef LCD_SAFE_PINS_H
#define LCD_SAFE_PINS_H
/* Waveshare Pico-ResTouch-LCD-3.5 control pins on SPI1 (design/gpio.json; the vendor
 * DEV_Config.h uses the same numbers) and the "LCD dark, all slaves deselected" state.
 *
 * GP13 backlight polarity is INVERTED (#41, design/evidence/backlight-interface.md). The
 * module has R16 10k from VSYS (5 V) to LCD_BL, the backlight regulator's EN. The carrier
 * therefore never ties GP13 to LCD_BL: GP13 -> R64 -> gate of Q1 (N-channel MOSFET, open
 * drain on LCD_BL, R88 100k gate pull-down). GP13 HIGH turns Q1 on and pulls LCD_BL to
 * ~0 V: backlight OFF. GP13 LOW or undriven (reset, boot ROM, before this hook) leaves Q1
 * off and R16 pulls LCD_BL to VSYS: backlight ON. The pad only ever sees its own drive or
 * 0 V through R88, so no state exceeds IOVDD + 0.5 V; the early hook exists to darken the
 * panel quickly, not to protect the pin. */
#define LCD_PIN_DC 8u
#define LCD_PIN_CS 9u
#define LCD_PIN_SCK 10u
#define LCD_PIN_MOSI 11u
#define LCD_PIN_BL 13u
#define LCD_PIN_RST 15u
#define LCD_PIN_TP_CS 16u
#define LCD_PIN_SD_CS 22u

/* Active-low backlight through the Q1 open-drain stage. */
#define LCD_BL_LEVEL_OFF true
#define LCD_BL_LEVEL_ON false

/* Backlight OFF (GP13 high), LCD/touch/SD chip selects high, panel held in reset. Glitch-free, idempotent. */
void lcd_safe_pins_apply(void);
#endif
