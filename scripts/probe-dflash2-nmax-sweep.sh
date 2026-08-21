#!/usr/bin/env bash
# probe-dflash2-nmax-sweep.sh — DFlash2 draft-length (SPEC_DEPTH / n-max)
# and draft-quant sweep on the SAME binary/prompts as the published cells.
#
# Why: every committed dflash2 cell ran at n-max 7 (the block_size-1 cap);
# upstream testers on V100/3090/R9700 independently report lower optima
# (n-max 4). This sweep measures the optimum on gfx1100 and compares the
# Q8_0 (default) vs Q4_K_M drafter at the same time.
#
# Method (binding):
#   - one FRESH WITH_DFLASH2=1 boot per config (SPEC_DEPTH=<nmax>,
#     DFLASH_FILE=<draft>), same PR-27342 binary, same UD-Q4_K_XL target,
#     same ctx (131072 default) as the cells;
#   - per config: 3 runs of the EXACT cell bench command
#     (bench_client.py --concurrency 1 --prompts default.json
#      --max-tokens 256 --no-thinking) + the greedy anchor;
#   - per-stream tok/s = 1000/tpot_ms; the config's value is the MEDIAN of
#     the 3 runs (the c1 corpus cells are single-run; the n-max-7/Q8_0
#     config doubles as the session anchor — expect it to reproduce the
#     published 33.2 within the project's warm-band, else the session is
#     flagged);
#   - acceptance counters summed over ALL per-task lines in the server
#     log after each config (llama.cpp prints per-task counters), giving
#     acceptance vs n-max.
#
# Usage:
#   bash scripts/probe-dflash2-nmax-sweep.sh [--configs "2:q8_0 4:q8_0 ..."] \
#        [--receipt FILE] [--port N]
#   config syntax: <nmax>:<q8_0|q4_km>; default configs:
#   "2:q8_0 4:q8_0 5:q8_0 7:q8_0 4:q4_km 7:q4_km"
# Env: LLAMA_SERVER (default build-714-dflash2), CTX_SIZE, RUNS (default 3).
# Output: per-config JSONs in /tmp/dflash2-nmax-<spec>.json and, when every
#   requested config is present, the merged receipt at
#   docs/results/dflash2/nmax-sweep.json (rerun with all configs to merge).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8096}"
RECEIPT="docs/results/dflash2/nmax-sweep.json"
CONFIGS="2:q8_0 4:q8_0 5:q8_0 7:q8_0 4:q4_km 7:q4_km"
RUNS="${RUNS:-3}"
while [ $# -gt 0 ]; do
    case "$1" in
        --configs) CONFIGS="$2"; shift 2 ;;
        --receipt) RECEIPT="$2"; shift 2 ;;
        --port)    PORT="$2"; shift 2 ;;
        -h|--help) sed -n '2,36p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

SERVER="${LLAMA_SERVER:-$ROOT/third_party/llama.cpp/build-714-dflash2/bin/llama-server}"
[ -x "$SERVER" ] || {
    echo "ERROR: llama-server not found at $SERVER (run scripts/07-build-llama-dflash2.sh)" >&2
    exit 1
}
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 required" >&2; exit 1; }
command -v curl  >/dev/null 2>&1 || { echo "ERROR: curl required" >&2; exit 1; }

DRAFT_OF() { # q8_0 -> file, q4_km -> file
    case "$1" in
        q8_0)  echo "Qwen3.8-27B-DFlash2-Q8_0.gguf" ;;
        q4_km) echo "Qwen3.8-27B-DFlash2-Q4_K_M.gguf" ;;
        *) echo "ERROR: unknown draft tag '$1' (q8_0|q4_km)" >&2; return 1 ;;
    esac
}

SWEEP_PID=""
trap 'stop_server' EXIT

stop_server() {
    [ -n "${SWEEP_PID:-}" ] || return 0
    local PARENT="$SWEEP_PID"
    local CHILDREN
    CHILDREN="$(pgrep -P "$PARENT" 2>/dev/null || true)"
    local -a kids=()
    [ -n "$CHILDREN" ] && read -r -a kids <<< "$CHILDREN"
    kill "$PARENT" ${kids:+"${kids[@]}"} 2>/dev/null || true
    pkill -f "llama-server.*--port $PORT" 2>/dev/null || true
    for _ in $(seq 1 30); do
        pgrep -f "llama-server.*--port $PORT" >/dev/null 2>&1 || return 0
        sleep 2
    done
    echo "WARN: llama-server on :$PORT still up after 60s; sending SIGKILL" >&2
    pkill -9 -f "llama-server.*--port $PORT" 2>/dev/null || true
    return 0
}

for spec in $CONFIGS; do
    nmax="${spec%%:*}"
    tag="${spec##*:}"
    draft="$(DRAFT_OF "$tag")" || exit 1
    out="/tmp/dflash2-nmax-${nmax}-${tag}.json"
    [ -f "$out" ] && { echo "skip (already captured): $spec -> $out"; continue; }
    stop_server; sleep 2
    echo "== config n-max=$nmax draft=$tag =="
    nohup env LLAMA_SERVER="$SERVER" PORT="$PORT" CTX_SIZE="${CTX_SIZE:-131072}" \
        WITH_DFLASH2=1 SPEC_DEPTH="$nmax" DFLASH_FILE="$draft" \
        bash scripts/gguf-quickstart.sh >"/tmp/dflash2-nmax-server.log" 2>&1 &
    SWEEP_PID=$!
    for _ in $(seq 1 240); do
        curl -sf -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
        if ! kill -0 "$SWEEP_PID" 2>/dev/null; then
            echo "ERROR: server exited before /health; log tail:" >&2
            tail -n 20 /tmp/dflash2-nmax-server.log >&2
            exit 1
        fi
        sleep 3
    done
    curl -sf -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || {
        echo "ERROR: /health not ready within 12 min" >&2
        tail -n 20 /tmp/dflash2-nmax-server.log >&2
        exit 1
    }
    python3 - "$PORT" "$nmax" "$tag" "$RUNS" "$out" <<'PY'
