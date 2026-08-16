# Qwen3.8-27B-ROCm

> Work in progress. Goal: the reproducible RDNA reference for
> [Qwen/Qwen3.8-27B](https://modelscope.cn/models/Qwen/Qwen3.8-27B) on
> AMD ROCm 7.14.0 — method: Adapt → Validate → Benchmark → Explain →
> Reproduce.
>
> Status: vLLM serving path validated on the reference host (see the table).
> Validated platform: AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S (`gfx1151`).
> W7900 (`gfx1100`) is planned, evidence-gated.

Design spec: `docs/superpowers/specs/2026-08-16-qwen3.8-27b-rocm-design.md`

## Serving paths

| Path | Status (`gfx1151`, ROCm 7.14) | Evidence |
| --- | --- | --- |
| vLLM (source build @ `4d2a68d`, BF16) | Validated — text, MTP speculative decoding, 262144 context, and single-small-image vision; encoder-peak memory for larger image workloads is unbudgeted under `--skip-mm-profiling` | `docs/results/rocm-7.14/vllm-validation.md` |
| llama.cpp / GGUF | Planned — see decision table | `docs/results/spike/decision-table.md` |
