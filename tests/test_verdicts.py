"""Task 5: verdict system + generated README blocks + anti-pit CI guarantee.

Three guarantees under test, all CPU-safe:

1. Verdicts JSON (configs/benchmark-verdicts.json) is schema-valid, covers
   exactly the matrix's measured cells, and carries an honest per-cell record
   (headline metrics in every cell; conditions on every caution; reason +
   workaround on every avoid; the interactive floor named wherever it is
   unmet).
2. The auto-verdict ladder in scripts/gen-verdicts.py behaves per the
   pre-declared METHODOLOGY.md §3 rules on SYNTHETIC cells (abort -> avoid;
   8 tok/s at c1 -> not recommended; c16 aggregate up but per-stream 3 tok/s
   -> caution/avoid; clean c4 -> recommended; anchor break -> avoid;
   aggregate regression -> avoid candidate).
3. The quickstart can never point at a pit (test_quickstart_configs_*): every
   config the user-facing scripts reference by default maps to the verdict
   the controller ruling of 2026-08-17 recorded — gguf defaults + WITH_MTP
   recommended; vllm serve confs caution WITH non-empty conditions — and,
   since the controller ruling of 2026-08-18 (v0.1.2), the BACKEND=vulkan
   opt-in maps to a recommended, anchor-clean cell while the DEFAULT stays
   hip. If a future measurement changes that, this test fails and the
   controller must either change the quickstart default or record a new
   justified ruling.
"""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent
VERDICTS = ROOT / "configs" / "benchmark-verdicts.json"
MATRIX = ROOT / "docs" / "results" / "matrix-714" / "matrix.json"
CELLS_DIR = ROOT / "docs" / "results" / "matrix-714" / "cells"
SCHEMA = ROOT / "schemas" / "benchmark-verdicts.schema.json"
GEN = ROOT / "scripts" / "gen-verdicts.py"
RENDER = ROOT / "scripts" / "render-readme-blocks.py"
README = ROOT / "README.md"
BENCH_MD = ROOT / "docs" / "results" / "benchmark.md"
QUICKSTART = ROOT / "scripts" / "gguf-quickstart.sh"


def load(p):
    return json.loads(Path(p).read_text())


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------ 1. verdicts JSON

def test_verdicts_file_is_schema_valid():
    schema = load(SCHEMA)
    verdicts = load(VERDICTS)
    jsonschema.validate(verdicts, schema)


def test_verdicts_cover_exactly_the_measured_cells():
    """Measured <-> verdicted consistency, both directions: every measured
    matrix cell carries a verdict, and no verdict exists for a cell the
    matrix does not list as measured (planned/dropped cells are never
    verdicted — an unmeasured cell has no evidence to verdict on)."""
    m = load(MATRIX)
    measured = {c["id"] for c in m["cells"] if c["status"] == "measured"}
    verdicted = {c["id"] for c in load(VERDICTS)["cells"]}
    assert verdicted == measured, (
        f"verdicts/measured mismatch: missing={sorted(measured - verdicted)} "
        f"extra={sorted(verdicted - measured)}")


def test_review_is_recorded():
    v = load(VERDICTS)
    assert v.get("reviewed_by", "").startswith("controller-"), (
        "auto-verdicts must never ship unreviewed (METHODOLOGY 3 final "
        "authority): reviewed_by must be controller-<date>")


def test_every_cell_carries_headline_metrics():
    v = load(VERDICTS)
    for cell in v["cells"]:
        m = cell["metrics"]
        for key in ("per_stream_tok_s_median", "aggregate_tok_s",
                    "ttft_ms_median", "anchor_ok"):
            assert key in m, f"{cell['id']} metrics missing {key}"
        assert isinstance(m["per_stream_tok_s_median"], (int, float))
        assert m["aggregate_tok_s"] > 0
        assert isinstance(m["anchor_ok"], bool)
        assert m.get("healthy_streams", 0) >= 1, (
            f"{cell['id']}: no healthy stream (>=2 content tokens) — the "
            f"cell's UX numbers would be vacuous")


def test_every_caution_has_conditions_every_avoid_has_remedies():
    v = load(VERDICTS)
    for cell in v["cells"]:
        verdict, cid = cell["verdict"], cell["id"]
        assert len(cell["reason"]) >= 20, f"{cid}: reason too thin"
        if verdict == "caution":
            assert cell.get("conditions", "").strip(), (
                f"{cid}: caution without conditions is a trap for the reader")
        if verdict == "avoid":
            assert cell.get("workaround", "").strip(), (
                f"{cid}: avoid without a workaround strands the operator")
            assert cell.get("conditions", "").strip() or cell.get("upstream", "").strip(), (
                f"{cid}: avoid needs conditions or an upstream pointer")


def test_floor_unmet_is_said_out_loud_in_the_reason():
    """The honesty clause: a cell below the 10 tok/s interactive floor must
    name the floor (or 'tok/s') in its reason — aggregate wins are never the
    first and only sentence."""
    v = load(VERDICTS)
    for cell in v["cells"]:
        if cell["metrics"]["per_stream_tok_s_median"] < 10.0:
            reason = cell["reason"].lower()
            assert "tok/s" in reason or "floor" in reason, (
                f"{cell['id']}: below-floor cell whose reason never states "
                f"the per-stream cost")


