# Phase 3 benchmark matrix

Cells: 19 (schema bench-cell-v1; SHA256SUMS covers all).
Params: temp 0, ctx 32768 total, 5 reps, 128-token gens (MTP cells 512). Host: W7900 gfx1100, ROCm 7.14.0.

| quant | c=1 | c=4 | c=16 | c=32 |
|---|---:|---:|---:|---:|
| Q4_K_M | 28.6 | 60.9 | 120.0 | 164.4 |
| Q6_K | 28.7 | 61.0 | 120.3 | 160.9 |
| Q8_0 | 28.7 | 60.7 | 120.5 | 165.3 |

## MTP (draft-mtp, 512-token generations)

- mtp-q4km-c1: 37.4 tok/s (baseline 28.6)
- mtp-q4km-c4: 89.3 tok/s (baseline 60.9)

## KV q8_0 on Q8_0

- kv-q8-c4: 60.4 tok/s (f16-KV 60.7)
- kv-q8-c16: 119.2 tok/s (f16-KV 120.5)

## vLLM FP8 (contingent cells)

- vllm-c1: 0.6 tok/s
- vllm-c4: 2.3 tok/s
- vllm-c16: 8.7 tok/s

## Decision guide

- Default pick: Q4_K_M — 28.6 tok/s single-stream with ~30 GiB VRAM headroom for context.
- Best quality: Q8_0 — 28.7 tok/s single-stream (27.1 GiB weights; pair with KV q8_0 when context matters: 60.4 vs 60.7 tok/s at c=4).
- Single-stream speed: open MTP — +31% at c=1 (37.4 vs 28.6 tok/s).
- Throughput over latency: raise -np; aggregate scales to 164.4 tok/s at c=32 on Q4_K_M.
