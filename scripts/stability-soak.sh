#!/usr/bin/env bash
# stability-soak.sh — sustained-load soak for the recommended config
# (BACKEND=vulkan, MTP depth 1, c1, ctx131072), stability follow-up S1.
#
# Usage:
#   SOAK_DIR=<receipt-dir> scripts/stability-soak.sh [--dry-run]
#
# Boots the cell gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072 EXACTLY the way
# scripts/run-cell-gguf.sh boots it, then runs repeated bench cycles
# (scripts/bench_client.py, same prompt set/args as the runner's bench)
# back-to-back for SOAK_MINUTES, and ends with ONE greedy anchor (same
# anchor invocation the runner uses, same anchor_ok-field gate). Writes a
# soak receipt JSON into SOAK_DIR and prints a non-JSON summary line.
#
# DERIVATION NOTE (binding): scripts/run-cell-gguf.sh is the source of truth
# for the cell -> server env derivation and MUST NOT be refactored from here
# (S1 constraint: no churn of the verified runner, no shared helper). This
# script therefore re-derives the boot with the SAME code shape as the
# runner's (id regex -> backend/mtp/conc/ctx, mtp => depth 1, c1 => default
# unified boot, no -np) and boots through scripts/gguf-quickstart.sh with
# exactly the env the runner passes — the quickstart (untouched) resolves
# the model/mmproj/port flags, so nothing is duplicated. The cell id below
# is pinned: this is a soak of ONE config, not a general runner.
#
# Environment knobs: SOAK_DIR (required — no implicit default; receipts
# never overwrite anything, the dir must be a fresh session dir),
# SOAK_MINUTES (default 30), PORT (8080), HEALTH_TIMEOUT_S (420),
# BENCH_TIMEOUT_S (1800), HEALTH_RECOVER_S (120 — mid-soak health flap
# grace before the soak is aborted as a server death).
#
# Fail-loud: missing SOAK_DIR, non-integer SOAK_MINUTES, missing binary /
# prompt set / rocm-smi, occupied port, boot health timeout. Teardown is
# guaranteed (trap on EXIT) so no orphan llama-server holds the GTT pool;
# a GPU-clean check (GTT drained + no llama-server process) is recorded in
# the receipt and a failure degrades the run.
#
# Receipt schema (follows the cell-receipt field conventions,
# docs/results/matrix-714/cells/*.json): started_utc, server_flags verbatim
# (incl. llama_server_flags), model/pin refs, slot_info from the server log,
# load (rocm-smi VRAM/GTT at load), cycles[] (per-cycle: index, started_utc,
# wall_s, tok_per_s aggregate, stream_median_tok_s, ok/failed, error), one
# anchor block, totals (tok/s min/median/max, first/second-half drift,
# wall_minutes), exit_gpu_clean, script_git_rev.
#
# CI note: --dry-run resolves and prints the plan without launching anything;
# the test suite only exercises --dry-run and the refusal paths.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

QUICKSTART="scripts/gguf-quickstart.sh"
BENCH="scripts/bench_client.py"
PROMPTS="scripts/prompt-sets/default.json"

PORT="${PORT:-8080}"
BASE_URL="http://127.0.0.1:$PORT"
HEALTH_TIMEOUT_S="${HEALTH_TIMEOUT_S:-420}"
BENCH_TIMEOUT_S="${BENCH_TIMEOUT_S:-1800}"
HEALTH_RECOVER_S="${HEALTH_RECOVER_S:-120}"
SOAK_MINUTES="${SOAK_MINUTES:-30}"

usage() {
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------- arguments
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unknown option: $arg (this soaks ONE pinned cell; no cell id argument)" >&2
           usage >&2; exit 2 ;;
    esac
done

if [ -z "${SOAK_DIR:-}" ]; then
    echo "ERROR: SOAK_DIR is required (the soak receipt directory — a fresh stability-session dir; receipts are never overwritten); refusing to guess a default." >&2
    exit 2
fi
case "$SOAK_MINUTES" in
    ''|*[!0-9]*) echo "ERROR: SOAK_MINUTES must be a positive integer (got '$SOAK_MINUTES')." >&2; exit 2 ;;
