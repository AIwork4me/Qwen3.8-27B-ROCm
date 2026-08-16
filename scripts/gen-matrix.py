#!/usr/bin/env python3
"""Generate the declared benchmark matrix: docs/results/matrix-714/matrix.json.

Deterministic by construction: fixed iteration order, no timestamps inside
cells, `generated_at` is a constant date. Re-running reproduces the same
bytes (until the constants below change). This emits the DECLARATION (all
valid cells `planned`, unsupported tiers `dropped`); Tasks 3/4 flip statuses
to `measured` as cells run — regenerating resets to the declaration, which
is the intended semantics of a declaration generator.

Cell id grammar (shared with schemas/benchmark-verdicts.schema.json and the
cell runners — keep the literal in sync):
    {path}-{weight}-auto-{mtp}-c{N}-ctx{K}

Rules encoded here (see docs/results/METHODOLOGY.md §8):
- weight is path-bound by construction: gguf<->udq4kxl, vllm<->bf16.
  Cross pairs are invalid and never emitted.
- vllm ctx tier 32768 is not a supported conf tier -> emitted as dropped
  with reason (spec 4.3: every dropped cell is recorded with reason).
- declared-priority subset for this session:
  gguf {base,mtp} x {1,4,8,16} @131072 + base x {32768,262144} @N=1,4;
  vllm {base,mtp} x {1,4,8,16} @262144.
  Everything else valid: planned(reason="time-boxed session; machinery
  complete").
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "results" / "matrix-714" / "matrix.json"

GENERATED_AT = "2026-08-17"  # declaration date; a date, never a timestamp

# path -> bound weight (invalid cross pairs are never constructed)
PATH_WEIGHT = {"gguf": "udq4kxl", "vllm": "bf16"}
# path -> offered ctx tiers
PATH_CTX = {
    "gguf": (32768, 131072, 262144),
    "vllm": (131072, 262144),
}
UNSUPPORTED_TIERS = {("vllm", 32768)}  # recorded as dropped, with reason

CONCURRENCIES = (1, 4, 8, 16)
MTP_MODES = ("base", "mtp")

RUNNER_HINT = {"gguf": "scripts/run-cell-gguf.sh", "vllm": "scripts/run-cell-vllm.sh"}

PLANNED_REASON_PRIORITY = "declared priority subset for this session (see METHODOLOGY.md §8)"
PLANNED_REASON_REST = "time-boxed session; machinery complete"
DROPPED_REASONS = {
    ("vllm", 32768): (
        "32768 is not a supported conf tier for the vllm path "
        "(validated conf serves --max-model-len 262144; no tier below it is offered)"
    ),
}


def cell_id(path: str, mtp: str, n: int, ctx: int) -> str:
    return f"{path}-{PATH_WEIGHT[path]}-auto-{mtp}-c{n}-ctx{ctx}"


def is_priority(path: str, mtp: str, n: int, ctx: int) -> bool:
    if path == "gguf" and ctx == 131072:
        return True  # {base,mtp} x {1,4,8,16} @131072
    if path == "gguf" and mtp == "base" and ctx in (32768, 262144) and n in (1, 4):
        return True  # base x {32768,262144} @N=1,4
    if path == "vllm" and ctx == 262144:
        return True  # {base,mtp} x {1,4,8,16} @262144
    return False


def build_cells() -> list[dict]:
    cells: list[dict] = []
    for path in ("gguf", "vllm"):
        for mtp in MTP_MODES:
            for ctx in (32768, 131072, 262144):
                for n in CONCURRENCIES:
                    if (path, ctx) in UNSUPPORTED_TIERS:
                        cells.append({
                            "id": cell_id(path, mtp, n, ctx),
                            "status": "dropped",
                            "reason": DROPPED_REASONS[(path, ctx)],
                            "runner_hint": "none (dropped tier)",
                            "priority": False,
                        })
                        continue
                    if (path, ctx) not in {(p, c) for p in PATH_CTX for c in PATH_CTX[p]}:
                        continue  # not offered and not a recorded drop; unreachable by construction
                    priority = is_priority(path, mtp, n, ctx)
                    cells.append({
                        "id": cell_id(path, mtp, n, ctx),
                        "status": "planned",
                        "reason": PLANNED_REASON_PRIORITY if priority else PLANNED_REASON_REST,
                        "runner_hint": RUNNER_HINT[path],
                        "priority": priority,
                    })
    return cells


def main() -> None:
    cells = build_cells()
    ids = [c["id"] for c in cells]
    assert len(ids) == len(set(ids)), "duplicate cell ids"

    matrix = {
        "generated_at": GENERATED_AT,
        "generator": "scripts/gen-matrix.py",
        "notes": [
            "Declaration only: statuses flip to measured by the cell runners (Tasks 3/4); "
            "regenerating resets to this declaration.",
            "Weight is path-bound by construction (gguf<->udq4kxl, vllm<->bf16); cross "
            "pairs are invalid and never emitted (METHODOLOGY.md §8).",
            "Dropped cells record the unsupported-tier exclusions per spec 4.3.",
        ],
        "cells": cells,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(matrix, indent=2) + "\n")

    n_prio = sum(1 for c in cells if c["priority"])
    counts: dict[str, int] = {}
    for c in cells:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(cells)} cells "
          f"({counts.get('planned', 0)} planned, {counts.get('dropped', 0)} dropped), "
          f"{n_prio} priority")


if __name__ == "__main__":
    main()
