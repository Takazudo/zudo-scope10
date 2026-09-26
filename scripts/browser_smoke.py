#!/usr/bin/env python3
"""Browser smoke checks: inline DOM/canvas checks plus an HTTP mode.

Inline mode injects local HTML/JS bytes via page.set_content() — no URL
navigation, so it works even where loopback navigation is blocked.

HTTP mode (the default now that loopback navigation works in this
environment; pass --inline-only to skip it) serves the repo with
scripts/serve.py on a free local port and drives Chromium against real
http://127.0.0.1 URLs, covering what inline mode cannot: the offline
catalogue at /, the ten-pane UI simulator, the standalone Three.js/GLTFLoader
GLB viewer (needs a same-origin fetch of the .glb, which set_content() cannot
provide), and the built zfb site in doc/dist.

Chromium is pre-installed at /opt/pw-browsers; never run `playwright install`.
"""
from pathlib import Path
import argparse
import fcntl
import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import closing, contextmanager

from playwright.sync_api import sync_playwright

R = Path(__file__).resolve().parents[1]
LOCK_DIR = Path('/tmp/x-wt-teams-zudo-scope10-locks')
PORT_RANGE = range(8100, 8200)
# Headless Chromium needs a software GL backend to get a non-blank WebGL
# canvas out of the GLTF/Three.js viewer; swiftshader is bundled with the
# Playwright Chromium build under /opt/pw-browsers.
CHROMIUM_ARGS = ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist']


def find_chromium():
    """Resolve the Chromium binary under /opt/pw-browsers.

    Not hardcoded to one revision folder name (e.g. chromium-1194): the
    Playwright-managed browser cache names it after the pinned build, and
    that number moves when the pinned Playwright version changes.
    """
    base = Path('/opt/pw-browsers')
    if base.is_dir():
        for candidate in sorted(base.glob('chromium-*/chrome-linux/chrome')):
            return str(candidate)
    on_path = shutil.which('chromium') or shutil.which('chromium-browser')
    if on_path:
        return on_path
    raise SystemExit('No Chromium executable found under /opt/pw-browsers; refusing to run `playwright install`.')


