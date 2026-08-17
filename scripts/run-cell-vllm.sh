#!/usr/bin/env bash
# run-cell-vllm.sh — benchmark-matrix cell runner for the vLLM path.
#
# Usage:
#   scripts/run-cell-vllm.sh <cell-id> [cell-id...] [--dry-run]
#
# Same lifecycle pattern as run-cell-gguf.sh (Task 3): resolve every cell id
# against docs/results/matrix-714/matrix.json (refuse unknown ids), derive
# the server config, boot scripts/03-serve-vllm.sh [--mtp] (nohup, port
# 8000, health-polled — vLLM boots ~5 min for the 51.7 GiB bf16 weights),
# snapshot load memory (rocm-smi VRAM/GTT, MiB binary), run
# scripts/bench_client.py per cell (throughput run + --anchor-only greedy
# anchor, gated on the JSON's anchor_ok field, never the exit code), kill
# the server, wait for GTT drain, write one raw cell JSON per id to
# $CELLS_DIR/<id>.json (default docs/results/matrix-714/cells) and flip each
# matrix cell to `measured` (degraded runs keep `measured` + a degraded
# note; the auto-verdict ladder in METHODOLOGY.md §3 does the demoting).
# With a non-default CELLS_DIR (community run) the matrix flip is skipped —
# community submissions never edit the project matrix.
#
# BATCH MODE (Task 4): vLLM has no -np analog — concurrency is CLIENT-side
# (bench_client opens N parallel SSE streams; METHODOLOGY.md §7). All cells
# of one invocation must share the same server config ({base,mtp} × one ctx
# tier); the runner boots ONE server and runs every listed cell against it
# sequentially (bench + anchor per cell), i.e. {c1,c4,c8,c16}@262144 is two
# boots total for the whole matrix (one base, one mtp) instead of eight.
# The shared boot is recorded per cell (boot.shared_boot).
#
# Confs are NEVER edited: flags come from configs/serve-args.conf /
# serve-args-mtp.conf verbatim; the only override is the documented
# MAX_MODEL_LEN env pass-through in 03-serve-vllm.sh, applied solely when a
# cell's ctx tier differs from the conf's --max-model-len (262144) — a CI
# test asserts the confs are byte-stable across the branch.
#
# Instrument mode (METHODOLOGY.md §2 erratum): cells send
# chat_template_kwargs {"enable_thinking": false} (bench_client
# --no-thinking) so the measured stream is the visible-answer stream both
# paths share; the confs' --reasoning-parser qwen3 would otherwise split
# <think> into message.reasoning and defer content past the 256-token cap.
# The mode actually used is recorded per cell in cell JSON "instrument_mode".
#
# Environment knobs (rarely needed): PORT (8000), HEALTH_TIMEOUT_S (900 —
# vLLM boot is ~5 min), BENCH_TIMEOUT_S (2400 per cell), CELLS_DIR (default
# docs/results/matrix-714/cells; a non-default value means a community run
# and SKIPS the matrix flip — see docs/hardware-validation.md), MATRIX_FILE
# (default docs/results/matrix-714/matrix.json).
#
# CI note: --dry-run resolves and prints the plan without launching
# anything; the test suite only exercises --dry-run and the refusal paths.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MATRIX_FILE="${MATRIX_FILE:-docs/results/matrix-714/matrix.json}"
CELLS_DIR="${CELLS_DIR:-docs/results/matrix-714/cells}"
# Community cell namespace (docs/hardware-validation.md, "Producing your
# cells"): point CELLS_DIR at your own cells dir to keep the run out of the
# project namespace. Any CELLS_DIR outside the project default skips the
# matrix flip entirely — community submissions never edit the project
# matrix (evidence enters only via configs/community/platforms.json).
UPDATE_MATRIX=1
[ "$CELLS_DIR" = "docs/results/matrix-714/cells" ] || UPDATE_MATRIX=0
SERVE="scripts/03-serve-vllm.sh"
BENCH="scripts/bench_client.py"
PROMPTS="scripts/prompt-sets/default.json"

