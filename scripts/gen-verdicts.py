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

2026-08-19 evidence integration S5 (v0.1.4): the session-3 receipts
(clean depth-1/depth-1 backend pairing + cross-day re-runs, same loader
convention) SUPERSEDE the 2026-08-18 promotion basis — the hip side of the
promoted pairing was depth-confounded. Dated supersession, not a silent
rewrite: the vulkan mtp-c1 ruling note records ruling 2026-08-18
(promotion, mixed-depth basis) SUPERSEDED BY ruling 2026-08-19 (clean d1
pairing +4.81% single-stream, aggregate −13.31%, cross-day variance), both
dates visible. The quickstart recommendation MAPPING is downgraded
(vulkan: available experimental opt-in, not recommended; hip WITH_MTP=1 is
both the default and the recommended path). Cell VERDICTS, metrics, and
the 8/14/6 distribution are UNCHANGED — the mechanical verdicts from their
own receipts stand; only the mapping-layer prose changed. The pit finding
(vulkan anchor-clean) is unaffected and stays stated. The host-level cause
of the vulkan cross-day drop is NOT recorded — receipts carry VRAM/GTT
only, no clock/thermal telemetry (stated honestly; known harness debt).

2026-08-19 variance root-cause R2 (v0.1.6): session 4 (the R1 telemetry
harness + controlled runs: two warm vulkan boots, two hip controls, one
cache-aside arm; receipts session4-2026-08-19/ per-run subdirs) EXPLAINS
the v0.1.4 cross-day variance as Mesa shader-cache state dependence —
cold→warm swing +38% on identical config/flags/pin, s3's 14.53 sitting
between cold (12.38) and warm (17.03 mean) → partial-cold state
consistent, TRIGGER of the partial-cold state unidentified (no Mesa
upgrade, no reboot — host up since 2026-08-12, no cache-clear found). The
v0.1.6 ruling note is a DATED SUPERSESSION of the v0.1.4 "cause not
recorded" sentence (which stays visible in the note for history) plus the
floor/ceiling RELABELS of the pairings: the +4.81% clean pairing =
conservative floor case (vk measured partial-cold; arithmetic and the
no-flip conclusion unchanged); the warm same-day boot-paired pairings
(+15.9%/+20.6%) = warm-cache ceiling context. Recommendation layer
UNCHANGED (controller ruling 2026-08-19: vulkan stays
available-experimental-not-recommended; hip WITH_MTP=1 SPEC_DEPTH=1 stays
default AND recommended); a one-line warmup guidance lands in the
quickstart echo + adaptation, and the "re-recommend vulkan?" question is
recorded as OPEN for the human owner in the README roadmap. Zero
metric/verdict changes: the 8/14/6 distribution is untouched; the only
verdicts-JSON delta is the vulkan mtp-c1 ruling note.

