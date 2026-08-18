# Spike decision table — 2026-08-16

| Path / lever | Status | Evidence | Plan implication |
|---|---|---|---|
| ROCm 7.14.0 on W7900 | supported | [rocm-w7900.md](rocm-w7900.md) | serving phases build on the validated ~/rocm-7.14.0-gfx1100 prefix |
| vLLM | supported | [vllm.md](vllm.md) | full validation now: pin v0.27.1 (or main at 83f591d) + transformers v5.8.0; Qwen/Qwen3.8-27B-FP8 load is the gating smoke test (supports_fp8() is False on gfx1100, qwen3_5 unvalidated on RDNA3, open bug #39348 on an RX 7900 card) |
| GGUF / llama.cpp | supported | [gguf.md](gguf.md) | consume the ready-made ModelScope quants (unsloth 21, bartowski 26 — bartowski: built for llama.cpp b10419+; unsloth: upstream qwen35 arch string header-verified) against the untested gfx1100 HIP/Vulkan backend; local BF16 conversion is the contingency that carries the --no-mtp workaround for open bugs #27019/#26916 (fix PR #27132 unmerged at probed HEAD) |
| Official quants | 1 official (FP8) + 2 community GGUF repos | [quant-kv.md](quant-kv.md) | benchmark plan sweeps GGUF Q4_K_M-class first (unsloth 15.9 GiB, bartowski 16.6 GiB — multi-quant repo totals in configs/spike-findings.json are the measured Q4_K_M file size, the representative 48-GiB serving pick); the official FP8 (28.7 GiB) is the vLLM contingent, gated behind the supports_fp8()-on-gfx1100 smoke test |
| KV fp8 | partial | [quant-kv.md](quant-kv.md) | swept as a Phase 3 matrix variable behind a load/correctness gate, not a plan dependency: fp8_e4m3 is advertised and implemented in ROCM_ATTN/TRITON_ATTN (per-tensor scales only) but never executed on gfx1100 and AMD scopes FP8 KV to CDNA; fp8_e5m2 and per-head scaling are CUDA-only, and llama.cpp has no f8 KV at all (q8_0 family only) — recorded as gaps |
| FP8 load on gfx1100 (smoke) | UNLOCKED (smoke) | [fp8-unlock.md](fp8-unlock.md) (was GAP: [fp8-smoke.md](fp8-smoke.md)) | FP8 serves on W7900D via lever 1 — VLLM_ENGINE_READY_TIMEOUT_S=1800 covers the one-time ~1475 s untuned W8A8 config search, and the 3 contingent vLLM cells completed OK (aggregate decode 0.612/2.301/8.730 tok/s at c1/c4/c16; 105/105 requests); a second one-time cost is ~43 min of first-inference Triton JIT staging — both cached on disk, later starts ~2 min — a timeout/config gap, not an arch refusal, but ~47x slower per stream than llama.cpp Q4_K_M, so FP8 vLLM is a correctness/capacity unlock, not a performance one; upstream issue ready to file (ship Radeon tuned configs or document the env var) |

## Next plans gated on this table

1. vLLM serving path plan (Phase 1) — scope per row 2.
2. GGUF path plan (Phase 2) — scope per row 3.
3. Benchmark matrix plan (Phase 3) — variables per rows 4–5.