PORT="${PORT:-8000}"
BASE_URL="http://127.0.0.1:$PORT"
HEALTH_TIMEOUT_S="${HEALTH_TIMEOUT_S:-900}"
BENCH_TIMEOUT_S="${BENCH_TIMEOUT_S:-2400}"

ID_RE='^vllm-bf16-auto-(base|mtp)-c(1|4|8|16)-ctx(131072|262144)$'

usage() {
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------- arguments
DRY_RUN=0
CELL_IDS=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "ERROR: unknown option: $arg" >&2; usage >&2; exit 2 ;;
        *) CELL_IDS+=("$arg") ;;
    esac
done
if [ "${#CELL_IDS[@]}" -eq 0 ]; then
    echo "ERROR: at least one cell id is required, e.g. scripts/run-cell-vllm.sh vllm-bf16-auto-base-c1-ctx262144 [more-ids...] [--dry-run]" >&2
    exit 2
fi
if [ "${#CELL_IDS[@]}" -gt 1 ]; then
    # Reject duplicates (a duplicate would overwrite its own cell JSON).
    dup_check="$(printf '%s\n' "${CELL_IDS[@]}" | sort | uniq -d)"
    [ -z "$dup_check" ] || { echo "ERROR: duplicate cell id(s) in batch: $dup_check" >&2; exit 2; }
fi

# ------------------------------------------------------------ matrix resolve
# (before the grammar refusal so undeclared ids get the clearer "unknown
# cell" message; both refusals are binding either way — the matrix is the
# source of truth)
for CELL_ID in "${CELL_IDS[@]}"; do
    MATRIX_STATUS="$(python3 - "$MATRIX_FILE" "$CELL_ID" <<'PY' || true
import json, sys
try:
    cells = json.load(open(sys.argv[1]))["cells"]
except (OSError, KeyError, ValueError) as e:
    print(f"ERROR: cannot read matrix manifest {sys.argv[1]}: {e}")
    raise SystemExit(3)
for c in cells:
    if c["id"] == sys.argv[2]:
        print(c.get("status", ""))
        raise SystemExit(0)
print("UNKNOWN")
PY
)"
    case "$MATRIX_STATUS" in
        UNKNOWN)
            echo "ERROR: cell id '$CELL_ID' is not declared in $MATRIX_FILE (unknown id; the matrix is the source of truth — see scripts/gen-matrix.py)." >&2
            exit 3 ;;
        ERROR*) echo "$MATRIX_STATUS" >&2; exit 3 ;;
    esac
    [ "$MATRIX_STATUS" != "dropped" ] || {
        echo "ERROR: cell id '$CELL_ID' is declared dropped in the matrix; dropped tiers are never run." >&2
        exit 3; }
done

# ------------------------------------------------------------- id grammar
MTP_PART=""; CTX=""; CONCS=()
for CELL_ID in "${CELL_IDS[@]}"; do
    if [[ "$CELL_ID" =~ $ID_RE ]]; then
        m="${BASH_REMATCH[1]}"; c="${BASH_REMATCH[2]}"; k="${BASH_REMATCH[3]}"
    else
        echo "ERROR: '$CELL_ID' is not a valid vllm cell id." >&2
        echo "       grammar: vllm-bf16-auto-{base,mtp}-c{1,4,8,16}-ctx{131072,262144} (32768 is a dropped tier for this path)" >&2
        exit 2
    fi
    if [[ "$CELL_ID" != vllm-* ]]; then
        # Unreachable after the regex, kept as a loud guard for copy-paste slips.
        echo "ERROR: '$CELL_ID' is not a vllm cell; this runner only handles the vllm path." >&2
        exit 2
    fi
    if [ -z "$MTP_PART" ]; then MTP_PART="$m"; CTX="$k"; fi
    # Batch rule: one boot per invocation — every cell must share the server
    # config ({base,mtp} and the ctx tier are boot-level; concurrency is not).
    if [ "$m" != "$MTP_PART" ] || [ "$k" != "$CTX" ]; then
        echo "ERROR: all cells in one invocation must share the same server config (one boot):" >&2
        echo "       '$CELL_ID' (${m}-ctx${k}) vs the first cell (${MTP_PART}-ctx${CTX}). Split them into two invocations." >&2
        exit 2
    fi
    CONCS+=("$c")
