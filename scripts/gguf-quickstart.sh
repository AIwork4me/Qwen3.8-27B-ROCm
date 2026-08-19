#!/usr/bin/env bash
# GGUF quick-start for gfx1151: serve the validated unsloth UD-Q4_K_XL GGUF
# with the pinned, fingerprinted llama.cpp HIP build (scripts/05-build-llama.sh).
#
# Defaults come from the validated stack / artifact manifest, never a guess:
#   - model: the UD-Q4_K_XL file of the "gguf" set in configs/artifact-manifest.json
#     (fetched+hash-verified by scripts/02-fetch-model.sh)
#   - ctx : configs/validated-stack.json llama_cpp.validated.ctx_size, else 131072
#
# Overrides (explicit, experimental):
#   GGUF_FILE=<name-or-path>  serve another quant from the set (or any GGUF path)
#   CTX_SIZE=<n>              context size
#   PORT=<n>                  port (default 8080)
#   WITH_MTP=1                opt in to MTP speculative decoding (see below)
#   SPEC_DEPTH=<n>            with WITH_MTP=1: MTP draft depth, passed as
#                             --spec-draft-n-max n (discovered at the pin,
#                             see configs/validated-stack.json
#                             llama_cpp_vulkan.mtp_depth; upstream default 3)
#   BACKEND=<hip|vulkan>      llama.cpp build to serve. DEFAULT hip (build-714,
#                             unchanged) — hip WITH_MTP=1 is BOTH the default
#                             and the recommended path. vulkan = build-714-vk —
#                             an AVAILABLE experimental opt-in, NOT
#                             recommended (project ruling 2026-08-19 supersedes
#                             the 2026-08-18 promotion, which rested on a
#                             mixed-depth pairing: the clean depth-1 same-day
#                             pairing measures vulkan 14.53 vs hip 13.86 tok/s
#                             = +4.81% single-stream, aggregate basis
#                             hip 10.74 vs vulkan 9.31 tok/s = -13.31%;
#                             cross-day re-runs dropped every vulkan cell, up
#                             to -23.49% — cause not recorded, no clock/
#                             thermal telemetry in the receipts; build via
#                             scripts/06-build-llama-vulkan.sh; evidence:
#                             docs/results/matrix-714/stability/ and the
#                             benchmark verdicts). Experimental — single host
#                             (gfx1151), one ICD (RADV 25.2.8).
#   WITH_MMPROJ=0             skip the vision projector even when present
#   VERIFY_GGUF=1             full SHA256 re-verification before serving (~1 min)
#   EXTRA_ARGS='...'          extra llama-server flags appended verbatim
#                             (word-split; empty by default so default boots
#                             are byte-identical. Added for the benchmark
#                             matrix cell runner scripts/run-cell-gguf.sh,
#                             which passes explicit `-np N` for concurrency
#                             cells — split KV semantics, METHODOLOGY.md §6)
#
# UX patterns adapted from muse-rocm scripts/gguf-quickstart.sh: port preflight,
# required-commands loop, manifest-driven resolution, disk preflight for the
# fetch remedy, and the end-of-launch "where to point your client" echo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8080}"

# --- Port preflight: gate before anything expensive (muse F-11 pattern) ------
port_probe_rc=0
if command -v python3 >/dev/null 2>&1; then
    python3 - "$PORT" <<'PY_PORT' || port_probe_rc=$?
import socket, sys
try:
    port = int(sys.argv[1])
except ValueError:
    sys.exit(2)
sock = socket.socket()
# SO_REUSEADDR mirrors how a real server binds: sockets lingering in TIME_WAIT
# from a just-killed server must NOT read as "in use" (the matrix cell runner
# boots back-to-back cells and hit exactly that false positive); an ACTIVE
# listener still fails the bind and is reported.
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind(("127.0.0.1", port))
except OSError:
    sys.exit(1)
finally:
    sock.close()
PY_PORT
fi
if [ "$port_probe_rc" -eq 2 ]; then
    echo "ERROR: PORT=$PORT is not a usable port number; choose PORT=<free-port>." >&2
    exit 1
