/* P0 diagnostic only. NOT the final monitor firmware.
 * LCD is deliberately held dark/unselected until G01/G06 are resolved.
 * Polling is rate-limited and outputs serial readings; it does not claim 10 kS/s/channel.
 * Pico SDK target compilation was not possible in the delivery environment.
 */
#include "pico/stdlib.h"
#include "hardware/adc.h"
#include "scope_core.h"
#include <stdio.h>
#define ADDR_MASK (0x0fu << 2)
static void out(unsigned pin,bool high){gpio_init(pin);gpio_set_dir(pin,GPIO_OUT);gpio_put(pin,high);}
static void select_channel(unsigned n){
    gpio_put(7,1); gpio_put_masked(ADDR_MASK,(n&15u)<<2); sleep_us(2); gpio_put(7,0); sleep_us(10);
}
static uint16_t sample(unsigned adc_channel){
    adc_select_input(adc_channel); (void)adc_read(); sleep_us(2); return adc_read();
}
int main(void){
    out(7,true); /* disable all muxes before changing addresses */
    for(unsigned p=2;p<=5;p++)out(p,false);
    out(9,true);out(16,true);out(22,true);out(13,false);out(15,false);out(14,false);
    for(unsigned p=0;p<=1;p++){gpio_init(p);gpio_set_dir(p,GPIO_IN);gpio_pull_up(p);}
    stdio_init_all(); adc_init(); for(unsigned p=26;p<=28;p++)adc_gpio_init(p);
    sleep_ms(1500);
    puts("P0 DIAGNOSTIC ONLY / LCD OFF / UNCALIBRATED / no fault-voltage testing authorized");
    puts("elapsed_us,channel,signal_code,time_code,range_code,hold_pressed,link_pressed");
    for(;;){
        for(unsigned n=0;n<10;n++){
            select_channel(n); gpio_put(14,true);
            uint16_t sig=sample(0),tim=sample(1),rng=sample(2);
            gpio_put(14,false);gpio_put(7,true);
            printf("%llu,%u,%u,%u,%u,%u,%u\n",(unsigned long long)time_us_64(),n+1,sig,tim,rng,!gpio_get(0),!gpio_get(1));
            sleep_ms(10);
        }
    }
}
