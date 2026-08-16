#!/usr/bin/env bash
# Build vLLM from pinned upstream source for gfx1151 into the uv venv
# (TheRock torch). Idempotent: re-runs clone+shim+build. Control parallelism
# via MAX_JOBS; override toolchain via ROCM_PATH; override source via
# VLLM_REPO/VLLM_REF/VLLM_SRC.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# --- Pinned vLLM source: defaults come from the validated stack manifest. ----
# vllm.source_repo / vllm.commit pin the exact tree; vllm.patches lists the
# patch files (under patches/) that this script applies idempotently.
mapfile -t STACK_VLLM < <(python3 - "$ROOT/configs/validated-stack.json" <<'PY_STACK'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data["vllm"]["source_repo"])
print(data["vllm"]["commit"])
print("\n".join(data["vllm"].get("patches", [])))
PY_STACK
)
VALIDATED_VLLM_REPO="${STACK_VLLM[0]}"
VALIDATED_VLLM_REF="${STACK_VLLM[1]}"
VLLM_REPO="${VLLM_REPO:-$VALIDATED_VLLM_REPO}"
VLLM_REF="${VLLM_REF:-$VALIDATED_VLLM_REF}"
SRC="${VLLM_SRC:-third_party/vllm}"

if [ "$VLLM_REPO" = "$VALIDATED_VLLM_REPO" ] && [ "$VLLM_REF" = "$VALIDATED_VLLM_REF" ]; then
  echo "vLLM source: validated reference"
else
  echo "vLLM source: EXPERIMENTAL override (validated-stack claims do not apply)"
fi
# This repo builds upstream vLLM only; anything else is an explicit override.
case "$VLLM_REPO" in
  https://github.com/vllm-project/vllm.git|git@github.com:vllm-project/vllm.git) ;;
  *) echo "  note: non-upstream vLLM repo: $VLLM_REPO" ;;
esac
echo "  repo: $VLLM_REPO"
echo "  ref:  $VLLM_REF"

# uv lives in ~/.local/bin on this host.
export PATH="$HOME/.local/bin:$PATH"

# --- Toolchain selection -----------------------------------------------------
# Prefer the full 7.14 SDK at ~/rocm-7.14.0 (clang 23, complete cmake config
# set: hip, amd_comgr, rocblas, miopen, hiprand, rocprim, hipcub, rocthrust,
# rccl, ...). It is the ROCm this repo validates (host.recommended_rocm 7.14).
# Fall back to the host /opt/rocm (7.2.1, complete cmake configs, proven by
# muse-rocm) if the 7.14 tree lacks lib/cmake/hip. Either way we BUILD against
# a full host toolchain and rely on torch's bundled ROCm userspace at RUNTIME:
# vLLM's .so links libamdhip64.so.7 (SONAME, identical in 7.2.1 / 7.13.0a /
# 7.14); at runtime python loads torch's userspace libamdhip64.so.7 first (via
# torch's RPATH) and the already-loaded symbol set satisfies vLLM. Override
# with ROCM_PATH to force a specific tree.
# ROCM_PATH is exported so torch.utils.cpp_extension.ROCM_HOME picks it up and
# setup.py forwards it to cmake as -DROCM_PATH=.
export ROCM_PATH="${ROCM_PATH:-$HOME/rocm-7.14.0}"
if [ ! -d "$ROCM_PATH/lib/cmake/hip" ]; then
  echo "  ROCM_PATH=$ROCM_PATH has no lib/cmake/hip; falling back to /opt/rocm"
  export ROCM_PATH=/opt/rocm
fi
export HIP_PATH="${HIP_PATH:-$ROCM_PATH}"
# Put the chosen ROCm first so hipcc/hipconfig/amdclang come from one
# internally-consistent toolchain.
export PATH="$ROCM_PATH/bin:$HOME/.local/bin:$PATH"

echo "=== Toolchain (chosen: $ROCM_PATH) ==="
echo "  hipcc:   $(command -v hipcc)"
echo "  ROCM_PATH=$ROCM_PATH"
hipcc --version | sed 's/^/  hipcc> /' | head -3

