# Qwen3.8-27B-ROCm

> Work in progress. Goal: the reproducible RDNA reference for
> [Qwen/Qwen3.8-27B](https://modelscope.cn/models/Qwen/Qwen3.8-27B) on
> AMD ROCm 7.14.0 — method: Adapt → Validate → Benchmark → Explain →
> Reproduce.
>
> Status: both serving paths (vLLM and llama.cpp/GGUF) validated on the
> reference host (see the table).
> Validated platform: AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S (`gfx1151`).
> W7900 (`gfx1100`) is planned, evidence-gated.

Design spec: `docs/superpowers/specs/2026-08-16-qwen3.8-27b-rocm-design.md`

## Serving paths

| Path | Status (`gfx1151`, ROCm 7.14) | Evidence |
| --- | --- | --- |
| vLLM (source build @ `4d2a68d`, BF16) | Validated — text, MTP speculative decoding, 262144 context, and single-small-image vision; encoder-peak memory for larger image workloads is unbudgeted under `--skip-mm-profiling` | `docs/results/rocm-7.14/vllm-validation.md` |
| llama.cpp / GGUF (HIP build @ `4df29be`, UD-Q4_K_XL) | Validated — text (greedy smoke at ctx 131072), MTP via `--spec-type draft-mtp`, and single-small-image vision via mmproj-F16; `CTX_SIZE=262144` boots but total GTT grows to 33.9 GiB (weights + KV; the 262144 KV increment is ≈ 8.2 GiB over the 131072 boot), so the validated default stays 131072 | `docs/results/rocm-7.14/gguf-validation.md` |
