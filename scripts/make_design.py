#!/usr/bin/env python3
"""Generate a review schematic/netlist from an explicit pin-to-net circuit.
This is NOT a routing or fabrication tool. Unqualified interfaces remain visible.
Standard library only. Run from any working directory.
"""
from pathlib import Path
import json,uuid,math,csv,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
CAT={r['id']:r for r in json.loads((ROOT/'catalog/components.json').read_text())['records']}
parts=[]
def add(ref,kind,nets,sheet,notes='',value=None):
 record=CAT[kind]
 pins={str(k):v for k,v in nets.items()}
 if set(pins)!=set(record['pins']):raise ValueError(f'{ref}: incomplete pins {set(record["pins"])-set(pins)}')
 parts.append({'ref':ref,'record':kind,'value':value or record.get('value') or record['mpn'] or kind,'pins':pins,'sheet':sheet,'notes':notes,'footprint':record['footprint_candidate']})
 return ref
# One physical quad per two input channels, all 14 pins visible.
for bank in range(5):
 sheet=f'inputs-{bank*2+1:02d}-{bank*2+2:02d}'
 an={4:'+3V3A',11:'GND'}
 for off in range(2):
  n=bank*2+off+1;tag=f'CH{n:02d}';b=100*n
  add(f'J{n}','jack',{1:'GND',2:None,3:tag+'_IN'},sheet,'3 logical contacts / 5 physical legs: duplicated pad mapping is OPEN')
  add(f'R{b+1}','r1m',{1:tag+'_IN',2:tag+'_BIAS'},sheet)
  add(f'R{b+2}','r200k',{1:'+3V0_REF',2:tag+'_BIAS'},sheet)
  add(f'R{b+3}','r249k',{1:tag+'_BIAS',2:'GND'},sheet)
  add(f'C{b+1}','c470p',{1:tag+'_BIAS',2:'GND'},sheet)
  add(f'D{n}','clamp',{1:'GND',2:'+3V3A',3:tag+'_BIAS'},sheet)
  add(f'R{b+4}','r4k7',{1:tag+'_BUF1',2:tag+'_LP2'},sheet)
  add(f'C{b+2}','c10n',{1:tag+'_LP2',2:'GND'},sheet)
  if off==0:an.update({1:tag+'_BUF1',2:tag+'_BUF1',3:tag+'_BIAS',5:tag+'_LP2',6:tag+'_OUT',7:tag+'_OUT'})
  else:an.update({8:tag+'_BUF1',9:tag+'_BUF1',10:tag+'_BIAS',12:tag+'_LP2',13:tag+'_OUT',14:tag+'_OUT'})
  add(f'TP{n}','testpoint',{1:tag+'_OUT'},sheet)
 add(f'U{bank+1}','tlv9064',an,sheet)
 add(f'C{bank+1}','c100n',{1:'+3V3A',2:'GND'},sheet)
# Controls: ranges are display scaling only, not switched input attenuators.
for n in range(1,11):
 sheet='controls-left' if n<=5 else 'controls-right';t=f'CH{n:02d}';b=1100+n*10
 add(f'RV{n}','pot',{1:'GND',2:t+'_TIME_W',3:'+3V3A'},sheet,'Endpoint direction must be checked on actual sample')
 add(f'R{b+1}','r1k',{1:t+'_TIME_W',2:t+'_TIME'},sheet)
 add(f'C{b+1}','c100n',{1:t+'_TIME',2:'GND'},sheet)
 add(f'SW{n}','range',{'C':t+'_RANGE_W','L':'GND','M':'RANGE_MID','H':'+3V3A'},sheet,'Logical pin letters intentionally block footprint release')
 add(f'R{b+2}','r1k',{1:t+'_RANGE_W',2:t+'_RANGE'},sheet)
 add(f'C{b+2}','c100n',{1:t+'_RANGE',2:'GND'},sheet)
add('R40','r10k',{1:'+3V3A',2:'RANGE_MID'},'controls-left')
add('R41','r10k',{1:'RANGE_MID',2:'GND'},'controls-left')
for n,(name,pin) in enumerate([('HOLD_N',0),('LINK_N',1)],11):
 add(f'SW{n}','button',{1:name,2:'GND'},'controls-right','Two contacts 1/2 from retained XUNPU drawing; independent footprint review required')
 add(f'R{n+40}','r10k',{1:'+3V3D',2:name},'controls-right')
 add(f'C{n+40}','c100n',{1:name,2:'GND'},'controls-right')