def test_degraded_gguf_cells_are_avoid():
    """The 5 anchor-degraded cells (greedy '////' corruption, METHODOLOGY 6)
    must be avoid with the pit in the reason and llama.cpp as upstream."""
    m = load(MATRIX)
    degraded = {c["id"] for c in m["cells"]
                if c["status"] == "measured" and c.get("degraded")}
    v = {c["id"]: c for c in load(VERDICTS)["cells"]}
    assert degraded, "expected the 5 degraded matrix cells to exist"
    for cid in degraded:
        cell = v[cid]
        assert cell["verdict"] == "avoid", f"{cid}: anchor-degraded must avoid"
        assert "////" in cell["reason"] or "greedy" in cell["reason"].lower(), (
            f"{cid}: avoid reason must cite the greedy-degradation pit")
        assert "llama.cpp" in cell.get("upstream", ""), (
            f"{cid}: pit upstream must point at llama.cpp")


def test_units_stay_binary_no_decimal_gib():
    """No committed verdict text may reintroduce the parked /1000 'GiB' slip
    (METHODOLOGY 5: the correct figure is 8.0 GiB, never 'approx 8.2')."""
    v = load(VERDICTS)
    for cell in v["cells"]:
        blob = json.dumps(cell)
        assert "8.2 GiB" not in blob, f"{cell['id']}: the 8.2 slip is back"
        assert "MiB / 1000" not in blob and "MiB/1000" not in blob


# ------------------------------------------------------- 2. ladder unit tests

gv = load_module(GEN, "gen_verdicts_ladder")


def synth(**over):
    """A clean synthetic c1 cell at 12 tok/s; override per test."""
    m = {
        "c": 1, "boot_ok": True, "failed_streams": 0, "anchor_ok": True,
        "per_stream_tok_s_median": 12.0, "per_stream_tok_s_min": 11.5,
        "tpot_ms_median": 83.3, "ttft_ms_median": 4000.0,
        "aggregate_tok_s": 12.0, "healthy_streams": 1,
        "lower_aggregate_best": None, "base_aggregate": None,
    }
    m.update(over)
    return m


def test_ladder_abort_is_avoid():
    out = gv.auto_ladder(synth(failed_streams=2))
    assert out["verdict"] == "avoid"
    assert out["rung"].startswith("rung1")


def test_ladder_floor_8_tok_s_c1_is_not_recommended():
    # METHODOLOGY 3 rung 2 severity: 8-10 tok/s band -> caution.
    out = gv.auto_ladder(synth(per_stream_tok_s_median=8.0))
    assert out["verdict"] == "caution"
    assert "floor" in out["reason"].lower()


def test_ladder_below_8_tok_s_c1_is_avoid():
    out = gv.auto_ladder(synth(per_stream_tok_s_median=6.5))
    assert out["verdict"] == "avoid"
    assert out["rung"].startswith("rung2")


def test_ladder_c16_aggregate_up_but_per_stream_3_tok_s():
    out = gv.auto_ladder(synth(c=16, per_stream_tok_s_median=3.0,
                               per_stream_tok_s_min=2.4, aggregate_tok_s=30.0,
                               lower_aggregate_best=20.0, healthy_streams=16))
    assert out["verdict"] in ("caution", "avoid")
    assert out["verdict"] != "recommended"


def test_ladder_clean_c4_is_recommended():
    out = gv.auto_ladder(synth(c=4, per_stream_tok_s_median=11.0,
                               aggregate_tok_s=38.0,
                               lower_aggregate_best=12.0, healthy_streams=4))
    assert out["verdict"] == "recommended"


def test_ladder_anchor_break_is_avoid():
    out = gv.auto_ladder(synth(anchor_ok=False))
    assert out["verdict"] == "avoid"
    assert out["rung"].startswith("rung1")


def test_ladder_aggregate_regression_is_avoid_candidate():
    # Floor passed but the family's aggregate regresses vs lower concurrency
    # (rung 3): avoid candidate -> avoid, confirmed against the raw cell.
    out = gv.auto_ladder(synth(c=16, per_stream_tok_s_median=12.0,
                               aggregate_tok_s=25.0,
                               lower_aggregate_best=30.0, healthy_streams=16))
    assert out["verdict"] == "avoid"
    assert out["rung"].startswith("rung3")


def test_ladder_mtp_regression_vs_base_counterpart_flags_rung3():
    # The DFlash lesson form: mtp aggregate below the BASE aggregate at the
    # same concurrency is a rung-3 avoid candidate even within-family it
    # improved vs lower c.
    out = gv.auto_ladder(synth(c=16, per_stream_tok_s_median=3.0,
                               aggregate_tok_s=31.1,
                               lower_aggregate_best=24.7, base_aggregate=38.6,
                               healthy_streams=16))
    assert out["avoid_candidate"], (
        "mtp below its base counterpart must at least flag the regression")


def test_compute_metrics_excludes_non_healthy_streams():
    """The c4 caveat: streams with <2 content tokens (tpot null) or a
    degenerate 0.0 tpot must not count toward per-stream UX statistics."""
    cell = {
        "boot": {"ok": True},
        "anchor": {"ok": True},
        "load": {"vram_mib": 1131, "gtt_mib": 26550},
        "client": {
            "streams": [
                {"ttft_ms": 1000.0, "tpot_ms": 100.0,
                 "completion_tokens": 256, "finish_reason": "length", "ok": True},
                {"ttft_ms": None, "tpot_ms": None,
                 "completion_tokens": 1, "finish_reason": "stop", "ok": True},
                {"ttft_ms": 1000.0, "tpot_ms": 0.0,
                 "completion_tokens": 2, "finish_reason": "stop", "ok": True},
                {"ttft_ms": 1000.0, "tpot_ms": 120.0,
                 "completion_tokens": 219, "finish_reason": "stop", "ok": True},
            ],
            "aggregate": {"tok_per_s": 9.42, "wall_s": 54.1,
                          "ok_streams": 4, "failed_streams": 0},
        },
    }
    m = gv.compute_metrics(cell)
    assert m["streams"] == 4
    assert m["healthy_streams"] == 2  # the 1-token and 2-token streams excluded
    assert m["per_stream_tok_s_median"] == 9.17  # median(1000/100, 1000/120)
    assert m["min_completion_tokens"] == 1
    assert m["capped_streams"] == 1