esac
[ "$SOAK_MINUTES" -ge 1 ] || { echo "ERROR: SOAK_MINUTES must be >= 1 (got $SOAK_MINUTES)." >&2; exit 2; }

# ------------------------------------------------- cell derivation (pinned)
# Same grammar + code shape as scripts/run-cell-gguf.sh (source of truth;
# see DERIVATION NOTE in the header). The id is pinned to the recommended
# config; the regex derivation is kept so the boot cannot silently drift
# from what the runner would derive for this id.
CELL_ID="gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"
ID_RE='^gguf-(hip|vulkan)-udq4kxl-auto-(base|mtp|mtp4)-c(1|4|8|16)-ctx(32768|131072|262144)(-unified)?$'
if [[ "$CELL_ID" =~ $ID_RE ]]; then
    BACKEND="${BASH_REMATCH[1]}"       # hip | vulkan
    MTP_PART="${BASH_REMATCH[2]}"      # base | mtp | mtp4
    CONC="${BASH_REMATCH[3]}"          # 1 | 4 | 8 | 16
    CTX="${BASH_REMATCH[4]}"           # 32768 | 131072 | 262144
    UNIFIED="${BASH_REMATCH[5]:-}"     # -unified suffix or empty
else
    echo "ERROR: pinned cell id '$CELL_ID' no longer matches the id grammar (derive-again from scripts/run-cell-gguf.sh)." >&2
    exit 2
fi

case "$BACKEND" in
    hip)    LLAMA_BIN="$ROOT/third_party/llama.cpp/build-714/bin/llama-server" ;;
    vulkan) LLAMA_BIN="$ROOT/third_party/llama.cpp/build-714-vk/bin/llama-server" ;;
    *)      echo "ERROR: unknown backend '$BACKEND'." >&2; exit 2 ;;
esac
case "$MTP_PART" in
    base) SPEC_DEPTH=0 ;;
    mtp)  SPEC_DEPTH=1 ;;
    mtp4) SPEC_DEPTH=4 ;;
    *)    echo "ERROR: unknown mtp part '$MTP_PART'." >&2; exit 2 ;;
esac
WITH_MTP=0
[ "$MTP_PART" != "base" ] && WITH_MTP=1

# c1 (concurrency 1, no -unified rider): the runner keeps the quickstart
# DEFAULT boot — unified KV pool, no explicit -np — so EXTRA_ARGS stays
# verbatim empty and the quickstart default boot is byte-identical.
EXTRA_ARGS=""
KV_MODE="unified (default boot: auto n_parallel=4, shared ctx pool)"

# The cell-level llama-server flags the runner records in its receipt
# (model/port/mmproj resolution stays inside the quickstart, untouched).
read -r -a CELL_FLAGS <<< "--ctx-size $CTX -ngl 99 --jinja"
if [ "$WITH_MTP" = "1" ]; then
    CELL_FLAGS+=(--spec-type draft-mtp)
    [ "$SPEC_DEPTH" -ge 1 ] && CELL_FLAGS+=(--spec-draft-n-max "$SPEC_DEPTH")
fi
# EXTRA_ARGS is pinned empty (c1); kept verbatim in the plan/receipt anyway.
if [ -n "$EXTRA_ARGS" ]; then
    read -r -a extra_args_arr <<< "$EXTRA_ARGS"
    CELL_FLAGS+=("${extra_args_arr[@]}")
fi

BENCH_CMD=(python3 "$BENCH" --base-url "$BASE_URL" --concurrency "$CONC"
           --prompts "$PROMPTS" --max-tokens 256 --label "$CELL_ID-soak"
           --model default --no-thinking)
ANCHOR_CMD=(python3 "$BENCH" --base-url "$BASE_URL" --anchor-only
            --prompts "$PROMPTS" --max-tokens 256 --label "${CELL_ID}-soak-anchor"
            --model default --no-thinking)

