#!/usr/bin/env bash
# Build llama.cpp (Vulkan backend, RADV/Mesa on gfx1151) against the SAME
# pinned source tree as the HIP build, into third_party/llama.cpp/build-714-vk.
# Pinned commit comes from configs/validated-stack.json["llama_cpp"]["commit"]
# (one pin, two backends: build-714 = HIP is never touched by this script).
# Idempotent: skips the build if the fingerprint (commit + backend + active
# ICD identity + cmake flags) matches. LLAMA_COMMIT overrides the pin.
#
# Prerequisites (llama.cpp's build docs at the pin, Vulkan/Linux/system-packages):
#   sudo apt-get install -y mesa-vulkan-drivers vulkan-tools libvulkan-dev glslc spirv-headers
#   (mesa-vulkan-drivers = the RADV ICD; vulkan-tools = vulkaninfo; glslc +
#   spirv-headers compile the compute shaders at build time).
# No-root fallback: the build-side packages extract cleanly into a user
# prefix, e.g.
#   mkdir -p ~/vkdeps && cd /tmp && apt-get download libvulkan1 libvulkan-dev \
#       glslc spirv-headers vulkan-tools libshaderc1 \
#   && for d in *.deb; do dpkg-deb -x "$d" ~/vkdeps; done
#   VULKAN_DEPS_PREFIX=~/vkdeps bash scripts/06-build-llama-vulkan.sh
# (libvulkan1 makes the libvulkan.so symlink resolvable inside the prefix;
# runtime against the system Mesa ICD needs only mesa-vulkan-drivers +
# libvulkan1, which are usually already installed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/llama_build.sh
source "$ROOT/scripts/lib/llama_build.sh"

LLAMA_DIR="$ROOT/third_party/llama.cpp"
STACK="$ROOT/configs/validated-stack.json"
REPO="https://github.com/ggml-org/llama.cpp.git"
BUILD_DIR="$LLAMA_DIR/build-714-vk"
BUILD_FINGERPRINT="$BUILD_DIR/llama-build-fingerprint.json"
COMMIT="${LLAMA_COMMIT:-$(python3 -c 'import json;print(json.load(open("'"$STACK"'"))["llama_cpp"]["commit"])')}"

echo "llama.cpp source: $REPO"
echo "llama.cpp commit : $COMMIT"
echo "llama.cpp build  : $BUILD_DIR (Vulkan; the HIP build-714 is not touched)"

for cmd in cmake git python3 curl tar; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: required command not found: $cmd" >&2
        echo "  Debian/Ubuntu:  sudo apt-get install $cmd" >&2
        exit 1
    }
done

# --- Vulkan prerequisites (actionable hints, VULKAN_DEPS_PREFIX support) ------
# VULKAN_DEPS_PREFIX points at a dpkg-deb -x extraction of the build-side
# packages (see header) when the system packages cannot be installed.
VULKAN_DEPS_PREFIX="${VULKAN_DEPS_PREFIX:-}"
VDP_USR=""
if [ -n "$VULKAN_DEPS_PREFIX" ]; then
    VDP_USR="$VULKAN_DEPS_PREFIX/usr"
    export PATH="$VDP_USR/bin:$PATH"
    export LD_LIBRARY_PATH="$VDP_USR/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
fi

die_hint() { # die_hint <what> <hint...>
    echo "ERROR: $1" >&2
    shift
    for line in "$@"; do echo "       $line" >&2; done
    exit 1
}

# 1) vulkaninfo (runtime ICD visibility; package vulkan-tools, ICD from
#    mesa-vulkan-drivers) — also the ICD-identity probe below.
VULKANINFO="$(command -v vulkaninfo || true)"
[ -n "$VULKANINFO" ] || die_hint "vulkaninfo not found (need it to verify the ICD and record its identity)" \
    "sudo apt-get install -y mesa-vulkan-drivers vulkan-tools"

# 2) Vulkan loader headers + import library (package libvulkan-dev).
VK_HEADER=""
for d in /usr/include ${VDP_USR:+$VDP_USR/include}; do
    [ -f "$d/vulkan/vulkan_core.h" ] && VK_HEADER="$d/vulkan/vulkan_core.h"
done
[ -n "$VK_HEADER" ] || die_hint "Vulkan headers not found (vulkan/vulkan_core.h)" \
    "sudo apt-get install -y libvulkan-dev" \
    "(or point VULKAN_DEPS_PREFIX at a dpkg-deb extraction)"

# 3) glslc (compute-shader compiler; llama.cpp does NOT vendor shaderc at
#    this pin — ggml/src/ggml-vulkan/CMakeLists.txt does
#    find_package(Vulkan COMPONENTS glslc REQUIRED) and shells out to glslc).
GLSLC="$(command -v glslc || true)"
[ -n "$GLSLC" ] || die_hint "glslc not found" \
    "sudo apt-get install -y glslc" \
    "(Debian/Ubuntu 'glslc' ships shaderc's compiler; the pin's build docs list it)"

