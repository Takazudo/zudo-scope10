#ifndef SCOPE_CORE_H
#define SCOPE_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define SCOPE_CHANNELS 10
#define SCOPE_HISTORY_LEVELS 10
#define SCOPE_HISTORY_BINS 192
/* Each history level doubles the sample span, preserving both extremes. */
typedef struct { uint16_t lo, hi; } scope_bin;
typedef struct {
    scope_bin bins[SCOPE_HISTORY_BINS];
    scope_bin pending;
    uint16_t head, count;
    bool has_pending;
} scope_history_level;
typedef struct { scope_history_level level[SCOPE_HISTORY_LEVELS]; } scope_history;
typedef struct { float volts_per_code, zero_code; bool calibrated; } scope_calibration;
typedef struct { int stable, candidate; uint32_t since_ms; } scope_range_state;
float scope_code_to_volts(uint16_t code, scope_calibration cal);
bool scope_calibrate(float code_lo, float volts_lo, float code_hi, float volts_hi, scope_calibration *out);
float scope_time_seconds(uint16_t code);
int scope_range_decode(uint16_t code); /* Returns 0/1/2 for +/-3/5/8 V; -1 in deadband. */
int scope_range_update(scope_range_state *s, uint16_t code, uint32_t now_ms);
void scope_history_init(scope_history *h);
void scope_history_push(scope_history *h, uint16_t code);
size_t scope_history_recent(const scope_history *h, unsigned level, scope_bin *out, size_t capacity);
unsigned scope_history_level_for_window(uint32_t window_samples, unsigned width);
#endif