done

# --------------------------------------------------------- server conf derive
MTP_FLAG=()
CONF_NAME="serve-args.conf"
if [ "$MTP_PART" = "mtp" ]; then MTP_FLAG=(--mtp); CONF_NAME="serve-args-mtp.conf"; fi
CONF="configs/$CONF_NAME"

# Served model name + conf max-model-len come from the conf (the source of
# truth). The SERVED fallback below only fires if the conf parse yields
# nothing (malformed conf): it mirrors the validated conf value so the bench
# can name the error, never to override what the conf says.
SERVED="$(awk '$1=="--served-model-name"{print $2; exit}' "$CONF")"
CONF_MAXLEN="$(awk '$1=="--max-model-len"{print $2; exit}' "$CONF")"
SERVED="${SERVED:-qwen3.8-27b}"
[ -n "$CONF_MAXLEN" ] || { echo "ERROR: $CONF has no --max-model-len line" >&2; exit 3; }

MAX_MODEL_LEN_OVERRIDE=""
if [ "$CTX" != "$CONF_MAXLEN" ]; then
    MAX_MODEL_LEN_OVERRIDE="$CTX"   # documented env pass-through; conf untouched
fi

print_plan() {
    echo "cells        : ${CELL_IDS[*]}"
    echo "matrix       : statuses resolved (see above); one boot serves all cells in this batch"
    echo "server       : $SERVE ${MTP_FLAG[*]} (conf: $CONF, PORT=$PORT)"
    echo "conf flags   : verbatim from $CONF (confs are never edited; CI asserts byte-stability)"
    [ -n "$MAX_MODEL_LEN_OVERRIDE" ] && \
        echo "ctx override : MAX_MODEL_LEN=$MAX_MODEL_LEN_OVERRIDE (cell ctx != conf --max-model-len $CONF_MAXLEN)"
    echo "served model : $SERVED  (bench --model)"
    echo "concurrency  : client-side parallel streams (vLLM has no -np analog; engine max_num_seqs stays the pin default — METHODOLOGY 7)"
    echo "health poll  : curl $BASE_URL/health (timeout ${HEALTH_TIMEOUT_S}s; vLLM boot ~5 min)"
    echo "mem snapshot : rocm-smi --showmeminfo vram + gtt after load (MiB, /1024; shared across the batch)"
    echo "engine args  : non-default args + V1 engine init lines captured verbatim from the boot log (METHODOLOGY 7)"
    echo "instrument   : --no-thinking (chat_template_kwargs enable_thinking=false; recorded per cell)"
    for i in "${!CELL_IDS[@]}"; do
        echo "cell[$i]      : python3 $BENCH --base-url $BASE_URL --concurrency ${CONCS[$i]} --prompts $PROMPTS --max-tokens 256 --label ${CELL_IDS[$i]} --model $SERVED --no-thinking"
        echo "             + python3 $BENCH --anchor-only --prompts $PROMPTS --model $SERVED --no-thinking  [gate: anchor_ok in the JSON]"
    done
    if [ "$UPDATE_MATRIX" = "1" ]; then
        echo "outputs      : $CELLS_DIR/{${CELL_IDS[*]}}.json + matrix status flips to measured"
    else
        echo "outputs      : $CELLS_DIR/{${CELL_IDS[*]}}.json (matrix untouched: community submissions never edit the project matrix — docs/hardware-validation.md)"
    fi
}

if [ "$DRY_RUN" = "1" ]; then
    echo "DRY RUN — nothing launched, nothing written:"
    print_plan
    exit 0
fi

