#!/usr/bin/env bash
# Validate the vLLM server (text path + MTP) and write receipts to
# docs/results/rocm-7.14/vllm-validation.md.
#
# Two passes, matching plan Task 5:
#   baseline: 04-validate-vllm.sh [server-log]      — (re)creates the receipt
#             with ## Boot + ## Greedy smoke + ## Context probe
#   mtp:      04-validate-vllm.sh --mtp [server-log] — appends ## MTP
#             (health + greedy re-run + acceptance-rate lines from the log)
#
# The server itself (scripts/03-serve-vllm.sh, optionally --mtp) must already
# be listening on $BASE_URL; this script never starts or stops it — boot wall
# time comes from the caller (BOOT_SECONDS env, measured nohup->first healthy
# poll). jq-free by design: request parsing is python3.
#
# Env:
#   BASE_URL      default http://127.0.0.1:8000
#   BOOT_SECONDS  optional wall-clock boot time measured by the launcher
#   SERVE_CONF    conf used for the running server (default per mode)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
RECEIPT="$ROOT/docs/results/rocm-7.14/vllm-validation.md"
mkdir -p "$(dirname "$RECEIPT")"

MODE="baseline"
if [[ "${1:-}" == "--mtp" ]]; then MODE="mtp"; shift; fi
LOG="${1:-${VLLM_LOG:-}}"
CONF_DEFAULT="$ROOT/configs/serve-args.conf"
[[ "$MODE" == "mtp" ]] && CONF_DEFAULT="$ROOT/configs/serve-args-mtp.conf"
CONF="${SERVE_CONF:-$CONF_DEFAULT}"

health() { curl -fsS --max-time 10 "$BASE_URL/health" >/dev/null 2>&1 && echo ok || echo "FAIL: /health unreachable"; }

conf_flags() {
    awk 'NF && $1 !~ /^#/ { printf "%s ", $0 } END { print "" }' "$CONF"
}

log_grep() { # log_grep <pattern> [tail-n]
    [[ -n "$LOG" && -f "$LOG" ]] || return 0
    grep -iE "$1" "$LOG" | tail -n "${2:-8}" | sed 's/^/    /'
}

# POST <json-file> [stream] -> response (stdout); curl exit code preserved.
post() {
    local extra=()
    [[ "${2:-}" == "stream" ]] && extra=(-N)
    curl -fsS --max-time 900 "${extra[@]}" "$BASE_URL/v1/chat/completions" \
        -H 'Content-Type: application/json' -d @"$1"
}

# ---------------------------------------------------------------- baseline --
if [[ "$MODE" == "baseline" ]]; then
    echo "# vLLM validation receipts — $(date -u +%Y-%m-%dT%H:%MZ)" > "$RECEIPT"
    cat >> "$RECEIPT" <<EOF
## Boot
- server: $BASE_URL
- health: $(health)
- boot wall time: ${BOOT_SECONDS:-unknown}s (measured nohup -> first healthy /health poll)
- conf: $CONF
- flags: $(conf_flags)

