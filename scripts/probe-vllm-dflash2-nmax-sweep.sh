#!/usr/bin/env bash
# probe-vllm-dflash2-nmax-sweep.sh — vLLM-side DFlash2 draft-length
# (num_speculative_tokens / n-max) sweep, same-session with base/mtp
# controls, on the same bench command as the corpus cells.
#
# Why: the vLLM conf serves the VENDOR default num_speculative_tokens=7
# (not a measured optimum); the GGUF-path sweep (gfx1100,
# docs/results/dflash2/nmax-sweep.json) found draft length 2–4 clearly
# better there (+21–27%). This probe measures the vLLM optimum on the
# reference host (gfx1151) — and, run on a later day than the pairing
# session, doubles as its cross-day replication (the n=7 arm is the
# same config as the corpus dflash-c1 cell).
#
# Method (binding):
#   - one FRESH boot per arm: base-c1, mtp-c1 (--mtp), and dflash-c1 at
#     SPEC_N ∈ {2,3,4,7}; all at MAX_MODEL_LEN=131072 (the dflash
#     KV-feasible tier); the cells' exact bench command per arm;
#   - per dflash arm: RUNS (default 3) throughput runs + the greedy anchor
#     once; per-stream tok/s = 1000/tpot_ms; the arm's value is the median
#     of the runs; the n=7 arm doubles as the cross-day anchor vs the
#     published 10.23 (pairing session 2026-08-21);
#   - controls (base/mtp): single run + anchor, same session — the
#     same-session pairing basis, refreshed cross-day;
#   - receipts are SESSION receipts in a dated dflash-nmax-sweep-<date>
#     directory under docs/results/matrix-714/stability/ (receipts-only
#     namespace; corpus cells and verdicts are never touched).
#
# Usage:
#   bash scripts/probe-vllm-dflash2-nmax-sweep.sh [--arms "2 3 4 7"]
#        [--controls "base mtp"] [--receipt DIR] [--port N] [--runs N]
#   Env: RUNS (default 3), PORT (default 8000), HEALTH_TIMEOUT_S (900).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
ARMS="${ARMS:-2 3 4 7}"
CONTROLS="${CONTROLS:-base mtp}"
RUNS="${RUNS:-3}"
STABILITY_DIR="docs/results/matrix-714/stability"
RECEIPT_DIR="$STABILITY_DIR/dflash-nmax-sweep-$(date -u +%F)"
HEALTH_TIMEOUT_S="${HEALTH_TIMEOUT_S:-900}"
while [ $# -gt 0 ]; do
    case "$1" in
        --arms)     ARMS="$2"; shift 2 ;;
        --controls) CONTROLS="$2"; shift 2 ;;
        --receipt)  RECEIPT_DIR="$2"; shift 2 ;;
        --port)     PORT="$2"; shift 2 ;;
        --runs)     RUNS="$2"; shift 2 ;;
        -h|--help)  sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 required" >&2; exit 1; }
command -v curl  >/dev/null 2>&1 || { echo "ERROR: curl required" >&2; exit 1; }
for f in models/Qwen3.8-27B-DFlash2/config.json models/Qwen3.8-27B/config.json; do
    [ -f "$f" ] || { echo "ERROR: $f missing — run the fetch scripts first (SET=bf16, SET=dflash2-bf16)" >&2; exit 1; }
done
mkdir -p "$RECEIPT_DIR"

BENCH="scripts/bench_client.py"
PROMPTS="scripts/prompt-sets/default.json"
BASE_URL="http://127.0.0.1:$PORT"
SERVER_LOG="/tmp/vllm-nmax-server.log"

SWEEP_PID=""
trap 'stop_server' EXIT

stop_server() {
    [ -n "${SWEEP_PID:-}" ] || return 0
    kill "$SWEEP_PID" 2>/dev/null || true
    pkill -f "vllm serve" 2>/dev/null || true
    for _ in $(seq 1 45); do
        pgrep -f "vllm serve" >/dev/null 2>&1 || return 0
        sleep 4
    done
    echo "WARN: vllm still up after 180s; sending SIGKILL" >&2
    pkill -9 -f "vllm serve" 2>/dev/null || true
    return 0
}

boot_and_poll() { # $1..: serve script + args (env via callers)
    local started=$SECONDS
    nohup "$@" >"$SERVER_LOG" 2>&1 &
    SWEEP_PID=$!
    echo "  booting: $* (pid $SWEEP_PID; polling /health up to ${HEALTH_TIMEOUT_S}s)"
    for _ in $(seq 1 $((HEALTH_TIMEOUT_S / 10))); do
        sleep 10
        curl -s --max-time 3 "$BASE_URL/health" >/dev/null 2>&1 && {
            echo "  healthy after $((SECONDS - started))s"; return 0; }
        kill -0 "$SWEEP_PID" 2>/dev/null || {
            echo "ERROR: server process died during boot (log tail):" >&2
            tail -5 "$SERVER_LOG" >&2; return 1; }
    done
    echo "ERROR: health timeout after ${HEALTH_TIMEOUT_S}s" >&2
    return 1
}

