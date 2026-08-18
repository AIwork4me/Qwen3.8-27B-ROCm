#!/usr/bin/env python3
"""Task 5: verdict generator — configs/benchmark-verdicts.json.

Reads the raw matrix cells (docs/results/matrix-714/cells/*.json) plus
matrix.json, applies the pre-declared auto-verdict ladder (METHODOLOGY.md §3,
frozen 2026-08-17 BEFORE any measurement), then the dated controller-review
layer ("the ladder proposes; the controller disposes" — §3 Final authority),
and emits the verdicts JSON consumed by the README generator and the anti-pit
CI test.

Usage:
    python3 scripts/gen-verdicts.py           # write configs/benchmark-verdicts.json
    python3 scripts/gen-verdicts.py --check   # exit 1 if the committed file is stale

Output is deterministic: ids sorted, floats rounded at emission, no wall-clock
timestamps — `--check` is a byte comparison, safe as a CI freshness gate.

2026-08-18 backend-dimension migration (v0.1.2 Vulkan×MTP): gguf cell ids
carry an explicit -hip-|-vulkan- tag (legacy unprefixed ids ARE hip) and an
mtp4 depth variant; vLLM ids are unchanged. Verdict CONTENT is unaffected
by the migration — ids aside, regeneration is byte-stable (families and
base-counterparts are matched within one backend; hip and vulkan never mix).

2026-08-18 Task 4 (verdicts + ruling): the 8 v0.1.2 cells carry the
controller-2026-08-18 review (per-cell `metrics.reviewed_by` plus a ruling
note in each reason — the quickstart opt-in promotion, the
depth-1-over-depth-4 finding, the unified-rider finding); the frozen
2026-08-17 review continues to govern the 20 migrated cells. Two
prose-template defects disclosed by the verifier were fixed in the same
release (the c4-caution MTP sentence now follows the actual
numbers/basis instead of asserting "Better than base" with a mislabeled
"c1:" tag; the hip-family "c8/c16 hit the pit" clause is gated on the
backend), and the unified-default c4 caveat was rewritten — the v0.1.2
rider MEASURED that configuration.

2026-08-18 stability follow-up S2 (v0.1.3): the "single-session Vulkan
runtime" caveat in the v0.1.2 ruling note is upgraded to the two-session +
soak wording (session-2 receipts + the 30-min soak live under
docs/results/matrix-714/stability/ — receipts-only, never matrix cells),
and the no-flip arithmetic is recorded in the note so the session-2
headline (+25.0% exactly) is never misread as the >25% default-flip
trigger. Wording upgrade ONLY: no verdict, metric, or default changes.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CELLS_DIR = ROOT / "docs" / "results" / "matrix-714" / "cells"
MATRIX = ROOT / "docs" / "results" / "matrix-714" / "matrix.json"
OUT = ROOT / "configs" / "benchmark-verdicts.json"

# METHODOLOGY §3 rung 2: per-stream TPOT < 10 tok/s at an interactive tier is
# not recommendable; severity band 8–10 tok/s -> caution, < 8 -> avoid.
INTERACTIVE_FLOOR_TOK_S = 10.0
FLOOR_CAUTION_BAND_TOK_S = 8.0
# §3 rung 3 tolerance: aggregate must regress by more than this fraction to
# be an avoid-candidate (guards against noise-level "regressions").
REGRESSION_TOLERANCE = 0.05

LEGACY_REVIEW_DATE = "2026-08-17"  # the frozen review of the 20 migrated cells
CONTROLLER_REVIEW_DATE = "2026-08-18"  # v0.1.2 review; produced this file state
REVIEWED_BY = f"controller-{CONTROLLER_REVIEW_DATE}"


def parse_cell_id(cid: str) -> dict:
    """Both grammar forms (2026-08-18 backend-dimension migration):
    gguf-{backend}-udq4kxl-auto-{mtp}-c{N}-ctx{K}(-unified)? and the
    unchanged vllm-bf16-auto-{mtp}-c{N}-ctx{K}."""
    parts = cid.split("-")
    if parts[0] == "gguf":
        backend, weight, kv, mtp, c, ctx = parts[1:7]
        return {"path": "gguf", "backend": backend, "weight": weight,
                "kv": kv, "mtp": mtp, "c": int(c[1:]), "ctx": int(ctx[3:]),
                "unified": cid.endswith("-unified")}
    path, weight, kv, mtp, c, ctx = parts
    return {"path": path, "backend": None, "weight": weight, "kv": kv,
            "mtp": mtp, "c": int(c[1:]), "ctx": int(ctx[3:]),
            "unified": False}


def fmt(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}"


def mib_to_gib(mib: float) -> float:
    return round(mib / 1024, 1)


# --------------------------------------------------------------------- metrics

def compute_metrics(cell: dict) -> dict:
    """Headline numbers for one raw cell.

    Healthy streams (the c4 caveat, controller review 2026-08-17): a stream
    with < 2 content tokens carries no defined TPOT (the client emits null,
    or a degenerate 0.0 when two deltas share a timestamp). Such streams are
    excluded from every per-stream UX statistic — they must not count toward
    latency claims — but remain visible via healthy_streams vs streams.
    """
    client = cell["client"]
    streams = client["streams"]
    healthy = [s for s in streams
               if s.get("ok") and s.get("tpot_ms") and s["tpot_ms"] > 0
               and (s.get("completion_tokens") or 0) >= 2]
    tps = sorted(1000.0 / s["tpot_ms"] for s in healthy)
    ttfts = [s["ttft_ms"] for s in streams
             if s.get("ok") and s.get("ttft_ms") is not None]
    agg = client["aggregate"]
    return {
        "streams": len(streams),
        "ok_streams": agg["ok_streams"],
        "failed_streams": agg["failed_streams"],
        "healthy_streams": len(healthy),
        "per_stream_tok_s_median": round(statistics.median(tps), 2) if tps else None,
        "per_stream_tok_s_min": round(tps[0], 2) if tps else None,
        "tpot_ms_median": round(statistics.median(
            [s["tpot_ms"] for s in healthy]), 1) if healthy else None,
        "ttft_ms_median": round(statistics.median(ttfts), 1) if ttfts else None,
        "aggregate_tok_s": round(agg["tok_per_s"], 2),
        "wall_s": round(agg["wall_s"], 1),
        "anchor_ok": bool(cell.get("anchor", {}).get("ok")),
        "boot_ok": bool(cell.get("boot", {}).get("ok", True)),
        "gtt_mib": (cell.get("load") or {}).get("gtt_mib"),
        "vram_mib": (cell.get("load") or {}).get("vram_mib"),
        "min_completion_tokens": min(
            (s.get("completion_tokens") or 0) for s in streams) if streams else None,
        "capped_streams": sum(1 for s in streams
                              if s.get("finish_reason") == "length"),
    }


# ------------------------------------------------------------------ the ladder

def _regression(m: dict) -> dict | None:
    """§3 rung 3: aggregate regression vs (a) the same family's best
    lower-concurrency aggregate and (b) — for mtp cells — the BASE
    counterpart at the same concurrency (MTP is a pure add-on; regressing vs
    its own baseline is the pre-declared avoid-candidate, the muse-rocm
    DFlash lesson mirrored by the controller ruling)."""
    this = m.get("aggregate_tok_s")
    if this is None:
        return None
    candidates = []
    lower = m.get("lower_aggregate_best")
    if lower is not None:
        candidates.append(("lower-concurrency cell of the same family", lower))
    base = m.get("base_aggregate")
    if base is not None:
        candidates.append(("base counterpart at the same concurrency", base))
    worst = None
    for label, other in candidates:
        if other and this < other * (1.0 - REGRESSION_TOLERANCE):
            pct = (this / other - 1.0) * 100.0
            if worst is None or pct < worst["pct"]:
                worst = {"vs": label, "other": round(other, 2),
                         "pct": round(pct, 1)}
    return worst


def auto_ladder(m: dict) -> dict:
    """The pre-declared ladder (METHODOLOGY §3), mechanically applied. Pure
    function of one cell's metrics dict (+ family context injected by the
    caller: lower_aggregate_best, base_aggregate). First matching rung wins.

    Tier framing (§1/§2 journey): c1 is S1 — always interactive, full
    severity. c4/c8 are interactive-shaped multi-user tiers — below-floor is
    always at least caution. c16 is the batch/throughput presentation — the
    floor still forces the honesty clause (never a bare pass), and rung 3
    regressions still demote.
    """
    reg = _regression(m)
    avoid_candidate = reg is not None

    # Rung 1 — abort / OOM / hang / boot failure / failed stream.
    if not m.get("boot_ok", True) or m.get("failed_streams", 0) > 0:
        return {"verdict": "avoid", "rung": "rung1-abort",
                "avoid_candidate": True,
                "reason": "Abort-class failure in the raw cell (boot failure "
                          "or failed streams): pre-declared rung 1 — avoid."}

    # Rung 1b — greedy byte-identity anchor broken (METHODOLOGY §6 pit).
    if not m.get("anchor_ok", True):
        return {"verdict": "avoid", "rung": "rung1b-anchor-drift",
                "avoid_candidate": True,
                "reason": "Greedy byte-identity anchor failed — the llama.cpp "
                          "degradation pit (METHODOLOGY §6); the floor is moot "
                          "when correctness itself is untrustworthy."}

    med = m.get("per_stream_tok_s_median")
    c = m.get("c", 1)

    # Rung 3 first-check on the way down: an aggregate regression at a
    # floor-passing tier is the avoid-candidate of the pre-declared rule.
    if reg is not None and med is not None and med >= INTERACTIVE_FLOOR_TOK_S:
        return {"verdict": "avoid", "rung": "rung3-aggregate-regression",
                "avoid_candidate": True,
                "reason": f"Aggregate regresses vs the {reg['vs']} "
                          f"({m['aggregate_tok_s']} vs {reg['other']} tok/s, "
                          f"{reg['pct']}%): rung-3 avoid-candidate confirmed "
                          f"against the raw cell."}

    # Rung 2 — the interactive floor.
    if med is not None and med < INTERACTIVE_FLOOR_TOK_S:
        if c == 1:
            verdict = ("caution" if med >= FLOOR_CAUTION_BAND_TOK_S else "avoid")
        else:
            verdict = "caution"
        return {"verdict": verdict,
                "rung": "rung2-interactive-floor" if verdict == "caution"
                        else "rung2-interactive-floor-severe",
                "avoid_candidate": avoid_candidate,
                "reason": f"Per-stream median {fmt(med)} tok/s is below the "
                          f"{fmt(INTERACTIVE_FLOOR_TOK_S, 0)} tok/s interactive "
                          f"floor at c{c}: not recommendable for interactive "
                          f"presentation (aggregate {m['aggregate_tok_s']} "
                          f"tok/s is the batch figure, never the headline)."}

    # Rung 4 — clean.
    return {"verdict": "recommended", "rung": "rung4-clean",
            "avoid_candidate": avoid_candidate,
            "reason": "Clean cell: boot healthy, anchor byte-identical, "
                      "per-stream at/above the interactive floor."}


# ------------------------------------------------------- controller review layer
#
# The ladder proposes; the controller disposes (METHODOLOGY §3 Final
# authority). Every override below is dated, cites the ruling, and is
# recorded per cell in the emitted JSON (metrics.controller_override) so an
# audited trail exists from raw cell -> auto verdict -> final verdict.

CONTROLLER_OVERRIDES: dict[str, dict] = {
    "vllm-bf16-auto-base-c1-ctx262144": {
        "verdict": "caution",
        "note": "Controller ruling 2026-08-17: rung 2 proposed avoid (4.3 "
                "tok/s < 8 at the S1 tier); disposed CAUTION — the cell is "
                "healthy (anchor clean, zero failed streams) and this path is "
                "the only one serving 262144 context + vision + the highest "
                "aggregate batch throughput. The floor miss is a property of "
                "BF16 on this host, recorded as conditions, not a pit.",
    },
    "vllm-bf16-auto-mtp-c1-ctx262144": {
        "verdict": "caution",
        "note": "Controller ruling 2026-08-17: rung 2 proposed avoid (6.5 "
                "tok/s < 8 at the S1 tier); disposed CAUTION per the same "
                "ruling — MTP is a real +53% per-stream win on this path but "
                "still below the floor; conditions carry the redirect.",
    },
    "vllm-bf16-auto-mtp-c16-ctx262144": {
        "verdict": "avoid",
        "note": "Controller ruling 2026-08-17: the rung-3 avoid-CANDIDATE "
                "(aggregate 31.1 vs base-c16 38.6 tok/s, ~-19%) is CONFIRMED "
                "against the raw cell — the speculative win inverts at c16 "
                "(the muse-rocm DFlash lesson mirrored); disposed AVOID.",
    },
}

# Per-cell review prose (merged into reasons/conditions on top of the
# metrics-derived text; numbers are interpolated from the raw cells so this
# prose can never drift from the receipts).
# Updated 2026-08-18 (step 2c): the upstream control experiments
# (docs/results/upstream-controls/) established the pit is live at master HEAD
# 01818e495 and that candidate fix PR #25863 removes it on this host; existing
# trackers #25992 (primary, same host — maintainer invited PR testing) and
# #23577 (////-family) cover us, so no new issue is filed.
GGUF_PIT_UPSTREAM = ("llama.cpp HIP on gfx1151 — live at master HEAD 01818e495 "
                     "(2026-08-17), same pit as the 4df29be4 pin; candidate fix "
                     "PR #25863 https://github.com/ggml-org/llama.cpp/pull/25863 "
                     "differentially verified on this host (patched 2/2 anchor "
                     "PASS vs unpatched 3/3 FAIL on the idle host; receipts "
                     "docs/results/upstream-controls/); tracked upstream in "
                     "#25992 https://github.com/ggml-org/llama.cpp/issues/25992 "
                     "(primary — same-host bisect, maintainer invited testing "
                     "of the PR) and #23577 "
                     "https://github.com/ggml-org/llama.cpp/issues/23577 "
                     "(////-family); exact mechanism unresolved at session "
                     "close (METHODOLOGY §6)")
GGUF_PIT_WORKAROUND = ("Restart the server to restore greedy decoding; for "
                       "multi-stream loads use the vLLM path — all 8 vLLM "
                       "anchors stayed clean, including anchors run "
                       "immediately after 16-stream benches (METHODOLOGY §7).")

# Final-review caveat, UPDATED 2026-08-18 (Task 4): the v0.1.2 unified rider
# MEASURED the configuration the 2026-08-17 final review had to bracket —
# the "was NOT measured" wording is gone. Finding (measured-with-caveat):
# unified-default-boot c4@131072 DEGRADES interactivity vs split-mode c4 on
# the 8060S (healthy-stream median and aggregate both down; 3-of-4 streams
# early-EOS so the unified aggregate is not comparable). Recorded on the two
# recommended quickstart c1 cells (mirrored in the README quickstart) and on
# the rider's own verdict; numbers interpolate from the receipts.
QUICKSTART_C4_CAVEAT_CELLS = (
    "gguf-hip-udq4kxl-auto-base-c1-ctx131072",
    "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072",
)
UNIFIED_RIDER_ID = "gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified"
SPLIT_C4_131072_ID = "gguf-hip-udq4kxl-auto-base-c4-ctx131072"
# "Early EOS" for the rider prose: a stream that stops (finish_reason=stop)
# within this many tokens never produced a real answer (the rider receipt:
# 2/4/8-token stops + one full 221-token answer). Stated in the prose, not
# a verdict metric — healthy-stream exclusion stays the UX rule.
EARLY_EOS_MAX_TOKENS = 8


def early_eos_streams(cell: dict) -> int:
    return sum(1 for s in cell["client"]["streams"]
               if s.get("finish_reason") == "stop"
               and (s.get("completion_tokens") or 0) <= EARLY_EOS_MAX_TOKENS)


def quickstart_c4_caveat(all_metrics: dict | None,
                         unified_cell: dict | None) -> str:
    u, s = all_metrics[UNIFIED_RIDER_ID], all_metrics[SPLIT_C4_131072_ID]
    early = early_eos_streams(unified_cell) if unified_cell else None
    eos_txt = (f"{early}-of-{u['streams']} streams stopped within "
               f"{EARLY_EOS_MAX_TOKENS} tokens — early EOS — so the "
               f"aggregate {fmt(u['aggregate_tok_s'])} tok/s is not "
               f"comparable"
               if early is not None else
               f"{u['streams'] - u['healthy_streams']}-of-{u['streams']} "
               f"streams carry no defined TPOT (aggregate not comparable)")
    return (f"Caveat (measured 2026-08-18, rider `{UNIFIED_RIDER_ID}`): "
            f"unified-default-boot c4 at ctx 131072 (the stock quickstart's "
            f"4-slot default under 4 concurrent users) measures "
            f"{fmt(u['per_stream_tok_s_median'])} tok/s healthy-stream median "
            f"({eos_txt}) "
            f"vs the split-mode c4 cell "
            f"{fmt(s['per_stream_tok_s_median'])} tok/s median / "
            f"{fmt(s['aggregate_tok_s'])} tok/s aggregate — unified default "
            f"boot degrades interactivity; prefer the split boot "
            f"(`EXTRA_ARGS='-np 4'`) for light multi-user. Single-stream use "
            f"is unaffected.")


# ---------------------------------------------- v0.1.2 controller ruling (T4)
#
# Task 4 ruling (2026-08-18) — plan outcome (a), the pre-registered rule
# triggered; recorded, not re-deliberated: `BACKEND=vulkan` is promoted in
# the gguf-quickstart echo as the recommended OPT-IN for best single-stream
# tok/s (the "experimental, see verdicts" note kept); the quickstart DEFAULT
# stays hip. Trigger: >=15% win over hip mtp-c1 AND anchor-clean —
# mixed-depth headline +23.1% (16.0 vs 13.0 tok/s) plus the clean
# same-depth depth-4 pairing +18.0% (15.05 vs 12.76 tok/s, both explicit
# depth 4, same day); 6/6 vulkan anchors clean. Default unchanged because
# the headline is <25%, the Vulkan runtime is single-session, and one ICD
# (RADV 25.2.8) is covered. mtp (depth 1) stays the recommended variant on
# both backends — depth 4 never beats depth 1 on either. The unified rider
# is measured-with-caveat, no config change.
#
# v0.1.3 addendum (2026-08-18, S2 — wording upgrade ONLY, recorded, not
# re-deliberated): the stability follow-up replaced the "single-session"
# caveat with two independent measurement sessions (2026-08-18, hours
# apart, independent server boots) + a 30-min sustained soak (108 cycles,
# -2.6% settle; docs/results/matrix-714/stability/). The DEFAULT still
# stays hip: the pre-registered flip rule requires >25% AND stability, and
# the session-2 headline 16.25 vs 13.00 tok/s is EXACTLY +25.0% (not >25%),
# still mixed-depth — the clean same-depth d4 pairing on session-2 numbers
# is 15.25 vs 12.76 tok/s, +19.5%. That arithmetic is quoted in the ruling
# note below so nobody misreads +25.0% as a trigger.
V012_REVIEWED_BY = "controller-2026-08-18"
V012_CELLS = frozenset({
    "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-base-c4-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp-c4-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp4-c4-ctx131072",
    "gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072",
    UNIFIED_RIDER_ID,
})

# The cross-depth caveat (configs/validated-stack.json
# llama_cpp_vulkan.mtp_depth.note): the historical hip mtp receipts
# (2026-08-17) ran the IMPLICIT --spec-draft-n-max default 3; every v0.1.2
# cell passes its depth explicitly. Cited wherever a hip-vs-vulkan MTP
# number is quoted.
CROSS_DEPTH_CAVEAT = ("the hip mtp-c1 receipt (2026-08-17) ran the implicit "
                      "--spec-draft-n-max default 3 while every v0.1.2 cell "
                      "passes its depth explicitly "
                      "(configs/validated-stack.json llama_cpp_vulkan."
                      "mtp_depth.note)")


def _pct(this: float, other: float) -> str:
    return f"{(this / other - 1) * 100:+.1f}%"


# ------------------------------------------- stability evidence (S2, v0.1.3)
#
# Session-2 receipts + the 30-min soak live OUTSIDE the matrix corpus (the
# S1 constraint: new-facts-new-receipts, docs/results/matrix-714/matrix.json
# and the 28 cells are untouched), but the v0.1.3 wording upgrade quotes
# them — so they are loaded here and interpolated with the same
# never-drift convention as the cells (moved/edited receipts fail the
# regen loudly instead of letting the prose drift).
STABILITY_DIR = ROOT / "docs" / "results" / "matrix-714" / "stability"
SESSION2_DIR = STABILITY_DIR / "session2-2026-08-18"
STABILITY_POINTER = "docs/results/matrix-714/stability/"
STABILITY_CELLS = (
    "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072",
)


def _c1_stream_tok_s(cell: dict) -> float:
    """Exact (unrounded) per-stream tok/s of a c1 cell's healthy stream.
    Session-2 deltas are computed on exact values so +1.5% prints +1.5% —
    2dp-rounded operands would print +1.6%."""
    healthy = [s for s in cell["client"]["streams"]
               if s.get("ok") and s.get("tpot_ms") and s["tpot_ms"] > 0
               and (s.get("completion_tokens") or 0) >= 2]
    return statistics.median(1000.0 / s["tpot_ms"] for s in healthy)


def _load_stability_evidence() -> dict:
    ev = {"pointer": STABILITY_POINTER, "cells": {}}
    for cid in STABILITY_CELLS:
        s1 = _c1_stream_tok_s(
            json.loads((CELLS_DIR / f"{cid}.json").read_text()))
        s2 = _c1_stream_tok_s(
            json.loads((SESSION2_DIR / f"{cid}.json").read_text()))
        ev["cells"][cid] = {
            "s1": s1, "s2": s2,                       # exact, for deltas
            "s1_2dp": round(s1, 2), "s2_2dp": round(s2, 2),
            "delta_pct": _pct(s2, s1),
        }
    soak = json.loads((SESSION2_DIR /
                       "soak-gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json")
                      .read_text())
    meds = [c["stream_median_tok_s"] for c in soak["cycles"]]
    half = len(meds) // 2
    first, second = statistics.median(meds[:half]), statistics.median(meds[half:])
    ev["soak"] = {
        "cycles": soak["totals"]["cycles"],
        "ok_cycles": soak["totals"]["ok_cycles"],
        "first_half_2dp": round(first, 2),
        "second_half_2dp": round(second, 2),
        "settle_pct": round((second / first - 1) * 100, 1),
    }
    return ev


_STABILITY_EVIDENCE: dict | None = None


def stability_evidence() -> dict:
    """Memoized stability-evidence loader (lazy — importing this module,
    e.g. from the tests, must stay side-effect-free). Missing receipts
    raise FileNotFoundError on purpose: the v0.1.3 ruling note quotes this
    evidence, so regenerating without it must fail loudly rather than
    silently regress to pre-v0.1.3 wording."""
    global _STABILITY_EVIDENCE
    if _STABILITY_EVIDENCE is None:
        _STABILITY_EVIDENCE = _load_stability_evidence()
    return _STABILITY_EVIDENCE


def v012_ruling_note(cid: str, all_metrics: dict | None,
                     unified_cell: dict | None = None) -> str | None:
    """Per-cell controller-2026-08-18 review/ruling prose. Numbers are
    interpolated from the raw-cell metrics so the notes can never drift
    from the receipts (same convention as the review prose above)."""
    if cid not in V012_CELLS or not all_metrics:
        return None
    vk = {k: all_metrics[k] for k in V012_CELLS if k in all_metrics}
    vk_base1 = vk["gguf-vulkan-udq4kxl-auto-base-c1-ctx131072"]
    vk_mtp1 = vk["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]
    vk_mtp41 = vk["gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072"]
    hip_base1 = all_metrics["gguf-hip-udq4kxl-auto-base-c1-ctx131072"]
    hip_mtp1 = all_metrics["gguf-hip-udq4kxl-auto-mtp-c1-ctx131072"]
    hip_mtp41 = vk["gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072"]
    headline = _pct(vk_mtp1["per_stream_tok_s_median"],
                    hip_mtp1["per_stream_tok_s_median"])
    same_depth = _pct(vk_mtp41["per_stream_tok_s_median"],
                      hip_mtp41["per_stream_tok_s_median"])
    n_vk = len([k for k in all_metrics
                if parse_cell_id(k)["backend"] == "vulkan"])
    n_ok = len([k for k in all_metrics
                if parse_cell_id(k)["backend"] == "vulkan"
                and all_metrics[k]["anchor_ok"]])

    if cid == "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072":
        ev = stability_evidence()
        c1 = ev["cells"]
        m1 = c1["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]
        m4 = c1["gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072"]
        b1 = c1["gguf-vulkan-udq4kxl-auto-base-c1-ctx131072"]
        soak = ev["soak"]
        hip1_2dp = round(hip_mtp1["per_stream_tok_s_median"], 2)
        hip4_2dp = round(hip_mtp41["per_stream_tok_s_median"], 2)
        # The no-flip arithmetic uses the corpus 2dp convention (the same
        # numbers every surface prints): 16.25 vs 13.00 is EXACTLY +25.0%.
        headline2 = f"{(m1['s2_2dp'] / hip1_2dp - 1) * 100:+.1f}%"
        same_depth2 = f"{(m4['s2_2dp'] / hip4_2dp - 1) * 100:+.1f}%"
        return (f"Controller ruling 2026-08-18 (v0.1.2, plan outcome (a) — "
                f"pre-registered rule triggered; stability wording upgraded "
                f"same day, v0.1.3): promoted in the gguf-quickstart echo "
                f"as the recommended OPT-IN for best single-stream tok/s "
                f"({fmt(vk_mtp1['per_stream_tok_s_median'])} vs hip mtp-c1 "
                f"{fmt(hip_mtp1['per_stream_tok_s_median'])} tok/s, "
                f"{headline}); the quickstart DEFAULT stays hip and the "
                f"'experimental, see verdicts' label is kept. Stability "
                f"evidence ({ev['pointer']}): two independent measurement "
                f"sessions (2026-08-18, hours apart, independent server "
                f"boots) + 30-min sustained soak ({soak['cycles']} cycles, "
                f"{soak['settle_pct']:+.1f}% settle) — session-2 reproduced "
                f"every c1 cell (mtp {m1['s1_2dp']:.2f}→{m1['s2_2dp']:.2f} "
                f"{m1['delta_pct']}, mtp4 {m4['s1_2dp']:.2f}→"
                f"{m4['s2_2dp']:.2f} {m4['delta_pct']}, base "
                f"{b1['s1_2dp']:.2f}→{b1['s2_2dp']:.2f} {b1['delta_pct']}), "
                f"soak {soak['ok_cycles']}/{soak['cycles']} cycles clean "
                f"with zero health flaps and a clean post-soak anchor, "
                f"anchors 7/7 across all runs; remaining limits unchanged: "
                f"single host (gfx1151), single ICD (RADV 25.2.8), same-day "
                f"sessions, boot-per-cell — the soak covers sustained load "
                f"only. NO default flip, read the arithmetic (recorded so "
                f"{headline2} is never misread as a trigger): the "
                f"pre-registered flip rule requires >25% AND stability — "
                f"the session-2 headline {m1['s2_2dp']:.2f} vs hip "
                f"{hip1_2dp:.2f} tok/s is exactly {headline2} (NOT >25%), "
                f"and the headline is still MIXED-DEPTH; the clean "
                f"same-depth d4 pairing on session-2 numbers is "
                f"{m4['s2_2dp']:.2f} vs {hip4_2dp:.2f} tok/s, "
                f"{same_depth2}. Cross-depth caveat: the {headline} "
                f"headline is MIXED-DEPTH — {CROSS_DEPTH_CAVEAT}; the clean "
                f"same-depth cross-backend pairing is depth 4 — vulkan mtp4 "
                f"{fmt(vk_mtp41['per_stream_tok_s_median'])} vs hip mtp4 "
                f"{fmt(hip_mtp41['per_stream_tok_s_median'])} tok/s "
                f"({same_depth}, both explicit depth 4, same day). "
                f"Anchor-clean trigger met ({n_ok}-of-{n_vk} vulkan anchors "
                f"byte-identical — the hip greedy pit does not reproduce on "
                f"this backend). mtp (depth 1) stays the recommended "
                f"variant: depth 4 never beats it on either backend.")
    if cid == "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072":
        return (f"Controller review 2026-08-18: mechanical verdict confirmed, "
                f"no override. Backend alone is a small c1 delta — "
                f"{fmt(vk_base1['per_stream_tok_s_median'])} vs hip "
                f"{fmt(hip_base1['per_stream_tok_s_median'])} tok/s "
                f"({_pct(vk_base1['per_stream_tok_s_median'], hip_base1['per_stream_tok_s_median'])}) "
                f"— the AMD 24.5 tok/s Day-0 anchor gap is not a pure "
                f"backend effect; the biggest single-stream lever measured on "
                f"this host is Vulkan+MTP "
                f"({fmt(vk_mtp1['per_stream_tok_s_median'])} tok/s, the "
                f"recommended opt-in). {n_ok}-of-{n_vk} vulkan anchors clean "
                f"— the hip greedy pit does not reproduce on this backend.")
    if cid == "gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072":
        return (f"Controller review 2026-08-18: depth 4 does NOT beat depth 1 "
                f"on Vulkan ({fmt(vk_mtp41['per_stream_tok_s_median'])} vs "
                f"{fmt(vk_mtp1['per_stream_tok_s_median'])} tok/s) — mtp "
                f"(depth 1) stays the recommended variant on both backends; "
                f"no mtp4 recommendation. Clean same-depth cross-backend "
                f"pairing vs hip mtp4 "
                f"({fmt(hip_mtp41['per_stream_tok_s_median'])} tok/s): "
                f"{same_depth} (both cells explicit --spec-draft-n-max 4, "
                f"measured the same day).")
    if cid == "gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072":
        return (f"Controller review 2026-08-18: depth 4 does NOT beat depth 1 "
                f"on hip either ({fmt(hip_mtp41['per_stream_tok_s_median'])} "
                f"vs {fmt(hip_mtp1['per_stream_tok_s_median'])} tok/s) — mtp "
                f"(depth 1) stays the recommended variant on both backends; "
                f"no mtp4 recommendation anywhere. Cross-depth caveat: "
                f"{CROSS_DEPTH_CAVEAT}, so the "
                f"{fmt(hip_mtp41['per_stream_tok_s_median'])}-vs-"
                f"{fmt(hip_mtp1['per_stream_tok_s_median'])} pairing is "
                f"depth-4-explicit vs implicit-depth-3; the fixed-depth "
                f"cross-backend comparison lives on the vulkan side "
                f"(depth 1: {fmt(vk_mtp1['per_stream_tok_s_median'])} vs "
                f"depth 4: {fmt(vk_mtp41['per_stream_tok_s_median'])} tok/s). "
                f"Anchor clean, measured the same day as the vulkan cells.")
    if cid == "gguf-vulkan-udq4kxl-auto-base-c4-ctx131072":
        return (f"Controller review 2026-08-18: caution confirmed. Vulkan c4 "
                f"aggregates well above hip split-mode "
                f"({fmt(vk['gguf-vulkan-udq4kxl-auto-base-c4-ctx131072']['aggregate_tok_s'])} "
                f"vs {fmt(all_metrics[SPLIT_C4_131072_ID]['aggregate_tok_s'])} "
                f"tok/s) but per-stream stays below the floor — interactive "
                f"guidance is unchanged cross-backend (the c1 cells). Anchor "
                f"clean; the hip-family greedy pit does not reproduce on "
                f"Vulkan ({n_ok}-of-{n_vk} v0.1.2 anchors clean).")
    if cid == "gguf-vulkan-udq4kxl-auto-mtp-c4-ctx131072":
        g = vk[cid]
        b = vk["gguf-vulkan-udq4kxl-auto-base-c4-ctx131072"]
        return (f"Controller review 2026-08-18: caution confirmed, with the "
                f"basis corrected this release (the c4-caution template "
                f"previously asserted 'Better than base c4' regardless of "
                f"direction and mislabeled a c4-basis number as 'c1:'): MTP "
                f"vs the base counterpart at c4 on Vulkan is a REGRESSION — "
                f"aggregate {fmt(g['aggregate_tok_s'])} vs "
                f"{fmt(b['aggregate_tok_s'])} tok/s "
                f"({_pct(g['aggregate_tok_s'], b['aggregate_tok_s'])}), "
                f"per-stream {fmt(g['per_stream_tok_s_median'])} vs "
                f"{fmt(b['per_stream_tok_s_median'])} tok/s "
                f"({_pct(g['per_stream_tok_s_median'], b['per_stream_tok_s_median'])}) "
                f"— the c1 MTP payoff inverts under concurrency on this "
                f"backend too.")
    if cid == "gguf-vulkan-udq4kxl-auto-mtp4-c4-ctx131072":
        g = vk[cid]
        b = vk["gguf-vulkan-udq4kxl-auto-base-c4-ctx131072"]
        return (f"Controller review 2026-08-18: caution confirmed (corrected "
                f"basis, same template fix): depth-4 MTP vs the base "
                f"counterpart at c4 on Vulkan regresses — aggregate "
                f"{fmt(g['aggregate_tok_s'])} vs {fmt(b['aggregate_tok_s'])} "
                f"tok/s ({_pct(g['aggregate_tok_s'], b['aggregate_tok_s'])}), "
                f"per-stream {fmt(g['per_stream_tok_s_median'])} vs "
                f"{fmt(b['per_stream_tok_s_median'])} tok/s "
                f"({_pct(g['per_stream_tok_s_median'], b['per_stream_tok_s_median'])}); "
                f"depth 1 beats depth 4 at c1 as well — no mtp4 "
                f"recommendation.")
    if cid == UNIFIED_RIDER_ID:
        u = all_metrics[UNIFIED_RIDER_ID]
        s = all_metrics[SPLIT_C4_131072_ID]
        early = (early_eos_streams(unified_cell) if unified_cell
                 else u["streams"] - u["healthy_streams"])
        return (f"Controller ruling 2026-08-18 (measured-with-caveat rider): "
                f"the stock quickstart's 4-slot unified default boot under 4 "
                f"concurrent users DEGRADES interactivity vs split-mode c4 at "
                f"ctx 131072 — healthy-stream median "
                f"{fmt(u['per_stream_tok_s_median'])} vs "
                f"{fmt(s['per_stream_tok_s_median'])} tok/s, aggregate "
                f"{fmt(u['aggregate_tok_s'])} vs "
                f"{fmt(s['aggregate_tok_s'])} tok/s "
                f"({early}-of-{u['streams']} streams stopped within "
                f"{EARLY_EOS_MAX_TOKENS} tokens — early EOS: the unified "
                f"aggregate is not comparable; UX claims use the "
                f"healthy-stream median). No config change: single-stream "
                f"quickstart use is unaffected and light multi-user already "
                f"steers to vLLM. This closes the v0.1.0/v0.1.1 "
                f"'unified-default-boot c4@131072 not measured' bracketing "
                f"gap.")
    return None


def _pit_correlation(m: dict) -> str:
    n, capped = m["streams"], m["capped_streams"]
    if capped == n:
        return (f"every stream hit the 256-token length cap in this bench "
                f"({capped}-of-{n})")
    return (f"{capped}-of-{n} streams hit the 256-token cap; the remaining "
            f"stream(s) stopped early (content degraded anyway)")


def compose_verdict(cid: str, cell: dict, m: dict, base_m: dict | None,
                    family_best_lower: float | None,
                    all_metrics: dict | None = None,
                    unified_cell: dict | None = None) -> dict:
    parts = parse_cell_id(cid)
    m = dict(m)
    m["c"] = parts["c"]
    m["lower_aggregate_best"] = family_best_lower
    m["base_aggregate"] = base_m["aggregate_tok_s"] if base_m else None
    ladder = auto_ladder(m)
    override = CONTROLLER_OVERRIDES.get(cid)
    verdict = override["verdict"] if override else ladder["verdict"]

    med = m["per_stream_tok_s_median"]
    mn = m["per_stream_tok_s_min"]
    agg = m["aggregate_tok_s"]
    ttft_s = m["ttft_ms_median"] / 1000.0 if m["ttft_ms_median"] else None
    gtt_gib = mib_to_gib(m["gtt_mib"]) if m["gtt_mib"] else None
    slot = cell.get("slot_info") or {}
    boot_s = (cell.get("boot") or {}).get("health_wall_s")

    # MTP gain vs the base counterpart (both bases labeled, §2-style honesty).
    # mtp4 (depth-4 variant, v0.1.2) gains against the same base cell.
    gains = None
    if parts["mtp"] in ("mtp", "mtp4") and base_m:
        gains = {
            "per_stream_pct": round((med / base_m["per_stream_tok_s_median"] - 1) * 100, 1),
            "aggregate_pct": round((agg / base_m["aggregate_tok_s"] - 1) * 100, 1),
            "base_per_stream_tok_s_median": base_m["per_stream_tok_s_median"],
            "base_aggregate_tok_s": base_m["aggregate_tok_s"],
        }

    reason, conditions, workaround, upstream = ladder["reason"], None, None, None

    if verdict == "avoid" and not m["anchor_ok"] and m["boot_ok"] and not m["failed_streams"]:
        # The §6 greedy-degradation pit cells.
        unified = slot.get("kv_unified")
        boot_desc = (f"unified default boot, n_ctx_slot {slot.get('n_ctx_slot')}"
                     if unified == "true" else
                     f"split boot (-np {parts['c']}, n_ctx_slot {slot.get('n_ctx_slot')})")
        reason = (f"Greedy byte-identity anchor FAILED after the "
                  f"{parts['c']}-stream bench ({boot_desc}): greedy decoding "
                  f"on the same server instance degenerates into a '////…' "
                  f"repetition loop (METHODOLOGY §6 pit). Recorded throughput "
                  f"(per-stream median {fmt(med)} tok/s, aggregate {fmt(agg)} tok/s) "
                  f"is secondary — the cell is measured(degraded) and its "
                  f"anchor drift invalidates cross-path comparison.")
        conditions = (f"Pit correlation, stated honestly per the corrected "
                      f"§6 erratum: {_pit_correlation(m)}, while all clean "
                      f"cells had early-stopping streams; the exact trigger "
                      f"is unresolved (not split-KV-specific: this reproduces "
                      f"on the unified default boot too).")
        workaround = GGUF_PIT_WORKAROUND
        upstream = GGUF_PIT_UPSTREAM

    elif cid == "vllm-bf16-auto-mtp-c16-ctx262144":
        reason = (f"MTP regresses vs baseline at c16: aggregate {fmt(agg)} vs "
                  f"base {fmt(m['base_aggregate'])} tok/s "
                  f"({ladder_rung3_pct(agg, m['base_aggregate'])}), with "
                  f"per-stream min {fmt(m['per_stream_tok_s_min'], 2)} tok/s — "
                  f"the speculative win inverts at high concurrency (rung-3 "
                  f"avoid-candidate confirmed by controller review; the "
                  f"muse-rocm DFlash lesson mirrored). Anchor clean, boot "
                  f"healthy.")
        conditions = (f"Use the base config at c16 for batch work "
                      f"({fmt(m['base_aggregate'])} tok/s aggregate, the best cell "
                      f"measured); MTP pays off only through c8 on this path "
                      f"(see the mtp-c4/mtp-c8 caution cells).")
        workaround = ("Serve without --mtp (configs/serve-args.conf) when "
                      "batching at 16 streams.")

    elif parts["path"] == "vllm":
        gain_txt = ""
        if gains:
            gain_txt = (f" MTP lifts per-stream +{gains['per_stream_pct']:.1f}% "
                        f"({fmt(med)} vs {fmt(gains['base_per_stream_tok_s_median'])} tok/s; "
                        f"aggregate basis +{gains['aggregate_pct']:.1f}% "
                        f"{fmt(agg)} vs {fmt(gains['base_aggregate_tok_s'])} tok/s) — but not to the floor.")
        # The full ruling sentence goes in the reason only when the bracketed
        # override note (added below) does not already state it.
        ruling = ("" if override else
                  " Controller ruling 2026-08-17: all 8 measured vLLM cells "
                  "are below the 10 tok/s interactive floor.")
        reason = (f"Per-stream median {fmt(med)} tok/s (TPOT "
                  f"{fmt(m['tpot_ms_median'])} ms/token) is below the 10 tok/s "
                  f"interactive floor on this host — vLLM BF16 is not "
                  f"interactive-grade on this host.{gain_txt} Anchor clean, "
                  f"boot healthy ({boot_s} s, GTT {gtt_gib} GiB).{ruling}")
        conditions = ("Per-stream < 10 tok/s on this host: use for "
                      "262144-context, vision, and aggregate batch throughput "
                      "(to 38.6 tok/s), and as the greedy-degradation-free "
                      "path; interactive chat → GGUF path (mtp-c1 13.0 tok/s).")
        if gains:
            conditions += (" Percentages are per-stream basis unless labeled "
                           "aggregate.")
        workaround = ("Interactive workloads: serve the GGUF path "
                      "(scripts/gguf-quickstart.sh, WITH_MTP=1).")

    elif parts["path"] == "gguf" and verdict == "caution":
        healthy_note = ""
        if m["healthy_streams"] < m["streams"]:
            unhealthy = m["streams"] - m["healthy_streams"]
            healthy_note = (f" UX claims exclude non-healthy streams: "
                            f"{unhealthy}-of-{m['streams']} stream(s) emitted "
                            f"<2 content tokens (no defined TPOT) and must not "
                            f"count toward latency claims.")
        mtp_txt = ""
        if gains:
            # 2026-08-18 defect fix (Task 4): direction and basis now follow
            # the actual numbers — both comparisons are THIS cell vs the BASE
            # counterpart at the same c (never a "c1:" basis), and a lowering
            # aggregate/per-stream is stated as a regression, never "Better".
            agg_pct = gains["aggregate_pct"]
            if agg_pct > 0:
                lead = (f"Above the base c{parts['c']} aggregate "
                        f"({fmt(agg)} vs {fmt(gains['base_aggregate_tok_s'])} "
                        f"tok/s, +{agg_pct:.1f}%)")
            else:
                lead = (f"Aggregate {fmt(agg)} vs base c{parts['c']} "
                        f"{fmt(gains['base_aggregate_tok_s'])} tok/s "
                        f"({agg_pct:+.1f}%)")
            mtp_txt = (f" {lead}, but MTP's payoff shrinks with concurrency "
                       f"(per-stream at c{parts['c']}: {fmt(med)} vs "
                       f"{fmt(gains['base_per_stream_tok_s_median'])} tok/s, "
                       f"{gains['per_stream_pct']:+.1f}%).")
        gttn = f"; GTT {gtt_gib} GiB at load" if gtt_gib else ""
        reason = (f"Per-stream median {fmt(med)} tok/s (TPOT "
                  f"{fmt(m['tpot_ms_median'])} ms/token) is below the 10 tok/s "
                  f"interactive floor at the c{parts['c']} "
                  f"{'light-multi-user' if parts['c'] == 4 else 'multi-user'} "
                  f"tier; aggregate {fmt(agg)} tok/s.{mtp_txt} Anchor clean{gttn}.")
        conditions = (f"Batch/light-multi-user use only — aggregate {fmt(agg)} "
                      f"tok/s; interactive chat → the c1 cells "
                      f"(mtp-c1 13.0 tok/s).{healthy_note}")
        if parts["ctx"] == 262144:
            conditions += (" Full-context tier: GTT +8.0 GiB over the 131072 "
                           "boot and the deep-context retrieval caveat apply "
                           "(see the context-capacity table).")

    elif parts["path"] == "gguf" and verdict == "recommended":
        mtp_txt = ""
        if gains:
            mtp_txt = (f" MTP speculative decoding lifts per-stream throughput "
                       f"+{gains['per_stream_pct']}% ({fmt(med)} vs "
                       f"{fmt(gains['base_per_stream_tok_s_median'])} tok/s "
                       f"median; aggregate basis "
                       f"+{gains['aggregate_pct']}%) — the quickstart's "
                       f"WITH_MTP=1 opt-in is safe for interactive chat.")
        slot_txt = (f"unified default boot, full {slot.get('n_ctx_slot')} window"
                    if slot.get("kv_unified") == "true" else "validated boot")
        reason = (f"Interactive single-stream at the validated defaults "
                  f"({slot_txt}): per-stream {fmt(med)} tok/s median (TPOT "
                  f"{fmt(m['tpot_ms_median'])} ms/token) at/above the 10 tok/s "
                  f"interactive floor; greedy anchor byte-identical; GTT "
                  f"{gtt_gib} GiB at load.{mtp_txt}")
        conditions = (f"Single-user interactive chat at the validated defaults "
                      f"(UD-Q4_K_XL, ctx {parts['ctx']}). TTFT "
                      f"{fmt(ttft_s)} s on ~1.4K-token prompts; concurrency "
                      f"demotes per-stream below the floor (see the c4 cells).")
        if parts["mtp"] in ("mtp", "mtp4"):
            # Same-variant c4 cell first (mtp4 cells cite mtp4-c4 when
            # measured), falling back to the depth-1 mtp-c4 of the same
            # backend (the pre-2026-08-18 behavior).
            c4 = ((all_metrics or {}).get(
                    f"gguf-{parts['backend']}-{parts['weight']}-{parts['kv']}-"
                    f"{parts['mtp']}-c4-ctx{parts['ctx']}")
                or (all_metrics or {}).get(
                    f"gguf-{parts['backend']}-udq4kxl-auto-mtp-c4-ctx{parts['ctx']}"))
            c4_txt = (f"c4 median {fmt(c4['per_stream_tok_s_median'])} tok/s "
                      f"(below floor)" if c4 else "c4 below floor")
            # 2026-08-18 defect fix (Task 4): the "c8/c16 hit the pit" clause
            # is hip-family history measured at this ctx — it must not leak
            # into backends/families with no pit cells (vulkan). The tiers
            # enumerate from the backend's own measured pit cells at this
            # ctx, so hip output is unchanged.
            pit_tiers = sorted({parse_cell_id(k)["c"] for k, mm
                                in (all_metrics or {}).items()
                                if parse_cell_id(k)["backend"] == parts["backend"]
                                and parse_cell_id(k)["ctx"] == parts["ctx"]
                                and not mm["anchor_ok"] and mm["boot_ok"]
                                and not mm["failed_streams"]})
            if pit_tiers:
                pit_txt = (f", and {'/'.join(f'c{t}' for t in pit_tiers)} "
                           f"hit the anchor-degradation pit (avoid cells)")
            else:
                n_b = len([k for k in all_metrics
                           if parse_cell_id(k)["backend"] == parts["backend"]])
                n_ok = len([k for k, mm in all_metrics.items()
                            if parse_cell_id(k)["backend"] == parts["backend"]
                            and mm["anchor_ok"]])
                pit_txt = (f"; c8/c16 are unmeasured on this backend, and "
                           f"the hip-family greedy pit does not reproduce "
                           f"here ({n_ok}-of-{n_b} anchors clean in the "
                           f"v0.1.2 cells)")
            conditions = (f"+{gains['per_stream_pct']}% is the PER-STREAM basis "
                          f"({fmt(med)} vs "
                          f"{fmt(gains['base_per_stream_tok_s_median'])} tok/s "
                          f"median, c1 ctx {parts['ctx']}); aggregate basis "
                          f"+{gains['aggregate_pct']}% ({fmt(agg)} vs "
                          f"{fmt(gains['base_aggregate_tok_s'])} tok/s). Payoff "
                          f"shrinks under concurrency: {c4_txt}{pit_txt}.")
        if parts["ctx"] == 262144:
            conditions += (" GTT grows +8.0 GiB over the 131072 boot (34,742 "
                           "vs 26,548 MiB = 64 KiB/token bf16 KV, the closed "
                           "form); deep-context retrieval is not depth-reliable "
                           "on this path (120K tier confident miss — see the "
                           "context-capacity table).")
        if parts["ctx"] == 32768:
            conditions += (" Long-context retrieval smoke PASSED at this tier "
                           "(needle recalled at ~30K-token depth).")
        if cid in QUICKSTART_C4_CAVEAT_CELLS:
            conditions = (f"{conditions} "
                          f"{quickstart_c4_caveat(all_metrics, unified_cell)}")

    if cid == UNIFIED_RIDER_ID and conditions:
        conditions = (f"{conditions} Prefer the split boot "
                      f"(`EXTRA_ARGS='-np 4'`) for light multi-user — the "
                      f"unified default boot degrades interactivity (see the "
                      f"ruling in the reason).")

    if override:
        reason += f" [{override['note']}]"

    ruling = v012_ruling_note(cid, all_metrics, unified_cell)
    if ruling:
        reason = f"{reason} {ruling}"

    out = {
        "id": cid,
        "verdict": verdict,
        "reason": reason,
        "metrics": {
            **{k: v for k, v in m.items()
               if k not in ("c", "lower_aggregate_best", "base_aggregate")},
            "c": parts["c"],
            "ctx": parts["ctx"],
            "gtt_gib": gtt_gib,
            "auto_verdict": ladder["verdict"],
            "auto_rung": ladder["rung"],
            "avoid_candidate": ladder["avoid_candidate"],
            "controller_override": (None if not override else
                                    {"verdict": override["verdict"],
                                     "note": override["note"]}),
        },
    }
    if cid in V012_CELLS:
        # v0.1.2 review trail: per-cell reviewer of record for the 8 new
        # cells (the 20 migrated cells stay governed by the frozen
        # controller-2026-08-17 review and carry no per-cell field — their
        # content is byte-stable modulo the id migration).
        out["metrics"]["reviewed_by"] = V012_REVIEWED_BY
    if gains:
        out["metrics"]["mtp_gain_vs_base"] = gains
    if conditions:
        out["conditions"] = conditions
    if workaround:
        out["workaround"] = workaround
    if upstream:
        out["upstream"] = upstream
    return out


def ladder_rung3_pct(this: float, other: float) -> str:
    return f"{(this / other - 1) * 100:.1f}%"


# ------------------------------------------------------------------- assembly

def build_verdicts(root: Path = ROOT) -> dict:
    matrix = json.loads((root / "docs/results/matrix-714/matrix.json").read_text())
    measured = [c["id"] for c in matrix["cells"] if c["status"] == "measured"]
    cells_dir = root / "docs/results/matrix-714/cells"
    cells = {cid: json.loads((cells_dir / f"{cid}.json").read_text())
             for cid in measured}
    metrics = {cid: compute_metrics(cell) for cid, cell in cells.items()}

    out_cells = []
    for cid in sorted(measured):
        parts = parse_cell_id(cid)
        # Base counterpart: same path/backend/ctx/c, base MTP.
        if parts["path"] == "gguf":
            base_id = (f"gguf-{parts['backend']}-{parts['weight']}-{parts['kv']}-"
                       f"base-c{parts['c']}-ctx{parts['ctx']}")
        else:
            base_id = (f"{parts['path']}-{parts['weight']}-{parts['kv']}-"
                       f"base-c{parts['c']}-ctx{parts['ctx']}")
        base_m = metrics.get(base_id) if parts["mtp"] in ("mtp", "mtp4") else None
        # Best lower-concurrency aggregate in the same family (a family is
        # path x backend x mtp-variant x ctx — hip and vulkan never mix).
        lowers = [metrics[o]["aggregate_tok_s"] for o in measured
                  if (p := parse_cell_id(o))["path"] == parts["path"]
                  and p["backend"] == parts["backend"]
                  and p["mtp"] == parts["mtp"]
                  and p["ctx"] == parts["ctx"] and p["c"] < parts["c"]]
        family_best = max(lowers) if lowers else None
        out_cells.append(compose_verdict(cid, cells[cid], metrics[cid],
                                         base_m, family_best, metrics,
                                         cells.get(UNIFIED_RIDER_ID)))

    # Top-level shape is locked by schemas/benchmark-verdicts.schema.json
    # (additionalProperties: false) — provenance stays in this generator's
    # docstring and in the rendered docs, not in the JSON.
    return {
        "checked_at": CONTROLLER_REVIEW_DATE,
        "reviewed_by": REVIEWED_BY,
        "cells": out_cells,
    }


def render_json(verdicts: dict) -> str:
    return json.dumps(verdicts, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    check = "--check" in args
    verdicts = build_verdicts()
    text = render_json(verdicts)
    if check:
        committed = OUT.read_text() if OUT.exists() else ""
        if committed != text:
            print("STALE: configs/benchmark-verdicts.json differs from a "
                  "fresh regeneration over docs/results/matrix-714/cells/.",
                  file=sys.stderr)
            print("Rerun: python3 scripts/gen-verdicts.py", file=sys.stderr)
            return 1
        n = len(verdicts["cells"])
        dist = {}
        for c in verdicts["cells"]:
            dist[c["verdict"]] = dist.get(c["verdict"], 0) + 1
        print(f"fresh: {n} cells " +
              "/".join(f"{v} {k}" for k, v in sorted(dist.items())))
        return 0
    OUT.write_text(text)
    n = len(verdicts["cells"])
    dist = {}
    for c in verdicts["cells"]:
        dist[c["verdict"]] = dist.get(c["verdict"], 0) + 1
    print(f"wrote {OUT} ({n} cells: " +
          "/".join(f"{v} {k}" for k, v in sorted(dist.items())) + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
