#include "scope_core.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static scope_history hist;
int main(void) {
    scope_calibration cal={0};
    assert(scope_calibrate(620, -10, 3100, 10, &cal));
    assert(fabsf(scope_code_to_volts(1860,cal)) < .0001f);
    assert(fabsf(scope_code_to_volts(620,cal)+10) < .0001f);
    assert(!scope_calibrate(1,0,1,5,&cal));
    assert(!scope_calibrate(NAN,0,3000,5,&cal));
    assert(fabsf(scope_time_seconds(0)-.002f)<.000001f);
    assert(fabsf(scope_time_seconds(4095)-8.192f)<.00001f);
    float prev=0;
    for(unsigned i=0;i<4096;i++){ float t=scope_time_seconds((uint16_t)i); assert(t>prev); prev=t; }
    assert(scope_range_decode(0)==0 && scope_range_decode(2048)==1 && scope_range_decode(4095)==2);
    assert(scope_range_decode(1100)==-1 && scope_range_decode(3000)==-1);
    scope_range_state range={-1,-1,0};
    assert(scope_range_update(&range,2048,10)==-1);
    assert(scope_range_update(&range,2048,29)==-1);
    assert(scope_range_update(&range,2048,30)==1);
    assert(scope_range_update(&range,1100,31)==1);
    assert(scope_range_update(&range,4095,40)==1);
    assert(scope_range_update(&range,4095,60)==2);
    range=(scope_range_state){0,2,UINT32_MAX-10};
    assert(scope_range_update(&range,4095,20)==2);
    scope_history_init(&hist); scope_bin b[192];
    for(unsigned i=0;i<4096;i++) scope_history_push(&hist,(uint16_t)i);
    assert(scope_history_recent(&hist,0,b,192)==192); assert(b[191].lo==4095);
    assert(scope_history_recent(&hist,1,b,192)==192); assert(b[191].lo==4094 && b[191].hi==4095);
    assert(scope_history_recent(&hist,9,b,192)==8); assert(b[7].lo==3584 && b[7].hi==4095);
    assert(scope_history_level_for_window(81920,144)==9);
    assert(scope_history_level_for_window(20,144)==0);
    assert(scope_history_recent(&hist,99,b,192)==0);
    assert(sizeof(scope_history)*10 < 100000);
    printf("PASS: calibration, 4096 time points, range/debounce/wrap, multiresolution extremes.\n");
    printf("Ten-channel history allocation: %zu bytes.\n",sizeof(scope_history)*10);
    return 0;
}
