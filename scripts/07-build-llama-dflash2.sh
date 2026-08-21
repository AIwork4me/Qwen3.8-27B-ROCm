#!/usr/bin/env bash
# Build the DFlash2 llama.cpp variant (HIP) for speculative decoding with
# incoai/Qwen3.8-27B-DFlash2 draft GGUFs.
#
# Source: ggml-org/llama.cpp PR #27342 ("spec : add DFlash2 support (local
# convolution + candidate selector)") — OPEN, not merged at the time of pinning.
# Pinned commit comes from configs/validated-stack.json
# ["llama_cpp_dflash2"]["commit"] (the PR head SHA; re-pin there when the PR
# moves or merges — scripts/gguf-quickstart.sh's WITH_DFLASH2=1 mode and the
# dflash2 receipts record what actually ran).
#
# Builds into third_party/llama.cpp/build-714-dflash2 — the pinned baseline
# (build-714) and Vulkan (build-714-vk) builds are never touched, so every
# existing receipt stays reproducible.
#
# AMDGPU_TARGETS defaults to the first GPU rocminfo reports (gfx1151 on the
# project reference host, gfx1100 on W7900-class hosts); export it to
# override. Toolchain resolution mirrors scripts/05-build-llama.sh
# (ROCM_PREFIX override honored; ~/rocm-7.14.0 preferred, /opt/rocm fallback).
#
# Idempotent: skips the build if the fingerprint matches.
# Env: LLAMA_COMMIT (override ref)  ROCM_PREFIX  AMDGPU_TARGETS  MAX_JOBS
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/llama_build.sh
source "$ROOT/scripts/lib/llama_build.sh"
# shellcheck source=scripts/lib/rocm.sh
source "$ROOT/scripts/lib/rocm.sh"

ROCM_PREFIX="${ROCM_PREFIX:-$HOME/rocm-7.14.0}"
LLAMA_DIR="$ROOT/third_party/llama.cpp"
STACK="$ROOT/configs/validated-stack.json"
REPO="$(python3 -c 'import json;print(json.load(open("'"$STACK"'"))["llama_cpp_dflash2"]["source_repo"])')"
PR_NUM="$(python3 -c 'import json;print(json.load(open("'"$STACK"'"))["llama_cpp_dflash2"]["pr"])')"
PINNED_COMMIT="$(python3 -c 'import json;print(json.load(open("'"$STACK"'"))["llama_cpp_dflash2"]["commit"])')"
COMMIT="${LLAMA_COMMIT:-$PINNED_COMMIT}"
BUILD_DIR="$LLAMA_DIR/build-714-dflash2"
BUILD_FINGERPRINT="$BUILD_DIR/llama-build-fingerprint.json"

# GPU target: the first concrete gfx* rocminfo lists (gfx1151 on the
# reference host, gfx1100 on W7900-class hosts); explicit override wins, and
# a headless sandbox falls back to the project reference arch rather than
# failing. Exactly four digits — rocminfo also lists generic families
# ("gfx11-generic") that the compiler refuses ("unsupported HIP gpu
# architecture: gfx11"), so those must never win the sort.
if [ -z "${AMDGPU_TARGETS:-}" ]; then
    AMDGPU_TARGETS="$({ "$ROCM_PREFIX/bin/rocminfo" 2>/dev/null || /opt/rocm/bin/rocminfo 2>/dev/null || rocminfo 2>/dev/null || true; } \
        | grep -oE 'gfx[0-9]{4}' | sort -u | head -n1 || true)"
    AMDGPU_TARGETS="${AMDGPU_TARGETS:-gfx1151}"
fi

[ -x "$ROCM_PREFIX/bin/hipcc" ] || {
    if [ -f /opt/rocm/bin/hipcc ]; then
        echo "NOTE: $ROCM_PREFIX/bin/hipcc missing; falling back to /opt/rocm" >&2
        ROCM_PREFIX=/opt/rocm
    else
        echo "ERROR: no hipcc found ($ROCM_PREFIX or /opt/rocm) — run scripts/install-rocm-7.14.sh" >&2
        exit 1
    fi
}
if [ ! -f "$ROCM_PREFIX/lib/cmake/hip/hip-config.cmake" ]; then
    if [ -f /opt/rocm/lib/cmake/hip/hip-config.cmake ]; then
        echo "NOTE: $ROCM_PREFIX lacks lib/cmake/hip; falling back to /opt/rocm" >&2
        ROCM_PREFIX=/opt/rocm
    else
        echo "ERROR: no hip CMake package config found — reinstall ROCm" >&2
        exit 1
    fi