# ------------------------------------------------------------ real execution
[ -x "$SERVE" ]     || { echo "ERROR: $SERVE not found/executable" >&2; exit 3; }
[ -f "$BENCH" ]     || { echo "ERROR: bench client $BENCH missing" >&2; exit 3; }
[ -f "$PROMPTS" ]   || { echo "ERROR: prompt set $PROMPTS missing" >&2; exit 3; }
command -v rocm-smi >/dev/null 2>&1 || { echo "ERROR: rocm-smi not found (host-only runner)" >&2; exit 3; }

# Refuse to stomp a live server.
if pgrep -f "vllm serve" >/dev/null 2>&1; then
    echo "ERROR: a vllm server is already running; kill it first (leave the GPU clean between cells)." >&2
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

mkdir -p "$CELLS_DIR"
LOG="/tmp/matrix-cell-vllm-${MTP_PART}-ctx${CTX}.log"
rm -f "$LOG"

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
    # setsid boot: SERVER_PID is the process-group id; signal the whole group
    # so the uv->vllm->EngineCore tree goes down together.
    kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill "$SERVER_PID" 2>/dev/null || true
    local _
    for _ in $(seq 1 90); do
        kill -0 "$SERVER_PID" 2>/dev/null && { sleep 1; continue; }
        break
    done
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        kill -KILL -- "-$SERVER_PID" 2>/dev/null || true
        sleep 2
    fi
    # Sweep orphaned engine cores: VLLM_WORKER_MULTIPROC_METHOD=spawn children
    # can outlive the API server (observed 2026-08-17: an EngineCore held
    # ~75 GiB of GTT after the group leader was gone — the early-exit above
    # would otherwise skip this sweep). Their proctitle is exact, so the
    # pattern cannot match anything else.
    pkill -KILL -f "VLLM::EngineCore" 2>/dev/null || true
}
trap cleanup_server EXIT

wait_gtt_drain() { # vLLM holds ~74 GiB of the 80 GiB GTT pool; block until it
    # returns near the idle baseline (max 300s — release is prompt once the
    # engine processes are gone, but give the driver slack).
    local _ g
    for _ in $(seq 1 150); do
        g="$(mem_used_bytes gtt)"
        [ -n "$g" ] && [ "$g" -lt $((4 * 1024 * 1024 * 1024)) ] && return 0
        sleep 2
    done
    echo "WARN: GTT did not drain below 4 GiB within 300s of server exit (continuing)" >&2
    return 0
}

write_cell_and_matrix() { # write_cell_and_matrix <assembled-json-path> <cell-id>
    CELL_DIR="$CELLS_DIR" python3 - "$2" "$1" <<'PY'
import json, os, shutil, sys
cell_id, assembled = sys.argv[1:3]
dest = os.path.join(os.environ["CELL_DIR"], cell_id + ".json")
shutil.copyfile(assembled, dest)
print(f"cell json   -> {dest}")
PY
    if [ "$UPDATE_MATRIX" != "1" ]; then
        echo "matrix      -> not touched (CELLS_DIR '$CELLS_DIR' is outside the project default; community submissions never edit the project matrix — docs/hardware-validation.md)"
        return 0
    fi
    python3 - "$MATRIX_FILE" "$2" "$1" <<'PY'
import json, sys
matrix_path, cell_id, assembled = sys.argv[1:4]
cell = json.load(open(assembled))
m = json.load(open(matrix_path))
for c in m["cells"]:
    if c["id"] == cell_id:
        c["status"] = "measured"
        c.pop("reason", None)
        if cell.get("degraded"):
            c["degraded"] = True
            c["note"] = "measured (degraded): " + cell["degraded_reason"]
        else:
            # clear any stale degraded note from an earlier failed attempt
            c.pop("degraded", None)
            c.pop("note", None)
        break
with open(matrix_path, "w") as f:
    json.dump(m, f, indent=2)
    f.write("\n")
print(f"matrix      -> {cell_id}: measured" + (" (degraded)" if cell.get("degraded") else ""))
PY
}

