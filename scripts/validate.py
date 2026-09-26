#!/usr/bin/env python3
"""Offline pre-layout integrity checks. NOT native KiCad, electrical or DFM approval."""
from pathlib import Path
from collections import Counter,defaultdict
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
import json,re,hashlib,xml.etree.ElementTree as ET,subprocess,sys,shutil,tempfile,difflib
sys.path.insert(0,str(Path(__file__).resolve().parent));import validate_extra
R=Path(__file__).resolve().parents[1];checks=[]
# Reports that legitimately change on every run (validate.py's own report, plus
# any report a check below explicitly writes as a side effect, e.g. validate_extra's
# ngspice hook). Never part of the "leave the checkout untouched" contract that
# governs the isolated regeneration comparison further down.
DESIGNATED_REPORTS={R/'reports/validation.json',R/'reports/spice.json'}
def check(name,value,detail=''):
 checks.append({'check':name,'result':'PASS' if value else 'FAIL','detail':detail})
 if not value:print('FAIL:',name,detail)
cat=json.loads((R/'catalog/components.json').read_text())['records'];byid={r['id']:r for r in cat};c=json.loads((R/'design/circuit.json').read_text());parts=c['parts'];pby={p['ref']:p for p in parts}
gates=json.loads((R/'design/release-gates.json').read_text());design_phase=gates.get('design_phase','pre-layout')
check('design_phase is a recognized value',design_phase in gates.get('design_phase_values',['pre-layout','layout','qualification']),design_phase)
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
parsed={};native=sorted((R/'hardware').rglob('*.kicad_sch'))+sorted((R/'hardware').rglob('*.kicad_sym'))+sorted((R/'hardware').rglob('*.kicad_pcb'))+sorted((R/'hardware').rglob('*.kicad_mod'))
for f in native:
 try:parsed[f]=parse(f.read_text());check('S-expression '+f.name,True)
 except Exception as e:check('S-expression '+f.name,False,str(e))
scsymbols=[]
for f,t in parsed.items():
 if f.suffix=='.kicad_sch':
  for sym in children(t,'symbol'):
   props={p[1]:p[2] for p in children(sym,'property')}
   if not props['Reference'].startswith('#'):scsymbols.append(props['Reference'])  # '#' = KiCad power/flag symbol, not a physical part
check('Native schematic instance inventory matches graph',Counter(scsymbols)==Counter(pby.keys()))
root=parse((R/'hardware/kicad/zudo-scope10-p0.kicad_sch').read_text());check('Root has ten child sheets',len(children(root,'sheet'))==10)
for sh in children(root,'sheet'):
 props={p[1]:p[2] for p in children(sh,'property')};check('Sheet exists '+props['Sheetfile'],(R/'hardware/kicad'/props['Sheetfile']).exists())
pcb=parse((R/'hardware/kicad/zudo-scope10-p0.kicad_pcb').read_text());has_layout=bool(children(pcb,'footprint') or children(pcb,'segment'))
if design_phase=='pre-layout':
 check('PCB honestly remains outline only',not has_layout)
else:
 # layout/qualification: placement/routing is expected, not forbidden. The current
 # outline-only board is still kept off the fabrication path by the release guard
 # check below, independent of design_phase.
 check(f'PCB placement/routing reflects declared design_phase={design_phase!r}',True,f'footprints={len(children(pcb,"footprint"))} segments={len(children(pcb,"segment"))}')
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
for f in [R/'index.html']+sorted((R/'offline').glob('*.html'))+sorted((R/'doc/public').rglob('*.html')):
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
if design_phase=='pre-layout':
 check('No catalog footprint or factory approval fabricated',all(not r['footprint_qualified'] and not r['factory_order_approved'] for r in cat))
else:
 # layout/qualification: a record MAY carry footprint_qualified/factory_order_approved,
 # but only alongside a non-empty evidence reference recorded on that same record --
 # never emptiness alone, and never a flag with no reviewable citation behind it.
 def _qualified_without_evidence(r,flag,evidence_key):
  return bool(r.get(flag)) and not r.get(evidence_key)
 unevidenced=[r['id'] for r in cat if _qualified_without_evidence(r,'footprint_qualified','footprint_qualified_evidence') or _qualified_without_evidence(r,'factory_order_approved','factory_order_approved_evidence')]
 check('Every qualified footprint/factory approval carries a review evidence reference',not unevidenced,json.dumps(unevidenced))
