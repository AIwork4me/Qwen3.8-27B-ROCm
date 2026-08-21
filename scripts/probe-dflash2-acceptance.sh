#!/usr/bin/env bash
# probe-dflash2-acceptance.sh — DFlash2 draft acceptance under two sampling
# regimes on the SAME binary/prompts: the project bench convention
# (temperature 0.7 / top_p 0.95) vs the vendor's recommended sampling
# (temperature 1.0 / top_p 0.95 / top_k 20, per the model card's evaluation
# section). Each arm boots its own WITH_DFLASH2=1 server so the server's
# cumulative draft-acceptance counters are fresh per arm; the probe runs the
# repo's 8-prompt bench set (256 tokens, thinking off) and then parses the
# per-slot "draft acceptance = R (A accepted / G generated), mean len = L"
# lines from the server log, summing across slots.
#
# Motivation: docs/results/dflash2/experiments.md F1 measured acceptance
# 0.36 under the project bench and hypothesized the vendor's ~5/7 acceptance
# is workload/sampling-dependent. This probe separates the sampling variable
# (same prompts, same binary, only the sampling regime changes).
#
# Usage:
#   bash scripts/probe-dflash2-acceptance.sh [--out FILE] [--port N]
# Env: LLAMA_SERVER (default build-714-dflash2 — the DFlash2 PR build, BOTH
#      arms), CTX_SIZE, DFLASH_FILE, MAX_TOKENS (default 256).
# Output: JSON receipt (default docs/results/dflash2/acceptance-probe.json);
#      exit 0 iff both arms produced countable acceptance lines.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8097}"
OUT="docs/results/dflash2/acceptance-probe.json"
MAX_TOKENS="${MAX_TOKENS:-256}"
while [ $# -gt 0 ]; do
    case "$1" in
        --out)  OUT="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        -h|--help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

SERVER="${LLAMA_SERVER:-$ROOT/third_party/llama.cpp/build-714-dflash2/bin/llama-server}"
[ -x "$SERVER" ] || {
    echo "ERROR: llama-server not found at $SERVER" >&2
    echo "       run scripts/07-build-llama-dflash2.sh first." >&2
    exit 1
}
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 required" >&2; exit 1; }
command -v curl  >/dev/null 2>&1 || { echo "ERROR: curl required" >&2; exit 1; }

PROBE_PID=""
trap 'stop_server' EXIT

stop_server() {
    [ -n "${PROBE_PID:-}" ] || return 0
    local PARENT="$PROBE_PID"
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

# run_arm <temp> <top_p> <top_k|-> : boot fresh, run the 8-prompt set, parse
# acceptance counters, leave /tmp/dflash2-accept-<tag>.json
run_arm() { # run_arm <tag> <temp> <top_p> <top_k-or-empty>
    local tag="$1" temp="$2" top_p="$3" top_k="$4"
    stop_server; sleep 2
    echo "== arm '$tag' (temperature=$temp top_p=$top_p top_k=${top_k:-off}) =="
    nohup env LLAMA_SERVER="$SERVER" PORT="$PORT" CTX_SIZE="${CTX_SIZE:-131072}" \
        WITH_DFLASH2=1 bash scripts/gguf-quickstart.sh \
        >"/tmp/dflash2-accept-server.log" 2>&1 &
    PROBE_PID=$!
    for _ in $(seq 1 240); do
        curl -sf -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
        if ! kill -0 "$PROBE_PID" 2>/dev/null; then
            echo "ERROR: server exited before /health; log tail:" >&2
            tail -n 20 /tmp/dflash2-accept-server.log >&2
            exit 1
        fi
        sleep 3
    done
    curl -sf -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || {
        echo "ERROR: /health not ready within 12 min" >&2
        tail -n 20 /tmp/dflash2-accept-server.log >&2
        exit 1
    }
    python3 - "$PORT" "$temp" "$top_p" "$top_k" "$MAX_TOKENS" \
        "/tmp/dflash2-accept-$tag.json" "/tmp/dflash2-accept-server.log" <<'PY'
import json, re, sys, time, urllib.request

port, temp, top_p, top_k, max_tokens, out, logpath = sys.argv[1:8]
port, temp, top_p, max_tokens = port, float(temp), float(top_p), int(max_tokens)
prompts = [p["text"] for p in json.load(
    open("scripts/prompt-sets/default.json", encoding="utf-8"))["prompts"]]
for text in prompts:
    body = {"messages": [{"role": "user", "content": text}],
            "max_tokens": max_tokens, "temperature": temp, "top_p": top_p,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False}}
    if top_k and top_k != "-":
        body["top_k"] = int(top_k)
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        json.load(r)
# Parse the LAST cumulative acceptance line per slot; sum across slots.
per_slot = {}
with open(logpath, encoding="utf-8", errors="replace") as fh:
    for line in fh:
        m = re.search(r"slot print_timing: id\s+(\d+).*?draft acceptance = "
                      r"([0-9.]+) \(\s*(\d+) accepted /\s*(\d+) generated\)"
                      r", mean len =\s*([0-9.]+)", line)
        if m:
            per_slot[int(m.group(1))] = (int(m.group(3)), int(m.group(4)),
                                         float(m.group(5)))
acc = sum(v[0] for v in per_slot.values())
gen = sum(v[1] for v in per_slot.values())
mean_lens = [v[2] for v in per_slot.values()]
result = {"accepted": acc, "generated": gen,
          "acceptance": (acc / gen) if gen else None,
          "mean_len_min": min(mean_lens) if mean_lens else None,
          "mean_len_max": max(mean_lens) if mean_lens else None,
          "slots_reporting": len(per_slot),
          "sampling": {"temperature": temp, "top_p": top_p,
                       "top_k": (int(top_k) if top_k not in ("", "-") else None)},
          "prompts": len(prompts), "max_tokens": max_tokens}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(result, fh, indent=1)
    fh.write("\n")
print(f"  accepted/gen = {acc}/{gen}"
      f" (acceptance {result['acceptance']:.4f}, mean len "
      f"{result['mean_len_min']}..{result['mean_len_max']},"
      f" {result['slots_reporting']} slots)")
PY
}

echo "DFlash2 acceptance probe (same binary both arms: $SERVER)"
run_arm project07 0.7 0.95 -
run_arm vendor10  1.0 0.95 20

python3 - /tmp/dflash2-accept-project07.json /tmp/dflash2-accept-vendor10.json "$OUT" <<'PY'
import json, sys
from datetime import datetime, timezone

proj, vend, out = sys.argv[1:4]
p, v = json.load(open(proj)), json.load(open(vend))
ok = p["generated"] > 0 and v["generated"] > 0
receipt = {
    "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "method": "same llama.cpp PR-27342 binary, same 8-prompt bench set, "
              "256 tokens, thinking off; only the sampling regime changes; "
              "fresh server per arm (cumulative counters); counters summed "
              "across slots from the server log's print_timing lines",
    "verdict": "OK" if ok else "UNCOUNTABLE",
    "project_bench_sampling": p,
    "vendor_recommended_sampling": v,
}
if ok:
    receipt["acceptance_delta"] = round(v["acceptance"] - p["acceptance"], 4)
with open(out, "w", encoding="utf-8") as fh:
    json.dump(receipt, fh, indent=1)
    fh.write("\n")
print(f"project(0.7) acceptance {p['acceptance']:.4f} ({p['accepted']}/{p['generated']})")
print(f"vendor(1.0/k20) acceptance {v['acceptance']:.4f} ({v['accepted']}/{v['generated']})")
print(f"receipt: {out}")
sys.exit(0 if ok else 1)
PY
