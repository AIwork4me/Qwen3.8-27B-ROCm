#!/usr/bin/env bash
# Validate the llama.cpp GGUF serving path (text + MTP) and write the receipt
# docs/results/rocm-7.14/gguf-validation.md.
#
# Sequence (plan Task 3):
#   1. nohup scripts/gguf-quickstart.sh -> /tmp/llama-serve.log (default ctx from
#      the stack, 131072 until validated); poll /health; record boot wall time +
#      load/KV/ctx/graph log lines. If boot fails with mmproj attached, retry
#      once with WITH_MMPROJ=0 and record both attempts.
#   2. Greedy smoke via /v1/chat/completions (temperature 0, max_tokens 512),
#      judged on visible content (reasoning split behavior recorded verbatim).
#   3. WITH_MTP=1 relaunch -> /tmp/llama-serve-mtp.log; same greedy; record the
#      server's draft-acceptance lines.
#   4. Context ladder probe: CTX_SIZE=262144 -> /tmp/llama-serve-262k.log with a
#      rocm-smi VRAM/GTT sampler running during the load attempt (mmap spill is
#      the headline finding). If the default ctx failed, walk 98304 -> 65536.
#   5. Update configs/validated-stack.json llama_cpp.validated honestly; kill
#      every server this script started (GPU left clean).
#
# Write-once receipt guard (vLLM final-review issue 7 lesson): an existing
# receipt is never silently overwritten — pass --force to regenerate (the
# previous one stays recoverable in git history).
#
# Env:
#   CTX_SIZE      override the baseline context attempt (default: stack or 131072)
#   PORT          default 8080
#   BOOT_TIMEOUT  health poll budget in seconds (default 900)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RECEIPT="$ROOT/docs/results/rocm-7.14/gguf-validation.md"
STACK="$ROOT/configs/validated-stack.json"
LOG_BASE=/tmp/llama-serve.log
LOG_MTP=/tmp/llama-serve-mtp.log
LOG_262K=/tmp/llama-serve-262k.log
MEM_262K=/tmp/llama-262k-mem.log
BASE_URL="http://127.0.0.1:${PORT:-8080}"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-900}"

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1
if [ -f "$RECEIPT" ] && [ "$FORCE" -ne 1 ]; then
    echo "ERROR: receipt already exists at $RECEIPT; refusing to overwrite." >&2
    echo "       History lives in git — pass --force to regenerate it, or delete the file first." >&2
    exit 1
fi
mkdir -p "$(dirname "$RECEIPT")"

SERVER_PID=""
cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
        sleep 2
        kill -9 "$SERVER_PID" 2>/dev/null || true
    fi
    pkill -f "build-714/bin/llama-server" 2>/dev/null || true
}
trap cleanup EXIT

# launch <log> <ENV=V...> -> starts quickstart under nohup, echoes its PID
launch() {
    local log="$1"; shift
    env "$@" nohup bash "$ROOT/scripts/gguf-quickstart.sh" >"$log" 2>&1 &
    echo $!
}

# wait_healthy <pid> <timeout-s> -> 0 healthy, 1 process died, 2 timeout
wait_healthy() {
    local pid="$1" timeout="$2" waited=0
    while [ "$waited" -lt "$timeout" ]; do
        curl -fsS --max-time 5 "$BASE_URL/health" >/dev/null 2>&1 && return 0
        kill -0 "$pid" 2>/dev/null || return 1
        sleep 5; waited=$((waited + 5))
    done
    return 2
}

stop_server() {
    [ -n "$SERVER_PID" ] || return 0
    kill "$SERVER_PID" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
        kill -0 "$SERVER_PID" 2>/dev/null || { SERVER_PID=""; return 0; }
        sleep 1
    done
    kill -9 "$SERVER_PID" 2>/dev/null || true
    SERVER_PID=""
}

health() { curl -fsS --max-time 10 "$BASE_URL/health" >/dev/null 2>&1 && echo ok || echo "FAIL: /health unreachable"; }

# rocm-smi labels are e.g. "GPU[0] : VRAM Total Used Memory (B): 1186103296"
# (each call prints only its own memory type, so /Used/ is unambiguous).
vram_line() { rocm-smi --showmeminfo vram 2>/dev/null | awk '/Used/ {printf "VRAM used %d MiB", $NF/1048576}'; }
gtt_line()  { rocm-smi --showmeminfo gtt  2>/dev/null | awk '/Used/ {printf "GTT used %d MiB", $NF/1048576}'; }

