#!/usr/bin/env bash
# Launch vLLM (OpenAI-compatible server) for Qwen3.8-27B on gfx1151.
# Source of truth for the flags is configs/serve-args.conf (baseline),
# configs/serve-args-mtp.conf (--mtp: baseline + MTP speculative decoding),
# or configs/serve-args-dflash2.conf (--dflash2: baseline + DFlash2
# block-diffusion speculative decoding; draft model fetched via
# SET=dflash2-bf16 scripts/02-fetch-model.sh);
# the runtime env is configs/vllm-gfx1151.env. All are CI-checked by
# tests/test_serve_args.py.
#
# CRITICAL: uses `uv run --no-sync`. vLLM was source-installed editable
# (scripts/01-build-vllm.sh, --no-build-isolation) and is NOT in uv.lock. A bare
# `uv run` would re-sync and DELETE the editable vLLM. Never drop --no-sync here.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

# uv lives in ~/.local/bin on this host.
export PATH="$HOME/.local/bin:$PATH"

CONF_NAME="serve-args.conf"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mtp)
            CONF_NAME="serve-args-mtp.conf"
            ;;
        --dflash2)
            CONF_NAME="serve-args-dflash2.conf"
            DRAFT_DIR="$HERE/models/Qwen3.8-27B-DFlash2"
            if [ ! -f "$DRAFT_DIR/config.json" ]; then
                echo "ERROR: $DRAFT_DIR/config.json missing — run: SET=dflash2-bf16 scripts/02-fetch-model.sh" >&2
                exit 1
            fi
            ;;
        -h|--help)
            sed -n '2,9p' "$0" >&2
            echo "Usage: scripts/03-serve-vllm.sh [--mtp|--dflash2]  (env: MODEL_DIR=..., MAX_MODEL_LEN=<override of the conf --max-model-len>)" >&2
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1 (only --mtp and --dflash2 are supported)" >&2
            exit 2
            ;;
    esac
    shift
done

# shellcheck source=/dev/null
source "$HERE/configs/vllm-gfx1151.env"

MODEL_DIR="${MODEL_DIR:-$HERE/models/Qwen3.8-27B}"
if [ ! -f "$MODEL_DIR/config.json" ]; then
    echo "ERROR: $MODEL_DIR/config.json missing — run scripts/02-fetch-model.sh first." >&2
    exit 1
fi

# Parse each non-comment config line into an argument array. This avoids command
# substitution, accidental glob expansion, and evaluation of shell metacharacters.
SERVE_ARGS=()
while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    read -r -a words <<<"$line"
    SERVE_ARGS+=("${words[@]}")
done < "$HERE/configs/$CONF_NAME"

# MAX_MODEL_LEN env pass-through (benchmark matrix, Task 4): documented,
# minimal override for the cell runner — the confs themselves are NEVER
# edited (they stay the validated defaults; a CI test asserts they are
# byte-stable across the branch). Unset by default → conf boot unchanged.
# Replaces any conf --max-model-len in place (last-wins would also work, but
# a single occurrence keeps the echoed flags honest).
if [ -n "${MAX_MODEL_LEN:-}" ]; then
    FILTERED_ARGS=()
    skip_next=0
    for a in "${SERVE_ARGS[@]}"; do
        if [ "$skip_next" = "1" ]; then skip_next=0; continue; fi
        if [ "$a" = "--max-model-len" ]; then skip_next=1; continue; fi
        FILTERED_ARGS+=("$a")
    done
    SERVE_ARGS=("${FILTERED_ARGS[@]}" --max-model-len "$MAX_MODEL_LEN")
    echo "MAX_MODEL_LEN override: --max-model-len $MAX_MODEL_LEN (conf value replaced; conf file untouched)"
elif [ "$CONF_NAME" = "serve-args-dflash2.conf" ]; then
    # Statically known (boot receipt 2026-08-21): with the draft loaded, the
    # conf's 262144 tier exceeds the 80 GiB pool's KV budget (21.63 needed
    # vs 15.46 GiB available) — the boot refuses ~5 min in. Warn now; the
    # validated tier is 131072. See docs/results/rocm-7.14/dflash2-validation.md.
    echo "WARNING: --dflash2 at the conf's ctx 262144 is KV-infeasible on the 80 GiB pool (21.63 vs 15.46 GiB; the boot will refuse after model load)." >&2
    echo "WARNING: boot the validated tier with: MAX_MODEL_LEN=131072 $0 --dflash2 (see docs/troubleshooting.md#dflash2-vllm-kv)" >&2
fi

# Task 5's validation client talks to http://127.0.0.1:8000/v1/chat/completions;
# the confs pin --port 8000. Echo the effective port for the operator.
PORT=8000
for ((i = 0; i < ${#SERVE_ARGS[@]} - 1; i++)); do
    if [[ "${SERVE_ARGS[$i]}" == "--port" ]]; then
        PORT="${SERVE_ARGS[$((i + 1))]}"
    fi
done
echo "Serving $MODEL_DIR ($CONF_NAME) on http://127.0.0.1:${PORT}/v1 ..."

exec uv run --no-sync vllm serve "$MODEL_DIR" "${SERVE_ARGS[@]}"
