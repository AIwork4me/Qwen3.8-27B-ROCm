#!/usr/bin/env bash
# FP8 unlock: two bounded levers against the warm Phase 2 venv/cache.
# Lever 1: VLLM_ENGINE_READY_TIMEOUT_S=1800. Lever 2 (if 1 fails): pre-seed
# the tuned-config JSON from a wheel-shipped MI300X N=16384,K=5120 file.
# Outcome UNLOCKED or STILL-GAPPED — both write the receipt and exit 0.
# Env: VLLM_VENV=/root/venv-fp8probe PROBE_PGREP_PATTERN (test seam) PORT_V=8199
set -euo pipefail
usage() { echo "Usage: bash scripts/probe-fp8-unlock.sh  (writes docs/results/spike/fp8-unlock.md)"; }
while [ "$#" -gt 0 ]; do case "$1" in -h|--help) usage; exit 0 ;; *) echo "unknown: $1" >&2; exit 2 ;; esac; done

HERE="$(cd "$(dirname "$0")/.." && pwd)"
VLLM_VENV="${VLLM_VENV:-/root/venv-fp8probe}"
PORT_V="${PORT_V:-8199}"
PATTERN="${PROBE_PGREP_PATTERN:-llama-server|vllm}"
mkdir -p /root/fp8probe
LOG=/root/fp8probe/unlock.log
: > "$LOG"

# R6: only a LIVE (non-zombie) pid counts as busy — this host carries dozens
# of unreapable Z-state pids matching the pattern forever (see 06-run-matrix.sh).
gpu_free() {
    local pid state
    for pid in $(pgrep -f "$PATTERN" 2>/dev/null || true); do
        [ "$pid" = "$$" ] && continue
        [ -r "/proc/$pid/status" ] || continue
        state="$(awk '/^State:/{print $2}' "/proc/$pid/status" 2>/dev/null || true)"
        [ -z "$state" ] && continue
        [ "$state" = "Z" ] && continue
        return 1
    done
    return 0
}
gpu_free || { echo "FAIL: GPU busy (pattern '$PATTERN')" >&2; exit 1; }

SNAP=/root/.cache/modelscope/models/Qwen--Qwen3.8-27B-FP8/snapshots/master
[ -d "$SNAP" ] || { echo "FAIL: FP8 snapshot missing (rerun Phase 2 probe first)" >&2; exit 1; }

try_server() {  # try_server <label> <timeout_s> <log>
    local label="$1" tmo="$2" log="$3"
    echo "=== lever: $label (engine timeout ${tmo}s) ===" | tee -a "$LOG"
    VLLM_ENGINE_READY_TIMEOUT_S="$tmo" timeout 2400 \
        "$VLLM_VENV/bin/python" -m vllm.entrypoints.openai.api_server \
        --model "$SNAP" --served-model-name Qwen/Qwen3.8-27B-FP8 \
        --max-model-len 8192 --gpu-memory-utilization 0.90 \
        --enforce-eager --port "$PORT_V" > "$log" 2>&1 &
    local pid=$!
    for _ in $(seq 1 90); do
        curl -sf -m 2 "http://127.0.0.1:$PORT_V/health" >/dev/null 2>&1 && return 0
        kill -0 "$pid" 2>/dev/null || break
        sleep 20
    done
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    return 1
}

