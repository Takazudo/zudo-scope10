#!/usr/bin/env python3
"""Offline pre-layout integrity checks. NOT native KiCad, electrical or DFM approval."""
from pathlib import Path
from collections import Counter,defaultdict
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
import json,re,hashlib,xml.etree.ElementTree as ET,subprocess,sys
R=Path(__file__).resolve().parents[1];checks=[]
def check(name,value,detail=''):
 checks.append({'check':name,'result':'PASS' if value else 'FAIL','detail':detail})
 if not value:print('FAIL:',name,detail)
cat=json.loads((R/'catalog/components.json').read_text())['records'];byid={r['id']:r for r in cat};c=json.loads((R/'design/circuit.json').read_text());parts=c['parts'];pby={p['ref']:p for p in parts}
check('Unique component records',len(byid)==len(cat))
check('Unique physical references',len(pby)==len(parts))
check('Every part has exactly its record pins',all(set(p['pins'])==set(byid[p['record']]['pins']) for p in parts))
counts=Counter(p['record'] for p in parts)
check('Ten inputs, TIME pots and RANGE switches',all(counts[k]==10 for k in ['jack','pot','range']))
check('Required silicon counts',counts['tlv9064']==6 and counts['mux']==3 and counts['ldo']==1 and counts['ref']==1)
check('Module strips included in factory BOM',counts['socket20']==2 and counts['header20']==2)
check('No raw RP2040 pretending to be a Pico',c['external_modules']==['pico-h','display'])
expected=defaultdict(set)
for p in parts:
 for pin,net in p['pins'].items():
  if net:expected[net].add((p['ref'],pin))
ex=ET.parse(R/'hardware/kicad/zudo-scope10-p0.net');actual={n.attrib['name']:{(v.attrib['ref'],v.attrib['pin']) for v in n} for n in ex.findall('./nets/net')}
check('XML netlist equals explicit pin/net graph',dict(expected)==actual)
check('Mux outputs remain independent',len({pby['U'+str(i)]['pins']['1'] for i in [7,8,9]})==3)
for bank,typ,ref in [(7,'OUT',0),(8,'TIME',1),(9,'RANGE',2)]:
 check(f'U{bank} common and supply contract',pby['U'+str(bank)]['pins']['1']=='MUX_'+typ and pby['U'+str(bank)]['pins']['24']=='+3V3A')
check('Display power position 39 only is explicit',pby['J31']['pins']['2']=='+5V_FUSED' and pby['J31']['pins']['1'] is None and pby['J31']['pins']['5'] is None,'Conditional G01; does not validate hardware straps')
check('Display spare GP3 GP5 GP14 not passed through',all(pby['J30']['pins'][str(n)] is None for n in [5,7,19]))
check('No bipolar power net on digital mux supply',not any('12V' in str(pby['U'+str(i)]['pins']['24']) for i in [7,8,9]))
# Lossless shallow S-expression reader: syntax/node-count checks only.
def parse(text):
 tokens=re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+',text);stack=[];roots=[]
 for tok in tokens:
  if tok=='(':stack.append([])
  elif tok==')':
   if not stack:raise ValueError('Unexpected closing parenthesis')
   node=stack.pop();(stack[-1] if stack else roots).append(node)
  else:
   if not stack:raise ValueError('Bare token outside root')
   stack[-1].append(json.loads(tok,strict=False) if tok.startswith('"') else tok)
 if stack or len(roots)!=1:raise ValueError('Unclosed or multiple roots')
 return roots[0]
def children(node,kind):return [n for n in node[1:] if isinstance(n,list) and n and n[0]==kind]
parsed={};native=list((R/'hardware').rglob('*.kicad_sch'))+list((R/'hardware').rglob('*.kicad_sym'))+list((R/'hardware').rglob('*.kicad_pcb'))+list((R/'hardware').rglob('*.kicad_mod'))
for f in native:
 try:parsed[f]=parse(f.read_text());check('S-expression '+f.name,True)
 except Exception as e:check('S-expression '+f.name,False,str(e))
