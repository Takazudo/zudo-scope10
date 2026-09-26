#!/usr/bin/env python3
"""Serve this project on loopback only. No credentials or cloud deployment."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import argparse,functools
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8000);a=p.parse_args()
h=functools.partial(SimpleHTTPRequestHandler,directory=str(root))
print(f'Open http://127.0.0.1:{a.port}/ — Ctrl+C stops the server.',flush=True)
try:ThreadingHTTPServer(('127.0.0.1',a.port),h).serve_forever()
except KeyboardInterrupt:pass
