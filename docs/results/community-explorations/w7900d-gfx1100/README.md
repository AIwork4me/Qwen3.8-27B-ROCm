# W7900D (gfx1100) local-lineage exploration archive — context, not evidence

This directory preserves the full record of the **submitter's own working
repository** — a parallel lineage in which the W7900D platform was explored
before the community submission landed. Per
[docs/hardware-validation.md](../../../hardware-validation.md) these numbers
come from a **local harness** (`bench_driver.py`, `probe-fp8-unlock.sh`) and
are therefore **context, never evidence** for the project index. The
evidence-grade cells for this platform live exclusively in
[matrix-714/community/w7900d-gfx1100-rocm721/](../../matrix-714/community/w7900d-gfx1100-rocm721/)
(this repo's own runners, PR #1, merged 2026-08-18).

## What is here

| Path | Content |
|---|---|
| `results/spike/` | Pre-validation reconnaissance on the W7900D host: environment, llama.cpp/GGUF support, quant + KV levers, vLLM probing, decision table |
| `results/gguf-serving/` | GGUF serving receipt + experiments (build identity, VRAM at load, smoke logs) |
| `results/matrix/` | 16-cell local-runner matrix (Q4_K_M/Q6_K/Q8_0 × c1/c4/c16/c32, MTP, KV-q8) + 3 contingent FP8-vLLM cells; `SHA256SUMS` covers all cells and stays valid inside this tree |
| `results/upstream/` upstream-issue draft | Evidence pack for vllm-project/vllm#52663 (FP8 on RDNA3 gfx1100: engine-timeout unlock, Triton JIT first-request cliff) |
| `scripts/` | The reproduction code for the above: `probe-fp8-unlock.sh`, `bench_driver.py`, `bench-prompt.txt` |

## Key results (local harness — see caveat above)

- GGUF single-stream ≈ 28.6–28.7 tok/s (c1, all three quants); aggregate to
  164.4 tok/s at c32; MTP +31% at c1 (37.4 tok/s); KV q8_0 ≈ parity with f16.
- FP8 vLLM (Qwen3.8-27B-FP8, 28.75 GiB checkpoint): boots on gfx1100 only
  with `VLLM_ENGINE_READY_TIMEOUT_S=1800` (untuned W8A8 config search
  ≈1474 s) + ~43 min first-inference Triton JIT staging; then 0.6 / 2.3 /
  8.7 tok/s (c1/c4/c16) — a capacity unlock, not a performance path.
- vLLM BF16 was never attempted: ~51.7 GiB of weights cannot fit the 48 GiB
  board (docs/hardware-validation.md).

## Cross-verification against the official runners

The protocol-grade re-run (PR #1) confirms the local lineage's GGUF-path
conclusions under the frozen methodology: single-stream 29.9 tok/s (local:
28.6), MTP +26.2% same-context at ctx 131072 (local: +31% at ctx 32768),
and the FP8 exploration stands as documented context referenced by the
platform's `stack-manifest.md`. Divergences are harness-shape differences
(generation length, prompt set, KV semantics at c4), which is exactly why
the protocol requires the repo's own runners for the index.

## Reproduction

The archived `scripts/` are the exact ones the receipts quote; `results/`
documents carry their invocation lines verbatim (paths inside the archived
docs refer to the original lineage layout — `scripts/…`/`configs/…` at that
repo's root, mirrored here under `scripts/`). The FP8 path additionally
needs the official FP8 checkpoint (`Qwen/Qwen3.8-27B-FP8`) and a vLLM
`0.27.1+rocm723`-class wheel on ROCm 7.2.x.