STARTED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "== booting $SERVE ${MTP_FLAG[*]} (ctx $CTX from $CONF) =="
STARTED_S=$SECONDS
[ -z "$MAX_MODEL_LEN_OVERRIDE" ] || export MAX_MODEL_LEN="$MAX_MODEL_LEN_OVERRIDE"
setsid nohup bash "$SERVE" ${MTP_FLAG[@]+"${MTP_FLAG[@]}"} >"$LOG" 2>&1 &
SERVER_PID=$!
unset MAX_MODEL_LEN

BOOT_OK=0
while [ $SECONDS -lt $((STARTED_S + HEALTH_TIMEOUT_S)) ]; do
    if curl -sf "$BASE_URL/health" >/dev/null 2>&1; then BOOT_OK=1; break; fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "ERROR: server process died during boot (see $LOG)" >&2
        break
    fi
    sleep 3
done
BOOT_WALL=$((SECONDS - STARTED_S))

ENGINE_JSON='null'
LOAD_JSON='{"vram_mib": null, "gtt_mib": null}'

if [ "$BOOT_OK" != "1" ]; then
    echo "ERROR: server not healthy within ${HEALTH_TIMEOUT_S}s (see $LOG)" >&2
else
    echo "health OK after ${BOOT_WALL}s; settling 5s before the memory snapshot"
    sleep 5

    # Engine-args capture, verbatim from the boot log (METHODOLOGY 7).
    ENGINE_JSON="$(LOG="$LOG" python3 <<'PY'
import json, os, re
try:
    raw = open(os.environ["LOG"], errors="replace").read().splitlines()
except OSError:
    raw = []
def first(pred, limit=None):
    for ln in raw:
        if pred(ln):
            return ln[:limit] if limit else ln
    return None
non_default = first(lambda l: "non-default args:" in l)
engine_init = first(lambda l: "Initializing a V1 LLM engine" in l, 1200)
kv = [l.strip() for l in raw if re.search(
        r"Available KV cache memory|GPU KV cache size|Model loading took|"
        r"init engine \(profile", l)][:4]
print(json.dumps({
    "non_default_args": non_default,
    "engine_init_excerpt": engine_init,
    "kv_and_load_lines": kv,
    "max_num_seqs_note": ("absent from the non-default args line -> the pin default "
                          "applied (max_num_seqs=1024, max_num_batched_tokens=8192; "
                          "vllm/engine/arg_utils.py:2592-2601, METHODOLOGY 7)"),
}))
PY
)"
    echo "engine args : $ENGINE_JSON" | head -c 600; echo

    VRAM_B="$(mem_used_bytes vram)"; GTT_B="$(mem_used_bytes gtt)"
    LOAD_JSON="$(VRAM_B="${VRAM_B:-}" GTT_B="${GTT_B:-}" python3 <<'PY'
import json, os
v = os.environ.get("VRAM_B", ""); g = os.environ.get("GTT_B", "")
def mib(s):
    return int(s) // 1048576 if s else None
print(json.dumps({"vram_mib": mib(v), "gtt_mib": mib(g)}))
PY
)"
    echo "load memory : $LOAD_JSON (shared by every cell in this batch)"
fi

LOG_EXCERPT_JSON="$(LOG="$LOG" python3 <<'PY'
import json, os, re
try:
    raw = open(os.environ["LOG"], errors="replace").read().splitlines()
except OSError:
    raw = []
interesting = re.compile(r"(Serving .* on http|non-default args:|Initializing a V1 LLM engine|"
                         r"Resolved architecture|Loading drafter|Available KV cache|GPU KV cache size|"
                         r"Model loading took|init engine \(profile|WARNING|Error|error|OutOfMemory|Traceback)", re.I)
seen, uniq = set(), []
for ln in raw:
    if interesting.search(ln):
        t = ln.strip()[:300]
        if t not in seen:
            seen.add(t); uniq.append(t)
