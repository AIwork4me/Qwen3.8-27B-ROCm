#!/usr/bin/env bash
# check-dflash2-equiv.sh — greedy byte-identity: baseline vs DFlash 2 boot.
#
# DFlash 2 is lossless by construction ("greedy output matches the target
# model exactly", model card). This script verifies that claim ON HOST: it
# boots the SAME llama.cpp PR #27342 binary twice — once with no drafter,
# once with WITH_DFLASH2=1 — runs a fixed prompt set greedily (temperature
# 0, thinking disabled, fixed max_tokens) through both, and compares the
# completions byte-for-byte. Any mismatch is a FAIL and a finding.
#
# Pattern adapted from muse-rocm scripts/check_dflash_equiv.sh (DFlash v1).
#
# Usage:
#   bash scripts/check-dflash2-equiv.sh [--arm baseline|dflash2|compare] [--out FILE] [--port N]
#      default (no --arm): baseline then dflash2 then compare, one process —
#      needs a ~20-min uninterrupted window. --arm splits the run for hosts
#      where long-lived driver processes are awkward: capture each arm in its
#      own invocation (state persists in /tmp/dflash2-equiv-<arm>.json), then
#      --arm compare writes the receipt.
# Env: LLAMA_SERVER (default: third_party/llama.cpp/build-714-dflash2 —
#      BOTH arms must boot the same binary for the claim to be about the
#      drafter, not the build), CTX_SIZE, DFLASH_FILE, KEEP_SERVER.
# Output: human verdict + JSON receipt (default
#      docs/results/dflash2/equiv.json); exit 0 iff every prompt matches.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8099}"
OUT="docs/results/dflash2/equiv.json"
ARM="all"
while [ $# -gt 0 ]; do
    case "$1" in
        --out)  OUT="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --arm)  ARM="$2"; shift 2 ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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

boot_and_wait() { # boot_and_wait <extra env...> — env vars come via callers
    nohup env LLAMA_SERVER="$SERVER" PORT="$PORT" "$@" bash scripts/gguf-quickstart.sh \
        >"/tmp/dflash2-equiv-server.log" 2>&1 &
    EQUIV_SERVER_PID=$!
    for _ in $(seq 1 240); do  # model load can take minutes; 240 * 3s = 12 min
        if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
            return 0
        fi
        if ! kill -0 "$EQUIV_SERVER_PID" 2>/dev/null; then
            echo "ERROR: server exited before /health went ready; log tail:" >&2
            tail -n 20 /tmp/dflash2-equiv-server.log >&2
            return 1
        fi
        sleep 3
    done
    echo "ERROR: /health not ready within 12 min; log tail:" >&2
    tail -n 20 /tmp/dflash2-equiv-server.log >&2
    return 1
}

stop_server() {
    [ -n "${EQUIV_SERVER_PID:-}" ] || return 0
    local PARENT="$EQUIV_SERVER_PID"
    local CHILDREN
    CHILDREN="$(pgrep -P "$PARENT" 2>/dev/null || true)"
    # SC2086-clean: pgrep output word-split deliberately into kill args via
    # a read array (same idiom as the quickstart's EXTRA_ARGS handling).
    local -a kids=()
    [ -n "$CHILDREN" ] && read -r -a kids <<< "$CHILDREN"
    kill "$PARENT" ${kids:+"${kids[@]}"} 2>/dev/null || true
    pkill -f "llama-server.*--port $PORT" 2>/dev/null || true
    for _ in $(seq 1 30); do
        pgrep -f "llama-server.*--port $PORT" >/dev/null 2>&1 || return 0
        sleep 2
    done
    # A server wedged mid-teardown (observed: "Received second interrupt"
    # then a hang holding ~27 GiB VRAM) must not leak into the next arm —
    # escalate after the SIGTERM grace window.
    echo "WARN: llama-server on :$PORT still up after 60s; sending SIGKILL" >&2
    pkill -9 -f "llama-server.*--port $PORT" 2>/dev/null || true
    sleep 3
    pgrep -f "llama-server.*--port $PORT" >/dev/null 2>&1 && \
        echo "ERROR: llama-server on :$PORT survived SIGKILL — clean it up manually before the next arm." >&2
    return 0
}
trap stop_server EXIT