Log evidence (\`$LOG\`):
EOF
    {
        log_grep 'model loading took'
        log_grep 'KV cache|Maximum concurrency|max.*seq.*len|memory' 6
    } >> "$RECEIPT"

    # ---- greedy smoke: reasoning model thinks first; judge the CONTENT field
    cat > /tmp/q38-greedy.json <<'EOF'
{"model": "qwen3.8-27b",
 "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
 "temperature": 0, "max_tokens": 512}
EOF
    echo >> "$RECEIPT"
    echo "## Greedy smoke" >> "$RECEIPT"
    t0=$(date +%s)
    if post /tmp/q38-greedy.json > /tmp/q38-greedy.resp; then
        python3 - "$RECEIPT" "$(( $(date +%s) - t0 ))" /tmp/q38-greedy.resp <<'PY'
import json, sys
receipt, wall, resp_file = sys.argv[1], sys.argv[2], sys.argv[3]
resp = json.load(open(resp_file))
ch = resp["choices"][0]
msg, content, reasoning = ch["message"], ch["message"].get("content") or "", ch["message"].get("reasoning_content") or ""
u = resp.get("usage", {})
lines = [
    f"- prompt: {resp['model']}, temperature=0, max_tokens=512 (wall {wall}s)",
    f"- finish_reason: {ch['finish_reason']}",
    f"- usage: prompt_tokens={u.get('prompt_tokens')} completion_tokens={u.get('completion_tokens')}",
    f"- reasoning chars (hidden reasoning_content): {len(reasoning)}",
    f"- content: {content!r}",
    f"- greedy OK present (in content): {'OK' in content}",
]
open(receipt, "a").write("\n".join(lines) + "\n")
PY
    else
        echo "FAIL: greedy chat completion curl error (exit $?) — see server log" >> "$RECEIPT"
    fi

    # ---- context probe: functional only (~2000-token filler, max_tokens 32)
    echo >> "$RECEIPT"
    echo "## Context probe" >> "$RECEIPT"
    python3 - "$RECEIPT" "$BASE_URL" <<'PY'
import json, sys, time, urllib.request
receipt, base = sys.argv[1], sys.argv[2]

# ~2000-token deterministic filler (~1 token per 4 chars of numbered prose).
filler = " ".join(f"Paragraph {i:04d} records the validation harness filler sample."
                  for i in range(310))
payload = {"model": "qwen3.8-27b", "messages": [{"role": "user", "content":
           filler + "\n\nReply with exactly: OK"}], "temperature": 0,
           "max_tokens": 32, "stream": True}

t0 = time.monotonic(); first = None
req = urllib.request.Request(base + "/v1/chat/completions",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=900) as r:
        for line in r:
            if first is None and line.startswith(b"data:") and b"[DONE]" not in line:
                first = time.monotonic() - t0  # TTFT: first streamed chunk
    total = time.monotonic() - t0
    open(receipt, "a").write(
        f"- filler ~2000 tokens, max_tokens=32, stream=True\n"
        f"- TTFT (first data chunk): {first:.2f}s; stream wall: {total:.2f}s\n")
except Exception as e:
    open(receipt, "a").write(f"FAIL: context probe: {e!r}\n")
PY
    # record the actual prompt length from a non-streaming repeat
    python3 - "$RECEIPT" "$BASE_URL" <<'PY'
import json, sys, urllib.request
receipt, base = sys.argv[1], sys.argv[2]
filler = " ".join(f"Paragraph {i:04d} records the validation harness filler sample."
                  for i in range(310))
payload = {"model": "qwen3.8-27b", "messages": [{"role": "user", "content":
           filler + "\n\nReply with exactly: OK"}], "temperature": 0,
           "max_tokens": 32}
req = urllib.request.Request(base + "/v1/chat/completions",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"})
try:
    resp = json.load(urllib.request.urlopen(req, timeout=900))
    u = resp.get("usage", {})
    ch = resp["choices"][0]
    open(receipt, "a").write(
        f"- non-stream repeat: prompt_tokens={u.get('prompt_tokens')} "
        f"completion_tokens={u.get('completion_tokens')} "
        f"finish_reason={ch['finish_reason']} content={ch['message'].get('content')!r}\n")
except Exception as e:
    open(receipt, "a").write(f"FAIL: context probe non-stream repeat: {e!r}\n")
PY
    echo "(baseline pass done — run MTP pass per plan Task 5 step 3b: restart server with --mtp, then $0 --mtp /tmp/vllm-serve-mtp.log)"
    exit 0
fi

# ------------------------------------------------------------------ mtp pass --
{ echo; echo "## MTP"; } >> "$RECEIPT"
cat >> "$RECEIPT" <<EOF
- server: $BASE_URL (relaunched with configs/serve-args-mtp.conf)
- health: $(health)
- conf: $CONF
- flags: $(conf_flags)
EOF
cat > /tmp/q38-greedy.json <<'EOF'
{"model": "qwen3.8-27b",
 "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
 "temperature": 0, "max_tokens": 512}
EOF
t0=$(date +%s)
if post /tmp/q38-greedy.json > /tmp/q38-greedy-mtp.resp; then
    python3 - "$RECEIPT" "$(( $(date +%s) - t0 ))" /tmp/q38-greedy-mtp.resp <<'PY'
import json, sys
receipt, wall, resp_file = sys.argv[1], sys.argv[2], sys.argv[3]
resp = json.load(open(resp_file))
ch = resp["choices"][0]
msg = ch["message"]
content, reasoning = msg.get("content") or "", msg.get("reasoning_content") or ""
u = resp.get("usage", {})
lines = [
    f"- prompt: same greedy prompt, temperature=0, max_tokens=512 (wall {wall}s)",
    f"- finish_reason: {ch['finish_reason']}",
    f"- usage: prompt_tokens={u.get('prompt_tokens')} completion_tokens={u.get('completion_tokens')}",
    f"- reasoning chars (hidden): {len(reasoning)}",
    f"- content: {content!r}",
    f"- greedy OK present (in content): {'OK' in content}",
]
open(receipt, "a").write("\n".join(lines) + "\n")
PY
else
    echo "FAIL: MTP greedy chat completion curl error (exit $?) — see server log" >> "$RECEIPT"
fi
{
    echo "Acceptance / spec-decode evidence from $LOG:"
    log_grep 'acceptance|spec' 6 || echo "    (no acceptance/spec lines in log)"
} >> "$RECEIPT"
echo "(MTP pass done)"
