#!/usr/bin/env python3
"""Nominal calculations and explicit corner checks, NOT measured hardware."""
from pathlib import Path
import json, math, itertools, csv
import power_budget
R=Path(__file__).resolve().parents[1]
x=json.loads((R/'design/requirements.json').read_text())['input']
ri=x['r_input'];rb=x['r_to_ref'];rg=x['r_to_gnd'];vr=x['reference_v']
def tf(a,b,c,vref):
 g=1/a+1/b+1/c
 return (1/a)/g, (vref/b)/g,1/g
slope,zero,rth=tf(ri,rb,rg,vr)
f1=1/(2*math.pi*rth*x['filter1_c_f']);f2=1/(2*math.pi*x['filter2_r_ohm']*x['filter2_c_f'])
def response(f):return 1/math.sqrt((1+(f/f1)**2)*(1+(f/f2)**2))
corner=[]
for sa,sb,sc,sv in itertools.product([-1,1],repeat=4):
 a,b,c,v=ri*(1+sa*.001),rb*(1+sb*.001),rg*(1+sc*.001),vr*(1+sv*.0015)
 m,q,_=tf(a,b,c,v)
 corner.append({'slope':m,'zero':q,'minus12':q-12*m,'plus12':q+12*m})
# Input current direction is important: the level shift injects a small bias into the source.
open_v_adc=(vr/rb)/(1/rb+1/rg)
open_apparent=(open_v_adc-zero)/slope
report={'basis':'Analytical ideal resistors/buffers. No vendor SPICE, no tolerances for op amp/ADC/diode/PCB included unless explicitly stated.','gain_v_per_v':slope,'zero_input_adc_v':zero,'thevenin_ohm':rth,'small_signal_input_impedance_ohm':ri+1/(1/rb+1/rg),'shorted_input_bias_current_uA':zero/ri*1e6,'adc_volts_at_input':{str(v):zero+slope*v for v in [-12,-8,-5,-3,0,3,5,8,12]},'input_referred_ideal_adc_lsb_mV':3.3/4096/slope*1000,'adc_zero_code_ideal':zero/3.3*4095,'open_input_adc_v':open_v_adc,'open_input_apparent_volts':open_apparent,'filter_poles_hz':[f1,f2],'filter_amplitude':{str(f):{'ratio':response(f),'dB':20*math.log10(response(f))} for f in [20,100,500,1000,2000,5000,10000,20000]},'corner_assumptions':{'divider_R_fraction':.001,'reference_fraction':.0015,'other_error_sources':'EXCLUDED'},'corner_results':{'min_voltage_minus12':min(t['minus12'] for t in corner),'max_voltage_plus12':max(t['plus12'] for t in corner),'gain_min':min(t['slope'] for t in corner),'gain_max':max(t['slope'] for t in corner)},'ideal_positive_fault_current_upper_bound_uA_at_24V':24/ri*1e6,'ten_channel_unpowered_injection_bound_uA':10*24/ri*1e6,'one_k_bleed_ideal_rail_bound_V':10*24/ri*1000,'fault_note':'Conservative resistor current bound only; not an ESD, negative-voltage, current-path or latch-up proof. Do not claim ±24V rated immunity.','acquisition':{'nominal_samples_per_channel_s':10000,'sample_period_per_channel_us':100,'maximum_sequential_channel_skew_us':72,'nyquist_hz':5000,'ideal_spi_full_frame_ms_at8MHz':320*480*16/8e6*1000,'ideal_spi_full_frame_ms_at24MHz':320*480*16/24e6*1000,'note':'SPI times exclude framing/commands. Full RGB565 framebuffer is 307200B, larger than RP2040 264kB SRAM; stream small tiles, never allocate full frame.'}}
(R/'reports/analog-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
with (R/'reports/filter-response.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['Hz','gain','dB','source'])
 for k in range(181):
  hz=10**(k/45);g=response(hz);w.writerow([hz,g,20*math.log10(g),'CALCULATED_IDEAL_NOT_MEASURED'])
print(json.dumps({k:report[k] for k in ['gain_v_per_v','zero_input_adc_v','small_signal_input_impedance_ohm','open_input_apparent_volts','filter_poles_hz','corner_results']},indent=2))
power_budget.main()  # writes reports/power-budget.json; G07 calculation-only, see that report
