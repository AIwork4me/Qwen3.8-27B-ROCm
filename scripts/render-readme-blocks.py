#!/usr/bin/env python3
"""Task 5: README block + benchmark report renderer.

Renders, from configs/benchmark-verdicts.json (+ raw cells, the long-context
smoke receipt, and matrix.json — never hand-edited copies):

  * the GENERATED blocks inside README.md (performance highlights,
    context capacity, known good / known bad, and — via
    scripts/render-hardware-matrix.py, imported below — the hardware
    matrix), replaced between
    `<!-- BEGIN GENERATED: <name> -->` / `<!-- END GENERATED: <name> -->`
    markers — regeneration is idempotent (byte-identical);
  * docs/results/benchmark.md, wholesale (headline tables + links to the
    raw cells).

Usage:
    python3 scripts/render-readme-blocks.py         # write README blocks + benchmark.md
    python3 scripts/render-readme-blocks.py --check # exit 1 if either is stale

Hand-editing inside the markers is forbidden: the next regen destroys it.

2026-08-18 backend-dimension migration (v0.1.2 Vulkan×MTP): gguf cell ids
carry an explicit -hip-|-vulkan- tag (legacy unprefixed ids ARE hip; the
cells/ files were renamed in lockstep, filename == id). Tables that mix
backends render a Backend column derived from the id — the v0.1.2 session
measured 6 vulkan cells + 2 hip cells (mtp4 depth, unified-boot c4 rider),
so measured rows span both backends and every stale "all measured cells
are hip" / "unmeasured" qualifier is derived from the data, never assumed.

2026-08-18 stability follow-up S2 (v0.1.3): the 2026-08-18 ruling
paragraph and the known-good vulkan bullet quote the two-session + soak
evidence via gen-verdicts.stability_evidence() (session-2 deltas, soak
cycles/settle) — the "single-session runtime" caveat is gone from every
generated surface, and the no-flip arithmetic is printed with it.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERDICTS = ROOT / "configs" / "benchmark-verdicts.json"
CELLS_DIR = ROOT / "docs" / "results" / "matrix-714" / "cells"
MATRIX = ROOT / "docs" / "results" / "matrix-714" / "matrix.json"
SMOKE = ROOT / "docs" / "results" / "matrix-714" / "long-context-smoke.json"
README = ROOT / "README.md"
BENCH_MD = ROOT / "docs" / "results" / "benchmark.md"

BLOCKS = ("performance-highlights", "context-capacity", "known-good-bad")


def _load_hardware_matrix_renderer():
    """scripts/render-hardware-matrix.py (hyphenated name: no plain import).
    One regen covers every README block, so this renderer owns the
    hardware-matrix block too; it stays independently runnable with the
    same --check semantics."""
    spec = importlib.util.spec_from_file_location(
        "render_hardware_matrix", ROOT / "scripts" / "render-hardware-matrix.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_gen_verdicts():
    """scripts/gen-verdicts.py — imported (not copied) for its
    stability_evidence() loader (2026-08-18, v0.1.3 S2): the session-2
    deltas + soak stats quoted in the ruling paragraph and the known-good
    bullet interpolate from the same receipts the ruling note uses, so
    there is one source of truth for the stability numbers."""
    spec = importlib.util.spec_from_file_location(
        "gen_verdicts_stability", ROOT / "scripts" / "gen-verdicts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HARDWARE_MATRIX = _load_hardware_matrix_renderer()
GEN_VERDICTS = _load_gen_verdicts()


def mark(verdict: str) -> str:
    return {"recommended": "✅", "caution": "⚠️", "avoid": "❌"}[verdict]


def fmt(x, nd=1):
    return f"{x:.{nd}f}" if x is not None else "—"


def backend_of(cid: str) -> str:
    """Backend tag straight from the cell id (2026-08-18 grammar:
    gguf-{backend}-...). vLLM has exactly one backend — no tag, no column."""
    return cid.split("-")[1] if cid.startswith("gguf-") else ""


def measured_date_range(cells: dict) -> str:
    """The 'Measured <dates>' range, DERIVED from the raw receipts'
    started_utc (2026-08-18 defect fix: the hardcoded 2026-08-16/17 range
    went stale the day new cells landed)."""
    ds = sorted({c["started_utc"][:10] for c in cells.values()})
    if len(ds) == 1:
        return ds[0]
    if len(ds) == 2:
        return f"{ds[0]} and {ds[1]}"
    return f"{ds[0]} through {ds[-1]}"


def review_attribution(verdicts: dict) -> str:
    """Honest per-family review line for a mixed corpus (2026-08-18 defect
    fix: a single `reviewed_by` overstated review for cells added after the
    frozen review). The 20 migrated cells carry no per-cell
    metrics.reviewed_by — they are governed by the frozen
    controller-2026-08-17 review; every cell WITH metrics.reviewed_by names
    its own reviewer of record."""
    per_cell = [c for c in verdicts["cells"]
                if c.get("metrics", {}).get("reviewed_by")]
    legacy = [c for c in verdicts["cells"]
              if not c.get("metrics", {}).get("reviewed_by")]
    if not per_cell:
        return (f"Verdicts reviewed and recorded by "
                f"`{verdicts['reviewed_by']}`; ladder proposes, controller "
                f"disposes.")
    parts = []
    if legacy:
        parts.append(f"{len(legacy)} cells by `controller-2026-08-17` "
                     f"(frozen review, unchanged by the later regeneration)")
    reviewers = sorted({c["metrics"]["reviewed_by"] for c in per_cell})
    for r in reviewers:
        n = sum(1 for c in per_cell if c["metrics"]["reviewed_by"] == r)
        parts.append(f"{n} cells by `{r}` (per-cell `metrics.reviewed_by`)")
    return ("Verdicts reviewed and recorded: " + "; ".join(parts)
            + ". Ladder proposes, controller disposes.")


def short_id(cid: str) -> str:
    """Table label: the id minus its fixed prefixes (path, backend, weight,
    kv-mode) — e.g. `mtp-c1-ctx131072`."""
    for prefix in (f"gguf-{backend_of(cid)}-udq4kxl-auto-",
                   "vllm-bf16-auto-"):
        if cid.startswith(prefix):
            return cid[len(prefix):]
    return cid


def load_data() -> dict:
    verdicts = json.loads(VERDICTS.read_text())
    vmap = {c["id"]: c for c in verdicts["cells"]}
    cells = {p.stem: json.loads(p.read_text()) for p in CELLS_DIR.glob("*.json")}
    matrix = json.loads(MATRIX.read_text())
    smoke = json.loads(SMOKE.read_text()) if SMOKE.exists() else None
    return {"verdicts": verdicts, "vmap": vmap, "cells": cells,
            "matrix": matrix, "smoke": smoke}


def dist(data) -> dict:
    d = {}
    for c in data["verdicts"]["cells"]:
        d[c["verdict"]] = d.get(c["verdict"], 0) + 1
    return d


def parse_kv_line(cell: dict) -> dict:
    """Parse vLLM boot-log KV lines captured verbatim in the cell JSON."""
    out = {}
    for line in (cell.get("engine", {}).get("kv_and_load_lines") or []):
        m = re.search(r"GPU KV cache size: ([\d,]+) tokens, "
                      r"Maximum concurrency for ([\d,]+) tokens per request: "
                      r"([\d.]+)x", line)
        if m:
            out["kv_tokens"] = int(m.group(1).replace(",", ""))
            out["max_len"] = int(m.group(2).replace(",", ""))
            out["concurrency_x"] = m.group(3)
        m = re.search(r"Available KV cache memory: ([\d.]+) GiB", line)
        if m:
            out["kv_gib"] = float(m.group(1))
        m = re.search(r"Model loading took ([\d.]+) GiB", line)
        if m:
            out["weights_gib"] = float(m.group(1))
    return out


def reasoning_moot_mark(cells: dict) -> str:
    """METHODOLOGY §2 fold-in: the thinking-mode TPOT question is moot-marked
    when every measured stream recorded reasoning_tokens = 0."""
    nonzero = [s.get("reasoning_tokens") or 0
               for c in cells.values() for s in c["client"]["streams"]
               if (s.get("reasoning_tokens") or 0) > 0]
    if nonzero:
        return (f"NOT moot: {len(nonzero)} streams recorded reasoning tokens "
                f"(thinking leaked into a cell) — investigate before trusting "
                f"TTFT/TPOT comparability.")
    return ("Moot-mark (METHODOLOGY §2): reasoning_tokens = 0 across all "
            "measured cells — every cell ran the shared --no-thinking "
            "instrument mode, so TPOT is visible-answer TPOT; thinking-mode "
            "latency remains a declared non-goal of this session.")


# ------------------------------------------------------------ README blocks

def render_performance_highlights(data: dict) -> str:
    v = data["vmap"]
    d = dist(data)
    gguf_reco = [v[i] for i in (
        "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-base-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-base-c1-ctx32768",
        "gguf-hip-udq4kxl-auto-base-c1-ctx262144")]
    lines = [
        f"Measured {measured_date_range(data['cells'])} on the reference "
        f"host (gfx1151, ROCm 7.14, 80 GiB GTT pool): "
        f"**{len(data['verdicts']['cells'])} cells — "
        f"{d.get('recommended', 0)} recommended / {d.get('caution', 0)} caution "
        f"/ {d.get('avoid', 0)} avoid**. Verdicts: "
        f"`configs/benchmark-verdicts.json`; raw receipts: "
        f"`docs/results/matrix-714/cells/`; full tables: "
        f"`docs/results/benchmark.md`.",
        "",
        "**Recommended — interactive chat (GGUF path, UD-Q4_K_XL):**",
        "",
        "| Config | Backend | Per-stream (median) | Aggregate | TTFT | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for c in gguf_reco:
        m = c["metrics"]
        label = {
            "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072":
                "`BACKEND=vulkan` + `WITH_MTP=1` mtp-c1 @131072 — "
                "recommended opt-in, best single-stream (project ruling "
                "2026-08-18)",
            "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072":
                "`WITH_MTP=1` mtp-c1 @131072 — +28% per-stream (the default "
                "recommendation)",
            "gguf-hip-udq4kxl-auto-base-c1-ctx131072":
                "default boot base-c1 @131072",
            "gguf-hip-udq4kxl-auto-base-c1-ctx32768": "base-c1 @32768",
            "gguf-hip-udq4kxl-auto-base-c1-ctx262144":
                "base-c1 @262144 (GTT +8.0 GiB)",
        }[c["id"]]
        lines.append(
            f"| {label} | {backend_of(c['id'])} | "
            f"{fmt(m['per_stream_tok_s_median'])} tok/s "
            f"(TPOT {fmt(m['tpot_ms_median'])} ms) | "
            f"{fmt(m['aggregate_tok_s'])} tok/s | "
            f"{fmt(m['ttft_ms_median'] / 1000)} s | {mark(c['verdict'])} "
            f"{c['verdict']} |")
    lines += [
        "",
        "**Caution — batch / throughput (vLLM BF16 @262144):** every measured "
        "vLLM cell is below the 10 tok/s interactive floor — project ruling "
        "(2026-08-17); use this path for what it wins:",
        "",
        "| Config | Per-stream (median, min) | Aggregate | Verdict |",
        "|---|---|---|---|",
    ]
    for cid, note in (
            ("vllm-bf16-auto-base-c16-ctx262144", "best batch cell measured"),
            ("vllm-bf16-auto-mtp-c8-ctx262144", "MTP beneficial through c8"),
            ("vllm-bf16-auto-mtp-c1-ctx262144",
             "+52.6% per-stream vs base (+45.5% aggregate, basis labeled in the verdict)")):
        m = v[cid]["metrics"]
        # min is only informative when there is more than one healthy stream
        span = (f" (min {fmt(m['per_stream_tok_s_min'], 2)})"
                if m.get("healthy_streams", 1) > 1 else "")
        lines.append(
            f"| {cid.removeprefix('vllm-bf16-auto-')} | "
            f"{fmt(m['per_stream_tok_s_median'])}{span} tok/s | "
            f"{fmt(m['aggregate_tok_s'])} tok/s | {mark('caution')} caution — "
            f"{note} |")
    best_batch = v["vllm-bf16-auto-base-c16-ctx262144"]["metrics"]
    vk_mtp = v["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["metrics"]
    hip_mtp = v["gguf-hip-udq4kxl-auto-mtp-c1-ctx131072"]["metrics"]
    lines += [
        "",
        f"**Honesty clause (aggregate never headlines over UX):** the best "
        f"aggregate on this host — vLLM base-c16, "
        f"{fmt(best_batch['aggregate_tok_s'])} tok/s — runs each stream at "
        f"{fmt(best_batch['per_stream_tok_s_median'])} tok/s median "
        f"(min {fmt(best_batch['per_stream_tok_s_min'], 2)}): batch "
        f"presentation only. GGUF-hip c8/c16 aggregates (to 27.5 tok/s) are ❌ "
        f"avoid cells — greedy decoding degrades after sustained multistream "
        f"load (see Known good / known bad; the pit does NOT reproduce on "
        f"Vulkan, whose c8/c16 tiers are unmeasured). Interactive chat → GGUF "
        f"`WITH_MTP=1` ({fmt(hip_mtp['per_stream_tok_s_median'])} tok/s per "
        f"stream; best single-stream measured: `BACKEND=vulkan WITH_MTP=1`, "
        f"{fmt(vk_mtp['per_stream_tok_s_median'])} tok/s — opt-in, +"
        f"{(vk_mtp['per_stream_tok_s_median'] / hip_mtp['per_stream_tok_s_median'] - 1) * 100:.0f}% "
        f"mixed-depth headline, cross-depth caveat in the verdict).",
    ]
    return "\n".join(lines)


def render_context_capacity(data: dict) -> str:
    smoke = data["smoke"]
    v = data["vmap"]
    lines = [
        "Boot ladder (S3) + deep-prompt retrieval smoke — GGUF path, needle "
        "sentence at ~80% depth, judged by exact substring recall "
        "(`docs/results/matrix-714/long-context-smoke.json`):",
        "",
        "| Path | Tier | Boots | GTT at load | Retrieval @~80% depth | Cell verdicts |",
        "|---|---|---|---|---|---|",
    ]
    if smoke:
        verdicts_by_tier = {
            32768: "base-c1 ✅ (base-c4-ctx32768 ❌ — greedy pit)",
            131072: "c1 base/mtp ✅; c4 ⚠️ (below floor); c8/c16 ❌ (greedy pit)",
            262144: "base-c1 ✅ (+8.0 GiB GTT); base-c4 ⚠️ (below floor)",
        }
        for t in smoke["tiers"]:
            recall = ("PASS" if t["recall"] else
                      f"**FAIL — confident miss** (answered "
                      f"\"{t['answer_excerpt']}\", finish_reason={t['finish_reason']})")
            lines.append(
                f"| gguf | {t['ctx_size']} | OK ({fmt(t['boot_wall_s'])} s) | "
                f"{t['load']['gtt_mib']:,} MiB | "
                f"{recall} @ {t['prompt_tokens']:,} prompt tokens "
                f"(TTFT {fmt(t['ttft_ms'] / 1000)} s) | "
                f"{verdicts_by_tier.get(t['ctx_size'], '')} |")
    kv_base = parse_kv_line(data["cells"]["vllm-bf16-auto-base-c1-ctx262144"])
    kv_mtp = parse_kv_line(data["cells"]["vllm-bf16-auto-mtp-c1-ctx262144"])
    lines.append(
        f"| vllm | 262144 | OK (171 s) | 75,040 MiB "
        f"(weights {fmt(kv_base.get('weights_gib'), 1)}, KV "
        f"{fmt(kv_base.get('kv_gib'), 2)} GiB) | not run on this path | "
        f"8 cells ⚠️/❌ per the 2026-08-17 ruling (mtp-c16 ❌) |")
    lines += [
        "",
        "**`max_usable_context`, honestly:** every tier boots on the GGUF "
        "path, but functional retrieval is **non-monotonic in depth** — 30K "
        "PASS, 120K confident miss, 247K PASS (one needle, one depth, one "
        "seed) — so a reliable max_usable_context for deep-prompt retrieval "
        "is **not established above ~30K** by this smoke; treat deep-context "
        "answers as unverified until re-tested (METHODOLOGY §1 ruling).",
        "",
        f"**KV ceilings:** GGUF KV grows 64 KiB/token bf16 — +8.0 GiB per "
        f"131,072 tokens, the closed form confirmed by the GTT ladder "
        f"(26,548 → 34,742 MiB). vLLM @262144 budgets KV "
        f"{fmt(kv_base.get('kv_gib'), 2)} GiB = "
        f"{kv_base.get('kv_tokens', 0):,} tokens "
        f"({kv_base.get('concurrency_x')}x max-len; MTP: "
        f"{fmt(kv_mtp.get('kv_gib'), 2)} GiB, "
        f"{kv_mtp.get('kv_tokens', 0):,} tokens, "
        f"{kv_mtp.get('concurrency_x')}x) — **a single full-depth request "
        f"fits; two concurrent full-depth streams do not** (deep-context "
        f"concurrency is KV-budget-bound long before `max_num_seqs`).",
    ]
    return "\n".join(lines)


def _pit_upstream_shared(upstream: str, npits: int) -> str:
    """The ONE shared upstream-tracking subsection for the greedy-pit cells.

    Single source of truth: every load-bearing token (HEAD commit + date,
    fix-PR link, issue links, differential-verification counts, receipts
    path) is extracted from the pit cells' own `upstream` field
    (GGUF_PIT_UPSTREAM in gen-verdicts.py) — a shape change fails loudly
    instead of letting this summary drift from
    configs/benchmark-verdicts.json (which keeps the full per-cell string).
    """
    def need(pattern: str) -> re.Match:
        m = re.search(pattern, upstream)
        if not m:
            raise SystemExit(
                f"pit `upstream` field no longer matches the shape the "
                f"shared-tracking renderer expects (missing {pattern!r}) — "
                f"update scripts/render-readme-blocks.py alongside "
                f"GGUF_PIT_UPSTREAM in scripts/gen-verdicts.py")
        return m

    head, date = need(
        r"master HEAD ([0-9a-f]+) \((\d{4}-\d{2}-\d{2})\)").groups()
    pr, pr_url = need(r"PR (#\d+) (\S*/pull/\d+)").groups()
    p_ok, p_fail = need(
        r"patched (\d+/\d+) anchor PASS vs unpatched (\d+/\d+) FAIL").groups()
    receipts = need(r"receipts (docs/\S*upstream-controls/)").group(1)
    issues = re.findall(r"(#\d+) (\S*/issues/\d+)", upstream)
    if len(issues) != 2:
        raise SystemExit(
            "pit `upstream` field: expected exactly two issue links — "
            "update scripts/render-readme-blocks.py alongside "
            "GGUF_PIT_UPSTREAM in scripts/gen-verdicts.py")
    (primary, primary_url), (family, family_url) = issues
    return (
        f"**Upstream tracking (shared by the {npits} greedy-pit cells):** "
        f"live at llama.cpp master HEAD {head} ({date}); candidate fix PR "
        f"{pr} {pr_url} differentially verified on this host (patched "
        f"{p_ok} anchor PASS vs unpatched {p_fail} FAIL idle-host; receipts "
        f"{receipts}); tracked in {primary} {primary_url} (primary — "
        f"same-host bisect, maintainer invited testing) and {family} "
        f"{family_url} (////-family); exact mechanism unresolved at "
        f"session close (METHODOLOGY §6).")


def render_known_good_bad(data: dict) -> str:
    v = data["vmap"]
    cells = data["cells"]
    pit_ids = [cid for cid, c in v.items()
               if c["verdict"] == "avoid" and not c["metrics"]["anchor_ok"]]
    vk_ids = sorted(cid for cid in v
                    if cid.startswith("gguf-vulkan-"))
    vk_clean = [cid for cid in vk_ids if v[cid]["metrics"]["anchor_ok"]]
    vk_mtp = v["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["metrics"]
    ev = GEN_VERDICTS.stability_evidence()
    lines = [
        "**Known good** (verdict receipts in `configs/benchmark-verdicts.json`):",
        "",
        "- ✅ **GGUF interactive at c1** — hip: all three ctx tiers "
        "recommended, default boot (10.1 tok/s per stream) and `WITH_MTP=1` "
        "(13.0 tok/s, +28% per-stream); vulkan (opt-in): base 10.7 and mtp "
        f"{fmt(vk_mtp['per_stream_tok_s_median'])} tok/s — the best "
        "single-stream cells measured on this host.",
        "- ✅ **vLLM path anchor-clean in all 8 cells** — including anchors "
        "run immediately after 16-stream benches: the GGUF greedy-degradation "
        "pit does NOT reproduce here; the honest choice for 262144 context, "
        "vision, and batch throughput (38.6 tok/s aggregate @base-c16).",
        "- ✅ **Vulkan backend (v0.1.2, opt-in)** — anchor-clean in all "
        f"{len(vk_clean)} measured vulkan cells (the hip greedy pit does NOT "
        "reproduce on this backend); `BACKEND=vulkan WITH_MTP=1` reaches "
        f"{fmt(vk_mtp['per_stream_tok_s_median'])} tok/s per stream — the "
        "recommended opt-in for best single-stream speed (project ruling "
        "2026-08-18; the quickstart default stays hip). Stability: "
        "reproduced by two independent measurement sessions (2026-08-18) "
        f"+ a 30-min soak ({ev['soak']['cycles']} cycles, "
        f"{ev['soak']['settle_pct']:+.1f}% settle; "
        f"`{ev['pointer']}`), one host / one ICD (RADV 25.2.8) remain the "
        "limits.",
        "- ✅ **Boot reliability** — every declared-priority cell booted (GGUF "
        "4–6 s warm; vLLM 171/226 s); zero failed streams across all "
        f"{len(cells)} cells.",
        "",
        "**Known bad / pits:**",
        "",
    ]
    for cid in sorted(pit_ids):
        m = v[cid]["metrics"]
        # Short per-cell bullet: its OWN measured numbers + the workaround.
        # The shared ~600-char upstream tail is NOT inlined per bullet — it
        # is emitted once, right below, from the verdicts' own `upstream`
        # field (GGUF_PIT_UPSTREAM in gen-verdicts.py).
        lines.append(
            f"- ❌ `{cid}` — greedy `'////'` corruption after sustained "
            f"multistream load (per-stream median "
            f"{fmt(m['per_stream_tok_s_median'])} tok/s, aggregate "
            f"{fmt(m['aggregate_tok_s'])} tok/s). Workaround: restart the "
            f"server; multi-stream loads → vLLM.")
    ups = {v[cid].get("upstream", "").strip() for cid in pit_ids}
    ups.discard("")
    if pit_ids:
        if len(ups) != 1:
            raise SystemExit(
                "greedy-pit cells no longer share one upstream string — the "
                "README shared-tracking dedup cannot apply; update "
                "render_known_good_bad alongside scripts/gen-verdicts.py")
        lines += ["", _pit_upstream_shared(ups.pop(), len(pit_ids))]
    lines += [
        "",
        f"- ❌ `vllm-bf16-auto-mtp-c16-ctx262144` — MTP regresses vs baseline "
        f"at c16 (31.1 vs 38.6 tok/s aggregate, per-stream min 1.85 tok/s); "
        f"serve without `--mtp` at high concurrency.",
        "- ⚠️ **vLLM encoder profiling** — boot OOMs at `--max-model-len "
        "262144` without `--skip-mm-profiling` (ViT dummy batch scales with "
        "max_model_len; attempted allocation 256 GiB vs the 80 GiB pool). "
        "The flag is mandatory — and with it the encoder activation peak is "
        "unbudgeted: the operator budgets image traffic "
        "(`docs/results/rocm-7.14/vllm-validation.md` ## Vision).",
        "- ⚠️ **GGUF ctx 262144 GTT growth** — +8.0 GiB over the 131072 boot "
        "(34,742 vs 26,548 MiB; 64 KiB/token bf16 KV): capacity-OK, "
        "caution-grade — fits the 80 GiB pool with headroom.",
        "- ⚠️ **vLLM KV ceiling at 262144** — KV 19.57 GiB = 313,650 tokens "
        "(1.20x max-len; MTP 1.06x): one full-depth stream fits, two don't.",
        "- ⚠️ **Deep-context retrieval (GGUF)** — 120K tier returned a "
        "confident miss; non-monotonic vs depth, unverified above ~30K (see "
        "Context capacity).",
        f"- ⚠️ **Unified default boot under concurrent users (GGUF, v0.1.2 "
        f"rider)** — the stock quickstart's 4-slot unified boot at ctx 131072 "
        f"with 4 concurrent users degrades interactivity vs the split boot: "
        f"{fmt(v['gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified']['metrics']['per_stream_tok_s_median'])} "
        f"vs "
        f"{fmt(v['gguf-hip-udq4kxl-auto-base-c4-ctx131072']['metrics']['per_stream_tok_s_median'])} "
        f"tok/s healthy-median, aggregate "
        f"{fmt(v['gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified']['metrics']['aggregate_tok_s'])} "
        f"vs "
        f"{fmt(v['gguf-hip-udq4kxl-auto-base-c4-ctx131072']['metrics']['aggregate_tok_s'])} "
        f"(3-of-4 streams early-EOS; single-stream use unaffected — see the "
        f"rider verdict).",
        "",
        "Every verdict with its full reason/conditions/workaround: "
        "`configs/benchmark-verdicts.json`.",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------- benchmark.md

def _row(cid: str, data: dict) -> str:
    c = data["vmap"][cid]
    m = c["metrics"]
    auto = m.get("auto_verdict", "")
    final = c["verdict"]
    trail = auto if auto == final else f"{auto} → **{final}** (ruling)"
    # Backend: "—" when the id carries no backend tag (vLLM has exactly one
    # backend) — same convention as the MTP-effect table, never a blank cell
    # (2026-08-18 v0.1.3 debt fix).
    return (f"| [`{cid}`](matrix-714/cells/{cid}.json) | "
            f"{backend_of(cid) or '—'} | "
            f"{mark(final)} {final} | {fmt(m['per_stream_tok_s_median'], 2)} | "
            f"{fmt(m['per_stream_tok_s_min'], 2)} | "
            f"{fmt(m['tpot_ms_median'])} | {fmt(m['aggregate_tok_s'], 2)} | "
            f"{fmt(m['ttft_ms_median'] / 1000)} s | "
            f"{'ok' if m['anchor_ok'] else 'FAILED'} | "
            f"{m['gtt_mib']:,} | {trail} |")


def gguf_c4_slot_note(cells: dict, vmap: dict | None = None) -> str:
    """Footnote for the GGUF table: the `c4` rows are NOT one configuration
    across ctx tiers (METHODOLOGY §6) — derived from each cell's recorded
    `slot_info` so the note can never drift from the receipts. Updated
    2026-08-18 (Task 4): the unified-default-boot c4@131072 rider MEASURED
    that configuration — the old 'was not measured' caveat is replaced by
    the measured finding (numbers from the verdicts)."""
    rows = []
    for ctx in (32768, 131072, 262144):
        cell = cells.get(f"gguf-hip-udq4kxl-auto-base-c4-ctx{ctx}")
        s = (cell or {}).get("slot_info") or {}
        if not s:
            continue
        if s.get("kv_unified") == "true":
            mode = (f"unified default boot (`kv_unified='true'`, per-slot "
                    f"window = full ctx {s.get('n_ctx_slot')} over one "
                    f"shared KV pool)")
        else:
            mode = (f"split boot (`-np 4` explicit, `kv_unified='false'`, "
                    f"per-slot window {s.get('n_ctx_slot')} = ctx/4)")
        rows.append(f"ctx {ctx}: {mode}")
    rider = ""
    if vmap and "gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified" in vmap:
        u = vmap["gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified"]["metrics"]
        s = vmap["gguf-hip-udq4kxl-auto-base-c4-ctx131072"]["metrics"]
        rider = (f" (the unified-default-boot c4@131072 rider is measured: "
                 f"`gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified` — "
                 f"{fmt(u['per_stream_tok_s_median'])} tok/s healthy-median / "
                 f"{fmt(u['aggregate_tok_s'])} aggregate vs split-mode "
                 f"{fmt(s['per_stream_tok_s_median'])} / "
                 f"{fmt(s['aggregate_tok_s'])}; unified boot degrades "
                 f"interactivity, 3-of-4 streams early-EOS)")
    return ("Note on the `c4` rows (slot semantics, METHODOLOGY §6): `c4` is "
            "not one configuration across ctx tiers — " + "; ".join(rows)
            + ". Compare like with like" + rider + ".")


def render_benchmark_md(data: dict) -> str:
    v = data["vmap"]
    d = dist(data)
    m = data["matrix"]
    planned = sum(1 for c in m["cells"] if c["status"] == "planned")
    dropped = sum(1 for c in m["cells"] if c["status"] == "dropped")
    gguf_ids = sorted(i for i in v if i.startswith("gguf-"))
    vllm_ids = sorted(i for i in v if i.startswith("vllm-"))

    out = []
    out.append("# Benchmark matrix results — Qwen3.8-27B on gfx1151 (ROCm 7.14)\n")
    out.append("<!-- GENERATED FILE — do not hand-edit. "
               "Regenerate: python3 scripts/render-readme-blocks.py -->\n")
    out.append(
        f"**{len(v)} measured cells: {d.get('recommended', 0)} recommended / "
        f"{d.get('caution', 0)} caution / {d.get('avoid', 0)} avoid** "
        f"({planned} planned — time-boxed session, machinery complete; "
        f"{dropped} dropped — vLLM ctx-32768 tier not offered). "
        f"Method: [`METHODOLOGY.md`](METHODOLOGY.md) (rules frozen before any "
        f"measurement). {review_attribution(data['verdicts'])}\n")
    out.append("Generated by `scripts/gen-verdicts.py` + "
               "`scripts/render-readme-blocks.py` from the raw cells under "
               "`matrix-714/cells/` — every number below is reproducible from "
               "those receipts.\n")

    out.append("## Quickstart mapping (the UX guarantee)\n")
    out.append("The user-facing defaults map to measured, verdicted cells — "
               "a quickstart can never point at a pit (CI-enforced by "
               "`tests/test_verdicts.py::test_quickstart_configs_are_recommended`):\n")
    out.append("| User-facing default | Cell | Verdict |")
    out.append("|---|---|---|")
    for label, cid in (
            ("`scripts/gguf-quickstart.sh` default boot (UD-Q4_K_XL, ctx 131072)",
             "gguf-hip-udq4kxl-auto-base-c1-ctx131072"),
            ("`WITH_MTP=1` opt-in", "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072"),
            ("`BACKEND=vulkan` + `WITH_MTP=1` opt-in (recommended, 2026-08-18)",
             "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"),
            ("`scripts/03-serve-vllm.sh` (`serve-args.conf`, 262144)",
             "vllm-bf16-auto-base-c1-ctx262144"),
            ("`scripts/03-serve-vllm.sh --mtp` (`serve-args-mtp.conf`)",
             "vllm-bf16-auto-mtp-c1-ctx262144")):
        c = v[cid]
        out.append(f"| {label} | `{cid}` | {mark(c['verdict'])} "
                   f"{c['verdict']} |")
    out.append("\nController ruling (2026-08-17, binding): all 8 measured "
               "vLLM cells are below the 10 tok/s interactive floor — the "
               "vLLM c1 cells are `caution` **with non-empty conditions**: "
               "\"per-stream < 10 tok/s on this host: use for 262144-context, "
               "vision, and aggregate batch throughput (to 38.6 tok/s), and "
               "as the greedy-degradation-free path; interactive chat → GGUF "
               "path (mtp-c1 13.0 tok/s)\". README quickstart guidance points "
               "at the GGUF path.\n")
    vk_mtp = v["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["metrics"]
    hip_mtp = v["gguf-hip-udq4kxl-auto-mtp-c1-ctx131072"]["metrics"]
    vk_mtp4 = v["gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072"]["metrics"]
    hip_mtp4 = v["gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072"]["metrics"]
    ev = GEN_VERDICTS.stability_evidence()
    s2_m1 = ev["cells"]["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["s2_2dp"]
    s2_m4 = ev["cells"]["gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072"]["s2_2dp"]
    delta_range = [
        (c["s2"] / c["s1"] - 1) * 100 for c in ev["cells"].values()]
    headline2 = (s2_m1 / hip_mtp["per_stream_tok_s_median"] - 1) * 100
    same_depth2 = (s2_m4 / hip_mtp4["per_stream_tok_s_median"] - 1) * 100
    # Session-1 (v0.1.2 corpus) same-depth depth-4 pairing, interpolated
    # from the same verdict metrics the ruling note quotes (2026-08-18
    # v0.1.3 debt fix: the old hand literal "+18.0%" mis-rounded the exact
    # 15.05/12.76 arithmetic, which is +17.9%).
    same_depth1 = ((vk_mtp4["per_stream_tok_s_median"]
                    / hip_mtp4["per_stream_tok_s_median"] - 1) * 100)
    out.append(
        "Controller ruling (2026-08-18, binding, v0.1.2 plan outcome (a); "
        "stability wording upgraded 2026-08-18, v0.1.3):\n"
        "`BACKEND=vulkan` is promoted in the gguf-quickstart echo as the "
        "recommended OPT-IN for best single-stream tok/s — vulkan mtp-c1 "
        f"{fmt(vk_mtp['per_stream_tok_s_median'], 2)} vs hip "
        f"{fmt(hip_mtp['per_stream_tok_s_median'], 2)} tok/s "
        f"(+{(vk_mtp['per_stream_tok_s_median'] / hip_mtp['per_stream_tok_s_median'] - 1) * 100:.1f}% "
        "mixed-depth headline; the clean same-depth depth-4 pairing is "
        f"{fmt(vk_mtp4['per_stream_tok_s_median'], 2)} vs "
        f"{fmt(hip_mtp4['per_stream_tok_s_median'], 2)} tok/s, "
        f"+{same_depth1:.1f}%), anchors clean 6/6 — while the "
        "quickstart DEFAULT stays `hip`. Stability evidence "
        f"(`{ev['pointer']}`): two independent measurement sessions "
        "(2026-08-18, hours apart, independent server boots) + 30-min "
        f"sustained soak ({ev['soak']['cycles']} cycles, "
        f"{ev['soak']['settle_pct']:+.1f}% settle) — session-2 reproduced "
        f"every c1 cell within {min(delta_range):+.1f}%…"
        f"{max(delta_range):+.1f}% per-stream, anchors 7/7 across "
        "all runs; remaining limits: one host (gfx1151), one ICD "
        "(RADV 25.2.8), same-day sessions, boot-per-cell, and the soak "
        "covers sustained load only. NO default flip, read the arithmetic "
        "(recorded so the session-2 headline is never misread as a "
        "trigger): the pre-registered flip rule requires >25% AND "
        "stability — the session-2 headline "
        f"{s2_m1:.2f} vs {fmt(hip_mtp['per_stream_tok_s_median'], 2)} tok/s "
        f"is exactly {headline2:+.1f}% (NOT >25%) and stays mixed-depth; "
        "the clean same-depth d4 pairing is "
        f"{s2_m4:.2f} vs {fmt(hip_mtp4['per_stream_tok_s_median'], 2)} "
        f"tok/s, {same_depth2:+.1f}%. MTP depth 1 stays the "
        "recommended variant on both backends (depth 4 never beats it); "
        "cross-depth caveat: the hip 13.0 receipt ran the implicit "
        "`--spec-draft-n-max` default 3 while every v0.1.2 cell passes "
        "depth explicitly "
        "(`configs/validated-stack.json` `llama_cpp_vulkan.mtp_depth.note`). "
        "The unified-default-boot c4@131072 rider is measured-with-caveat "
        "(degrades interactivity vs split boot; no config change).\n")

    out.append("\n## GGUF path (llama.cpp `4df29be4`, UD-Q4_K_XL; Backend "
               "column from the cell id)\n")
    per_backend: dict[str, int] = {}
    for cid in gguf_ids:
        per_backend[backend_of(cid)] = per_backend.get(backend_of(cid), 0) + 1
    backend_bits = " + ".join(
        f"{n} `{b}`" + (" (ROCm build-714, incl. the mtp4 depth cell and "
                        "the unified-boot c4 rider)" if b == "hip" else
                        " (build-714-vk, Mesa RADV — the v0.1.2 cells)"
                        if b == "vulkan" else "")
        for b, n in sorted(per_backend.items()))
    out.append("Per-stream medians over **healthy streams only** (≥2 content "
               "tokens — streams with <2 tokens carry no defined TPOT and "
               "never count toward UX claims; see healthy-vs-total in the raw "
               f"cells). Measured gguf cells: {backend_bits}.\n")
    out.append("| Cell | Backend | Verdict | Per-stream med tok/s | min | "
               "TPOT med ms | Aggregate tok/s | TTFT med | Anchor | GTT MiB "
               "| auto → final |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for cid in gguf_ids:
        out.append(_row(cid, data))

    out.append("\n" + gguf_c4_slot_note(data["cells"], v) + "\n")

    out.append("\n## vLLM path (`4d2a68d`, BF16, ctx 262144)\n")
    kv = parse_kv_line(data["cells"]["vllm-bf16-auto-base-c1-ctx262144"])
    out.append(
        f"Boots: base healthy in 171 s (GTT 75,040 MiB: weights "
        f"{fmt(kv.get('weights_gib'))} GiB, KV {fmt(kv.get('kv_gib'), 2)} GiB, "
        f"rest activations/buffers — KV = {kv.get('kv_tokens', 0):,} tokens "
        f"= {kv.get('concurrency_x')}x the 262,144 max-len); mtp healthy in "
        f"226 s (KV 18.59 GiB = 279,146 tokens = 1.06x). Engine args "
        f"captured verbatim per cell; `max_num_seqs` never overridden (pin "
        f"default 1024). All 8 greedy anchors `OK` — the GGUF §6 pit does "
        f"not reproduce on this path.\n")
    out.append("| Cell | Verdict | Per-stream med tok/s | min | TPOT med ms "
               "| Aggregate tok/s | TTFT med | Anchor | GTT MiB | auto → final |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for cid in vllm_ids:
        out.append(_row(cid, data))

    out.append("\n## MTP effect (basis labeled)\n")
    out.append("| Config | Backend | Per-stream basis | Aggregate basis | Verdict |")
    out.append("|---|---|---|---|---|")
    for cid in sorted(v):
        g = v[cid]["metrics"].get("mtp_gain_vs_base")
        if not g:
            continue
        base_cid = cid.replace("-mtp-", "-base-").replace("-mtp4-", "-base-")
        out.append(
            f"| `{short_id(cid)}` vs {short_id(base_cid)} | "
            f"{backend_of(cid) or '—'} | "
            f"{g['per_stream_pct']:+.1f}% "
            f"({fmt(v[cid]['metrics']['per_stream_tok_s_median'], 2)} vs "
            f"{fmt(g['base_per_stream_tok_s_median'], 2)} tok/s) | "
            f"{g['aggregate_pct']:+.1f}% ({fmt(v[cid]['metrics']['aggregate_tok_s'], 2)} "
            f"vs {fmt(g['base_aggregate_tok_s'], 2)} tok/s) | "
            f"{mark(v[cid]['verdict'])} {v[cid]['verdict']} |")
    out.append("\nRead: MTP is the interactive win on the GGUF path "
               "(+28.2% per-stream at c1) and beneficial through c8 on the "
               "vLLM path (+33%/+27% per-stream at c4/c8, aggregate "
               "+21%/+9%), but inverts at vLLM c16 (−19.4% aggregate — the "
               "avoid cell; muse-rocm DFlash lesson mirrored). On the GGUF "
               "path the hip c8/c16 MTP cells are degraded by the §6 anchor "
               "pit, so their negative deltas are pit artifacts, not MTP "
               "evidence (the pit does NOT reproduce on Vulkan, whose c8/c16 "
               "tiers are unmeasured; on Vulkan the c4 MTP regressions are "
               "real cells, anchor-clean). v0.1.2: MTP depth 1 beats depth 4 "
               "on both backends at c1 (vulkan 16.00 vs 15.05; hip 13.00 vs "
               "12.76 tok/s) — depth 1 stays the recommended variant; "
               f"cross-backend at c1 Vulkan leads HIP at both depths (+23.1% "
               f"mixed-depth headline, +{same_depth1:.1f}% at fixed depth 4 — "
               f"the hip mtp "
               "receipts of 2026-08-17 ran the implicit depth default 3, "
               "see `configs/validated-stack.json`).\n")

    out.append("## Context capacity & retrieval smoke\n")
    out.append(render_context_capacity(data))
    out.append("\n## Verdict rule application\n")
    out.append(
        "- Rung 1 (abort/OOM/hang): not triggered — no boot failures, zero "
        "failed streams in any cell.\n"
        "- Rung 1b (anchor drift, METHODOLOGY §6): 5 GGUF cells → avoid "
        "(the `'////'` greedy-degradation pit; correlation with all-capped "
        "benches stated honestly per the corrected §6 erratum — 4-of-5 "
        "all-capped, mtp-c8 7-of-8).\n"
        "- Rung 2 (interactive floor): every remaining below-floor cell → "
        "caution (severity band <8 tok/s at c1 proposed avoid on the two "
        "vLLM c1 cells; see overrides).\n"
        "- Rung 3 (aggregate regression): 1 confirmed avoid — "
        "`vllm-bf16-auto-mtp-c16-ctx262144` (31.11 vs 38.58 tok/s vs its "
        "base counterpart, −19.4%).\n"
        "- Controller overrides (recorded per cell in the verdicts JSON "
        "`metrics.controller_override`): 3 — the two vLLM c1 cells "
        "avoid→caution and mtp-c16 caution→avoid, all citing the "
        "2026-08-17 ruling.\n"
        "- Controller review 2026-08-18 (v0.1.2): the 8 new cells took their "
        "MECHANICAL verdicts — no overrides (`controller_override` null) — "
        "with the quickstart ruling recorded per cell (reason + "
        "`metrics.reviewed_by` = `controller-2026-08-18`): vulkan promoted "
        "as the recommended quickstart OPT-IN (default stays hip), mtp "
        "depth 1 over depth 4 on both backends, unified rider "
        "measured-with-caveat. Two prose-template defects (a mislabeled "
        "'c1:' basis with a fixed 'Better than base' direction in the "
        "c4-caution MTP sentence; the hip-family pit clause leaking into "
        "vulkan conditions) were corrected in the same release.\n")
    out.append(reasoning_moot_mark(data["cells"]) + "\n")
    out.append("\n## Raw receipts\n")
    out.append("Every cell links from the tables above; the declaration "
               "manifest is [`matrix-714/matrix.json`](matrix-714/matrix.json), "
               "the measurement contract is "
               "[`METHODOLOGY.md`](METHODOLOGY.md), and the long-context "
               "smoke receipt is "
               "[`matrix-714/long-context-smoke.json`](matrix-714/long-context-smoke.json).\n")
    return "\n".join(out).rstrip() + "\n"


# ------------------------------------------------------------------- plumbing

def update_readme(data: dict, write: bool = True) -> bool:
    """Replace the generated blocks; returns whether anything would change.
    With write=False (check mode) nothing is written."""
    text = README.read_text()
    changed = False
    rendered = {
        "performance-highlights": render_performance_highlights(data),
        "context-capacity": render_context_capacity(data),
        "known-good-bad": render_known_good_bad(data),
    }
    for name in BLOCKS:
        begin = f"<!-- BEGIN GENERATED: {name} -->"
        end = f"<!-- END GENERATED: {name} -->"
        if begin not in text or end not in text:
            raise SystemExit(f"README.md missing generated-block markers for "
                             f"{name!r} — add the marker pair by hand once, "
                             f"then regenerate.")
        pattern = re.compile(
            re.escape(begin) + r"\n(?:.*?\n)?" + re.escape(end), re.S)
        replacement = begin + "\n" + rendered[name] + "\n" + end
        new_text, n = pattern.subn(replacement, text, count=1)
        if n != 1:
            raise SystemExit(f"README.md: could not substitute block {name!r}")
        changed |= new_text != text
        text = new_text
    if changed and write:
        README.write_text(text)
    return changed


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    check = "--check" in args
    data = load_data()
    readme_changed = update_readme(data, write=not check)
    # One regen covers all README blocks: the hardware-matrix renderer
    # (project + community + planned platform rows) runs on the same pass.
    hw_changed = HARDWARE_MATRIX.update_readme(write=not check)
    bench = render_benchmark_md(data)
    bench_changed = not (BENCH_MD.exists() and BENCH_MD.read_text() == bench)
    if bench_changed and not check:
        BENCH_MD.write_text(bench)
    if check:
        stale = []
        if readme_changed or hw_changed:
            stale.append("README.md")
        if bench_changed:
            stale.append("docs/results/benchmark.md")
        if stale:
            print(f"STALE: {', '.join(stale)} differ from a fresh render — "
                  f"rerun scripts/render-readme-blocks.py", file=sys.stderr)
            return 1
        print("fresh: README blocks + docs/results/benchmark.md")
        return 0
    print(f"README blocks {'updated' if readme_changed else 'unchanged'}"
          f"{' (+ hardware matrix)' if hw_changed else ''}; "
          f"benchmark.md {'written' if bench_changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
