#!/usr/bin/env bash
# run-cell-gguf.sh — benchmark-matrix cell runner for the GGUF (llama.cpp) path.
#
# Usage:
#   scripts/run-cell-gguf.sh <cell-id> [--dry-run]
#
# Resolves <cell-id> against docs/results/matrix-714/matrix.json (refuses
# unknown ids), derives the server env, boots scripts/gguf-quickstart.sh
# (nohup, health-polled), snapshots load memory (rocm-smi VRAM/GTT, MiB
# binary), runs scripts/bench_client.py (throughput run + --anchor-only
# greedy anchor, gated on the JSON's anchor_ok field, never the exit code),
# records the ACTUAL slot semantics from the server log (n_slots /
# n_ctx_slot / kv_unified — METHODOLOGY.md §6 obligation), kills the server,
# waits for GPU memory to drain, writes the raw cell JSON to
# $CELLS_DIR/<id>.json (default docs/results/matrix-714/cells) and flips the
# matrix cell to `measured` (degraded runs keep `measured` status + a
# degraded note, per plan Task 3; the auto-verdict ladder in METHODOLOGY §3
# does the demoting). With a non-default CELLS_DIR (community run) the matrix
# flip is skipped — community submissions never edit the project matrix.
#
# Cell -> server env derivation (binding, METHODOLOGY.md §1/§6):
#   CTX_SIZE  = the id's ctx. The cell ctx is ALWAYS the server --ctx-size,
#               i.e. the TOTAL KV budget in both slot modes (llama.cpp
#               allocates --ctx-size tokens of KV whether unified or split).
#   WITH_MTP=1 for mtp cells (--spec-type draft-mtp from the same GGUF).
#   EXTRA_ARGS="-np N" ONLY for the concurrency-sweep cells with N>1 at the
#               131072 tier. An explicit -np N flips llama.cpp to SPLIT KV
#               semantics: per-slot window = ctx/N, kv_unified=false
#               (e.g. c4@131072 -> every stream gets a 32768 window).
#   Everything else (N=1 cells and the 32768/262144 ctx-tier cells at
#   N=1,4) keeps the quickstart DEFAULT boot — auto n_parallel=4,
#   kv_unified=true — exactly what a user of the validated defaults gets;
#               for those the cell ctx is the total over one shared pool.
#
# Environment knobs (rarely needed): PORT (8080), HEALTH_TIMEOUT_S (420),
# BENCH_TIMEOUT_S (1800), KEEP_SERVER (1 = leave the server up after the
# cell, for interactive follow-ups; the caller owns killing it), CELLS_DIR
# (default docs/results/matrix-714/cells; a non-default value means a
# community run and SKIPS the matrix flip — see docs/hardware-validation.md),
# MATRIX_FILE (default docs/results/matrix-714/matrix.json).
#
# CI note: --dry-run resolves and prints the plan without launching anything;
# the test suite only exercises --dry-run and the refusal paths.
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
QUICKSTART="scripts/gguf-quickstart.sh"
BENCH="scripts/bench_client.py"
PROMPTS="scripts/prompt-sets/default.json"

PORT="${PORT:-8080}"
BASE_URL="http://127.0.0.1:$PORT"
HEALTH_TIMEOUT_S="${HEALTH_TIMEOUT_S:-420}"
BENCH_TIMEOUT_S="${BENCH_TIMEOUT_S:-1800}"

# Cell id grammar (2026-08-18 backend-dimension migration, shared with
# gen-matrix.py and the verdicts schema — legacy unprefixed ids ARE hip):
ID_RE='^gguf-(hip|vulkan)-udq4kxl-auto-(base|mtp|mtp4)-c(1|4|8|16)-ctx(32768|131072|262144)(-unified)?$'

usage() {
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------- arguments
DRY_RUN=0
CELL_ID=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "ERROR: unknown option: $arg" >&2; usage >&2; exit 2 ;;
        *)
            if [ -n "$CELL_ID" ]; then
                echo "ERROR: exactly one cell id expected (got '$CELL_ID' and '$arg')" >&2
                exit 2
            fi
            CELL_ID="$arg" ;;
    esac