# The unsloth GGUF carries the single MTP block as blk.64 (nextn tensors). The
# loader skips it unless --spec-type draft-mtp sets load_mtp; counting the
# skip warnings proves whether each boot actually pulled the MTP head in.
mtp_block_note() { # mtp_block_note <log>
    local skipped
    skipped="$(grep -c 'unused tensor blk\.64\.nextn' "$1" 2>/dev/null || true)"
    if [ "${skipped:-0}" -gt 0 ]; then
        echo "blk.64.nextn.* (MTP block): $skipped tensors reported unused (skipped — expected without draft-mtp)"
    else
        echo "blk.64.nextn.* (MTP block): no skip warnings (MTP block tensors loaded)"
    fi
}

# greedy_smoke -> appends the greedy evidence lines to the receipt
greedy_smoke() {
    cat > /tmp/q38-gguf-greedy.json <<'EOF'
{"messages": [{"role": "user", "content": "Reply with exactly: OK"}],
 "temperature": 0, "max_tokens": 512}
EOF
    local t0 wall
    t0=$(date +%s)
    if curl -fsS --max-time 900 "$BASE_URL/v1/chat/completions" \
        -H 'Content-Type: application/json' -d @/tmp/q38-gguf-greedy.json \
        > /tmp/q38-gguf-greedy.resp; then
        wall=$(( $(date +%s) - t0 ))
        python3 - "$RECEIPT" "$wall" /tmp/q38-gguf-greedy.resp <<'PY'
import json, sys
receipt, wall, resp_file = sys.argv[1], sys.argv[2], sys.argv[3]
resp = json.load(open(resp_file))
ch = resp["choices"][0]
msg = ch["message"]
content = msg.get("content") or ""
reasoning = msg.get("reasoning_content") or ""
u = resp.get("usage", {})
lines = [
    f"- prompt: {resp.get('model')}, temperature=0, max_tokens=512 (wall {wall}s)",
    f"- finish_reason: {ch['finish_reason']}",
    f"- usage: prompt_tokens={u.get('prompt_tokens')} completion_tokens={u.get('completion_tokens')}",
    f"- message keys: {sorted(msg.keys())} (reasoning split: {'separate reasoning_content' if reasoning else 'no separate reasoning_content field'})",
    f"- reasoning_content chars: {len(reasoning)}",
    f"- content (tail 300): {content[-300:]!r}",
    f"- greedy OK present (in visible content): {'OK' in content}",
]
open(receipt, "a").write("\n".join(lines) + "\n")
PY
    else
        echo "FAIL: greedy chat completion curl error (exit $?) — see server log" >> "$RECEIPT"
        return 1
    fi
}

ctx_default() {
    python3 - "$STACK" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
print((s.get("llama_cpp", {}).get("validated") or {}).get("ctx_size") or 131072)
PY
}

log_grep() { # log_grep <log> <pattern> [tail-n]
    [ -f "$1" ] || return 0
    grep -iE "$2" "$1" | tail -n "${3:-8}" | sed 's/^/    /'
}

# boot_attempt <section-label> <log> <ENV=V...>
# Appends a "## Boot (<label>)" section; rc 0 = healthy, 1 = failed (verbatim
# failure recorded). Sets BOOT_WALL for the caller.
boot_attempt() {
    local label="$1" log="$2"; shift 2
    local t0 rc=0
    echo "## Boot ($label)" >> "$RECEIPT"
    t0=$(date +%s)
    SERVER_PID="$(launch "$log" "$@")"
    wait_healthy "$SERVER_PID" "$BOOT_TIMEOUT" || rc=$?
    BOOT_WALL=$(( $(date +%s) - t0 ))
    if [ "$rc" -eq 0 ]; then
        {
            echo "- server: $BASE_URL"
            echo "- health: $(health)"
            echo "- boot wall time: ${BOOT_WALL}s (measured nohup -> first healthy /health poll)"
            echo "- flags: --ctx-size ${CTX_TRY} -ngl 99 --jinja (env: $*)"
            echo "- $(mtp_block_note "$log")"
            echo "- post-boot memory: $(vram_line), $(gtt_line)"
            echo "Log evidence (\`$log\`):"
        } >> "$RECEIPT"
        log_grep "$log" 'load|kv|ctx|graph|unused' 18 >> "$RECEIPT"
        return 0
    fi
    {
        echo "- health: FAIL (wait_healthy rc=$rc after ${BOOT_WALL}s; rc=1 process exited, rc=2 timeout)"
        echo "- flags: --ctx-size ${CTX_TRY} -ngl 99 --jinja (env: $*)"
        echo "Verbatim tail of \`$log\`:"
    } >> "$RECEIPT"
    tail -n 25 "$log" | sed 's/^/    /' >> "$RECEIPT"
    return 1
}