# Three mux banks; analog outputs never tied together.
muxpin={0:9,1:8,2:7,3:6,4:5,5:4,6:3,7:2,8:23,9:22,10:21,11:20,12:19,13:18,14:17,15:16}
for u,suffix in [(7,'OUT'),(8,'TIME'),(9,'RANGE')]:
 ns={str(k):None for k in CAT['mux']['pins']}
 ns.update({'1':'MUX_'+suffix,'10':'ADDR0','11':'ADDR1','14':'ADDR2','13':'ADDR3','15':'MUX_DISABLE','12':'GND','24':'+3V3A'})
 for k,pin in muxpin.items():ns[str(pin)]=f'CH{k+1:02d}_{suffix}' if k<10 else ('GND' if k%2==0 else '+3V0_REF')
 add(f'U{u}','mux',ns,'acquisition')
 add(f'C{u}','c100n',{1:'+3V3A',2:'GND'},'acquisition')
ns={1:'ADC_DRV0',2:'ADC_DRV0',3:'MUX_OUT',4:'+3V3A',5:'MUX_TIME',6:'ADC_DRV1',7:'ADC_DRV1',8:'ADC_DRV2',9:'ADC_DRV2',10:'MUX_RANGE',11:'GND',12:'REF_RAW',13:'+3V0_REF',14:'+3V0_REF'}
add('U6','tlv9064',ns,'acquisition')
add('C6','c100n',{1:'+3V3A',2:'GND'},'acquisition')
for i in range(3):
 add(f'R{20+i}','r100',{1:f'ADC_DRV{i}',2:f'ADC{i}'},'acquisition')
 add(f'C{20+i}','c1n',{1:f'ADC{i}',2:'GND'},'acquisition')
 add(f'TP{20+i}','testpoint',{1:f'ADC{i}'},'acquisition')
# MCU contact assignment. These are PHYSICAL carrier strips, not duplicated module silicon.
gpio={0:'HOLD_N',1:'LINK_N',2:'ADDR0_SRC',3:'ADDR1_SRC',4:'ADDR2_SRC',5:'ADDR3_SRC',7:'MUX_DISABLE',8:'LCD_DC_SRC',9:'LCD_CS_SRC',10:'LCD_CLK_SRC',11:'LCD_MOSI_SRC',12:'LCD_MISO',13:'LCD_BL_SRC',14:'TIMING_TP',15:'LCD_RST_SRC',16:'TP_CS_N',22:'SD_CS_N',26:'ADC0',27:'ADC1',28:'ADC2'}
pico_nets={}
for pin,name in CAT['pico-h']['pins'].items():
 if name in ('GND','AGND'):net='GND'
 elif name=='VBUS':net='VBUS_USB'
 elif name=='3V3_OUT':net='+3V3D'
 elif name.startswith('GP'):net=gpio.get(int(name.split('_')[0][2:]))
 else:net=None
 pico_nets[int(pin)]=net
add('J20','socket20',{k:pico_nets[k] for k in range(1,21)},'module-interfaces','Left Pico H socket: pin 1 = Pico pin 1')
add('J21','socket20',{k:pico_nets[41-k] for k in range(1,21)},'module-interfaces','Right Pico H socket: pin 1 = Pico pin 40; do not mirror blindly')
# Isolate ALL unused display header positions. No broad 40-pin pass-through.
displaymap={3:'GND',8:'GND',13:'GND',18:'GND',23:'GND',28:'GND',33:'GND',38:'GND',39:'+5V_FUSED',11:'LCD_DC',12:'LCD_CS',14:'LCD_CLK',15:'LCD_MOSI',16:'LCD_MISO',17:'LCD_BL',20:'LCD_RST',21:'TP_CS_N',29:'SD_CS_N'}
add('J30','header20',{k:displaymap.get(k) for k in range(1,21)},'module-interfaces','Display left header: pin 1 = Pico position 1. Power straps OPEN gate G01.')
add('J31','header20',{k:displaymap.get(41-k) for k in range(1,21)},'module-interfaces','Display right header: pin 1 = Pico position 40; pin 2 supplies VSYS position')
for n,name in enumerate(['LCD_DC','LCD_CS','LCD_CLK','LCD_MOSI','LCD_BL','LCD_RST','ADDR0','ADDR1','ADDR2','ADDR3']):
 add(f'R{60+n}','r33',{1:name+'_SRC',2:name},'module-interfaces')
