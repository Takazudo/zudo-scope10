#!/usr/bin/env python3
"""Project-local evidence projection into MDX and an offline reading site.
No network. Data remain in catalog/*.json, narrative text in design/narrative-pages.json.
Offline HTML uses a small stdlib Markdown renderer defined below: no optional
dependency, so the committed HTML is identical in every environment.
"""
from pathlib import Path
import json,html,shutil,re
R=Path(__file__).resolve().parents[1];D=R/'doc/src/content/docs';O=R/'offline';O.mkdir(exist_ok=True)
cat=json.loads((R/'catalog/components.json').read_text())['records'];src=json.loads((R/'catalog/sources.json').read_text())['sources'];sources={s['id']:s for s in src}
circuit=json.loads((R/'design/circuit.json').read_text());placements={r['id']:[] for r in cat}
for p in circuit['parts']:placements[p['record']].append(p['ref'])
allpages=json.loads((R/'design/narrative-pages.json').read_text())
def esc(s):return str(s).replace('|','\\|').replace('<','&lt;').replace('>','&gt;').replace('{','&#123;').replace('}','&#125;')
for r in cat:
 fields={'Record':r['id'],'Manufacturer':r['manufacturer'],'Orderable identity':r['mpn'] or 'NOT SELECTED','JLC/LCSC':r['jlc_code'] or 'NOT VERIFIED / NOT APPLICABLE','Package':r['package'],'Identity':r['identity_state'],'Fit':r['fit_state'],'References':' '.join(placements[r['id']]) or ('External plug-in module' if r['id'] in circuit['external_modules'] else 'Not fitted in P0'),'Footprint candidate':r['footprint_candidate'] or 'NOT ASSIGNED'}
 if 'contact_material' in r:fields['Contact material']=r['contact_material']
 if 'application_suitability_status' in r:fields['Application suitability']=r['application_suitability_status']
 body='## Identity\n\n| Field | Value |\n|---|---|\n'+'\n'.join(f'| {k} | {esc(v)} |' for k,v in fields.items())+'\n\n## Intended function\n\n'+r['role']+'\n\n## Recorded findings\n\n'
 for fact in r['facts']:body+=esc(fact)+'\n\n'
 body+='## Pin map\n\nPin assignments below are electrical evidence or explicitly logical placeholders. They are not footprint qualification.\n\n| Pin | Function |\n|---|---|\n'+'\n'.join(f'| {esc(k)} | {esc(v)} |' for k,v in r['pins'].items())+'\n\n'
 body+='## Documents and models\n\n'
 if not r['assets']:body+='No original model or source binary was recovered for this record in this package. See the sources and the local download manifest; no nominal model is presented as an exact replacement.\n\n'
 for a in r['assets']:
  f=R/a['path'];dest=R/'doc/public/assets'/a['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
  body+=f'[{f.name}](/assets/{a["path"]}) — {esc(a["kind"])}; applicability: {esc(a["match"])}.\n\nSource: [{a["source_url"]}]({a["source_url"]})\n\nSHA-256: `{a["sha256"]}`.\n\n'
 if r['id']=='pot':body+='[Interactive original manufacturer model](/models/index.html) · [Nominal layout drawing](/assets/panel-study.svg). The exact pot is not an exact module/board assembly model.\n\n'
 body+='## Coverage and unresolved questions\n\n**Footprint independently qualified: NO. Factory order approved: NO. Bench result: NOT TESTED.**\n\n'
 for gap in r['open_questions']:body+='- '+esc(gap)+'\n'
 body+='\nThe presence of a part number, datasheet or model closes none of these remaining gates automatically.\n\n## Sources\n\n'
 for id in r['source_ids']:
  s=sources[id];body+=f'### {esc(s["title"])}\n\n[{s["url"]}]({s["url"]})\n\nEvidence state: `{s["retrieval"]}`. {esc(s["evidence_note"])}\n\n'
 if not r['source_ids']:body+='Values and package constraints are authored design requirements, not manufacturer-verified specifications of a selected orderable part. Select the exact item and add its evidence before placement.\n'
 allpages['components/records/'+r['id']]={'title':r['mpn'] or (r['id']+' / supplier selection open'),'order':cat.index(r)+1,'body':body}
body='## Component-first reference\n\nThe table is generated from the component records. Exact identity, footprint qualification, factory acceptance and actual test evidence remain separate. No record represents a qualified PCB.\n\n| Part | Function | Identity | CAD assets |\n|---|---|---|---|\n'
for r in cat:body+=f'| [{esc(r["mpn"] or r["id"])}](/docs/components/records/{r["id"]}/) | {esc(r["role"])} | {r["identity_state"]} | {len(r["assets"])} retained files |\n'
body+='\n## Working views\n\n[UI simulation](/prototype/index.html) · [Panel study](/assets/panel-study.svg) · [Architecture drawing](/assets/architecture.svg) · [Original pot 3D](/models/index.html).\n'
allpages['components/index']={'title':'Component catalogue','order':1,'body':body}
# Source list remains explicit even for unassigned future candidates.
body='## Retrieval status\n\nFiles not present remain absent; source URLs are not proof of binary retention. New local downloads require review.\n\n'
for s in src:body+=f'### {s["title"]}\n\n[{s["url"]}]({s["url"]})\n\n**{s["retrieval"]}** — {s["evidence_note"]}\n\n'
allpages['components/sources']={'title':'Source manifest and availability','order':99,'body':body}
for slug,p in allpages.items():
 f=D/(slug+'.mdx');f.parent.mkdir(parents=True,exist_ok=True)
 f.write_text('---\n# GENERATED by scripts/build_docs.py\ntitle: '+json.dumps(p['title'])+'\nsidebar_position: '+str(p['order'])+'\n---\n\n'+p['body'].strip()+'\n')
# Canonical stdlib renderer. No optional dependency: same bytes in every environment.
# Covers exactly the subset used by design/narrative-pages.json and the generated
# component-record bodies above: headings (## / ###), fenced ```code blocks, pipe
# tables, bullet/numbered lists, paragraphs, and inline **bold**/`code`/[link](url).
def inline(s):
 s=html.escape(s,quote=False)
 s=re.sub(r'`([^`]+?)`',lambda m:'<code>'+m.group(1)+'</code>',s)
 s=re.sub(r'\*\*([^*]+?)\*\*',r'<strong>\1</strong>',s)
 s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',lambda m:'<a href="'+m.group(2)+'">'+m.group(1)+'</a>',s)
 return s
def table_cells(line):
 line=line.strip()
 if line.startswith('|'):line=line[1:]
 if line.endswith('|'):line=line[:-1]
 return [c.strip().replace('\\|','|') for c in re.split(r'(?<!\\)\|',line)]
def render(text):
 lines=text.split('\n');out=[];i=0;n=len(lines)
 while i<n:
  line=lines[i]
  if line.strip()=='':i+=1;continue
  if line.startswith('```'):
   i+=1;code=[]
   while i<n and not lines[i].startswith('```'):code.append(lines[i]);i+=1
   i+=1;out.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>');continue
  if line.startswith('### '):out.append('<h3>'+inline(line[4:])+'</h3>');i+=1;continue
  if line.startswith('## '):out.append('<h2>'+inline(line[3:])+'</h2>');i+=1;continue
  if line.startswith('# '):out.append('<h1>'+inline(line[2:])+'</h1>');i+=1;continue
  if line.lstrip().startswith('|'):
   tbl=[]
   while i<n and lines[i].lstrip().startswith('|'):tbl.append(lines[i]);i+=1
   head=table_cells(tbl[0]);rows=[table_cells(r) for r in tbl[2:]] if len(tbl)>1 else []
   t='<table><thead><tr>'+''.join('<th>'+inline(h)+'</th>' for h in head)+'</tr></thead><tbody>'
   for r in rows:t+='<tr>'+''.join('<td>'+inline(c)+'</td>' for c in r)+'</tr>'
   out.append(t+'</tbody></table>');continue
  if re.match(r'^-\s+',line):
   items=[]
   while i<n and re.match(r'^-\s+',lines[i]):items.append(lines[i][2:].strip());i+=1
   out.append('<ul>'+''.join('<li>'+inline(it)+'</li>' for it in items)+'</ul>');continue
  if re.match(r'^\d+\.\s+',line):
   items=[]
   while i<n and re.match(r'^\d+\.\s+',lines[i]):items.append(re.sub(r'^\d+\.\s+','',lines[i]));i+=1
   out.append('<ol>'+''.join('<li>'+inline(it)+'</li>' for it in items)+'</ol>');continue
  para=[line];i+=1
  while i<n and lines[i].strip()!='' and not lines[i].startswith(('#','```','|')) and not re.match(r'^-\s+|^\d+\.\s+',lines[i]):
   para.append(lines[i]);i+=1
  out.append('<p>'+inline(' '.join(para))+'</p>')
 return '\n'.join(out)
def name(slug):return slug.replace('/','__')+'.html'
def linkfix(s):
 s=re.sub(r'href="/docs/([^"]*?)"',lambda m:'href="'+name(m[1].rstrip('/').removesuffix('/index'))+'"',s)
 # special category index target
 s=s.replace('href="components.html"','href="components__index.html"')
 for pref in ['assets','prototype','models']:s=s.replace(f'="/{pref}/',f'="../doc/public/{pref}/')
 return s
css='''*{box-sizing:border-box}body{margin:0;background:#eeeade;color:#173535;font:16px/1.65 system-ui,sans-serif}header{border-bottom:1px solid #aabcb3;background:#faf7ee;padding:22px max(24px,calc((100vw - 1140px)/2))}header a{color:inherit}main{max-width:1140px;margin:auto;padding:30px 24px 70px}h1{font-size:36px;line-height:1.2;letter-spacing:-.025em}h2{margin-top:2.2em}h3{margin-top:1.8em}p,li{max-width:95ch}a{color:#215e57;overflow-wrap:anywhere}pre{background:#173535;color:#f2f0e8;border-radius:6px;padding:18px;overflow:auto}code{font-size:.9em;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #b7c7bf;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#dce4db}.tag{color:#a24c32;font-size:12px;font-weight:750;letter-spacing:.15em}img{max-width:100%;height:auto}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:15px}.card{border:1px solid #b7c7bf;border-radius:8px;padding:18px;background:#f8f5ec}input{width:100%;font:inherit;padding:12px;background:#faf8f0;border:1px solid #9bb0a4;border-radius:5px;margin:10px 0 24px}.warning{border-left:4px solid #a9593d;padding:12px 18px;background:#f7e6d4}.crumb{font-size:13px}.row{display:flex;gap:18px;flex-wrap:wrap}button{font:inherit;padding:8px 16px}footer{margin-top:50px;font-size:13px;color:#65786d}@media(max-width:600px){h1{font-size:27px}table{display:block;overflow-x:auto}main{padding:20px 14px}header{padding:20px 14px}}'''
(O/'style.css').write_text(css)
for slug,p in allpages.items():
 content=linkfix(render(p['body']))
 (O/name(slug)).write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(p["title"])} · SCOPE10</title><link rel="stylesheet" href="style.css"><header><div class="tag">ZUDO / SCOPE 10 / P0</div><a href="index.html">Project catalogue</a> · <a href="../doc/public/prototype/index.html">UI simulation</a></header><main><div class="crumb">{html.escape(slug)}</div><h1>{html.escape(p["title"])}</h1>{content}<footer>Pre-layout evidence. No factory approval or hardware measurements are implied.</footer></main></html>')
