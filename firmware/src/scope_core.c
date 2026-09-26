#include "scope_core.h"
#include <math.h>
#include <string.h>
float scope_code_to_volts(uint16_t code, scope_calibration cal) {
    return ((float)(code > 4095 ? 4095 : code) - cal.zero_code) * cal.volts_per_code;
}
scope_calibration scope_calibration_nominal(void) {
    return (scope_calibration){SCOPE_NOMINAL_VOLTS_PER_CODE, SCOPE_NOMINAL_ZERO_CODE, false};
}
bool scope_calibration_valid(scope_calibration c) {
    return c.calibrated && isfinite(c.volts_per_code) && isfinite(c.zero_code)
        && c.volts_per_code > 0 && c.volts_per_code < 1;
}
scope_calibration scope_calibration_effective(scope_calibration c) {
    return scope_calibration_valid(c) ? c : scope_calibration_nominal();
}
bool scope_calibrate(float c0, float v0, float c1, float v1, scope_calibration *out) {
    if (!out || !isfinite(c0) || !isfinite(c1) || !isfinite(v0) || !isfinite(v1)
        || c0 < 0 || c1 > 4095 || c1-c0 < 100 || v1 <= v0) return false;
    float slope = (v1-v0)/(c1-c0);
    if (!(slope > 0 && slope < 1)) return false;
    *out = (scope_calibration){slope, c0-v0/slope, true};
    return true;
}
float scope_time_seconds(uint16_t code) {
    if (code > 4095) code=4095;
    return 0.002f * expf(logf(4096.0f)*(float)code/4095.0f);
}
int scope_range_decode(uint16_t c) {
    if (c < 900) return 0;
    if (c >= 1350 && c <= 2650) return 1;
    if (c > 3200 && c <= 4095) return 2;
    return -1;
}
int scope_range_update(scope_range_state *s, uint16_t code, uint32_t now) {
    if (!s) return -1;
    int r=scope_range_decode(code);
    if (r < 0) { s->candidate=-1; return s->stable; }
    if (r != s->candidate) { s->candidate=r; s->since_ms=now; }
    else if ((uint32_t)(now-s->since_ms) >= 20) s->stable=r;
    return s->stable;
}
void scope_history_init(scope_history *h) { if (h) memset(h,0,sizeof(*h)); }
void scope_history_push(scope_history *h, uint16_t value) {
    if (!h) return;
    scope_bin b={value,value};
    for (unsigned i=0;i<SCOPE_HISTORY_LEVELS;i++) {
        scope_history_level *l=&h->level[i];
        l->bins[l->head]=b; l->head=(uint16_t)((l->head+1)%SCOPE_HISTORY_BINS);
        if (l->count<SCOPE_HISTORY_BINS) l->count++;
        if (!l->has_pending) { l->pending=b; l->has_pending=true; break; }
        b.lo=b.lo<l->pending.lo?b.lo:l->pending.lo;
        b.hi=b.hi>l->pending.hi?b.hi:l->pending.hi;
        l->has_pending=false;
    }
}
size_t scope_history_recent(const scope_history *h,unsigned idx,scope_bin *out,size_t cap) {
    if (!h || !out || idx>=SCOPE_HISTORY_LEVELS || !cap) return 0;
    const scope_history_level *l=&h->level[idx];
    size_t n=l->count<cap?l->count:cap;
    for (size_t i=0;i<n;i++) out[i]=l->bins[(l->head+SCOPE_HISTORY_BINS-n+i)%SCOPE_HISTORY_BINS];
    return n;
}
uint32_t scope_window_samples(uint16_t code, uint32_t samples_per_s) {
    float w = scope_time_seconds(code) * (float)samples_per_s + 0.5f;
    if (w < 1.0f) return 1;
    if (w >= (float)SCOPE_WINDOW_MAX_SAMPLES) return SCOPE_WINDOW_MAX_SAMPLES;
    return (uint32_t)w;
}
unsigned scope_window_level(uint32_t samples) {
    unsigned i=0;
    while (i+1<SCOPE_HISTORY_LEVELS && ((uint32_t)SCOPE_HISTORY_BINS<<i) < samples) i++;
    return i;
}
scope_window scope_window_map(const scope_history *h, uint32_t window, unsigned width, scope_bin *out) {
    scope_window w={0};
    if (window<1) window=1;
    if (window>SCOPE_WINDOW_MAX_SAMPLES) window=SCOPE_WINDOW_MAX_SAMPLES;
    w.window=window;
    w.level=(uint8_t)scope_window_level(window);
    w.first_col=(uint16_t)width;
    if (!h || !out || !width) return w;
    for (unsigned j=0;j<w.level;j++) if (h->level[j].has_pending) w.lag+=(uint32_t)1<<j;
    uint32_t need=window>w.lag?window-w.lag:1, unit=(uint32_t)1<<w.level;
    uint32_t n=(need+unit-1)>>w.level;
    if (n>SCOPE_HISTORY_BINS) n=SCOPE_HISTORY_BINS;
    const scope_history_level *l=&h->level[w.level];
    uint32_t avail=l->count<n?l->count:n, missing=n-avail;
    w.bins=(uint16_t)n; w.avail=(uint16_t)avail;
    for (unsigned c=0;c<width;c++) {
        uint32_t a=(uint32_t)c*n/width, b=(uint32_t)(c+1)*n/width;
        if (b<=a) b=a+1;
        if (a<missing) a=missing;
        if (a>=b) continue;
        if (c<w.first_col) w.first_col=(uint16_t)c;
        scope_bin m={0xFFFF,0};
        for (uint32_t i=a;i<b;i++) {
            scope_bin v=l->bins[(l->head+SCOPE_HISTORY_BINS-n+i)%SCOPE_HISTORY_BINS];
            if (v.lo<m.lo) m.lo=v.lo;
            if (v.hi>m.hi) m.hi=v.hi;
        }
        out[c]=m;
    }
    return w;
}
