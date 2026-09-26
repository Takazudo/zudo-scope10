#include "lcd_safe_pins.h"
#include "hardware/gpio.h"
#include "pico/runtime.h"
#include "pico/runtime_init.h"

static void drive(unsigned pin, bool level) {
    /* Value and direction first, function last: the pin never floats or glitches. */
    gpio_put(pin, level);
    gpio_set_dir(pin, GPIO_OUT);
    gpio_set_function(pin, GPIO_FUNC_SIO);
}

void lcd_safe_pins_apply(void) {
    drive(LCD_PIN_BL, false);
    drive(LCD_PIN_CS, true);
    drive(LCD_PIN_TP_CS, true);
    drive(LCD_PIN_SD_CS, true);
    drive(LCD_PIN_RST, false);
}

/* IO_BANK0/PADS_BANK0 leave reset in runtime_init_early_resets (priority 00100) and are not
 * reset again; clocks come up at 00500. Runs once, on core 0. */
#define LCD_SAFE_PINS_INIT_PRIORITY "00110"
_Static_assert(sizeof(LCD_SAFE_PINS_INIT_PRIORITY) == sizeof(PICO_RUNTIME_INIT_EARLY_RESETS),
               "runtime-init priority strings sort as fixed-width text");
PICO_RUNTIME_INIT_FUNC_HW(lcd_safe_pins_apply, LCD_SAFE_PINS_INIT_PRIORITY);