# amdsmi must be importable at RUNTIME: vLLM's ROCm platform plugin calls
# amdsmi.amdsmi_init() during platform detection, and our amdsmi-import patch
# prepends `import amdsmi` to vllm/__init__.py. The venv does not have amdsmi
# on sys.path by default; expose the TheRock-bundled amdsmi (from the ROCm
# userspace tree torch ships) via a .pth. Its wrapper resolves its .so via a
# path RELATIVE TO THE PACKAGE FILE, so it must stay at its original location
# (a `pip install` copy would break that).
# The site dir is derived from the live venv interpreter (never hardcode a
# pythonX.Y path component); --no-sync is mandatory (a sync would drop the
# editable vllm install).
if ! VENV_SITE="$(uv run --no-sync python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])' 2>/dev/null)" || [ -z "$VENV_SITE" ]; then
  echo "ERROR: cannot locate the uv venv interpreter — is the venv bootstrapped?" >&2
  echo "       Run: uv sync --group vllm" >&2
  exit 1
fi
if [ ! -d "$VENV_SITE" ]; then
  echo "ERROR: venv site dir $VENV_SITE does not exist — bootstrap with: uv sync --group vllm" >&2
  exit 1
fi
VENV_ROCM="$VENV_SITE/_rocm_sdk_core"
AMD_PTH="$VENV_SITE/_amdsmi_therock.pth"
echo "$VENV_ROCM/share/amd_smi" > "$AMD_PTH"

# --- Install build backend deps ---------------------------------------------
# --no-build-isolation means the build backend must already live in the venv.
echo "=== Installing build backend deps (no-build-isolation needs them in-env) ==="
uv pip install "setuptools-scm>=8.0" "cmake>=3.26.1" "ninja" "wheel" "setuptools-rust>=1.9.0"

# --- Fetch or reuse the pinned source safely ---------------------------------
# Never delete an existing checkout: it may contain developer work. A checkout
# at another commit must be clean before this script changes HEAD.
mkdir -p "$(dirname "$SRC")"
if [ -e "$SRC" ] && [ ! -d "$SRC/.git" ]; then
  echo "ERROR: $SRC exists but is not a git checkout; choose VLLM_SRC or move it." >&2
  exit 1
fi
if [ ! -d "$SRC/.git" ]; then
  echo "=== Cloning vLLM @ $VLLM_REF ==="
  git clone --depth 1 "$VLLM_REPO" "$SRC"
fi

CURRENT_REF="$(git -C "$SRC" rev-parse HEAD 2>/dev/null || true)"
if [ "$CURRENT_REF" != "$VLLM_REF" ]; then
  if ! git -C "$SRC" diff --quiet --ignore-submodules HEAD -- ||
     ! git -C "$SRC" diff --cached --quiet; then
    echo "ERROR: $SRC has tracked changes at $CURRENT_REF; use a clean VLLM_SRC for another ref." >&2
    exit 1
  fi
  git -C "$SRC" fetch --depth 1 "$VLLM_REPO" "$VLLM_REF"
  git -C "$SRC" checkout --detach FETCH_HEAD
else
  echo "  checkout already at pinned commit; no fetch needed"
fi
ACTUAL_REF="$(git -C "$SRC" rev-parse HEAD)"
if [[ "$VLLM_REF" =~ ^[0-9a-fA-F]{40}$ ]] && [ "$ACTUAL_REF" != "$VLLM_REF" ]; then
  echo "ERROR: requested $VLLM_REF but checked out $ACTUAL_REF" >&2
  exit 1
fi
echo "  HEAD: $(git -C "$SRC" log --oneline -1)"

# --- Source patches (committed in patches/, listed in validated-stack.json) --
# Applied idempotently; the tracked-modification guard below pins the patch
# set to exactly what the manifest declares.
apply_pinned_patch() {
  local patch="$1"
  if git -C "$SRC" apply --check "$patch"; then
    git -C "$SRC" apply "$patch"
    echo "  applied $(basename "$patch")"
  elif git -C "$SRC" apply --reverse --check "$patch"; then
    echo "  already applied $(basename "$patch")"
  else
    echo "ERROR: $(basename "$patch") neither applies nor matches the source tree." >&2
    exit 1
  fi
}

# vllm-amdsmi-import.diff: vLLM's ROCm platform init imports amdsmi lazily and
# fails to see the TheRock shim unless amdsmi is imported up-front (gfx1151
# workaround; see muse-rocm docs/troubleshooting.md#amdsmi).
EXPECTED_FILES=()
for patch in "${STACK_VLLM[@]:2}"; do
  patch_path="$ROOT/$patch"
  if [ ! -f "$patch_path" ]; then
    echo "ERROR: manifest-listed patch missing: $patch_path" >&2
    exit 1
  fi
  apply_pinned_patch "$patch_path"
  mapfile -t -O "${#EXPECTED_FILES[@]}" EXPECTED_FILES < <(
    git -C "$SRC" apply --numstat "$patch_path" | awk '{print $3}'
  )