run_arm() { # run_arm <label> <quickstart-env...> -> /tmp/dflash2-equiv-<label>.json
    local label="$1"; shift
    stop_server; sleep 2
    echo "== booting arm '$label' =="
    boot_and_wait "$@" || exit 1
    python3 - "$PORT" "/tmp/dflash2-equiv-$label.json" <<'PY'
import json, sys, urllib.request

port, out = sys.argv[1], sys.argv[2]
base_url = f"http://127.0.0.1:{port}"  # full URL — a bare port would parse
#                                       as a legacy shorthand IP (0.0.x.x)
#                                       and SYN-timeout, not "connection
#                                       refused" (a hard-won gotcha)
# Fixed prompt set: varied surfaces (arithmetic, code, factual recall,
# instruction-following), thinking disabled so the answer budget is visible
# content. Deterministic by construction; changing this list changes the
# claim's scope, not its method.
PROMPTS = [
    ("arith", "Compute step by step, then give the final number on the last line: 17 * 23 - 45."),
    ("code", "Write a Python function is_palindrome(s) that ignores case and spaces. Code only, no prose."),
    ("factual", "Name the four largest planets of the Solar System in order. One per line."),
    ("instr", "Reply with exactly the word: BANANA"),
]
results = {}
for pid, text in PROMPTS:
    body = json.dumps({
        "messages": [{"role": "user", "content": text}],
        "max_tokens": 512,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.load(r)
    msg = resp["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    results[pid] = {"content": content, "reasoning": reasoning,
                    "finish": resp["choices"][0].get("finish_reason"),
                    "tokens": resp.get("usage", {}).get("completion_tokens")}
with open(out, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=1, ensure_ascii=False)
print(f"  arm captured: {len(results)} prompts -> {out}")
PY
}

echo "DFlash2 greedy equivalence check (same binary both arms: $SERVER)"
case "$ARM" in
    baseline) run_arm baseline WITH_DFLASH2=0 ;;
    dflash2)  run_arm dflash2  WITH_DFLASH2=1 ;;
    compare)  : ;;
    all)      run_arm baseline WITH_DFLASH2=0
              run_arm dflash2  WITH_DFLASH2=1 ;;
    *) echo "ERROR: --arm must be baseline|dflash2|compare (got '$ARM')." >&2; exit 2 ;;
esac

if [ "$ARM" != "compare" ] && [ "$ARM" != "all" ]; then
    echo "arm '$ARM' captured; run the other arm, then --arm compare."
    exit 0
fi

for f in /tmp/dflash2-equiv-baseline.json /tmp/dflash2-equiv-dflash2.json; do
    [ -f "$f" ] || { echo "ERROR: $f missing — capture both arms first (--arm baseline, --arm dflash2)." >&2; exit 1; }
done

python3 - /tmp/dflash2-equiv-baseline.json /tmp/dflash2-equiv-dflash2.json "$OUT" <<'PY'
import json, sys
from datetime import datetime, timezone

base_p, df_p, out = sys.argv[1:4]
base, df = json.load(open(base_p)), json.load(open(df_p))
rows, all_ok = [], True
for pid in base:
    same = base[pid]["content"] == df[pid].get("content")
    tok_b, tok_d = base[pid]["tokens"], df[pid].get("tokens")
    rows.append({"id": pid, "match": same,
                 "baseline_tokens": tok_b, "dflash2_tokens": tok_d,
                 "baseline_finish": base[pid]["finish"],
                 "dflash2_finish": df[pid].get("finish")})
    all_ok = all_ok and same
receipt = {
    "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "method": "greedy (temperature 0, thinking disabled, max_tokens 512), "
              "same llama.cpp binary for both arms, byte-identical content required",
    "verdict": "PASS" if all_ok else "FAIL",
    "prompts": rows,
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(receipt, f, indent=1, ensure_ascii=False)
    f.write("\n")
for r in rows:
    print(f"  {r['id']:8s} {'MATCH' if r['match'] else 'MISMATCH'}  "
          f"(tokens {r['baseline_tokens']} vs {r['dflash2_tokens']})")
print(f"VERDICT: {receipt['verdict']} (receipt: {out})")
sys.exit(0 if all_ok else 1)
PY
