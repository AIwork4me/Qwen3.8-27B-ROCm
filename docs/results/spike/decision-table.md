# Spike decision table — 2026-08-16

Synthesis of the three spike receipts ([vllm.md](vllm.md), [gguf.md](gguf.md),
[quant-kv.md](quant-kv.md)); machine-readable form in
`configs/spike-findings.json` (validated by `schemas/spike-findings.schema.json`).
Pins: vLLM main `4d2a68d` (2026-08-16), llama.cpp master `3cb7ffb` (Spike B)
re-pinned `4df29be` (Spike C), transformers v5.8.0–v5.15.0, all probed 2026-08-16.

| Path / lever | Status | Evidence | Plan implication |
|---|---|---|---|
| vLLM | supported | [vllm.md](vllm.md) | Full validation now — arch + MTP registered at main `4d2a68d` (`Qwen3_5ForConditionalGeneration`, `Qwen3_5MTP`), transformers released since v5.8.0; recorded gap is platform-local: vLLM-on-ROCm-gfx1151 runtime unvalidated for qwen3_5 (community source builds only; head_dim 256 forces Triton attention, custom paged attn never fires), no open ROCm-specific qwen3_5 MTP issue (vllm#52480/#52481 platform-agnostic, TP=1 dodges #52480) — our work is a ROCm 7.14 gfx1151 source build, not upstream changes |
| GGUF / llama.cpp | supported | [gguf.md](gguf.md) | Full validation now — arch `qwen35` at master `3cb7ffb` with GDN + draft-mtp + mmproj; download prebuilts (unsloth 2026-08-13, lmstudio-community/bartowski 2026-08-14); AMD's official gfx1151 route is llama.cpp/Vulkan with MTP=4; recorded gaps: HIP-for-gfx1151 buildable but not CI-covered (open #21284 prefill-perf; keep a Vulkan fallback build) and self-conversion carries open bug #27019 / unmerged PR #27132 — prebuilts primary, converter fallback |
| Official quants | 1 official (FP8); 8 variants catalogued in `configs/spike-findings.json` | [quant-kv.md](quant-kv.md) | Benchmark plan sweeps GGUF `UD-Q4_K_XL` (16.69 GiB, AMD Day-0 reference quant) first, then `Q4_K_M`/`Q6_K`; for the vLLM path sweep `cyankiwi` AWQ-INT4 W4A16 (19.6 GiB, the one int4 class with an upstream gfx1151 kernel — RDNAHybrid); official FP8 (28.7 GiB) and Quark W4A16-int4 excluded on gfx1151 (`supports_fp8`=False CDNA/RDNA4-only; Quark int4 unloadable in vLLM main), Quark MXFP4 (18.4 GiB) low-priority emulation datapoint only |
| KV fp8 | partial | [quant-kv.md](quant-kv.md) | Swept as matrix variable, not a given: vLLM `--kv-cache-dtype fp8` (e4m3-only on ROCm) vs `auto` under Triton attention — unvalidated on gfx1151, watch #13147-class fp8+prefix-caching interaction; llama.cpp `-ctk/-ctv q8_0` vs f16 (FA on, mandatory for quantized V; f8 does not exist upstream); capacity at 262K ctx: on the validated 80 GiB GPU-visible pool KV quant is NOT mandatory (bf16 KV ≈16.0 GiB fits alongside quantized — or even BF16 — weights; constraint is GTT-spill performance and activation headroom), on the 32 GiB-class minimum-SKU envelope (e.g. R9700/32 GB) it IS mandatory (bf16 16.0 GiB vs fp8 8.0 / q8_0 8.5 GiB); bf16/f16 fallback cell in every sweep |

Notes for the plans reading this table:

- `quant_variants[].method` maps the receipt's `quantization_config.quant_method`
  onto the schema enum: Quark W4A16-int4 (`quant_method: quark`) is `other` to
  keep it distinct from genuine awq/compressed-tensors W4A16 (`cyankiwi` = `awq`);
  GGUF rows use `repo::file` in `repo_id` to disambiguate the unsloth ladder.
- All hosts are `modelscope` because that hub was directly reachable from the
  probe host; the same repos mirror on HF (via hf-mirror) per Spike B/C receipts.

## Next plans gated on this table

1. vLLM path plan — scope per row 1.
2. GGUF path plan — scope per row 2.
3. Benchmark matrix plan — variables per rows 3–4.