RECEIPT="$SOAK_DIR/soak-$CELL_ID.json"

print_plan() {
    echo "cell          : $CELL_ID (pinned: the recommended config under stability re-measurement)"
    echo "backend       : $BACKEND (binary: ${LLAMA_BIN#"$ROOT"/})"
    echo "server        : $QUICKSTART  (PORT=$PORT)"
    echo "server env    : BACKEND=$BACKEND CTX_SIZE=$CTX WITH_MTP=$WITH_MTP SPEC_DEPTH=$SPEC_DEPTH EXTRA_ARGS='${EXTRA_ARGS}'"
    echo "cell flags    : ${CELL_FLAGS[*]}  (model/port/mmproj resolved by the quickstart)"
    echo "kv semantics  : $KV_MODE"
    echo "soak          : SOAK_MINUTES=$SOAK_MINUTES repeated bench cycles, then ONE greedy anchor"
    echo "health poll   : curl $BASE_URL/health (boot timeout ${HEALTH_TIMEOUT_S}s, mid-soak grace ${HEALTH_RECOVER_S}s)"
    echo "mem snapshot  : rocm-smi --showmeminfo vram + gtt after load (MiB, /1024)"
    echo "bench         : ${BENCH_CMD[*]}"
    echo "anchor        : ${ANCHOR_CMD[*]}  [gate: anchor_ok in the JSON, not exit code]"
    echo "receipt       : $RECEIPT (SOAK_DIR; never overwrites a project cell receipt)"
}

if [ "$DRY_RUN" = "1" ]; then
    echo "DRY RUN — nothing launched, nothing written:"
    print_plan
    exit 0
fi

# ------------------------------------------------------------ real execution
[ -x "$QUICKSTART" ] || { echo "ERROR: $QUICKSTART not found/executable" >&2; exit 3; }
[ -x "$LLAMA_BIN" ] || {
    echo "ERROR: llama-server not found at $LLAMA_BIN" >&2
    echo "       run scripts/06-build-llama-vulkan.sh first (pinned Vulkan build)." >&2
    exit 3
}
[ -f "$PROMPTS" ]    || { echo "ERROR: prompt set $PROMPTS missing" >&2; exit 3; }
command -v rocm-smi >/dev/null 2>&1 || { echo "ERROR: rocm-smi not found (host-only soak)" >&2; exit 3; }
[ -d "$SOAK_DIR" ] || mkdir -p "$SOAK_DIR" || { echo "ERROR: cannot create SOAK_DIR $SOAK_DIR" >&2; exit 3; }
if [ -e "$RECEIPT" ]; then
    echo "ERROR: receipt $RECEIPT already exists (receipts are never overwritten — new facts, new receipts)." >&2
    exit 3
fi

if pgrep -f "llama-server.*--port $PORT" >/dev/null 2>&1; then
    echo "ERROR: a llama-server is already listening on port $PORT; kill it first (GPU clean between runs)." >&2
    exit 3
fi

port_probe_wait() {
    local _
    for _ in $(seq 1 15); do
        if python3 - "$PORT" <<'PY_PORT' 2>/dev/null
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY_PORT
        then return 0; fi
        sleep 2
    done
    return 1
}
port_probe_wait || { echo "ERROR: port $PORT not bindable within 30s" >&2; exit 3; }

LOG="/tmp/soak-$CELL_ID.log"
CYCLES_FILE="/tmp/soak-$CELL_ID-cycles.jsonl"
CYCLE_JSON="/tmp/soak-$CELL_ID-cycle-bench.json"
ANCHOR_JSON="/tmp/soak-$CELL_ID-anchor.json"
rm -f "$LOG" "$CYCLES_FILE" "$CYCLE_JSON" "$ANCHOR_JSON"
touch "$CYCLES_FILE"

