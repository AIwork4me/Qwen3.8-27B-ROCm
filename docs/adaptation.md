# Adaptation map — from MI-series / Day-0 recipes to RDNA `gfx1151`

What changes when you take an upstream (or AMD Day-0, Instinct-oriented)
recipe for Qwen3.8-27B onto the RDNA 3.5 APU this project validated — and how
long each delta can be trusted to stay true. Every row cites the committed
receipt that established it; nothing here is folklore.

**Durability classes:**

- **durable** — gated by hardware/architecture or by slow-moving upstream
  predicates; re-check only when the silicon or the model changes.
- **pin-local** — verified only at the pinned commits
  ([`configs/validated-stack.json`](../configs/validated-stack.json): vLLM
  `4d2a68d`, llama.cpp `4df29be4`, ROCm 7.14.0); re-verify when a pin moves.
- **host-class** — true of Strix-Halo-class APUs (unified memory), not of
  discrete boards.

## What carries over unchanged

The model-facing wiring is platform-agnostic and needed no patches:

- transformers supports `qwen3_5` in every release tag checked (v5.8.0 →
  v5.15.0) — no from-source install
  ([spike A](results/spike/vllm.md)).
- vLLM registers `Qwen3_5ForConditionalGeneration` (multimodal) and
  `Qwen3_5MTP` (speculative) in-tree
  ([spike A](results/spike/vllm.md));
  our build applied no upstream code changes beyond the two shim patches
  listed in [`configs/validated-stack.json`](../configs/validated-stack.json).
