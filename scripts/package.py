#!/usr/bin/env python3
"""Build a portable ZIP with hashes. Packaging does NOT grant fabrication approval."""
from pathlib import Path
import hashlib,json,zipfile
R=Path(__file__).resolve().parents[1]
paths=sorted(p for p in R.rglob('*') if p.is_file() and p.name!='SHA256SUMS.txt' and not any(s in p.parts for s in ['__pycache__','node_modules','build','.git','.zfb','dist']) and p.suffix not in ['.pyc','.zip.tmp'])
(R/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(R).as_posix()+'\n' for p in paths))
paths.append(R/'SHA256SUMS.txt');out=R.parent/(R.name+'.zip')
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=8) as z:
 for p in paths:z.write(p,arcname=R.name+'/'+p.relative_to(R).as_posix())
with zipfile.ZipFile(out) as z:
 bad=z.testzip()
 if bad:raise SystemExit('Corrupt ZIP entry: '+bad)
print(json.dumps({'archive':str(out),'files':len(paths),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'fabrication_approval':False},indent=2))