mem_used_bytes() { # mem_used_bytes <vram|gtt> -> used bytes (empty on failure)
    rocm-smi --showmeminfo "$1" 2>/dev/null \
        | awk -v kind="$1" 'BEGIN{k=toupper(kind)}
                           index($0, k " Total Used") {print $NF; exit}'
}
mib() { # mib <bytes> -> binary MiB (blank -> blank)
    [ -n "${1:-}" ] && echo $(( $1 / 1048576 )) || echo ""
}

print_plan
echo

SERVER_PID=""
cleanup_server() {
    [ -n "$SERVER_PID" ] || return 0
    kill "$SERVER_PID" 2>/dev/null || true
    local _
    for _ in $(seq 1 60); do
        kill -0 "$SERVER_PID" 2>/dev/null || return 0
        sleep 1
    done
    kill -9 "$SERVER_PID" 2>/dev/null || true
}
trap cleanup_server EXIT

wait_gtt_drain() { # block until GTT returns near the idle baseline (max 150s)
    local _ g
    for _ in $(seq 1 75); do
        g="$(mem_used_bytes gtt)"
        [ -n "$g" ] && [ "$g" -lt $((4 * 1024 * 1024 * 1024)) ] && return 0
        sleep 2
    done
    echo "WARN: GTT did not drain below 4 GiB within 150s of server exit (continuing)" >&2
    return 0
}

SCRIPT_GIT_REV="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
WORKTREE_DIRTY=0
# --porcelain covers untracked files too: the common session flow runs the
# soak BEFORE the script itself is committed, and the receipt must say so.
[ -z "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ] || WORKTREE_DIRTY=1

STARTED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DEGRADED=0
DEGRADED_REASON=""

echo "== booting $QUICKSTART (backend $BACKEND, ctx $CTX, mtp $WITH_MTP, depth $SPEC_DEPTH, extra '${EXTRA_ARGS:-none}') =="
STARTED_S=$SECONDS
PORT="$PORT" BACKEND="$BACKEND" CTX_SIZE="$CTX" WITH_MTP="$WITH_MTP" \
    SPEC_DEPTH="$SPEC_DEPTH" EXTRA_ARGS="$EXTRA_ARGS" \
    nohup bash "$QUICKSTART" >"$LOG" 2>&1 &
SERVER_PID=$!

BOOT_OK=0
while [ $SECONDS -lt $((STARTED_S + HEALTH_TIMEOUT_S)) ]; do
    if curl -sf "$BASE_URL/health" >/dev/null 2>&1; then BOOT_OK=1; break; fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "ERROR: server process died during boot (see $LOG)" >&2
        break
    fi
    sleep 2
done
BOOT_WALL=$((SECONDS - STARTED_S))

SLOT_INFO_JSON='null'
LOAD_JSON='{"vram_mib": null, "gtt_mib": null}'
MODEL_JSON='null'
CYCLES_RAN=0
ABORTED=0
ABORT_REASON=""
ANCHOR_OK=false
ANCHOR_TAIL=""

server_alive() { curl -sf "$BASE_URL/health" >/dev/null 2>&1; }

if [ "$BOOT_OK" != "1" ]; then
    [ "$BOOT_WALL" -ge "$HEALTH_TIMEOUT_S" ] && DEGRADED_REASON="health poll timed out after ${HEALTH_TIMEOUT_S}s"
    [ -z "$DEGRADED_REASON" ] && DEGRADED_REASON="server died during boot"
    echo "ERROR: $DEGRADED_REASON" >&2
    DEGRADED=1
else
    echo "health OK after ${BOOT_WALL}s; settling 3s before the memory snapshot"
    sleep 3

    SLOT_LINE="$(grep -m1 'n_slots = ' "$LOG" | sed 's/^.*initializing,//' | sed 's/^ *//; s/ *$//')"
    SLOT_INFO_JSON="$(SLOT_LINE="$SLOT_LINE" python3 <<'PY'
import os, re, sys
line = os.environ.get("SLOT_LINE", "")
m = re.search(r"n_slots = (\d+), n_ctx_slot = (\d+), kv_unified = '(\w+)'", line)
if not m:
    print("null"); raise SystemExit
import json
print(json.dumps({"n_slots": int(m.group(1)), "n_ctx_slot": int(m.group(2)),
                  "kv_unified": m.group(3), "log_line": line}))
PY
)"
    [ "$SLOT_INFO_JSON" != "null" ] || echo "WARN: no slot semantics line found in $LOG" >&2

    VRAM_B="$(mem_used_bytes vram)"; GTT_B="$(mem_used_bytes gtt)"
    LOAD_JSON="$(VRAM_B="${VRAM_B:-}" GTT_B="${GTT_B:-}" python3 <<'PY'