done
if [ -z "$CELL_ID" ]; then
    echo "ERROR: a cell id is required, e.g. scripts/run-cell-gguf.sh gguf-hip-udq4kxl-auto-base-c4-ctx131072 [--dry-run]" >&2
    exit 2
fi

# ------------------------------------------------------------ matrix resolve
# (before the grammar refusal so undeclared ids get the clearer "unknown
# cell" message; both refusals are binding either way)
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

# ------------------------------------------------------------- id grammar
if [[ "$CELL_ID" =~ $ID_RE ]]; then
    BACKEND="${BASH_REMATCH[1]}"        # hip | vulkan
    MTP_PART="${BASH_REMATCH[2]}"       # base | mtp | mtp4
    CONC="${BASH_REMATCH[3]}"           # 1 | 4 | 8 | 16
    CTX="${BASH_REMATCH[4]}"            # 32768 | 131072 | 262144
    UNIFIED="${BASH_REMATCH[5]:-}"      # -unified suffix (c4 rider) or empty
else
    echo "ERROR: '$CELL_ID' is not a valid gguf cell id." >&2
    echo "       grammar: gguf-(hip|vulkan)-udq4kxl-auto-{base,mtp,mtp4}-c{1,4,8,16}-ctx{32768,131072,262144}[-unified]" >&2
    echo "       (2026-08-18 migration: legacy unprefixed gguf ids are hip; use the explicit tag)" >&2
    exit 2
fi
if [[ "$CELL_ID" != gguf-* ]]; then
    # Unreachable after the regex, kept as a loud guard for copy-paste slips.
    echo "ERROR: '$CELL_ID' is not a gguf cell; this runner only handles the gguf path." >&2
    exit 2
fi

# Vulkan backend / mtp4 depth / unified-boot rider: the v0.1.2 runner
# plumbing (Vulkan build + backend binary selection, MTP depth, unified
# default boot) is NOT in this runner yet — refuse loudly rather than
# silently measure a vulkan/mtp4/unified cell with the hip base/mtp
# machinery (the receipt would lie about what ran).
if [ "$BACKEND" != "hip" ] || [ "$MTP_PART" = "mtp4" ] || [ -n "$UNIFIED" ]; then
    echo "ERROR: '$CELL_ID' needs the v0.1.2 Vulkan×MTP runner plumbing (backend binary selection / MTP depth / unified default boot) — not yet implemented in this runner; only hip {base,mtp} cells can run today." >&2
    exit 2
fi

# --------------------------------------------------------- server env derive
WITH_MTP=0
[ "$MTP_PART" = "mtp" ] && WITH_MTP=1

EXTRA_ARGS=""
KV_MODE="unified (default boot: auto n_parallel=4, shared ctx pool)"
if [ "$CTX" = "131072" ] && [ "$CONC" -gt 1 ]; then
    EXTRA_ARGS="-np $CONC"
    KV_MODE="split (explicit -np $CONC: per-slot window = 131072/$CONC = $((131072 / CONC)), kv_unified=false)"
fi

BENCH_CMD=(python3 "$BENCH" --base-url "$BASE_URL" --concurrency "$CONC"
           --prompts "$PROMPTS" --max-tokens 256 --label "$CELL_ID" --model default
           --no-thinking)
ANCHOR_CMD=(python3 "$BENCH" --base-url "$BASE_URL" --anchor-only
            --prompts "$PROMPTS" --max-tokens 256 --label "${CELL_ID}-anchor"
            --model default --no-thinking)

print_plan() {
    echo "cell          : $CELL_ID (matrix status: $MATRIX_STATUS)"
    echo "backend       : $BACKEND (llama.cpp build-714 binary class)"
    echo "server        : $QUICKSTART  (PORT=$PORT)"
    echo "server env    : CTX_SIZE=$CTX WITH_MTP=$WITH_MTP EXTRA_ARGS='${EXTRA_ARGS}'"
    echo "kv semantics  : $KV_MODE"
    echo "health poll   : curl $BASE_URL/health (timeout ${HEALTH_TIMEOUT_S}s)"
    echo "mem snapshot  : rocm-smi --showmeminfo vram + gtt after load (MiB, /1024)"
    echo "bench         : ${BENCH_CMD[*]}"
    echo "anchor        : ${ANCHOR_CMD[*]}  [gate: anchor_ok in the JSON, not exit code]"
    echo "slot record   : n_slots / n_ctx_slot / kv_unified grepped from the server log (METHODOLOGY 6)"
    if [ "$UPDATE_MATRIX" = "1" ]; then
        echo "outputs       : $CELLS_DIR/$CELL_ID.json + matrix status flip to measured"
    else
        echo "outputs       : $CELLS_DIR/$CELL_ID.json (matrix untouched: community submissions never edit the project matrix — docs/hardware-validation.md)"
    fi
}