elif [ "$port_probe_rc" -ne 0 ]; then
    echo "ERROR: port $PORT is already in use; choose PORT=<free-port>." >&2
    exit 1
fi

# --- Required commands (actionable errors) ------------------------------------
for cmd in python3 curl; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: required command not found: $cmd" >&2
        exit 1
    }
done

MANIFEST="configs/artifact-manifest.json"
STACK="configs/validated-stack.json"
# Backend selection: hip (the validated default AND the recommended path,
# unchanged) or an explicit Vulkan opt-in. Project ruling 2026-08-19
# (v0.1.4) SUPERSEDES the 2026-08-18 promotion: the clean depth-1 same-day
# pairing (session 3, both backends explicit --spec-draft-n-max 1) is
# vulkan 14.53 vs hip 13.86 tok/s = +4.81% single-stream, the aggregate
# basis flips to -13.31% (vulkan TTFT 9.94-12.21 s vs 8.36-8.83 s on
# 08-18), and the cross-day re-runs dropped every vulkan cell (spreads to
# 30.70%) — so BACKEND=vulkan is an AVAILABLE experimental opt-in, NOT a
# recommendation; hip WITH_MTP=1 is the recommended path. No-flip closed:
# +4.81% << the >25% flip threshold (arithmetic recorded in the verdicts;
# docs/results/matrix-714/stability/). Limits: single host (gfx1151), one
# ICD (RADV 25.2.8). LLAMA_SERVER remains the top-level override.
BACKEND="${BACKEND:-hip}"
case "$BACKEND" in
    hip)    SERVER="${LLAMA_SERVER:-$ROOT/third_party/llama.cpp/build-714/bin/llama-server}"
            BUILD_HINT="run scripts/05-build-llama.sh first (pinned HIP build for gfx1151)." ;;
    vulkan) SERVER="${LLAMA_SERVER:-$ROOT/third_party/llama.cpp/build-714-vk/bin/llama-server}"
            BUILD_HINT="run scripts/06-build-llama-vulkan.sh first (pinned Vulkan build; experimental)." ;;
    *)      echo "ERROR: unknown BACKEND '$BACKEND' (expected hip|vulkan)." >&2
            exit 1 ;;
esac

[ -x "$SERVER" ] || {
    echo "ERROR: llama-server not found at $SERVER" >&2
    echo "       $BUILD_HINT" >&2
    exit 1
}

# --- Manifest-driven model resolution -----------------------------------------
# Resolve the "gguf" set: dest dir + per-file size/sha. Default file is the
# validated UD-Q4_K_XL quant; GGUF_FILE overrides (bare name -> set dir, or any path).
GGUF_FILE="${GGUF_FILE:-Qwen3.8-27B-UD-Q4_K_XL.gguf}"
MMPROJ_FILE="mmproj-F16.gguf"
DEST="$(python3 -c 'import json;print(json.load(open("'"$MANIFEST"'"))["sets"]["gguf"]["dest"])')"

manifest_size() { # manifest_size <filename> -> size_bytes (0 if unrecorded)
    python3 - "$MANIFEST" "$1" <<'PY'
import json, sys
files = json.load(open(sys.argv[1]))["sets"]["gguf"]["files"]
print(next((f["size_bytes"] for f in files if f["path"] == sys.argv[2]), 0))
PY
}