fi
ROCM_BUILD_PREFIX="$(canonical_rocm_prefix "$ROCM_PREFIX")"
export PATH="$ROCM_BUILD_PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$ROCM_BUILD_PREFIX/lib:${LD_LIBRARY_PATH:-}"
ROCM_VER="$(detect_rocm_version "$ROCM_BUILD_PREFIX")"
echo "Selected ROCm: $ROCM_BUILD_PREFIX (version $ROCM_VER)"
echo "llama.cpp source: $REPO (PR #$PR_NUM)"
echo "llama.cpp commit : $COMMIT"
echo "llama.cpp build  : $BUILD_DIR (AMDGPU_TARGETS=$AMDGPU_TARGETS)"

for cmd in cmake git python3 curl; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: required command not found: $cmd" >&2
        exit 1
    }
done

# --- Source acquisition: clone once, then fetch the PR ref ---------------------
# The PR ref (refs/pull/<n>/head) resolves to the PR head; the checkout must
# land on exactly $COMMIT or the build refuses to proceed (same pin discipline
# as 05-build-llama.sh).
COMMIT_MARKER="$LLAMA_DIR/.llama-commit"

clone_with_retries() {
    local attempt
    for attempt in 1 2 3; do
        if git clone --filter=blob:none --no-checkout "$REPO" "$LLAMA_DIR"; then
            return 0
        fi
        echo "NOTE: clone attempt $attempt failed; cleaning up and retrying" >&2
        rm -rf "$LLAMA_DIR"
        sleep 3
    done
    return 1
}

if [ ! -d "$LLAMA_DIR/.git" ] && [ ! -f "$COMMIT_MARKER" ]; then
    if [ -e "$LLAMA_DIR" ] && [ -n "$(find "$LLAMA_DIR" -mindepth 1 -maxdepth 1 -not -name .git -print -quit 2>/dev/null)" ]; then
        echo "ERROR: $LLAMA_DIR exists but is not a llama.cpp checkout; move it aside first." >&2
        exit 1
    fi
    mkdir -p "$(dirname "$LLAMA_DIR")"
    clone_with_retries || { echo "ERROR: clone failed after 3 attempts" >&2; exit 1; }
fi

if [ -d "$LLAMA_DIR/.git" ]; then
    CURRENT_COMMIT="$(git -C "$LLAMA_DIR" rev-parse HEAD 2>/dev/null || true)"
    if [ "$CURRENT_COMMIT" != "$COMMIT" ]; then
        if llama_has_tracked_changes "$LLAMA_DIR"; then
            llama_refuse_dirty_checkout "$LLAMA_DIR" \
                "switch llama.cpp from ${CURRENT_COMMIT:-<empty>} to $COMMIT"
            exit 1
        fi
        # The PR head may not be on any branch: fetch the pull ref explicitly,
        # plus the pinned SHA directly (works after the PR merges, too).
        git -C "$LLAMA_DIR" fetch --depth 1 "$REPO" "$COMMIT" 2>/dev/null ||
            git -C "$LLAMA_DIR" fetch --depth 1 "$REPO" "refs/pull/$PR_NUM/head"
        git -C "$LLAMA_DIR" checkout --detach "$COMMIT"
    elif llama_has_tracked_changes "$LLAMA_DIR"; then
        llama_refuse_dirty_checkout "$LLAMA_DIR" "reuse the llama.cpp checkout at $CURRENT_COMMIT"
        exit 1
    fi
    ACTUAL_COMMIT="$(git -C "$LLAMA_DIR" rev-parse HEAD)"
else
    ACTUAL_COMMIT="$(cat "$COMMIT_MARKER")"
fi
if [ "$ACTUAL_COMMIT" != "$COMMIT" ]; then
    echo "ERROR: requested $COMMIT but checked out $ACTUAL_COMMIT" >&2
    echo "       (if PR #$PR_NUM moved, re-pin llama_cpp_dflash2.commit in configs/validated-stack.json)" >&2
    exit 1
