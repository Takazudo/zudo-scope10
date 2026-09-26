#!/usr/bin/env python3
"""Original technical/ergonomic drawings. NOT fabrication artwork."""
from pathlib import Path
import math,json
R=Path(__file__).resolve().parents[1];A=R/'doc/public/assets';A.mkdir(parents=True,exist_ok=True)
BG='#ede9de';INK='#183535';MID='#617673';ACC='#be5f3c';GRID='#9baea7'
def text(x,y,s,size=3,fill=INK,anchor='start'):
 return f'<text x="{x}" y="{y}" fill="{fill}" font-family="DejaVu Sans,sans-serif" font-size="{size}" text-anchor="{anchor}">{s}</text>'
s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="250mm" height="180mm" viewBox="0 0 250 180"><rect width="250" height="180" rx="4" fill="{BG}"/><rect x="2" y="2" width="246" height="176" rx="3" fill="none" stroke="{INK}" stroke-width=".35"/>',text(13,16,'ZUDO / SCOPE 10',5.5),text(13,23,'ONE DISPLAY · TEN SIGNALS · P0',2.7),text(237,16,'PRE-LAYOUT',2.7,ACC,'end'),text(237,23,'250 × 180 mm study',2.5,MID,'end')]
for x,y in [(5,5),(245,5),(245,175),(5,175)]:s.append(f'<circle cx="{x}" cy="{y}" r="1.5" fill="{INK}"/>')
# Nominal module envelope, centred active rectangle; centring is unverified.
s.append(f'<rect x="96.4" y="47" width="57.2" height="86" fill="none" stroke="{MID}" stroke-width=".3" stroke-dasharray="1,1"/>')
s.append('<rect x="99.8" y="52.3" width="50.4" height="75" rx="1" fill="#122424"/>')
x0=100.52;y0=53.08;w=24.48;h=14.688
for n in range(10):
 col=n//5;row=n%5;x=x0+col*w;y=y0+row*h
 s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#496562" stroke-width=".2"/>')
 s.append(text(x+1,y+2.8,f'{n+1:02d}  ±5 V',1.8,'#b5cbbb'))
 pts=[]
 for k in range(80):
  xx=x+1+k*(w-2)/79;yy=y+9-2.9*math.sin(k/79*math.tau*(1.4+(n%4)*.7)+n)
  pts.append(f'{xx:.3f},{yy:.3f}')
 s.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#d7e6b8" stroke-width=".3"/>')
for side in [0,1]:
 for row in range(5):
  n=side*5+row+1;y=43+row*23.5;kx=48 if side==0 else 202;rx=77 if side==0 else 173;jx=1.5 if side==0 else 234.5
  s.append(f'<rect x="{jx}" y="{y-3}" width="14" height="6" rx="1" fill="#607570"/>')
  s.append(text(21 if not side else 229,y+1.2,f'{n:02d}',4,INK,'middle'))
  s.append(f'<circle cx="{kx}" cy="{y}" r="8" fill="#1f3838"/><circle cx="{kx}" cy="{y}" r="6.8" fill="none" stroke="#748582" stroke-width=".3"/><line x1="{kx}" y1="{y}" x2="{kx+2}" y2="{y-6}" stroke="#ede9de" stroke-width=".7"/>')
  s.append(text(kx,y+12,'TIME',2.5,INK,'middle'))
  s.append(f'<rect x="{rx-7}" y="{y-3}" width="14" height="6" rx="1" fill="#afbeb7"/><rect x="{rx-2}" y="{y-2.5}" width="4" height="5" fill="{INK}"/>')
  s.append(text(rx,y-5,'3   5   8',2.4,INK,'middle'));s.append(text(rx,y+9,'± V',2.5,INK,'middle'))
  s.append(f'<line x1="{(85 if side==0 else 165)}" y1="{y}" x2="{(95 if side==0 else 155)}" y2="{y0+row*h+h/2}" stroke="{GRID}" stroke-width=".35"/>')
for x,label in [(114,'HOLD'),(138,'LINK')]:
 s.append(f'<circle cx="{x}" cy="147" r="3" fill="{ACC}"/>');s.append(text(x,155,label,2.5,INK,'middle'))
s+=[text(125,165,'CV / LFO / LOW-AUDIO MONITOR',2.7,INK,'middle'),text(125,171,'ERGONOMIC ENVELOPES ONLY — DO NOT MACHINE',2.2,ACC,'middle'),'</svg>']
(A/'panel-study.svg').write_text(''.join(s))
# Block diagram
s=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="650" viewBox="0 0 1200 650">',f'<rect width="1200" height="650" fill="{BG}"/>',text(48,58,'SCOPE 10 / P0 ARCHITECTURE',30),text(48,91,'Preassembled modules + one factory-populated carrier',18,MID)]
def box(x,y,w,h,lines):
 s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="none" stroke="{MID}" stroke-width="2"/>')
 for i,l in enumerate(lines):s.append(text(x+18,y+30+i*25,l,18))
