#!/usr/bin/env bash
# Fetch a Qwen3.8-27B artifact set from ModelScope into models/.
# Set-aware: SET selects the manifest set — "bf16" (default; the 18-shard
# safetensors checkpoint, models/Qwen3.8-27B) or "gguf" (unsloth
# UD-Q4_K_XL + mmproj-F16 + config sidecar, models/Qwen3.8-27B-GGUF).
# Manifest-driven: every file is verified against configs/artifact-manifest.json
# (size + SHA256) after download; verified files are skipped on re-run.
# Resumable: partial downloads continue with -C -.
#   SET=bf16|gguf          artifact set to fetch (default bf16)
#   MODEL_DEST=/path      override destination
#   NCONNS=N              parallel shard downloads (default 6)
#   MS_ENDPOINT=https://modelscope.cn   override mirror
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 required" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "ERROR: curl required" >&2; exit 1; }

SET="${SET:-bf16}"
MANIFEST="configs/artifact-manifest.json"

if ! python3 -c 'import json,sys;sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1]))["sets"] else 1)' "$MANIFEST" "$SET"; then
  echo "ERROR: SET=$SET not found in $MANIFEST (available sets: bf16, gguf)" >&2
  exit 1
fi

read_set_field() {
  python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["sets"][sys.argv[2]][sys.argv[3]])' \
    "$MANIFEST" "$SET" "$1"
}

REPO="$(read_set_field repository)"
REV="$(read_set_field revision)"
DEST="${MODEL_DEST:-$(read_set_field dest)}"
MS_ENDPOINT="${MS_ENDPOINT:-https://modelscope.cn}"
NCONNS="${NCONNS:-6}"

echo "Fetching set '$SET': $REPO @ $REV -> $DEST"
mkdir -p "$DEST"

python3 - "$MANIFEST" "$DEST" "$MS_ENDPOINT" "$REPO" "$REV" "$NCONNS" "$SET" <<'PY'
import hashlib, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

manifest, dest, endpoint, repo, rev, nconns, set_name = sys.argv[1:8]
files = json.load(open(manifest))["sets"][set_name]["files"]
base = f"{endpoint}/api/v1/models/{repo}/repo"
os.makedirs(dest, exist_ok=True)

def verified(path, size, sha):
    f = os.path.join(dest, path)
    if not os.path.isfile(f) or os.path.getsize(f) != size:
        return False
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest() == sha

def fetch(item):
    path, size, sha = item["path"], item["size_bytes"], item["sha256"]
    if verified(path, size, sha):
        print(f"  skip (already verified): {path}", flush=True)
        return path, True
    url = f"{base}?FilePath={path}&Revision={rev}"
    out = os.path.join(dest, path)
    for attempt in range(1, 6):
        # A complete-but-unverified file (wrong revision or corrupt bytes)
        # can never be resumed into correctness — restart it from scratch.
        try:
            if os.path.isfile(out) and os.path.getsize(out) >= size:
                os.remove(out)
        except OSError:
            pass
        r = subprocess.run(["curl", "--fail", "--location", "--silent",
                            "--show-error", "--retry", "3",
                            "--retry-all-errors", "--connect-timeout", "20",
                            "--speed-limit", "10240", "--speed-time", "60",
                            "--continue-at", "-", "--output", out, url])
        if r.returncode == 0 and verified(path, size, sha):
            print(f"  ok: {path}", flush=True)
            return path, True
        if r.returncode == 0:
            # Transfer completed but bytes don't verify: drop them so the
            # next attempt restarts instead of resuming from bad bytes.
            try:
                os.remove(out)
            except OSError:
                pass
        elif r.returncode == 33:
            # Server refused the resume range (rc=33): the partial on disk
            # is unresumable — drop it so the next attempt starts fresh.
            try:
                os.remove(out)
            except OSError:
                pass
        print(f"  retry {attempt}/5: {path} (rc={r.returncode})", flush=True)
        time.sleep(min(30, 5 * attempt))
    print(f"  FAIL: {path} — size/sha256 mismatch after 5 attempts", flush=True)
    return path, False

with ThreadPoolExecutor(max_workers=int(nconns)) as ex:
    results = list(ex.map(fetch, files))

failed = [p for p, ok in results if not ok]
if failed:
    print(f"ERROR: {len(failed)} file(s) failed verification: {failed}", file=sys.stderr)
    sys.exit(1)
total = sum(f["size_bytes"] for f in files)
print(f"OK: {len(files)} files verified ({total/2**30:.1f} GiB) in {dest}")
PY
