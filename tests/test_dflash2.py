"""DFlash2 phase contract tests (2026-08-21) — CI-safe, no GPU.

Pins the DFlash 2 wiring the way the muse-rocm F-18 tests pinned DFlash v1:
the n-max constant lives in exactly one home (validated-stack.json) with a
single mirror (gguf-quickstart.sh's SPEC_DEPTH default) pinned against
drift; the quickstart refuses ambiguous drafter combinations; the runner
grammar/env derivation and the receipt flags stay in sync with what
actually boots; the artifact manifest carries the draft set with full
hashes; the build script pins the PR via the stack and never touches the
validated builds.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUICKSTART = ROOT / "scripts" / "gguf-quickstart.sh"
RUNNER = ROOT / "scripts" / "run-cell-gguf.sh"
BUILD = ROOT / "scripts" / "07-build-llama-dflash2.sh"
EQUIV = ROOT / "scripts" / "check-dflash2-equiv.sh"
STACK = ROOT / "configs" / "validated-stack.json"
MANIFEST = ROOT / "configs" / "artifact-manifest.json"


def stack():
    return json.loads(STACK.read_text(encoding="utf-8"))


def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# ------------------------------------------------------------ the n-max cap

def test_nmax_seven_has_exactly_one_home_and_one_mirror():
    s = stack()
    assert s["llama_cpp_dflash2"]["spec_draft_n_max"] == 7
    # The basis names the physics, not folklore.
    assert "block_size - 1" in s["llama_cpp_dflash2"]["spec_draft_n_max_basis"]
    # The quickstart default mirrors the stack value.
    src = QUICKSTART.read_text()
    assert 'DFLASH_N_MAX="${SPEC_DEPTH:-7}"' in src
    # The muse F-18 lesson: no hardcoded n-max literal at any call site —
    # the flags always consume the variable.
    assert "--spec-draft-n-max 16" not in src
    assert "--spec-draft-n-max 7" not in src


def test_quickstart_caps_nmax_at_seven_with_refusal():
    src = QUICKSTART.read_text()
    # Requesting > 7 is refused (upstream clamps it back anyway — ask for the
    # effective maximum directly, never a value that silently runs at 7).
    assert "exceeds the DFlash2 cap" in src


def test_runner_derives_seven_for_dflash2_cells():
    src = RUNNER.read_text()
    assert "dflash2) SPEC_DEPTH_DERIVED=7" in src
    assert "mtp)     SPEC_DEPTH_DERIVED=1" in src  # neighbors unchanged


# ------------------------------------------------------- quickstart wiring

def test_quickstart_dflash2_mode_wires_the_documented_flags():
    src = QUICKSTART.read_text()
    assert "WITH_DFLASH2" in src
    assert '"--spec-type" "draft-dflash"' in src.replace("'//", '"') \
        or "--spec-type draft-dflash" in src \
        or '"draft-dflash"' in src
    # The draft rides -md (the muse silent-no-op trap: -md WITHOUT
    # --spec-type is a silent no-op; the mode must pass BOTH).
    assert '-md "$DRAFT_PATH"' in src
    assert "build-714-dflash2" in src


def test_quickstart_refuses_mtp_and_dflash2_together():
    src = QUICKSTART.read_text()
    assert "mutually exclusive" in src
    assert 'if [ "$WITH_DFLASH2" = "1" ] && [ "${WITH_MTP:-0}" = "1" ]; then' in src


def test_quickstart_dflash2_draft_is_manifest_gated():
    src = QUICKSTART.read_text()
    assert '["sets"]["dflash2"]["dest"]' in src
    assert "SET=dflash2 bash scripts/02-fetch-model.sh" in src


def test_dflash2_default_boot_unchanged_without_opt_in():
    # The opt-in must be additive: the default server args line is built
    # exactly as before, and dflash2 flags only append under WITH_DFLASH2=1.
    src = QUICKSTART.read_text()
    assert 'SERVER_ARGS=(-m "$MODEL_PATH" --port "$PORT" -ngl 99 --ctx-size "$CTX_SIZE" --jinja)' in src
    assert 'if [ "$WITH_DFLASH2" = "1" ]; then' in src


# ---------------------------------------------------------------- artifacts

def test_manifest_dflash2_set_is_complete_and_hashed():
    d = manifest()["sets"]["dflash2"]
    assert d["host"] == "modelscope"
    assert d["repository"] == "incoai/Qwen3.8-27B-DFlash2-GGUF"
    files = {f["path"] for f in d["files"]}
    assert "Qwen3.8-27B-DFlash2-Q8_0.gguf" in files
    assert "Qwen3.8-27B-DFlash2-Q4_K_M.gguf" in files
    for f in d["files"]:
        assert f["size_bytes"] > 0
        assert len(f["sha256"]) == 64
        assert f["sha256"] == f["sha256"].lower()


# -------------------------------------------------------------------- build

def test_build_script_pins_pr_via_stack_and_protects_validated_builds():
    src = BUILD.read_text()
    assert "llama_cpp_dflash2" in src
    assert "build-714-dflash2" in src
    # The PR head pin is read from the stack, never hardcoded in the script.
    assert "5ecbe1ac17ec" not in src
    # Guard rails: refuse commits without DFlash2 support rather than
    # silently building a baseline-only binary.
    assert "draft-dflash" in src


def test_build_defaults_to_a_concrete_gpu_arch():
    # The generic-family bug (gfx11 vs gfx1100): the detection must match
    # exactly four digits so rocminfo's "gfx11-generic" can never win.
    src = BUILD.read_text()
    assert "gfx[0-9]{4}" in src
    assert "gfx[0-9a-f]+" not in src


# ------------------------------------------------------------------- runner

def test_runner_grammar_and_receipt_know_dflash2():
    src = RUNNER.read_text()
    assert "(base|mtp|mtp4|dflash2)" in src
    # Derivation + boot env + receipt all carry the flag.
    assert 'WITH_DFLASH2="$WITH_DFLASH2"' in src
    assert '"draft-dflash"' in src
    assert '"with_dflash2"' in src


def test_runner_honors_llama_server_override_in_preflight():
    # Clean-pairing support: an evidence run exporting LLAMA_SERVER (both
    # arms on one binary) must not be refused for build-714 being absent.
    src = RUNNER.read_text()
    assert '${LLAMA_SERVER:-' in src


# ------------------------------------------------------------------ evidence

def test_dflash2_matrix_declares_clean_paired_cells():
    m = json.loads((ROOT / "docs" / "results" / "dflash2" / "matrix.json")
                   .read_text(encoding="utf-8"))
    ids = {c["id"] for c in m["cells"]}
    for expected in (
        "gguf-hip-udq4kxl-auto-base-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-dflash2-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-base-c4-ctx131072",
        "gguf-hip-udq4kxl-auto-dflash2-c4-ctx131072",
        "gguf-hip-udq4kxl-auto-dflash2-c16-ctx32768",
    ):
        assert expected in ids, f"missing declared cell {expected}"
    # The pairing rule is stated, not implied.
    assert "SAME PR-27342 binary" in json.dumps(m)


def test_equiv_script_compares_same_binary_arms_and_writes_receipt():
    src = EQUIV.read_text()
    assert "byte" in src.lower()
    assert "WITH_DFLASH2=0" in src and "WITH_DFLASH2=1" in src
    assert "LLAMA_SERVER" in src


def test_stack_records_pr_pin_and_state():
    s = stack()["llama_cpp_dflash2"]
    assert s["pr"] == 27342
    assert s["commit"].startswith("5ecbe1ac")
    assert "OPEN" in s["pr_state_at_pin"]
    assert s["spec_type"] == "draft-dflash"


# ------------------------------------------------- acceptance probe (v0.1.10)

def test_probe_script_defaults_to_the_two_declared_regimes():
    src = (ROOT / "scripts" / "probe-dflash2-acceptance.sh").read_text()
    # Arm 1: the project bench convention; arm 2: the vendor's recommended
    # sampling (model card evaluation section) — the probe's whole point.
    assert "run_arm project07 0.7 0.95 -" in src
    assert "run_arm vendor10  1.0 0.95 20" in src
    # Fresh server per arm (cumulative acceptance counters must not mix).
    assert "WITH_DFLASH2=1 bash scripts/gguf-quickstart.sh" in src.replace(
        "env LLAMA_SERVER=\"$SERVER\" PORT=\"$PORT\" CTX_SIZE=\"${CTX_SIZE:-131072}\" \\\n        WITH_DFLASH2=1 bash scripts/gguf-quickstart.sh",
        "WITH_DFLASH2=1 bash scripts/gguf-quickstart.sh")


def test_acceptance_probe_receipt_is_committed_and_countable():
    r = json.loads((ROOT / "docs" / "results" / "dflash2" /
                    "acceptance-probe.json").read_text(encoding="utf-8"))
    assert r["verdict"] == "OK"
    for arm in ("project_bench_sampling", "vendor_recommended_sampling"):
        assert r[arm]["generated"] > 0
        assert 0.0 < r[arm]["acceptance"] < 1.0
    assert r["project_bench_sampling"]["sampling"]["top_k"] is None
    assert r["vendor_recommended_sampling"]["sampling"]["top_k"] == 20


# ------------------------------------------- headline numbers vs receipts

def _median_tok_s(cell_name):
    d = json.loads((ROOT / "docs" / "results" / "dflash2" / "cells" /
                    f"{cell_name}.json").read_text(encoding="utf-8"))
    toks = [1000 / s["tpot_ms"] for s in d["client"]["streams"]
            if s.get("tpot_ms")]
    toks.sort()
    n = len(toks)
    return (toks[n // 2] if n % 2 else (toks[n // 2 - 1] + toks[n // 2]) / 2)


def test_readme_claims_recompute_from_cell_receipts():
    """Guard against rounding-propagation drift (v0.1.11 correction): every
    headline percentage in the two README tables must recompute from the raw
    cell medians at 1 decimal place — never from the rounded display values."""
    base = {c: _median_tok_s(f"gguf-hip-udq4kxl-auto-base-{c}-ctx131072")
            for c in ("c1", "c4")}
    dflash = {c: _median_tok_s(f"gguf-hip-udq4kxl-auto-dflash2-{c}-ctx131072")
              for c in ("c1", "c4")}
    mtp = {c: _median_tok_s(f"gguf-hip-udq4kxl-auto-mtp-{c}-ctx131072")
           for c in ("c1", "c4")}
    claims = {
        "c1": f"{(dflash['c1'] / base['c1'] - 1) * 100:+.1f}%",   # +12.8%
        "c4": f"{(dflash['c4'] / base['c4'] - 1) * 100:+.1f}%",   # +23.3%
        "mtp_c1": f"{(mtp['c1'] / base['c1'] - 1) * 100:+.1f}%",  # +40.5%
        "mtp_c4": f"{(mtp['c4'] / base['c4'] - 1) * 100:+.1f}%",  # -5.0%
    }
    for name in ("README.md", "docs/results/dflash2/README.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        # READMEs use the typographic minus (U+2212); normalize before
        # comparing against the ASCII recomputation.
        text = text.replace("\u2212", "-")
        for claim in claims.values():
            assert claim in text, f"{name}: recomputed claim {claim} missing"
    # VRAM claims recompute too (mtp-c1 was once labeled with the c4 value).
    mtp_c1_vram = json.loads(
        (ROOT / "docs" / "results" / "dflash2" / "cells" /
         "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072.json").read_text(
            encoding="utf-8"))["load"]["vram_mib"] / 1024
    for name in ("README.md", "docs/results/dflash2/README.md"):
        assert f"{mtp_c1_vram:.1f} GiB" in (ROOT / name).read_text(
            encoding="utf-8"), f"{name}: mtp-c1 VRAM {mtp_c1_vram:.1f} GiB missing"