import json, os
v = os.environ.get("VRAM_B", ""); g = os.environ.get("GTT_B", "")
def mib(s):
    return int(s) // 1048576 if s else None
print(json.dumps({"vram_mib": mib(v), "gtt_mib": mib(g)}))
PY
)"
    echo "load memory : $LOAD_JSON"

    # Model/pin refs (configs are the source of truth; binary version from
    # its own --version, commit from the validated stack pin).
    MODEL_JSON="$(LLAMA_BIN="$LLAMA_BIN" python3 <<'PY'
import json, os, re, subprocess
stack = json.load(open("configs/validated-stack.json"))
vk = stack.get("llama_cpp_vulkan", {})
man = json.load(open("configs/artifact-manifest.json"))
dest = man["sets"]["gguf"]["dest"]
ver = ""
try:
    p = subprocess.run([os.environ["LLAMA_BIN"], "--version"],
                       capture_output=True, text=True, timeout=60)
    # llama-server prints its banner to stderr; capture both.
    ver = (p.stdout or "") + (p.stderr or "")
except Exception:
    pass
m = re.search(r"commit ([0-9a-f]+)", ver)
print(json.dumps({
    "gguf": f"{dest}/Qwen3.8-27B-UD-Q4_K_XL.gguf",
    "mmproj": f"{dest}/mmproj-F16.gguf",
    "llama_server_version": ver.strip().splitlines()[0] if ver.strip() else None,
    "llama_cpp_commit": m.group(1) if m else vk.get("commit"),
    "build_dir": vk.get("build_dir"),
    "icd": vk.get("icd"),
}))
PY
)"
    echo "model/pins  : $MODEL_JSON"

    echo "== soak: repeated bench cycles for ${SOAK_MINUTES} min (concurrency $CONC) =="
    SOAK_START=$SECONDS
    CYCLE_INDEX=0
    while [ $((SECONDS - SOAK_START)) -lt $((SOAK_MINUTES * 60)) ]; do
        if ! server_alive; then
            echo "WARN: health check failed before cycle $((CYCLE_INDEX + 1)); waiting up to ${HEALTH_RECOVER_S}s" >&2
            RECOVER_OK=0
            for _ in $(seq 1 $((HEALTH_RECOVER_S / 2))); do
                sleep 2
                if server_alive; then RECOVER_OK=1; break; fi
                kill -0 "$SERVER_PID" 2>/dev/null || break
            done
            if [ "$RECOVER_OK" != "1" ]; then
                ABORTED=1
                ABORT_REASON="server unhealthy/dead mid-soak before cycle $((CYCLE_INDEX + 1)) (after $(( (SECONDS - SOAK_START) / 60 )) min)"
                break
            fi
            echo "health recovered; continuing" >&2
        fi
        CYCLE_INDEX=$((CYCLE_INDEX + 1))
        CYCLE_RC=0
        timeout "$BENCH_TIMEOUT_S" "${BENCH_CMD[@]}" --label "$CELL_ID-soak-c$CYCLE_INDEX" --out "$CYCLE_JSON" >/dev/null || CYCLE_RC=$?
        CYCLE_JSON="$CYCLE_JSON" CYCLE_INDEX="$CYCLE_INDEX" CYCLE_RC="$CYCLE_RC" \
            NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)" python3 >>"$CYCLES_FILE" <<'PY'
