#!/usr/bin/env bash
# Build llama.cpp (HIP, gfx1151) against ROCm 7.14 into third_party/llama.cpp/build-714.
# Pinned commit comes from configs/validated-stack.json["llama_cpp"]["commit"].
# Idempotent: skips the build if the fingerprint matches. LLAMA_COMMIT / ROCM_PREFIX override.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/llama_build.sh
source "$ROOT/scripts/lib/llama_build.sh"
# shellcheck source=scripts/lib/rocm.sh
source "$ROOT/scripts/lib/rocm.sh"

ROCM_PREFIX="${ROCM_PREFIX:-$HOME/rocm-7.14.0}"
LLAMA_DIR="$ROOT/third_party/llama.cpp"
STACK="$ROOT/configs/validated-stack.json"
REPO="https://github.com/ggml-org/llama.cpp.git"
# gfx1151 (Radeon 8060S iGPU). Written as a literal assignment because
# tests/test_llama_build.py asserts the exact pin in this script.
AMDGPU_TARGETS=gfx1151
COMMIT="${LLAMA_COMMIT:-$(python3 -c 'import json;print(json.load(open("'"$STACK"'"))["llama_cpp"]["commit"])')}"

[ -x "$ROCM_PREFIX/bin/hipcc" ] || {
    echo "ERROR: $ROCM_PREFIX/bin/hipcc missing — run scripts/install-rocm-7.14.sh" >&2
    exit 1
}
# The HIP build needs the CMake package config; only fall back to the
# historical /opt/rocm install when the 7.14 SDK lacks it (choice is recorded
# below and ends up in validated-stack.json via the toolchain field).
if [ ! -f "$ROCM_PREFIX/lib/cmake/hip/hip-config.cmake" ]; then
    if [ -f /opt/rocm/lib/cmake/hip/hip-config.cmake ]; then
        ROCM_VER_FALLBACK="$(detect_rocm_version /opt/rocm)"
        echo "NOTE: $ROCM_PREFIX lacks lib/cmake/hip; falling back to /opt/rocm ($ROCM_VER_FALLBACK)" >&2
        ROCM_PREFIX=/opt/rocm
    else
        echo "ERROR: $ROCM_PREFIX/lib/cmake/hip/hip-config.cmake missing and /opt/rocm has none either — reinstall ROCm" >&2
        exit 1
    fi
fi
ROCM_BUILD_PREFIX="$(canonical_rocm_prefix "$ROCM_PREFIX")"
export PATH="$ROCM_BUILD_PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$ROCM_BUILD_PREFIX/lib:${LD_LIBRARY_PATH:-}"
ROCM_VER="$(detect_rocm_version "$ROCM_BUILD_PREFIX")"
echo "Selected ROCm: $ROCM_BUILD_PREFIX (version $ROCM_VER)"
BUILD_DIR="$(llama_build_dir "$LLAMA_DIR" "$ROCM_BUILD_PREFIX" "$ROCM_VER" "")"
BUILD_FINGERPRINT="$BUILD_DIR/llama-build-fingerprint.json"
echo "llama.cpp source: $REPO"
echo "llama.cpp commit : $COMMIT"
echo "llama.cpp build  : $BUILD_DIR"

for cmd in cmake git python3 curl tar; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: required command not found: $cmd" >&2
        echo "  Debian/Ubuntu:  sudo apt-get install $cmd" >&2
        echo "  Fedora/RHEL:    sudo dnf install $cmd" >&2
        echo "  Arch:           sudo pacman -S $cmd" >&2
        exit 1
    }
done

