#!/usr/bin/env python3
"""Generate the declared benchmark matrix: docs/results/matrix-714/matrix.json.

Deterministic by construction: fixed iteration order, no timestamps inside
cells, `generated_at` is a constant date. Re-running reproduces the same
bytes (until the constants below change). This emits the DECLARATION (all
valid cells `planned`, unsupported tiers `dropped`); Tasks 3/4 flip statuses
to `measured` as cells run — regenerating resets those statuses back to the
declaration. That reset is a CLOBBER of the measurement manifest, so since
the 2026-08-17 final-review guard a plain run REFUSES to write while any
committed cell is `measured`:

    python3 scripts/gen-matrix.py            # guarded: refuses if measured cells
                                             # would be reset (names them)
    python3 scripts/gen-matrix.py --check    # exit 0 iff regeneration is a
                                             # no-op vs the committed file
    python3 scripts/gen-matrix.py --force    # re-emit the declaration anyway

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
import sys
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


def build_matrix() -> dict:
    cells = build_cells()
    ids = [c["id"] for c in cells]
    assert len(ids) == len(set(ids)), "duplicate cell ids"
    return {
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


def render_matrix(matrix: dict) -> str:
    return json.dumps(matrix, indent=2) + "\n"


def committed_measured_cells(out_path: Path | None = None) -> list[str]:
    """Ids of cells recorded 'measured' in the committed matrix, if any."""
    out_path = OUT if out_path is None else out_path  # read at call time
    if not out_path.exists():
        return []
    try:
        committed = json.loads(out_path.read_text())
    except json.JSONDecodeError:
        return []  # unreadable committed file: --check is the honest reporter
    return [c["id"] for c in committed.get("cells", [])
            if c.get("status") == "measured"]


def summary(cells: list[dict]) -> str:
    n_prio = sum(1 for c in cells if c["priority"])
    counts: dict[str, int] = {}
    for c in cells:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return (f"{len(cells)} cells ({counts.get('planned', 0)} planned, "
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
    text = render_matrix(matrix)

    if check:
        committed = OUT.read_text() if OUT.exists() else ""
        if committed != text:
            print(f"STALE: {rel(OUT)} differs from a fresh declaration "
                  f"(regeneration would NOT be a no-op).", file=sys.stderr)
            print("Note: a plain rerun refuses while measured cells exist — "
                  "re-run with --force only if resetting the measurement "
                  "manifest is intended.", file=sys.stderr)
            return 1
        print(f"fresh: {rel(OUT)} is byte-identical to a fresh declaration "
              f"({summary(matrix['cells'])})")
        return 0

    measured = committed_measured_cells()
    if measured and not force:
        print(f"REFUSING to write {rel(OUT)}: regeneration would reset "
              f"{len(measured)} committed 'measured' cell(s) back to the "
              f"declaration:", file=sys.stderr)
        for cid in measured:
            print(f"  would reset: {cid}", file=sys.stderr)
        print("Re-emit deliberately with --force (statuses must then be "
              "re-flipped by the cell runners), or compare only with "
              "--check.", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {rel(OUT)}: {summary(matrix['cells'])}"
          + (" (--force: measurement manifest reset to the declaration)"
             if measured else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