# ------------------------------------------------------------- 3. freshness

def test_gen_verdicts_check_mode_reports_fresh():
    r = subprocess.run([sys.executable, str(GEN), "--check"],
                       capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert r.returncode == 0, (
        f"verdicts stale vs raw cells — rerun scripts/gen-verdicts.py:\n"
        f"{r.stdout}\n{r.stderr}")


README_BLOCKS = ("performance-highlights", "context-capacity", "known-good-bad")


def test_readme_has_generated_block_markers():
    text = README.read_text()
    for block in README_BLOCKS:
        assert f"<!-- BEGIN GENERATED: {block}" in text, f"missing marker {block}"
        assert f"<!-- END GENERATED: {block} -->" in text, f"missing end marker {block}"


def test_readme_blocks_and_benchmark_md_regenerate_byte_identical():
    """Marker freshness: a regeneration pass must be a no-op diff on README.md
    and docs/results/benchmark.md (hand-editing inside markers is forbidden —
    it would be silently destroyed by the next regen)."""
    before = {p: p.read_bytes() for p in (README, BENCH_MD)}
    r = subprocess.run([sys.executable, str(RENDER)], capture_output=True,
                       text=True, cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stderr
    for p, b in before.items():
        assert p.read_bytes() == b, (
            f"{p.name} changed on regeneration — regenerate and commit, never "
            f"hand-edit generated content")


# -------------------------- 3b. known-bad block contract (readme-polish B)
#
# The README rendering dedups the ~600-char upstream tail the 5 greedy-pit
# cells share (the verdicts JSON keeps the full per-cell string — only the
# README rendering collapses it into one shared subsection).

def _readme_block(name: str) -> str:
    text = README.read_text()
    m = re.search(rf"<!-- BEGIN GENERATED: {name} -->\n(.*?)\n"
                  rf"<!-- END GENERATED: {name} -->", text, re.S)
    assert m, f"README missing generated block {name!r}"
    return m.group(1)


def _pit_cells() -> dict:
    return {c["id"]: c for c in load(VERDICTS)["cells"]
            if c["verdict"] == "avoid" and not c["metrics"]["anchor_ok"]}


def test_known_bad_pit_bullets_are_short_and_keep_own_numbers():
    """Each greedy-pit bullet carries only its own measured numbers plus the
    workaround — no inlined upstream tail (that lives in the shared
    subsection, emitted once)."""
    block = _readme_block("known-good-bad")
    bullets = [ln for ln in block.splitlines() if ln.startswith("- ❌ `gguf-")]
    pits = _pit_cells()
    assert len(bullets) == len(pits) >= 5, (
        f"{len(bullets)} pit bullets vs {len(pits)} pit verdicts")
    for ln in bullets:
        cid = re.match(r"- ❌ `([^`]+)`", ln).group(1)
        assert cid in pits, f"{cid} is not a greedy-pit verdict cell"
        assert len(ln) <= 300, (
            f"{cid}: pit bullet is {len(ln)} chars (target <= 300) — the "
            f"shared upstream tail must not be inlined per bullet")
        m = pits[cid]["metrics"]
        assert f"{m['per_stream_tok_s_median']:.1f}" in ln, (
            f"{cid}: own per-stream median missing from its bullet")
        assert f"{m['aggregate_tok_s']:.1f}" in ln, (
            f"{cid}: own aggregate missing from its bullet")
        assert "Upstream:" not in ln, f"{cid}: upstream tail still inlined"


def test_known_bad_shared_upstream_subsection_appears_exactly_once():
    block = _readme_block("known-good-bad")
    assert block.count("**Upstream tracking (shared by the") == 1, (
        "the shared upstream subsection must appear exactly once in the "
        "known-bad block")


def test_known_bad_shared_subsection_carries_the_upstream_links():
    """Single source of truth: every link and identifier in the shared
    subsection recomputes from the pit cells' own `upstream` field
    (GGUF_PIT_UPSTREAM in gen-verdicts.py) — the README summary can never
    drift from configs/benchmark-verdicts.json."""
    block = _readme_block("known-good-bad")
    shared = next(ln for ln in block.splitlines()
                  if ln.startswith("**Upstream tracking"))
    ups = {c["upstream"] for c in _pit_cells().values()}
    assert len(ups) == 1, ("greedy-pit cells no longer share one upstream "
                           "string — update the dedup contract")
    up = ups.pop()
    for link in re.findall(r"https://\S+", up):  # fix PR + both issue links
        assert link in shared, f"{link} missing from the shared subsection"
    assert re.search(r"master HEAD ([0-9a-f]+)", up).group(1) in shared, (
        "HEAD commit from the verdicts upstream field missing")
    assert "docs/results/upstream-controls/" in shared, (
        "receipts path missing from the shared subsection")
    assert all(f"#{n}" in shared for n in (25863, 25992, 23577))


def test_known_bad_names_every_avoid_cell_and_keeps_vllm_mtp16_distinct():
    """All avoid cells stay listed; the vllm mtp-c16 bullet keeps its own
    distinct cause and is NOT folded into the shared greedy-pit tracking."""
    block = _readme_block("known-good-bad")
    for cell in load(VERDICTS)["cells"]:
        if cell["verdict"] == "avoid":
            assert cell["id"] in block, f"{cell['id']} dropped from known-bad"
    m = re.search(r"- ❌ `vllm-bf16-auto-mtp-c16-ctx262144`[^\n]*", block)
    assert m, "vllm mtp-c16 avoid bullet missing"
    assert "MTP regresses" in m.group(0)
    assert "greedy" not in m.group(0), (
        "vllm mtp-c16 is a different failure — do not fold it into the "
        "shared greedy-pit upstream block")


def test_performance_highlights_says_project_ruling():
    """Jargon sweep: the generated block says 'project ruling (2026-08-17)',
    never 'controller ruling' (see also test_docs.py for the README-wide
    global assert)."""
    block = _readme_block("performance-highlights")
    assert "project ruling (2026-08-17)" in block
    assert "controller" not in block.lower()


# ------------------------------------------- 4. quickstart anti-pit mapping

def quickstart_defaults():
    """Parse the actual user-facing defaults out of the quickstart script:
    model file, ctx default, MTP opt-in."""
    src = QUICKSTART.read_text()
    gguf = re.search(r'GGUF_FILE:-([^}"]+)', src).group(1)
    ctx = re.search(r'CTX_DEFAULT="(\d+)"', src).group(1)
    mtp_opt_in = bool(re.search(r'WITH_MTP:-0', src))
    return gguf, ctx, mtp_opt_in


def parse_conf(name):
    args = {}
    for line in (ROOT / "configs" / name).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words = line.split()
        args[words[0]] = words[1] if len(words) > 1 else None
    return args


def verdict_of(cid):
    for cell in load(VERDICTS)["cells"]:
        if cell["id"] == cid:
            return cell
    raise AssertionError(f"{cid} not in verdicts")


def test_quickstart_configs_are_recommended():
    """The UX guarantee, working as designed.

    CONTROLLER RULING (2026-08-17, binding): all 8 measured vLLM cells are
    below the 10 tok/s interactive floor, so the vLLM c1 cells are `caution`
    WITH non-empty conditions — "per-stream < 10 tok/s on this host: use for
    262144-context, vision, and aggregate batch throughput (to 38.6 tok/s),
    and as the greedy-degradation-free path; interactive chat -> GGUF path
    (mtp-c1 13.0 tok/s)". The GGUF quickstart defaults (and the WITH_MTP
    opt-in) are the recommended interactive configs. If a future measurement
    invalidates this mapping, this test FAILS and the controller must change
    the quickstart default or record a justified new ruling.

    CONTROLLER RULING (2026-08-18, binding, v0.1.2): `BACKEND=vulkan` is the
    recommended OPT-IN for best single-stream tok/s — the opt-in cell must
    be recommended AND anchor-clean, while the default-boot cells stay hip
    (the script's BACKEND default is pinned by test_gguf_quickstart_ux.py).
    """
    gguf, ctx, mtp_opt_in = quickstart_defaults()
    assert "UD-Q4_K_XL" in gguf, "quickstart default must stay the validated quant"
    assert ctx == "131072", "quickstart default ctx must stay the validated 131072"
    assert mtp_opt_in, "MTP must stay opt-in in the quickstart"

    # quickstart default boot -> gguf base c1 @131072 must be recommended.
    cell = verdict_of("gguf-hip-udq4kxl-auto-base-c1-ctx131072")
    assert cell["verdict"] == "recommended"

    # WITH_MTP=1 -> gguf mtp c1 @131072 must be recommended (13.0 tok/s).
    cell = verdict_of("gguf-hip-udq4kxl-auto-mtp-c1-ctx131072")
    assert cell["verdict"] == "recommended"
    assert cell["metrics"]["per_stream_tok_s_median"] > 13.0 - 0.05

    # BACKEND=vulkan + WITH_MTP=1 (the 2026-08-18 recommended opt-in) ->
    # the vulkan mtp c1 cell must be recommended and anchor-clean, and must
    # beat the hip default recommendation it is promoted against.
    vk = verdict_of("gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072")
    assert vk["verdict"] == "recommended"
    assert vk["metrics"]["anchor_ok"], (
        "the promoted opt-in must be anchor-clean (ruling trigger)")
    assert (vk["metrics"]["per_stream_tok_s_median"]
            > cell["metrics"]["per_stream_tok_s_median"])

    # vLLM serve confs -> the validated 262144 cells: caution WITH conditions
    # (the ruling above); never a bare pass, never avoid (the path is the
    # 262144/vision/batch path).
    base_conf = parse_conf("serve-args.conf")
    assert base_conf["--max-model-len"] == "262144"
    cell = verdict_of("vllm-bf16-auto-base-c1-ctx262144")
    assert cell["verdict"] == "caution"
    assert cell.get("conditions", "").strip(), (
        "the ruling requires non-empty conditions on the vllm c1 cells")
    assert "GGUF" in cell["conditions"] or "gguf" in cell["conditions"]

    mtp_conf = parse_conf("serve-args-mtp.conf")
    num_spec = re.search(r'"num_speculative_tokens":(\d+)',
                         mtp_conf["--speculative-config"]).group(1)
    assert num_spec == "1"
    cell = verdict_of("vllm-bf16-auto-mtp-c1-ctx262144")
    assert cell["verdict"] == "caution"
    assert cell.get("conditions", "").strip()


def test_no_quickstart_referenced_config_is_avoid():
    # 2026-08-18: the promoted BACKEND=vulkan opt-in joins the protected
    # set — the recommended opt-in path must never be a pit/avoid cell.
    for cid in ("gguf-hip-udq4kxl-auto-base-c1-ctx131072",
                "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072",
                "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072",
                "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072",
                "vllm-bf16-auto-base-c1-ctx262144",
                "vllm-bf16-auto-mtp-c1-ctx262144"):
        assert verdict_of(cid)["verdict"] != "avoid", (
            f"{cid}: a quickstart/serve-default config must never be a pit")


def test_readme_interactive_guidance_points_at_gguf():
    """Per the same ruling: README quickstart/interactive guidance points at
    the GGUF path, with the vLLM path framed for its actual wins."""
    text = README.read_text()
    m = re.search(r"## Quick start.*?(?=\n## )", text, re.S)
    assert m, "README needs a Quick start section"
    section = m.group(0)
    assert "gguf-quickstart.sh" in section
    assert "WITH_MTP=1" in section
    # The GGUF path is the interactive recommendation; vLLM appears only with
    # its batch/context/vision framing, not as the interactive default.
    assert re.search(r"[Ii]nteractive", section)
    assert "262144" in section or "vLLM" in section


def test_benchmark_md_links_raw_cells_and_lists_every_verdict():
    text = BENCH_MD.read_text()
    v = load(VERDICTS)
    for cell in v["cells"]:
        assert cell["id"] in text, f"benchmark.md missing {cell['id']}"
    assert "cells/" in text  # links to the raw receipts
    assert str(len(v["cells"])) in text  # headline count


# ------------------- 5. 2026-08-18 backend-dimension id migration (v0.1.2)
#
# gguf ids gained an explicit backend tag (legacy unprefixed == hip); the
# migration must lose nothing: verdict CONTENT stays byte-stable modulo the
# id string, every live id-naming surface carries the tag, and the tables
# that will mix hip/vulkan rows render a Backend column derived from the id.

LEGACY_ID_RE = re.compile(r"gguf-udq4kxl-auto-")


def migrated(cid: str) -> str:
    """LEGACY->NEW mapping baked into the 2026-08-18 migration."""
    return LEGACY_ID_RE.sub("gguf-hip-udq4kxl-auto-", cid, count=1)


def test_no_legacy_unprefixed_gguf_ids_on_migrated_surfaces():
    """Migration completeness. Deliberately OUT of scope (immutable history,
    kept by design): CHANGELOG v0.1.0/v0.1.1 entries (interpreted via the
    v0.1.2 migration note), docs/results receipts produced under the old
    ids (upstream-controls/, community/ cells — the community namespace has
    its own grammar), and spike docs."""
    for name, path in (("matrix.json", MATRIX),
                       ("benchmark-verdicts.json", VERDICTS),
                       ("README.md", README),
                       ("benchmark.md", BENCH_MD)):
        assert not LEGACY_ID_RE.search(path.read_text()), (
            f"{name} still carries legacy unprefixed gguf ids")
    for p in CELLS_DIR.glob("*.json"):
        assert not LEGACY_ID_RE.search(p.name), (
            f"cells/{p.name} not renamed (filename == id invariant)")


def test_verdict_content_is_byte_stable_modulo_the_id_migration():
    """The 2026-08-18 migration changed ids ONLY: every verdict from the
    pre-migration commit must survive byte-identically (verdict, reason,
    conditions, workaround, upstream, metrics) under its mapped id.

    Updated 2026-08-18 (Task 3, raw receipts): the 8 measured v0.1.2 cells
    legitimately ADD verdicts on top of the migrated set — the byte-stable
    guarantee applies to the pre-migration survivors, and the additions must
    be exactly the declared v0.1.2 cells."""
    old = subprocess.run(
        ["git", "show", "f67ddc6:configs/benchmark-verdicts.json"],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    if old.returncode != 0:
        pytest.skip("pre-migration commit f67ddc6 not in this clone")
    old_cells = {c["id"]: c for c in json.loads(old.stdout)["cells"]}
    new_cells = {c["id"]: c for c in load(VERDICTS)["cells"]}
    migrated_ids = {migrated(i) for i in old_cells}
    assert migrated_ids <= set(new_cells), (
        "the verdict id set lost migrated pre-commit ids")
    t3_additions = {
        "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072",
        "gguf-vulkan-udq4kxl-auto-base-c4-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp-c4-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp4-c4-ctx131072",
        "gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified",
    }
    assert set(new_cells) - migrated_ids == t3_additions, (
        "beyond the migrated pre-commit set, only the measured v0.1.2 "
        "cells may carry verdicts")
    # Task 4 (2026-08-18) controller-review prose corrections — the ONLY
    # permitted content drift beyond the id migration on the pre-commit
    # cells. Verdict and every metric stay byte-stable; only the
    # reason/conditions PROSE changed (dated and explained in
    # scripts/gen-verdicts.py): the unified-c4 caveat was rewritten because
    # the v0.1.2 rider measured that configuration, and the c4-caution MTP
    # sentence was corrected to follow the actual numbers/basis.
    t4_prose_corrected = {
        "gguf-hip-udq4kxl-auto-base-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-mtp-c4-ctx131072",
    }
    for old_id, old_cell in sorted(old_cells.items()):
        new_id = migrated(old_id)
        migrated_cell = dict(new_cells[new_id])
        expected = dict(old_cell)
        assert migrated_cell.pop("id") == new_id
        assert expected.pop("id") == old_id
        if new_id in t4_prose_corrected:
            assert migrated_cell["verdict"] == expected["verdict"], (
                f"{new_id}: prose correction must never change the verdict")
            assert migrated_cell["metrics"] == expected["metrics"], (
                f"{new_id}: prose correction must never change metrics")
            assert migrated_cell.get("upstream") == expected.get("upstream")
            assert migrated_cell.get("workaround") == expected.get("workaround")
            continue
        assert migrated_cell == expected, (
            f"{new_id}: content drifted beyond the id string during the "
            f"migration")


def test_measured_matrix_cells_and_verdicts_survived_the_migration():
    """The measured cells (5 degraded) keep their statuses and degraded
    notes under the migrated ids; verdict coverage stays exact. Updated
    2026-08-18 (Task 3): 20 migration survivors + the 8 measured v0.1.2
    Vulkan×MTP/unified cells = 28 (the new cells are all non-degraded)."""
    m = load(MATRIX)
    measured = {c["id"] for c in m["cells"] if c["status"] == "measured"}
    assert len(measured) == 28
    degraded = {c["id"] for c in m["cells"] if c["status"] == "measured"
                and c.get("degraded")}
    assert len(degraded) == 5
    verdicted = {c["id"] for c in load(VERDICTS)["cells"]}
    assert verdicted == measured


def test_benchmark_tables_render_a_backend_column_from_ids():
    """Backend dimension: the tables that mix hip/vulkan rows carry a
    Backend column derived from the cell id (updated 2026-08-18, Task 3:
    measured gguf rows now span both backends — the column must track the
    id, whichever backends are measured)."""
    text = BENCH_MD.read_text()
    assert "| Cell | Backend | Verdict |" in text, (
        "benchmark.md GGUF table lacks the Backend column")
    assert "| Config | Backend |" in text, (
        "benchmark.md MTP-effect table lacks the Backend column")
    readme = README.read_text()
    assert "| Config | Backend | Per-stream (median) |" in readme, (
        "README performance highlights lack the Backend column")
    # Values come from the ids: every measured gguf row states its backend.
    for cid in sorted(c["id"] for c in load(VERDICTS)["cells"]
                      if c["id"].startswith("gguf-")):
        backend = cid.split("-")[1]
        row = re.search(rf"\| \[`{re.escape(cid)}`\]\([^)]*\) \| (\w+) \|", text)
        assert row, f"benchmark.md has no row link for {cid}"
        assert row.group(1) == backend, (
            f"{cid}: Backend column must derive from the id")
        assert f"| {backend} |" in text


def test_declared_v012_cells_are_measured_and_verdicted():
    """Updated 2026-08-18 (Task 3): the 8 v0.1.2 cells are now MEASURED
    (raw receipts committed) and carry ladder verdicts — and the receipts
    must state honestly what booted: the id's backend tag, the mtp part's
    explicit spec depth, and unified slots only on the -unified rider."""
    m = load(MATRIX)
    new_ids = {
        "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072",
        "gguf-vulkan-udq4kxl-auto-base-c4-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp-c4-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp4-c4-ctx131072",
        "gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified",
    }
    by_id = {c["id"]: c for c in m["cells"]}
    assert set(by_id) >= new_ids
    for cid in sorted(new_ids):
        assert by_id[cid]["status"] == "measured", f"{cid} must be measured"
        assert not by_id[cid].get("degraded"), f"{cid} must not be degraded"
        assert "reason" not in by_id[cid], (
            f"{cid}: a measured non-degraded cell carries no planned-reason")
    verdicted = {c["id"] for c in load(VERDICTS)["cells"]}
    assert verdicted >= new_ids, "the measured v0.1.2 cells must be verdicted"
    # Receipt honesty: server_flags must agree with the id grammar.
    depth_by_part = {"base": None, "mtp": 1, "mtp4": 4}
    for cid in sorted(new_ids):
        cell = json.loads((CELLS_DIR / f"{cid}.json").read_text(encoding="utf-8"))
        sf = cell["server_flags"]
        part = cid.split("-")[4]
        assert sf["backend"] == cid.split("-")[1], f"{cid}: backend mismatch"
        assert sf["mtp_part"] == part, f"{cid}: mtp part mismatch"
        assert sf["spec_depth"] == depth_by_part[part], (
            f"{cid}: spec_depth {sf['spec_depth']} != grammar depth")
        assert sf["slots"] == ("unified-rider" if cid.endswith("-unified")
                               else "default"), f"{cid}: slots mismatch"


# ------------------- 6. v0.1.2 controller ruling (2026-08-18) — the mapping
#
# Plan outcome (a), the pre-registered rule triggered (>=15% win over hip
# mtp-c1 AND anchor-clean): `BACKEND=vulkan` is promoted in the quickstart
# echo as the recommended OPT-IN; the quickstart DEFAULT stays hip; mtp
# (depth 1) stays the recommended variant on both backends; the unified
# rider is measured-with-caveat. Recorded per cell — metrics.reviewed_by
# plus the ruling prose in each reason (the frozen 2026-08-17 review keeps
# governing the 20 migrated cells, which carry no per-cell field).

V012_IDS = {
    "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-base-c4-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp-c4-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp4-c4-ctx131072",
    "gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072",
    "gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified",
}


def test_v012_cells_have_verdicts_and_the_ruling_recorded():
    v = load(VERDICTS)
    by_id = {c["id"]: c for c in v["cells"]}
    assert V012_IDS <= set(by_id), "the 8 v0.1.2 cells must all carry verdicts"
    for cid in sorted(V012_IDS):
        cell = by_id[cid]
        # Review trail: per-cell reviewer of record; the MECHANICAL verdict
        # was confirmed (no override — the ruling notes live in the reason).
        assert cell["metrics"].get("reviewed_by") == "controller-2026-08-18", (
            f"{cid}: missing the 2026-08-18 per-cell review record")
        assert cell["metrics"]["controller_override"] is None, (
            f"{cid}: v0.1.2 cells are rule-correct, zero overrides")
        assert "2026-08-18" in cell["reason"], (
            f"{cid}: the ruling/review note is missing from the reason")
    # Corpus attribution: the 2026-08-18 review produced this file state;
    # exactly the 8 v0.1.2 cells carry a per-cell reviewed_by (the 20
    # migrated cells stay governed by the frozen 2026-08-17 review).
    assert v["reviewed_by"] == "controller-2026-08-18"
    per_cell = [c for c in v["cells"] if c["metrics"].get("reviewed_by")]
    assert len(per_cell) == 8


def test_ruling_vulkan_optin_trigger_and_default_stays_hip():
    """The ruling is justified by the receipts AND recorded where it binds:
    >=15% single-stream win, anchor-clean, quickstart opt-in promoted,
    default hip unchanged, cross-depth caveat stated with the clean
    same-depth pairing. Updated 2026-08-18 (v0.1.3, S2): the
    'single-session' caveat is upgraded to the two-session + soak wording
    with the evidence pointer — the default-stays-hip rationale now cites
    the flip-rule arithmetic, not a single-session limitation."""
    by_id = {c["id"]: c for c in load(VERDICTS)["cells"]}
    vk = by_id["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]
    hip = by_id["gguf-hip-udq4kxl-auto-mtp-c1-ctx131072"]
    # Trigger: >=15% win AND anchor-clean (plan outcome (a)).
    assert (vk["metrics"]["per_stream_tok_s_median"]
            >= 1.15 * hip["metrics"]["per_stream_tok_s_median"]), (
        "the opt-in promotion requires the >=15% trigger")
    assert vk["metrics"]["anchor_ok"]
    assert vk["verdict"] == "recommended"
    # The recorded rationale on the promoted cell.
    r = vk["reason"]
    assert "recommended OPT-IN" in r
    assert "DEFAULT stays hip" in r
    assert "two independent measurement sessions" in r
    assert "docs/results/matrix-714/stability/" in r
    assert "RADV 25.2.8" in r
    assert "single-session" not in r
    assert "MIXED-DEPTH" in r and "implicit --spec-draft-n-max default 3" in r
    assert "depth 4" in r and "explicit depth 4" in r  # same-depth pairing
    # The quickstart binds: opt-in promoted in the echo, DEFAULT unchanged.
    src = QUICKSTART.read_text()
    assert 'BACKEND="${BACKEND:-hip}"' in src, "default must stay hip"
    assert "RECOMMENDED OPT-IN" in src
    assert "BACKEND=vulkan WITH_MTP=1" in src
    assert "16.0" in src


def test_ruling_no_flip_arithmetic_recorded_v013():
    """v0.1.3 (S2): the two-session evidence upgraded the WORDING but did
    NOT flip the default — and the arithmetic is recorded in the ruling
    note so the session-2 headline (+25.0% exactly) is never misread as
    the >25% flip trigger. The session-2/soak numbers interpolate from the
    committed receipts via gen-verdicts.stability_evidence() (receipts-only:
    they never enter the 28-cell matrix)."""
    ev = gv.stability_evidence()
    assert ev, ("stability receipts failed to load from "
                "docs/results/matrix-714/stability/")
    by_id = {c["id"]: c for c in load(VERDICTS)["cells"]}
    hip_mtp1 = by_id["gguf-hip-udq4kxl-auto-mtp-c1-ctx131072"][
        "metrics"]["per_stream_tok_s_median"]
    hip_mtp4 = by_id["gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072"][
        "metrics"]["per_stream_tok_s_median"]
    m1 = ev["cells"]["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]
    m4 = ev["cells"]["gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072"]
    # The headline arithmetic itself, at the corpus 2dp convention:
    # 16.25 vs 13.00 is EXACTLY +25.0% — i.e. NOT > 25% (the flip rule).
    assert m1["s2_2dp"] == 16.25 and hip_mtp1 == 13.0
    headline2 = (m1["s2_2dp"] / hip_mtp1 - 1) * 100
    assert round(headline2, 1) == 25.0, (
        f"session-2 headline must be exactly +25.0%, got {headline2:+.1f}%")
    assert not headline2 > 25.0, "exactly +25.0% must never read as >25%"
    # The clean same-depth d4 pairing: 15.25 vs 12.76 = +19.5%.
    assert m4["s2_2dp"] == 15.25 and hip_mtp4 == 12.76
    assert round((m4["s2_2dp"] / hip_mtp4 - 1) * 100, 1) == 19.5
    # Session-2 reproduction deltas (exact-receipt basis): +1.5/+1.3/+2.5%.
    assert m1["delta_pct"] == "+1.5%"
    assert m4["delta_pct"] == "+1.3%"
    assert ev["cells"]["gguf-vulkan-udq4kxl-auto-base-c1-ctx131072"][
        "delta_pct"] == "+2.5%"
    # The soak stats the wording quotes: 108 cycles, -2.6% settle.
    assert ev["soak"]["cycles"] == 108 and ev["soak"]["ok_cycles"] == 108
    assert ev["soak"]["settle_pct"] == -2.6
    # All of it is recorded in the promoted cell's ruling note...
    r = by_id["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["reason"]
    assert "exactly +25.0%" in r and "NOT >25%" in r
    assert ">25% AND stability" in r
    assert "MIXED-DEPTH" in r  # the caveat the headline still carries
    assert "+19.5%" in r and "15.25 vs 12.76" in r
    assert "108 cycles, -2.6% settle" in r
    # ...and the default is still hip everywhere the quickstart binds.
    assert 'BACKEND="${BACKEND:-hip}"' in QUICKSTART.read_text()
    # The generated surfaces carry the two-session wording, never the old
    # "single-session" caveat.
    for surface in (BENCH_MD, README):
        text = surface.read_text()
        assert "single-session" not in text, (
            f"{surface.name}: stale single-session caveat survived")
        if surface is BENCH_MD:
            assert "two independent measurement sessions" in text
            assert "exactly +25.0%" in text


def test_ruling_mtp_depth1_beats_depth4_on_both_backends():
    """The recommendation mapping extends to depth: depth 4 never beats
    depth 1 on either backend, so mtp (depth 1) stays the recommended
    variant and nothing promotes mtp4."""
    by_id = {c["id"]: c for c in load(VERDICTS)["cells"]}
    for backend in ("hip", "vulkan"):
        mtp = by_id[f"gguf-{backend}-udq4kxl-auto-mtp-c1-ctx131072"]
        mtp4 = by_id[f"gguf-{backend}-udq4kxl-auto-mtp4-c1-ctx131072"]
        assert mtp["verdict"] == "recommended"
        assert mtp4["verdict"] == "recommended"  # clean, just not preferred
        assert (mtp4["metrics"]["per_stream_tok_s_median"]
                < mtp["metrics"]["per_stream_tok_s_median"]), (
            f"{backend}: depth 4 must never beat depth 1 (no mtp4 rec)")
        assert "no mtp4 recommendation" in mtp4["reason"]
    # The quickstart promotes no depth-4 path.
    assert "mtp4" not in QUICKSTART.read_text()


def test_ruling_unified_rider_finding_recorded():
    by_id = {c["id"]: c for c in load(VERDICTS)["cells"]}
    rider = by_id["gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified"]
    split = by_id["gguf-hip-udq4kxl-auto-base-c4-ctx131072"]
    assert rider["verdict"] == "caution"
    assert "DEGRADES interactivity" in rider["reason"]
    assert rider["metrics"]["per_stream_tok_s_median"] < split[
        "metrics"]["per_stream_tok_s_median"], "unified must not beat split"
    assert "early EOS" in rider["reason"]
    assert "not measured" not in rider["reason"].replace(
        "'unified-default-boot c4@131072 not measured'", "")
    # The quickstart c1 caveat cells now cite the MEASURED rider (the old
    # "was NOT measured" bracketing caveat is gone everywhere).
    for cid in ("gguf-hip-udq4kxl-auto-base-c1-ctx131072",
                "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072"):
        cond = by_id[cid].get("conditions", "")
        assert "was NOT measured" not in cond, (
            f"{cid}: stale unmeasured-caveat wording survived")
        assert "measured 2026-08-18" in cond
        assert "degrades interactivity" in cond


# --------------------- 7. 2026-08-18 template-defect fixes stay fixed

def test_vulkan_verdict_text_never_claims_the_hip_pit():
    """Defect fix: the 'c8/c16 hit the anchor-degradation pit (avoid
    cells)' clause is hip-family history — no vulkan cell may carry it
    (no vulkan c8/c16 cells exist; the pit does not reproduce there)."""
    for cell in load(VERDICTS)["cells"]:
        if not cell["id"].startswith("gguf-vulkan-"):
            continue
        blob = cell["reason"] + cell.get("conditions", "")
        assert "hit the anchor-degradation pit" not in blob, (
            f"{cell['id']}: hip pit clause leaked into a vulkan verdict")
        if "pit" in blob:
            assert "does not reproduce" in blob, (
                f"{cell['id']}: mentions the pit without the "
                f"non-reproduction finding")


def test_caution_mtp_sentence_follows_the_actual_numbers():
    """Defect fix: the c4-caution MTP sentence must state direction and
    basis from the actual gains (never a hardcoded 'Better than base c4',
    never a 'c1:' tag on a c4-basis number)."""
    for cell in load(VERDICTS)["cells"]:
        if not cell["id"].startswith("gguf-"):
            continue  # the defect was in the GGUF c4-caution template
        g = cell["metrics"].get("mtp_gain_vs_base")
        if not g or cell["verdict"] != "caution":
            continue
        c = cell["metrics"]["c"]
        # The template-generated portion only (the 2026-08-18 review note
        # legitimately QUOTES the old defective wording it corrected).
        r = cell["reason"].split(" Controller review 2026-08-18")[0]
        assert "Better than base" not in r, (
            f"{cell['id']}: hardcoded direction is back")
        assert f"base c{c}" in r, (
            f"{cell['id']}: the aggregate comparison must name its "
            f"same-concurrency basis")
        assert "(c1: " not in r, (
            f"{cell['id']}: mislabeled c1 basis is back")
        # The stated direction matches the sign of the measured gains.
        if g["aggregate_pct"] > 0:
            assert "Above the base c" in r
        else:
            assert "Above the base c" not in r, (
                f"{cell['id']}: says 'Above base' on a regressing cell")