cards=''
for slug,p in allpages.items():cards+=f'<article class="card"><a href="{name(slug)}"><strong>{html.escape(p["title"])}</strong></a><div class="crumb">{html.escape(slug)}</div></article>'
(O/'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ZUDO SCOPE 10 · P0 handoff</title><link rel="stylesheet" href="style.css"><header><div class="tag">ZUDO / ENGINEERING HANDOFF / 2026-09-26</div><h1>Ten signals. One screen.</h1><p>A factory-soldered first carrier for CV, LFO and low-audio waveform monitoring.</p></header><main><p class="warning"><strong>PRE-LAYOUT — NOT FOR FABRICATION.</strong> Native schematic drafts and an outline-only PCB are included. Display power/driver integration, exact footprints and hardware tests remain open.</p><div class="row"><a href="../doc/public/prototype/index.html">Operate the synthetic UI</a><a href="../doc/public/models/index.html">Inspect the original pot model</a><a href="../START_HERE.md">Local handoff instructions</a><a href="../hardware/kicad/zudo-scope10-p0.kicad_pro">KiCad project</a></div><img src="../doc/public/assets/panel-study.png" alt="250 by 180 mm panel envelope with central portrait LCD and ten control pairs"><h2>Evidence and design reference</h2><label for="search">Find a component or topic</label><input id="search" placeholder="e.g. mux, power, TLV9064, firmware…"><div class="cards">'''+cards+'''</div><footer>All electrical assembly is assigned to the factory. Synthetic UI and nominal envelopes are not hardware-test evidence.</footer></main><script>document.querySelector('#search').addEventListener('input',e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>c.hidden=!c.textContent.toLowerCase().includes(q))})</script></html>''')
(R/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=offline/index.html"><title>SCOPE10 handoff</title><p><a href="offline/index.html">Open the project catalogue</a></p><p><a href="doc/public/prototype/index.html">Open the synthetic UI</a></p></html>')
(R/'reports/doc-generation.json').write_text(json.dumps({'mdx_pages':len(allpages),'component_records':len(cat),'offline_pages':len(allpages)+1,'native_zudo_doc_build':'NOT_RUN'},indent=2)+'\n')
print('Generated',len(allpages),'MDX pages and offline reference')