def line(x1,y1,x2,y2):
 s.append(f'<path d="M{x1},{y1} L{x2},{y2}" stroke="{ACC}" stroke-width="3" fill="none"/>');s.append(f'<circle cx="{x2}" cy="{y2}" r="4" fill="{ACC}"/>')
box(48,145,250,145,['10 SIGNAL INPUTS','Bias / limit / filter','2 buffers per channel','Six TLV9064 total'])
box(365,145,225,145,['SIGNAL MUX','74HC4067 → buffer','100 Ω / 1 nF','→ GP26 / ADC0'])
box(48,345,250,135,['10 TIME + 10 RANGE','Dedicated physical controls','Filtered unipolar voltages'])
box(365,345,225,135,['2 CONTROL MUXES','TIME → GP27 / ADC1','RANGE → GP28 / ADC2'])
box(665,210,230,205,['PICO H','Factory-installed headers','Sequential acquisition','Small-tile rendering','USB 5 V / programming'])
box(960,220,195,185,['ONE LCD','Waveshare 19907','480 × 320 pixels','Portrait 2 × 5','SPI bridge'])
line(298,217,365,217);line(298,410,365,410);line(590,217,665,260);line(590,410,665,365);line(895,310,960,310)
s+=[text(48,555,'Targets: 10 ksample/s/channel; CV/LFO and low audio. Not simultaneous sampling.',20),text(48,590,'STOP: verify display power straps, exact footprints and factory acceptance before fabrication.',18,ACC),'</svg>']
(A/'architecture.svg').write_text(''.join(s))
# Simplified circuit specification rendered as vector diagram, native sheets contain full pins.
s=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="600" viewBox="0 0 1280 600">',f'<rect width="1280" height="600" fill="{BG}"/>',text(40,55,'ONE OF TEN / ANALOG INPUT',30),text(40,90,'Component values are proposed; protection and ADC settling remain unqualified.',17,ACC)]
for x,y,w,h,label in [(40,245,100,60,'TIP'),(190,245,135,60,'1 MΩ'),(500,245,140,60,'BUFFER'),(700,245,125,60,'4.7 kΩ'),(945,245,145,60,'BUFFER'),(1140,245,105,60,'MUX')]:
 s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="none" stroke="{INK}" stroke-width="2"/>');s.append(text(x+w/2,y+37,label,17,INK,'middle'))
for a,b in [(140,190),(325,500),(640,700),(825,945),(1090,1140)]:s.append(f'<path d="M{a} 275H{b}" stroke="{INK}" stroke-width="2"/>')
s+=[f'<path d="M400 160V425 M885 275V425" fill="none" stroke="{MID}" stroke-width="2"/>',text(400,130,'3.0 V via 200 kΩ',19,INK,'middle'),text(400,465,'249 kΩ ∥ 470 pF → GND',18,INK,'middle'),text(400,205,'BAV199 rail clamp',16,ACC,'middle'),text(885,465,'10 nF → GND',18,INK,'middle'),text(40,540,'VADC ≈ 1.497594 + 0.0998396 × Vin  |  ±12 V → 0.300 … 2.696 V nominal',20),text(40,573,'Unplugged input ≈ +1.66 V indicated. Ranges ±3 / ±5 / ±8 change the display only.',17,ACC),'</svg>']
(A/'input-channel.svg').write_text(''.join(s))
try:
 import cairosvg
 for f in A.glob('*.svg'):cairosvg.svg2png(url=str(f),write_to=str(f.with_suffix('.png')),output_width=1600)
 print('SVG + PNG drawings written')
except ImportError:print('SVG written; install cairosvg to regenerate PNGs')
# Coordinates are envelope studies, not pads or drill centroids.
items=[]
for n in range(10):
 side=n//5;row=n%5;items.append({'channel':n+1,'pot_axis_mm':[48 if side==0 else 202,43+row*23.5],'range_envelope_centre_mm':[77 if side==0 else 173,43+row*23.5],'jack_envelope_centre_mm':[8.5 if side==0 else 241.5,43+row*23.5]})
(R/'mechanical/panel-layout-study.json').write_text(json.dumps({'units':'mm','purpose':'ERGONOMIC_STUDY_NOT_PAD_PLACEMENT','screen_active_mm':[48.96,73.44],'module_envelope_mm':[57.2,86],'active_centring':'UNVERIFIED_VISUAL_STUDY','channels':items},indent=2)+'\n')
