#!/usr/bin/env bash
# Builds firmware/scope10_diagnostic.uf2 against the real Raspberry Pi Pico SDK.
#
# Picotool strategy: SDK 2.x needs picotool present at CMake configure time
# (tools/CMakeLists.txt pico_init_picotool() requires exactly version 2.1.1,
# matching the pinned pico-sdk tag). Rather than build+install picotool by
# hand, this script sets PICOTOOL_FETCH_FROM_GIT_PATH to a cache dir; the SDK's
# own CMake then clones and builds picotool into that dir itself (once) via
# FetchContent, and reuses it on later runs. This avoids a separate libusb
# dependency: picotool builds in this "fetch" mode without libusb-1.0-dev
# installed (offline UF2 post-processing does not need the USB backend).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PICO_SDK_TAG="2.1.1"
PICO_SDK_SHA="bddd20f928ce76142793bef434d4f75f4af6e433"
PICO_SDK_REPO="https://github.com/raspberrypi/pico-sdk.git"

CACHE_DIR="$ROOT/reference/downloads"
SDK_CACHE_DIR="$CACHE_DIR/pico-sdk"
PICOTOOL_CACHE_DIR="$CACHE_DIR/picotool-fetch"
BUILD_DIR="$ROOT/firmware/build"
REPORT="$ROOT/reports/firmware-target-build.json"

log() { echo "[build_firmware] $*" >&2; }

if [ -n "${PICO_SDK_PATH:-}" ]; then
    log "Honoring caller-provided PICO_SDK_PATH=$PICO_SDK_PATH"
else
    if [ ! -d "$SDK_CACHE_DIR/.git" ]; then
        log "Cloning pico-sdk (tag $PICO_SDK_TAG) into gitignored cache $SDK_CACHE_DIR"
        mkdir -p "$CACHE_DIR"
        git clone --branch "$PICO_SDK_TAG" --depth 1 "$PICO_SDK_REPO" "$SDK_CACHE_DIR"
    fi
    export PICO_SDK_PATH="$SDK_CACHE_DIR"
fi

SDK_HEAD_SHA="$(git -C "$PICO_SDK_PATH" rev-parse HEAD)"
if [ "$SDK_HEAD_SHA" != "$PICO_SDK_SHA" ]; then
    log "WARNING: PICO_SDK_PATH HEAD ($SDK_HEAD_SHA) does not match the pinned commit ($PICO_SDK_SHA)."
    log "Continuing with the checkout provided, but the pin in this script and the report below assume $PICO_SDK_TAG / $PICO_SDK_SHA."
fi

log "Initialising the tinyusb submodule (required by pico_stdio_usb)"
git -C "$PICO_SDK_PATH" submodule update --init lib/tinyusb

mkdir -p "$PICOTOOL_CACHE_DIR"
export PICOTOOL_FETCH_FROM_GIT_PATH="$PICOTOOL_CACHE_DIR"

log "Configuring CMake (PICO_SDK_PATH=$PICO_SDK_PATH)"
rm -rf "$BUILD_DIR"
cmake -S "$ROOT/firmware" -B "$BUILD_DIR" -G Ninja -DCMAKE_BUILD_TYPE=Release

BUILD_LOG="$(mktemp)"
trap 'rm -f "$BUILD_LOG"' EXIT

log "Building scope10_diagnostic"
cmake --build "$BUILD_DIR" -j"$(nproc)" 2>&1 | tee "$BUILD_LOG"

UF2="$BUILD_DIR/scope10_diagnostic.uf2"
if [ ! -f "$UF2" ]; then
    log "ERROR: expected UF2 output missing at $UF2"
    exit 1
fi

WARNING_COUNT="$(grep -c "warning:" "$BUILD_LOG" || true)"
UF2_SIZE="$(stat -c%s "$UF2")"
UF2_SHA256="$(sha256sum "$UF2" | cut -d' ' -f1)"
TOOLCHAIN_VERSION="$(arm-none-eabi-gcc --version | head -1)"
CMAKE_VERSION="$(cmake --version | head -1)"

mkdir -p "$(dirname "$REPORT")"
python3 - "$REPORT" "$PICO_SDK_TAG" "$SDK_HEAD_SHA" "$TOOLCHAIN_VERSION" "$CMAKE_VERSION" \
    "$UF2" "$UF2_SIZE" "$UF2_SHA256" "$WARNING_COUNT" <<'PY'
import json, sys
report, sdk_tag, sdk_sha, toolchain, cmake_v, uf2_path, uf2_size, uf2_sha256, warnings = sys.argv[1:10]
data = {
    "pico_sdk_tag": sdk_tag,
    "pico_sdk_commit_sha": sdk_sha,
    "toolchain": toolchain,
    "cmake": cmake_v,
    "picotool_strategy": "PICOTOOL_FETCH_FROM_GIT_PATH (CMake FetchContent builds picotool 2.1.1 once into reference/downloads/picotool-fetch; no libusb-1.0-dev required)",
    "target": "scope10_diagnostic",
    "board": "pico",
    "uf2_path": "firmware/build/scope10_diagnostic.uf2",
    "uf2_size_bytes": int(uf2_size),
    "uf2_sha256": uf2_sha256,
    "compile_flags": "-Wall -Wextra",
    "warning_count": int(warnings),
    "warning_baseline": 0,
    "notes": "Target UF2 build only; hardware/bench behaviour is NOT tested here (G06 stays OPEN). LCD held dark, serial output rate-limited (unchanged from the diagnostic's host-tested behaviour).",
}
with open(report, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

log "Wrote $REPORT"
log "UF2: $UF2 ($UF2_SIZE bytes, sha256 $UF2_SHA256)"
log "Warnings: $WARNING_COUNT"

if [ "$WARNING_COUNT" -ne 0 ]; then
    log "WARNING: build produced $WARNING_COUNT warning(s) with -Wall -Wextra; see report for baseline."
fi
