#!/usr/bin/env python3
"""Generate the declared benchmark matrix: docs/results/matrix-714/matrix.json.

Deterministic by construction: fixed iteration order, no timestamps inside
cells, `generated_at` is a constant date. Re-running reproduces the same
bytes (until the constants below change). This emits the DECLARATION (valid
cells `planned`, unsupported tiers `dropped`); the cell runners flip statuses
to `measured` as cells run.

Measurement-state preservation (2026-08-18 id-migration semantics, superset
of the 2026-08-17 final-review guard): a plain run CARRIES OVER the
committed measurement state — every committed `measured` cell's `status` +
`degraded` + `note` — onto its declared id via the baked-in LEGACY->NEW
mapping (legacy unprefixed gguf ids ARE hip; vllm ids never had a tag).
Regeneration therefore never clobbers measured cells that remain declared;
it REFUSES only when a committed `measured` cell would fall OUT of the
declaration entirely (lost evidence), naming it:

    python3 scripts/gen-matrix.py            # carry-over regen; refuses only
                                             # if a measured cell would be lost
    python3 scripts/gen-matrix.py --check    # exit 0 iff regeneration is a
                                             # no-op vs the committed file
    python3 scripts/gen-matrix.py --force    # re-emit the bare declaration
                                             # (statuses must be re-flipped
                                             # by the cell runners)

Cell id grammar (shared with schemas/benchmark-verdicts.schema.json and the
cell runners — keep the literal in sync):
    vllm-bf16-auto-{mtp}-c{N}-ctx{K}                        (unchanged)
    gguf-{backend}-udq4kxl-auto-{mtp}-c{N}-ctx{K}[-unified] (2026-08-18)
    backend ∈ {hip, vulkan}   — gguf only; legacy unprefixed ids == hip
    mtp     ∈ {base, mtp, mtp4} — mtp4 is the depth-4 variant (v0.1.2)
    -unified — optional, c4 gguf cells only: the unified-default-boot rider

Rules encoded here (see docs/results/METHODOLOGY.md §8 + the 2026-08-18
addendum):
- weight is path-bound by construction: gguf<->udq4kxl, vllm<->bf16.
  Cross pairs are invalid and never emitted.
- vllm ctx tier 32768 is not a supported conf tier -> emitted as dropped
  with reason (spec 4.3: every dropped cell is recorded with reason).
- The 2026-08-17 declared-priority subset rides on the hip backend:
  gguf {base,mtp} x {1,4,8,16} @131072 + base x {32768,262144} @N=1,4;
  vllm {base,mtp} x {1,4,8,16} @262144.
- 2026-08-18 (v0.1.2 Vulkan x MTP experiment, declared pre-measurement):
  8 additional planned cells — vulkan x {base,mtp,mtp4} x {1,4} @131072,
  hip mtp4-c1 @131072, and the hip unified-default-boot c4@131072 rider
  (id suffix -unified). Everything else valid: planned(reason="time-boxed
  session; machinery complete").
- 2026-08-21 (v0.1.9 DFlash2 integration, declared pre-measurement): 2
  additional planned cells — vllm dflash x {1,8} @131072 (the spec-variant
  slot gains "dflash", vllm path only: llama.cpp cannot run the
  block-diffusion drafter; 262144 re-tiered away same day — KV-infeasible
  with the draft loaded on the 80 GiB pool, boot receipt 2026-08-21).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "results" / "matrix-714" / "matrix.json"

GENERATED_AT = "2026-08-21"  # declaration date; a date, never a timestamp

# path -> bound weight (invalid cross pairs are never constructed)
PATH_WEIGHT = {"gguf": "udq4kxl", "vllm": "bf16"}
# path -> offered ctx tiers
PATH_CTX = {
    "gguf": (32768, 131072, 262144),
    "vllm": (131072, 262144),
}
UNSUPPORTED_TIERS = {("vllm", 32768)}  # recorded as dropped, with reason

CONCURRENCIES = (1, 4, 8, 16)
MTP_MODES = ("base", "mtp")  # hip base product; mtp4 enters via NEW_CELLS
HIP = "hip"  # the incumbent backend: all 2026-08-17 cells are hip

RUNNER_HINT = {"gguf": "scripts/run-cell-gguf.sh", "vllm": "scripts/run-cell-vllm.sh"}

PLANNED_REASON_PRIORITY = "declared priority subset for this session (see METHODOLOGY.md §8)"
PLANNED_REASON_REST = "time-boxed session; machinery complete"
PLANNED_REASON_V012 = ("v0.1.2 Vulkan×MTP experiment priority (declared "
                       "pre-measurement, METHODOLOGY.md §8 addendum 2026-08-18)")
PLANNED_REASON_V019 = ("v0.1.9 DFlash2 block-diffusion speculative decoding "
                       "priority (draft incoai/Qwen3.8-27B-DFlash2 on the "
                       "vllm path; same-session pairing cells c1/c8 "
                       "@131072 — re-tiered from 262144 after the dflash "
                       "boot failed the KV budget there (21.63 needed vs "
                       "15.46 GiB available; engine max-len estimate "
                       "181376), declared 2026-08-21)")
DROPPED_REASONS = {
    ("vllm", 32768): (
        "32768 is not a supported conf tier for the vllm path "
        "(validated conf serves --max-model-len 262144; no tier below it is offered)"
    ),
}

# The 8 new v0.1.2 cells (fixed order; all declared planned + priority):
# vulkan x {base,mtp,mtp4} x {1,4} @131072 (6) + hip mtp4-c1 @131072 (1) +
# hip unified-default-boot base-c4 @131072 (1 rider, -unified suffix).
NEW_CELLS_V012: tuple[tuple[str, str, int, int, bool], ...] = (
    ("vulkan", "base", 1, 131072, False),
    ("vulkan", "base", 4, 131072, False),
    ("vulkan", "mtp", 1, 131072, False),
    ("vulkan", "mtp", 4, 131072, False),
    ("vulkan", "mtp4", 1, 131072, False),
    ("vulkan", "mtp4", 4, 131072, False),
    ("hip", "mtp4", 1, 131072, False),
    ("hip", "base", 4, 131072, True),  # unified-default-boot rider (no -np)
)

# The 2 new v0.1.9 cells (fixed order; declared planned + priority): the
# DFlash2 block-diffusion draft on the vllm path — dflash x {c1,c8} @131072
# (262144 is KV-infeasible with the draft loaded on the 80 GiB pool — see
# PLANNED_REASON_V019). The base/mtp same-session pairing partners run at
# the same tier (stability-session receipts; the corpus base/mtp cells are
# the 262144 ones).
NEW_CELLS_V019: tuple[tuple[str, str, int, int], ...] = (
    ("vllm", "dflash", 1, 131072),
    ("vllm", "dflash", 8, 131072),
)


def cell_id(path: str, mtp: str, n: int, ctx: int, *,
            backend: str = HIP, unified: bool = False) -> str:
    if path == "gguf":
        cid = f"gguf-{backend}-{PATH_WEIGHT[path]}-auto-{mtp}-c{n}-ctx{ctx}"
        return f"{cid}-unified" if unified else cid
    return f"{path}-{PATH_WEIGHT[path]}-auto-{mtp}-c{n}-ctx{ctx}"


def is_priority(path: str, mtp: str, n: int, ctx: int) -> bool:
    if path == "gguf" and ctx == 131072:
        return True  # {base,mtp} x {1,4,8,16} @131072
    if path == "gguf" and mtp == "base" and ctx in (32768, 262144) and n in (1, 4):
        return True  # base x {32768,262144} @N=1,4
    if path == "vllm" and ctx == 262144:
        return True  # {base,mtp} x {1,4,8,16} @262144
    return False


def legacy_to_new(cid: str) -> str:
    """The 2026-08-18 id migration map: legacy unprefixed gguf ids ARE hip.
    Identity for ids that already carry their backend tag (and for vllm)."""
    if cid.startswith("gguf-udq4kxl-auto-"):
        return "gguf-hip-" + cid[len("gguf-"):]
    return cid


def build_cells() -> list[dict]:
    cells: list[dict] = []
    # gguf path: the 2026-08-17 product, now explicit -hip- (24 cells) ...
    for mtp in MTP_MODES:
        for ctx in (32768, 131072, 262144):
            for n in CONCURRENCIES:
                priority = is_priority("gguf", mtp, n, ctx)
                cells.append({
                    "id": cell_id("gguf", mtp, n, ctx),
                    "status": "planned",
                    "reason": PLANNED_REASON_PRIORITY if priority else PLANNED_REASON_REST,
                    "runner_hint": RUNNER_HINT["gguf"],
                    "priority": priority,
                })
    # ... + the 8 new v0.1.2 cells (backend dimension: vulkan; mtp4 depth;
    # unified-default-boot c4 rider).
    for backend, mtp, n, ctx, unified in NEW_CELLS_V012:
        cells.append({
            "id": cell_id("gguf", mtp, n, ctx, backend=backend, unified=unified),
            "status": "planned",
            "reason": PLANNED_REASON_V012,
            "runner_hint": RUNNER_HINT["gguf"],
            "priority": True,
        })
    # vllm path (unchanged grammar and product).
    for mtp in MTP_MODES:
        for ctx in (32768, 131072, 262144):
            for n in CONCURRENCIES:
                if ("vllm", ctx) in UNSUPPORTED_TIERS:
                    cells.append({
                        "id": cell_id("vllm", mtp, n, ctx),
                        "status": "dropped",
                        "reason": DROPPED_REASONS[("vllm", ctx)],
                        "runner_hint": "none (dropped tier)",
                        "priority": False,
                    })
                    continue
                if ("vllm", ctx) not in {(p, c) for p in PATH_CTX for c in PATH_CTX[p]}:
                    continue  # not offered and not a recorded drop; unreachable by construction
                priority = is_priority("vllm", mtp, n, ctx)
                cells.append({
                    "id": cell_id("vllm", mtp, n, ctx),
                    "status": "planned",
                    "reason": PLANNED_REASON_PRIORITY if priority else PLANNED_REASON_REST,
                    "runner_hint": RUNNER_HINT["vllm"],
                    "priority": priority,
                })
    # ... + the 2 new v0.1.9 dflash cells (spec-variant dimension: the
    # DFlash2 block-diffusion draft, vllm path only — the gguf path has no
    # dflash support by construction, llama.cpp cannot run the drafter).
    for path, mtp, n, ctx in NEW_CELLS_V019:
        cells.append({
            "id": cell_id(path, mtp, n, ctx),
            "status": "planned",
            "reason": PLANNED_REASON_V019,
            "runner_hint": RUNNER_HINT[path],
            "priority": True,
        })
    return cells


def build_matrix() -> dict:
    cells = build_cells()
    ids = [c["id"] for c in cells]
    assert len(ids) == len(set(ids)), "duplicate cell ids"
    return {
        "generated_at": GENERATED_AT,
        "generator": "scripts/gen-matrix.py",
        "notes": [
            "Declaration only: statuses flip to measured by the cell runners (Tasks 3/4); "
            "regeneration resets to this declaration.",
            "Weight is path-bound by construction (gguf<->udq4kxl, vllm<->bf16); cross "
            "pairs are invalid and never emitted (METHODOLOGY.md §8).",
            "Dropped cells record the unsupported-tier exclusions per spec 4.3.",
            "Backend dimension (2026-08-18, v0.1.2): gguf ids carry an explicit "
            "-hip-|-vulkan- tag; legacy unprefixed gguf ids are hip. The 8 new "
            "Vulkan×MTP cells are declared planned pre-measurement.",
            "Measured-state carry-over (2026-08-18): regeneration transfers committed "
            "measured cells (status/degraded/note) onto the declared ids via the "
            "LEGACY->NEW mapping; it refuses only if a measured cell would leave the "
            "declaration (--force re-emits the bare declaration).",
        ],
        "cells": cells,
    }


def render_matrix(matrix: dict) -> str:
    return json.dumps(matrix, indent=2) + "\n"


def committed_matrix(out_path: Path | None = None) -> dict:
    out_path = OUT if out_path is None else out_path  # read at call time
    if not out_path.exists():
        return {}
    try:
        return json.loads(out_path.read_text())
    except json.JSONDecodeError:
        return {}  # unreadable committed file: --check is the honest reporter


def carry_over_measured(cells: list[dict], committed: dict) -> list[str]:
    """Transfer committed measurement state onto the declared ids, in place.

    Applies exactly the state transitions the cell runners perform (status
    measured, reason dropped, degraded/note added), keyed by the LEGACY->NEW
    mapping so the 2026-08-18 backend-tag migration carried the 20 measured
    cells (and their 5 degraded notes) across intact. Returns the committed
    measured ids that found NO declared target (lost evidence) — those are
    the guard's refusal set.
    """
    declared = {c["id"] for c in cells}
    by_new_id: dict[str, dict] = {}
    for c in committed.get("cells", []):
        if c.get("status") == "measured":
            by_new_id[legacy_to_new(c["id"])] = c
    lost = [c["id"] for c in committed.get("cells", [])
            if c.get("status") == "measured"
            and legacy_to_new(c["id"]) not in declared]
    for cell in cells:
        src = by_new_id.get(cell["id"])
        if src is None:
            continue
        cell["status"] = "measured"
        cell.pop("reason", None)
        if src.get("degraded"):
            cell["degraded"] = True
            cell["note"] = src.get("note")
    return lost


def summary(cells: list[dict]) -> str:
    n_prio = sum(1 for c in cells if c["priority"])
    counts: dict[str, int] = {}
    for c in cells:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return (f"{len(cells)} cells ({counts.get('measured', 0)} measured, "
            f"{counts.get('planned', 0)} planned, "
            f"{counts.get('dropped', 0)} dropped), {n_prio} priority")


def rel(path: Path) -> str:
    """Repo-relative display path (full path when outside the repo, e.g. a
    test sandbox redirecting OUT)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    force = "--force" in args
    check = "--check" in args
    matrix = build_matrix()
    committed = committed_matrix()
    lost: list[str] = []
    if not force:
        lost = carry_over_measured(matrix["cells"], committed)
    text = render_matrix(matrix)

    if check:
        committed_text = OUT.read_text() if OUT.exists() else ""
        if committed_text != text:
            print(f"STALE: {rel(OUT)} differs from a fresh declaration "
                  f"(regeneration would NOT be a no-op).", file=sys.stderr)
            print("Note: measured cells are carried over by a plain rerun; a "
                  "lost measured cell makes the rerun refuse — re-run with "
                  "--force only if resetting the measurement manifest is "
                  "intended.", file=sys.stderr)
            return 1
        print(f"fresh: {rel(OUT)} is byte-identical to a fresh declaration "
              f"({summary(matrix['cells'])})")
        return 0

    if lost and not force:
        print(f"REFUSING to write {rel(OUT)}: regeneration would drop "
              f"{len(lost)} committed 'measured' cell(s) that are not in "
              f"the declaration:", file=sys.stderr)
        for cid in lost:
            print(f"  would lose: {cid}", file=sys.stderr)
        print("Re-emit deliberately with --force (the dropped measurements "
              "must then be re-run and re-flipped by the cell runners), or "
              "compare only with --check.", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    n_committed_measured = sum(
        1 for c in committed.get("cells", []) if c.get("status") == "measured")
    print(f"wrote {rel(OUT)}: {summary(matrix['cells'])}"
          + (f" (--force: {n_committed_measured} committed measured cell(s) "
             f"reset to the declaration)" if force and n_committed_measured else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