if [[ "$GGUF_FILE" = /* ]]; then
    MODEL_PATH="$GGUF_FILE"
else
    MODEL_PATH="$DEST/$GGUF_FILE"
fi

if [ ! -f "$MODEL_PATH" ]; then
    need_bytes="$(manifest_size "$GGUF_FILE")"
    echo "ERROR: model file not found: $MODEL_PATH" >&2
    echo "       run SET=gguf bash scripts/02-fetch-model.sh" >&2
    # Disk preflight for that remedy (muse pattern): refuse to point the user
    # at a fetch the filesystem cannot hold before they start it. Probe
    # $ROOT (always exists): $DEST may not exist yet before the first
    # fetch, and df on a missing path silently yields nothing.
    if [ "$need_bytes" -gt 0 ]; then
        avail_kb="$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2 {print $4}')"
        if [ -n "$avail_kb" ] && [ "$((avail_kb * 1024))" -lt "$need_bytes" ]; then
            echo "       (that filesystem has $((avail_kb / 1024 / 1024)) GiB free; the fetch needs $((need_bytes / 1024 / 1024 / 1024)) GiB)" >&2
        fi
    fi
    exit 1
fi

# Cheap size gate against the manifest; full SHA256 only on VERIFY_GGUF=1
# (Task 1 already hash-verified every file at fetch time).
expected_size="$(manifest_size "$(basename "$MODEL_PATH")")"
if [ "$expected_size" -gt 0 ]; then
    actual_size="$(stat -c%s "$MODEL_PATH")"
    if [ "$actual_size" -ne "$expected_size" ]; then
        echo "ERROR: $MODEL_PATH has size $actual_size, manifest says $expected_size;" >&2
        echo "       delete it and rerun SET=gguf bash scripts/02-fetch-model.sh" >&2
        exit 1
    fi
fi
if [ "${VERIFY_GGUF:-0}" = "1" ]; then
    python3 - "$MANIFEST" "$MODEL_PATH" <<'PY'
import hashlib, json, sys
files = json.load(open(sys.argv[1]))["sets"]["gguf"]["files"]
path = sys.argv[2]
want = next((f["sha256"] for f in files if f["path"] == path.rsplit("/", 1)[-1]), None)
if want is None:
    print(f"WARN: {path} is outside the validated artifact set; hash not asserted.", file=sys.stderr)
    sys.exit(0)
h = hashlib.sha256()
with open(path, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 22), b""):
        h.update(chunk)
if h.hexdigest() != want:
    print(f"ERROR: {path}: sha256 {h.hexdigest()} != manifest {want}; refetch it.", file=sys.stderr)
    sys.exit(1)
print(f"verified: {path} sha256 matches the manifest")
PY
fi

# --- Context default from the validated stack (write-once, then read back) ----
CTX_DEFAULT="131072"
if python3 -c 'import json,sys;sys.exit(0 if json.load(open(sys.argv[1]))["llama_cpp"].get("validated",{}).get("ctx_size") else 1)' "$STACK" 2>/dev/null; then
    CTX_DEFAULT="$(python3 -c 'import json;print(json.load(open("'"$STACK"'"))["llama_cpp"]["validated"]["ctx_size"])')"
fi
CTX_SIZE="${CTX_SIZE:-$CTX_DEFAULT}"

# --- Server flags --------------------------------------------------------------
SERVER_ARGS=(-m "$MODEL_PATH" --port "$PORT" -ngl 99 --ctx-size "$CTX_SIZE" --jinja)

MMPROJ_PATH="$DEST/$MMPROJ_FILE"
if [ "${WITH_MMPROJ:-1}" != "0" ] && [ -f "$MMPROJ_PATH" ]; then
    SERVER_ARGS+=(--mmproj "$MMPROJ_PATH")
fi

# MTP speculative decoding, opt-in via WITH_MTP=1.
# Exact syntax at the pinned commit 4df29be4: `--spec-type draft-mtp`
#   - flag defined in common/arg.cpp (add_opt {"--spec-type"}, env LLAMA_ARG_SPEC_TYPE)
#   - "draft-mtp" name mapped in common/speculative.cpp:36
#   - no separate draft GGUF is needed: setting the type makes the loader pull
#     the MTP block out of the SAME model file (common.cpp:1689 sets
#     mparams.load_mtp; qwen35.cpp:97 load_block_mtp reads blk.<n> MTP tensors
#     from the main GGUF for this dense qwen35 arch; the mechanism is
#     identical in qwen35moe.cpp), and the draft context is created against
#     the target model itself (common/speculative.cpp: "creating MTP draft
#     context against the target model"). -md is therefore deliberately NOT
#     passed.
if [ "${WITH_MTP:-0}" = "1" ]; then
    SERVER_ARGS+=(--spec-type draft-mtp)
    # SPEC_DEPTH=<n> (matrix runner): the depth flag discovered at the pin.
    # Upstream default is n_max=3 (common/common.h); passing it explicitly
    # makes the boot (and its receipt) state the exact draft depth.
    if [ -n "${SPEC_DEPTH:-}" ]; then
        case "$SPEC_DEPTH" in
            ''|*[!0-9]*) echo "ERROR: SPEC_DEPTH must be a positive integer (got '$SPEC_DEPTH')." >&2; exit 1 ;;
        esac
        [ "$SPEC_DEPTH" -ge 1 ] || {
            echo "ERROR: SPEC_DEPTH must be >= 1 (got $SPEC_DEPTH)." >&2; exit 1
        }
        SERVER_ARGS+=(--spec-draft-n-max "$SPEC_DEPTH")
    fi
fi

# EXTRA_ARGS pass-through (benchmark matrix, Task 3): appended verbatim after
# the validated flags, word-split on whitespace. Empty default → unchanged
# behavior; the matrix cell runner is the only intended user (explicit -np N
# flips llama.cpp to split KV semantics — see METHODOLOGY.md §6 and
# scripts/run-cell-gguf.sh).
if [ -n "${EXTRA_ARGS:-}" ]; then
    # word-split deliberately, but robustly (shellcheck SC2206-clean)
    read -r -a extra_args_arr <<< "$EXTRA_ARGS"
    SERVER_ARGS+=("${extra_args_arr[@]}")
fi

echo "llama-server : $SERVER ($("$SERVER" --version 2>&1 | head -n1))"
if [ "$BACKEND" = "vulkan" ]; then
    echo "backend      : $BACKEND (AVAILABLE experimental opt-in — NOT recommended; project ruling 2026-08-19 supersedes the 2026-08-18 promotion: the clean depth-1 same-day pairing is 14.53 vs 13.86 tok/s = +4.81% single-stream, aggregate basis -13.31%; cross-day re-runs dropped every vulkan cell — see benchmark verdicts and docs/results/matrix-714/stability/)"
else
    echo "backend      : $BACKEND (default AND recommended path — run WITH_MTP=1 for the recommended interactive config, 13.0 tok/s per stream)"
    echo "note (opt-in): BACKEND=vulkan exists as an experimental opt-in, not a recommendation (downgraded 2026-08-19; clean d1 pairing +4.81% vs hip, aggregate -13.31% — evidence: benchmark verdicts, docs/results/matrix-714/stability/)"
fi
echo "model        : $MODEL_PATH ($(du -h "$MODEL_PATH" | cut -f1))"
echo "ctx-size     : $CTX_SIZE  (override: CTX_SIZE=<n>)"
echo "gpu layers   : 99 (all)"
echo "mmproj       : $([ "${WITH_MMPROJ:-1}" != "0" ] && [ -f "$MMPROJ_PATH" ] && echo "$MMPROJ_PATH" || echo "none")"
echo "speculative  : $([ "${WITH_MTP:-0}" = "1" ] && echo "draft-mtp (MTP head from the same GGUF, depth ${SPEC_DEPTH:-default 3} via --spec-draft-n-max)" || echo "off (opt in: WITH_MTP=1)")"
echo "extra args   : ${EXTRA_ARGS:-none}"

# --- End-of-launch UX (muse pattern): where to point the client, how to verify.
cat <<EOF

Serving on http://127.0.0.1:$PORT ...
Verify with:
  curl -s http://127.0.0.1:$PORT/health
  curl -s http://127.0.0.1:$PORT/v1/chat/completions -H 'Content-Type: application/json' \\
    -d '{"messages":[{"role":"user","content":"Reply with exactly: OK"}],"temperature":0,"max_tokens":512}'
(keep max_tokens >= 512: this model thinks before answering; a low cap truncates it)
Press Ctrl-C to stop the server.
EOF

exec "$SERVER" "${SERVER_ARGS[@]}"
