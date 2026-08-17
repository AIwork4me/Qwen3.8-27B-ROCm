#!/usr/bin/env bash
set -euo pipefail

fail() {
    echo "FAIL: $1" >&2
    echo "    see docs/troubleshooting.md" >&2
    exit 1
}
warn() { echo "WARNING: $1" >&2; }
missing_tool_fail() {
    echo "FAIL: required command not found: $1" >&2
    echo "  Debian/Ubuntu:  sudo apt-get install $1" >&2
    echo "  Fedora/RHEL:    sudo dnf install $1" >&2
    echo "  Arch:           sudo pacman -S $1" >&2
    echo "    see docs/troubleshooting.md" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: bash scripts/00-check-env.sh [--profile base|community]

Profiles:
  base       (default) the project-validated stack: host tools, ROCm
             toolchain (7.14.x recommended, 7.2.x historical fallback),
             kernel floor, gfx1151 GPU arch, GPU-visible memory pool.
  community  third-party hardware validation (docs/hardware-validation.md):
             any AMD gfx GPU with ROCm present. Host tools + kernel floor
             are still enforced; the observed GPU arch and memory pool are
             reported, never gated — the run is evidence for a community
             platform submission, not a project validation.
EOF
}

PROFILE="base"
while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --profile)
            [ "$#" -ge 2 ] || { echo "ERROR: --profile requires a value (base|community)" >&2; usage >&2; exit 2; }
            PROFILE="$2"; shift ;;
        --profile=*) PROFILE="${1#--profile=}" ;;
        *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done
case "$PROFILE" in
    base|community) ;;
    *) echo "ERROR: unknown profile: '$PROFILE' (expected base or community)" >&2; usage >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v python3 >/dev/null 2>&1 || missing_tool_fail python3
# shellcheck source=scripts/lib/version.sh
source "$ROOT/scripts/lib/version.sh"
# shellcheck source=scripts/lib/rocm.sh
source "$ROOT/scripts/lib/rocm.sh"

read_manifest() {
    python3 - "$ROOT/configs/validated-stack.json" "$1" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for key in sys.argv[2].split("."):
    value = value[key]
print(value)
PY
}

MIN_KERNEL="$(read_manifest host.minimum_kernel)"
GPU_ARCH="$(read_manifest host.gpu_arch)"

if [ "$PROFILE" = base ]; then
    echo "Environment profile: base (Qwen3.8-27B, gfx1151)"
else
    echo "Environment profile: community (any AMD gfx GPU; evidence per docs/hardware-validation.md)"
fi

echo "host tools:"
for tool in git curl python3; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo "  tool $tool: $(command -v "$tool")"
    else
        missing_tool_fail "$tool"
    fi
done

resolve_rocm_prefix || exit 1
export PATH="$ROCM_PREFIX/bin:$PATH"
rocm_ver="$(detect_rocm_version "$ROCM_PREFIX")"
print_selected_rocm "$rocm_ver"

if [ "$PROFILE" = base ]; then
    case "$rocm_ver" in
        7.14.*) ;;
        7.2.*) warn "using the historical ROCm $rocm_ver fallback; ROCm 7.14 is recommended." ;;
        *) fail "base profile expects ROCm 7.14.x (recommended) or historical 7.2.x; got '$rocm_ver'. Run scripts/install-rocm-7.14.sh to install 7.14, or set ROCM_PREFIX to an existing 7.14.x/7.2.x prefix." ;;
    esac
else
    # Community evidence may come from any ROCm the submitter actually ran;
    # the exact version belongs in the submission's stack manifest.
    case "$rocm_ver" in
        7.14.*) ;;
        *) warn "community profile: ROCm $rocm_ver is not the project's 7.14.x — acceptable for a submission, but record the exact version in the stack manifest (docs/hardware-validation.md)." ;;
    esac
fi

