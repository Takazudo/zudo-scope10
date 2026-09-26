#!/usr/bin/env python3
"""Download missing primary-source assets locally; never label an HTML error as CAD/PDF.
Only downloads the explicit manifest allowlist. No credentials, no archive extraction.
Existing files are never silently overwritten. Record URL/time/hash for review.
"""
from pathlib import Path
import argparse, json, hashlib, urllib.request, urllib.parse, datetime, sys
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args()
sources=json.loads((ROOT/'catalog/sources.json').read_text())['sources'];log=[]
for s in sources:
 u=s['url'];path=urllib.parse.urlsplit(u).path.lower()
 if not path.endswith(('.pdf','.zip')):continue
 ext='.pdf' if path.endswith('.pdf') else '.zip';dest=ROOT/'reference/downloaded'/f"{s['id']}{ext}"
 if not args.execute:print(s['id'],u);continue
 row={'id':s['id'],'url':u,'path':str(dest.relative_to(ROOT)),'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  if dest.exists():data=dest.read_bytes();row['state']='EXISTING_NOT_OVERWRITTEN'
  else:
   req=urllib.request.Request(u,headers={'User-Agent':'zudo-scope10-source-collector/0.1'})
   with urllib.request.urlopen(req,timeout=35) as res:
    data=res.read(35_000_001);row['final_url']=res.url;row['content_type']=res.headers.get('Content-Type','')
   if len(data)>35_000_000:raise ValueError('File exceeds 35 MB limit')
   if ext=='.pdf' and not data.startswith(b'%PDF-'):raise ValueError('Expected PDF, received different content')
   if ext=='.zip' and not data.startswith(b'PK'):raise ValueError('Expected ZIP, received different content')
   dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);row['state']='DOWNLOADED_UNREVIEWED'
  row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 except Exception as e:row.update(state='UNAVAILABLE',error=str(e))
 log.append(row);print(s['id'],row['state'])
if args.execute:
 (ROOT/'reports/source-fetch-local.json').write_text(json.dumps(log,indent=2)+'\n')
 sys.exit(1 if any(x['state']=='UNAVAILABLE' for x in log) else 0)