if [ "$DRY_RUN" = "1" ]; then
    echo "DRY RUN — nothing launched, nothing written:"
    print_plan
    exit 0
fi

# ------------------------------------------------------------ real execution
[ -x "$QUICKSTART" ] || { echo "ERROR: $QUICKSTART not found/executable" >&2; exit 3; }
[ -f "$PROMPTS" ]    || { echo "ERROR: prompt set $PROMPTS missing" >&2; exit 3; }
command -v rocm-smi >/dev/null 2>&1 || { echo "ERROR: rocm-smi not found (host-only runner)" >&2; exit 3; }

# Refuse to stomp a live server: the quickstart's own port preflight would
# abort anyway, but a clear message here keeps the receipt honest.
if pgrep -f "llama-server.*--port $PORT" >/dev/null 2>&1; then
    echo "ERROR: a llama-server is already listening on port $PORT; kill it first (leave the GPU clean between cells)." >&2
    exit 3
fi

# Give a just-killed predecessor's TIME_WAIT sockets a moment to clear so
# back-to-back cells cannot trip a port preflight (SO_REUSEADDR probe: an
# active listener still fails, matching the check above).
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
LOG="/tmp/matrix-cell-${CELL_ID}.log"
BENCH_JSON="/tmp/matrix-cell-${CELL_ID}-bench.json"
ANCHOR_JSON="/tmp/matrix-cell-${CELL_ID}-anchor.json"
rm -f "$LOG" "$BENCH_JSON" "$ANCHOR_JSON"