# KERNEL_RELEASE lets the fake-prefix CI tests pin a kernel at/above the floor
# instead of depending on the runner's real kernel (often below 6.16.9).
krel="${KERNEL_RELEASE:-$(uname -r)}"
echo "kernel: $krel"
version_at_least "$krel" "$MIN_KERNEL" ||
    fail "project Strix Halo host floor is kernel >= $MIN_KERNEL (docs/troubleshooting.md#uma-bug); got $krel"

# Buffer rocminfo output. A live rocminfo piped to grep -q can receive SIGPIPE
# under pipefail, so parsing always uses the complete captured output.
rocminfo_out="$("$ROCM_PREFIX/bin/rocminfo" 2>/dev/null || true)"
observed_gpus="$( { grep -oE 'gfx[0-9]+' <<<"$rocminfo_out" || true; } | sort -u | paste -sd' ' -)"
# Agent Name: lines only — the loose grep above also catches ISA target names
# like `amdgcn-amd-amdhsa--gfx11-generic`, which must not become the arch.
agent_gpus="$( { grep -oE 'Name:[[:space:]]+gfx[0-9]+[a-z]*' <<<"$rocminfo_out" || true; } | awk '{print $NF}' | sort -u | paste -sd' ' -)"

if [ "$PROFILE" = base ]; then
    if ! grep -q "$GPU_ARCH" <<<"$rocminfo_out"; then
        fail "$GPU_ARCH not found in $ROCM_PREFIX/bin/rocminfo output; observed GPU id(s): ${observed_gpus:-none}. This project is validated on gfx1151 (AMD Strix Halo) only — see docs/hardware-validation.md for non-gfx1151 platforms."
    fi
    gpu_arch="$GPU_ARCH"
else
    # Community: accept ANY observed gfx arch; ROCm must still see an AMD GPU.
    if [ -z "$agent_gpus" ]; then
        fail "no AMD gfx GPU found in $ROCM_PREFIX/bin/rocminfo output (observed GPU id(s): ${observed_gpus:-none}) — the community profile still requires a visible AMD GPU (ROCm present)."
    fi
    gpu_arch="${agent_gpus%% *}"
fi

vram_kb="$(awk -v arch="$gpu_arch" '
  $0 ~ ("Name:[[:space:]]+" arch) { gpu = 1 }
  gpu && /Segment:[[:space:]]+GLOBAL; FLAGS: COARSE GRAINED/ { coarse = 1; next }
  coarse && /Size:/ { size = $2; sub(/\(.*/, "", size); print size; exit }
' <<<"$rocminfo_out")"

if [ "$PROFILE" = base ]; then
    [[ "$vram_kb" =~ ^[0-9]+$ ]] ||
        fail "could not read $GPU_ARCH global memory pool from rocminfo"
    pool_gib=$(( vram_kb / 1024 / 1024 ))
    echo "GPU-visible pool: ${pool_gib} GiB (BF16 weights ~49.8 GiB need a large visible pool; on this validated-class 80 GiB pool they fit — on 32 GiB-class pools they do not)"
    echo "OK: base environment ready for Qwen3.8-27B on gfx1151"
else
    # Reuses the same rocminfo pool parsing, but reports whatever was observed
    # (no floor): discrete-VRAM boards report board VRAM here, not the GTT
    # pool the gfx1151 host exposes — memory models differ.
    if [[ "$vram_kb" =~ ^[0-9]+$ ]]; then
        pool_gib=$(( vram_kb / 1024 / 1024 ))
        pool_str="${pool_gib}GiB"
        echo "GPU-visible pool: ${pool_gib} GiB (as reported by rocminfo on this host; discrete boards report board VRAM, gfx1151 reports a GTT pool)"
    else
        pool_str="unreadable"
        warn "could not read a ${gpu_arch} global memory pool from rocminfo — record rocm-smi output in your submission receipts (docs/hardware-validation.md)."
    fi
    echo "COMMUNITY-PROFILE: arch=${gpu_arch} pool=${pool_str} NOT project-validated — submit evidence per docs/hardware-validation.md"
    echo "OK: community profile environment readable"
fi