2026-08-20 evidence integration H2 (v0.1.7): the trigger-hunt forensics
(read-only host-log hunt in the s2->s3 causal window, evidence note
docs/results/matrix-714/stability/trigger-hunt-2026-08-19.md,
independently reproduced) REFUTE the v0.1.6 "s3 partial-cold" reading —
the mesa cache was INTACT at s3 (866 files pre-window / 0 written inside
the causal window / 1 post — the session-4 marker): s3 ran slow (14.53)
with a warm untouched cache, so its vk-specific trigger is UNIDENTIFIED
(cache ruled out; no suspend/resume, no amdgpu reset/errors, no
power-profile switch in the window; the clock-stepping condition was
ABSENT during s3's run; the only discrete in-window state change is an
unattended-upgrade of linux-libc-dev/linux-tools-common 6.8.0-137->138 —
recorded as fact, NO mechanism claimed). The cold-cache arm stays the
swing BOUND proof (cold 12.38 vs warm 17.03 mean, +38% class), NOT s3's
explanation — dated supersession #3, history visible. New recorded
findings: (a) chronic common-mode clock-stepping (883+ "Clock change
detected" since the 08-12 boot, still accruing — NOT s3-specific);
(b) common-mode session drift (s5 vs s4: vk -4.6% / hip -6.0%); (c) the
warm pairing band across 4 sessions (+15.88/+20.61/+19.90/+15.93);
(d) overnight warm persistence CONFIRMED (session 6, 7 h 50 m after s5,
receipts-derived — cache byte-identical, pairing in band); (e)
aggregate/TTFT consistently hip-favored — vk's edge is the single-stream
median only. The recommendation layer is UNCHANGED (controller ruling
2026-08-20, recorded, not re-deliberated); warmup guidance stands; the
README roadmap OPEN question is restated both ways honestly. Zero
metric/verdict changes: the 8/14/6 distribution is untouched; the
verdicts-JSON delta is the vulkan mtp-c1 ruling note plus the top-level
ruling-of-record attribution date (controller-2026-08-20 — the H2
refinement is the latest ruling of record; the mapping layer it leaves
unchanged remains the 2026-08-19 ruling, quoted as such in the prose).

2026-08-20 decision closeout (v0.1.8): the repository owner DECIDED the
OPEN re-recommendation question — NO (owner ruling 2026-08-20, recorded
verbatim in substance, never re-deliberated here): NOT re-recommending
BACKEND=vulkan; it stays an available experimental opt-in, NOT
recommended; hip WITH_MTP=1 SPEC_DEPTH=1 stays default AND recommended
(the mapping of record is CONFIRMED, not changed). The vulkan mtp-c1
ruling note gains the dated OWNER DECISION addendum — resolution #4,
with the two earlier "OPEN for the owner" phrasings (v0.1.6/v0.1.7
layers) kept visible and marked resolved, consistent with the three
supersession layers. Every rationale number interpolates from the same
loaders (s4/s5/s6 TTFTs, the warm band, the cold-arm figures, the
session-4 power envelopes); the crossover prints as "≈230–310 tokens"
explicitly labeled DERIVED (arithmetic over three sessions' receipts,
never a measurement). The addendum also records the SELECTION GUIDANCE
(self-selection criteria, never promotion) and the four PRE-REGISTERED
promotion criteria (all four must hold before any future upgrade to
conditional-recommended). Zero metric/verdict changes: the 8/14/6
distribution and every cell verdict stand; the verdicts-JSON delta is
the one ruling note.
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CELLS_DIR = ROOT / "docs/results/matrix-714/cells"
MATRIX = ROOT / "docs/results/matrix-714/matrix.json"
OUT = ROOT / "configs/benchmark-verdicts.json"

# v0.1.14 (2026-08-21): the DFlash2 corpus cells' same-session pairing
# partners live in the stability session tree, NOT the corpus (the corpus
# base/mtp cells are the 262144 story; the pairing ran at 131072 — the
# dflash KV-feasible tier). Same loader convention as the stability
# sessions: receipts-only, read by explicit path.
DFLASH_SESSION_DIR = (ROOT / "docs/results/matrix-714/stability" /
                      "dflash-pairing-2026-08-21")

# METHODOLOGY §3 rung 2: per-stream TPOT < 10 tok/s at an interactive tier is
# not recommendable; severity band 8–10 tok/s -> caution, < 8 -> avoid.
INTERACTIVE_FLOOR_TOK_S = 10.0
FLOOR_CAUTION_BAND_TOK_S = 8.0
# §3 rung 3 tolerance: aggregate must regress by more than this fraction to
# be an avoid-candidate (guards against noise-level "regressions").
REGRESSION_TOLERANCE = 0.05

LEGACY_REVIEW_DATE = "2026-08-17"  # the frozen review of the 20 migrated cells
CONTROLLER_REVIEW_DATE = "2026-08-18"  # v0.1.2 mechanical review of the 8 new cells
# v0.1.4 (S5, 2026-08-19): the clean-pairing supersession ruling re-based the
# quickstart MAPPING (vulkan downgraded) — the mapping layer it produced is
# still the mapping of record (unchanged by every later ruling, quoted as
# "controller ruling 2026-08-19" in the prose below).
MAPPING_RULING_DATE = "2026-08-19"
# v0.1.7 (H2, 2026-08-20): the trigger-hunt + overnight-series refinement is
# the LATEST ruling of record and produced THIS file state — the top-level
# attribution follows it (the 8 v0.1.2 cells keep their own per-cell
# controller-2026-08-18 mechanical-review record, unchanged; the 20 migrated
# cells stay governed by the frozen controller-2026-08-17 review).
EVIDENCE_RULING_DATE = "2026-08-20"
REVIEWED_BY = f"controller-{EVIDENCE_RULING_DATE}"


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
#
# v0.1.4 SUPERSESSION (2026-08-19, S5 — DECIDED, recorded, not
# re-deliberated): session 3 measured the CLEAN depth-1 pairing both sides
# explicit (hip mtp-c1 --spec-draft-n-max 1 + the 3 vulkan c1 re-runs,
# next UTC day). Result: vulkan 14.53 vs hip 13.86 tok/s = +4.81%
# single-stream (exact basis; the 2026-08-18 promotion basis was the
# MIXED-DEPTH +23.1% headline — vulkan d1 vs hip IMPLICIT d3, a
# depth-confounded hip side), aggregate basis hip 10.74 vs vulkan 9.31 =
# -13.31% (TTFT-driven), and the vulkan cells show cross-day variance up
# to a 30.70% spread while hip is same-session stable. Ruling:
# quickstart guidance downgrades BACKEND=vulkan from "RECOMMENDED OPT-IN"
# to an AVAILABLE experimental opt-in (mechanism + experimental framing
# kept, recommendation language dropped); hip WITH_MTP=1 is BOTH the
# default AND the recommended path. No-flip closed on the clean basis:
# +4.81% << the >25% threshold. Corpus cell verdicts and the 8/14/6
# distribution UNCHANGED (mechanical verdicts from their own receipts
# stand); the pit finding (vulkan anchor-clean) is unaffected and stays
# stated. Cause of the vulkan cross-day drop NOT recorded (VRAM/GTT only
# in the receipts — no clock/thermal telemetry; known harness debt).
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
# number is quoted. The parenthetical states the date convention once
# (2026-08-18, v0.1.3 debt fix): receipt timestamps are UTC, while caveat
# dates before v0.1.2 were written in the operator's local UTC+8 — the
# same day either way, never a different one.
CROSS_DEPTH_CAVEAT = ("the hip mtp-c1 receipt (2026-08-17; receipt "
                      "timestamps are UTC, caveat dates before v0.1.2 use "
                      "local UTC+8) ran the implicit "
                      "--spec-draft-n-max default 3 while every v0.1.2 cell "
                      "passes its depth explicitly "
                      "(configs/validated-stack.json llama_cpp_vulkan."
                      "mtp_depth.note)")


def _pct2(this: float, other: float) -> str:
    """2dp exact-basis pct — the convention the committed stability README
    uses for the cross-day deltas (−3.35% must not 1dp-round to −3.3%)."""
    return f"{(this / other - 1) * 100:+.2f}%"


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
#
# S5 (v0.1.4, 2026-08-19): the loader extends to the session-3 receipts
# (session3-2026-08-19/ — the 4th receipt there is hip mtp-c1 with EXPLICIT
# depth 1, the depth-matched pairing side) and computes the clean d1/d1
# pairing, the cross-day deltas/spreads, the aggregate flip, the TTFT
# observation, and the cross-session anchor tally the v0.1.4 supersession
# note quotes. Same fail-loud convention: a moved/edited session-3 receipt
# breaks the regen, never the prose.
STABILITY_DIR = ROOT / "docs" / "results" / "matrix-714" / "stability"
SESSION2_DIR = STABILITY_DIR / "session2-2026-08-18"
SESSION3_DIR = STABILITY_DIR / "session3-2026-08-19"
SESSION4_DIR = STABILITY_DIR / "session4-2026-08-19"
STABILITY_POINTER = "docs/results/matrix-714/stability/"
STABILITY_CELLS = (
    "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072",
    "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072",
)
VULKAN_MTP1_ID = "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"
HIP_MTP1_ID = "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072"
HIP_MTP1_S3 = HIP_MTP1_ID  # session-3 receipt name == the corpus cell id

# Session 4 (R1, 2026-08-19): the same cell id is measured more than once,
# so each run writes into its OWN subdirectory — the loader reads exact
# paths (fail-loud, no globs), same convention as session2/3. Fixed run
# order by design: vk boot1 → hip ctrl1 → vk boot2 → hip ctrl2 → the
# cache-aside arm (orchestrated outside the runner — see the stability
# README's orchestration note; the receipt is runner-shaped regardless).
SESSION4_RUNS = (
    ("run1-vk-boot1", "vulkan"),
    ("run2-hip-ctrl1", "hip"),
    ("run3-vk-boot2", "vulkan"),
    ("run4-hip-ctrl2", "hip"),
    ("run5-vk-cacheaside", "vulkan"),
)
SESSION4_DATE = "2026-08-19"

# Sessions 5 and 6 (2026-08-19 evening / 2026-08-20 local morning — the
# H1/H2 daily warm-pair series): per-run subdirectories, exact paths,
# fail-loud, no globs (same convention as session 4). The v0.1.7 ruling
# note quotes these receipts AND references the committed trigger-hunt
# evidence note by path — a moved/edited artifact breaks the regen, never
# the prose. (The note itself is a committed receipt-class artifact and is
# never edited here — its chronically-accruing clock-event count is cited
# as "883+ (per the note)", never frozen into a loader constant.)
SESSION5_DIR = STABILITY_DIR / "session5-2026-08-19T2321local"
SESSION6_DIR = STABILITY_DIR / "session6-2026-08-20T0712local"
SESSION56_RUNS = (
    ("run1-vk", "vulkan"),
    ("run2-hip", "hip"),
)
SESSION5_DATE = "2026-08-19"   # evening (15:20–15:22Z = 23:20–23:22 local)
SESSION6_DATE = "2026-08-20"   # local morning (23:12–23:13Z prev UTC day)
TRIGGER_HUNT_NOTE = (STABILITY_DIR / "trigger-hunt-2026-08-19.md")
TRIGGER_HUNT_POINTER = ("docs/results/matrix-714/stability/"
                        "trigger-hunt-2026-08-19.md")


def _c1_stream_tok_s(cell: dict) -> float:
    """Exact (unrounded) per-stream tok/s of a c1 cell's healthy stream.
    Session-2 deltas are computed on exact values so +1.5% prints +1.5% —
    2dp-rounded operands would print +1.6%."""
    healthy = [s for s in cell["client"]["streams"]
               if s.get("ok") and s.get("tpot_ms") and s["tpot_ms"] > 0
               and (s.get("completion_tokens") or 0) >= 2]
    return statistics.median(1000.0 / s["tpot_ms"] for s in healthy)


def _c1_ttft_s(cell: dict) -> float:
    """Exact (unrounded) TTFT seconds of a c1 cell's ok stream (the v0.1.4
    TTFT observation: session-3 vulkan TTFT vs the 2026-08-18 sessions)."""
    ttfts = [s["ttft_ms"] for s in cell["client"]["streams"]
             if s.get("ok") and s.get("ttft_ms") is not None]
    return statistics.median(ttfts) / 1000.0


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

    # ---- session 3 (2026-08-19): cross-day re-runs + the clean d1 pairing
    s3_cells = {}
    for cid in STABILITY_CELLS:
        c3 = json.loads((SESSION3_DIR / f"{cid}.json").read_text())
        s3_cells[cid] = {
            "s3": _c1_stream_tok_s(c3),
            "s3_2dp": round(_c1_stream_tok_s(c3), 2),
            "agg_2dp": round(c3["client"]["aggregate"]["tok_per_s"], 2),
            "ttft_s_2dp": round(_c1_ttft_s(c3), 2),
            "anchor_ok": bool(c3.get("anchor", {}).get("ok")),
        }
    hip3 = json.loads((SESSION3_DIR / f"{HIP_MTP1_S3}.json").read_text())
    hip3_v = _c1_stream_tok_s(hip3)
    hip1_corpus = json.loads((CELLS_DIR / f"{HIP_MTP1_ID}.json").read_text())
    hip1_corpus_v = _c1_stream_tok_s(hip1_corpus)
    ev["session3"] = {
        "hip_mtp1": {
            "s3": hip3_v, "s3_2dp": round(hip3_v, 2),
            "agg_2dp": round(hip3["client"]["aggregate"]["tok_per_s"], 2),
            "ttft_s_2dp": round(_c1_ttft_s(hip3), 2),
            "anchor_ok": bool(hip3.get("anchor", {}).get("ok")),
            # corpus 2026-08-16 receipt: implicit depth 3, TTFT historical.
            # The d1-vs-implicit-d3 delta is exact-basis, 2dp display
            # (+6.61%, matching the committed stability README) —
            # day-confounded, and always labeled as such where quoted.
            "corpus_2dp": round(hip1_corpus_v, 2),
            "corpus_ttft_s_2dp": round(_c1_ttft_s(hip1_corpus), 2),
            "corpus_delta_pct": _pct2(hip3_v, hip1_corpus_v),
        },
        "cells": s3_cells,
    }

    # Cross-day variance: s3 vs s1/s2 + the max spread over the three
    # exact session medians (both exact-basis, 2dp display — the committed
    # stability README convention).
    ev["crossday"] = {}
    for cid in STABILITY_CELLS:
        e = ev["cells"][cid]
        vals = (e["s1"], e["s2"], s3_cells[cid]["s3"])
        ev["crossday"][cid] = {
            "vs_s1_pct": _pct2(s3_cells[cid]["s3"], e["s1"]),
            "vs_s2_pct": _pct2(s3_cells[cid]["s3"], e["s2"]),
            "spread_pct": round((max(vals) / min(vals) - 1) * 100, 2),
        }

    # The clean d1/d1 pairing (both sides explicit depth 1, same session,
    # same pin/model/prompts/harness): single-stream AND aggregate basis.
    vk3 = s3_cells[VULKAN_MTP1_ID]
    hip3m = ev["session3"]["hip_mtp1"]
    ev["clean_pairing"] = {
        "date": "2026-08-19",
        "vk_2dp": vk3["s3_2dp"], "hip_2dp": hip3m["s3_2dp"],
        "gap_2dp": round(vk3["s3"] - hip3_v, 2),
        "pct_2dp": f"{(vk3['s3'] / hip3_v - 1) * 100:+.2f}%",
        "vk": vk3["s3"], "hip": hip3_v,          # exact, for assertions
        "vk_agg_2dp": vk3["agg_2dp"], "hip_agg_2dp": hip3m["agg_2dp"],
        "agg_pct_2dp": f"{(vk3['agg_2dp'] / hip3m['agg_2dp'] - 1) * 100:+.2f}%",
    }

    # ---- session 4 (2026-08-19, R1): cross-boot / cache-arm root cause (R2)
    #
    # Five controlled runs under the R1 telemetry harness (clock/power/temp
    # at load AND post-bench + mesa_shader_cache stats on the vulkan
    # receipts). Exact-path reads per run subdirectory — fail-loud, no
    # globs; the v0.1.6 ruling note quotes this evidence so a moved/edited
    # session-4 receipt breaks the regen, never the prose.
    s4 = {}
    s4_boot_times = set()
    for run, backend in SESSION4_RUNS:
        path = (SESSION4_DIR / run /
                f"gguf-{backend}-udq4kxl-auto-mtp-c1-ctx131072.json")
        c4 = json.loads(path.read_text())
        tel = (c4.get("post_bench") or {}).get("telemetry") or {}
        env = ((c4.get("load") or {}).get("telemetry") or {}).get("env") or {}
        s4_boot_times.add(env.get("boot_time"))
        mc = (((c4.get("load") or {}).get("telemetry") or {})
              .get("mesa_cache")) or {}
        s4[run] = {
            "tok_s": _c1_stream_tok_s(c4),
            "tok_s_2dp": round(_c1_stream_tok_s(c4), 2),
            "ttft_s_2dp": round(_c1_ttft_s(c4), 2),
            "anchor_ok": bool(c4.get("anchor", {}).get("ok")),
            "post_sclk_mhz": tel.get("sclk_mhz"),
            "post_power_w": tel.get("power_w"),
            "post_temp_c": tel.get("temp_edge_c"),
            "mesa_cache": mc,
        }
    vk1, vk2 = s4["run1-vk-boot1"], s4["run3-vk-boot2"]
    h1, h2 = s4["run2-hip-ctrl1"], s4["run4-hip-ctrl2"]
    aside = s4["run5-vk-cacheaside"]
    warm_mean = (vk1["tok_s"] + vk2["tok_s"]) / 2.0

    def _tel_range(runs, key):
        vals = [s4[r][key] for r in runs if s4[r][key] is not None]
        return (min(vals), max(vals)) if vals else (None, None)

    vk_runs, hip_runs = ("run1-vk-boot1", "run3-vk-boot2",
                         "run5-vk-cacheaside"), ("run2-hip-ctrl1",
                                                 "run4-hip-ctrl2")
    warm_cache = (vk2["mesa_cache"] or {}).get("before_boot") or {}
    aside_cache = (aside["mesa_cache"] or {}).get("after_teardown") or {}
    ev["session4"] = {
        "date": SESSION4_DATE,
        "runs": {r: {"tok_s_2dp": s4[r]["tok_s_2dp"],
                     "ttft_s_2dp": s4[r]["ttft_s_2dp"],
                     "anchor_ok": s4[r]["anchor_ok"]} for r in s4},
        # Warm vulkan boots (cache present) + within-day cross-boot delta.
        "vk_boot1_2dp": vk1["tok_s_2dp"], "vk_boot2_2dp": vk2["tok_s_2dp"],
        "vk_crossboot_pct_2dp": f"{(vk2['tok_s'] / vk1['tok_s'] - 1) * 100:+.2f}%",
        # Hip controls + their cross-boot spread (near-deterministic, ±5%).
        "hip_ctrl1_2dp": h1["tok_s_2dp"], "hip_ctrl2_2dp": h2["tok_s_2dp"],
        "hip_crossboot_pct_1dp": f"{(h2['tok_s'] / h1['tok_s'] - 1) * 100:+.1f}%",
        # Cache-aside arm (cold cache) vs the warm mean — and the swing.
        "aside_2dp": aside["tok_s_2dp"],
        "aside_ttft_s_2dp": aside["ttft_s_2dp"],
        "warm_mean_2dp": round(warm_mean, 2),
        "warm_mean": warm_mean,                     # exact, for assertions
        "warm_ttft_range": tuple(sorted((vk1["ttft_s_2dp"], vk2["ttft_s_2dp"]))),
        "aside": aside["tok_s"],                    # exact, for assertions
        "aside_vs_warm_pct_1dp": f"{(aside['tok_s'] / warm_mean - 1) * 100:+.1f}%",
        "swing_pct_0dp": f"{(warm_mean / aside['tok_s'] - 1) * 100:+.0f}%",
        # The floor/ceiling relabels (v0.1.6): warm-cache, boot-paired,
        # same-day pairings vs the hip controls of the SAME session.
        "warm_pairings": {
            "label": "warm-cache, boot-paired",
            "date": SESSION4_DATE,
            "boot1_pct_1dp": f"{(vk1['tok_s'] / h1['tok_s'] - 1) * 100:+.1f}%",
            "boot2_pct_1dp": f"{(vk2['tok_s'] / h2['tok_s'] - 1) * 100:+.1f}%",
            "boot1": (vk1["tok_s"], h1["tok_s"]),   # exact, for assertions
            "boot2": (vk2["tok_s"], h2["tok_s"]),
        },
        # Telemetry envelopes (post-bench snapshots): each backend sits in
        # its own normal envelope — no thermal/power anomaly to explain
        # the cold/warm gap.
        "telemetry": {
            "vk_post_sclk_range": _tel_range(vk_runs, "post_sclk_mhz"),
            "vk_post_power_range": _tel_range(vk_runs, "post_power_w"),
            "vk_post_temp_range": _tel_range(vk_runs, "post_temp_c"),
            "hip_post_sclk_range": _tel_range(hip_runs, "post_sclk_mhz"),
            "hip_post_power_range": _tel_range(hip_runs, "post_power_w"),
            "hip_post_temp_range": _tel_range(hip_runs, "post_temp_c"),
        },
        # Mesa cache state, receipt-derived: the warm cache is stable across
        # runs (run3 touched nothing), the aside arm rebuilt a fresh cache
        # mid-run.
        "cache": {
            "warm_du_kib": warm_cache.get("du_kib"),
            "warm_files": warm_cache.get("files"),
            "aside_built_du_kib": aside_cache.get("du_kib"),
            "aside_built_files": aside_cache.get("files"),
        },
        # Host state: no reboot between s1 and session 4 (same boot since
        # 2026-08-12) — one common boot_time across all five receipts.
        "host_boot_time": (s4_boot_times.pop() if len(s4_boot_times) == 1
                           else sorted(t for t in s4_boot_times if t)),
        "anchors_ok": sum(1 for r in s4.values() if r["anchor_ok"]),
        "anchors_total": len(s4),
    }

    # ---- sessions 5/6 (H1/H2 daily warm-pair series, 2026-08-19 evening /
    # 2026-08-20 local morning): one vk + one hip run each, exact per-run
    # paths (fail-loud). Session 5 additionally anchors the common-mode
    # drift finding (both backends slower evening vs the session-4 morning
    # runs); session 6 is the OVERNIGHT persistence receipt (cache
    # byte-identical across an idle night, pairing in band). The
    # trigger-hunt evidence note the v0.1.7 ruling cites must exist.
    if not TRIGGER_HUNT_NOTE.exists():
        raise FileNotFoundError(TRIGGER_HUNT_NOTE)

    def _pair_session(sess_dir: Path) -> dict:
        runs = {}
        for run, backend in SESSION56_RUNS:
            path = (sess_dir / run /
                    f"gguf-{backend}-udq4kxl-auto-mtp-c1-ctx131072.json")
            c = json.loads(path.read_text())
            mc = (((c.get("load") or {}).get("telemetry") or {})
                  .get("mesa_cache")) or {}
            runs[run] = {
                "tok_s": _c1_stream_tok_s(c),
                "tok_s_2dp": round(_c1_stream_tok_s(c), 2),
                "ttft_s_2dp": round(_c1_ttft_s(c), 2),
                "agg": c["client"]["aggregate"]["tok_per_s"],
                "agg_2dp": round(c["client"]["aggregate"]["tok_per_s"], 2),
                "anchor_ok": bool(c.get("anchor", {}).get("ok")),
                "started_utc": c["started_utc"],
                "mesa_cache": mc,
            }
        return runs

    def _utc(t: str) -> datetime:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))

    def _pair_block(runs: dict, **extra) -> dict:
        v, h = runs["run1-vk"], runs["run2-hip"]
        blk = {
            "vk_2dp": v["tok_s_2dp"], "hip_2dp": h["tok_s_2dp"],
            "vk": v["tok_s"], "hip": h["tok_s"],    # exact, for assertions
            "pct_2dp": f"{(v['tok_s'] / h['tok_s'] - 1) * 100:+.2f}%",
            "vk_ttft_s_2dp": v["ttft_s_2dp"], "hip_ttft_s_2dp": h["ttft_s_2dp"],
            "vk_agg_2dp": v["agg_2dp"], "hip_agg_2dp": h["agg_2dp"],
            "agg_pct_2dp": f"{(v['agg'] / h['agg'] - 1) * 100:+.2f}%",
            "anchors_ok": sum(1 for r in runs.values() if r["anchor_ok"]),
            "anchors_total": len(runs),
        }
        blk.update(extra)
        return blk

    s5r, s6r = _pair_session(SESSION5_DIR), _pair_session(SESSION6_DIR)
    s5v, s5h = s5r["run1-vk"], s5r["run2-hip"]
    s6v, s6h = s6r["run1-vk"], s6r["run2-hip"]
    # Common-mode drift (finding b): s5 evening vs the s4 morning means,
    # per backend — exact basis, 1dp display.
    wp4 = ev["session4"]["warm_pairings"]
    hip4_mean = (wp4["boot1"][1] + wp4["boot2"][1]) / 2.0
    ev["session5"] = _pair_block(
        s5r, date=SESSION5_DATE, when="evening",
        drift_vs_s4={
            "vk_pct_1dp": f"{(s5v['tok_s'] / warm_mean - 1) * 100:+.1f}%",
            "hip_pct_1dp": f"{(s5h['tok_s'] / hip4_mean - 1) * 100:+.1f}%",
        })
    # Overnight persistence (finding d): the s5->s6 gap is receipts-derived
    # (session-5's LAST receipt start -> session-6's FIRST receipt start,
    # same boot throughout) — 7 h 50 m, not the "~20 h" a naive date-label
    # reading suggests. Cache byte-identity is receipt-derived from the s6
    # vk run's own before_boot/after_teardown readings.
    gap_min = int((_utc(s6v["started_utc"]) - _utc(s5h["started_utc"]))
                  .total_seconds() // 60)
    s6_before = s6v["mesa_cache"].get("before_boot") or {}
    s6_after = s6v["mesa_cache"].get("after_teardown") or {}
    ev["session6"] = _pair_block(
        s6r, date=SESSION6_DATE, when="local morning",
        gap_after_s5_min=gap_min,
        gap_after_s5_hm=f"{gap_min // 60} h {gap_min % 60} m",
        cache={
            "identical": (
                s6_before.get("du_kib") == s6_after.get("du_kib")
                and s6_before.get("files") == s6_after.get("files")
                and s6_before.get("newest_mtime_utc")
                == s6_after.get("newest_mtime_utc")),
            "du_kib": s6_before.get("du_kib"),
            "files": s6_before.get("files"),
            "newest_mtime_utc": s6_before.get("newest_mtime_utc"),
        })
    # Warm pairing band (finding c): 4 sessions — session-4 boots 1/2,
    # session 5, session 6 — exact-basis 2dp (the committed stability
    # README's series convention).
    ev["warm_band"] = {
        "label": "warm-cache pairing band",
        "sessions": ("s4 boot1", "s4 boot2", "s5", "s6"),
        "pcts_2dp": (
            f"{(wp4['boot1'][0] / wp4['boot1'][1] - 1) * 100:+.2f}%",
            f"{(wp4['boot2'][0] / wp4['boot2'][1] - 1) * 100:+.2f}%",
            ev["session5"]["pct_2dp"], ev["session6"]["pct_2dp"]),
    }

    # TTFT observation (aggregate flip is TTFT-driven): vulkan s3 range vs
    vk_ttfts_12 = [
        _c1_ttft_s(json.loads(path.read_text()))
        for path in [*(CELLS_DIR / f"{cid}.json" for cid in STABILITY_CELLS),
                     *(SESSION2_DIR / f"{cid}.json" for cid in STABILITY_CELLS)]]
    vk_ttfts_3 = [s3_cells[cid]["ttft_s_2dp"] for cid in STABILITY_CELLS]
    ev["ttft"] = {
        "vk_s12_range": (round(min(vk_ttfts_12), 2), round(max(vk_ttfts_12), 2)),
        "vk_s3_range": (min(vk_ttfts_3), max(vk_ttfts_3)),
        "hip_s3_2dp": hip3m["ttft_s_2dp"],
        "hip_corpus_2dp": hip3m["corpus_ttft_s_2dp"],
    }

    # Cross-session anchor tally: the re-measured cell runs s1/s2/s3 (3+3+4
    # receipts), the five session-4 runs (R2), the four session-5/6 runs
    # (H1/H2 daily series), plus the soak's post-load anchor — the "pit
    # does NOT reproduce on vulkan" evidence the supersession note restates.
    cell_runs = [json.loads((CELLS_DIR / f"{cid}.json").read_text())
                 for cid in STABILITY_CELLS]
    cell_runs += [json.loads((SESSION2_DIR / f"{cid}.json").read_text())
                  for cid in STABILITY_CELLS]
    cell_runs += [hip3] + [json.loads((SESSION3_DIR / f"{cid}.json").read_text())
                           for cid in STABILITY_CELLS]
    cell_runs += [json.loads((SESSION4_DIR / run /
                              f"gguf-{backend}-udq4kxl-auto-mtp-c1-"
                              f"ctx131072.json").read_text())
                  for run, backend in SESSION4_RUNS]
    cell_runs += [json.loads((sess / run /
                              f"gguf-{backend}-udq4kxl-auto-mtp-c1-"
                              f"ctx131072.json").read_text())
                  for sess in (SESSION5_DIR, SESSION6_DIR)
                  for run, backend in SESSION56_RUNS]
    ev["anchors"] = {
        "cell_runs_ok": sum(1 for c in cell_runs
                            if c.get("anchor", {}).get("ok")),
        "cell_runs_total": len(cell_runs),
        "with_soak_ok": sum(1 for c in cell_runs if c.get("anchor", {}).get("ok"))
        + (1 if soak.get("anchor", {}).get("ok") else 0),
        "with_soak_total": len(cell_runs) + 1,
    }
    return ev


_STABILITY_EVIDENCE: dict | None = None


def stability_evidence() -> dict:
    """Memoized stability-evidence loader (lazy — importing this module,
    e.g. from the tests, must stay side-effect-free). Missing receipts
    raise FileNotFoundError on purpose: the v0.1.3/v0.1.4/v0.1.6/v0.1.7
    ruling notes quote this evidence, so regenerating without it must fail
    loudly rather than silently regress to pre-v0.1.3 wording. Covers
    session 2 (+ soak) since v0.1.3, session 3 since v0.1.4, session 4
    (per-run subdirectories, exact paths) since v0.1.6, and sessions 5/6
    (warm-pair series; plus the trigger-hunt note existence check) since
    v0.1.7."""
    global _STABILITY_EVIDENCE
    if _STABILITY_EVIDENCE is None:
        _STABILITY_EVIDENCE = _load_stability_evidence()
    return _STABILITY_EVIDENCE


def v012_ruling_note(cid: str, all_metrics: dict | None,
                     unified_cell: dict | None = None) -> str | None:
    """Controller ruling-layer prose (v0.1.2 review; v0.1.4 supersession on
    the vulkan mtp-c1 mapping cell). Numbers are interpolated from the
    raw-cell metrics + stability receipts so the notes can never drift
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
        s3 = ev["session3"]["cells"]
        hip3 = ev["session3"]["hip_mtp1"]
        cp = ev["clean_pairing"]
        cd = ev["crossday"]
        an = ev["anchors"]
        tf = ev["ttft"]
        m1 = c1["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]
        m4 = c1["gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072"]
        b1 = c1["gguf-vulkan-udq4kxl-auto-base-c1-ctx131072"]
        m1d = cd["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]
        m4d = cd["gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072"]
        b1d = cd["gguf-vulkan-udq4kxl-auto-base-c1-ctx131072"]
        clean_gap_pct = (cp["vk"] / cp["hip"] - 1) * 100.0
        # Session-4 evidence (R2, v0.1.6): cache-state bounds, the warm
        # boot-paired relabels, the telemetry envelopes, and the cache
        # receipts — every number in the R2 paragraph interpolates from
        # these, never a hand literal.
        s4 = ev["session4"]
        s3vk_2dp = s3["gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072"]["s3_2dp"]
        wp = s4["warm_pairings"]
        ch = s4["cache"]
        t4 = s4["telemetry"]
        # Sessions 5/6 + the warm band (H2, v0.1.7): every number in the
        # H2 refinement paragraph interpolates from these, never a hand
        # literal.
        s5 = ev["session5"]
        s6 = ev["session6"]
        wb = ev["warm_band"]
        # Warm-session vk range for the floor-case relabel (s1/s2 corpus +
        # session-2 re-runs, s4 warm boots, s5, s6 — every vk mtp-c1 run
        # with the cache present).
        warm_vals = [m1["s1_2dp"], m1["s2_2dp"],
                     s4["vk_boot1_2dp"], s4["vk_boot2_2dp"],
                     s5["vk_2dp"], s6["vk_2dp"]]
        warm_lo_2dp, warm_hi_2dp = min(warm_vals), max(warm_vals)

        def _rng(pair) -> str:
            """Envelope display: '1433–1533 MHz'; a single value prints
            once ('58 °C'), never '58–58'."""
            return (f"{pair[0]:.0f}" if pair[0] == pair[1]
                    else f"{pair[0]:.0f}–{pair[1]:.0f}")

        t4v = (_rng(t4["vk_post_sclk_range"]), _rng(t4["vk_post_power_range"]),
               _rng(t4["vk_post_temp_range"]))
        t4h = (_rng(t4["hip_post_sclk_range"]),
               _rng(t4["hip_post_power_range"]), _rng(t4["hip_post_temp_range"]))
        return (f"Controller ruling {MAPPING_RULING_DATE} (v0.1.4) "
                f"SUPERSEDES the controller ruling 2026-08-18 (the v0.1.2 "
                f"promotion + the v0.1.3 two-session/soak wording; both "
                f"preserved in CHANGELOG.md): the promotion rested on a "
                f"MIXED-DEPTH headline — vulkan d1 "
                f"{fmt(vk_mtp1['per_stream_tok_s_median'], 2)} vs hip "
                f"implicit-d3 {fmt(hip_mtp1['per_stream_tok_s_median'], 2)} "
                f"tok/s ({headline}, cross-depth caveat: "
                f"{CROSS_DEPTH_CAVEAT}) — the hip side of that pairing was "
                f"depth-confounded. The CLEAN same-day d1/d1 pairing "
                f"(session 3, {cp['date']}: both backends explicit "
                f"--spec-draft-n-max 1, same pin/model/prompts/harness; "
                f"receipts {ev['pointer']}session3-{cp['date']}/) measures "
                f"vulkan {cp['vk_2dp']:.2f} vs hip {cp['hip_2dp']:.2f} "
                f"tok/s = {cp['pct_2dp']} single-stream median (gap "
                f"+{cp['gap_2dp']:.2f}), and the AGGREGATE basis flips: "
                f"hip {cp['hip_agg_2dp']:.2f} vs vulkan "
                f"{cp['vk_agg_2dp']:.2f} tok/s ({cp['agg_pct_2dp']}, "
                f"TTFT-driven — vulkan TTFT {tf['vk_s3_range'][0]:.2f}–"
                f"{tf['vk_s3_range'][1]:.2f} s this session vs "
                f"{tf['vk_s12_range'][0]:.2f}–{tf['vk_s12_range'][1]:.2f} s "
                f"across the 2026-08-18 sessions; hip TTFT "
                f"{tf['hip_s3_2dp']:.2f} s this session vs "
                f"{tf['hip_corpus_2dp']:.2f} s on its corpus receipt). "
                f"Cross-day variance (s3 {cp['date']} vs s1/s2 2026-08-18, "
                f"same cells): mtp {m1['s1_2dp']:.2f}/{m1['s2_2dp']:.2f}→"
                f"{s3['gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072']['s3_2dp']:.2f} "
                f"({m1d['vs_s1_pct']}/{m1d['vs_s2_pct']}, max spread "
                f"{m1d['spread_pct']:.2f}%), mtp4 {m4['s1_2dp']:.2f}/"
                f"{m4['s2_2dp']:.2f}→"
                f"{s3['gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072']['s3_2dp']:.2f} "
                f"({m4d['vs_s1_pct']}/{m4d['vs_s2_pct']}, spread "
                f"{m4d['spread_pct']:.2f}%), base {b1['s1_2dp']:.2f}/"
                f"{b1['s2_2dp']:.2f}→"
                f"{s3['gguf-vulkan-udq4kxl-auto-base-c1-ctx131072']['s3_2dp']:.2f} "
                f"({b1d['vs_s1_pct']}/{b1d['vs_s2_pct']}, spread "
                f"{b1d['spread_pct']:.2f}%); hip is same-session stable "
                f"(d1 {cp['hip_2dp']:.2f} vs implicit-d3 "
                f"{hip3['corpus_2dp']:.2f} tok/s = "
                f"{hip3['corpus_delta_pct']} is DAY-confounded — labeled, "
                f"not a depth claim). The host-level cause of the vulkan "
                f"cross-day drop is NOT recorded — the receipts carry "
                f"VRAM/GTT only, no clock/thermal telemetry (known harness "
                f"debt) — that cause statement is itself SUPERSEDED the "
                f"same day by the R2 note below. MAPPING, per the "
                f"{MAPPING_RULING_DATE} ruling: the "
                f"quickstart downgrades BACKEND=vulkan from 'recommended "
                f"opt-in' to an AVAILABLE experimental opt-in (mechanism "
                f"unchanged, 'experimental, see verdicts/stability' framing "
                f"kept — no recommendation language), and hip WITH_MTP=1 is "
                f"BOTH the default backend AND the recommended path; this "
                f"cell's MECHANICAL verdict (recommended) is unchanged — "
                f"what changed is the quickstart recommendation-mapping "
                f"layer. No-flip closed on the clean basis, arithmetic "
                f"recorded: {cp['vk_2dp']:.2f} vs {cp['hip_2dp']:.2f} "
                f"tok/s is {cp['pct_2dp']} << the >25% pre-registered flip "
                f"threshold (the mixed-depth {headline} and the "
                f"exactly-+25.0% session-2 headline the v0.1.3 note guarded "
                f"are both superseded by this clean pairing). R2 "
                f"ROOT-CAUSE (2026-08-19, v0.1.6) SUPERSEDES the cause "
                f"statement above — dated, history visible: session 4 "
                f"(5 controlled runs under the telemetry harness, receipts "
                f"{ev['pointer']}session4-2026-08-19/, per-run "
                f"subdirectories) EXPLAINS the cross-day variance as Mesa "
                f"shader-cache state dependence. Bounds, identical "
                f"config/flags/pin: warm boots "
                f"{s4['vk_boot1_2dp']:.2f}/{s4['vk_boot2_2dp']:.2f} tok/s "
                f"(cross-boot {s4['vk_crossboot_pct_2dp']}, warm mean "
                f"{s4['warm_mean_2dp']:.2f}, warm TTFT "
                f"{s4['warm_ttft_range'][0]:.2f}–"
                f"{s4['warm_ttft_range'][1]:.2f} s); cache-aside arm "
                f"{s4['aside_2dp']:.2f} tok/s / TTFT "
                f"{s4['aside_ttft_s_2dp']:.2f} s "
                f"({s4['aside_vs_warm_pct_1dp']} vs the warm mean — "
                f"reproduces and exceeds the s3 slow signature "
                f"{s3vk_2dp:.2f}/{tf['vk_s3_range'][0]:.2f} s TTFT; the "
                f"run rebuilt {ch['aside_built_du_kib']} KiB/"
                f"{ch['aside_built_files']} cache files mid-run while the "
                f"warm cache stayed stable at {ch['warm_du_kib']} KiB/"
                f"{ch['warm_files']} files across runs, one run touching "
                f"nothing): a cold→warm swing of {s4['swing_pct_0dp']}. "
                f"s3's {s3vk_2dp:.2f} sits BETWEEN cold "
                f"({s4['aside_2dp']:.2f}) and warm "
                f"({s4['warm_mean_2dp']:.2f}) → a PARTIAL-COLD cache "
                f"state is consistent with the s3 drop; the s3 TRIGGER "
                f"remains UNIDENTIFIED (no Mesa upgrade, no reboot — host "
                f"up since {s4['host_boot_time'][:10]}, no cache-clear "
                f"found — stated honestly; that PARTIAL-COLD reading is "
                f"itself SUPERSEDED 2026-08-20 by the H2 forensics below — "
                f"the cache was forensically INTACT at s3). RELABELS, arithmetic "
                f"unchanged: the clean pairing {cp['pct_2dp']} is the "
                f"CONSERVATIVE FLOOR CASE (vk measured in a partial-cold "
                f"state; the no-flip conclusion stands, "
                f"{cp['pct_2dp']} << the >25% threshold); the warm "
                f"same-day boot-paired pairings are "
                f"{wp['boot1_pct_1dp']} ({s4['vk_boot1_2dp']:.2f} vs "
                f"{s4['hip_ctrl1_2dp']:.2f}) and {wp['boot2_pct_1dp']} "
                f"({s4['vk_boot2_2dp']:.2f} vs "
                f"{s4['hip_ctrl2_2dp']:.2f}) — label: {wp['label']}, "
                f"{wp['date']} (warm-cache ceiling context, a single warm "
                f"session; hip cross-boot "
                f"{s4['hip_crossboot_pct_1dp']} — near-deterministic, "
                f"within ±5%). Telemetry shows NO thermal/power anomaly "
                f"(vk post-bench {t4v[0]} MHz / "
                f"{t4v[1]} W / "
                f"{t4v[2]} °C; hip "
                f"{t4h[0]} MHz / "
                f"{t4h[1]} W / "
                f"{t4h[2]} °C — each backend in "
                f"its own normal envelope). RECOMMENDATION UNCHANGED "
                f"(controller ruling 2026-08-19, recorded, not "
                f"re-deliberated): vulkan stays an AVAILABLE experimental "
                f"opt-in, NOT recommended; hip WITH_MTP=1 SPEC_DEPTH=1 "
                f"stays BOTH the default AND the recommended path — "
                f"rationale: one warm session; the trigger is unknown "
                f"(users cannot be guaranteed to stay warm); the "
                f"warm/cold swing is a user-facing UX risk (first boot "
                f"after a cache clear: ~12.4 tok/s / ~12.5 s TTFT until "
                f"warm). The re-recommendation question is recorded as "
                f"OPEN for the human owner (README roadmap) — RESOLVED "
                f"2026-08-20 by the OWNER DECISION addendum below (NO). H2 "
                f"REFINEMENT (2026-08-20, v0.1.7) SUPERSEDES the v0.1.6 "
                f"partial-cold reading of s3 — dated supersession #3, "
                f"history visible above: the trigger-hunt cache forensics "
                f"({TRIGGER_HUNT_POINTER} — a read-only host-log hunt in "
                f"the s2→s3 causal window, independently reproduced) found "
                f"the mesa cache INTACT at s3 — 866 files pre-window / "
                f"0 written inside the causal window / 1 post (the "
                f"session-4 marker) — so 's3 = partial-cold cache' is "
                f"CONTRADICTED as the explanation: s3 ran slow "
                f"({s3vk_2dp:.2f}) with a warm untouched cache. The "
                f"cold-cache ARM remains valid as the swing BOUND proof "
                f"(cold {s4['aside_2dp']:.2f} vs warm mean "
                f"{s4['warm_mean_2dp']:.2f} = the {s4['swing_pct_0dp']} "
                f"class), NOT s3's explanation. s3's vk-specific TRIGGER: "
                f"UNIDENTIFIED — cache ruled out; NO suspend/resume, NO "
                f"amdgpu reset/errors, NO power-profile switch in the "
                f"causal window; the clock-stepping condition was ABSENT "
                f"during s3's run; the only discrete in-window state "
                f"change is the unattended-upgrade of linux-libc-dev/"
                f"linux-tools-common 6.8.0-137→138 (06:20 local 08-19) — "
                f"recorded as fact, NO mechanism claimed. NEW RECORDED "
                f"FINDINGS: (a) chronic common-mode clock-stepping — 883+ "
                f"'Clock change detected' events since the 2026-08-12 "
                f"boot, still accruing (count per the note; present "
                f"during s1 ×2, the s2 soak ×1, and s5 ×3) — explicitly "
                f"NOT s3-specific; (b) common-mode session drift — BOTH "
                f"backends slower evening vs morning (s5 vs the s4 means: "
                f"vk {s5['drift_vs_s4']['vk_pct_1dp']}, hip "
                f"{s5['drift_vs_s4']['hip_pct_1dp']}): shared host-state "
                f"drift of ±5–6%; (c) the warm pairing band across 4 "
                f"sessions is {'/'.join(wb['pcts_2dp'])} (s4 boots 1-2, "
                f"s5, s6); (d) OVERNIGHT warm persistence CONFIRMED — "
                f"session 6 ran {s6['gap_after_s5_hm']} after s5 "
                f"(receipts-derived, same boot), the cache byte-identical "
                f"({s6['cache']['du_kib']} KiB/{s6['cache']['files']} "
                f"files, zero writes, newest mtime still session-4 run "
                f"1's {s6['cache']['newest_mtime_utc']}), pairing "
                f"{s6['pct_2dp']} in band (vk {s6['vk_2dp']:.2f} / TTFT "
                f"{s6['vk_ttft_s_2dp']:.2f} s; hip {s6['hip_2dp']:.2f} / "
                f"TTFT {s6['hip_ttft_s_2dp']:.2f} s); (e) aggregate/TTFT "
                f"consistently hip-favored — TTFT vk 8.4–8.6 s vs hip "
                f"5.4–5.6 s every session (s5 "
                f"{s5['vk_ttft_s_2dp']:.2f}/{s5['hip_ttft_s_2dp']:.2f} s, "
                f"s6 {s6['vk_ttft_s_2dp']:.2f}/{s6['hip_ttft_s_2dp']:.2f} "
                f"s); aggregate s5 {s5['agg_pct_2dp']} (vk "
                f"{s5['vk_agg_2dp']:.2f} vs hip {s5['hip_agg_2dp']:.2f}), "
                f"s6 {s6['agg_pct_2dp']} (hip {s6['hip_agg_2dp']:.2f} vs "
                f"vk {s6['vk_agg_2dp']:.2f}) — vulkan's edge is the "
                f"single-stream median only. RELABEL basis refined: the "
                f"clean pairing {cp['pct_2dp']} keeps the CONSERVATIVE "
                f"FLOOR CASE label — vk measured in the UNIDENTIFIED slow "
                f"state, well below its warm-session range "
                f"({warm_lo_2dp:.2f}–{warm_hi_2dp:.2f} tok/s across "
                f"s1/s2/s4/s5/s6) — the arithmetic and the "
                f"no-flip conclusion stand unchanged. RECOMMENDATION UNCHANGED "
                f"(controller ruling 2026-08-20, recorded, not "
                f"re-deliberated): vulkan stays an AVAILABLE experimental "
                f"opt-in, NOT recommended; hip WITH_MTP=1 SPEC_DEPTH=1 "
                f"stays BOTH the default AND the recommended path; the "
                f"warmup guidance stands. The OPEN re-recommendation "
                f"question (README roadmap) is restated BOTH ways "
                f"honestly: FOR — the warm band is now 4 consistent "
                f"sessions and overnight persistence is proven; AGAINST — "
                f"the s3 trigger is MORE mysterious (cache ruled out), "
                f"P(vk-specific slow state) is unquantified, and "
                f"aggregate/TTFT stay hip-favored. Not decided here — "
                f"DECIDED 2026-08-20 (owner ruling, v0.1.8): NO, see the "
                f"OWNER DECISION addendum below. "
                f"Unaffected "
                f"findings, restated: the greedy pit still does NOT "
                f"reproduce on vulkan — cell-run anchors "
                f"{an['cell_runs_ok']}/{an['cell_runs_total']} clean "
                f"across s1–s6 ({an['with_soak_ok']}/{an['with_soak_total']} "
                f"with the soak anchor); depth 1 still beats depth 4 on "
                f"both backends (mtp stays the recommended variant, no "
                f"mtp4 recommendation; clean-gap exact basis "
                f"{clean_gap_pct:+.2f}%). "
                # v0.1.8 (2026-08-20): the OWNER DECISION addendum —
                # resolution #4. Every number interpolates from the same
                # loaders as the layers above (s4/s5/s6 TTFTs, the warm
                # band, the cold-arm figures, the session-4 telemetry
                # envelopes t4v/t4h); the crossover is arithmetic over
                # three sessions' receipts and prints labeled DERIVED.
                f"OWNER DECISION (2026-08-20, v0.1.8) RESOLVES the OPEN "
                f"re-recommendation question — dated resolution #4, "
                f"history visible above: NO. The repository owner rules "
                f"— recorded, not re-deliberated — NOT re-recommending "
                f"BACKEND=vulkan: it stays an AVAILABLE experimental "
                f"opt-in, NOT recommended, and hip WITH_MTP=1 "
                f"SPEC_DEPTH=1 stays BOTH the default AND the recommended "
                f"path (the mapping of record is CONFIRMED, not changed). "
                f"Rationale, from the verifier-locked evidence above: "
                f"(1) end-to-end latency PARITY at typical reply lengths "
                f"— vk's TTFT is consistently ~3 s higher (s5/s6 "
                f"{s5['vk_ttft_s_2dp']:.2f}/{s6['vk_ttft_s_2dp']:.2f} vs "
                f"hip {s5['hip_ttft_s_2dp']:.2f}/"
                f"{s6['hip_ttft_s_2dp']:.2f} s), offsetting the warm "
                f"streaming gain (4-session band "
                f"{'/'.join(wb['pcts_2dp'])}); the crossover where vk's "
                f"streaming gain repays the slower first token is "
                f"≈230–310 tokens (DERIVED from the s4/s5/s6 receipts — "
                f"arithmetic over three sessions, not a measurement: "
                f"2.91/0.00927≈314, 2.86/0.01227≈233, 3.05/0.00978≈312); "
                f"(2) a cold-cache first boot ({s4['aside_2dp']:.2f} "
                f"tok/s, TTFT {s4['aside_ttft_s_2dp']:.2f} s — worse "
                f"than default hip on both) is the state a "
                f"recommendation would systematically deliver to new "
                f"users first; (3) 1-of-7 vk runs hit the unexplained "
                f"slow state (s3 {s3vk_2dp:.2f}, trigger UNIDENTIFIED "
                f"after forensics); (4) the evidence base is "
                f"single-host / single-ICD (RADV 25.2.8) / "
                f"single-Mesa-point / 2-days. SELECTION GUIDANCE "
                f"(user-facing, NON-recommending — self-selection "
                f"criteria, never promotion; mirrored in the README "
                f"roadmap decision entry, the quickstart echo, and "
                f"docs/adaptation.md §Vulkan): users generating LONG "
                f"outputs (≳300-token replies, the derived crossover) or "
                f"sensitive to GPU power/heat/noise (package ~{t4v[1]} W "
                f"vs ~{t4h[1]} W hip) may reasonably SELF-SELECT the vk "
                f"opt-in; short-reply interactive users get no "
                f"end-to-end benefit and a slower first token. "
                f"PRE-REGISTERED PROMOTION CRITERIA — ALL four must hold "
                f"before any future upgrade to conditional-recommended: "
                f"(1) a daily warm series of at least 7 days with ZERO "
                f"slow-state recurrence; (2) the vk c8/c16 cells measured "
                f"with anchors clean (pit coverage — currently "
                f"unmeasured); (3) at least one independent host/ICD "
                f"replication (a community submission is ideal); (4) the "
                f"TTFT gap stated as an applicability condition "
                f"(long-generation only), not a footnote. Zero "
                f"metric/verdict changes — the 8/14/6 distribution "
                f"stands.")
    if cid == "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072":
        cp = stability_evidence()["clean_pairing"]
        return (f"Controller review 2026-08-18: mechanical verdict confirmed, "
                f"no override. Backend alone is a small c1 delta — "
                f"{fmt(vk_base1['per_stream_tok_s_median'])} vs hip "
                f"{fmt(hip_base1['per_stream_tok_s_median'])} tok/s "
                f"({_pct(vk_base1['per_stream_tok_s_median'], hip_base1['per_stream_tok_s_median'])}) "
                f"— the AMD 24.5 tok/s Day-0 anchor gap is not a pure "
                f"backend effect; the biggest single-stream lever measured on "
                f"this host is Vulkan+MTP "
                f"({fmt(vk_mtp1['per_stream_tok_s_median'])} tok/s in this "
                f"v0.1.2 cell) — downgraded {MAPPING_RULING_DATE} from "
                f"recommended to an AVAILABLE experimental opt-in (see the "
                f"mtp-c1 supersession note: the clean d1 pairing is "
                f"{cp['pct_2dp']}). {n_ok}-of-{n_vk} vulkan anchors clean "
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
                    unified_cell: dict | None = None,
                    dflash_pair: dict | None = None) -> dict:
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

    elif parts["mtp"] == "dflash":
        # v0.1.14 (2026-08-21): the DFlash2 corpus cells. Gains cite the
        # same-session pairing partners (session receipts, NOT corpus —
        # the corpus base/mtp cells are the 262144 story; the pairing ran
        # at the dflash KV-feasible 131072 tier).
        base_m2 = dflash_pair["base"]
        mtp_m2 = dflash_pair["mtp"]
        gains_base = {
            "per_stream_pct": round((med / base_m2["per_stream_tok_s_median"] - 1) * 100, 1),
            "aggregate_pct": round((agg / base_m2["aggregate_tok_s"] - 1) * 100, 1),
            "base_per_stream_tok_s_median": base_m2["per_stream_tok_s_median"],
            "base_aggregate_tok_s": base_m2["aggregate_tok_s"],
            "basis": "same-session pairing receipt 2026-08-21 @131072 "
                     "(stability/dflash-pairing-2026-08-21/)",
        }
        gains_mtp = {
            "per_stream_pct": round((med / mtp_m2["per_stream_tok_s_median"] - 1) * 100, 1),
            "aggregate_pct": round((agg / mtp_m2["aggregate_tok_s"] - 1) * 100, 1),
            "mtp_per_stream_tok_s_median": mtp_m2["per_stream_tok_s_median"],
            "mtp_aggregate_tok_s": mtp_m2["aggregate_tok_s"],
            "basis": "same-session pairing receipt 2026-08-21 @131072 "
                     "(stability/dflash-pairing-2026-08-21/)",
        }
        applicability = (
            "Applicability: single session, one host; needs the upstream "
            "PR #52816 patch (patches/vllm-dflash2-pr52816.diff, unmerged "
            "at measurement — vLLM pin 4d2a68d has DFlash v1 only); ctx "
            "262144 is KV-infeasible with the draft loaded (21.63 needed "
            "vs 15.46 GiB available — 131072 only; boot receipt "
            "dflash2-validation.md).")
        if parts["c"] == 1:
            reason = (
                f"DFlash2 speculative decoding lifts the single-stream vLLM "
                f"cell to {fmt(med)} tok/s (TPOT "
                f"{fmt(m['tpot_ms_median'])} ms/token) — the first measured "
                f"vLLM cell at/above the 10 tok/s interactive floor on this "
                f"host. Same-session pairing @131072: "
                f"+{gains_base['per_stream_pct']}% vs base ({fmt(med)} vs "
                f"{fmt(gains_base['base_per_stream_tok_s_median'])} tok/s) "
                f"and +{gains_mtp['per_stream_pct']}% vs MTP ({fmt(med)} vs "
                f"{fmt(gains_mtp['mtp_per_stream_tok_s_median'])} tok/s) — "
                f"the draft beats both native speculators' single-stream "
                f"cells. Anchor clean (greedy byte-identity — the lossless "
                f"claim holds), boot healthy ({boot_s} s, GTT {gtt_gib} "
                f"GiB). Controller ruling 2026-08-21: the 2026-08-17 "
                f"premise 'all measured vLLM cells are below the 10 tok/s "
                f"floor' is SUPERSEDED for this cell (dated supersession, "
                f"never silent); the GGUF hip MTP path (13.86 tok/s, clean "
                f"d1 pairing) REMAINS the recommended interactive-chat "
                f"path — dflash-c1 is the vLLM-path single-stream choice. "
                f"{applicability}")
            conditions = (
                "Single-stream vLLM serving; multi-user tiers erode the "
                "gain (see the dflash-c8 caution cell). Concurrency erodes "
                "DFlash2's edge (upstream's stated shape, confirmed here at "
                "c8). The corpus base/mtp @262144 cells remain the "
                "262144-context/vision/batch reference. " + applicability)
            workaround = (
                "Interactive chat stays on the GGUF path "
                "(WITH_MTP=1 SPEC_DEPTH=1); serve DFlash2 with "
                "scripts/03-serve-vllm.sh --dflash2 (ctx via MAX_MODEL_LEN "
                "=131072 or lower).")
        else:
            reason = (
                f"Per-stream median {fmt(med)} tok/s (TPOT "
                f"{fmt(m['tpot_ms_median'])} ms/token) at the multi-user "
                f"c{parts['c']} tier — below the 10 tok/s interactive "
                f"floor. DFlash2's single-stream gain erodes under "
                f"concurrency (upstream's stated shape, confirmed here): "
                f"same-session @131072 pairing +{gains_base['per_stream_pct']}% "
                f"vs base-c{parts['c']} per-stream ({fmt(med)} vs "
                f"{fmt(gains_base['base_per_stream_tok_s_median'])} tok/s) "
                f"but only +{gains_mtp['per_stream_pct']}% vs mtp-c{parts['c']} "
                f"({fmt(med)} vs {fmt(gains_mtp['mtp_per_stream_tok_s_median'])} "
                f"tok/s); aggregate {fmt(agg)} vs base "
                f"{fmt(gains_base['base_aggregate_tok_s'])} tok/s "
                f"(+{gains_base['aggregate_pct']}%) — no regression; MTP's "
                f"beneficial-through-c8 story is unchanged. Anchor clean, "
                f"boot healthy ({boot_s} s, GTT {gtt_gib} GiB). "
                f"{applicability}")
            conditions = (
                "Multi-user/batch on this path: the corpus base/mtp "
                "@262144 cells remain the reference (262144 context, "
                "vision, best aggregate); single-stream → the dflash-c1 "
                "recommended cell. " + applicability)
            workaround = (
                "Single-stream workloads: scripts/03-serve-vllm.sh "
                "--dflash2; batch: serve base per the corpus cells.")

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
    if dflash_pair:
        out["metrics"]["dflash_gain_vs_base"] = gains_base
        out["metrics"]["dflash_gain_vs_mtp"] = gains_mtp
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
        # v0.1.14: dflash cells pair against the same-session receipts (the
        # corpus has no base/mtp cells at the 131072 tier).
        dflash_pair = None
        if parts["mtp"] == "dflash":
            dflash_pair = {
                who: compute_metrics(json.loads(
                    (DFLASH_SESSION_DIR / who /
                     f"{parts['path']}-{parts['weight']}-{parts['kv']}-{who}"
                     f"-c{parts['c']}-ctx{parts['ctx']}.json").read_text()))
                for who in ("base", "mtp")
            }
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
                                         cells.get(UNIFIED_RIDER_ID),
                                         dflash_pair))

    # Top-level shape is locked by schemas/benchmark-verdicts.schema.json
    # (additionalProperties: false) — provenance stays in this generator's
    # docstring and in the rendered docs, not in the JSON.
    return {
        "checked_at": EVIDENCE_RULING_DATE,
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
