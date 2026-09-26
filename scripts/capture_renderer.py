#!/usr/bin/env python3
"""Deterministic host capture of the real firmware renderer into a PNG (#44 / #26 part 3).

Compiles firmware/tools/capture_renderer.c against the unmodified scope_core.c /
scope_render.c with the host cc, the same way scripts/test_firmware.py builds its host
suites, runs it to get a raw RGB565 320x480 framebuffer dump, and encodes that into
reports/renderer-capture.png. No display hardware and no target build are involved --
strictly a host tool; G06 (display integration) stays OPEN.

The PNG writer below is dependency-free and hand-written down to the DEFLATE stream: it
stores each scanline in uncompressed ("stored") DEFLATE blocks rather than calling
zlib's compressor, so the output bytes depend only on the pixel data, never on a
particular zlib build's compression heuristics -- the byte-identical-regeneration
requirement (validate_extra._check_renderer_capture) must hold across machines, not
just within one process. It still uses the stdlib `zlib` module for the two required
checksums (CRC-32 per chunk, Adler-32 for the zlib stream), which are fixed, portable
arithmetic, not compression output. No new CI dependency either way.
"""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

R = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 320, 480
SRC = R / 'firmware/src'
TOOLS = R / 'firmware/tools'
PNG_OUT = R / 'reports/renderer-capture.png'
META_OUT = R / 'reports/renderer-capture.json'


def host_cc():
    cc = shutil.which('cc') or shutil.which('gcc')
    if not cc:
        raise SystemExit('A host C compiler is required')
    return cc


def build_capture(cc=None):
    """Compiles and runs the capture tool. Returns (raw_rgb565_bytes, host_compiler)."""
    cc = cc or host_cc()
    with tempfile.TemporaryDirectory() as t:
        exe = Path(t) / 'capture_renderer'
        raw = Path(t) / 'capture.raw'
        files = [SRC / 'scope_core.c', SRC / 'scope_render.c', TOOLS / 'capture_renderer.c']
        cmd = [cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-O2',
               '-I' + str(SRC), *map(str, files), '-lm', '-o', str(exe)]
        build = subprocess.run(cmd, capture_output=True, text=True)
        print(build.stdout + build.stderr, end='')
        build.check_returncode()
        run = subprocess.run([str(exe), str(raw)], capture_output=True, text=True)
        print(run.stdout + run.stderr, end='')
        run.check_returncode()
        data = raw.read_bytes()
    if len(data) != WIDTH * HEIGHT * 2:
        raise SystemExit(f'capture_renderer wrote {len(data)} bytes, expected {WIDTH * HEIGHT * 2}')
    return data, cc


def _rgb565_scanlines(raw):
    """Row-major little-endian RGB565 -> PNG scanlines (filter type 0 + 3 bytes/pixel)."""
    rows = []
    for y in range(HEIGHT):
        row = bytearray(1 + WIDTH * 3)
        off = y * WIDTH * 2
        for x in range(WIDTH):
            v = raw[off + x * 2] | (raw[off + x * 2 + 1] << 8)
            r5, g6, b5 = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
            p = 1 + x * 3
            row[p] = (r5 * 255 + 15) // 31
            row[p + 1] = (g6 * 255 + 31) // 63
            row[p + 2] = (b5 * 255 + 15) // 31
        rows.append(bytes(row))
    return b''.join(rows)


def _deflate_stored(data):
    """DEFLATE stream made only of uncompressed ("stored") blocks (RFC 1951 SS3.2.4):
    fully portable, since it never invokes an actual compression algorithm."""
    out = bytearray()
    n = len(data)
    i = 0
    while True:
        chunk = data[i:i + 65535]
        final = 1 if i + len(chunk) >= n else 0
        out.append(final)
        length = len(chunk)
        out += struct.pack('<H', length)
        out += struct.pack('<H', (~length) & 0xFFFF)
        out += chunk
        i += length
        if final:
            break
    return bytes(out)


def _zlib_stream(data):
    """RFC 1950 zlib wrapper (CMF/FLG header, DEFLATE payload, big-endian Adler-32)."""
    header = bytes([0x78, 0x01])  # 32K window, deflate, no preset dict, valid FCHECK
    return header + _deflate_stored(data) + struct.pack('>I', zlib.adler32(data) & 0xFFFFFFFF)


def _png_chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)


def encode_png(raw):
    """Minimal 8-bit truecolor PNG: no timestamp/text chunks, so it depends only on the
    pixel data -- running it twice on the same input gives byte-identical output."""
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    idat = _zlib_stream(_rgb565_scanlines(raw))
    return sig + _png_chunk(b'IHDR', ihdr) + _png_chunk(b'IDAT', idat) + _png_chunk(b'IEND', b'')


def build_png(cc=None):
    """Returns (png_bytes, meta_dict) without touching the reports/ directory."""
    raw, cc = build_capture(cc)
    png = encode_png(raw)
    meta = {
        'width': WIDTH,
        'height': HEIGHT,
        'sha256': hashlib.sha256(png).hexdigest(),
        'source': 'firmware/tools/capture_renderer.c',
        'host_compiler': cc,
        'channels': (
            'ch1(index0): sine, normal, UNCAL (invalid calibration). '
            'ch2: square, normal. ch3: ramp, normal. '
            'ch4: sine, VIEW CLIP (~4.0V swing at +-3V RANGE, raw codes off the ADC rails). '
            'ch5: square, normal. ch6: ramp, normal. '
            'ch7: sine, ADC SAT (raw codes driven to 0/4095). '
            'ch8: square, normal. ch9: ramp, normal. ch10: sine, normal. '
            'HOLD and LINK are both latched for the captured frame.'
        ),
        'note': ('Deterministic host capture of the unmodified scope_render.c / scope_core.c '
                 'renderer through a recording display_port.h backend (firmware/tools/'
                 'capture_renderer.c). No display hardware is involved; G06 stays OPEN.'),
    }
    return png, meta


def main():
    png, meta = build_png()
    PNG_OUT.parent.mkdir(parents=True, exist_ok=True)
    PNG_OUT.write_bytes(png)
    META_OUT.write_text(json.dumps(meta, indent=2) + '\n')
    print(f'Wrote {PNG_OUT} ({len(png)} bytes) and {META_OUT}')


if __name__ == '__main__':
    sys.exit(main())
