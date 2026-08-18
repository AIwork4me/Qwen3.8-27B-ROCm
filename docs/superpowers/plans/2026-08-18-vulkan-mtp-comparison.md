# Vulkan Backend × MTP Depth Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer "AMD says 24.5 tok/s (Vulkan, MTP=4) — we measure 13.0 (HIP, MTP=1): what does each factor contribute?" with measured cells on the same host, model, prompts, and harness — plus close the unified-default c4@131072 bracketing gap as a rider.

**Architecture:** Add a `backend` dimension (hip|vulkan) to the existing GGUF matrix machinery — schema, cell-id pattern, generator, runner, verdicts, README blocks — then measure a priority subset: Vulkan {base, mtp(num_spec=1), mtp4} × c{1,4} @131072 (6 cells) + HIP mtp4 c1 (depth comparison on the incumbent backend, 1 cell) + HIP unified-default c4@131072 (1 rider cell). Same pin (llama.cpp `4df29be4`), same UD-Q4_K_XL + mmproj-F16, same bench_client/prompt set; greedy-degradation anchor checked on every cell (does the pit reproduce on Vulkan?). Recommendation impact is evidence-gated: if Vulkan wins clearly, quickstart gains an opt-in; defaults flip only via a recorded controller ruling.

**Tech Stack:** bash, cmake + Vulkan loader/RADV (Mesa), llama.cpp @4df29be4 `-DGGML_VULKAN=ON`, existing pytest/JSON-schema/generator machinery.

**Spec:** `docs/superpowers/specs/2026-08-16-qwen3.8-27b-rocm-design.md` (§4.3 matrix, §4.4 verdicts); roadmap bullet in README "Status & roadmap".
**Local handoff (ops context, proxy/network facts):** `.superpowers/sdd/release-ops/HANDOFF.md`.

## Global Constraints

- Same llama.cpp commit `4df29be4f4c3f428170fda944a5b19f743bb8` for the Vulkan build (separate build dir `build-714-vk`; HIP build-714 untouched).
- Cell-id grammar extension: `^(gguf|vllm)-(udq4kxl|bf16)-auto-(base|mtp|mtp4)-c(1|4|8|16)-ctx(32768|131072|262144)$` PLUS a backend tag for gguf cells only: new full form `gguf-<backend>-udq4kxl-auto-(base|mtp|mtp4)-cN-ctxK` with backend ∈ {hip, vulkan}; existing ids are implicitly hip (migration: generator emits `hip` explicitly for all gguf cells; verdicts/README renderer updated in lockstep; tests updated to the new grammar). vLLM cells unchanged.
- Vulkan runtime prerequisites to verify before building: `vulkaninfo` present (Mesa RADV — package `mesa-vulkan-drivers` + `vulkan-tools`; SDK headers via `libvulkan-dev`, shaderc via `libshaderc-dev` or llama.cpp bundled); if the loader sees the AMD proprietary driver instead of RADV, record which ICD is active in the cell receipts (`VK_ICD_FILENAMES` if forced) — backend identity is part of the evidence.
- MTP depth: `num_speculative_tokens` 1 (existing `mtp`) and 4 (`mtp4`) — verify at the pin that llama.cpp accepts the depth (server `--spec-type draft-mtp` + depth flag; discover exact mechanism in `common/arg.cpp`/speculative code, record in receipt; llama.cpp MTP depth may be fixed by `mtp_num_hidden_layers` — if depth=4 is NOT configurable at this pin, record that as the finding and measure what IS configurable; do not fake a variant).
- Greedy anchor on EVERY new cell (bench → anchor, gate on `anchor_ok`) — the pit's backend-dependence (gfx1100-clean, gfx1151-HIP-broken, Vulkan unknown) is a headline question of this experiment.
- Rider cell `gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified`: unified-default-boot 4-slot semantics (NO `-np` flag — the stock quickstart default), recorded with slot_info as usual; id suffix `-unified` distinguishes it from the existing split-mode c4 cell (grammar: optional `-unified` suffix allowed only on c4 gguf cells).
- Verdicts: new cells enter `benchmark-verdicts.json` under the SAME rules (10 tok/s interactive floor; pit → avoid; MTP regression vs base-counterpart at same c). Recommendation changes (quickstart default or new opt-in) require: measured cells + controller ruling recorded in verdicts `reviewed_by` + anti-pit test updated in the same commit.
- CI CPU-safe; suite baseline 142 passed, 2 deselected; both freshness gates green at every commit; branch `feature/vulkan-mtp` off main (@6f6194e); cadence: implement → INDEPENDENT verifier → next task (user-mandated).
- All numbers binary units; receipts verbatim; network via proxy `http://127.0.0.1:7897` if GitHub is needed.

