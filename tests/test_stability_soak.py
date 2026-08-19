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

import json
import os
import re
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
    # v0.1.3 telemetry (2026-08-18 debt fix): health_flaps counts mid-soak
    # health-check failures (0 in a normal run) into totals.
    assert '"health_flaps"' in src, "soak totals must name health_flaps"


def test_soak_captures_llama_server_banner_from_stderr():
    # v0.1.3 debt fix verification (CI-safe, no host run): llama-server
    # prints its --version banner to STDERR, so the receipt's
    # llama_server_version resolves only when BOTH streams are captured
    # (stdout alone — the pre-fix behavior that left the committed soak
    # receipt with llama_server_version: null — is not enough). The capture
    # lives in the real-execution MODEL_JSON block; this pins the source
    # contract that keeps it resolving.
    src = SCRIPT.read_text()
    assert "llama_server_version" in src
    assert "banner to stderr" in src or "prints to STDERR" in src, (
        "the banner-is-on-stderr fact must stay documented next to the capture")
    assert "ver = (p.stdout or \"\") + (p.stderr or \"\")" in src, (
        "both streams must be captured for llama_server_version to resolve")


def test_soak_counts_health_flaps_during_the_soak():
    # The counter is incremented at every failed health check at a cycle
    # boundary (the HEALTH_RECOVER_S wait path) and lands in totals — 0 in a
    # normal run, >0 surfaced as an anomaly.
    src = SCRIPT.read_text()
    assert "HEALTH_FLAPS=0" in src, "the counter must start at 0"
    assert 'HEALTH_FLAPS=$((HEALTH_FLAPS + 1))' in src, (
        "a failed health check during the soak must count as a flap")
    assert "mid-soak health flap(s)" in src, (
        "a non-zero flap count must be surfaced as an anomaly")


# --------------------- R1 telemetry (2026-08-19): clocks/power/temp + cache
# Variance root-cause step 1, same harness as the cell runner: the soak's
# load snapshot gains a telemetry block and a NEW post_bench snapshot is
# taken after the soak window/anchor, before teardown. Same tolerance
# contract (null + snippet per field; rocm-smi binary stays fatal).


def test_soak_gains_the_same_telemetry_block():
    src = SCRIPT.read_text()
    for token in ("telemetry_snapshot()", "telemetry_parse_json",
                  "--showclocks", "--showpower", "--showtemp",
                  "sclk_mhz", "mclk_mhz", "power_w", "temp_edge_c",
                  '["uptime", "-s"]', '["powerprofilesctl", "get"]',
                  "power_dpm_force_performance_level",
                  "mesa_shader_cache", '"mesa_cache"',
                  '"telemetry"', "POST_BENCH_JSON", '"post_bench"',
                  "command -v rocm-smi", '"errors"'):
        assert token in src, f"soak telemetry must capture {token!r}"
    # The soak is vulkan-pinned, so the mesa-cache readings are unconditional.
    assert "MESA_CACHE_BEFORE_JSON" in src and "MESA_CACHE_AFTER_JSON" in src
    # Functional: the parser (extracted, no GPU) reads the reference-host
    # rocm-smi output shapes.
    m = re.search(r"^telemetry_parse_json\(\) \{.*?^\}", src, re.S | re.M)
    assert m, "telemetry_parse_json() not found in the soak source"
    env = dict(os.environ,
               CLOCKS_RAW="GPU[0]\t\t: sclk clock level: 1: (1409Mhz)\n"
                          "GPU[0]\t\t: mclk clock level: 2: (1000Mhz)\n",
               POWER_RAW="GPU[0]\t\t: Current Socket Graphics Package Power "
                         "(W): 16.1\n",
               TEMP_RAW="GPU[0]\t\t: Temperature (Sensor edge) (C): 46.0\n")
    r = subprocess.run(["bash", "-c", m.group(0) + "\ntelemetry_parse_json"],
                       capture_output=True, text=True, timeout=60, cwd=ROOT,
                       env=env)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert (got["sclk_mhz"], got["mclk_mhz"]) == (1409.0, 1000.0)
    assert got["power_w"] == 16.1 and got["temp_edge_c"] == 46.0
    assert got["errors"] == {}
