"""Task 3+4: cell runners (run-cell-gguf.sh, run-cell-vllm.sh) — CI-safe contract.

Everything here runs WITHOUT a GPU: the runners are exercised only on their
refusal paths (unknown/malformed ids) and on --dry-run, which must resolve
and print the plan without launching anything. The matrix<->cells pairing
test keeps the committed receipts honest once host execution flips statuses.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run-cell-gguf.sh"
VSCRIPT = ROOT / "scripts" / "run-cell-vllm.sh"
MATRIX = ROOT / "docs" / "results" / "matrix-714" / "matrix.json"
CELLS_DIR = ROOT / "docs" / "results" / "matrix-714" / "cells"
# Branch point of feature/benchmark-matrix (main @ 2bb00ba): the serve confs
# must stay byte-stable across the whole branch — cells override via env only.
BRANCH_BASE = "2bb00ba"

# Cell id grammar, shared with gen-matrix.py and the verdicts schema
# (2026-08-18 backend-dimension migration: gguf ids carry -hip-|-vulkan-;
# 2026-08-21 dflash2 phase: the spec part gains the DFlash 2 drafter).
ID_RE_PARTS = ("gguf", "(hip|vulkan)", "udq4kxl", "auto", "{base|mtp|mtp4|dflash2}",
               "c{1,4,8,16}", "ctx{32768|131072|262144}")


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
    # The id grammar is asserted by the runner itself, not just by convention
    # (2026-08-21: the spec part includes the DFlash 2 drafter).
    for part in ("gguf-(hip|vulkan)-udq4kxl-auto-", "(base|mtp|mtp4|dflash2)",
                 "c(1|4|8|16)", "ctx(32768|131072|262144)"):
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
    r = run_runner(["gguf-hip-udq4kxl-auto-base-c3-ctx131072"])
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
    r = run_runner(["gguf-hip-udq4kxl-auto-base-c4-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "dry run" in out.lower()
    # Plan: the derived server env for a c4@131072 concurrency cell —
    # split KV semantics via explicit -np 4 over the declared total ctx.
    assert "CTX_SIZE=131072" in out
    assert "-np 4" in out
    assert "--concurrency 4" in out
    assert "backend" in out.lower() and "hip" in out.lower()
    assert MATRIX.read_bytes() == before_matrix, "dry run must not touch matrix.json"
    after_files = sorted(p.name for p in CELLS_DIR.glob("*.json")) if CELLS_DIR.exists() else []
    assert after_files == before_files, "dry run must not write cell files"


def test_runner_dry_run_mtp_and_ctx_tiers_derive_correct_env():
    # mtp cell: WITH_MTP=1; c1 keeps the default (unified) boot, no -np.
    r = run_runner(["gguf-hip-udq4kxl-auto-mtp-c1-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "WITH_MTP=1" in r.stdout
    assert "-np" not in r.stdout

    # ctx-tier cell at c4 keeps the declared unified/naive boot (no -np):
    # the cell ctx is the total, default slots are the validated quickstart.
    r = run_runner(["gguf-hip-udq4kxl-auto-base-c4-ctx262144", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "CTX_SIZE=262144" in r.stdout
    assert "-np" not in r.stdout

    # c8/c16 concurrency cells scale -np with N.
    r = run_runner(["gguf-hip-udq4kxl-auto-base-c16-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "-np 16" in r.stdout


def test_runner_refuses_legacy_unprefixed_id():
    # The 2026-08-18 migration made the backend tag explicit: legacy
    # unprefixed ids are hip but no longer resolvable (matrix-first lookup).
    r = run_runner(["gguf-udq4kxl-auto-base-c4-ctx131072", "--dry-run"])
    assert r.returncode != 0
    assert "not declared" in (r.stdout + r.stderr).lower() or \
        "unknown" in (r.stdout + r.stderr).lower()


# ---------------------------- v0.1.2 Task 2 plumbing: backend / depth / unified
# The pre-plumbing refusal test (T1) is REPLACED here by the real plumbing
# contract: backend binary resolution (build-714 vs build-714-vk), MTP depth
# id mapping (--spec-draft-n-max), and the unified-default-boot rider. Env
# knobs (BACKEND/SPEC_DEPTH/SLOTS) must AGREE with the id — a mismatch would
# make the receipt lie about what booted, so it is refused loudly.


def test_runner_resolves_backend_binary_class():
    # vulkan cell -> the build-714-vk binary; hip cell stays on build-714.
    r = run_runner(["gguf-vulkan-udq4kxl-auto-base-c1-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "build-714-vk/bin/llama-server" in r.stdout
    assert "build-714/bin/llama-server" not in r.stdout  # no silent hip fallback

    r = run_runner(["gguf-hip-udq4kxl-auto-base-c4-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "build-714/bin/llama-server" in r.stdout
    assert "build-714-vk" not in r.stdout


def test_runner_refuses_backend_env_id_mismatch():
    # BACKEND env is a cross-check, not an override: the id is the source of
    # truth. A vulkan id with BACKEND=hip would boot the HIP binary and the
    # receipt would lie about the backend.
    env = dict(os.environ, BACKEND="hip")
    r = subprocess.run(["bash", str(SCRIPT),
                        "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072", "--dry-run"],
                       capture_output=True, text=True, timeout=60, cwd=ROOT, env=env)
    assert r.returncode != 0
    combined = (r.stdout + r.stderr).lower()
    assert "backend" in combined and "mismatch" in combined


def test_runner_spec_depth_id_mapping():
    # mtp -> depth 1, mtp4 -> depth 4: the discovered depth mechanism at the
    # pin is --spec-draft-n-max (default 3 upstream), so the runner passes
    # the depth EXPLICITLY and the plan shows it.
    r = run_runner(["gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "--spec-draft-n-max 4" in r.stdout
    assert "WITH_MTP=1" in r.stdout

    r = run_runner(["gguf-hip-udq4kxl-auto-mtp-c1-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "--spec-draft-n-max 1" in r.stdout

    # base cell: no speculative machinery at all.
    r = run_runner(["gguf-vulkan-udq4kxl-auto-base-c1-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "--spec-draft-n-max" not in r.stdout


def test_runner_refuses_spec_depth_env_id_mismatch():
    env = dict(os.environ, SPEC_DEPTH="1")
    r = subprocess.run(["bash", str(SCRIPT),
                        "gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072", "--dry-run"],
                       capture_output=True, text=True, timeout=60, cwd=ROOT, env=env)
    assert r.returncode != 0
    combined = (r.stdout + r.stderr).lower()
    assert "spec_depth" in combined and "mismatch" in combined


def test_runner_unified_rider_boots_default_unified():
    # The -unified c4@131072 rider: NO -np flag (the stock quickstart default
    # boot), while the plain c4 cell at the same tier keeps the split -np 4.
    r = run_runner(["gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified", "--dry-run"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "-np" not in out
    assert "unified" in out.lower()
    assert "--concurrency 4" in out
    assert "CTX_SIZE=131072" in out

    r = run_runner(["gguf-hip-udq4kxl-auto-base-c4-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "-np 4" in r.stdout


def test_runner_refuses_unified_on_non_c4_and_slots_mismatch():
    # The grammar itself refuses -unified on non-c4; the runner must also
    # enforce it (belt and braces) and refuse a SLOTS env that contradicts
    # the id.
    r = run_runner(["gguf-hip-udq4kxl-auto-base-c1-ctx131072-unified", "--dry-run"])
    assert r.returncode != 0
    assert "unified" in (r.stdout + r.stderr).lower()

    env = dict(os.environ, SLOTS="unified")
    r = subprocess.run(["bash", str(SCRIPT),
                        "gguf-hip-udq4kxl-auto-base-c4-ctx131072", "--dry-run"],
                       capture_output=True, text=True, timeout=60, cwd=ROOT, env=env)
    assert r.returncode != 0
    combined = (r.stdout + r.stderr).lower()
    assert "slots" in combined and "mismatch" in combined


def test_runner_refuses_unified_on_non_c4_via_own_enforcement(tmp_path):
    # PATH PINNED (2026-08-18, v0.1.3 debt fix): the RUNNER's own c4-only
    # -unified enforcement ("the -unified suffix is only valid on c4 gguf
    # cells", exit 2) — NOT the matrix "not declared" refusal (exit 3) that
    # the test above rides on for undeclared ids. Here the id IS declared
    # (a scratch MATRIX_FILE, the runner's own override knob) and IS
    # grammatically valid (the regex accepts -unified on any c), so the
    # grammar passes and the c4-only guard is what refuses.
    manifest = json.loads(MATRIX.read_text())
    manifest["cells"] = manifest["cells"] + [{
        "id": "gguf-hip-udq4kxl-auto-base-c1-ctx131072-unified",
        "status": "planned", "runner_hint": "scripts/run-cell-gguf.sh"}]
    scratch_matrix = tmp_path / "scratch-matrix.json"
    scratch_matrix.write_text(json.dumps(manifest))
    env = dict(os.environ, MATRIX_FILE=str(scratch_matrix),
               CELLS_DIR=str(tmp_path / "cells"))  # never the project ns
    r = subprocess.run(["bash", str(SCRIPT),
                        "gguf-hip-udq4kxl-auto-base-c1-ctx131072-unified",
                        "--dry-run"],
                       capture_output=True, text=True, timeout=60, cwd=ROOT,
                       env=env)
    combined = r.stdout + r.stderr
    assert r.returncode == 2, combined  # the grammar-class exit, not matrix 3
    assert "-unified suffix is only valid on c4" in combined
    assert "not declared" not in combined.lower()  # matrix path did not fire


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
                    "load", "client", "anchor", "log_excerpt"):
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
        assert set(cell["load"]) >= {"vram_mib", "gtt_mib"}
        assert cell["load"]["gtt_mib"] is not None, f"{cid}.json has no GTT split"
        if cid.startswith("gguf-"):
            # llama.cpp slot semantics from the server log (METHODOLOGY 6).
            assert set(cell["slot_info"]) >= {"n_slots", "n_ctx_slot", "kv_unified"}
        else:
            # vLLM engine args captured verbatim from the boot log
            # (METHODOLOGY 7) + the instrument mode record (Task 4 contract).
            assert cell.get("engine", {}).get("non_default_args"), \
                f"{cid}.json missing engine.non_default_args capture"
            assert isinstance(cell.get("instrument_mode"), dict), \
                f"{cid}.json missing instrument_mode"


# --------------------------------------------------------------- Task 4 (vLLM)

def run_vllm_runner(args, timeout=60):
    return subprocess.run(["bash", str(VSCRIPT)] + args,
                          capture_output=True, text=True, timeout=timeout,
                          cwd=ROOT)


def test_vllm_runner_script_exists_and_names_the_contract():
    src = VSCRIPT.read_text()
    # Same lifecycle pattern as the gguf runner: matrix resolve, boot via the
    # serve script (confs untouched), health poll, rocm-smi split, bench
    # client + greedy anchor, cell JSON, matrix flip.
    assert "bench_client.py" in src
    assert "matrix-714/matrix.json" in src
    assert "rocm-smi" in src
    assert "--anchor-only" in src
    assert "03-serve-vllm.sh" in src
    assert "/health" in src
    # vLLM-specific: served model name comes from the conf, engine args are
    # captured from the boot log, the instrument mode is recorded per cell.
    assert "served-model-name" in src
    assert "non-default args" in src
    assert "instrument_mode" in src
    # Client-side concurrency (no -np analog); --no-thinking instrument mode.
    assert "--concurrency" in src
    assert "--no-thinking" in src
    # vLLM concurrency is client-parallel: no llama.cpp -np/EXTRA_ARGS path.
    assert "EXTRA_ARGS" not in src


def test_vllm_runner_enforces_id_format():
    src = VSCRIPT.read_text()
    for part in ("vllm-bf16-auto-", "(base|mtp|dflash)", "c(1|4|8|16)",
                 "ctx(131072|262144)"):
        assert part in src, f"vllm runner must encode id grammar part {part!r}"


def test_vllm_runner_dry_run_dflash_derives_dflash2_boot():
    # dflash cells boot 03-serve-vllm.sh --dflash2 with the dedicated conf;
    # ctx 131072 != the conf's 262144, so the MAX_MODEL_LEN override path
    # exercises too (the declared dflash tier — 262144 is KV-infeasible).
    r = run_vllm_runner(["vllm-bf16-auto-dflash-c1-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "--dflash2" in r.stdout
    assert "serve-args-dflash2.conf" in r.stdout
    assert "MAX_MODEL_LEN=131072" in r.stdout


def test_vllm_runner_dry_run_dflash_c1_c8_share_one_boot():
    r = run_vllm_runner(["vllm-bf16-auto-dflash-c1-ctx131072",
                         "vllm-bf16-auto-dflash-c8-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr


def test_vllm_runner_refuses_mixed_dflash_mtp_in_one_boot():
    # Same batch rule as {base,mtp}: one server config per invocation.
    r = run_vllm_runner(["vllm-bf16-auto-dflash-c1-ctx131072",
                         "vllm-bf16-auto-mtp-c1-ctx131072", "--dry-run"])
    assert r.returncode == 2
    assert "same server config" in r.stderr


def test_vllm_runner_records_spec_variant_in_cell_json():
    # Receipt honesty: the cell JSON must state which spec variant booted,
    # not just the legacy mtp boolean (a dflash cell records "dflash").
    src = VSCRIPT.read_text()
    assert '"spec_variant"' in src


def test_vllm_runner_refuses_unknown_id_not_in_matrix():
    # Grammar-valid (c3 outside the declared N set) but never declared.
    r = run_vllm_runner(["vllm-bf16-auto-base-c3-ctx262144"])
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    assert "matrix" in combined.lower()
    assert "unknown" in combined.lower() or "not declared" in combined.lower()


def test_vllm_runner_refuses_wrong_path_id():
    # A real matrix id, but for the OTHER path: the vllm runner must refuse it.
    r = run_vllm_runner(["gguf-hip-udq4kxl-auto-base-c1-ctx262144"])
    assert r.returncode != 0


def test_vllm_runner_refuses_ctx32768_tier():
    # Dropped tier for the vllm path: grammar-refused (no 32768 in the grammar).
    r = run_vllm_runner(["vllm-bf16-auto-base-c1-ctx32768"])
    assert r.returncode != 0


def test_vllm_runner_dry_run_prints_plan_without_launching():
    before_matrix = MATRIX.read_bytes()
    before_files = sorted(p.name for p in CELLS_DIR.glob("*.json"))
    r = run_vllm_runner(["vllm-bf16-auto-base-c1-ctx262144", "--dry-run"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "dry run" in out.lower()
    # Plan: conf-driven boot on :8000, served model from the conf, the exact
    # bench command (client-side concurrency, no-thinking instrument), anchor.
    assert "serve-args.conf" in out
    assert "03-serve-vllm.sh" in out
    assert "8000" in out
    assert "qwen3.8-27b" in out
    assert "--concurrency 1" in out
    assert "--no-thinking" in out
    assert "--anchor-only" in out
    # The validated conf boots max-model-len 262144 already: no override
    # needed for a ctx262144 cell (confs stay the validated defaults).
    assert "MAX_MODEL_LEN" not in out
    assert MATRIX.read_bytes() == before_matrix, "dry run must not touch matrix.json"
    after_files = sorted(p.name for p in CELLS_DIR.glob("*.json"))
    assert after_files == before_files, "dry run must not write cell files"


def test_vllm_runner_dry_run_mtp_conf_batch_and_ctx_override():
    # mtp cell -> serve-args-mtp.conf via --mtp.
    r = run_vllm_runner(["vllm-bf16-auto-mtp-c1-ctx262144", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "serve-args-mtp.conf" in r.stdout
    assert "--mtp" in r.stdout

    # Batch mode: one boot serves every listed cell of the same server config.
    r = run_vllm_runner(["vllm-bf16-auto-base-c1-ctx262144",
                         "vllm-bf16-auto-base-c4-ctx262144",
                         "vllm-bf16-auto-base-c8-ctx262144",
                         "vllm-bf16-auto-base-c16-ctx262144", "--dry-run"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "1 boot" in out or "one boot" in out.lower()
    assert "--concurrency 16" in out

    # A ctx131072 cell (declared, non-priority) needs the documented
    # MAX_MODEL_LEN env pass-through; the conf itself is never edited.
    r = run_vllm_runner(["vllm-bf16-auto-base-c1-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "MAX_MODEL_LEN=131072" in r.stdout

    # Mixed server configs in one invocation are refused (would need 2 boots).
    r = run_vllm_runner(["vllm-bf16-auto-base-c1-ctx262144",
                         "vllm-bf16-auto-mtp-c4-ctx262144", "--dry-run"])
    assert r.returncode != 0
    assert "same server config" in (r.stdout + r.stderr).lower()


# --------------------------------------- community cell namespace (T1 gap fix)
# Independent-verification gap: a community submitter following
# docs/hardware-validation.md must be able to run the SAME runners without
# writing into the project namespace. Contract (string-level, matching the
# runner tests above):
#   - CELLS_DIR defaults to the project cells dir but is overridable;
#   - MATRIX_FILE defaults to the project matrix manifest;
#   - any CELLS_DIR outside the project default skips the matrix flip
#     entirely (community submissions never edit the project matrix).

CELLS_DIR_DEFAULT_LINE = 'CELLS_DIR="${CELLS_DIR:-docs/results/matrix-714/cells}"'
MATRIX_FILE_DEFAULT_LINE = 'MATRIX_FILE="${MATRIX_FILE:-docs/results/matrix-714/matrix.json}"'
SKIP_MATRIX_RULE_LINE = '[ "$CELLS_DIR" = "docs/results/matrix-714/cells" ] || UPDATE_MATRIX=0'


def test_runner_declares_community_cells_namespace():
    src = SCRIPT.read_text()
    assert CELLS_DIR_DEFAULT_LINE in src
    assert MATRIX_FILE_DEFAULT_LINE in src
    assert SKIP_MATRIX_RULE_LINE in src
    assert "never edit the project matrix" in src


def test_vllm_runner_declares_community_cells_namespace():
    src = VSCRIPT.read_text()
    assert CELLS_DIR_DEFAULT_LINE in src
    assert MATRIX_FILE_DEFAULT_LINE in src
    assert SKIP_MATRIX_RULE_LINE in src
    assert "never edit the project matrix" in src


def test_runners_dry_run_honor_community_cells_dir(tmp_path):
    # Functional check (CI-safe: --dry-run only): with CELLS_DIR outside the
    # project default the plan writes cells there and says the matrix stays
    # untouched; with the default env the matrix flip is still in the plan.
    community = tmp_path / "community-cells"
    before_matrix = MATRIX.read_bytes()
    for runner, cell in ((SCRIPT, "gguf-hip-udq4kxl-auto-base-c4-ctx131072"),
                         (VSCRIPT, "vllm-bf16-auto-base-c1-ctx262144")):
        r = subprocess.run(["bash", str(runner), cell, "--dry-run"],
                           capture_output=True, text=True, timeout=60, cwd=ROOT,
                           env=dict(os.environ, CELLS_DIR=str(community)))
        assert r.returncode == 0, r.stderr
        assert str(community) in r.stdout, "plan must name the override CELLS_DIR"
        assert "matrix untouched" in r.stdout
        assert "never edit the project matrix" in r.stdout
        r2 = subprocess.run(
            ["bash", str(runner), cell, "--dry-run"],
            capture_output=True, text=True, timeout=60, cwd=ROOT)
        assert r2.returncode == 0, r2.stderr
        assert "matrix status flip" in r2.stdout, \
            "default CELLS_DIR must keep the matrix flip in the plan"
    assert MATRIX.read_bytes() == before_matrix, "dry run must not touch matrix.json"


def test_serve_confs_byte_stable_across_branch():
    # The matrix cells override nothing in the confs (env pass-through only,
    # METHODOLOGY 3 "confs stay the validated defaults"): both serve confs
    # must be byte-identical to their state at the branch point.
    try:
        verify = subprocess.run(["git", "rev-parse", "--verify",
                                 f"{BRANCH_BASE}^{{commit}}"],
                                cwd=ROOT, capture_output=True)
    except FileNotFoundError:
        pytest.skip("git unavailable")
    if verify.returncode != 0:
        pytest.skip(f"branch base {BRANCH_BASE} not in this clone")
    for conf in ("serve-args.conf", "serve-args-mtp.conf"):
        old = subprocess.run(["git", "show", f"{BRANCH_BASE}:configs/{conf}"],
                             cwd=ROOT, capture_output=True)
        assert old.returncode == 0, f"configs/{conf} missing at {BRANCH_BASE}"
        current = (ROOT / "configs" / conf).read_bytes()
        assert current == old.stdout, (
            f"configs/{conf} drifted from the branch point — cells must "
            f"override via documented env (03-serve-vllm.sh), never conf edits")


def test_long_context_smoke_builder_places_needle_at_80_percent():
    # Task 4 (S3): the haystack builder is deterministic and puts the needle
    # paragraph at ~80% depth with the retrieval question at the very end.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "long_context_smoke", ROOT / "scripts" / "long-context-smoke.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    para_tokens = 50
    counts = []

    def count(text):
        counts.append(text)
        return para_tokens * (text.count("maintenance log for sector") or 1)

    needle_q = "What is the validation codename?"
    prompt, meta = mod.build_haystack(1000, count, needle="The validation codename is STRIX-HALO-7741.",
                                      question=needle_q, template_margin=64)
    depth = prompt.index("STRIX-HALO-7741") / len(prompt)
    assert 0.75 <= depth <= 0.85, f"needle at {depth:.2f}, expected ~0.80"
    assert prompt.rstrip().endswith(needle_q)
    # Deterministic: same inputs -> byte-identical prompt.
    prompt2, _ = mod.build_haystack(1000, count, needle="The validation codename is STRIX-HALO-7741.",
                                    question=needle_q, template_margin=64)
    assert prompt2 == prompt


def test_long_context_smoke_receipt_records_invocation_argv():
    # Final-review fix (2026-08-17): every future receipt self-documents its
    # exact invocation (tiers/timeouts), verbatim sys.argv of the run. The
    # committed receipt predates the field (its 247K tier needed a raised
    # --request-timeout); do not re-run to backfill.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "long_context_smoke", ROOT / "scripts" / "long-context-smoke.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    argv = ["long-context-smoke.py", "--tiers", "262144:228000",
            "--request-timeout", "5400"]
    rec = mod.result_skeleton(argv)
    assert rec["argv"] == argv, "argv must be recorded verbatim"
    assert isinstance(rec["tiers"], list) and rec["needle"] in rec["description"]


# --------------------- R1 telemetry (2026-08-19): clocks/power/temp + cache
# Variance root-cause step 1: the cross-day Vulkan drop (s3 vs s1/s2) had no
# host-level telemetry in the receipts, so the cause was honestly "not
# recorded". The runners now snapshot sclk/mclk/power/temp (the SAME rocm-smi
# commands the controller probed) plus host-state one-liners at load AND
# post-bench, and (vulkan only) mesa_shader_cache stats before boot and after
# teardown. Contract: fail-loud on a missing rocm-smi BINARY, tolerant (null +
# snippet) on every missing/unreadable FIELD — telemetry must never abort a
# measurement run.

# Verbatim rocm-smi fixtures from the reference gfx1151 host (the exact
# command shapes telemetry_parse_json must survive).
ROCM_SMI_SHOWCLOCKS_FIXTURE = (
    "============================ ROCm System Management Interface "
    "============================\n"
    "=============================== Current clock frequencies "
    "===============================\n"
    "GPU[0]\t\t: mclk clock level: 2: (1000Mhz)\n"
    "GPU[0]\t\t: sclk clock level: 1: (1395Mhz)\n"
    "===================================================================="
    "======================\n"
    "================================== End of ROCm SMI Log "
    "===================================\n")
ROCM_SMI_SHOWPOWER_FIXTURE = (
    "============================ ROCm System Management Interface "
    "============================\n"
    "=================================== Power Consumption "
    "===================================\n"
    "GPU[0]\t\t: Current Socket Graphics Package Power (W): 20.045\n"
    "===================================================================="
    "======================\n"
    "================================== End of ROCm SMI Log "
    "===================================\n")
ROCM_SMI_SHOWTEMP_FIXTURE = (
    "============================ ROCm System Management Interface "
    "============================\n"
    "====================================== Temperature "
    "=======================================\n"
    "GPU[0]\t\t: Temperature (Sensor edge) (C): 49.0\n"
    "===================================================================="
    "======================\n"
    "================================== End of ROCm SMI Log "
    "===================================\n")


def _bash_function(src, name):
    """Extract a top-level bash function body (closing brace at column 0)
    from a script's source, so the parser can be exercised in CI without
    a GPU: the block is replayed in a fresh `bash -c` with fixture env."""
    m = re.search(rf"^{name}\(\) {{.*?^}}", src, re.S | re.M)
    assert m, f"{name}() not found in the script source"
    return m.group(0)


def _run_telemetry_parse(env_raw):
    src = SCRIPT.read_text()
    block = _bash_function(src, "telemetry_parse_json")
    env = dict(os.environ, **env_raw)
    r = subprocess.run(["bash", "-c", block + "\ntelemetry_parse_json"],
                       capture_output=True, text=True, timeout=60, cwd=ROOT,
                       env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_runner_telemetry_block_contract():
    src = SCRIPT.read_text()
    # The snapshot function parses the SAME rocm-smi commands the controller
    # probed and names every field the session README table needs.
    assert "telemetry_snapshot()" in src
    for token in ("--showclocks", "--showpower", "--showtemp",
                  "sclk_mhz", "mclk_mhz", "power_w", "temp_edge_c"):
        assert token in src, f"telemetry must capture {token!r}"
    # Host-state one-liners + raw-verbatim discipline + mesa-cache stats
    # (vulkan runs: before boot AND after teardown readings).
    assert '["uptime", "-s"]' in src
    assert '["powerprofilesctl", "get"]' in src
    assert "power_dpm_force_performance_level" in src
    assert '"raw"' in src and "mesa_shader_cache" in src and '"mesa_cache"' in src
    # Tolerant fields (null + snippet), fatal binary: both contracts present.
    assert '"errors"' in src
    assert "command -v rocm-smi" in src
    # The mesa-cache arm is vulkan-only.
    assert '[ "$BACKEND" = "vulkan" ]' in src


def test_runner_telemetry_parses_rocm_smi_fixture_output():
    got = _run_telemetry_parse({
        "CLOCKS_RAW": ROCM_SMI_SHOWCLOCKS_FIXTURE,
        "POWER_RAW": ROCM_SMI_SHOWPOWER_FIXTURE,
        "TEMP_RAW": ROCM_SMI_SHOWTEMP_FIXTURE,
    })
    assert got["sclk_mhz"] == 1395.0
    assert got["mclk_mhz"] == 1000.0
    assert got["power_w"] == 20.045
    assert got["temp_edge_c"] == 49.0
    assert got["errors"] == {}


def test_runner_telemetry_missing_fields_are_null_with_snippet():
    # Empty / unparsable / error-carrying raw output: null + the stderr
    # snippet recorded — telemetry never aborts the measurement run.
    got = _run_telemetry_parse({
        "CLOCKS_RAW": "",
        "CLOCKS_ERR": "",
        "POWER_RAW": "======== ROCm SMI Log ========\n(no power line)\n",
        "POWER_ERR": "",
        "TEMP_RAW": "",
        "TEMP_ERR": "ERROR: GPU busy, try again",
    })
    assert got["sclk_mhz"] is None and got["mclk_mhz"] is None
    assert got["power_w"] is None and got["temp_edge_c"] is None
    assert got["errors"]["sclk_mhz"] == "--showclocks: no rocm-smi output captured"
    assert got["errors"]["power_w"].startswith("--showpower:")
    assert "GPU busy" in got["errors"]["temp_edge_c"], (
        "the stderr snippet must land next to the null field")


def test_runner_post_bench_snapshot_and_load_telemetry_in_receipt():
    # Source contract: the receipt gains telemetry inside the load snapshot
    # AND a post_bench snapshot taken after the bench/anchor, before teardown.
    src = SCRIPT.read_text()
    assert '"telemetry"' in src, "load snapshot assembly must embed telemetry"
    assert "POST_BENCH_JSON" in src and '"post_bench"' in src
    # Ordering: the post_bench capture must precede teardown (cleanup_server),
    # the receipt assembly must follow it, and the after-teardown mesa-cache
    # reading must precede the assembly (it merges into load.telemetry).
    post_bench_at = src.index('POST_BENCH_JSON="$(TELEMETRY_JSON="$(telemetry_snapshot)')
    cleanup_at = src.index("cleanup_server\nwait_gtt_drain\ntrap - EXIT")
    mesa_after_at = src.index("mesa_cache_stats_json", src.index("MESA_CACHE_AFTER_JSON"))
    assert post_bench_at < cleanup_at, "post_bench must be captured before teardown"
    assert cleanup_at < mesa_after_at < src.index('CELL_TMP='), (
        "the after-teardown cache reading must land between teardown and the "
        "receipt assembly")
    # Dry-run still resolves and now names the telemetry snapshots.
    r = run_runner(["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "telemetry" in r.stdout.lower()