---

### Task 1: Backend dimension — schema, generator, migration

**Files:**
- Modify: `schemas/benchmark-verdicts.schema.json` (id pattern + mtp4 + unified suffix)
- Modify: `scripts/gen-matrix.py` (backend dim for gguf cells; emit hip explicitly; declare new priority cells as planned)
- Modify: `scripts/gen-verdicts.py` + `scripts/render-readme-blocks.py` (backend-aware ids, tables gain a Backend column where rows mix backends)
- Modify: `docs/results/METHODOLOGY.md` (dated addendum §1/§8: backend dimension declared pre-measurement; AMD anchor context quoted from spike/vllm.md)
- Test: `tests/test_bench_schema.py`, `tests/test_verdicts.py` (grammar/migration cases)

**Interfaces:**
- Produces: cell-id grammar `^(gguf)-(hip|vulkan)-udq4kxl-auto-(base|mtp|mtp4)-c(1|4|8|16)-ctx(32768|131072|262144)(-unified)?$` for gguf (vllm pattern unchanged); `gen-matrix.py` output with 8 new planned cells: vulkan×{base,mtp,mtp4}×c{1,4}@131072 (6) + hip-mtp4-c1@131072 (1) + hip-base-c4@131072-unified (1); migrated existing ids (all gguf cells get `-hip-`) — matrix.json, verdicts JSON, README blocks, benchmark.md, and the 20 existing cell FILES renamed via `git mv` in the same commit (filename == id invariant preserved).

- [ ] **Step 1 — failing tests**: grammar accepts `gguf-vulkan-udq4kxl-auto-mtp4-c4-ctx131072` and `gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified`, rejects `vllm-vulkan-...`, `gguf-hip-...-c3-...`, `...-unified` on non-c4; migration test: after regeneration, verdicts contain zero legacy ids and exactly 28 cells (20 measured migrated + 8 planned); README blocks render a Backend column (or per-row backend tag) with zero legacy ids.
- [ ] **Step 2 — verify FAIL**; **Step 3 — implement** (schema regex; generator cross-product; `git mv docs/results/matrix-714/cells/gguf-udq4kxl-*.json` → hip names; gen-verdicts id mapping 1:1 legacy→hip so verdict CONTENT is unchanged except id — add a test asserting verdict reasons/metrics byte-stable modulo id; METHODOLOGY dated addendum); **Step 4 — suite + gates + `git status` clean (no stray old files)**; **Step 5 — commit** `feat(matrix): backend dimension (hip|vulkan), mtp4, unified suffix — id migration`.

### Task 2: Vulkan build + runner backend plumbing

