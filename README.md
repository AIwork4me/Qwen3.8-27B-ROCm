# Qwen3.8-27B-ROCm

> Work in progress. Goal: the reproducible RDNA reference for
> [Qwen/Qwen3.8-27B](https://modelscope.cn/models/Qwen/Qwen3.8-27B) on
> AMD ROCm 7.14.0 — method: Adapt → Validate → Benchmark → Explain →
> Reproduce.
>
> Status: both serving paths (vLLM and llama.cpp/GGUF) validated on the
> reference host (see the table).
> Validated platform: AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S (`gfx1151`).
> W7900D (`gfx1100`) is community-validated (GGUF path, per the hardware matrix below); more platforms are evidence-gated.

Design spec: `docs/superpowers/specs/2026-08-16-qwen3.8-27b-rocm-design.md`

## Documentation

- [Getting started](docs/getting-started.md) — prerequisites, disk budget, both serving paths with the exact validated commands
- [Troubleshooting](docs/troubleshooting.md) — every measured pit in the standard symptom → repro → diagnosis → workaround → upstream format
- [Adaptation map](docs/adaptation.md) — MI-series/Day-0 → RDNA gfx1151 deltas, classified by durability
- [Results index](docs/results/README.md) — one line per validation track (spike, receipts, matrix, method)
- [Hardware validation protocol](docs/hardware-validation.md) — adding other AMD GPUs as community evidence

## Quick start (interactive chat: the GGUF path)

The benchmark matrix (20 measured cells; verdicts in
`configs/benchmark-verdicts.json`) puts interactive chat on the GGUF path —
every measured vLLM cell runs below the 10 tok/s interactive floor on this
host (controller ruling 2026-08-17; see [Performance](#performance)):

```bash
bash scripts/gguf-quickstart.sh              # UD-Q4_K_XL, ctx 131072 — 10.1 tok/s per stream
WITH_MTP=1 bash scripts/gguf-quickstart.sh   # +28% per-stream: 13.0 tok/s per stream
```

Point any OpenAI-compatible client at `http://127.0.0.1:8080/v1`. For
262144-token context, vision, or aggregate batch throughput (to 38.6 tok/s),
serve vLLM instead (`scripts/03-serve-vllm.sh`, port 8000) — it is the
greedy-degradation-free path but not interactive on this host. The measured
greedy-degradation pit hits the c8/c16 split-mode loads (`-np 8`/`-np 16` at
ctx 131072) **and** c4 on the unified default boot at ctx 32768
(`gguf-udq4kxl-auto-base-c4-ctx32768`); see
[Known good / known bad](#known-good--known-bad). Caveat: unified-default-boot
c4 at ctx 131072 (the stock quickstart's 4-slot default under 4 concurrent
users) was **not measured** — bracketed by the c4@32768 pit and the clean
split-mode c4@131072 cell; single-stream use is unaffected.

## Serving paths

| Path | Status (`gfx1151`, ROCm 7.14) | Evidence |
| --- | --- | --- |
| vLLM (source build @ `4d2a68d`, BF16) | Validated — text, MTP speculative decoding, 262144 context, and single-small-image vision; encoder-peak memory for larger image workloads is unbudgeted under `--skip-mm-profiling` | `docs/results/rocm-7.14/vllm-validation.md` |
| llama.cpp / GGUF (HIP build @ `4df29be`, UD-Q4_K_XL) | Validated — text (greedy smoke at ctx 131072), MTP via `--spec-type draft-mtp`, and single-small-image vision via mmproj-F16; `CTX_SIZE=262144` boots but total GTT grows to 33.9 GiB (weights + KV; the 262144 KV increment is 8.0 GiB over the 131072 boot), so the validated default stays 131072 | `docs/results/rocm-7.14/gguf-validation.md` |

## Hardware support

<!-- BEGIN GENERATED: hardware-matrix -->
| Platform | GPU arch | Memory model | Stack | Status | Evidence |
|---|---|---|---|---|---|
| AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S (reference host) | `gfx1151` | 80 GiB unified GTT pool | ROCm 7.14.0 — vLLM @`4d2a68d`, llama.cpp @`4df29be` | ✅ Project-validated | [vLLM](docs/results/rocm-7.14/vllm-validation.md), [GGUF](docs/results/rocm-7.14/gguf-validation.md) |
| AMD Radeon Pro W7900D | `gfx1100` | 48 GiB discrete VRAM (submitter's rocm-smi) | ROCm 7.2.1 (kernel 6.8.0-79-generic) — submitter stack, see docs/hardware-validation.md | 🧪 Community validated — GGUF | [env-check.txt](docs/results/matrix-714/community/w7900d-gfx1100-rocm721/env-check.txt), [w7900d-gfx1100-rocm721](docs/results/matrix-714/community/w7900d-gfx1100-rocm721/) |

✅ project-validated on the reference host; 🧪 community-validated — a submitter's receipts, schema-checked and reviewed per [docs/hardware-validation.md](docs/hardware-validation.md); 🚧 planned — invited, no evidence yet. Community status never changes project verdicts or quickstart defaults (`configs/community/` and the community receipts tree are a separate namespace).
<!-- END GENERATED: hardware-matrix -->

## Performance

<!-- BEGIN GENERATED: performance-highlights -->
Measured 2026-08-16/17 on the reference host (gfx1151, ROCm 7.14, 80 GiB GTT pool): **20 cells — 4 recommended / 10 caution / 6 avoid**. Verdicts: `configs/benchmark-verdicts.json`; raw receipts: `docs/results/matrix-714/cells/`; full tables: `docs/results/benchmark.md`.

**Recommended — interactive chat (GGUF path, UD-Q4_K_XL):**

| Config | Per-stream (median) | Aggregate | TTFT | Verdict |
|---|---|---|---|---|
| `WITH_MTP=1` mtp-c1 @131072 — +28% per-stream | 13.0 tok/s (TPOT 76.9 ms) | 10.2 tok/s | 5.5 s | ✅ recommended |
| default boot base-c1 @131072 | 10.1 tok/s (TPOT 98.6 ms) | 8.4 tok/s | 5.1 s | ✅ recommended |
| base-c1 @32768 | 10.0 tok/s (TPOT 99.6 ms) | 8.3 tok/s | 5.3 s | ✅ recommended |
| base-c1 @262144 (GTT +8.0 GiB) | 10.1 tok/s (TPOT 98.8 ms) | 8.4 tok/s | 5.3 s | ✅ recommended |

**Caution — batch / throughput (vLLM BF16 @262144):** every measured vLLM cell is below the 10 tok/s interactive floor (controller ruling 2026-08-17) — use this path for what it wins:

| Config | Per-stream (median, min) | Aggregate | Verdict |
|---|---|---|---|
| base-c16-ctx262144 | 3.0 (min 2.58) tok/s | 38.6 tok/s | ⚠️ caution — best batch cell measured |
| mtp-c8-ctx262144 | 4.2 (min 3.47) tok/s | 24.7 tok/s | ⚠️ caution — MTP beneficial through c8 |
| mtp-c1-ctx262144 | 6.5 tok/s | 5.8 tok/s | ⚠️ caution — +52.6% per-stream vs base (+45.5% aggregate, basis labeled in the verdict) |

**Honesty clause (aggregate never headlines over UX):** the best aggregate on this host — vLLM base-c16, 38.6 tok/s — runs each stream at 3.0 tok/s median (min 2.58): batch presentation only. GGUF c8/c16 aggregates (to 27.5 tok/s) are ❌ avoid cells — greedy decoding degrades after sustained multistream load (see Known good / known bad). Interactive chat → GGUF `WITH_MTP=1` (13.0 tok/s per stream).
<!-- END GENERATED: performance-highlights -->

## Context capacity

<!-- BEGIN GENERATED: context-capacity -->
Boot ladder (S3) + deep-prompt retrieval smoke — GGUF path, needle sentence at ~80% depth, judged by exact substring recall (`docs/results/matrix-714/long-context-smoke.json`):

| Path | Tier | Boots | GTT at load | Retrieval @~80% depth | Cell verdicts |
|---|---|---|---|---|---|
| gguf | 32768 | OK (14.0 s) | 20,406 MiB | PASS @ 29,614 prompt tokens (TTFT 137.4 s) | base-c1 ✅ (base-c4-ctx32768 ❌ — greedy pit) |
| gguf | 131072 | OK (4.0 s) | 26,546 MiB | **FAIL — confident miss** (answered "No validation codename is mentioned in the documents.", finish_reason=stop) @ 120,305 prompt tokens (TTFT 1012.1 s) | c1 base/mtp ✅; c4 ⚠️ (below floor); c8/c16 ❌ (greedy pit) |
| gguf | 262144 | OK (6.0 s) | 34,736 MiB | PASS @ 247,232 prompt tokens (TTFT 3457.3 s) | base-c1 ✅ (+8.0 GiB GTT); base-c4 ⚠️ (below floor) |
| vllm | 262144 | OK (171 s) | 75,040 MiB (weights 51.1, KV 19.57 GiB) | not run on this path | 8 cells ⚠️/❌ per the 2026-08-17 ruling (mtp-c16 ❌) |

**`max_usable_context`, honestly:** every tier boots on the GGUF path, but functional retrieval is **non-monotonic in depth** — 30K PASS, 120K confident miss, 247K PASS (one needle, one depth, one seed) — so a reliable max_usable_context for deep-prompt retrieval is **not established above ~30K** by this smoke; treat deep-context answers as unverified until re-tested (METHODOLOGY §1 ruling).

**KV ceilings:** GGUF KV grows 64 KiB/token bf16 — +8.0 GiB per 131,072 tokens, the closed form confirmed by the GTT ladder (26,548 → 34,742 MiB). vLLM @262144 budgets KV 19.57 GiB = 313,650 tokens (1.20x max-len; MTP: 18.59 GiB, 279,146 tokens, 1.06x) — **a single full-depth request fits; two concurrent full-depth streams do not** (deep-context concurrency is KV-budget-bound long before `max_num_seqs`).
<!-- END GENERATED: context-capacity -->

## Known good / known bad

<!-- BEGIN GENERATED: known-good-bad -->
**Known good** (verdict receipts in `configs/benchmark-verdicts.json`):

- ✅ **GGUF interactive at c1** — all three ctx tiers recommended; default boot (10.1 tok/s per stream) and `WITH_MTP=1` (13.0 tok/s, +28% per-stream).
- ✅ **vLLM path anchor-clean in all 8 cells** — including anchors run immediately after 16-stream benches: the GGUF greedy-degradation pit does NOT reproduce here; the honest choice for 262144 context, vision, and batch throughput (38.6 tok/s aggregate @base-c16).
- ✅ **Boot reliability** — every declared-priority cell booted (GGUF 4–6 s warm; vLLM 171/226 s); zero failed streams across all 20 cells.

**Known bad / pits:**

- ❌ `gguf-udq4kxl-auto-base-c16-ctx131072` — greedy `'////'` corruption after sustained multistream load (anchor failed; per-stream median 3.2 tok/s, aggregate 27.5 tok/s recorded but secondary). Workaround: restart the server; multi-stream loads → vLLM. Upstream: llama.cpp HIP on gfx1151 — live at master HEAD 01818e495 (2026-08-17), same pit as the 4df29be4 pin; candidate fix PR #25863 https://github.com/ggml-org/llama.cpp/pull/25863 differentially verified on this host (patched 2/2 anchor PASS vs unpatched 3/3 FAIL on the idle host; receipts docs/results/upstream-controls/); tracked upstream in #25992 https://github.com/ggml-org/llama.cpp/issues/25992 (primary — same-host bisect, maintainer invited testing of the PR) and #23577 https://github.com/ggml-org/llama.cpp/issues/23577 (////-family); exact mechanism unresolved at session close (METHODOLOGY §6).
- ❌ `gguf-udq4kxl-auto-base-c4-ctx32768` — greedy `'////'` corruption after sustained multistream load (anchor failed; per-stream median 5.8 tok/s, aggregate 15.7 tok/s recorded but secondary). Workaround: restart the server; multi-stream loads → vLLM. Upstream: llama.cpp HIP on gfx1151 — live at master HEAD 01818e495 (2026-08-17), same pit as the 4df29be4 pin; candidate fix PR #25863 https://github.com/ggml-org/llama.cpp/pull/25863 differentially verified on this host (patched 2/2 anchor PASS vs unpatched 3/3 FAIL on the idle host; receipts docs/results/upstream-controls/); tracked upstream in #25992 https://github.com/ggml-org/llama.cpp/issues/25992 (primary — same-host bisect, maintainer invited testing of the PR) and #23577 https://github.com/ggml-org/llama.cpp/issues/23577 (////-family); exact mechanism unresolved at session close (METHODOLOGY §6).
- ❌ `gguf-udq4kxl-auto-base-c8-ctx131072` — greedy `'////'` corruption after sustained multistream load (anchor failed; per-stream median 3.6 tok/s, aggregate 18.4 tok/s recorded but secondary). Workaround: restart the server; multi-stream loads → vLLM. Upstream: llama.cpp HIP on gfx1151 — live at master HEAD 01818e495 (2026-08-17), same pit as the 4df29be4 pin; candidate fix PR #25863 https://github.com/ggml-org/llama.cpp/pull/25863 differentially verified on this host (patched 2/2 anchor PASS vs unpatched 3/3 FAIL on the idle host; receipts docs/results/upstream-controls/); tracked upstream in #25992 https://github.com/ggml-org/llama.cpp/issues/25992 (primary — same-host bisect, maintainer invited testing of the PR) and #23577 https://github.com/ggml-org/llama.cpp/issues/23577 (////-family); exact mechanism unresolved at session close (METHODOLOGY §6).
- ❌ `gguf-udq4kxl-auto-mtp-c16-ctx131072` — greedy `'////'` corruption after sustained multistream load (anchor failed; per-stream median 1.4 tok/s, aggregate 16.3 tok/s recorded but secondary). Workaround: restart the server; multi-stream loads → vLLM. Upstream: llama.cpp HIP on gfx1151 — live at master HEAD 01818e495 (2026-08-17), same pit as the 4df29be4 pin; candidate fix PR #25863 https://github.com/ggml-org/llama.cpp/pull/25863 differentially verified on this host (patched 2/2 anchor PASS vs unpatched 3/3 FAIL on the idle host; receipts docs/results/upstream-controls/); tracked upstream in #25992 https://github.com/ggml-org/llama.cpp/issues/25992 (primary — same-host bisect, maintainer invited testing of the PR) and #23577 https://github.com/ggml-org/llama.cpp/issues/23577 (////-family); exact mechanism unresolved at session close (METHODOLOGY §6).
- ❌ `gguf-udq4kxl-auto-mtp-c8-ctx131072` — greedy `'////'` corruption after sustained multistream load (anchor failed; per-stream median 2.1 tok/s, aggregate 10.7 tok/s recorded but secondary). Workaround: restart the server; multi-stream loads → vLLM. Upstream: llama.cpp HIP on gfx1151 — live at master HEAD 01818e495 (2026-08-17), same pit as the 4df29be4 pin; candidate fix PR #25863 https://github.com/ggml-org/llama.cpp/pull/25863 differentially verified on this host (patched 2/2 anchor PASS vs unpatched 3/3 FAIL on the idle host; receipts docs/results/upstream-controls/); tracked upstream in #25992 https://github.com/ggml-org/llama.cpp/issues/25992 (primary — same-host bisect, maintainer invited testing of the PR) and #23577 https://github.com/ggml-org/llama.cpp/issues/23577 (////-family); exact mechanism unresolved at session close (METHODOLOGY §6).
- ❌ `vllm-bf16-auto-mtp-c16-ctx262144` — MTP regresses vs baseline at c16 (31.1 vs 38.6 tok/s aggregate, per-stream min 1.85 tok/s); serve without `--mtp` at high concurrency.
- ⚠️ **vLLM encoder profiling** — boot OOMs at `--max-model-len 262144` without `--skip-mm-profiling` (ViT dummy batch scales with max_model_len; attempted allocation 256 GiB vs the 80 GiB pool). The flag is mandatory — and with it the encoder activation peak is unbudgeted: the operator budgets image traffic (`docs/results/rocm-7.14/vllm-validation.md` ## Vision).
- ⚠️ **GGUF ctx 262144 GTT growth** — +8.0 GiB over the 131072 boot (34,742 vs 26,548 MiB; 64 KiB/token bf16 KV): capacity-OK, caution-grade — fits the 80 GiB pool with headroom.
- ⚠️ **vLLM KV ceiling at 262144** — KV 19.57 GiB = 313,650 tokens (1.20x max-len; MTP 1.06x): one full-depth stream fits, two don't.
- ⚠️ **Deep-context retrieval (GGUF)** — 120K tier returned a confident miss; non-monotonic vs depth, unverified above ~30K (see Context capacity).

Every verdict with its full reason/conditions/workaround: `configs/benchmark-verdicts.json`.
<!-- END GENERATED: known-good-bad -->

Full tables with links to the raw receipts: [docs/results/benchmark.md](docs/results/benchmark.md).