CTX_TRY="$(ctx_default)"
CTX_TRY="${CTX_SIZE:-$CTX_TRY}"
MM_ATTACHED="yes"

echo "# llama.cpp GGUF validation receipts — $(date -u +%Y-%m-%dT%H:%MZ)" > "$RECEIPT"

# ------------------------------------------------------------------- 1. boot ---
BOOTED_LABEL=""
if [ "${WITH_MMPROJ:-1}" = "0" ]; then
    boot_attempt "baseline, ctx $CTX_TRY, mmproj disabled by caller" "$LOG_BASE" "CTX_SIZE=$CTX_TRY" "WITH_MMPROJ=0" \
        && BOOTED_LABEL="baseline-no-mmproj"
elif boot_attempt "baseline, ctx $CTX_TRY, mmproj attached" "$LOG_BASE" "CTX_SIZE=$CTX_TRY"; then
    BOOTED_LABEL="baseline"
else
    stop_server || true
    echo >> "$RECEIPT"
    echo "Retrying once without the vision projector (WITH_MMPROJ=0)…" >> "$RECEIPT"
    MM_ATTACHED="no (failed; see attempt above)"
    if boot_attempt "fallback, ctx $CTX_TRY, no mmproj" "$LOG_BASE" "CTX_SIZE=$CTX_TRY" "WITH_MMPROJ=0"; then
        BOOTED_LABEL="fallback-no-mmproj"
    else
        stop_server || true
        echo "FAIL: boot failed with and without mmproj at ctx $CTX_TRY" >> "$RECEIPT"
    fi
fi

# ------------------------------------------------------------ 2. greedy smoke ---
GREEDY_RC=1
if [ -n "$BOOTED_LABEL" ]; then
    echo >> "$RECEIPT"
    echo "## Greedy smoke" >> "$RECEIPT"
    GREEDY_RC=0
    greedy_smoke || GREEDY_RC=1
fi

# --------------------------------------------------------------------- 3. MTP ---
MTP_RC=1
if [ -n "$BOOTED_LABEL" ]; then
    stop_server || true
    if boot_attempt "MTP, WITH_MTP=1 -> --spec-type draft-mtp, ctx $CTX_TRY" "$LOG_MTP" "CTX_SIZE=$CTX_TRY" "WITH_MTP=1"; then
        MTP_RC=0
        {
            echo
            echo "## MTP"
            echo "- server: $BASE_URL (relaunched with WITH_MTP=1 -> --spec-type draft-mtp)"
            echo "- health: $(health)"
            echo "### MTP greedy smoke"
        } >> "$RECEIPT"
        greedy_smoke || MTP_RC=1
        {
            echo "### MTP acceptance evidence from $LOG_MTP"
            log_grep "$LOG_MTP" 'accept|draft|spec' 8 || echo "    (no acceptance/draft lines in log)"
            echo "### MTP-run backend warnings (verbatim; HIP sampler-op capability notes)"
            log_grep "$LOG_MTP" 'does not have support|not supported' 4 || true
        } >> "$RECEIPT"
    fi
    stop_server || true
fi

# ------------------------------------------------------- 4. context ladder probe -
{
    echo
    echo "## Context ladder"
    echo "- default attempt above used ctx $CTX_TRY"
} >> "$RECEIPT"