**Files:**
- Create: `scripts/06-build-llama-vulkan.sh` (adapt 05-build-llama.sh: `-DGGML_VULKAN=ON`, `-DGGML_HIP=OFF`, build dir `build-714-vk`, same commit pin + fingerprint via llama_build.sh helpers extended with a backend field or separate `write_llama_build_fingerprint` call recording `"backend": "vulkan"`; prereq checks for vulkaninfo/libvulkan-dev with actionable apt hints)
- Modify: `scripts/run-cell-gguf.sh` (`BACKEND=${BACKEND:-hip}` env → binary from build-714|build-714-vk; `SPEC_DEPTH` env → mtp4 cells pass the discovered depth mechanism; unified rider: `SLOTS=unified` env skips `-np`, forces default unified boot, id suffix `-unified`)
- Modify: `scripts/gguf-quickstart.sh` — NO default change; add opt-in `BACKEND=vulkan` pass-through (binary selection + a one-line receipt note) behind an "experimental, see verdicts" comment
- Test: `tests/test_llama_build.py` (vk script contract), `tests/test_cell_runner.py` (backend/depth/unified plumbing, id derivation), `tests/test_gguf_quickstart_ux.py` (opt-in only, default unchanged)

- [ ] Steps: failing tests → implement → host build (nohup, ~5-10 min; verify `build-714-vk/bin/llama-server --version` and `--list-devices` shows the Vulkan device + ICD identity recorded) → MTP-depth discovery at pin recorded in `configs/validated-stack.json["llama_cpp_vulkan"]` + receipt note → suite/gates → commit `feat: Vulkan build path + backend/depth/unified runner plumbing`.

### Task 3: Host execution — 8 cells

**Files:**
- Create: `docs/results/matrix-714/cells/` 8 new cell JSONs; matrix.json statuses → measured
- Test: existing consistency tests (auto-cover); no new tests

- [ ] Steps: run the 8 cells (vulkan base/mtp/mtp4 × c1/c4; hip mtp4 c1; hip c4 unified) — each with rocm-smi/GTT snapshot, bench, anchor; failures = findings, still committed; verify anchor on every cell (Vulkan pit question); GPU clean at end; suite/gates; commit `feat: Vulkan×MTP-depth cells + unified c4 rider (raw receipts)`.

### Task 4: Verdicts + README regeneration + recommendation ruling

**Files:**
- Modify: `scripts/gen-verdicts.py` (new cells verdicted under frozen rules; any controller ruling recorded per cell)
- Modify: README blocks (regenerated), `docs/results/benchmark.md` (regenerated), `docs/adaptation.md` (Vulkan section: build facts, ICD identity, perf deltas, pit status)
- Modify: `CHANGELOG.md` (+ v0.1.2 section), `CITATION.cff` (version bump, consistency test enforces)
- Test: `tests/test_verdicts.py` (new cells have verdicts; recommendation-mapping test extended to whatever the ruling decides)

- [ ] Steps: verdict generation + controller review of each reason; ruling on quickstart (likely outcomes: (a) Vulkan wins ≥15% over HIP mtp-c1 AND anchor-clean → `BACKEND=vulkan` promoted in quickstart echo as recommended opt-in, default stays hip unless >25% + stable, ruling recorded; (b) Vulkan loses/broken → roadmap bullet answered, no config change; (c) depth=4 not configurable → document, mtp4 cells become mtp-depth=N reality); README/adaptation/CHANGELOG regen — **CHANGELOG v0.1.2 must carry a one-line id-migration note ("legacy gguf ids without a backend tag are `hip`")** so the historical v0.1.0/v0.1.1 entries stay interpretable; suite/gates; commit `feat: Vulkan×MTP verdicts + recommendation ruling (v0.1.2)`.

### Task 5 (gate): Independent verification + release

- Final whole-branch independent verifier (per cadence): cells traceable, verdicts honest, ruling justified by numbers, migration lost nothing (old ids nowhere), gates green; then merge to main, tag `v0.1.2`, push, GitHub Release notes, CI watch.

## Verification (whole plan)

```bash
uv run --no-sync pytest -v                       # green, ~150 passed
python3 scripts/render-readme-blocks.py --check && python3 scripts/gen-verdicts.py --check
git log --oneline main..HEAD                     # ≥ 4 commits
grep -rE "gguf-udq4kxl" docs/ README.md configs/ | wc -l   # 0 legacy ids anywhere
pgrep -f llama-server || echo clean
```
