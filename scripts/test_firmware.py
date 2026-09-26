#!/usr/bin/env python3
"""Host-only tests. Never claims Pico target build or hardware operation."""
from pathlib import Path
import subprocess,tempfile,json,shutil
root=Path(__file__).resolve().parents[1]
cc=shutil.which('cc') or shutil.which('gcc')
if not cc:raise SystemExit('A host C compiler is required')
src=root/'firmware/src'
suites={'test_core':[src/'scope_core.c',root/'firmware/tests/test_core.c'],
        'test_acq':[src/'scope_core.c',src/'acq_engine.c',root/'firmware/tests/test_acq.c'],
        'test_lcd':[src/'scope_core.c',src/'lcd_bridge.c',src/'scope_render.c',root/'firmware/tests/test_lcd.c']}
outputs={}
with tempfile.TemporaryDirectory() as t:
 for name,files in suites.items():
  exe=Path(t)/name
  cmd=[cc,'-std=c11','-Wall','-Wextra','-Werror','-pedantic','-O2','-I'+str(src),*map(str,files),'-lm','-o',str(exe)]
  build=subprocess.run(cmd,capture_output=True,text=True);print(build.stdout+build.stderr,end='');build.check_returncode()
  run=subprocess.run([str(exe)],capture_output=True,text=True);print(run.stdout+run.stderr,end='');run.check_returncode()
  outputs[name]=run.stdout
 (root/'reports/firmware-host-tests.json').write_text(json.dumps({'host_compiler':cc,'result':'PASS','output':outputs['test_core'],'suites':outputs,'target_build':'NOT_RUN','hardware_tests':'NOT_RUN'},indent=2)+'\n')