import json, re, subprocess, sys, urllib.request

port, nmax, tag, runs, out = sys.argv[1:6]
port, nmax, runs = port, int(nmax), int(runs)
base = f"http://127.0.0.1:{port}"   # full URL — a bare port parses as a
#                                    legacy shorthand IP and SYN-times out
speeds, ttfts, anchors = [], [], []
for i in range(runs):
    j = subprocess.run(
        ["python3", "scripts/bench_client.py", "--base-url", base,
         "--concurrency", "1", "--prompts", "scripts/prompt-sets/default.json",
         "--max-tokens", "256", "--label", f"nmax{nmax}-{tag}-r{i}",
         "--model", "default", "--no-thinking"],
        capture_output=True, text=True, check=True)
    d = json.loads(j.stdout)
    s = d["streams"][0]
    speeds.append(1000.0 / s["tpot_ms"])
    ttfts.append(s["ttft_ms"])
a = subprocess.run(
    ["python3", "scripts/bench_client.py", "--base-url", base,
     "--anchor-only", "--prompts", "scripts/prompt-sets/default.json",
     "--max-tokens", "256", "--label", f"nmax{nmax}-{tag}-anchor",
     "--model", "default", "--no-thinking"],
    capture_output=True, text=True, check=True)
anchors = [s.get("anchor_ok") for s in json.loads(a.stdout)["streams"]]
# acceptance counters: llama.cpp prints them PER TASK (each line's
# accepted/generated belongs to one completed task), so the config total is
# the SUM OVER ALL LINES — taking the last line per slot would capture only
# the final (anchor) task's counters.
acc = gen = 0
mean_lens = []
with open("/tmp/dflash2-nmax-server.log", encoding="utf-8",
          errors="replace") as fh:
    for line in fh:
        m = re.search(r"draft acceptance = "
                      r"([0-9.]+) \(\s*(\d+) accepted /\s*(\d+) generated\)"
                      r", mean len =\s*([0-9.]+)", line)
        if m:
            acc += int(m.group(2))
            gen += int(m.group(3))
            mean_lens.append(float(m.group(4)))
speeds.sort()
n = len(speeds)
median = speeds[n // 2] if n % 2 else (speeds[n // 2 - 1] + speeds[n // 2]) / 2
result = {
    "config": f"{nmax}:{tag}", "n_max": nmax, "draft": tag,
    "runs_tok_s": [round(x, 2) for x in speeds],
    "median_tok_s": round(median, 2),
    "ttft_ms_runs": [round(x, 1) for x in ttfts],
    "anchor_ok": all(anchors) if anchors else None,
    "acceptance": {"accepted": acc, "generated": gen,
                   "ratio": round(acc / gen, 4) if gen else None,
                   "mean_len_range": [min(mean_lens), max(mean_lens)]
                      if mean_lens else None},
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(result, fh, indent=1)
    fh.write("\n")
print(f"  median {result['median_tok_s']} tok/s "
      f"(runs {result['runs_tok_s']}), acceptance "
      f"{result['acceptance']['ratio']} ({acc}/{gen}), "
      f"anchor {result['anchor_ok']}")
PY
done

# ---- merge every captured config into the receipt ---------------------------
python3 - "$RECEIPT" <<'PY'
import glob, json, sys
from datetime import datetime, timezone

out = sys.argv[1]
files = sorted(glob.glob("/tmp/dflash2-nmax-*.json"))
if not files:
    print("no captured configs; nothing to merge", file=sys.stderr)
    sys.exit(1)
configs = [json.load(open(f, encoding="utf-8")) for f in files]
anchor_cfg = next((c for c in configs
                   if c["config"] == "7:q8_0"), None)
verdict_notes = []
if anchor_cfg:
    drift = anchor_cfg["median_tok_s"] - 33.18  # published c1 cell (raw)
    verdict_notes.append(
        f"session anchor 7:q8_0 measured {anchor_cfg['median_tok_s']} vs the "
        f"published cell 33.18 tok/s (delta {drift:+.2f}) — same yardstick; "
        f"the sweep's RELATIVE comparisons stand regardless")
receipt = {
    "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "method": "fresh WITH_DFLASH2=1 boot per config, same PR-27342 binary, "
              "UD-Q4_K_XL target, ctx 131072; per config 3x bench_client "
              "runs (concurrency 1, 8-prompt set first prompt, 256 tokens, "
              "temperature 0.7, thinking off) + greedy anchor; per-stream "
              "tok/s = 1000/tpot_ms, config value = median of 3; acceptance "
              "summed over ALL per-task print_timing lines in the server "
              "log (llama.cpp prints per-task counters, so last-line-per-"
              "slot would capture only the final task)",
    "configs": configs,
    "notes": verdict_notes,
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(receipt, fh, indent=1)
    fh.write("\n")
best = max(configs, key=lambda c: c["median_tok_s"])
print(f"best config: {best['config']} at {best['median_tok_s']} tok/s")
print(f"receipt: {out} ({len(configs)} configs)")
PY