done

# Fail if tracked modifications extend beyond the manifest-declared patches.
# (Sort both lists: git diff --name-only is alphabetical, manifest order is not.)
mapfile -t PATCHED_FILES < <(git -C "$SRC" diff --name-only | sort)
mapfile -t EXPECTED_FILES < <(printf '%s\n' "${EXPECTED_FILES[@]}" | sort -u)
if [ "${PATCHED_FILES[*]}" != "${EXPECTED_FILES[*]}" ] ||
   ! git -C "$SRC" diff --cached --quiet; then
  echo "ERROR: $SRC contains tracked changes beyond the validated patches:" >&2
  git -C "$SRC" status --short >&2
  exit 1
fi
echo "  patches: $(git -C "$SRC" diff --stat | tail -1)"

# --- triton_kernels FetchContent override ------------------------------------
# vLLM main's cmake configure FetchContent-clones ROCm/triton (a large repo)
# for the triton_kernels package on ROCm builds. A pre-fetched copy at
# third_party/triton-kernels (blobs fetched + git-SHA-verified) bypasses that
# clone via the upstream-supported TRITON_KERNELS_SRC_DIR override. Only .py
# files are consumed by the install. Reproduce the prefetch in 3 steps:
#   1. blob tarball at the pinned SHA via jsDelivr:
#      curl -L -o tk.tar.gz "https://cdn.jsdelivr.net/gh/ROCm/triton@0f380657dbf3ee86eb57558ff71df24f03b5d4e7.tar.gz"
#   2. extract python/triton_kernels/triton_kernels/*.py into third_party/triton-kernels/
#   3. sha256-verify the blobs against the pin recorded in
#      configs/validated-stack.json (vllm.triton_kernels: ROCm/triton@0f380657...).
TRITON_KERNELS_DIR="$ROOT/third_party/triton-kernels"
if [ -f "$TRITON_KERNELS_DIR/__init__.py" ]; then
  export TRITON_KERNELS_SRC_DIR="$TRITON_KERNELS_DIR"
  echo "  triton_kernels: using local SHA-verified copy $TRITON_KERNELS_SRC_DIR"
fi

# --- Build (editable, no isolation so the build sees installed torch+ROCm) ---
# --no-build-isolation is REQUIRED: an isolated build would not see the TheRock
# torch + host ROCm and would fail.
#
# The Rust frontend (vllm._rust_tool_parser / vllm-rs CLI) is OPTIONAL: lazily
# imported only for the generic Rust tool parser and `vllm bench serve`. We
# skip the Rust build (avoids requiring a cargo toolchain). Set
# VLLM_REQUIRE_RUST_FRONTEND=1 (and install rustup) for a full build.
export VLLM_REQUIRE_RUST_FRONTEND="${VLLM_REQUIRE_RUST_FRONTEND:-0}"
export PYTORCH_ROCM_ARCH=gfx1151
export FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE
export MAX_JOBS="${MAX_JOBS:-16}"

echo "=== Building (PYTORCH_ROCM_ARCH=$PYTORCH_ROCM_ARCH MAX_JOBS=$MAX_JOBS VLLM_REQUIRE_RUST_FRONTEND=$VLLM_REQUIRE_RUST_FRONTEND toolchain=$ROCM_PATH) ==="
uv pip install -e "$SRC" --no-build-isolation

# vLLM declares numpy unpinned; its editable install may pull numpy 2.x. The
# TheRock torch wheel was built against numpy<2 (numpy 2.x breaks the torch C
# extension ABI), so force it back. vLLM itself works with numpy 1.26.x.
# vLLM may also drag in a scipy that uses np.long (removed in numpy 1.24);
# pin a numpy-1.26-compatible scipy.
uv pip install "numpy<2" "scipy<1.14" >/dev/null && echo "  pinned numpy<2 ($(uv pip show numpy | awk '/^Version:/{print $2}')), scipy<1.14 ($(uv pip show scipy | awk '/^Version:/{print $2}'))"

# --- Registry smoke: the model must be registered, not merely importable ----
echo "=== Registry smoke ==="
uv run --no-sync python -c "from vllm.model_executor.models.registry import _MULTIMODAL_MODELS; assert 'Qwen3_5ForConditionalGeneration' in _MULTIMODAL_MODELS; print('registry OK')"

echo "=== OK: vLLM built for gfx1151 ==="
echo "Verify with: uv run --no-sync python -c 'import vllm; print(vllm.__version__)'"