print(json.dumps(uniq[:20]))
PY
)"

# ------------------------------------------------- per-cell bench + anchor
ANY_DEGRADED=0
CELL_IDX=0
BATCH_IDS="${CELL_IDS[*]}"
for CELL_ID in "${CELL_IDS[@]}"; do
    CONC="${CONCS[$CELL_IDX]}"
    CELL_IDX=$((CELL_IDX + 1))
    BENCH_JSON="/tmp/matrix-cell-${CELL_ID}-bench.json"
    ANCHOR_JSON="/tmp/matrix-cell-${CELL_ID}-anchor.json"
    rm -f "$BENCH_JSON" "$ANCHOR_JSON"

    DEGRADED=0
    DEGRADED_REASON=""
    if [ "$BOOT_OK" != "1" ]; then
        DEGRADED=1; DEGRADED_REASON="server failed to boot (see log excerpt)"
    else
        echo "== [$CELL_ID] throughput bench (client concurrency $CONC) =="
        BENCH_RC=0
        timeout "$BENCH_TIMEOUT_S" python3 "$BENCH" --base-url "$BASE_URL" \
            --concurrency "$CONC" --prompts "$PROMPTS" --max-tokens 256 \
            --label "$CELL_ID" --model "$SERVED" --no-thinking \
            --out "$BENCH_JSON" >/dev/null || BENCH_RC=$?
        if [ ! -s "$BENCH_JSON" ]; then
            echo "ERROR: bench client produced no JSON (rc=$BENCH_RC)" >&2
            DEGRADED=1; DEGRADED_REASON="bench client produced no JSON (rc=$BENCH_RC)"
        else
            echo "bench rc    : $BENCH_RC (0 = all streams ok; gate is the JSON below)"
            python3 - "$BENCH_JSON" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
agg = d.get("aggregate", {})
print(f"aggregate   : tok/s={agg.get('tok_per_s')}  wall_s={agg.get('wall_s')}  "
      f"ok={agg.get('ok_streams')}/{d.get('concurrency')}")
for i, s in enumerate(d.get("streams", [])):
    if s is None:
        print(f"stream {i}  : MISSING"); continue
    tpot = s.get("tpot_ms")
    tps = f"{1000.0/tpot:.1f}" if tpot else "n/a"
    print(f"stream {i:<2} : ttft={s.get('ttft_ms')}ms tpot={tpot}ms ({tps} tok/s) "
          f"tokens={s.get('completion_tokens')} ok={s.get('ok')} err={s.get('error') or ''}")
PY
            FAILED="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["aggregate"]["failed_streams"])' "$BENCH_JSON" 2>/dev/null || echo 1)"
            if [ "$FAILED" != "0" ]; then
                DEGRADED=1
                [ -n "$DEGRADED_REASON" ] || DEGRADED_REASON="bench: $FAILED failed stream(s)"
            fi
        fi

        echo "== [$CELL_ID] anchor (greedy, --anchor-only; gate = anchor_ok field) =="
        timeout "$BENCH_TIMEOUT_S" python3 "$BENCH" --anchor-only \
            --base-url "$BASE_URL" --prompts "$PROMPTS" --max-tokens 256 \
            --label "${CELL_ID}-anchor" --model "$SERVED" --no-thinking \
            --out "$ANCHOR_JSON" >/dev/null || echo "anchor rc non-zero (ignored; the JSON gate decides)"
        ANCHOR_TAIL_FILE="/tmp/matrix-cell-${CELL_ID}-anchor-tail.txt"
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

    CELL_TMP="/tmp/matrix-cell-${CELL_ID}.assembled.json"
    STARTED_UTC="$STARTED_UTC" CELL_ID="$CELL_ID" BASE_URL="$BASE_URL" CTX="$CTX" \
    CONC="$CONC" MTP_PART="$MTP_PART" CONF="$CONF" SERVED="$SERVED" \
    CONF_MAXLEN="$CONF_MAXLEN" MAX_MODEL_LEN_OVERRIDE="$MAX_MODEL_LEN_OVERRIDE" \
    PORT="$PORT" ENGINE_JSON="$ENGINE_JSON" LOAD_JSON="$LOAD_JSON" BOOT_OK="$BOOT_OK" \
    BOOT_WALL="$BOOT_WALL" BATCH_IDS="$BATCH_IDS" CELL_IDX="$CELL_IDX" \
    BENCH_JSON="$BENCH_JSON" ANCHOR_OK="${ANCHOR_OK:-false}" ANCHOR_TAIL="${ANCHOR_TAIL:-}" \
    LOG_EXCERPT_JSON="$LOG_EXCERPT_JSON" DEGRADED="$DEGRADED" \
    DEGRADED_REASON="$DEGRADED_REASON" python3 - "$CELL_TMP" <<'PY'