# 4) SPIRV-Headers (find_package(SPIRV-Headers CONFIG REQUIRED) at the pin;
#    NOT pulled in by libvulkan-dev — the pin's build docs say so explicitly).
SPIRV_HPP=""
for d in /usr/include ${VDP_USR:+$VDP_USR/include}; do
    [ -f "$d/spirv/unified1/spirv.hpp" ] && SPIRV_HPP="$d/spirv/unified1/spirv.hpp"
done
[ -n "$SPIRV_HPP" ] || die_hint "SPIRV-Headers not found (spirv/unified1/spirv.hpp)" \
    "sudo apt-get install -y spirv-headers"

# libvulkan.so (import lib; runtime .so.1 comes from libvulkan1/mesa and is
# expected system-wide — checked so the built binary can actually load).
# (grep without -q: it must read ALL of ldconfig's output, else ldconfig
# hits SIGPIPE under `set -o pipefail` and the check false-negatives.)
if ! ldconfig -p 2>/dev/null | grep "libvulkan.so" >/dev/null; then
    die_hint "libvulkan.so / libvulkan.so.1 not found in the linker cache" \
        "sudo apt-get install -y libvulkan-dev libvulkan1"
fi

# --- Source acquisition (same dance as 05-build-llama.sh, shared tree) --------
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

# --- Active ICD identity (part of the evidence AND the fingerprint) -----------
# RADV vs the AMD proprietary driver matters for the comparison cells: record
# which one the loader actually sees (vulkaninfo --summary, GPU0 block).
VULKANINFO_SUMMARY="$(vulkaninfo --summary 2>/dev/null || true)"
ICD_JSON="$(VULKANINFO_SUMMARY="$VULKANINFO_SUMMARY" python3 <<'PY'
import json, os, re

text = os.environ["VULKANINFO_SUMMARY"]
def grab(key, block):
    m = re.search(rf"^\s*{key}\s*=\s*(.+?)\s*$", block, re.M)
    return m.group(1) if m else None

gpu0 = text.split("GPU1:")[0]
fields = {
    "apiVersion": grab("apiVersion", gpu0),
    "deviceName": grab("deviceName", gpu0),
    "driverID": grab("driverID", gpu0),
    "driverName": grab("driverName", gpu0),
    "driverInfo": grab("driverInfo", gpu0),
}
m = re.search(r"Vulkan Instance Version:\s*([\d.]+)", text)
instance = m.group(1) if m else None
if not fields["driverID"]:
    print(json.dumps({"error": "no GPU0/driverID found in vulkaninfo --summary"}))
    raise SystemExit(0)
print(json.dumps({"instance_version": instance, "gpu0": fields}, sort_keys=True))
PY
)"
ICD_ERROR="$(printf '%s' "$ICD_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("error",""))')"
[ -z "$ICD_ERROR" ] || die_hint "vulkaninfo did not report a GPU/driver (RADV/AMD ICD not visible): $ICD_ERROR" \
    "sudo apt-get install -y mesa-vulkan-drivers vulkan-tools" \
    "(a headless host can force an ICD via VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json)"
ICD_LABEL="$(ICD_JSON="$ICD_JSON" python3 <<'PY'
import json, os
d = json.loads(os.environ["ICD_JSON"])["gpu0"]
did = (d.get("driverID") or "").upper()
if "RADV" in did:
    print("RADV")
elif did.startswith("DRIVER_ID_AMD"):
    print("AMD")
else:
    print(did.replace("DRIVER_ID_", "").replace("MESA_", ""))
PY
)"
VK_INSTANCE_VERSION="$(ICD_JSON="$ICD_JSON" python3 -c 'import json,os;print(json.loads(os.environ["ICD_JSON"])["instance_version"])')"
ICD_DEVICE_INFO="$(ICD_JSON="$ICD_JSON" python3 -c 'import json,os;d=json.loads(os.environ["ICD_JSON"])["gpu0"];print(d["deviceName"], "|", d["driverInfo"])')"
echo "Vulkan ICD    : $ICD_LABEL ($ICD_DEVICE_INFO)"

# --- Idempotent build ----------------------------------------------------------
mkdir -p "$BUILD_DIR"
EXPECTED_BUILD_FINGERPRINT="$(mktemp "$BUILD_DIR/.llama-build-fingerprint.expected.XXXXXX")"
trap 'rm -f "$EXPECTED_BUILD_FINGERPRINT"' EXIT
write_llama_vulkan_build_fingerprint "$EXPECTED_BUILD_FINGERPRINT" \
    "$ACTUAL_COMMIT" "$ICD_JSON" "libvulkan.so.1 (instance $VK_INSTANCE_VERSION)"

if [ ! -x "$BUILD_DIR/bin/llama-server" ]; then
    echo "llama.cpp Vulkan build missing; configuring GGML_VULKAN=ON (GGML_HIP=OFF)"
    rebuild=1
elif ! llama_build_fingerprint_matches "$EXPECTED_BUILD_FINGERPRINT" "$BUILD_FINGERPRINT"; then
    echo "llama.cpp Vulkan build fingerprint changed (commit/ICD/loader); reconfiguring"
    rebuild=1