import json, os, statistics, sys
idx = int(os.environ["CYCLE_INDEX"]); rc = int(os.environ["CYCLE_RC"])
rec = {"index": idx, "started_utc": os.environ["NOW_UTC"], "wall_s": None,
       "tok_per_s": None, "stream_median_tok_s": None,
       "ok_streams": 0, "failed_streams": 0, "error": None}
try:
    d = json.load(open(os.environ["CYCLE_JSON"]))
except Exception as e:
    rec["error"] = f"bench client produced no/invalid JSON (rc={rc}): {e}"
    print(json.dumps(rec)); raise SystemExit
agg = d.get("aggregate", {})
rec["wall_s"] = agg.get("wall_s")
rec["tok_per_s"] = agg.get("tok_per_s")
rec["ok_streams"] = agg.get("ok_streams", 0)
rec["failed_streams"] = agg.get("failed_streams", 0)
rates = [1000.0 / s["tpot_ms"] for s in (d.get("streams") or [])
         if s and s.get("ok") and s.get("tpot_ms")]
if rates:
    rec["stream_median_tok_s"] = round(statistics.median(rates), 3)
errs = [s.get("error") for s in (d.get("streams") or []) if s and s.get("error")]
if errs:
    rec["error"] = "; ".join(str(e) for e in errs)[:300]
print(json.dumps(rec))
PY
        # per-cycle stdout line (non-JSON, human tail)
        tail="$(tail -n1 "$CYCLES_FILE")"
        python3 - "$tail" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
tps = f"{r['tok_per_s']:.2f}" if isinstance(r.get("tok_per_s"), (int, float)) else "n/a"
err = f"  err={r['error']}" if r.get("error") else ""
print(f"cycle {r['index']:>3} : tok/s={tps}  ok={r['ok_streams']} failed={r['failed_streams']}{err}")
PY
    done
    CYCLES_RAN=$CYCLE_INDEX
    SOAK_WALL_S=$((SECONDS - SOAK_START))

    if [ "$ABORTED" = "1" ]; then
        echo "ERROR: $ABORT_REASON" >&2
        DEGRADED=1
        DEGRADED_REASON="$ABORT_REASON"
    else
        echo "soak window done: $CYCLES_RAN cycle(s) in $((SOAK_WALL_S / 60)) min $((SOAK_WALL_S % 60)) s"
        # ONE greedy anchor at the end — only meaningful if the server lived.
        echo "== anchor (greedy, --anchor-only; gate = anchor_ok field) =="
        timeout "$BENCH_TIMEOUT_S" "${ANCHOR_CMD[@]}" --out "$ANCHOR_JSON" >/dev/null || echo "anchor rc non-zero (ignored; the JSON gate decides)"
        ANCHOR_TAIL_FILE="/tmp/soak-$CELL_ID-anchor-tail.txt"
        ANCHOR_OUT="$(python3 - "$ANCHOR_JSON" "$ANCHOR_TAIL_FILE" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    s = (d.get("streams") or [None])[0] or {}
    ok = "true" if s.get("anchor_ok") else "false"
    tail = (s.get("content") or "")[-200:]
except Exception as e:
    ok, tail = "false", f"(no anchor JSON: {e})"
print(ok)
with open(sys.argv[2], "w") as f:  # side file: an EMPTY tail must survive
    f.write(tail)                  # ($() strips trailing newlines)
PY
)"
        ANCHOR_OK="${ANCHOR_OUT%%$'\n'*}"
        ANCHOR_TAIL="$(cat "$ANCHOR_TAIL_FILE" 2>/dev/null || true)"
        echo "anchor_ok   : $ANCHOR_OK   content tail: '$ANCHOR_TAIL'"
        if [ "$ANCHOR_OK" != "true" ]; then
            DEGRADED=1
            [ -n "$DEGRADED_REASON" ] || DEGRADED_REASON="anchor check failed (greedy byte-identity)"
        fi
    fi
