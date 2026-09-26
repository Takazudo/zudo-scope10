#!/usr/bin/env python3
"""Two-point channel calibration; no external packages.
Input CSV: channel,volts,mean_code. Exactly two rows/channel for all ten channels.
Record actual measured fixture voltage, NOT assumed nominal settings.
"""
import argparse,csv,json,math
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('csv');p.add_argument('output');a=p.parse_args()
groups={i:[] for i in range(1,11)}
for row in csv.DictReader(Path(a.csv).open(newline='')):
 ch=int(row['channel']);v=float(row['volts']);c=float(row['mean_code'])
 if ch not in groups or not all(map(math.isfinite,(v,c))) or not 0<=c<=4095:raise SystemExit('Invalid input row')
 groups[ch].append((c,v))
out=[]
for ch,pairs in groups.items():
 if len(pairs)!=2:raise SystemExit(f'Channel {ch}: exactly two rows required')
 (c0,v0),(c1,v1)=sorted(pairs)
 if c1-c0<100 or v1<=v0:raise SystemExit(f'Channel {ch}: invalid calibration span')
 m=(v1-v0)/(c1-c0);out.append({'channel':ch,'volts_per_code':m,'zero_code':c0-v0/m,'basis':'measured two-point DC fit'})
Path(a.output).write_text(json.dumps({'schema_version':1,'calibration':out,'note':'Validate intermediate points; this does not correct ADC INL, source impedance, AC bandwidth or noise.'},indent=2)+'\n')