else
    rebuild=0
fi

if [ "$rebuild" -eq 1 ]; then
    EXTRA_CMAKE=()
    if [ -n "$VULKAN_DEPS_PREFIX" ]; then
        # CMAKE_PREFIX_PATH covers headers + SPIRV-Headers config; the Debian
        # multiarch lib dir needs CMAKE_LIBRARY_PATH for find_library(vulkan).
        EXTRA_CMAKE+=(-DCMAKE_PREFIX_PATH="$VDP_USR"
                      -DCMAKE_LIBRARY_PATH="$VDP_USR/lib/x86_64-linux-gnu")
    fi
    cmake -S "$LLAMA_DIR" -B "$BUILD_DIR" -DGGML_VULKAN=ON -DGGML_HIP=OFF \
        -DCMAKE_BUILD_TYPE=Release "${EXTRA_CMAKE[@]}"
    cmake --build "$BUILD_DIR" -j "${MAX_JOBS:-16}"
    mv "$EXPECTED_BUILD_FINGERPRINT" "$BUILD_FINGERPRINT"
else
    echo "llama.cpp Vulkan build fingerprint matches; no rebuild needed"
    rm -f "$EXPECTED_BUILD_FINGERPRINT"
fi
trap - EXIT

# --- Smoke + record ------------------------------------------------------------
SMOKE_FIRST_LINE="$("$BUILD_DIR/bin/llama-server" --version 2>&1 | head -n 1)"
echo "smoke: $SMOKE_FIRST_LINE"
echo "== devices ($BUILD_DIR/bin/llama-server --list-devices) =="
"$BUILD_DIR/bin/llama-server" --list-devices 2>&1 | tee "$BUILD_DIR/.llama-list-devices.txt"
if ! grep -qi "vulkan" "$BUILD_DIR/.llama-list-devices.txt"; then
    echo "WARN: --list-devices shows no Vulkan device (ICD $ICD_LABEL active for vulkaninfo — check VK_ICD_FILENAMES)" >&2
fi

# MTP-depth discovery at the pin 4df29be4 (read from the checkout above, not
# assumed): the depth flag is --spec-draft-n-max (common/arg.cpp, "number of
# tokens to draft", default n_max=3 from common/common.h), and the draft-mtp
# driver (common/speculative.cpp) SELF-CHAINS the single trained qwen35 MTP
# head up to n_max drafts per step — the depth is NOT fixed at 1 by the
# checkpoint (the n_mtp_layers clamp only fires for chain_heads checkpoints
# with more than one trained nextn layer, e.g. step35). mtp4 IS expressible:
# --spec-type draft-mtp --spec-draft-n-max 4. mtp cells pin depth 1 explicitly.
MTP_DEPTH_JSON='{
  "flag": "--spec-draft-n-max",
  "default": 3,
  "mechanism": "draft-mtp self-chains the single trained qwen35 MTP head up to n_max drafted tokens per step (draft() feeds the head its own h output back); depth is configurable, NOT fixed by the checkpoint",
  "evidence": "third_party/llama.cpp@4df29be4: common/arg.cpp:4077 (--spec-draft-n-max, env LLAMA_ARG_SPEC_DRAFT_N_MAX), common/common.h:325 (draft n_max default 3), common/speculative.cpp:1274+ (draft-mtp impl; single-head else-branch chains h_row), :1371 (n_max clamped to n_mtp_layers only for chain_heads checkpoints)",
  "mtp4_expressible": true,
  "runner_depths": {"mtp": 1, "mtp4": 4},
  "note": "hip mtp receipts measured 2026-08-17 predate this discovery and ran at the implicit default n_max=3; cells booted by run-cell-gguf.sh now pass the depth explicitly and record it in server_flags"
}'

python3 - "$STACK" "$REPO" "$ACTUAL_COMMIT" "$BUILD_DIR" "$ICD_LABEL" "$ICD_JSON" "$MTP_DEPTH_JSON" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

stack_path, repo, commit, build_dir, icd_label, icd_json, depth_json = sys.argv[1:8]
stack = json.loads(Path(stack_path).read_text(encoding="utf-8"))
# Merge, never replace (same discipline as 05-build-llama.sh): the
# mtp_depth discovery record is knowledge, not build state — a rebuild must
# never clobber it. Write only when content changed (idempotent clean tree).
vk = stack.setdefault("llama_cpp_vulkan", {})
vk.update({
    "source_repo": repo,
    "commit": commit,
    "backend": "vulkan",
    "build_dir": "third_party/llama.cpp/build-714-vk",
    "icd": icd_label,
    "icd_details": json.loads(icd_json),
    "mtp_depth": json.loads(depth_json),
    "built_at": dt.date.today().isoformat(),
})
new_text = json.dumps(stack, indent=2) + "\n"
if new_text != Path(stack_path).read_text(encoding="utf-8"):
    Path(stack_path).write_text(new_text, encoding="utf-8")
PY

echo "OK: llama-server built at $BUILD_DIR/bin/llama-server (commit $COMMIT, Vulkan, ICD $ICD_LABEL)"