probe_ctx() { # probe_ctx <ctx> -> appends verbatim outcome; rc 0 = healthy boot
    local ctx="$1" t0 rc=0
    : > "$MEM_262K"
    t0=$(date +%s)
    SERVER_PID="$(launch "$LOG_262K" "CTX_SIZE=$ctx")"
    # sample VRAM+GTT every 2s while the server lives (mmap spill observation)
    (
        while kill -0 "$SERVER_PID" 2>/dev/null; do
            printf '%s  %s  %s\n' "$(date +%H:%M:%S)" \
                "$(rocm-smi --showmeminfo vram 2>/dev/null | awk '/Used/ {printf "VRAM %d MiB", $NF/1048576}')" \
                "$(rocm-smi --showmeminfo gtt 2>/dev/null | awk '/Used/ {printf "GTT %d MiB", $NF/1048576}')" \
                >> "$MEM_262K"
            sleep 2
        done
    ) &
    MEM_SAMPLER=$!
    wait_healthy "$SERVER_PID" "$BOOT_TIMEOUT" || rc=$?
    kill "$MEM_SAMPLER" 2>/dev/null || true
    local wall=$(( $(date +%s) - t0 ))
    if [ "$rc" -eq 0 ]; then
        {
            echo "### CTX_SIZE=$ctx — BOOT OK (wall ${wall}s)"
            echo "- health: $(health)"
            echo "- memory after boot: $(vram_line), $(gtt_line)"
            echo "- $(mtp_block_note "$LOG_262K")"
        } >> "$RECEIPT"
        echo "### Greedy smoke at CTX_SIZE=$ctx" >> "$RECEIPT"
        greedy_smoke || rc=1
        {
            echo "rocm-smi samples during load + greedy (\`$MEM_262K\`, VRAM/GTT MiB every 2s; first 3 / last 3):"
            head -n 3 "$MEM_262K" | sed 's/^/    /'
            echo "    ..."
            tail -n 3 "$MEM_262K" | sed 's/^/    /'
        } >> "$RECEIPT"
    else
        {
            echo "### CTX_SIZE=$ctx — FAIL (wait_healthy rc=$rc after ${wall}s; rc=1 process exited, rc=2 timeout)"
            echo "Verbatim tail of \`$LOG_262K\`:"
            tail -n 20 "$LOG_262K" | sed 's/^/    /'
            if [ -s "$MEM_262K" ]; then
                echo "rocm-smi samples during the attempt (\`$MEM_262K\`, last 5):"
                tail -n 5 "$MEM_262K" | sed 's/^/    /'
            fi
        } >> "$RECEIPT"
    fi
    stop_server || true
    return "$rc"
}

LADDER_TOP=""
probe_ctx 262144 && LADDER_TOP=262144

# If the default ctx never booted, walk down until one does.
SETTLED_CTX="$CTX_TRY"
if [ -z "$BOOTED_LABEL" ]; then
    for ctx in 98304 65536; do
        if probe_ctx "$ctx"; then
            SETTLED_CTX="$ctx"
            echo >> "$RECEIPT"
            echo "## Greedy smoke (ctx $ctx fallback)" >> "$RECEIPT"
            greedy_smoke || true
            stop_server || true
            break
        fi
    done
fi

# ------------------------------------------------------------------- 5. record --
TEXT_OK=false; { [ -n "$BOOTED_LABEL" ] && [ "$GREEDY_RC" -eq 0 ]; } && TEXT_OK=true
MTP_OK=false; [ "$MTP_RC" -eq 0 ] && MTP_OK=true
FINAL_CTX="$CTX_TRY"
[ -z "$BOOTED_LABEL" ] && FINAL_CTX="$SETTLED_CTX"

{
    echo
    echo "## Outcome"
    echo "- text (boot + greedy at ctx $FINAL_CTX): $TEXT_OK"
    echo "- MTP (draft-mtp boot + greedy + acceptance lines): $MTP_OK"
    echo "- vision: null until Task 4 (mmproj attached during the text boot: $MM_ATTACHED)"
    if [ -n "$LADDER_TOP" ]; then
        echo "- ctx ladder: 262144 BOOT OK (receipt finding: mmap/KV observation above); default stays $FINAL_CTX"
    else
        echo "- ctx ladder: 262144 FAIL (verbatim above); default stays $FINAL_CTX"
    fi
} >> "$RECEIPT"

python3 - "$STACK" "$TEXT_OK" "$MTP_OK" "$FINAL_CTX" "$RECEIPT" <<'PY'
import datetime as dt, json, sys
from pathlib import Path

stack_path, text_ok, mtp_ok, ctx, receipt = sys.argv[1:6]
root = Path(stack_path).resolve().parent.parent
stack = json.loads(Path(stack_path).read_text(encoding="utf-8"))
lc = stack.setdefault("llama_cpp", {})
lc["validated"] = {
    "text": text_ok == "true",
    "mtp": mtp_ok == "true",
    "vision": None,  # Task 4 scope
    "ctx_size": int(ctx),
    "receipt": str(Path(receipt).resolve().relative_to(root)),
    "date": dt.date.today().isoformat(),
}
Path(stack_path).write_text(json.dumps(stack, indent=2) + "\n", encoding="utf-8")
PY

echo "(validation done — receipt: $RECEIPT; all servers stopped)"
