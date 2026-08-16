#!/usr/bin/env bash
# Launch vLLM (OpenAI-compatible server) for Qwen3.8-27B on gfx1151.
# Source of truth for the flags is configs/serve-args.conf (baseline) or
# configs/serve-args-mtp.conf (--mtp: baseline + MTP speculative decoding);
# the runtime env is configs/vllm-gfx1151.env. Both are CI-checked by
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
        -h|--help)
            sed -n '2,8p' "$0" >&2
            echo "Usage: scripts/03-serve-vllm.sh [--mtp]  (env: MODEL_DIR=...)" >&2
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1 (only --mtp is supported)" >&2
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