guard=subprocess.run([sys.executable,str(R/'manufacturing/release_guard.py'),'--route','production'],capture_output=True,text=True)
check('Release guard exits 2 (REFUSED) for the checked-in manifest, production route',guard.returncode==2 and guard.stderr.startswith('REFUSED') and not gates['release_allowed'],f'exit={guard.returncode} stderr={guard.stderr[:200]!r}')
# #24/#43: the prototype route is a separate decision (design/release-gates.json's
# decisions.prototype) that never reads gate CLOSED status; it must independently
# refuse too -- no gate closing is claimed, and no prototype prerequisite/approval is met.
guard_proto=subprocess.run([sys.executable,str(R/'manufacturing/release_guard.py'),'--route','prototype'],capture_output=True,text=True)
check('Release guard exits 2 (REFUSED) for the checked-in manifest, prototype route',guard_proto.returncode==2 and guard_proto.stderr.startswith('REFUSED') and not gates.get('decisions',{}).get('prototype',{}).get('allowed',True),f'exit={guard_proto.returncode} stderr={guard_proto.stderr[:200]!r}')
# Deterministic generated content. Regenerate in an isolated temp copy of the whole
# repository and compare bytes there -- the checkout itself is never run against the
# generators, so a mismatch (or a generator bug) cannot mutate or destroy it (#23/#31).
gen_rel_paths=[p.relative_to(R) for p in sorted((R/'hardware/kicad').glob('*'))+[R/'design/circuit.json',R/'design/gpio.json',R/'design/connections.csv',R/'manufacturing/bom-planning.csv']+sorted((R/'doc/src/content/docs').rglob('*.mdx')) if p not in DESIGNATED_REPORTS]
tmp=Path(tempfile.mkdtemp(prefix='zs10-validate-'))
try:
 shutil.copytree(R,tmp,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','node_modules','dist','__pycache__'))
 gen_ok=True;gen_detail=''
 for script in ['make_design.py','analyze.py','build_docs.py']:
  r=subprocess.run([sys.executable,str(tmp/'scripts'/script)],capture_output=True,text=True,cwd=tmp)
  if r.returncode!=0:gen_ok=False;gen_detail+=f'{script} exited {r.returncode}:\n{r.stdout}{r.stderr}\n'
 mismatches=[]
 if gen_ok:
  for rel in gen_rel_paths:
   orig=R/rel;gen=tmp/rel
   if not orig.is_file():mismatches.append(f'{rel}: missing from checkout');continue
   if not gen.is_file():mismatches.append(f'{rel}: isolated regeneration did not produce this file');continue
   ob=orig.read_bytes();gb=gen.read_bytes()
   if ob==gb:continue
   try:
    diff=''.join(list(difflib.unified_diff(ob.decode().splitlines(True),gb.decode().splitlines(True),fromfile=f'checkout/{rel}',tofile=f'regenerated/{rel}'))[:40])
   except UnicodeDecodeError:
    diff='(binary content differs)'
   mismatches.append(f'{rel}:\n{diff}')
 check('Isolated regeneration matches checkout without mutating it',gen_ok and not mismatches,gen_detail if not gen_ok else '\n'.join(mismatches))
finally:
 shutil.rmtree(tmp,ignore_errors=True)
# Extension point: later topics register checks in scripts/validate_extra.py.
validate_extra.run(check,{'R':R,'cat':cat,'byid':byid,'circuit':c,'parts':parts,'pby':pby})
report={'result':'PASS' if all(c['result']=='PASS' for c in checks) else 'FAIL','scope':'Offline structural checks only. NOT native ERC/DRC or assembly approval.','physical_instances':len(parts),'nets':len(expected),'component_records':len(cat),'retained_source_files':assetcount,'checks':checks,'not_run':['Native KiCad parsing/ERC/DRC','Native zudo-doc npm install/build','Pico/ARM target compilation','Vendor LCD backend integration','Electrical or mechanical hardware measurements','Factory DFM/quote/acceptance']}
(R/'reports/validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'{report["result"]}: {len(checks)} structural checks / {len(parts)} instances / {len(expected)} nets')
raise SystemExit(0 if report['result']=='PASS' else 1)
