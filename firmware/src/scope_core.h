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
/* TIME window mapping, independent of storage level. A pane always spans the requested
 * window W = round(scope_time_seconds(code) x samples_per_s) samples, clamped to
 * [1, SCOPE_WINDOW_MAX_SAMPLES]. It is drawn from the smallest level L with
 * SCOPE_HISTORY_BINS x 2^L >= W, so no level beyond the existing ten is needed.
 * Samples younger than one complete level-L bin (the lower levels' pending halves, `lag`)
 * are not yet displayable. The pane takes n = ceil((W - lag) / 2^L) newest bins, so the
 * represented interval, in samples before the newest pushed sample, is [lag, lag + n x 2^L):
 * tolerance: 0 <= lag < 2^L and W <= lag + n x 2^L < W + 2^L, i.e. each edge is within one
 * coarse bin (2^L samples; 512 = 51.2 ms at level 9 and 10 kS/s) of the requested [0, W).
 * Columns merge (bins > width) or repeat (bins < width) bins; merging keeps min/max, so
 * extrema anywhere in the interval stay visible. The time axis always spans the whole
 * interval: with partial history the held bins sit right-aligned (newest at the right) and
 * the columns before first_col, which hold no retained sample, are left untouched (blank). */
#define SCOPE_WINDOW_MAX_SAMPLES ((uint32_t)SCOPE_HISTORY_BINS << (SCOPE_HISTORY_LEVELS - 1))
typedef struct {
    uint32_t window;    /* requested samples after clamping */
    uint32_t lag;       /* newest samples not yet in a complete level bin */
    uint16_t bins;      /* n: level bins the pane spans, oldest at column 0 */
    uint16_t avail;     /* of those, the newest ones held in history */
    uint16_t first_col; /* columns [0, first_col) hold no data */
    uint8_t level;
} scope_window;
uint32_t scope_window_samples(uint16_t time_code, uint32_t samples_per_s);
unsigned scope_window_level(uint32_t window_samples);
/* Fills out_cols[first_col .. width-1] and returns the plan; with no history every column is blank. */
scope_window scope_window_map(const scope_history *h, uint32_t window_samples, unsigned width, scope_bin *out_cols);
#endif
