"""Stability follow-up S1: scripts/stability-soak.sh — CI-safe contract.

The soak boots a real GPU server for SOAK_MINUTES, so CI (no GPU) only
exercises --dry-run (the resolved plan, nothing launched) and the
source-level contracts:

* the boot derivation is the SAME code shape run-cell-gguf.sh uses for
  gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072 (the recommended config under
  re-measurement): BACKEND=vulkan -> build-714-vk, WITH_MTP=1 + SPEC_DEPTH=1
  -> --spec-type draft-mtp --spec-draft-n-max 1, c1 default boot (no -np);
* SOAK_DIR is required (receipts never land in an implicit default);
* teardown is guaranteed (trap on EXIT) so a failed soak cannot orphan a
  llama-server holding 30+ GiB of GTT;
* the receipt names the schema keys the session README compares against.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "stability-soak.sh"
MATRIX = ROOT / "docs" / "results" / "matrix-714" / "matrix.json"
CELLS_DIR = ROOT / "docs" / "results" / "matrix-714" / "cells"


def run_soak(args, env_extra=None, timeout=60):
    env = dict(os.environ)
    env.pop("SOAK_DIR", None)
    env.pop("SOAK_MINUTES", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["bash", str(SCRIPT)] + args,
                          capture_output=True, text=True, timeout=timeout,
                          cwd=ROOT, env=env)


def test_soak_script_exists_and_names_the_contract():
    src = SCRIPT.read_text()
    # Same machinery as the cell runner: quickstart boot, bench client +
    # greedy anchor gate, rocm-smi split, health poll, GPU-drain wait.
    assert "gguf-quickstart.sh" in src
    assert "bench_client.py" in src
    assert "--anchor-only" in src
    assert "rocm-smi" in src
    assert "/health" in src
    assert "anchor_ok" in src  # gate is the JSON field, never the exit code
    # Pinned to the recommended config under stability re-measurement.
    assert "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072" in src
    assert "build-714-vk/bin/llama-server" in src
    # Source-of-truth pointer: the derivation mirrors the runner, which is
    # never refactored from here (S1 constraint).
    assert "run-cell-gguf.sh" in src


def test_soak_dry_run_prints_exact_vulkan_mtp_boot_flags(tmp_path):
    # The plan must show EXACTLY what run-cell-gguf.sh derives for the cell:
    # vulkan backend binary, ctx 131072, WITH_MTP=1 SPEC_DEPTH=1 (=> the
    # draft-mtp pair with depth 1), default c1 boot (no -np).
    before_matrix = MATRIX.read_bytes()
    before_files = sorted(p.name for p in CELLS_DIR.glob("*.json"))
    r = run_soak(["--dry-run"], env_extra={"SOAK_DIR": str(tmp_path)})
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "dry run" in out.lower()
    assert "BACKEND=vulkan" in out
    assert "CTX_SIZE=131072" in out
    assert "WITH_MTP=1" in out
    assert "SPEC_DEPTH=1" in out
    assert "--spec-type draft-mtp" in out
    assert "--spec-draft-n-max 1" in out
    assert "EXTRA_ARGS=''" in out  # c1 default boot: no -np, verbatim empty
    assert "-np " not in out
    assert "build-714-vk/bin/llama-server" in out
    # Boot nothing, write nothing: no receipt, no matrix/cells drift.
    assert list(tmp_path.iterdir()) == [], "dry run must not write the receipt"
    assert MATRIX.read_bytes() == before_matrix
    after_files = sorted(p.name for p in CELLS_DIR.glob("*.json"))
    assert after_files == before_files


def test_soak_dry_run_respects_env_knobs(tmp_path):
    r = run_soak(["--dry-run"], env_extra={"SOAK_DIR": str(tmp_path),
                                           "SOAK_MINUTES": "7"})
    assert r.returncode == 0, r.stderr
    assert "SOAK_MINUTES=7" in r.stdout
    assert str(tmp_path) in r.stdout  # the receipt destination is named
    assert list(tmp_path.iterdir()) == []


def test_soak_requires_soak_dir():
    r = run_soak(["--dry-run"])  # no SOAK_DIR in the env at all
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    assert "SOAK_DIR" in combined
    assert "required" in combined.lower()


def test_soak_guarantees_teardown_and_gpu_clean_check():
    src = SCRIPT.read_text()
    # Guaranteed teardown on any exit path: trap + graceful kill + escalate,
    # then a GTT drain wait and an explicit GPU-clean assertion at exit.
    assert "trap cleanup_server EXIT" in src
    assert "kill -9" in src
    assert "wait_gtt_drain" in src
    assert "gpu_clean" in src


def test_soak_receipt_schema_keys_named_in_source():
    src = SCRIPT.read_text()
    # Session README comparisons (v0.1.2 vs session-2 medians, soak per-cycle
    # min/median/max, anchor status) read these keys from the soak receipt.
    for key in ("started_utc", "server_flags", "slot_info", "load", "cycles",
                "anchor", "totals", "script_git_rev", "soak_minutes",
                "wall_minutes"):
        assert f'"{key}"' in src, f"soak receipt must name key {key!r}"
    # Per-cycle record fields the drift trend is computed from.
    assert '"tok_per_s"' in src
    assert '"index"' in src