- llama.cpp registers the arch as `qwen35` (GDN linear attention + single-block
  MTP + Qwen3-VL-type mmproj vision) since 2026-02
  ([spike B](results/spike/gguf.md)) — prebuilt GGUF quants exist from three
  publishers, so self-conversion (open bug #27019 at spike time) is a fallback
  only.

## Delta table

| # | Area | MI-series / Day-0 assumption | RDNA `gfx1151` reality (measured) | Durability | Receipts |
|---|---|---|---|---|---|
| 1 | Toolchain | One ROCm stack serves all data-center GPUs | PyTorch comes from the TheRock **per-arch** nightly index (`https://rocm.nightlies.amd.com/v2/gfx1151/`); the index has **no gfx1100 builds** (404, verified 2026-08-17), and it tops out at torch 2.10.0 for cp312 — vLLM then needs the torch-2.13-API compat shim to build | pin-local (nightly index drift) | [`configs/validated-stack.json`](../configs/validated-stack.json), [`hardware-validation.md`](hardware-validation.md), [spike A](results/spike/vllm.md) |
| 2 | Memory model | HBM VRAM sized in 10s of GiB, GPU-only | **UMA/GTT**: an 80 GiB GPU-visible pool carved from 94 GiB system RAM; weights+KV live in GTT, VRAM stays ~1.1 GiB (desktop residue). Budgeting must read the GTT number, and a "silent GTT spill" (throughput collapse with no load error, llama.cpp #26432 class) is the failure mode to watch | host-class (durable per host SKU; 32 GiB-class SKUs change every conclusion) | [`configs/validated-stack.json`](../configs/validated-stack.json), [METHODOLOGY §4](results/METHODOLOGY.md), [spike C](results/spike/quant-kv.md) |
| 3 | Quant surface | FP8 weights everywhere (Instinct Day-0 ships an FP8 checkpoint + Quark MXFP4 recipe) | vLLM's own predicates exclude gfx1151 from native FP8 (`supports_fp8()` = CDNA/RDNA4-only) and from MX compute; the official FP8 repo (28.7 GiB) is CDNA/RDNA4 territory. AMD's Quark W4A16-int4 export is **unloadable** at `4d2a68d` (no matching scheme); Quark MXFP4 loads but computes via high-precision **emulation**. The viable weight-quant class is W4A16 int4 (AWQ/GPTQ/compressed-tensors) via the RDNAHybrid/Triton kernels — `cyankiwi` AWQ-INT4 (19.6 GiB) is the candidate | predicates durable; quark-scheme availability pin-local | [spike C](results/spike/quant-kv.md), [decision table](results/spike/decision-table.md), [`configs/spike-findings.json`](../configs/spike-findings.json) |
| 4 | Attention | CDNA custom paged attention paths | The ROCm custom paged-attention gate requires `head_size == 128`; this model's `head_dim` is **256**, so custom paged attention never fires on gfx1151 regardless of KV dtype — everything routes to **Triton attention** (`--attention-backend TRITON_ATTN` pinned in the confs to protect against auto-select drift) | durable for this model+arch | [spike C](results/spike/quant-kv.md), [`configs/serve-args.conf`](../configs/serve-args.conf), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md) |
| 5 | MTP wiring | One flag, one behavior | **Syntax differs per path and per pin**: llama.cpp `--spec-type draft-mtp` (stock server flag at `4df29be4`; MTP head loads from the same GGUF — no `-md`); vLLM `--speculative-config {"method":"mtp","num_speculative_tokens":1}`. **Behavior is concurrency-dependent** (measured): +28.2% per-stream at GGUF c1, +52.6% at vLLM c1, beneficial through vLLM c8, **inverts at c16** (−19.4% aggregate). AMD's own Vulkan Day-0 measured MTP=4 net-negative on this platform class — backend-sensitive | behavior durable-ish (re-measure per pin); flags pin-local | [`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md), [`configs/serve-args-mtp.conf`](../configs/serve-args-mtp.conf), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md), [`results/benchmark.md`](results/benchmark.md), [troubleshooting](troubleshooting.md#mtp-concurrency) |
| 6 | Vision | Encoder memory profiled/reserved by default | llama.cpp: attach `mmproj-F16` (default ~20 image tokens; `--image-min-tokens 1024` for grounding work, ~1035 tokens). vLLM: **encoder profiling must be skipped** at 262144 (`--skip-mm-profiling`) because the profiling dummy batch scales with `max_model_len` (256 GiB demand vs the 80 GiB pool) — and with it skipped, encoder-peak budgeting becomes the operator's contract | host-class + pin-local | [`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md), [troubleshooting](troubleshooting.md#encoder-profiling) |
| 7 | Kernel floor | N/A on servers | Strix Halo UMA needs kernel ≥ 6.16.9 (muse-rocm heritage finding; enforced by the env check) | host-class | [`configs/validated-stack.json`](../configs/validated-stack.json), [troubleshooting](troubleshooting.md#uma-bug) |
| 8 | Output packaging | DeepSeek-style `reasoning_content` everywhere | llama.cpp emits `message.reasoning_content`; the vLLM `qwen3` parser at `4d2a68d` emits `message.reasoning` (generation identical) | pin-local | [`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md), [troubleshooting](troubleshooting.md#reasoning-field) |

## Porting checklists by durability

**Re-verify when a pin moves (pin-local):** TheRock index contents and torch
cap (row 1); quark scheme coverage (row 3); MTP flag spelling and reasoning
field name (rows 5, 8); encoder-profiling behavior (row 6).

**Re-verify per host (host-class):** GTT pool size and the spill watch-point
(row 2); kernel floor (row 7); encoder-peak headroom (row 6). Discrete boards
(W7900, `gfx1100`, 48 GiB GDDR6) have no GTT pool at all — memory evidence
must come from the submitter's own `rocm-smi` receipts per
[`hardware-validation.md`](hardware-validation.md), and the protocol
prescribes evidence format, not a stack.

**Trust as-is (durable):** Triton attention routing for `head_dim` 256
(row 4); the arch registration facts in "What carries over unchanged"; the
KV closed form (64 KiB/token bf16 — only the 16 full-attention layers grow
KV; [METHODOLOGY §4](results/METHODOLOGY.md)).

## Non-goals carried from the spike

FP8 weights on gfx1151 (`supports_fp8`=False), the AMD Quark W4A16-int4
checkpoint (unloadable), and Quark MXFP4 as anything more than an emulation
datapoint were **deliberately not scheduled** for validation
([decision table](results/spike/decision-table.md),
[spike C](results/spike/quant-kv.md)). KV-cache dtype sweeps (fp8/q8_0) were
declared non-goals of the measured session (METHODOLOGY §1) — on the
validated 80 GiB pool they are a throughput/quality lever, not a capacity
gate; on 32 GiB-class envelopes they are mandatory
([spike C impact tables](results/spike/quant-kv.md)).