for n,name in enumerate(['ADDR0','ADDR1','ADDR2','ADDR3']):add(f'R{80+n}','r100k',{1:name,2:'GND'},'module-interfaces')
for n,name in enumerate(['LCD_CS','TP_CS_N','SD_CS_N']):add(f'R{84+n}','r100k',{1:'+3V3D',2:name},'module-interfaces')
add('R87','r100k',{1:'+3V3A',2:'MUX_DISABLE'},'module-interfaces')
add('R88','r100k',{1:'LCD_BL',2:'GND'},'module-interfaces')
add('TP30','testpoint',{1:'TIMING_TP'},'module-interfaces')
# USB-only power; neither +/-12V nor PD input is allowed.
add('F1','fuse',{1:'VBUS_USB',2:'+5V_FUSED'},'power','Protection component identity pending; not an inrush/load-switch substitute')
add('U10','ldo',{1:'+5V_FUSED',2:'GND',3:'+5V_FUSED',4:None,5:'+3V3A'},'power')
add('U11','ref',{1:'+3V3A',2:'REF_RAW',3:'GND'},'power')
add('C30','c1u',{1:'+5V_FUSED',2:'GND'},'power')
add('C31','c1u',{1:'+3V3A',2:'GND'},'power')
add('C32','c1u',{1:'REF_RAW',2:'GND'},'power')
add('C33','c100n',{1:'+3V3A',2:'GND'},'power')
# Extra 10uF bulk is a DNP candidate, NOT fitted by default: USB inrush gate.
add('R30','r1k',{1:'+3V3A',2:'GND'},'power','Intentional 3.3mA bleed; bound unpowered injection, still requires testing')
for n,net in enumerate(['GND','VBUS_USB','+5V_FUSED','+3V3A','REF_RAW','+3V0_REF','+3V3D'],40):add(f'TP{n}','testpoint',{1:net},'power')
# Explicit physical-to-module relation is independent of pin-type assumptions.
interface={'pico_h':{'J20':{str(k):k for k in range(1,21)},'J21':{str(k):41-k for k in range(1,21)}},'display':{'J30':{str(k):k for k in range(1,21)},'J31':{str(k):41-k for k in range(1,21)}}}
write=lambda path,obj:(ROOT/path).write_text(json.dumps(obj,indent=2)+'\n')
write('design/circuit.json',{'schema_version':1,'generator':'scripts/make_design.py','status':'REVIEW_ONLY_NOT_FOR_FABRICATION','parts':parts,'external_modules':['pico-h','display'],'connector_position_maps':interface})
write('design/gpio.json',{'gpio_nets':gpio,'adc_channels':{0:'ADC0',1:'ADC1',2:'ADC2'},'mux_address_pins':[2,3,4,5],'mux_disable_pin':7,'display_spi':1,'display_spi_hz_initial':8000000,'display_cs_pin':9,'display_touch_sd_unused':True})
# Planning BOM; no locations are invented and no CPL is emitted.
groups={}
for p in parts:groups.setdefault(p['record'],[]).append(p)
with (ROOT/'manufacturing/bom-planning.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['REVIEW_ONLY','Record','Manufacturer part','Value','Quantity','References','Package','JLC/LCSC','Procurement state','Footprint candidate'])
 for id,ps in groups.items():
  r=CAT[id];w.writerow(['NOT_FOR_ORDER',id,r['mpn'] or 'UNSELECTED',ps[0]['value'],len(ps),' '.join(p['ref'] for p in ps),r['package'],r['jlc_code'] or '', 'EXACT_MPN_REVIEW' if r['mpn'] else 'RFQ_REQUIRED',r['footprint_candidate']])
 for id in ['pico-h','display']:
  r=CAT[id];w.writerow(['NOT_FOR_ORDER',id,r['mpn'],'',1,'EXTERNAL',r['package'],'','BUY_PREASSEMBLED',''])
with (ROOT/'design/connections.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['Reference','MPN/value','Pin','Pin function','Net','Sheet','Review note'])
 for p in parts:
  for k,v in p['pins'].items():w.writerow([p['ref'],p['value'],k,CAT[p['record']]['pins'][k],v or 'NO_CONNECT',p['sheet'],p['notes']])
# XML netlist for independent local inspection/import workflows.
ex=ET.Element('export',version='D');cs=ET.SubElement(ex,'components');nets={}
for p in parts:
 c=ET.SubElement(cs,'comp',ref=p['ref']);ET.SubElement(c,'value').text=p['value'];ET.SubElement(c,'footprint').text=p['footprint'];ET.SubElement(c,'libsource',lib='ZudoScope10',part=p['record'])
 for pin,net in p['pins'].items():
  if net:nets.setdefault(net,[]).append((p['ref'],pin))
n=ET.SubElement(ex,'nets')
for idx,(name,nodes) in enumerate(sorted(nets.items()),1):
 ne=ET.SubElement(n,'net',code=str(idx),name=name)
 for ref,pin in nodes:ET.SubElement(ne,'node',ref=ref,pin=pin)
ET.indent(ex);ET.ElementTree(ex).write(ROOT/'hardware/kicad/zudo-scope10-p0.net',encoding='utf-8',xml_declaration=True)
# Native KiCad 8 schematic format; all symbols embedded. User must open and run ERC.
def uid(s):return str(uuid.uuid5(uuid.NAMESPACE_URL,'zudo-scope10-p0/'+s))
def q(s):return json.dumps(str(s),ensure_ascii=False)
G=1.27
def f(v):
 t=f'{round(v,4):.4f}'.rstrip('0').rstrip('.')
 return '0' if t in ('','-0') else t
def effect(size=1.27,hide=False):return f'(effects (font (size {size} {size}))'+(' hide' if hide else '')+')'
def layout(record):
 keys=list(CAT[record]['pins']);n=math.ceil(len(keys)/2);out={}
 for i,k in enumerate(keys):
  left=i<n;j=i if left else i-n;y=(n-1)*1.27-j*2.54
  out[k]=(-12.7 if left else 12.7,y,0 if left else 180)
 return out,max(5.08,n*1.27+2.54)
def pin_type(kind,name):
 if kind=='tlv9064':return 'power_in' if name in ('VCC','GND') else ('output' if name.startswith('OUT') else 'input')
 # 74HC4067 Y/Z are analog-switch terminals with no drive of their own: passive, not bidirectional logic.
 if kind=='mux':return 'power_in' if name in ('VCC','GND') else ('input' if name.startswith('S') or name=='E_N' else 'passive')
 if kind in ('ldo','ref'):return 'no_connect' if name=='NC' else ('power_out' if name=='OUT' else ('input' if name=='EN' else 'power_in'))
 return 'passive'
def libsym(id,prefix=True):
 r=CAT[id];lo,h=layout(id);name='ZudoScope10:'+id if prefix else id
 a=[f'(symbol {q(name)} (pin_names (offset 0.508)) (in_bom yes) (on_board yes)',f'(property "Reference" "X" (at 0 {f(h+2.54)} 0) {effect()})',f'(property "Value" {q(id)} (at 0 {f(-h-2.54)} 0) {effect()})',f'(symbol {q(id+"_0_1")} (rectangle (start -10.16 {f(h)}) (end 10.16 {f(-h)}) (stroke (width 0.254) (type default)) (fill (type background))))',f'(symbol {q(id+"_1_1")}']
 for k,(x,y,ang) in lo.items():
  a.append(f'(pin {pin_type(id,r["pins"][k])} line (at {f(x)} {f(y)} {ang}) (length 2.54) (name {q(r["pins"][k])} {effect(1.0)}) (number {q(k)} {effect(1.0)}))')
 return '\n'.join(a)+'))'
# KiCad-standard PWR_FLAG shape: power symbol with one power_out pin; marks a net supplied from off-board (USB via the Pico module header).
PWR_FLAG=('(symbol "{name}" (power) (pin_numbers hide) (pin_names (offset 0) hide) (in_bom no) (on_board no) (property "Reference" "#FLG" (at 0 1.905 0) '+effect(1.27,True)+') (property "Value" "PWR_FLAG" (at 0 3.81 0) '+effect()+') '
 '(symbol "PWR_FLAG_0_0" (pin power_out line (at 0 0 90) (length 0) (name "~" '+effect()+') (number "1" '+effect()+'))) '
 '(symbol "PWR_FLAG_0_1" (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27)) (stroke (width 0) (type default)) (fill (type none)))))')
# Nets whose only source is the USB VBUS/GND contacts of the external Pico module (passive socket pins) and the passive fuse.
FLAGGED={'power':['+5V_FUSED','GND']}
rootid=uid('root');names=['power','module-interfaces','acquisition']+[f'inputs-{n:02d}-{n+1:02d}' for n in [1,3,5,7,9]]+['controls-left','controls-right']
for page,sh in enumerate(names,2):
 ps=[p for p in parts if p['sheet']==sh];sid=uid('sheet/'+sh)
 s=[f'(kicad_sch (version 20231120) (generator "eeschema") (uuid {sid}) (paper "A1")',f'(title_block (title {q("zudo-scope10 P0 / "+sh)}) (date "2026-09-26") (rev "P0 REVIEW ONLY") (comment 1 "GENERATED: no PCB routing or assembly approval"))','(lib_symbols '+''.join(libsym(id) for id in sorted({p['record'] for p in ps}))+(PWR_FLAG.format(name='ZudoScope10:PWR_FLAG') if sh in FLAGGED else '')+')',f'(text "NOT FOR FABRICATION - exact footprints and interface gates remain OPEN" (at 20 15 0) {effect(2) } (uuid {uid(sh+"/warning")}))']
 for idx,p in enumerate(ps):
  x=(35+(idx%7)*88)*G;y=(43+(idx//7)*72)*G;id=p['record'];lo,h=layout(id);inst=uid('ref/'+p['ref'])
  s.extend([f'(symbol (lib_id {q("ZudoScope10:"+id)}) (at {f(x)} {f(y)} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {inst})',f'(property "Reference" {q(p["ref"])} (at {f(x)} {f(y-h-5)} 0) {effect()})',f'(property "Value" {q(p["value"])} (at {f(x)} {f(y-h-2)} 0) {effect(1.0)})',f'(property "Footprint" {q(p["footprint"])} (at {f(x)} {f(y)} 0) {effect(1.0,True)})',f'(property "Datasheet" "" (at {f(x)} {f(y)} 0) {effect(1.0,True)})',f'(property "Record" {q(id)} (at {f(x)} {f(y)} 0) {effect(1.0,True)})'])
  for k in lo:s.append(f'(pin {q(k)} (uuid {uid(p["ref"]+"/pin/"+k)}))')
  s.append(f'(instances (project "zudo-scope10-p0" (path "/{rootid}/{sid}" (reference {q(p["ref"])}) (unit 1)))))')
  for pin,(dx,dy,ang) in lo.items():
   xx=f(x+dx);yy=f(y-dy);net=p['pins'][pin]
   if not net:s.append(f'(no_connect (at {xx} {yy}) (uuid {uid(p["ref"]+"/nc/"+pin)}))');continue
   xx2=f(x+dx+(-5.08 if dx<0 else 5.08))
   s.append(f'(wire (pts (xy {xx} {yy}) (xy {xx2} {yy})) (stroke (width 0) (type default)) (uuid {uid(p["ref"]+"/wire/"+pin)}))')
   rot=0 if dx<0 else 180
   s.append(f'(global_label {q(net)} (shape passive) (at {xx2} {yy} {rot}) (effects (font (size 1.0 1.0)) (justify left)) (uuid {uid(p["ref"]+"/label/"+pin)}) (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {xx2} {yy} {rot}) {effect(1,True)}))')
 for i,net in enumerate(FLAGGED.get(sh,[]),1):
  fx=f((16+i*16)*G);fy=f(20*G);fy2=f(24*G);ref=f'#FLG0{i}';fid=uid(sh+'/flag/'+net)
  s.append(f'(symbol (lib_id "ZudoScope10:PWR_FLAG") (at {fx} {fy} 0) (unit 1) (in_bom no) (on_board no) (dnp no) (uuid {fid}) (property "Reference" {q(ref)} (at {fx} {f(18*G)} 0) {effect(1.27,True)}) (property "Value" "PWR_FLAG" (at {fx} {f(16*G)} 0) {effect()}) (property "Footprint" "" (at {fx} {fy} 0) {effect(1.27,True)}) (property "Datasheet" "" (at {fx} {fy} 0) {effect(1.27,True)}) (pin "1" (uuid {uid(sh+"/flag/"+net+"/pin")})) (instances (project "zudo-scope10-p0" (path "/{rootid}/{uid("sheet/"+sh)}" (reference {q(ref)}) (unit 1)))))')
  s.append(f'(wire (pts (xy {fx} {fy}) (xy {fx} {fy2})) (stroke (width 0) (type default)) (uuid {uid(sh+"/flag/"+net+"/wire")}))')
  s.append(f'(global_label {q(net)} (shape passive) (at {fx} {fy2} 270) (effects (font (size 1.0 1.0)) (justify right)) (uuid {uid(sh+"/flag/"+net+"/label")}) (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {fx} {fy2} 270) {effect(1,True)}))')
 s.append(')');(ROOT/f'hardware/kicad/{sh}.kicad_sch').write_text('\n'.join(s)+'\n')
# KiCad 9's S-expression reader rejects a raw newline inside a quoted string ("Failed to load"); emit \\n escapes.
s=[f'(kicad_sch (version 20231120) (generator "eeschema") (uuid {rootid}) (paper "A3") (lib_symbols)', '(title_block (title "zudo-scope10 / P0 schematic review") (date "2026-09-26") (rev "P0 PRELAYOUT"))',f'(text "TEN INPUTS / ONE LCD / NO HOME SOLDERING\\nSchematic draft, not an approved netlist. Read START_HERE.md and design/release-gates.json." (at 20 15 0) (effects (font (size 2 2)) (justify left)) (uuid {uid("root/text")}))']
for n,sh in enumerate(names):
 x=20+(n%3)*128;y=42+(n//3)*55;sid=uid('sheet/'+sh)
 s.append(f'(sheet (at {x} {y}) (size 108 32) (stroke (width 0.254) (type default)) (fill (color 0 0 0 0)) (uuid {sid}) (property "Sheetname" {q(sh)} (at {x} {y-1} 0) (effects (font (size 1.5 1.5)) (justify left bottom))) (property "Sheetfile" {q(sh+".kicad_sch")} (at {x} {y+33} 0) (effects (font (size 1.27 1.27)) (justify left top))) (instances (project "zudo-scope10-p0" (path "/{rootid}" (page {q(n+2)})))))')
s.append('(sheet_instances (path "/" (page "1"))))');(ROOT/'hardware/kicad/zudo-scope10-p0.kicad_sch').write_text('\n'.join(s)+'\n')
(ROOT/'hardware/libraries/ZudoScope10.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "kicad_symbol_editor")\n'+''.join(libsym(id,False) for id in sorted(groups))+PWR_FLAG.format(name='PWR_FLAG')+')\n')
(ROOT/'hardware/kicad/sym-lib-table').write_text('(sym_lib_table (lib (name "ZudoScope10") (type "KiCad") (uri "${KIPRJMOD}/../libraries/ZudoScope10.kicad_sym") (options "") (descr "P0 review symbols")))\n')
write('hardware/kicad/zudo-scope10-p0.kicad_pro',{'meta':{'filename':'zudo-scope10-p0.kicad_pro','version':1},'text_variables':{'REVISION':'P0_PRELAYOUT_NOT_FOR_FAB'}})
# Outline only; no fabricated electrical pads, tracks, or fake placements.
pcb='''(kicad_pcb (version 20240108) (generator "pcbnew")
 (general (thickness 1.6)) (paper "A4")
 (layers (0 "F.Cu" signal) (1 "In1.Cu" power) (2 "In2.Cu" power) (31 "B.Cu" signal)
 (44 "Edge.Cuts" user) (40 "Dwgs.User" user) (36 "B.SilkS" user "b.silkscreen") (37 "F.SilkS" user "f.silkscreen")
 (38 "B.Mask" user) (39 "F.Mask" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user) (48 "B.Fab" user) (49 "F.Fab" user))
 (setup (pad_to_mask_clearance 0)) (net 0 "")
 (gr_rect (start 50 50) (end 300 230) (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts") (uuid "'''+uid('pcb/outline')+'''"))
 (gr_text "OUTLINE STUDY ONLY - NO COMPONENTS OR ROUTING\\nP0 / DO NOT FABRICATE" (at 175 140) (layer "Dwgs.User") (uuid "'''+uid('pcb/warn')+'''") (effects (font (size 3 3) (thickness 0.5))))
)'''
(ROOT/'hardware/kicad/zudo-scope10-p0.kicad_pcb').write_text(pcb+'\n')
print(f'{len(parts)} physical schematic instances / {len(nets)} nets / {len(names)+1} native sheets')
