#!/usr/bin/env bash
# Builds every firmware target (scope10_diagnostic, scope10_acq) against the real
# Raspberry Pi Pico SDK, one target at a time so warnings are counted per target.
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

TARGETS=(scope10_diagnostic scope10_acq)
LOG_DIR="$(mktemp -d)"
trap 'rm -rf "$LOG_DIR"' EXIT

TARGET_ARGS=()
TOTAL_WARNINGS=0
for TARGET in "${TARGETS[@]}"; do
    log "Building $TARGET"
    cmake --build "$BUILD_DIR" --target "$TARGET" -j"$(nproc)" 2>&1 | tee "$LOG_DIR/$TARGET.log"
    UF2="$BUILD_DIR/$TARGET.uf2"
    if [ ! -f "$UF2" ]; then
        log "ERROR: expected UF2 output missing at $UF2"
        exit 1
    fi
    WARNINGS="$(grep -c "warning:" "$LOG_DIR/$TARGET.log" || true)"
    TOTAL_WARNINGS=$((TOTAL_WARNINGS + WARNINGS))
    TARGET_ARGS+=("$TARGET" "$(stat -c%s "$UF2")" "$(sha256sum "$UF2" | cut -d' ' -f1)" "$WARNINGS")
    log "$TARGET: $UF2 ($(stat -c%s "$UF2") bytes), warnings: $WARNINGS"
done

TOOLCHAIN_VERSION="$(arm-none-eabi-gcc --version | head -1)"
CMAKE_VERSION="$(cmake --version | head -1)"

mkdir -p "$(dirname "$REPORT")"
python3 - "$REPORT" "$PICO_SDK_TAG" "$SDK_HEAD_SHA" "$TOOLCHAIN_VERSION" "$CMAKE_VERSION" \
    "$TOTAL_WARNINGS" "${TARGET_ARGS[@]}" <<'PY'
import json, sys
report, sdk_tag, sdk_sha, toolchain, cmake_v, total_warnings = sys.argv[1:7]
rest = sys.argv[7:]
notes = {
    "scope10_diagnostic": "Slow USB CSV diagnostic; LCD held dark, serial output rate-limited.",
    "scope10_acq": "10 kS/s/channel sequential acquisition engine (nominal design, see firmware/ACQUISITION.md); no rate, settle or jitter measured, G05 stays OPEN.",
}
targets = []
for i in range(0, len(rest), 4):
    name, size, sha, warnings = rest[i:i + 4]
    targets.append({
        "target": name,
        "uf2_path": f"firmware/build/{name}.uf2",
        "uf2_size_bytes": int(size),
        "uf2_sha256": sha,
        "warning_count": int(warnings),
        "notes": notes.get(name, ""),
    })
data = {
    "pico_sdk_tag": sdk_tag,
    "pico_sdk_commit_sha": sdk_sha,
    "toolchain": toolchain,
    "cmake": cmake_v,
    "picotool_strategy": "PICOTOOL_FETCH_FROM_GIT_PATH (CMake FetchContent builds picotool 2.1.1 once into reference/downloads/picotool-fetch; no libusb-1.0-dev required)",
    "board": "pico",
    "compile_flags": "-Wall -Wextra",
    "targets": targets,
    "warning_count": int(total_warnings),
    "warning_baseline": 0,
    "notes": "Target UF2 builds only; hardware/bench behaviour is NOT tested here (G05 and G06 stay OPEN).",
}
with open(report, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

log "Wrote $REPORT"
log "Warnings (all targets): $TOTAL_WARNINGS"

if [ "$TOTAL_WARNINGS" -ne 0 ]; then
    log "WARNING: build produced $TOTAL_WARNINGS warning(s) with -Wall -Wextra; see report for baseline."
fi