scsymbols=[]
for f,t in parsed.items():
 if f.suffix=='.kicad_sch':
  for sym in children(t,'symbol'):
   props={p[1]:p[2] for p in children(sym,'property')};scsymbols.append(props['Reference'])
check('Native schematic instance inventory matches graph',Counter(scsymbols)==Counter(pby.keys()))
root=parse((R/'hardware/kicad/zudo-scope10-p0.kicad_sch').read_text());check('Root has ten child sheets',len(children(root,'sheet'))==10)
for sh in children(root,'sheet'):
 props={p[1]:p[2] for p in children(sh,'property')};check('Sheet exists '+props['Sheetfile'],(R/'hardware/kicad'/props['Sheetfile']).exists())
pcb=parse((R/'hardware/kicad/zudo-scope10-p0.kicad_pcb').read_text());check('PCB honestly remains outline only',not children(pcb,'footprint') and not children(pcb,'segment'))
# Original retained files: integrity is not copyright clearance or fit verification.
assetcount=0
for r in cat:
 for a in r['assets']:
  path=R/a['path'];ok=path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==a['sha256'];check('Retained asset '+a['path'],ok);assetcount+=1
class Links(HTMLParser):
 def __init__(self):super().__init__();self.refs=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  for key in ('href','src'):
   if key in d:self.refs.append(d[key])
missing=[]
for f in [R/'index.html']+list((R/'offline').glob('*.html'))+list((R/'doc/public').rglob('*.html')):
 parser=Links();parser.feed(f.read_text())
 for uri in parser.refs:
  u=urlsplit(uri)
  if u.scheme or u.netloc or not u.path or u.path.startswith('/'):continue
  target=(f.parent/unquote(u.path)).resolve()
  if not target.exists():missing.append([str(f.relative_to(R)),uri])
check('All local HTML links/media exist',not missing,json.dumps(missing))
# Source manifest references and truthful state.
srcids={s['id'] for s in json.loads((R/'catalog/sources.json').read_text())['sources']}
check('All component source references resolve',all(set(r['source_ids'])<=srcids for r in cat))
check('No catalog footprint or factory approval fabricated',all(not r['footprint_qualified'] and not r['factory_order_approved'] for r in cat))
g=json.loads((R/'design/release-gates.json').read_text());guard=subprocess.run([sys.executable,str(R/'manufacturing/release_guard.py')],capture_output=True,text=True)
check('Release guard blocks this package',guard.returncode!=0 and not g['release_allowed'])
# Deterministic generated content. Regenerate and compare input/output bytes.
paths=list((R/'hardware/kicad').glob('*'))+[R/'design/circuit.json',R/'design/gpio.json',R/'design/connections.csv',R/'manufacturing/bom-planning.csv']+list((R/'doc/src/content/docs').rglob('*.mdx'))
before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
for script in ['make_design.py','analyze.py','build_docs.py']:
 subprocess.run([sys.executable,str(R/'scripts'/script)],check=True,capture_output=True,text=True)
check('Regeneration preserves generated design/page bytes',all(hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in before.items()))
report={'result':'PASS' if all(c['result']=='PASS' for c in checks) else 'FAIL','scope':'Offline structural checks only. NOT native ERC/DRC or assembly approval.','physical_instances':len(parts),'nets':len(expected),'component_records':len(cat),'retained_source_files':assetcount,'checks':checks,'not_run':['Native KiCad parsing/ERC/DRC','Native zudo-doc npm install/build','Pico/ARM target compilation','Vendor LCD backend integration','Electrical or mechanical hardware measurements','Factory DFM/quote/acceptance']}
(R/'reports/validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'{report["result"]}: {len(checks)} structural checks / {len(parts)} instances / {len(expected)} nets')
raise SystemExit(0 if report['result']=='PASS' else 1)