fi
echo "llama.cpp checkout at $ACTUAL_COMMIT; working tree clean"

# Refuse to build a commit without the two DFlash2 essentials: the drafter
# model support and the spec wiring (guards a silent baseline-only build).
if ! grep -q "dflash" "$LLAMA_DIR/src/models/dflash.cpp" 2>/dev/null; then
    echo "ERROR: src/models/dflash.cpp missing/changed at $ACTUAL_COMMIT — not a DFlash2-capable commit?" >&2
    exit 1
fi
if ! grep -q "draft-dflash" "$LLAMA_DIR/common/speculative.cpp" 2>/dev/null; then
    echo "ERROR: 'draft-dflash' spec type not registered in common/speculative.cpp at $ACTUAL_COMMIT." >&2
    exit 1
fi

# --- Idempotent build --------------------------------------------------------
mkdir -p "$BUILD_DIR"
EXPECTED_BUILD_FINGERPRINT="$(mktemp "$BUILD_DIR/.llama-build-fingerprint.expected.XXXXXX")"
trap 'rm -f "$EXPECTED_BUILD_FINGERPRINT"' EXIT
write_llama_build_fingerprint "$EXPECTED_BUILD_FINGERPRINT" \
    "$ACTUAL_COMMIT" "$ROCM_BUILD_PREFIX" "$ROCM_VER" "$AMDGPU_TARGETS"

if [ ! -x "$BUILD_DIR/bin/llama-server" ]; then
    echo "DFlash2 build missing; configuring HIP for $AMDGPU_TARGETS"
    rebuild=1
elif ! llama_build_fingerprint_matches "$EXPECTED_BUILD_FINGERPRINT" "$BUILD_FINGERPRINT"; then
    echo "DFlash2 build fingerprint changed; reconfiguring HIP for $AMDGPU_TARGETS"
    rebuild=1
else
    rebuild=0
fi

if [ "$rebuild" -eq 1 ]; then
    cmake -S "$LLAMA_DIR" -B "$BUILD_DIR" -DGGML_HIP=ON \
        -DAMDGPU_TARGETS="$AMDGPU_TARGETS" -DGPU_TARGETS="$AMDGPU_TARGETS" \
        -DCMAKE_BUILD_TYPE=Release -DROCM_PATH="$ROCM_BUILD_PREFIX" \
        -Dhip_DIR="$ROCM_BUILD_PREFIX/lib/cmake/hip"
    cmake --build "$BUILD_DIR" -j "${MAX_JOBS:-16}"
    mv "$EXPECTED_BUILD_FINGERPRINT" "$BUILD_FINGERPRINT"
else
    echo "DFlash2 build fingerprint matches; no rebuild needed"
    rm -f "$EXPECTED_BUILD_FINGERPRINT"
fi
trap - EXIT

# --- Smoke + record ----------------------------------------------------------
SMOKE_FIRST_LINE="$("$BUILD_DIR/bin/llama-server" --version 2>&1 | head -n 1)"
echo "smoke: $SMOKE_FIRST_LINE"

python3 - "$STACK" "$ACTUAL_COMMIT" "$AMDGPU_TARGETS" "$ROCM_BUILD_PREFIX" "$BUILD_DIR" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

stack_path, commit, arch, prefix, build_dir = sys.argv[1:6]
stack = json.loads(Path(stack_path).read_text(encoding="utf-8"))
# Merge, never replace: only the build facts move; the pin itself and the
# spec-draft evidence notes are owned by this file's committed values.
lc = stack.setdefault("llama_cpp_dflash2", {})
lc.update({
    "built_at": dt.date.today().isoformat(),
    "build_arch": arch,
    "toolchain": prefix,
    "build_dir": build_dir.removeprefix(str(Path(stack_path).parent.parent) + "/"),
})
new_text = json.dumps(stack, indent=2) + "\n"
if new_text != Path(stack_path).read_text(encoding="utf-8"):
    Path(stack_path).write_text(new_text, encoding="utf-8")
PY

echo "OK: DFlash2 llama-server at $BUILD_DIR/bin/llama-server (commit $COMMIT, $ROCM_VER, $AMDGPU_TARGETS)"
echo "    serve with: WITH_DFLASH2=1 bash scripts/gguf-quickstart.sh"