@contextmanager
def held_port():
    """Pick a free local port, holding an flock for the caller's duration.

    Shared with other topics that also serve this repo during CI/agent runs:
    the lock file name encodes the port so unrelated smoke runs never race
    for the same one.
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    for port in PORT_RANGE:
        lock_path = LOCK_DIR / f'port-{port}.lock'
        fh = open(lock_path, 'w')
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            continue
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                fh.close()
                continue
        try:
            yield port
            return
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()
    raise SystemExit(f'No free port in {PORT_RANGE.start}-{PORT_RANGE.stop - 1}')


@contextmanager
def running_server(port):
    proc = subprocess.Popen(
        [sys.executable, str(R / 'scripts/serve.py'), '--port', str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(R),
    )
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/index.html', timeout=0.5).close()
                break
            except Exception:
                if proc.poll() is not None:
                    raise SystemExit(f'scripts/serve.py exited early (port {port})')
                time.sleep(0.1)
        else:
            raise SystemExit(f'scripts/serve.py did not become ready on port {port}')
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def screenshot_nonblank(png_bytes):
    """True if the screenshot paints more than one color.

    Reads the compositor's own output (a real screenshot) rather than the
    WebGL canvas's backing buffer: three.js's renderer does not set
    `preserveDrawingBuffer`, so by the time page.evaluate() can run
    canvas.toDataURL() or gl.readPixels() the buffer has already been
    swapped/cleared for the next frame and reads back blank even when the
    model visibly rendered.
    """
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(png_bytes)).convert('RGB')
    colors = img.getcolors(maxcolors=img.width * img.height)
    return colors is None or len(colors) > 1


def run_inline(browser, results, errors):
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.on('pageerror', lambda e: errors.append(str(e)))
    html = (R / 'offline/index.html').read_text()
    html = html.replace('<link rel="stylesheet" href="style.css">', '<style>' + (R / 'offline/style.css').read_text() + '</style>')
    html = re.sub(r'<img [^>]+>', '', html)
    page.set_content(html)
    page.fill('#search', 'TLV9064')
    assert page.locator('.card:visible').count() == 1
    results.append('Inline offline catalogue search')
    html = (R / 'doc/public/prototype/index.html').read_text().replace(
        '<script src="scope-ui.js"></script>', '<script>' + (R / 'doc/public/prototype/scope-ui.js').read_text() + '</script>'
    )
    page.set_content(html)
    assert page.locator('input[type=range]').count() == 10
    assert page.locator('input[type=radio]').count() == 30
    for i, v in [(0, 1000), (5, 3000)]:
        page.locator(f'#time-{i}').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input",{bubbles:true}))}', v)
    a = page.locator('#out-0').inner_text()
    b = page.locator('#out-5').inner_text()
    assert a != b
    page.click('#link')
    assert page.locator('#out-5').inner_text() == a
    page.click('#link')
    assert page.locator('#out-5').inner_text() == b
    page.click('#hold')
    assert page.locator('#hold').get_attribute('aria-pressed') == 'true'
    page.wait_for_timeout(100)
    one = page.locator('#screen').evaluate('(e)=>e.toDataURL()')
    page.wait_for_timeout(100)
    assert one == page.locator('#screen').evaluate('(e)=>e.toDataURL()')
    results.append('Ten controls / three ranges / link restores local positions / hold freezes pixels')
    page.close()


def run_http(browser, port, results, errors):
    base = f'http://127.0.0.1:{port}'

    # 1. Offline catalogue at the repo root, loaded over HTTP, search works.
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.on('pageerror', lambda e: errors.append(f'catalogue: {e}'))
    page.goto(f'{base}/offline/index.html', wait_until='networkidle')
    assert page.locator('.card').count() > 0
    page.fill('#search', 'TLV9064')
    assert page.locator('.card:visible').count() == 1
    results.append('HTTP offline catalogue loads and search filters cards')
    page.close()

    # 2. Ten-pane UI simulator: time controls, radio choices, linked-time
    # restore, HOLD, and no horizontal overflow at 390px.
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    ui_errors = []
    page.on('pageerror', lambda e: ui_errors.append(str(e)))
    page.goto(f'{base}/doc/public/prototype/index.html', wait_until='networkidle')
    assert page.locator('input[type=range]').count() == 10
    assert page.locator('input[type=radio]').count() == 30
    for i, v in [(0, 1000), (5, 3000)]:
        page.locator(f'#time-{i}').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input",{bubbles:true}))}', v)
    a = page.locator('#out-0').inner_text()
    b = page.locator('#out-5').inner_text()
    assert a != b, 'per-pane time controls did not diverge'
    page.click('#link')
    assert page.locator('#out-5').inner_text() == a, 'linked time did not restore the local value'
    page.click('#link')
    assert page.locator('#out-5').inner_text() == b, 'unlinking did not restore the other local value'
    page.click('#hold')
    assert page.locator('#hold').get_attribute('aria-pressed') == 'true'
    # Let the in-flight rAF frame from the instant of the click land before
    # sampling: that one frame can still show the pre-freeze waveform over a
    # real HTTP navigation, which is a one-frame scheduling artifact, not
    # evidence that HOLD failed to freeze the canvas.
    page.wait_for_timeout(300)
    frozen_a = page.locator('#screen').evaluate('(e)=>e.toDataURL()')
    page.wait_for_timeout(150)
    frozen_b = page.locator('#screen').evaluate('(e)=>e.toDataURL()')
    assert frozen_a == frozen_b, 'HOLD did not freeze the screen canvas'
    page.screenshot(path=str(R / 'reports/ui-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_timeout(150)
    overflow = page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
    assert overflow, '390px viewport has horizontal document overflow'
    page.screenshot(path=str(R / 'reports/ui-mobile.png'), full_page=True)
    assert not ui_errors, f'console/page errors on the ten-pane UI: {ui_errors}'
    results.append('HTTP ten-pane UI: time controls, radios, link restore, HOLD freeze, no 390px overflow, no console errors')
    page.close()

    # 3. Standalone Three.js/GLTFLoader GLB viewer: loads the model with no
    # console errors, non-blank canvas captured.
    page = browser.new_page(viewport={'width': 1000, 'height': 700})
    glb_errors = []
    page.on('pageerror', lambda e: glb_errors.append(str(e)))
    page.on('console', lambda m: glb_errors.append(m.text) if m.type == 'error' else None)
    page.goto(f'{base}/doc/public/models/index.html', wait_until='networkidle')
    page.wait_for_function(
        "document.querySelector('#status').textContent.includes('Original geometry loaded')",
        timeout=15000,
    )
    page.wait_for_timeout(150)  # let a post-load render frame land before capture
    shot = page.locator('#view').screenshot(path=str(R / 'reports/ui-glb-viewer.png'))
    assert screenshot_nonblank(shot), 'GLB viewer screenshot is a single flat color (blank)'
    assert not glb_errors, f'console/page errors in the GLB viewer: {glb_errors}'
    results.append('HTTP GLB viewer: model loads, no console errors, non-blank canvas captured')
    page.close()

    # 4. The built zfb site in doc/dist serves and its pages load.
    dist_errors = []
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    page.on('pageerror', lambda e: dist_errors.append(str(e)))
    for path in ('/doc/dist/docs/getting-started/index.html', '/doc/dist/docs/components/index.html'):
        resp = page.goto(f'{base}{path}', wait_until='networkidle')
        assert resp.ok, f'{path} did not return 200 (got {resp.status})'
        assert page.locator('body').count() == 1
    assert not dist_errors, f'console/page errors in the built zfb site: {dist_errors}'
    results.append('HTTP built zfb site (doc/dist) serves getting-started and components pages')
    page.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inline-only', action='store_true', help='skip the HTTP mode (e.g. no loopback navigation)')
    args = parser.parse_args()

    errors = []
    results = []
    http_ok = not args.inline_only
    chromium_path = find_chromium()

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium_path, headless=True, args=CHROMIUM_ARGS)
        try:
            run_inline(browser, results, errors)
            if not args.inline_only:
                with held_port() as port, running_server(port):
                    run_http(browser, port, results, errors)
        except AssertionError as e:
            errors.append(str(e) or 'assertion failed')
        except Exception as e:  # surfaced in the report rather than a bare traceback
            errors.append(f'{type(e).__name__}: {e}')
        finally:
            browser.close()

    report = {
        'result': 'PASS' if not errors else 'FAIL',
        'mode': 'Inline local HTML/JS bytes plus HTTP navigation via scripts/serve.py' if http_ok else 'Inline local HTML/JS bytes only (--inline-only)',
        'checks': results,
        'page_errors': errors,
        'not_run': [] if http_ok else ['HTTP/file URL loading', 'Standalone ESM/GLB model viewer', 'Built zfb site (doc/dist)'],
        'native_zudo_doc_build': 'checked separately by `pnpm build` in doc/ (see reports/doc-generation.json)',
    }
    (R / 'reports/browser-smoke.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == '__main__':
    main()
