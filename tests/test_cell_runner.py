"""Task 3: GGUF cell runner (scripts/run-cell-gguf.sh) — CI-safe contract.

Everything here runs WITHOUT a GPU: the runner is exercised only on its
refusal paths (unknown/malformed ids) and on --dry-run, which must resolve
and print the plan without launching anything. The matrix<->cells pairing
test keeps the committed receipts honest once host execution flips statuses.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run-cell-gguf.sh"
MATRIX = ROOT / "docs" / "results" / "matrix-714" / "matrix.json"
CELLS_DIR = ROOT / "docs" / "results" / "matrix-714" / "cells"

# Cell id grammar, shared with gen-matrix.py and the verdicts schema.
ID_RE_PARTS = ("gguf", "udq4kxl", "auto", "{base|mtp}", "c{1,4,8,16}",
               "ctx{32768|131072|262144}")


def run_runner(args, timeout=60):
    return subprocess.run(["bash", str(SCRIPT)] + args,
                          capture_output=True, text=True, timeout=timeout,
                          cwd=ROOT)


def test_runner_script_exists_and_names_the_contract():
    src = SCRIPT.read_text()
    # The runner drives the Task 2 client, resolves against the matrix
    # manifest, snapshots memory via rocm-smi, and runs the greedy anchor.
    assert "bench_client.py" in src
    assert "matrix-714/matrix.json" in src
    assert "rocm-smi" in src
    assert "--anchor-only" in src
    assert "--health" in src or "/health" in src
    # Concurrency is server-side via llama.cpp -np, passed through the
    # quickstart's EXTRA_ARGS (authorized Task 3 addition).
    assert "EXTRA_ARGS" in src
    assert "-np" in src
    # Slot semantics recorded from the server log (METHODOLOGY section 6).
    assert "n_ctx_slot" in src
    assert "kv_unified" in src


def test_runner_enforces_id_format():
    src = SCRIPT.read_text()
    # The id grammar is asserted by the runner itself, not just by convention.
    for part in ("gguf-udq4kxl-auto-", "(base|mtp)", "c(1|4|8|16)",
                 "ctx(32768|131072|262144)"):
        assert part in src, f"runner must encode id grammar part {part!r}"


def test_runner_refuses_malformed_id():
    r = run_runner(["definitely-not-a-cell"])
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    # Refusal is matrix-first (the manifest is the source of truth), so a
    # garbage id is refused as undeclared before the grammar check fires.
    assert any(s in combined.lower() for s in
               ("not a valid", "invalid", "not declared", "unknown"))


def test_runner_refuses_unknown_id_not_in_matrix():
    # Grammar-valid (so the refusal exercises the matrix lookup, not the regex)
    # but never declared: c3 is outside the declared N set.
    r = run_runner(["gguf-udq4kxl-auto-base-c3-ctx131072"])
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    assert "matrix" in combined.lower()
    assert "unknown" in combined.lower() or "not declared" in combined.lower()


def test_runner_refuses_wrong_path_id():
    # A real matrix id, but for the OTHER path: the gguf runner must refuse it.
    r = run_runner(["vllm-bf16-auto-base-c1-ctx262144"])
    assert r.returncode != 0


def test_runner_dry_run_prints_plan_without_launching():
    # Snapshot the mutable receipts: a dry run must not create or change any.
    before_matrix = MATRIX.read_bytes()
    before_files = sorted(p.name for p in CELLS_DIR.glob("*.json")) if CELLS_DIR.exists() else []
    r = run_runner(["gguf-udq4kxl-auto-base-c4-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "dry run" in out.lower()
    # Plan: the derived server env for a c4@131072 concurrency cell —
    # split KV semantics via explicit -np 4 over the declared total ctx.
    assert "CTX_SIZE=131072" in out
    assert "-np 4" in out
    assert "--concurrency 4" in out
    assert MATRIX.read_bytes() == before_matrix, "dry run must not touch matrix.json"
    after_files = sorted(p.name for p in CELLS_DIR.glob("*.json")) if CELLS_DIR.exists() else []
    assert after_files == before_files, "dry run must not write cell files"


def test_runner_dry_run_mtp_and_ctx_tiers_derive_correct_env():
    # mtp cell: WITH_MTP=1; c1 keeps the default (unified) boot, no -np.
    r = run_runner(["gguf-udq4kxl-auto-mtp-c1-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "WITH_MTP=1" in r.stdout
    assert "-np" not in r.stdout

    # ctx-tier cell at c4 keeps the declared unified/naive boot (no -np):
    # the cell ctx is the total, default slots are the validated quickstart.
    r = run_runner(["gguf-udq4kxl-auto-base-c4-ctx262144", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "CTX_SIZE=262144" in r.stdout
    assert "-np" not in r.stdout

    # c8/c16 concurrency cells scale -np with N.
    r = run_runner(["gguf-udq4kxl-auto-base-c16-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "-np 16" in r.stdout


def test_matrix_measured_cells_pair_with_cell_files():
    m = json.loads(MATRIX.read_text())
    measured = {c["id"] for c in m["cells"] if c["status"] == "measured"}
    on_disk = {p.stem for p in CELLS_DIR.glob("*.json")} if CELLS_DIR.exists() else set()
    assert measured == on_disk, (
        f"matrix/cells mismatch: measured-not-on-disk={sorted(measured - on_disk)} "
        f"on-disk-not-measured={sorted(on_disk - measured)}")
    for cid in sorted(measured):
        cell = json.loads((CELLS_DIR / f"{cid}.json").read_text())
        for key in ("id", "label", "base_url", "started_utc", "server_flags",
                    "slot_info", "load", "client", "anchor", "log_excerpt"):
            assert key in cell, f"{cid}.json missing {key!r}"
        assert isinstance(cell["anchor"].get("ok"), bool)
        assert isinstance(cell["log_excerpt"], list)
        assert len(cell["log_excerpt"]) <= 20
        if cell.get("degraded"):
            # A degraded cell (boot failure, failed streams, anchor drift) is
            # still committed with the failure recorded, never silently rich
            # metrics: slot/load/client may be null, but the reason must be.
            assert cell.get("degraded_reason"), f"{cid}.json degraded without reason"
            continue
        assert set(cell["slot_info"]) >= {"n_slots", "n_ctx_slot", "kv_unified"}
        assert set(cell["load"]) >= {"vram_mib", "gtt_mib"}
        assert cell["load"]["gtt_mib"] is not None, f"{cid}.json has no GTT split"
