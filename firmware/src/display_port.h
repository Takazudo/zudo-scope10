#ifndef SCOPE_DISPLAY_PORT_H
#define SCOPE_DISPLAY_PORT_H
#include <stdbool.h>
#include <stdint.h>
/* Contract for the NOT YET INTEGRATED Waveshare SKU19907 backend.
 * RGB565 host values, portrait coordinates 320x480.
 * Caller supplies one small rectangle; backend may copy but must never retain pointer.
 * Serialize 16-bit bridge words as documented by the exact module's vendor driver.
 * No generic native-ILI9488 RGB666 assumptions.
 * This header is intentionally declarations only: linking a renderer without a real
 * backend MUST fail, instead of silently showing a fabricated success.
 */
bool scope_display_init(void);
bool scope_display_rect(uint16_t x,uint16_t y,uint16_t w,uint16_t h,const uint16_t *rgb565);
void scope_display_backlight(uint8_t percent);
#endif
