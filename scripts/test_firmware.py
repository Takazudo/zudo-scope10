#!/usr/bin/env python3
"""Host-only tests. Never claims Pico target build or hardware operation."""
from pathlib import Path
import subprocess,tempfile,json,shutil
root=Path(__file__).resolve().parents[1]
cc=shutil.which('cc') or shutil.which('gcc')
if not cc:raise SystemExit('A host C compiler is required')
with tempfile.TemporaryDirectory() as t:
 exe=Path(t)/'test_core'
 cmd=[cc,'-std=c11','-Wall','-Wextra','-Werror','-pedantic','-O2','-I'+str(root/'firmware/src'),str(root/'firmware/src/scope_core.c'),str(root/'firmware/tests/test_core.c'),'-lm','-o',str(exe)]
 build=subprocess.run(cmd,capture_output=True,text=True);print(build.stdout+build.stderr,end='');build.check_returncode()
 run=subprocess.run([str(exe)],capture_output=True,text=True);print(run.stdout+run.stderr,end='');run.check_returncode()
 (root/'reports/firmware-host-tests.json').write_text(json.dumps({'host_compiler':cc,'result':'PASS','output':run.stdout,'target_build':'NOT_RUN','hardware_tests':'NOT_RUN'},indent=2)+'\n')
