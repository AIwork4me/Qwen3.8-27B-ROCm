# Community hardware-validation protocol

This project is validated on one reference host: AMD Ryzen AI MAX+ PRO 395 /
Radeon 8060S (`gfx1151`, ROCm 7.14.0, 80 GiB unified GTT pool —
`configs/validated-stack.json`). This document is the contract for anyone
who wants their platform listed too — the first target being the AMD Radeon
PRO W7900 (`gfx1100`, 48 GiB discrete GDDR6), currently shown as 🚧
Planned in the README hardware-support matrix.

Community status is **evidence attached to this repository**, not a project
validation. It lands in a separate namespace (`configs/community/`,
`docs/results/matrix-714/community/`) and a generated 🧪 row in the README
matrix. It never changes project verdicts, quickstart defaults, or any
claim made about the reference host.

## Why a protocol (and not "it works on my machine")

Benchmark numbers are only comparable when the harness is identical. This
repository's cells are produced by its own runners (`scripts/run-cell-gguf.sh`,
`scripts/run-cell-vllm.sh`) driving `scripts/bench_client.py` under the rules
frozen in `docs/results/METHODOLOGY.md`. Numbers from other harnesses
(llama-bench, vLLM's benchmark_serving, vendor tools) are welcome as
**context** in your issue, but they are **not evidence** for this index —
the shape of the measurement (prompt set, stream count, healthy-stream
filtering, anchors) is the point.

Two facts shape the protocol for discrete-VRAM boards such as the W7900:

- **Memory model differs.** gfx1151 exposes a ~80 GiB unified GTT pool
  (system RAM visible to the GPU); a W7900 has 48 GiB discrete GDDR6 and no
  GTT pool. Capacity conclusions do not transfer: BF16 vLLM serving needs
  ~51.7 GiB of weights alone and will not fit 48 GiB — the GGUF
  (UD-Q4_K_XL) path is the realistic one on such boards, and
  per-path `validated` flags exist for exactly this reason.
- **There is no project-prescribed stack for gfx1100.** The AMD TheRock
  nightly index used on the reference host has no gfx1100 builds
  (404, verified 2026-08-17). Submitters therefore bring their own
  PyTorch/vLLM sources and MUST document them in the stack manifest below.
  The protocol prescribes the evidence format, not the stack.

## What a submission MUST include

Open the **Hardware validation** issue
(`.github/ISSUE_TEMPLATE/hardware-validation.yml`) and fill every field,
then open one pull request per platform containing:

1. **Filled issue template** — the issue (or the PR body referencing it) is
   the human-readable submission.
2. **Community env-check receipt** — output of

   ```bash
   bash scripts/00-check-env.sh --profile community | tee env-check.txt
   ```

   saved as `docs/results/matrix-714/community/<platform-id>/env-check.txt`.
   The community profile accepts any AMD gfx arch with ROCm present (host
   tools and the kernel floor are still enforced) and prints the
   `COMMUNITY-PROFILE: arch=<gfxNNNN> pool=<…>GiB NOT project-validated`
   line that anchors the receipt to this protocol.
3. **rocm-smi receipts** — `rocm-smi` output captured at idle and under
   load (e.g. right after model load, during a cell), saved under the same
   directory. On discrete-VRAM boards this is the authoritative memory
   evidence (the reference host's GTT-pool reading does not apply).
4. **Exact commands** — every command used to build and serve, verbatim
   (env exports, configure/build lines, server invocations). If they differ
   from the repo scripts, say where and why.
5. **Raw cells from this repo's runners** — cells produced by
   `scripts/run-cell-gguf.sh` / `scripts/run-cell-vllm.sh` +
   `scripts/bench_client.py` (the cell JSONs they write), committed under
   `docs/results/matrix-714/community/<platform-id>/cells/`. Keep the JSONs
   exactly as written by the runners — do not post-edit them.
6. **Stack manifest** — a short `stack-manifest.md` next to the receipts
   describing where PyTorch and vLLM came from (index URL, wheel tag,
   source repo + commit, local patches), the llama.cpp commit, the ROCm
   version, and the kernel. gfx1100 has no TheRock index — your own
   sources, documented, are expected.
7. **Index entry** — one object appended to
   `configs/community/platforms.json` validating against
   `schemas/community-platform.schema.json` (the test suite enforces it),
   e.g.:

   ```json
   {
     "id": "w7900-gfx1100-rocm714",
     "submitter": "colleague",
     "submitted": "2026-09-01",
     "gpu": {"arch": "gfx1100", "marketing_name": "Radeon PRO W7900", "vram_gib": 48},
     "stack": {"rocm": "7.14.0", "kernel": "6.17.0",
               "pytorch_source": "official rocm wheel 2.9",
               "vllm_source": "upstream main @<sha>",
               "llama_cpp_commit": "<40-hex>"},
     "validated": {"gguf": true, "vllm": false},
     "receipts": {
       "env_check": "docs/results/matrix-714/community/w7900-gfx1100-rocm714/env-check.txt",
       "cells": ["docs/results/matrix-714/community/w7900-gfx1100-rocm714/"]
     }
   }
   ```

   Set `validated.gguf` / `validated.vllm` only for paths whose cells are
   healthy in your receipts (boots + clean anchors). Then regenerate the
   README matrix (`python3 scripts/render-hardware-matrix.py`, or
   `scripts/render-readme-blocks.py` for all blocks) and commit the result.

**One PR per platform.** Mixed-platform PRs are hard to review against the
schema and the receipts tree.

Suggested receipts layout:

```
docs/results/matrix-714/community/<platform-id>/
├── env-check.txt          # --profile community output
├── rocm-smi-idle.txt
├── rocm-smi-loaded.txt
├── stack-manifest.md
└── cells/                 # raw runner-written cell JSONs
```

## Producing your cells

Run the same runners the project uses, with `CELLS_DIR` pointed at your
community namespace:

```bash
CELLS_DIR=docs/results/matrix-714/community/<platform-id>/cells \
  bash scripts/run-cell-gguf.sh gguf-udq4kxl-auto-base-c4-ctx131072

CELLS_DIR=docs/results/matrix-714/community/<platform-id>/cells \
  bash scripts/run-cell-vllm.sh vllm-bf16-auto-base-c1-ctx262144
```

With any `CELLS_DIR` other than the project default
(`docs/results/matrix-714/cells`), the runners **do not touch the project
matrix** — no status flip, no notes: they only resolve your cell ids against
it (read-only) and write each cell JSON into your `CELLS_DIR`, right next to
your `rocm-smi` receipts. A `MATRIX_FILE` override exists for the same
reason, but you should not need it.

Never edit `docs/results/matrix-714/matrix.json` or
`configs/benchmark-verdicts.json` — community evidence enters this
repository only through `configs/community/platforms.json`.

## Review criteria (maintainer)

A submission is accepted when the maintainer can, from the PR alone:

- **Reproduce the shape**: rerun `00-check-env.sh --profile community`
  semantics against the `env-check.txt` content (same arch/pool lines),
  confirm the commands plausibly produce the committed cells, and confirm
  the receipts tree matches the layout above.
- **Spot-check the receipts**: open at least one cell JSON — anchor result,
  healthy-stream filtering, stream counts, and memory snapshots must be
  internally consistent; rocm-smi numbers must be consistent with the
  claimed `vram_gib`.
- **Check the schema**: `uv run --no-sync pytest tests/test_community_protocol.py`
  passes (index validates, entry fields complete), and the README matrix
  regenerated byte-identically.

Anything the maintainer cannot check (they do not own your GPU) is taken on
the strength of the receipts' internal consistency — which is why
post-edited or foreign-harness numbers are rejected.

## What community status does NOT grant

- **No project verdicts.** `configs/benchmark-verdicts.json`, the verdict
  tables, and every ✅/⚠️/❌ in the README concern the reference host only.
- **No quickstart changes.** `scripts/gguf-quickstart.sh` defaults and the
  serving configs stay exactly as validated on gfx1151.
- **No project claims.** A 🧪 row says "a submitter produced these receipts
  with this stack" — nothing more. It is not an endorsement, not a support
  commitment, and not a statement that the platform will work for you.

If a community platform later becomes a maintained reference, that happens
through a project decision with project-owned receipts — never by
relabeling the row.