bench_once() { # $1 = label, $2 = out JSON
    timeout 900 python3 "$BENCH" --base-url "$BASE_URL" \
        --concurrency 1 --prompts "$PROMPTS" --max-tokens 256 \
        --label "$1" --model qwen3.8-27b --no-thinking \
        --out "$2" >/dev/null
}

anchor_once() { # $1 = out JSON
    timeout 600 python3 "$BENCH" --anchor-only --base-url "$BASE_URL" \
        --prompts "$PROMPTS" --model qwen3.8-27b --no-thinking \
        --out "$1" >/dev/null
}

arm_json() { # $1 = out, $2 = arm label, $3 = runs, $4 = anchor_ok, $5 = bench_files...
    local out="$1" label="$2" runs="$3" anchor_ok="$4"; shift 4
    STARTED_UTC="$(date -u +%FT%TZ)" label="$label" runs="$runs" anchor_ok="$anchor_ok" \
    bench_files="$*" python3 - "$out" <<'PY'
import json, os, statistics, sys
env = os.environ
runs = []
for f in env["bench_files"].split():
    try:
        d = json.load(open(f))
        s = d["streams"][0]
        runs.append(1000.0 / s["tpot_ms"] if s.get("tpot_ms") else None)
    except Exception:
        runs.append(None)
good = [r for r in runs if r]
cell = {
    "arm": env["label"],
    "started_utc": env["STARTED_UTC"],
    "runs": runs,
    "tok_s_median": round(statistics.median(good), 2) if good else None,
    "anchor_ok": env["anchor_ok"] == "true",
}
json.dump(cell, open(sys.argv[1], "w"), indent=1)
print(f"  {cell['arm']}: median {cell['tok_s_median']} tok/s "
      f"(runs {['%.2f' % r if r else None for r in runs]}) anchor {cell['anchor_ok']}")
PY
}

run_arm() { # $1 = arm label (base|mtp|dflash-<n>), $2 = extra env (SPEC_N for dflash)
    local arm="$1" spec_env="$2"
    echo "== arm $arm =="
    stop_server; sleep 3
    rm -f /tmp/vllm-nmax-*.json
    case "$arm" in
        base)    boot_and_poll env MAX_MODEL_LEN=131072 bash scripts/03-serve-vllm.sh || return 1 ;;
        mtp)     boot_and_poll env MAX_MODEL_LEN=131072 bash scripts/03-serve-vllm.sh --mtp || return 1 ;;
        dflash-*) boot_and_poll env SPEC_N="${arm#dflash-}" MAX_MODEL_LEN=131072 \
                      bash scripts/03-serve-vllm.sh --dflash2 || return 1 ;;
        *) echo "ERROR: unknown arm $arm" >&2; return 1 ;;
    esac
    local n=1 anchor_ok=false
    local bench_files=""
    local total=1
    [ "$spec_env" = "sweep" ] && total="$RUNS"
    while [ "$n" -le "$total" ]; do
        bench_once "$arm" "/tmp/vllm-nmax-${arm}-run${n}.json" || true
        bench_files="$bench_files /tmp/vllm-nmax-${arm}-run${n}.json"
        n=$((n + 1))
    done
    anchor_once "/tmp/vllm-nmax-${arm}-anchor.json" && anchor_ok=true
    arm_json "$RECEIPT_DIR/${arm}.json" "$arm" "$total" "$anchor_ok" "$bench_files"
}

# Controls first (pairing basis), then the sweep arms.
for arm in $CONTROLS; do
    run_arm "$arm" "single" || { echo "ERROR: control arm $arm failed" >&2; exit 1; }
done
for n in $ARMS; do
    run_arm "dflash-$n" "sweep" || { echo "ERROR: sweep arm dflash-$n failed" >&2; exit 1; }
done

# Merge the session receipt.
python3 - "$RECEIPT_DIR" <<'PY'
import glob, json, os, sys
d = sys.argv[1]
arms = {}
for f in sorted(glob.glob(os.path.join(d, "*.json"))):
    if os.path.basename(f) == "nmax-sweep.json":
        continue
    a = json.load(open(f))
    arms[a["arm"]] = a
out = {
    "generated_on": d.rstrip("/").split("-")[-3:] and "-".join(d.rstrip("/").split("-")[-3:]),
    "method": "fresh boot per arm (base, mtp, dflash@SPEC_N in ARMS) at "
              "MAX_MODEL_LEN=131072; the cells' exact bench command; "
              "dflash arms = median of RUNS runs; greedy anchor per arm",
    "arms": arms,
}
json.dump(out, open(os.path.join(d, "nmax-sweep.json"), "w"), indent=1)
print(f"receipt: {d}/nmax-sweep.json ({len(arms)} arms)")
PY
echo "== sweep done =="
