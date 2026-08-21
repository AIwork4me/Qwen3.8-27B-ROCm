# DFlash 2 on RDNA — with/without comparison (gfx1100 host evidence)

**DFlash 2** ([`incoai/Qwen3.8-27B-DFlash2`](https://huggingface.co/incoai/Qwen3.8-27B-DFlash2))
is a ~1.9 B block-diffusion **speculative-decoding drafter** for
Qwen3.8-27B: it drafts a whole block of tokens in one pass, a selector
traces one coherent path, and the target model verifies — **lossless**
(greedy output matches the target exactly; sampling preserves its
distribution). Decoding is lossless: verified on this host —
[`equiv.json`](equiv.json) shows 4/4 prompts byte-identical between the
baseline and DFlash2 boots.

This directory is the **host-labeled evidence namespace** for the DFlash2
phase (2026-08-21). It follows the community-namespace rule: the project
matrix (`docs/results/matrix-714/`, reference host gfx1151) is untouched;
the runner was pointed here via `MATRIX_FILE`/`CELLS_DIR`.

## The comparison (with vs without DFlash 2)

Measured 2026-08-21 on **AMD Radeon W7900-class `gfx1100`, 48 GiB VRAM,
ROCm 7.2.1 serving (`/opt/rocm`), llama.cpp PR
[#27342](https://github.com/ggml-org/llama.cpp/pull/27342) @ `5ecbe1ac`,
HIP build** — **clean pairing**: every row below, with or without a
drafter, boots the *same* binary from *this* build, same day, same prompt
set, so the deltas isolate the drafter (the v0.1.4 mixed-pairing lesson
applied from the start). Target: UD-Q4_K_XL GGUF at ctx 131072; draft:
Q8_0 (2.0 GiB); bench: 8-prompt set, 256 tokens, temperature 0.7
(project convention), greedy anchor gated per cell.

| Boot (one switch) | c=1 per-stream | c=1 delta | c=4 per-stream (median) | c=4 delta | TTFT c=1 | VRAM |
|---|---:|---:|---:|---:|---:|---:|
| `bash scripts/gguf-quickstart.sh` (baseline, no drafter) | 29.4 tok/s | — | 17.3 tok/s | — | 1.87 s | 25.9 GiB |
| `WITH_DFLASH2=1 bash scripts/gguf-quickstart.sh` | 33.2 tok/s | **+12.8%** | 21.4 tok/s | **+23.3%** | 2.29 s | 32.6 GiB |
| `WITH_MTP=1 SPEC_DEPTH=1 bash scripts/gguf-quickstart.sh` (context arm) | 41.3 tok/s | +40.5% | 16.4 tok/s | −5.0% | 2.06 s | 27.4 GiB |

Aggregates (total output tokens / wall): c=1 25.7 vs 24.3 tok/s (+5.6%);
c=4 47.5 vs 45.0 tok/s (+5.7%); MTP c4 aggregate 43.6. The per-stream vs
aggregate gap at c=1 is the TTFT cost — the drafter adds ~0.4 s prompt
processing before the first token.

**Why the win is smaller than the vendor table** (H200/SGLang 2.7–3.4× at
c=1; M5 Pro/llama.cpp 1.8×): acceptance. This host's bench measured
**draft acceptance ≈ 0.29** (8-prompt probe, 624/2186; the single-prompt
cell log showed 0.36) — versus the vendor's ≈ 5/7 on GSM8K-class
reasoning workloads — and a compute-limited `gfx1100` pays more per
8-token verification step than an H200. A post-release probe ruled the
sampling regime OUT (0.7/0.95 vs the vendor's 1.0/0.95/20 measured
statistically identical acceptance —
[`acceptance-probe.json`](acceptance-probe.json)): the gap is
workload-intrinsic on this prompt set. The vendor numbers are real for
their stacks; they do not transfer to this host as-is. Numbers here are
the honest local ones.

**c=16 probe (split KV, ctx 32768):** `dflash2-c16` completed — 16/16
streams OK in 93 s, 43.1 tok/s aggregate, per-stream median 13.9 tok/s
(spread 8.4–25.0, TTFT median 40.5 s). **The DFlash v1 `-np 16` hang
(Muse-Glimmer, aborted after 5 h 16 m) does NOT reproduce on DFlash 2 at
this scale** — but per-stream quality of service at c16 is poor; serve
c ≤ 4 with DFlash2.

**Bottom line for this host class (W7900/gfx1100) — the recommendation
splits by load shape:** single-stream interactive → **MTP depth 1**
(41.3 tok/s, no extra model); 2–4 concurrent streams → **DFlash 2**
(21.4 median vs 17.3 base — and MTP-d1 inverts to 16.4 at c4 here).
DFlash2 costs +6.9 GiB VRAM and ~0.4 s TTFT; its losslessness is proven
either way. Its case strengthens further on bandwidth-rich,
acceptance-friendly workloads (see the vendor blog for H200 numbers).

## Quick start (3 commands)

```bash
bash scripts/07-build-llama-dflash2.sh       # once: PR #27342 HIP build (gfx auto-detected)
SET=dflash2 bash scripts/02-fetch-model.sh   # once: draft GGUF, SHA256-verified (ModelScope)
WITH_DFLASH2=1 bash scripts/gguf-quickstart.sh   # serving on :8080, lossless, +13–23%
```

Verify (greedy anchor — must match the no-drafter boot byte-for-byte):

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply with exactly: OK"}],"temperature":0,"max_tokens":512}'
```

Without DFlash2: just omit `WITH_DFLASH2=1` (every default boot is
byte-identical to before this phase). Knobs: `DFLASH_FILE`
(Q4_K_M 1.1 GiB if VRAM-tight), `SPEC_DEPTH` (draft length, hard cap 7 =
block_size − 1), `LLAMA_SERVER` (binary override).

## Contents

| File | What it is |
|---|---|
| [`matrix.json`](matrix.json) | declared + measured cells (id grammar incl. the `dflash2` spec part) |
| [`cells/`](cells/) | raw cell receipts (server flags, slot semantics, load VRAM, telemetry, streams, anchor) |
| [`serving-receipt.md`](serving-receipt.md) | stack manifest: exact binary, commits, commands, environment |
| [`experiments.md`](experiments.md) | findings, acceptance analysis, negative results |
| [`equiv.json`](equiv.json) | greedy byte-identity receipt (losslessness proof, 4/4 PASS) |
| [`acceptance-probe.json`](acceptance-probe.json) | sampling-regime acceptance probe (0.7 vs vendor 1.0/k20 — identical) |

Spec: [`docs/superpowers/specs/2026-08-21-dflash2-phase-design.md`](../../superpowers/specs/2026-08-21-dflash2-phase-design.md).
Vendor numbers & other engines (SGLang/vLLM/oMLX):
[model card](https://huggingface.co/incoai/Qwen3.8-27B-DFlash2) ·
[blog](https://inco.ai/blog/dflash2/). On this 48 GiB host the vLLM/SGLang
DFlash2 paths are out of scope (BF16 needs 51.7 GiB of weights; the FP8
vLLM path is the recorded 47×-slower capacity unlock —
[`docs/results/spike/fp8-unlock.md`](../spike/fp8-unlock.md)).