# --- Source acquisition ------------------------------------------------------
# Clone once (3 retries for the flaky proxy), then fetch and detach at the
# pinned commit on every run. If GitHub git transport keeps failing, fall back
# to the codeload tarball for the exact commit (no .git dir; identity is kept
# in .llama-commit). Existing uncommitted changes are never deleted.
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
    if [ -e "$LLAMA_DIR" ] && [ -n "$(find "$LLAMA_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
        echo "ERROR: $LLAMA_DIR exists but is not a llama.cpp checkout; move it aside first." >&2
        exit 1
    fi
    mkdir -p "$(dirname "$LLAMA_DIR")"
    if clone_with_retries && git -C "$LLAMA_DIR" fetch --depth 1 "$REPO" "$COMMIT"; then
        git -C "$LLAMA_DIR" checkout --detach FETCH_HEAD
    else
        echo "NOTE: git transport failed; falling back to codeload tarball for $COMMIT" >&2
        rm -rf "$LLAMA_DIR"
        mkdir -p "$LLAMA_DIR"
        curl -fL --retry 3 "https://codeload.github.com/ggml-org/llama.cpp/tar.gz/$COMMIT" |
            tar -xz --strip-components=1 -C "$LLAMA_DIR"
        printf '%s\n' "$COMMIT" >"$COMMIT_MARKER"
    fi
fi

if [ -d "$LLAMA_DIR/.git" ]; then
    CURRENT_COMMIT="$(git -C "$LLAMA_DIR" rev-parse HEAD 2>/dev/null || true)"
    if [ "$CURRENT_COMMIT" != "$COMMIT" ]; then
        if llama_has_tracked_changes "$LLAMA_DIR"; then
            llama_refuse_dirty_checkout "$LLAMA_DIR" \
                "switch llama.cpp from $CURRENT_COMMIT to $COMMIT"
            exit 1
        fi
        git -C "$LLAMA_DIR" fetch --depth 1 "$REPO" "$COMMIT"
        git -C "$LLAMA_DIR" checkout --detach FETCH_HEAD
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
    exit 1
fi
echo "llama.cpp checkout at $ACTUAL_COMMIT; working tree clean"

# The model this repo serves is qwen35; refuse to build a commit that dropped it.
if ! grep -q "qwen35" "$LLAMA_DIR/src/llama-arch.cpp"; then
    echo "ERROR: qwen35 architecture is not registered in src/llama-arch.cpp at $ACTUAL_COMMIT;" >&2
    echo "       pick a llama.cpp commit that still supports it (grep -n qwen35 src/llama-arch.cpp)." >&2
    exit 1
fi

# --- Idempotent build --------------------------------------------------------
mkdir -p "$BUILD_DIR"
EXPECTED_BUILD_FINGERPRINT="$(mktemp "$BUILD_DIR/.llama-build-fingerprint.expected.XXXXXX")"
trap 'rm -f "$EXPECTED_BUILD_FINGERPRINT"' EXIT
write_llama_build_fingerprint "$EXPECTED_BUILD_FINGERPRINT" \
    "$ACTUAL_COMMIT" "$ROCM_BUILD_PREFIX" "$ROCM_VER" "$AMDGPU_TARGETS"

if [ ! -x "$BUILD_DIR/bin/llama-server" ]; then
    echo "llama.cpp build missing; configuring HIP for $AMDGPU_TARGETS"
    rebuild=1
elif ! llama_build_fingerprint_matches "$EXPECTED_BUILD_FINGERPRINT" "$BUILD_FINGERPRINT"; then
    echo "llama.cpp build fingerprint changed; reconfiguring HIP for $AMDGPU_TARGETS"
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
    echo "llama.cpp build fingerprint matches; no rebuild needed"
    rm -f "$EXPECTED_BUILD_FINGERPRINT"
fi
trap - EXIT

# --- Smoke + record ----------------------------------------------------------
SMOKE_FIRST_LINE="$("$BUILD_DIR/bin/llama-server" --version 2>&1 | head -n 1)"
echo "smoke: $SMOKE_FIRST_LINE"

python3 - "$STACK" "$REPO" "$ACTUAL_COMMIT" "$AMDGPU_TARGETS" "$ROCM_BUILD_PREFIX" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

stack_path, repo, commit, arch, prefix = sys.argv[1:6]
stack = json.loads(Path(stack_path).read_text(encoding="utf-8"))
stack["llama_cpp"] = {
    "source_repo": repo,
    "commit": commit,
    "build_arch": arch,
    "toolchain": prefix,
    "backend": "HIP",
    "built_at": dt.date.today().isoformat(),
}
Path(stack_path).write_text(json.dumps(stack, indent=2) + "\n", encoding="utf-8")
PY

echo "OK: llama-server built at $BUILD_DIR/bin/llama-server (commit $COMMIT, $ROCM_VER, $AMDGPU_TARGETS)"
