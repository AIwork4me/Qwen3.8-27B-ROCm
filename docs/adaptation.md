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
| 5 | MTP wiring | One flag, one behavior | **Syntax differs per path and per pin**: llama.cpp `--spec-type draft-mtp` (stock server flag at `4df29be4`; MTP head loads from the same GGUF — no `-md`; **depth configurable** via `--spec-draft-n-max`, upstream default 3 — measured: depth 1 beats depth 4 on both backends, see the Vulkan section below); vLLM `--speculative-config {"method":"mtp","num_speculative_tokens":1}`. **Behavior is concurrency-dependent** (measured): +28.2% per-stream at GGUF c1, +52.6% at vLLM c1, beneficial through vLLM c8, **inverts at c16** (−19.4% aggregate) and at GGUF-vulkan c4 (−7.5% aggregate). AMD's own Vulkan Day-0 measured MTP=4 net-negative on this platform class — depth-sensitive AND backend-sensitive | behavior durable-ish (re-measure per pin); flags pin-local | [`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md), [`configs/serve-args-mtp.conf`](../configs/serve-args-mtp.conf), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md), [`results/benchmark.md`](results/benchmark.md), [troubleshooting](troubleshooting.md#mtp-concurrency) |
| 6 | Vision | Encoder memory profiled/reserved by default | llama.cpp: attach `mmproj-F16` (default ~20 image tokens; `--image-min-tokens 1024` for grounding work, ~1035 tokens). vLLM: **encoder profiling must be skipped** at 262144 (`--skip-mm-profiling`) because the profiling dummy batch scales with `max_model_len` (256 GiB demand vs the 80 GiB pool) — and with it skipped, encoder-peak budgeting becomes the operator's contract | host-class + pin-local | [`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md), [troubleshooting](troubleshooting.md#encoder-profiling) |
| 7 | Kernel floor | N/A on servers | Strix Halo UMA needs kernel ≥ 6.16.9 (muse-rocm heritage finding; enforced by the env check) | host-class | [`configs/validated-stack.json`](../configs/validated-stack.json), [troubleshooting](troubleshooting.md#uma-bug) |
| 8 | Output packaging | DeepSeek-style `reasoning_content` everywhere | llama.cpp emits `message.reasoning_content`; the vLLM `qwen3` parser at `4d2a68d` emits `message.reasoning` (generation identical) | pin-local | [`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md), [troubleshooting](troubleshooting.md#reasoning-field) |

## Vulkan backend × MTP depth (v0.1.2, measured 2026-08-18)

The second llama.cpp backend measured on the same host, model, prompts, and
harness (8 cells; plan
[`superpowers/plans/2026-08-18-vulkan-mtp-comparison.md`](superpowers/plans/2026-08-18-vulkan-mtp-comparison.md),
tables [`results/benchmark.md`](results/benchmark.md)). All facts below are
**pin-local**.

- **Build** — the same llama.cpp pin as the HIP build (`4df29be4`), separate
  tree `third_party/llama.cpp/build-714-vk` via
  [`06-build-llama-vulkan.sh`](../scripts/06-build-llama-vulkan.sh)
  (`-DGGML_VULKAN=ON -DGGML_HIP=OFF`); the HIP `build-714` is untouched.
- **ICD identity** — Mesa RADV, no `VK_ICD_FILENAMES` forcing needed (the
  loader picks it on this host): `AMD Radeon Graphics (RADV GFX1151)`,
  `DRIVER_ID_MESA_RADV`, Mesa `25.2.8-0ubuntu0.24.04.2`, Vulkan 1.4.318
  device / 1.3.275 instance — recorded verbatim in
  [`configs/validated-stack.json`](../configs/validated-stack.json)
  (`llama_cpp_vulkan.icd_details`). Backend identity is part of the
  evidence; the whole ruling rests on ONE ICD.
- **Perf deltas (c1, ctx 131072, single-stream median)** — base: vulkan
  10.65 vs hip 10.14 tok/s (+5%: the backend alone is a small lever, not
  the AMD 24.5 anchor gap). MTP depth 1: vulkan 16.00 vs hip 13.00 tok/s
  — **+23% headline, MIXED-DEPTH** (see the caveat). The clean
  **same-depth** pairing is depth 4: vulkan mtp4 15.05 vs hip mtp4 12.76
  tok/s — **+18%** (both explicit `--spec-draft-n-max 4`, measured the
  same day).
- **Cross-depth caveat** — the historical hip mtp receipts (2026-08-17)
  ran the **implicit `--spec-draft-n-max` default 3** (discovered
  post-hoc; [`configs/validated-stack.json`](../configs/validated-stack.json)
  `llama_cpp_vulkan.mtp_depth.note`); every v0.1.2 cell passes its depth
  explicitly and records it in `server_flags`. So 16.00-vs-13.00 is
  depth-1-explicit vs depth-3-implicit, and the honest fixed-depth
  cross-backend number is the +18% depth-4 pairing (this caveat is also
  recorded in the vulkan/hip mtp4 verdict reasons).
- **MTP depth** — depth 4 never beats depth 1 on either backend (vulkan
  15.05 vs 16.00; hip 12.76 vs 13.00): the recommended variant stays
  `WITH_MTP=1` at depth 1 on both. Depth is configurable at the pin
  (`--spec-draft-n-max`, upstream default 3), NOT fixed by the checkpoint
  (row 5).
- **Greedy pit status** — the §6 HIP greedy-degradation pit does **NOT
  reproduce on Vulkan**: 6/6 vulkan cells anchor-clean (base/mtp/mtp4 ×
  c1/c4), and hip mtp4-c1 anchored clean the same day. The pit remains a
  hip-family (gfx1151/HIP) finding at this pin; Vulkan c8/c16 are
  unmeasured.
- **Quickstart status (project ruling 2026-08-18)** — `BACKEND=vulkan` is
  the **recommended opt-in** for best single-stream tok/s
  (`BACKEND=vulkan WITH_MTP=1`, 16.0 tok/s); the quickstart **default
  stays `hip`** (headline <25%, single-session Vulkan runtime, one ICD).
  Recorded per cell in [`configs/benchmark-verdicts.json`](../configs/benchmark-verdicts.json)
  (`metrics.reviewed_by` = `controller-2026-08-18`).
- **Unified rider (hip)** — `gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified`
  (the stock 4-slot unified default boot under 4 concurrent users): 6.7
  tok/s healthy-stream median / 5.0 aggregate (3-of-4 streams stopped
  within 8 tokens — early EOS, aggregate not comparable) vs split-mode c4
  7.5 / 9.4 — **unified-default-boot degrades interactivity on the
  8060S**; measured-with-caveat, no config change (single-stream use
  unaffected; light multi-user already steers to vLLM).

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