import json, os, sys
env = os.environ
def load_maybe(p):
    try:
        return json.load(open(p))
    except Exception:
        return {"error": f"missing/unreadable: {p}"}
cell = {
    "id": env["CELL_ID"],
    "label": env["CELL_ID"],
    "base_url": env["BASE_URL"],
    "started_utc": env["STARTED_UTC"],
    "server_flags": {
        "conf": env["CONF"],
        "mtp": env["MTP_PART"] == "mtp",
        "serve_script": "scripts/03-serve-vllm.sh",
        "served_model_name": env["SERVED"],
        "max_model_len_conf": int(env["CONF_MAXLEN"]),
        "max_model_len_override": int(env["MAX_MODEL_LEN_OVERRIDE"]) if env["MAX_MODEL_LEN_OVERRIDE"] else None,
        "port": int(env["PORT"]),
        "concurrency": int(env["CONC"]),  # client-side parallel streams
        "conf_flags_verbatim": [ln.strip() for ln in open(env["CONF"])
                                if ln.strip() and not ln.strip().startswith("#")],
    },
    "engine": json.loads(env["ENGINE_JSON"]),
    "instrument_mode": {
        "no_thinking": True,
        "mechanism": "chat_template_kwargs {'enable_thinking': false} (bench_client --no-thinking)",
        "reasoning_parser": "qwen3 (from the conf; splits <think> into message.reasoning — with thinking disabled no reasoning deltas are produced)",
        "comparability": "same visible-answer instrument mode as the gguf cells (METHODOLOGY 2 erratum)",
    },
    "load": json.loads(env["LOAD_JSON"]),
    "boot": {
        "ok": env["BOOT_OK"] == "1",
        "health_wall_s": int(env["BOOT_WALL"]),
        "shared_boot": {"cells": env["BATCH_IDS"].split(),
                        "this_cell_index": int(env["CELL_IDX"])},
    },
    "client": load_maybe(env["BENCH_JSON"]) if env["BOOT_OK"] == "1" else None,
    "anchor": {"ok": env["ANCHOR_OK"] == "true", "content_tail": env["ANCHOR_TAIL"]},
    "log_excerpt": json.loads(env["LOG_EXCERPT_JSON"]),
    "degraded": env["DEGRADED"] == "1",
    "degraded_reason": env["DEGRADED_REASON"] or None,
}
with open(sys.argv[1], "w") as f:
    json.dump(cell, f, indent=2)
    f.write("\n")
PY

    write_cell_and_matrix "$CELL_TMP" "$CELL_ID"
    if [ "$DEGRADED" = "1" ]; then
        ANY_DEGRADED=1
        echo "CELL DEGRADED: $CELL_ID — $DEGRADED_REASON (degraded note recorded in the cell JSON)"
    else
        echo "CELL OK: $CELL_ID"
    fi
done

cleanup_server
wait_gtt_drain
trap - EXIT

if [ "$ANY_DEGRADED" = "1" ]; then
    echo "BATCH finished WITH DEGRADED CELLS: ${CELL_IDS[*]}"
    exit 4
fi
echo "BATCH OK: ${CELL_IDS[*]} (server killed; GTT drained)"