fi

# ------------------------------------------------ teardown + GPU-clean check
cleanup_server
wait_gtt_drain
trap - EXIT

GPU_CLEAN=true
GT_EXIT_B="$(mem_used_bytes gtt)"
if [ -n "$GT_EXIT_B" ] && [ "$GT_EXIT_B" -ge $((4 * 1024 * 1024 * 1024)) ]; then
    GPU_CLEAN=false
    echo "WARN: GTT still above 4 GiB at exit ($(mib "$GT_EXIT_B") MiB)" >&2
fi
if pgrep -f "llama-server" >/dev/null 2>&1; then
    GPU_CLEAN=false
    echo "WARN: a llama-server process is still alive at exit" >&2
fi
if [ "$GPU_CLEAN" != "true" ]; then
    DEGRADED=1
    [ -n "$DEGRADED_REASON" ] || DEGRADED_REASON="GPU not clean at exit (GTT residual or live llama-server)"
fi

# ------------------------------------------------------- receipt + summary
TOTALS_JSON="$(STARTED_UTC="$STARTED_UTC" CELL_ID="$CELL_ID" BASE_URL="$BASE_URL" \
CTX="$CTX" CONC="$CONC" BACKEND="$BACKEND" SPEC_DEPTH="$SPEC_DEPTH" \
MTP_PART="$MTP_PART" UNIFIED="$UNIFIED" WITH_MTP="$WITH_MTP" EXTRA_ARGS="$EXTRA_ARGS" \
KV_MODE="$KV_MODE" SLOT_INFO_JSON="$SLOT_INFO_JSON" LOAD_JSON="$LOAD_JSON" \
MODEL_JSON="$MODEL_JSON" BOOT_OK="$BOOT_OK" BOOT_WALL="$BOOT_WALL" \
ANCHOR_OK="$ANCHOR_OK" ANCHOR_TAIL="$ANCHOR_TAIL" DEGRADED="$DEGRADED" \
DEGRADED_REASON="$DEGRADED_REASON" CYCLES_FILE="$CYCLES_FILE" CYCLES_RAN="$CYCLES_RAN" \
SOAK_MINUTES="$SOAK_MINUTES" SOAK_WALL_S="${SOAK_WALL_S:-0}" ABORTED="$ABORTED" \
ABORT_REASON="$ABORT_REASON" GPU_CLEAN="$GPU_CLEAN" SCRIPT_GIT_REV="$SCRIPT_GIT_REV" \
WORKTREE_DIRTY="$WORKTREE_DIRTY" LLAMA_BIN="$LLAMA_BIN" EXTRA_FLAGS="${CELL_FLAGS[*]}" \
RECEIPT="$RECEIPT" python3 <<'PY'
import json, os, statistics, sys
env = os.environ
cycles = []
try:
    with open(env["CYCLES_FILE"]) as f:
        cycles = [json.loads(ln) for ln in f if ln.strip()]
except OSError:
    cycles = []
ok_rates = [c["tok_per_s"] for c in cycles if isinstance(c.get("tok_per_s"), (int, float))]
failed = [c for c in cycles if c.get("error") or c.get("failed_streams")]
half = len(ok_rates) // 2
fh = statistics.median(ok_rates[:half]) if half else None
sh = statistics.median(ok_rates[half:]) if len(ok_rates[half:]) else None
drift = (round((sh - fh) / fh * 100.0, 2)
         if fh and sh is not None else None)
totals = {
    "cycles": len(cycles),
    "ok_cycles": len(cycles) - len(failed),
    "failed_cycles": len(failed),
    "tok_per_s_min": round(min(ok_rates), 3) if ok_rates else None,
    "tok_per_s_median": round(statistics.median(ok_rates), 3) if ok_rates else None,
    "tok_per_s_max": round(max(ok_rates), 3) if ok_rates else None,
    "first_half_median": round(fh, 3) if fh is not None else None,
    "second_half_median": round(sh, 3) if sh is not None else None,
    "drift_pct": drift,
    "wall_minutes": round(int(env["SOAK_WALL_S"]) / 60.0, 1),
}
anomalies = []
for c in failed:
    anomalies.append(f"cycle {c['index']}: {c.get('error') or c.get('failed_streams')} failed stream(s)")
