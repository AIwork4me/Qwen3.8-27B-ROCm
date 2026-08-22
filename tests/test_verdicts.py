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
   since the controller ruling of 2026-08-19 (v0.1.4, SUPERSEDING the
   2026-08-18 promotion on the clean d1 pairing), the BACKEND=vulkan
   opt-in maps to an anchor-clean recommended CELL while being presented
   as an AVAILABLE experimental opt-in, NOT a recommendation; the default
   stays hip and hip WITH_MTP=1 is the recommended path. If a future
   measurement changes that, this test fails and the controller must
   either change the quickstart mapping or record a new justified ruling.
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

    CONTROLLER RULING (2026-08-19, binding, v0.1.4 — SUPERSEDES the
    2026-08-18 promotion): hip WITH_MTP=1 is BOTH the default backend's
    recommended path AND the quickstart recommendation; `BACKEND=vulkan`
    remains an available EXPERIMENTAL opt-in — its CELL verdict stays
    `recommended` (mechanical, unchanged, anchor-clean), but the quickstart
    must NOT recommend it (the clean d1 pairing is +4.81%, aggregate
    −13.31%; the 2026-08-18 promotion basis was mixed-depth).
    """
    gguf, ctx, mtp_opt_in = quickstart_defaults()
    assert "UD-Q4_K_XL" in gguf, "quickstart default must stay the validated quant"
    assert ctx == "131072", "quickstart default ctx must stay the validated 131072"
    assert mtp_opt_in, "MTP must stay opt-in in the quickstart"

    # quickstart default boot -> gguf base c1 @131072 must be recommended.
    cell = verdict_of("gguf-hip-udq4kxl-auto-base-c1-ctx131072")
    assert cell["verdict"] == "recommended"

    # WITH_MTP=1 -> gguf mtp c1 @131072 must be recommended (13.0 tok/s) —
    # the recommended path on the (hip) default backend.
    cell = verdict_of("gguf-hip-udq4kxl-auto-mtp-c1-ctx131072")
    assert cell["verdict"] == "recommended"
    assert cell["metrics"]["per_stream_tok_s_median"] > 13.0 - 0.05
    src = QUICKSTART.read_text()
    assert "default AND recommended path" in src, (
        "the quickstart echo must name hip WITH_MTP=1 as the recommended "
        "path (ruling 2026-08-19)")

    # BACKEND=vulkan + WITH_MTP=1 -> the cell keeps its MECHANICAL verdict
    # (recommended, anchor-clean), but the quickstart maps it as an
    # AVAILABLE experimental opt-in, NOT a recommendation.
    vk = verdict_of("gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072")
    assert vk["verdict"] == "recommended"  # mechanical — unchanged by v0.1.4
    assert vk["metrics"]["anchor_ok"], (
        "the opt-in cell is anchor-clean (the pit does not reproduce on "
        "vulkan — that finding stands)")
    assert "AVAILABLE experimental opt-in" in src
    assert "NOT recommended" in src
    assert "RECOMMENDED OPT-IN" not in src and \
        "recommended OPT-IN" not in src, (
            "the 2026-08-18 promotion wording must be gone from the "
            "quickstart (superseded 2026-08-19)")
    assert "2026-08-19" in src and "2026-08-18" in src, (
        "both ruling dates stay visible in the quickstart (dated "
        "supersession, not a silent rewrite)")

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


def test_no_flip_closed_on_the_clean_pairing_arithmetic_v014():
    """v0.1.4 (S5): the no-flip question is closed DECISIVELY on the clean
    basis — the pre-registered flip rule needs >25%, and the clean d1/d1
    pairing gap is +4.81% (exact basis from the session-3 receipts). The
    arithmetic is recomputed here from stability_evidence() so the pinned
    strings can never drift from the receipts."""
    ev = gv.stability_evidence()
    cp = ev["clean_pairing"]
    assert cp["date"] == "2026-08-19"
    assert cp["vk_2dp"] == 14.53 and cp["hip_2dp"] == 13.86
    assert cp["gap_2dp"] == 0.67
    # Exact-basis: (vk/hip - 1) * 100 rounds to +4.81 at 2dp — and is
    # nowhere near the >25% flip threshold.
    gap_pct = (cp["vk"] / cp["hip"] - 1) * 100
    assert round(gap_pct, 2) == 4.81, (
        f"clean-pairing gap must be +4.81% (exact basis), got {gap_pct:+.4f}%")
    assert 4.81 < 25.0, "+4.81% << 25% — no-flip closed on the clean basis"
    assert cp["pct_2dp"] == "+4.81%"
    # The aggregate basis flips to −13.31% (hip leads).
    assert cp["vk_agg_2dp"] == 9.31 and cp["hip_agg_2dp"] == 10.74
    assert cp["agg_pct_2dp"] == "-13.31%"
    # The cross-day variance the ruling cites (3 cells × spreads).
    cd = ev["crossday"]
    assert cd["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"] == {
        "vs_s1_pct": "-9.21%", "vs_s2_pct": "-10.56%", "spread_pct": 11.81}
    assert cd["gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072"] == {
        "vs_s1_pct": "-22.49%", "vs_s2_pct": "-23.49%", "spread_pct": 30.70}
    assert cd["gguf-vulkan-udq4kxl-auto-base-c1-ctx131072"] == {
        "vs_s1_pct": "-3.35%", "vs_s2_pct": "-5.72%", "spread_pct": 6.07}
    # Hip: same-session stable; the d1-vs-implicit-d3 delta is labeled
    # day-confounded, never a depth claim.
    hip = ev["session3"]["hip_mtp1"]
    assert hip["s3_2dp"] == 13.86 and hip["corpus_2dp"] == 13.00
    assert hip["corpus_delta_pct"] == "+6.61%"
    # The TTFT observation behind the aggregate flip.
    assert ev["ttft"]["vk_s3_range"] == (9.94, 12.21)
    assert ev["ttft"]["vk_s12_range"] == (8.36, 8.83)
    assert ev["ttft"]["hip_s3_2dp"] == 5.43 and ev["ttft"]["hip_corpus_2dp"] == 5.47
    # The cross-session anchor tally (the pit non-reproduction stands);
    # extended v0.1.6 to the five session-4 runs and v0.1.7 to the four
    # session-5/6 runs.
    assert ev["anchors"] == {"cell_runs_ok": 19, "cell_runs_total": 19,
                             "with_soak_ok": 20, "with_soak_total": 20}


# --------------------- 6c. v0.1.6 R2 — the cache-state root-cause arithmetic
#
# Session 4 (2026-08-19, R1 telemetry harness) root-causes the v0.1.4
# cross-day variance: Mesa shader-cache state dependence. Every pinned
# number below recomputes from the session-4 receipts through
# stability_evidence() — cold/warm bounds, the +38% swing, the floor-case
# consistency (s3 between cold and warm), the warm boot-paired ceiling
# pairings, and the near-deterministic hip controls.

def test_cache_state_arithmetic_v016():
    ev = gv.stability_evidence()
    s4 = ev["session4"]
    assert s4["date"] == "2026-08-19"
    # Warm vulkan boots and their cross-boot delta (exact basis, 2dp).
    assert s4["vk_boot1_2dp"] == 17.10 and s4["vk_boot2_2dp"] == 16.96
    assert s4["vk_crossboot_pct_2dp"] == "-0.79%"
    assert s4["warm_mean_2dp"] == 17.03
    assert s4["warm_ttft_range"] == (8.37, 8.50)
    # Hip controls: near-deterministic within ±5%.
    assert s4["hip_ctrl1_2dp"] == 14.76 and s4["hip_ctrl2_2dp"] == 14.06
    assert s4["hip_crossboot_pct_1dp"] == "-4.7%"
    # Cold (cache-aside arm) vs warm: the bounds and the swing.
    assert s4["aside_2dp"] == 12.38 and s4["aside_ttft_s_2dp"] == 12.45
    assert s4["aside_vs_warm_pct_1dp"] == "-27.3%"
    assert s4["swing_pct_0dp"] == "+38%"
    swing = (s4["warm_mean"] / s4["aside"] - 1) * 100
    assert round(swing) == 38, (
        f"cold->warm swing must round to +38% (exact {swing:+.2f}%)")
    # FLOOR-CASE consistency: s3's 14.53 sits between cold and warm.
    s3vk = ev["session3"]["cells"][
        "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["s3_2dp"]
    assert s4["aside_2dp"] < s3vk < s4["warm_mean_2dp"], (
        "s3 must sit between cold and warm for the partial-cold reading")
    # The cache receipts behind the state labels.
    assert s4["cache"] == {"warm_du_kib": 7884, "warm_files": 867,
                           "aside_built_du_kib": 2136,
                           "aside_built_files": 100}
    # CEILING context: warm-cache, boot-paired, same-day pairings.
    wp = s4["warm_pairings"]
    assert wp["label"] == "warm-cache, boot-paired"
    assert wp["date"] == "2026-08-19"
    assert wp["boot1_pct_1dp"] == "+15.9%" and wp["boot2_pct_1dp"] == "+20.6%"
    assert round((wp["boot1"][0] / wp["boot1"][1] - 1) * 100, 1) == 15.9
    assert round((wp["boot2"][0] / wp["boot2"][1] - 1) * 100, 1) == 20.6
    # The warm pairings are ceiling context, NOT a flip trigger: both are
    # below the >25% pre-registered threshold, and they come from a single
    # warm session.
    assert 15.9 < 25.0 and 20.6 < 25.0
    # Telemetry envelopes: no thermal/power anomaly (each backend in its
    # own normal envelope); hip temp prints once, never '58–58'.
    t = s4["telemetry"]
    assert t["vk_post_sclk_range"] == (1433.0, 1533.0)
    assert t["vk_post_power_range"] == (30.043, 32.001)
    assert t["vk_post_temp_range"] == (54.0, 57.0)
    assert t["hip_post_sclk_range"] == (1910.0, 1929.0)
    assert t["hip_post_power_range"] == (52.066, 53.048)
    assert t["hip_post_temp_range"] == (58.0, 58.0)
    # Host state: one common boot since 2026-08-12 across all five runs —
    # the "no reboot" leg of the trigger-unknown statement.
    assert s4["host_boot_time"] == "2026-08-12 09:42:40"
    assert s4["anchors_ok"] == 5 and s4["anchors_total"] == 5
    assert all(v["anchor_ok"] for v in s4["runs"].values())
    # The ruling note quotes these bounds; the mapping does NOT move.
    r = {c["id"]: c for c in load(VERDICTS)["cells"]}[
        "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["reason"]
    for fragment in ("12.38", "17.10/16.96", "+38%", "-27.3%",
                     "+15.9%", "+20.6%", "RECOMMENDATION UNCHANGED"):
        assert fragment in r, f"ruling note lost the R2 fragment {fragment!r}"


def test_cache_state_story_on_user_facing_surfaces_v016():
    """Ruling 3 + 4: the warmup guidance line is in the quickstart echo and
    adaptation; the OPEN re-recommendation question is in the README
    roadmap with the warm/cold numbers; the recommendation language is
    unchanged everywhere (vulkan NOT recommended, hip recommended).
    v0.1.7: the cache-state CLASS story stays (it is still the root-cause
    class and the cold-cache arm is still the swing bound), but the s3
    partial-cold READING is superseded — both texts stay visible with
    markers, and the refined decomposition (band/overnight/drift/
    hip-favored aggregate) is present."""
    src = QUICKSTART.read_text()
    assert "warmup note" in src and "re-run before concluding" in src, (
        "the quickstart vulkan echo must carry the one-line warmup guidance")
    assert "cold Mesa shader cache" in src
    assert "~12.4 tok/s" in src and "~12.5 s TTFT" in src
    assert "status above is unchanged" in src
    # Boot logic untouched by the echo change.
    assert 'BACKEND="${BACKEND:-hip}"' in src
    adaptation = (ROOT / "docs" / "adaptation.md").read_text()
    assert "Mesa shader-cache state" in adaptation
    assert "root-cause CLASS v0.1.6" in adaptation
    for number in ("12.38", "14.53", "16.96–17.10", "16.00–16.25", "+38%"):
        assert number in adaptation, (
            f"adaptation.md warm/cold table lost {number}")
    # BOTH texts visible with supersession markers (v0.1.7): the v0.1.6
    # partial-cold wording stays as history, retired by the forensics.
    assert "TRIGGER is UNKNOWN" in adaptation, (
        "the superseded v0.1.6 sentence must stay visible, marked")
    assert "partial-cold" in adaptation and "retires that reading" in adaptation
    assert "forensically INTACT" in adaptation
    assert "trigger UNIDENTIFIED" in adaptation
    # The warm/cold table gained the s5/s6 rows; the refined decomposition
    # parts are all present.
    for fragment in ("16.25 | 8.49", "16.41 | 8.54", "+15.88 / +20.61",
                     "+19.90 / +15.93", "7 h 50 m", "byte-identical",
                     "±5–6%", "hip-favored", "no mechanism"):
        assert fragment in adaptation, (
            f"adaptation.md v0.1.7 decomposition lost {fragment!r}")
    assert "first-run cache warmup is the first suspect" in adaptation
    assert "conservative floor case" in adaptation.lower()
    readme = README.read_text()
    # v0.1.8: the OPEN question is closed — DECIDED 2026-08-20: NO.
    assert ("Re-recommend `BACKEND=vulkan`? — DECIDED 2026-08-20: NO"
            in readme), (
        "the roadmap decision entry (DECIDED 2026-08-20: NO) is missing")
    assert "OPEN decision for the repository" not in readme, (
        "the roadmap must no longer present the question as OPEN")
    # No recommendation drift on any surface: vulkan stays NOT recommended
    # (benchmark.md words it "NO recommendation").
    assert "NOT recommended" in readme
    assert "NO recommendation" in BENCH_MD.read_text()


# -------------- 6d. v0.1.7 H2 — trigger-hunt + overnight-series arithmetic
#
# The trigger-hunt forensics retire the v0.1.6 "s3 partial-cold" reading
# (supersession #3) and the session-5/6 series strengthens the warm band.
# Every pinned number below recomputes from the receipts through
# stability_evidence(): the s5/s6 pairings, the 4-session band, the
# overnight-persistence facts (gap + cache byte-identity on the s6 vk
# receipt), the common-mode drift deltas, and the ruling-note fragments.

def test_trigger_hunt_overnight_series_arithmetic_v017():
    ev = gv.stability_evidence()
    # Session 5 (2026-08-19 evening): the warm pair.
    s5 = ev["session5"]
    assert s5["date"] == "2026-08-19" and s5["when"] == "evening"
    assert s5["vk_2dp"] == 16.25 and s5["hip_2dp"] == 13.55
    assert s5["pct_2dp"] == "+19.90%"
    assert round((s5["vk"] / s5["hip"] - 1) * 100, 2) == 19.90
    assert s5["vk_ttft_s_2dp"] == 8.49 and s5["hip_ttft_s_2dp"] == 5.63
    assert s5["vk_agg_2dp"] == 10.58 and s5["hip_agg_2dp"] == 10.47
    assert s5["agg_pct_2dp"] == "+1.07%"
    assert s5["anchors_ok"] == 2 and s5["anchors_total"] == 2
    # Common-mode drift (finding b): BOTH backends slower evening vs the
    # session-4 morning means — shared host-state drift ±5–6%.
    assert s5["drift_vs_s4"] == {"vk_pct_1dp": "-4.6%",
                                 "hip_pct_1dp": "-6.0%"}
    # Session 6 (2026-08-20 local morning): the overnight pair.
    s6 = ev["session6"]
    assert s6["date"] == "2026-08-20" and s6["when"] == "local morning"
    assert s6["vk_2dp"] == 16.41 and s6["hip_2dp"] == 14.15
    assert s6["pct_2dp"] == "+15.93%"
    assert round((s6["vk"] / s6["hip"] - 1) * 100, 2) == 15.93
    assert s6["vk_ttft_s_2dp"] == 8.54 and s6["hip_ttft_s_2dp"] == 5.49
    assert s6["vk_agg_2dp"] == 10.63 and s6["hip_agg_2dp"] == 10.89
    assert s6["agg_pct_2dp"] == "-2.39%"   # hip-favored aggregate
    assert s6["anchors_ok"] == 2 and s6["anchors_total"] == 2
    # Overnight persistence (finding d): the receipts-derived gap is
    # 7 h 50 m (s5's LAST receipt start -> s6's FIRST receipt start) —
    # NOT the ~20 h a naive date-label reading suggests — and the s6 vk
    # receipt's own cache readings are byte-identical before/after (zero
    # writes; newest mtime still session-4 run 1's marker).
    assert s6["gap_after_s5_min"] == 470
    assert s6["gap_after_s5_hm"] == "7 h 50 m"
    assert s6["cache"] == {"identical": True, "du_kib": 7884, "files": 867,
                           "newest_mtime_utc": "2026-08-19T06:32:54Z"}
    # Warm pairing band (finding c): 4 sessions, exact-basis 2dp.
    wb = ev["warm_band"]
    assert wb["sessions"] == ("s4 boot1", "s4 boot2", "s5", "s6")
    assert wb["pcts_2dp"] == ("+15.88%", "+20.61%", "+19.90%", "+15.93%")
    wp = ev["session4"]["warm_pairings"]
    for pair, pct in zip((wp["boot1"], wp["boot2"],
                          (s5["vk"], s5["hip"]), (s6["vk"], s6["hip"])),
                         (15.88, 20.61, 19.90, 15.93)):
        assert round((pair[0] / pair[1] - 1) * 100, 2) == pct, (
            f"band value {pct} does not recompute from exact operands")
    # The anchor tally now spans s1-s6 (the pit non-reproduction finding).
    assert ev["anchors"]["cell_runs_ok"] == 19
    assert ev["anchors"]["with_soak_ok"] == 20
    # The ruling note carries supersession #3 + findings (a)-(e),
    # referencing the trigger-hunt note by path.
    r = {c["id"]: c for c in load(VERDICTS)["cells"]}[
        "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["reason"]
    for fragment in ("H2 REFINEMENT (2026-08-20, v0.1.7)",
                     "dated supersession #3",
                     "docs/results/matrix-714/stability/"
                     "trigger-hunt-2026-08-19.md",
                     "INTACT at s3", "0 written inside the causal window",
                     "CONTRADICTED", "swing BOUND proof",
                     "UNIDENTIFIED", "unattended-upgrade",
                     "linux-libc-dev/", "NO mechanism claimed",
                     "chronic common-mode clock-stepping", "883+",
                     "NOT s3-specific", "common-mode session drift",
                     "±5–6%", "warm pairing band across 4 sessions",
                     "OVERNIGHT warm persistence CONFIRMED",
                     "7 h 50 m", "byte-identical",
                     "hip-favored", "single-stream median only",
                     "controller ruling 2026-08-20",
                     "warmup guidance stands",
                     "MORE mysterious", "unquantified", "Not decided here"):
        assert fragment in r, (
            f"ruling note lost the v0.1.7 fragment {fragment!r}")
    # The superseded v0.1.6 wording stays visible, marked.
    assert "PARTIAL-COLD cache" in r and "SUPERSEDED 2026-08-20" in r


def test_trigger_hunt_note_is_committed_and_untouched_class():
    """The evidence note the v0.1.7 ruling cites is a committed
    receipt-class artifact: it exists at the referenced path and carries
    the forensic facts the ruling quotes (866/0/1 file buckets, the
    unattended-upgrade transaction, the chronic clock condition with its
    dated correction)."""
    note = (ROOT / "docs/results/matrix-714/stability/"
            "trigger-hunt-2026-08-19.md")
    text = note.read_text(encoding="utf-8")
    assert "866" in text and "0        # mtime INSIDE the window" in text
    assert "unattended-upgrade" in text
    assert "6.8.0-137.137" in text and "6.8.0-138.138" in text
    assert "Clock change detected" in text and "still accruing" in text
    assert "NONE inside s3" in text  # clock events absent during s3's run
    # It draws no causal conclusions itself (the interpretive layer is
    # H2's — recorded in the note's own preamble).
    assert "Facts + verbatim command output only" in text
    assert "No causal claim is made here" in text


# ------------- 6e. v0.1.8 D1 — the owner decision closes the question
#
# Owner ruling 2026-08-20 (DECIDED, recorded, not re-deliberated): NOT
# re-recommending BACKEND=vulkan. The README roadmap OPEN question is
# now a CLOSED decision entry carrying the four pre-registered
# promotion criteria verbatim; the ruling note gains the dated OWNER
# DECISION resolution (history visible — the earlier OPEN phrasings
# stay, marked resolved); selection guidance (self-selection, never
# promotion) lands on every surface that presents the opt-in; the
# mapping layer is untouched (vulkan still NOT recommended).

V018_CRITERIA = (
    "a daily warm series of at least 7 days with ZERO slow-state "
    "recurrence",
    "the vk c8/c16 cells measured with anchors clean (pit coverage — "
    "currently unmeasured)",
    "at least one independent host/ICD replication (a community "
    "submission is ideal)",
    "the TTFT gap stated as an applicability condition (long-generation "
    "only), not a footnote",
)


def test_owner_decision_closes_the_rerecommendation_question_v018():
    readme = README.read_text()
    roadmap = readme.split("## Status & roadmap", 1)[1]
    # The decision entry: DECIDED ... NO, stays experimental opt-in.
    assert "DECIDED 2026-08-20: NO" in roadmap, (
        "the roadmap decision entry verdict is missing")
    assert "owner" in roadmap and "ruling; stays experimental opt-in" in roadmap
    assert "NOT re-recommending vulkan" in roadmap
    # All four promotion criteria, VERBATIM, as the pre-registered path
    # to any future yes — and only as a future path (ALL four, no
    # upgrade now).
    for criterion in V018_CRITERIA:
        assert criterion in roadmap, (
            f"roadmap decision entry lost the criterion {criterion!r}")
    assert "ALL four must hold" in roadmap
    assert "conditional-recommended" in roadmap
    # The guidance reads as self-selection, never promotion; derived
    # numbers are labeled derived.
    assert "self-select" in roadmap
    assert "≈230–310 tokens (derived" in roadmap
    assert "power-sensitive setups" in roadmap
    # The ruling note carries the dated resolution; the v0.1.6/v0.1.7
    # OPEN phrasings stay visible, marked resolved (history intact).
    r = {c["id"]: c for c in load(VERDICTS)["cells"]}[
        "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["reason"]
    for fragment in ("OWNER DECISION (2026-08-20, v0.1.8)",
                     "RESOLVES the OPEN re-recommendation question",
                     "dated resolution #4",
                     "NOT re-recommending BACKEND=vulkan",
                     "mapping of record is CONFIRMED, not changed",
                     "≈230–310 tokens (DERIVED",
                     "not a measurement",
                     "12.38 tok/s, TTFT 12.45 s",
                     "1-of-7 vk runs",
                     "ZERO slow-state recurrence",
                     "RESOLVED 2026-08-20 by the OWNER DECISION addendum "
                     "below (NO)",
                     "DECIDED 2026-08-20 (owner ruling, v0.1.8): NO",
                     "OPEN for the human owner"):
        assert fragment in r, (
            f"ruling note lost the v0.1.8 resolution fragment {fragment!r}")
    # Zero metric/verdict changes rode along with the decision.
    # (v0.1.9, 2026-08-21: the two dflash cells shift the distribution to
    # 9/15/6 — dflash-c1 recommended, dflash-c8 caution.)
    dist = {}
    for c in load(VERDICTS)["cells"]:
        dist[c["verdict"]] = dist.get(c["verdict"], 0) + 1
    assert dist == {"recommended": 9, "caution": 15, "avoid": 6}


def test_selection_guidance_on_every_optin_surface_v018():
    """The owner-ruling selection guidance (self-selection criteria,
    never promotion) is present wherever the opt-in is presented: the
    quickstart echo (one new line, boot logic untouched), the README
    generated known-good bullet, the benchmark.md quickstart-mapping
    row, and adaptation.md §Vulkan — and the mapping still asserts
    vulkan NOT recommended everywhere."""
    src = QUICKSTART.read_text()
    assert "self-select this opt-in for long outputs" in src, (
        "the quickstart vulkan echo lost the selection-guidance line")
    assert "power-sensitive setups" in src
    assert "still NOT recommended" in src
    assert "owner ruling 2026-08-20" in src
    # Boot logic untouched: default hip, opt-in framing unchanged.
    assert 'BACKEND="${BACKEND:-hip}"' in src
    assert "AVAILABLE experimental opt-in" in src
    assert "RECOMMENDED OPT-IN" not in src
    readme = README.read_text()
    kg = readme.split("BEGIN GENERATED: known-good-bad", 1)[1]
    assert "Selection guidance (owner ruling 2026-08-20" in kg, (
        "the generated known-good bullet lost the guidance sentence")
    assert "≈230–310 tokens (derived)" in kg
    assert "package power ~30–32 W vs ~52–53 W" in kg
    bench = BENCH_MD.read_text()
    assert "self-select for long outputs (≳300-token replies)" in bench, (
        "the benchmark.md quickstart-mapping row lost the guidance")
    assert "Owner ruling 2026-08-20 (v0.1.8, DECISION" in bench
    adaptation = (ROOT / "docs" / "adaptation.md").read_text()
    assert "Choosing the backend (owner ruling 2026-08-20" in adaptation
    for criterion in V018_CRITERIA:
        assert criterion in adaptation, (
            f"adaptation.md §Vulkan lost the criterion {criterion!r}")
    assert "±0.6 s" in adaptation and "≈230–310 tokens (derived)" in adaptation
    # The guidance never promotes: vulkan stays NOT recommended.
    assert "NOT recommended" in readme
    assert "NO recommendation" in bench


def test_no_quickstart_referenced_config_is_avoid():
    # The BACKEND=vulkan opt-in stays in the protected set even downgraded —
    # an available opt-in path must never be a pit/avoid cell.
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
    assert set(new_cells) - migrated_ids == t3_additions | {
        # v0.1.9 (2026-08-21): the two measured DFlash2 corpus cells.
        "vllm-bf16-auto-dflash-c1-ctx131072",
        "vllm-bf16-auto-dflash-c8-ctx131072",
    }, (
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
    assert len(measured) == 30  # v0.1.9: 28 + the 2 dflash cells
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
#
# v0.1.4 (2026-08-19, S5): the quickstart mapping is SUPERSEDED — the clean
# d1/d1 pairing (+4.81%, aggregate −13.31%, cross-day variance) removed the
# recommendation basis: vulkan is an AVAILABLE experimental opt-in, hip
# WITH_MTP=1 is both the default and the recommended path. The per-cell
# review records and every mechanical verdict are UNCHANGED; the superseded
# ruling stays visible (dated supersession, never a silent rewrite).

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
    # Corpus attribution (updated v0.1.4, re-dated v0.1.7): the latest
    # ruling of record that produced THIS file state is the 2026-08-20 H2
    # refinement (the mapping layer it leaves unchanged remains the
    # 2026-08-19 ruling); exactly the 8 v0.1.2 cells carry a per-cell
    # reviewed_by (their MECHANICAL review — unchanged by every
    # mapping-layer supersession), while the 20 migrated cells stay
    # governed by the frozen controller-2026-08-17 review.
    # v0.1.14 (2026-08-21): the evidence-ruling date advances to the dflash
    # pairing ruling; the frozen per-cell reviews (2026-08-17/18) are
    # unchanged fields on their own cells.
    assert v["reviewed_by"] == "controller-2026-08-21"
    assert v["checked_at"] == "2026-08-21"  # v0.1.14: dflash ruling date
    per_cell = [c for c in v["cells"] if c["metrics"].get("reviewed_by")]
    assert len(per_cell) == 8


def test_ruling_supersession_2026_08_19_recorded_and_quickstart_matches():
    """The dated supersession is recorded where it binds AND the quickstart
    matches it. Ruling 2026-08-18 (promotion, mixed-depth basis) SUPERSEDED
    by ruling 2026-08-19 (clean-pairing basis) — both dates visible in the
    generated note; the mapping: vulkan = available experimental opt-in,
    hip WITH_MTP=1 = default AND recommended path; the pit non-reproduction
    finding stands. v0.1.6 (R2, same day): the cross-day cause statement
    ("NOT recorded") is itself SUPERSEDED — the variance is explained as
    Mesa shader-cache state dependence with warm/cold bounds, and the
    recommendation stays unchanged. v0.1.7 (H2, 2026-08-20): the v0.1.6
    partial-cold READING of s3 is superseded in turn — the cache was
    forensically INTACT at s3, the trigger is UNIDENTIFIED, and the
    recommendation STILL stays unchanged (see
    test_trigger_hunt_overnight_series_arithmetic_v017)."""
    by_id = {c["id"]: c for c in load(VERDICTS)["cells"]}
    vk = by_id["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]
    # Both dates visible in the supersession note (never a silent rewrite).
    r = vk["reason"]
    assert "Controller ruling 2026-08-19" in r
    assert "SUPERSEDES the controller ruling 2026-08-18" in r
    # The clean-pairing basis, with numbers.
    assert "14.53" in r and "13.86" in r and "+4.81%" in r
    assert "10.74" in r and "9.31" in r and "-13.31%" in r
    assert "depth-confounded" in r
    # The cross-day variance and the honest telemetry gap.
    assert "11.81%" in r and "30.70%" in r and "6.07%" in r
    # v0.1.6 R2: the cause statement is superseded dated, history visible —
    # the old sentence stays, and the cache-state story replaces it as the
    # finding of record.
    assert "NOT recorded" in r and "no clock/thermal telemetry" in r
    assert "SUPERSEDED the same day by the R2 note below" in r
    assert "R2 ROOT-CAUSE (2026-08-19, v0.1.6)" in r
    assert "Mesa shader-cache state dependence" in r
    assert "TRIGGER remains UNIDENTIFIED" in r
    assert "CONSERVATIVE FLOOR CASE" in r and "warm-cache, boot-paired" in r
    assert "RECOMMENDATION UNCHANGED" in r
    assert "OPEN for the human owner" in r
    # The mapping downgrade + the mechanical-verdict carve-out.
    assert "AVAILABLE experimental opt-in" in r
    assert "hip WITH_MTP=1 is BOTH the default backend AND the recommended path" in r
    assert "MECHANICAL verdict (recommended) is unchanged" in r
    # No-flip closed on the clean arithmetic.
    assert "+4.81% << the >25% pre-registered flip threshold" in r
    # The unaffected pit finding, restated (now 19/19 across s1-s6).
    assert "does NOT reproduce on vulkan" in r
    assert "19/19" in r and "20/20" in r
    # The mechanical verdicts stand (8/14/6 distribution unchanged).
    assert vk["verdict"] == "recommended"
    # The quickstart binds the same story: default hip, downgraded opt-in.
    src = QUICKSTART.read_text()
    assert 'BACKEND="${BACKEND:-hip}"' in src, "default must stay hip"
    assert "AVAILABLE experimental opt-in" in src
    assert "NOT recommended" in src
    assert "RECOMMENDED OPT-IN" not in src
    assert "default AND recommended path" in src
    assert "2026-08-19" in src and "2026-08-18" in src


def test_ruling_no_flip_arithmetic_recorded_v013():
    """v0.1.3 (S2) history note: the two-session evidence recorded the
    no-flip arithmetic so the exactly-+25.0% session-2 headline was never
    misread as the >25% flip trigger. v0.1.4 SUPERSEDES that guard with the
    clean pairing (+4.81% — see
    test_no_flip_closed_on_the_clean_pairing_arithmetic_v014); these pins
    keep the session-2/soak evidence loading from the committed receipts
    (receipts-only: they never enter the 28-cell matrix)."""
    ev = gv.stability_evidence()
    assert ev, ("stability receipts failed to load from "
                "docs/results/matrix-714/stability/")
    by_id = {c["id"]: c for c in load(VERDICTS)["cells"]}
    hip_mtp4 = by_id["gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072"][
        "metrics"]["per_stream_tok_s_median"]
    m1 = ev["cells"]["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]
    m4 = ev["cells"]["gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072"]
    # Session-2 evidence still loads with the same shape (the supersession
    # note quotes the 16.25 headline it retires).
    assert m1["s2_2dp"] == 16.25 and round(m1["s1"], 2) == 16.00
    assert m4["s2_2dp"] == 15.25 and round(m4["s1"], 2) == 15.05
    assert m1["delta_pct"] == "+1.5%"
    assert m4["delta_pct"] == "+1.3%"
    assert ev["cells"]["gguf-vulkan-udq4kxl-auto-base-c1-ctx131072"][
        "delta_pct"] == "+2.5%"
    # The soak stats: 108 cycles, -2.6% settle.
    assert ev["soak"]["cycles"] == 108 and ev["soak"]["ok_cycles"] == 108
    assert ev["soak"]["settle_pct"] == -2.6
    assert hip_mtp4 == 12.76
    # The v0.1.4 supersession note references the retired guard inline.
    r = by_id["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["reason"]
    assert "exactly-+25.0% session-2 headline" in r
    assert "superseded by this clean pairing" in r
    # ...and the default is still hip everywhere the quickstart binds.
    assert 'BACKEND="${BACKEND:-hip}"' in QUICKSTART.read_text()
    # The generated surfaces carry the dated supersession, never the old
    # "single-session" caveat or a standing promotion.
    for surface in (BENCH_MD, README):
        text = surface.read_text()
        assert "single-session" not in text, (
            f"{surface.name}: stale single-session caveat survived")
        assert "2026-08-19" in text and "2026-08-18" in text, (
            f"{surface.name}: the supersession dates must both be visible")
        assert "SUPERSEDES" in text, (
            f"{surface.name}: the dated supersession is missing")
    assert "recommended OPT-IN" not in BENCH_MD.read_text(), (
        "benchmark.md still carries the retired promotion wording")


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


# --------------------- 6b. v0.1.5 audit-F1 docs-accuracy pins
#
# Three independent audits of v0.1.4 (A docs-freshness, B reproducibility,
# C community-UX) found the depth-1 story not fully EXPRESSIBLE or
# consistently LABELED on user-facing surfaces. These pins keep the fixes
# fixed; none of them changes data — the corpus and verdicts are untouched.

def test_recommended_d1_invocation_is_expressible_from_docs():
    """Audit B-I2 / C-I3 (v0.1.5): the recommended depth-1 variant must be
    reachable from the docs, not only from script source — README quickstart
    and getting-started document `WITH_MTP=1 SPEC_DEPTH=1` as the
    recommended invocation, the bare `WITH_MTP=1` stays labeled
    implicit-depth-3 (the 13.0 corpus cell), and the quickstart echo
    carries the one-line SPEC_DEPTH=1 hint."""
    readme = README.read_text()
    assert "WITH_MTP=1 SPEC_DEPTH=1 bash scripts/gguf-quickstart.sh" in readme, (
        "README quickstart lacks the recommended d1 invocation")
    assert "implicit depth 3" in readme, (
        "the bare WITH_MTP=1 boot must be labeled implicit-depth-3")
    assert "13.86" in readme, (
        "the clean d1 number behind the recommendation must be stated")
    gs = (ROOT / "docs" / "getting-started.md").read_text()
    assert "WITH_MTP=1 SPEC_DEPTH=1 bash scripts/gguf-quickstart.sh" in gs
    assert "implicit upstream depth 3" in gs, (
        "getting-started must label the bare WITH_MTP boot")
    src = QUICKSTART.read_text()
    assert "SPEC_DEPTH=1 pins the recommended" in src, (
        "the quickstart echo must carry the one-line SPEC_DEPTH=1 hint")
    # Re-run drift note (audit B minor 3): the mapping tables state that a
    # re-run today pins depth 1 explicitly (~13.86, session 3).
    bench = BENCH_MD.read_text()
    assert "pins depth 1 explicitly" in bench and "13.86" in bench, (
        "benchmark.md mapping row lost the re-run drift note")
    assert "stability/session3-2026-08-19" in readme, (
        "README quickstart row must stay traceable to stability/session3")


def test_readme_recommended_table_two_verdict_layers_no_collision():
    """Audit C-I1 (v0.1.5): the generated 'Recommended' table must never
    show '✅ recommended' unqualified next to a NOT-recommended mapping in
    the same row — the CELL verdict (mechanical, corpus-backed) and the
    QUICKSTART mapping (recommendation layer) are separate, labeled
    columns (benchmark.md's mapping table is the model)."""
    block = _readme_block("performance-highlights")
    assert "| Cell verdict | Quickstart mapping |" in block, (
        "the Recommended table lacks the two labeled verdict columns")
    vk_row = next(ln for ln in block.splitlines()
                  if ln.startswith("| `BACKEND=vulkan`"))
    assert "✅ recommended" in vk_row, "cell verdict must stay visible"
    assert "**NOT recommended**" in vk_row, (
        "the vulkan row's mapping column must state NOT recommended")
    # The columns are ordered: cell verdict BEFORE quickstart mapping, so a
    # scanner reads the mechanical verdict first, the mapping second.
    assert vk_row.index("✅ recommended") < vk_row.index("**NOT recommended**")
    hip_row = next(ln for ln in block.splitlines()
                   if ln.startswith("| `WITH_MTP=1` mtp-c1"))
    assert "**recommended path**" in hip_row and "SPEC_DEPTH=1" in hip_row, (
        "the hip mtp row must map to the recommended SPEC_DEPTH=1 form")


def test_depth1_vs_depth4_citations_use_labeled_clean_numbers():
    """Audit A-M6 / C-I3 (v0.1.5): the 'depth 1 beats depth 4' comparison
    must never cite the implicit-depth-3 corpus receipt (13.00) as the
    hip depth-1 side — the hip side is the depth-explicit 13.86 (session 3,
    2026-08-19) vs 12.76 (2026-08-18, explicit d4), dates labeled; same
    discipline hand-edited into docs/adaptation.md."""
    text = BENCH_MD.read_text()
    # The sentence terminates at '...of a depth comparison.' — numbers like
    # 16.00 contain periods, so the terminator is textual, not '.'.
    m = re.search(r"MTP depth 1 beats depth 4.*?depth comparison\.", text, re.S)
    assert m, "benchmark.md lost the depth comparison sentence"
    s = m.group(0)
    for number in ("16.00", "15.05", "13.86", "12.76"):
        assert number in s, f"{number} missing from the depth comparison"
    assert "implicit depth 3" in s, (
        "the corpus-cell depth disclosure is missing")
    assert "2026-08-18" in s and "2026-08-19" in s, (
        "the depth-comparison dates must be labeled")
    adaptation = (ROOT / "docs" / "adaptation.md").read_text()
    assert "hip 12.76 vs 13.00" not in adaptation and \
        "hip 13.00 vs 12.76" not in adaptation, (
            "adaptation.md still cites 13.00 (implicit d3) as the hip d1 side")
    assert "13.86" in adaptation and "SPEC_DEPTH=1" in adaptation
    # The historical receipt's date label is consistent (UTC + local):
    assert "2026-08-16 UTC" in text and "2026-08-16 UTC" in adaptation, (
        "the hip corpus receipt must be dated 2026-08-16 UTC consistently")


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


def test_schema_accepts_the_dflash_spec_variant_ids():
    # v0.1.9: the spec-variant slot gains "dflash" (vllm path only — the
    # pattern must still refuse gguf dflash and the dropped ctx tiers).
    s = load(SCHEMA)
    pat = re.compile(
        s["properties"]["cells"]["items"]["properties"]["id"]["pattern"])
    assert pat.match("vllm-bf16-auto-dflash-c1-ctx131072")
    assert pat.match("vllm-bf16-auto-dflash-c8-ctx131072")
    assert not pat.match("vllm-bf16-auto-dflash-c1-ctx32768")
    assert not pat.match("gguf-hip-udq4kxl-auto-dflash-c1-ctx131072")


def test_dflash_cells_carry_pairing_basis_and_dated_supersession():
    """v0.1.9 DFlash2 cells (2026-08-21): the corpus dflash cells carry the
    same-session pairing basis ({base,mtp,dflash} x {c1,c8} @131072, session
    receipts under matrix-714/stability/dflash-pairing-2026-08-21/ — the
    corpus base/mtp cells are the 262144 story, so the pairing partners
    cannot come from the corpus)."""
    v = load(VERDICTS)
    by_id = {c["id"]: c for c in v["cells"]}
    c1 = by_id["vllm-bf16-auto-dflash-c1-ctx131072"]
    c8 = by_id["vllm-bf16-auto-dflash-c8-ctx131072"]

    # The ladder: c1 crosses the interactive floor (first vLLM cell to);
    # c8 stays below it at a multi-user tier.
    assert c1["verdict"] == "recommended"
    assert c8["verdict"] == "caution"

    # c1 must NOT carry the generic below-floor prose (it is ABOVE the
    # floor — the 2026-08-17 ruling premise is superseded FOR THIS CELL,
    # dated, never silently).
    assert "is below the 10 tok/s interactive floor" not in c1["reason"]
    assert "10.2 tok/s" in c1["reason"]
    assert "SUPERSEDED for this cell" in c1["reason"]

    # Gains cite the same-session pairing, both counterparts labeled
    # (percentages as computed by the generator from its own metric
    # rounding: +150.1% / +65.3% at c1; +31.5% / +3.3% at c8).
    c1_l = c1["reason"].lower()
    for token in ("+150.1%", "+65.3%", "same-session"):
        assert token in c1_l, f"{token!r} missing from the c1 reason"
    assert "dflash_gain_vs_base" in c1["metrics"]
    assert "dflash_gain_vs_mtp" in c1["metrics"]

    # c8: gain erosion stated honestly, no regression, aggregate basis kept.
    c8_l = c8["reason"].lower()
    for token in ("+31.5%", "+3.3%", "same-session"):
        assert token in c8_l, f"{token!r} missing from the c8 reason"

    # The patch + tier caveats ride along (they are applicability
    # conditions, not footnotes).
    for cell in (c1, c8):
        assert "#52816" in cell["reason"] or "#52816" in (cell["conditions"] or "")
        assert "262144" in cell["reason"] or "262144" in (cell["conditions"] or "")


def test_readme_carries_the_dflash2_pairing_comparison_table():
    """v0.1.9: the with-vs-without DFlash2 comparison is a generated
    performance-highlights surface — same-session pairing basis, both
    counterparts (base AND mtp) labeled, the floor-crossing stated, and
    the applicability caveats (PR #52816 patch, 131072-only) riding along."""
    text = README.read_text()
    assert "DFlash2 vs no-DFlash2" in text
    block = text.split("DFlash2 vs no-DFlash2", 1)[1][:1600]
    for token in ("10.2", "+150.1%", "+65.3%", "+31.5%", "+3.3%",
                  "same-session pairing", "#52816", "131072"):
        assert token in block, f"{token!r} missing from the comparison table"
    assert "first vLLM cell" in block and "10 tok/s" in block


def test_dflash_c1_carries_the_crossday_and_nmax_addendum():
    """v0.1.15 (2026-08-22): the n-max sweep session
    (stability/dflash-nmax-sweep-2026-08-22/) adds two dated facts to the
    dflash-c1 ruling: (1) the 10 tok/s floor-crossing is DAY-DEPENDENT
    (dflash-7 median 9.79 today vs the 10.23 corpus cell — controls
    replicated +1.5%/+0.5%, so common-mode drift); (2) num_speculative_
    tokens 7 is confirmed (n=4 statistically tied, gap +2.7% < the arm's
    own run spread; n=2–3 clearly lower) — the GGUF-side 2–4 optimum does
    NOT transfer to the vLLM path."""
    v = load(VERDICTS)
    by_id = {c["id"]: c for c in v["cells"]}
    c1 = by_id["vllm-bf16-auto-dflash-c1-ctx131072"]
    text = (c1["reason"] + " " + (c1["conditions"] or "")).lower()
    for token in ("2026-08-22", "9.79", "day-dependent", "n-max",
                  "does not transfer"):
        assert token in text, f"{token!r} missing from the c1 addendum"


def test_dflash_floor_series_criteria_are_preregistered():
    """v0.1.15 (2026-08-22): the dflash floor-crossing question gets a
    PRE-REGISTERED ruling protocol before the multi-day series runs
    (the Vulkan-series governance precedent): the criteria live in the
    README roadmap decision entry, the verdict points at them, and the
    series convention is documented in the stability README."""
    readme = README.read_text()
    block = readme[readme.find("dflash floor series (pre-registered"):][:2500] \
        if "dflash floor series (pre-registered" in readme else ""
    assert block, "README roadmap lacks the pre-registered series block"
    for token in ("first 5 committed installments", "5-of-5",
                  "median ≥ 10.0", "stably at/above the floor", "straddles",
                  "mapping does not change", "anchor", "missed day"):
        assert token in block, f"pre-registration lacks {token!r}"

    v = load(VERDICTS)
    c1 = {c["id"]: c for c in v["cells"]}["vllm-bf16-auto-dflash-c1-ctx131072"]
    assert "pre-registered 2026-08-22" in c1["reason"], (
        "the verdict addendum must point at the pre-registered protocol")

    stab = (ROOT / "docs/results/matrix-714/stability/README.md").read_text()
    assert 'ARMS="7"' in stab and "probe-vllm-dflash2-nmax-sweep" in stab, (
        "the stability README must document the daily one-liner")