mem_used_bytes() { # mem_used_bytes <vram|gtt> -> used bytes (empty on failure)
    # Line shape: "GPU[0]\t\t: <KIND> Total Used Memory (B): <bytes>" — the
    # value is the LAST field; kind must be uppercased (rocm-smi prints
    # "VRAM Total Used ...", the argument is lowercase).
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

wait_gtt_drain() { # block until GTT returns near the idle baseline (max 150s;
    # observed: releasing ~26-34 GiB of GTT can outlive the process by >90s)
    local _ g
    for _ in $(seq 1 75); do
        g="$(mem_used_bytes gtt)"
        [ -n "$g" ] && [ "$g" -lt $((4 * 1024 * 1024 * 1024)) ] && return 0
        sleep 2
    done
    echo "WARN: GTT did not drain below 4 GiB within 150s of server exit (continuing)" >&2
    return 0
}

write_cell_and_matrix() { # write_cell_and_matrix <assembled-json-path>
    CELL_DIR="$CELLS_DIR" python3 - "$CELL_ID" "$1" <<'PY'
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
    python3 - "$MATRIX_FILE" "$CELL_ID" "$1" <<'PY'
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
DEGRADED=0
DEGRADED_REASON=""

echo "== booting $QUICKSTART (ctx $CTX, mtp $WITH_MTP, extra '${EXTRA_ARGS:-none}') =="
STARTED_S=$SECONDS
PORT="$PORT" CTX_SIZE="$CTX" WITH_MTP="$WITH_MTP" EXTRA_ARGS="$EXTRA_ARGS" \
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
BENCH_RC=-1
ANCHOR_OK=false
ANCHOR_TAIL=""

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
    if [ "$SLOT_INFO_JSON" = "null" ]; then
        echo "WARN: no 'n_slots = ..., n_ctx_slot = ..., kv_unified' line found in $LOG" >&2
        DEGRADED=1; DEGRADED_REASON="slot semantics line not found in server log"
    else
        echo "slot info   : $SLOT_INFO_JSON"
    fi

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

    echo "== throughput bench (concurrency $CONC) =="
    BENCH_RC=0
    timeout "$BENCH_TIMEOUT_S" "${BENCH_CMD[@]}" --out "$BENCH_JSON" >/dev/null || BENCH_RC=$?
    if [ ! -s "$BENCH_JSON" ]; then
        echo "ERROR: bench client produced no JSON (rc=$BENCH_RC)" >&2
        DEGRADED=1
        [ -n "$DEGRADED_REASON" ] || DEGRADED_REASON="bench client produced no JSON (rc=$BENCH_RC)"
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

    echo "== anchor (greedy, --anchor-only; gate = anchor_ok field) =="
    timeout "$BENCH_TIMEOUT_S" "${ANCHOR_CMD[@]}" --out "$ANCHOR_JSON" >/dev/null || echo "anchor rc non-zero (ignored; the JSON gate decides)"
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

# ---------------------------------------------------- excerpt + cell JSON
LOG_EXCERPT_JSON="$(LOG="$LOG" python3 <<'PY'
import json, os, re
lines = []
try:
    raw = open(os.environ["LOG"], errors="replace").read().splitlines()
except OSError:
    raw = []
keep = re.compile(r"^(llama-server :|model        :|ctx-size     :|gpu layers   :|mmproj|speculative  :|extra args   :|Serving on)")
interesting = re.compile(r"(n_slots = |load:|main: model loaded|W |E |error|Error|speculative|KV|offloaded)")
for ln in raw:
    if keep.match(ln):
        lines.append(ln)
for ln in raw:
    if interesting.search(ln) and ln not in lines:
        lines.append(ln)
seen, uniq = set(), []
for ln in lines:
    if ln not in seen:
        seen.add(ln); uniq.append(ln)
print(json.dumps(uniq[:20]))
PY
)"

CELL_TMP="/tmp/matrix-cell-${CELL_ID}.assembled.json"
STARTED_UTC="$STARTED_UTC" CELL_ID="$CELL_ID" BASE_URL="$BASE_URL" CTX="$CTX" \
CONC="$CONC" WITH_MTP="$WITH_MTP" EXTRA_ARGS="${EXTRA_ARGS}" KV_MODE="$KV_MODE" \
SLOT_INFO_JSON="$SLOT_INFO_JSON" LOAD_JSON="$LOAD_JSON" BOOT_OK="$BOOT_OK" \
BOOT_WALL="$BOOT_WALL" BENCH_JSON="$BENCH_JSON" ANCHOR_OK="$ANCHOR_OK" \
ANCHOR_TAIL="$ANCHOR_TAIL" LOG_EXCERPT_JSON="$LOG_EXCERPT_JSON" DEGRADED="$DEGRADED" \
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
        "ctx_size": int(env["CTX"]),
        "concurrency_np": int(env["CONC"]),
        "with_mtp": env["WITH_MTP"] == "1",
        "extra_args": env["EXTRA_ARGS"],
        "port": int(env["BASE_URL"].rsplit(":", 1)[1]),
        "kv_semantics_expected": env["KV_MODE"],
        "quickstart": "scripts/gguf-quickstart.sh",
        "llama_server_flags": ["--ctx-size", env["CTX"], "-ngl", "99", "--jinja"]
                              + (["--spec-type", "draft-mtp"] if env["WITH_MTP"] == "1" else [])
                              + (env["EXTRA_ARGS"].split() if env["EXTRA_ARGS"] else []),
    },
    "slot_info": json.loads(env["SLOT_INFO_JSON"]),
    "load": json.loads(env["LOAD_JSON"]),
    "boot": {"ok": env["BOOT_OK"] == "1", "health_wall_s": int(env["BOOT_WALL"])},
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

cleanup_server
wait_gtt_drain
trap - EXIT

write_cell_and_matrix "$CELL_TMP"

if [ "$DEGRADED" = "1" ]; then
    echo "CELL DEGRADED: $CELL_ID — $DEGRADED_REASON (degraded note recorded in the cell JSON)"
    exit 4
fi
echo "CELL OK: $CELL_ID"