if env["ABORTED"] == "1":
    anomalies.append(env["ABORT_REASON"])
if env["GPU_CLEAN"] != "true":
    anomalies.append("GPU not clean at exit")
soak = {
    "id": "soak-" + env["CELL_ID"],
    "label": "soak-" + env["CELL_ID"],
    "kind": "stability-soak",
    "base_url": env["BASE_URL"],
    "started_utc": env["STARTED_UTC"],
    "script": "scripts/stability-soak.sh",
    "script_git_rev": env["SCRIPT_GIT_REV"],
    "worktree_dirty_at_run": env["WORKTREE_DIRTY"] == "1",
    "soak_minutes": int(env["SOAK_MINUTES"]),
    "server_flags": {
        "backend": env["BACKEND"],
        "ctx_size": int(env["CTX"]),
        "concurrency_np": int(env["CONC"]),
        "with_mtp": env["WITH_MTP"] == "1",
        "mtp_part": env["MTP_PART"],
        "spec_depth": int(env["SPEC_DEPTH"]) or None,
        "slots": "unified-rider" if env["UNIFIED"] else "default",
        "extra_args": env["EXTRA_ARGS"],
        "port": int(env["BASE_URL"].rsplit(":", 1)[1]),
        "kv_semantics_expected": env["KV_MODE"],
        "quickstart": "scripts/gguf-quickstart.sh",
        "llama_server_flags": env["EXTRA_FLAGS"].split(),
    },
    "model_pins": json.loads(env["MODEL_JSON"]) if env["MODEL_JSON"] != "null" else None,
    "slot_info": json.loads(env["SLOT_INFO_JSON"]),
    "load": json.loads(env["LOAD_JSON"]),
    "boot": {"ok": env["BOOT_OK"] == "1", "health_wall_s": int(env["BOOT_WALL"])},
    "cycles": cycles,
    "anchor": {"ok": env["ANCHOR_OK"] == "true", "content_tail": env["ANCHOR_TAIL"]},
    "totals": totals,
    "anomalies": anomalies,
    "exit_gpu_clean": env["GPU_CLEAN"] == "true",
    "degraded": env["DEGRADED"] == "1",
    "degraded_reason": env["DEGRADED_REASON"] or None,
}
with open(env["RECEIPT"], "w") as f:
    json.dump(soak, f, indent=2)
    f.write("\n")
print(json.dumps(totals))
PY
)"

echo "receipt     -> $RECEIPT"
SUMMARY_METRICS="$(TOTALS_JSON="$TOTALS_JSON" python3 <<'PY'
import json, os
t = json.loads(os.environ["TOTALS_JSON"])
fmt = lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "n/a"
drift = f"drift {t['drift_pct']:+.1f}% (first-half {fmt(t['first_half_median'])} -> second-half {fmt(t['second_half_median'])})" \
    if t["drift_pct"] is not None else "drift n/a (too few ok cycles)"
print(f"{t['cycles']} cycles in {t['wall_minutes']} min: "
      f"tok/s min {fmt(t['tok_per_s_min'])} / median {fmt(t['tok_per_s_median'])} / max {fmt(t['tok_per_s_max'])}, {drift}")
PY
)"

if [ "$DEGRADED" = "1" ]; then
    echo "SOAK DEGRADED: $CELL_ID — $DEGRADED_REASON | $SUMMARY_METRICS | anchor_ok=$ANCHOR_OK gpu_clean=$GPU_CLEAN -> $RECEIPT"
    exit 4
fi
echo "SOAK OK: $CELL_ID — $SUMMARY_METRICS | anchor_ok=$ANCHOR_OK gpu_clean=$GPU_CLEAN -> $RECEIPT"
