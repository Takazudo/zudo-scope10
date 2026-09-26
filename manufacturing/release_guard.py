#!/usr/bin/env python3
from pathlib import Path
import json,sys
r=Path(__file__).resolve().parents[1]
g=json.loads((r/'design/release-gates.json').read_text())
open_gates=[x['id']+' '+x['title'] for x in g['gates'] if x['status']!='CLOSED' or not x.get('evidence_files')]
if open_gates or not g.get('release_allowed'):
 print('REFUSED: no order files may be generated from this pre-layout handoff.\n'+'\n'.join(open_gates));sys.exit(2)
print('Evidence markers present. Independently review them before approving a quote.')