run_vllm_cells() {  # only on UNLOCKED
    # Second served name = the driver's hardcoded payload model ("qwen3.8-27b",
    # llama-server's alias); without it vLLM 404s every cell request.
    # M2: match the documented WORKING procedure (fp8-unlock.md afternoon
    # re-run; upstream issue): /health 200 says nothing about first-inference
    # Triton JIT staging (~43 min on a cold cache), so warm the request path
    # at cell concurrency before driving each cell, and give the driver a
    # 3600 s per-request ceiling instead of its 300 s default.
    local c pid wpid wrc
    local warmup_payload='{"model": "qwen3.8-27b", "messages": [{"role": "user", "content": "warmup: reply with one word"}], "max_tokens": 8, "temperature": 0}'
    local -a wpids
    for c in 1 4 16; do
        VLLM_ENGINE_READY_TIMEOUT_S=1800 "$VLLM_VENV/bin/python" -m vllm.entrypoints.openai.api_server \
            --model "$SNAP" --served-model-name Qwen/Qwen3.8-27B-FP8 qwen3.8-27b \
            --max-model-len 8192 --gpu-memory-utilization 0.90 \
            --enforce-eager --port "$PORT_V" > "/root/fp8probe/cell-c$c.log" 2>&1 &
        pid=$!
        for _ in $(seq 1 90); do curl -sf -m 2 "http://127.0.0.1:$PORT_V/health" >/dev/null 2>&1 && break; sleep 20; done
        # warmup burst: c concurrent posts, -m 3600 rides out JIT staging.
        # Non-fatal: echo each rc and run the cell anyway — the driver
        # records the cell's own outcome.
        wpids=()
        for _ in $(seq 1 "$c"); do
            curl -s -o /dev/null -m 3600 -H 'Content-Type: application/json' \
                -d "$warmup_payload" "http://127.0.0.1:$PORT_V/v1/chat/completions" &
            wpids+=("$!")
        done
        for wpid in "${wpids[@]}"; do
            wrc=0
            wait "$wpid" || wrc=$?
            echo "warmup c$c rc=$wrc"
        done
        python3 "$HERE/scripts/bench_driver.py" --url "http://127.0.0.1:$PORT_V" \
            --concurrency "$c" --reps 5 --max-tokens 128 --timeout 3600 \
            --prompt-file "$HERE/configs/bench-prompt.txt" \
            --identity /dev/stdin --out "$HERE/docs/results/matrix/cell-vllm-c$c.json" <<JSON
{"tag": "vllm-c$c", "quant": "FP8", "file": "Qwen3.8-27B-FP8", "size_bytes": 30866866928, "np": $c, "extra_args": "enforce-eager", "max_tokens": 128, "llama_cpp_commit": "n/a", "rocm_version": "7.2.1", "gpu": "AMD Radeon W7900D (gfx1100)", "engine": "vllm 0.27.1+rocm723"}
JSON
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
    ( cd "$HERE/docs/results/matrix" && sha256sum cell-*.json > SHA256SUMS )
}

UNLOCKED=0
if try_server "lever1-timeout1800" 1800 /root/fp8probe/unlock-l1.log; then
    UNLOCKED=1
    echo "PROBE-RESULT: UNLOCKED via lever 1 (engine timeout 1800s)" | tee -a "$LOG"
    pkill -f "api_server.*$PORT_V" 2>/dev/null || true
else
    echo "lever 1 failed; trying lever 2 (config pre-seed)" | tee -a "$LOG"
    CFG_DIR="$VLLM_VENV/lib/python3.12/site-packages/vllm/model_executor/layers/quantization/utils/configs"
    SRC="$(find "$CFG_DIR" -maxdepth 1 -name 'N=16384,K=5120*MI300X*' -printf '%f\n' | head -1 || true)"
    DST='N=16384,K=5120,device_name=AMD_Radeon_Graphics,dtype=fp8_w8a8,block_shape=[128,128].json'
    if [ -n "$SRC" ] && cp "$CFG_DIR/$SRC" "$CFG_DIR/$DST" 2>>"$LOG"; then
        echo "seeded $DST from $SRC" | tee -a "$LOG"
        if try_server "lever2-configseed" 600 /root/fp8probe/unlock-l2.log; then
            UNLOCKED=1
            echo "PROBE-RESULT: UNLOCKED via lever 2 (config pre-seed from $SRC)" | tee -a "$LOG"
            pkill -f "api_server.*$PORT_V" 2>/dev/null || true
        fi
    else
        echo "lever 2 skipped: no MI300X N=16384,K=5120 config found" | tee -a "$LOG"
    fi
fi

if [ "$UNLOCKED" -eq 1 ]; then
    run_vllm_cells
    echo "Next: update decision-table FP8 row to UNLOCKED and write fp8-unlock.md"
else
    echo "PROBE-RESULT: STILL-GAPPED (both levers)" | tee -a "$LOG"
    echo "Next: write fp8-unlock.md with both lever outcomes"
fi
