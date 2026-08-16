# Spike C: official quantizations + KV-cache dtype levers — 2026-08-16

Probed 2026-08-16. Every quoted block below is verbatim probe output recorded
at the stated commit. Absence of matches is recorded as absence. Where a brief
probe URL 404'd due to upstream refactor, the moved location was found and
probed — both are recorded. Network-level failures get exactly one retry.
Revised 2026-08-16 (fix round 1): ROCM_ATTN head_size constraint made
explicit (custom paged attention never fires for this model on gfx1151 —
head_dim 256 vs the gate's `head_size == 128`), line citations re-verified
against the pinned SHA, ROCm backend-list function renamed to
`_get_backend_priorities`, Q4_K_M GiB rounding fixed.

Pins for this entire probe:

- vLLM `main` HEAD re-checked 2026-08-16 (this session):
  `4d2a68d64d9e05921ed5c4099146e768a92d71d5` 2026-08-16T11:09:23Z —
  **unchanged from Spike A's pin**, so all vLLM greps are at the same commit
  Spike A used. Every vLLM raw-file fetch below was made against this SHA.
- llama.cpp `master` HEAD re-checked 2026-08-16 (this session):
  `4df29be4f4c3673f428170fda944a5b19f743bb8` 2026-08-16T12:53:13Z — **moved**
  since Spike B's `3cb7ffb1a1f612d5e4a46244ae5a3c77ad934b70`
  (2026-08-16T12:12:55Z); all llama.cpp greps below are re-pinned to
  `4df29be`.

Network note (same as Spike B): `huggingface.co` is TCP-unreachable from this
host (curl exit 28 / timeout on both attempts for every repo). `hf-mirror.com`
is used as the disclosed alternate for HF truth: 200 = public repo exists,
401 `{"error":"Invalid username or password."}` = not publicly readable
(nonexistent or gated).

## Q1 quant variants today

### Official Qwen repos — the brief's four probes

Probe (brief's command, verbatim):

```bash
for repo in Qwen/Qwen3.8-27B-AWQ Qwen/Qwen3.8-27B-GPTQ-Int4 Qwen/Qwen3.8-27B-FP8 Qwen/Qwen3.8-27B-MXFP4; do
  for host in modelscope huggingface; do
    if [ "$host" = modelscope ]; then url="https://modelscope.cn/api/v1/models/$repo"; else url="https://huggingface.co/api/models/$repo"; fi
    printf '%s %s -> ' "$host" "$repo"; curl -s -o /dev/null -w '%{http_code}\n' "$url"
  done
done
```

Output (first attempt, 2026-08-16):

```
modelscope Qwen/Qwen3.8-27B-AWQ -> 404
huggingface Qwen/Qwen3.8-27B-AWQ -> 000
modelscope Qwen/Qwen3.8-27B-GPTQ-Int4 -> 404
huggingface Qwen/Qwen3.8-27B-GPTQ-Int4 -> 404
modelscope Qwen/Qwen3.8-27B-FP8 -> 200
huggingface Qwen/Qwen3.8-27B-FP8 -> 000
modelscope Qwen/Qwen3.8-27B-MXFP4 -> 404
huggingface Qwen/Qwen3.8-27B-MXFP4 -> 000
```

(The `huggingface` 000s are exit 28 — connection timeout. One retry, same
result: 000 for all four. See network note. hf-mirror alternate, same date:)

```
hf-mirror Qwen/Qwen3.8-27B-AWQ -> 401
hf-mirror Qwen/Qwen3.8-27B-GPTQ-Int4 -> 401
hf-mirror Qwen/Qwen3.8-27B-FP8 -> 200
hf-mirror Qwen/Qwen3.8-27B-MXFP4 -> 401
```

So of the brief's four official quant repos **only
`Qwen/Qwen3.8-27B-FP8` exists today** (ModelScope 200, hf-mirror 200);
AWQ / GPTQ-Int4 / MXFP4 are absent on both hubs (404 / 401).

### Qwen-org listing — is there any OTHER official quant?

ModelScope org-listing endpoints probed (both 404 — the org enumeration API
is not at these addresses; recorded as moved/undiscoverable, same situation
as Spike B's dolphin search endpoint):

```
https://modelscope.cn/api/v1/models/Qwen?PageSize=200&PageNumber=1 -> 404
https://modelscope.cn/api/v1/models?Owner=Qwen&PageSize=200        -> 404
```

Alternate: hf-mirror org listing, `GET /api/models?author=Qwen&search=Qwen3.8-27B&limit=100`
(2026-08-16) returns **exactly two repos**:

```
Qwen/Qwen3.8-27B    | createdAt: 2026-08-05T08:22:59.000Z | downloads: 267725
Qwen/Qwen3.8-27B-FP8 | createdAt: 2026-08-13T08:01:58.000Z | downloads: 352971
```

Conclusion: the official quant surface for this model is **base (BF16) +
FP8 only**. No official AWQ, GPTQ, MXFP4, INT8, or NVFP4 from the Qwen org.

### Sizes and formats (ModelScope file-list API, brief's Step-1 command shape)

The brief's example targeted `-AWQ` (nonexistent), so the identical command
was run against every 200-repo found. Total-safetensors probe:

```bash
curl -s "https://modelscope.cn/api/v1/models/<repo>/repo/files?Revision=master" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); fs=d['Data']['Files']; print('GiB:', round(sum(f['Size'] for f in fs if f['Path'].endswith('.safetensors'))/2**30,1))"
```

| repo id | ModelScope | hf-mirror | safetensors GiB | shards | `quantization_config.quant_method` |
|---|---|---|---|---|---|
| `Qwen/Qwen3.8-27B` (base, reference) | 200 | 200 | **51.7** | 18 | (none — BF16) |
| `Qwen/Qwen3.8-27B-FP8` (official) | 200 | 200 | **28.7** | 66 | `fp8` (`fmt: e4m3`, `activation_scheme: dynamic`) |
| `Qwen/Qwen3.8-27B-AWQ` | 404 | 401 | — | — | **absent** |
| `Qwen/Qwen3.8-27B-GPTQ-Int4` | 404 | 401 | — | — | **absent** |
| `Qwen/Qwen3.8-27B-MXFP4` | 404 | 401 | — | — | **absent** |
| `amd/Qwen3.8-27B-Quark-AWQ-INT4-W4A16` | 200 | 200 | **18.2** | 1 | `quark` (weight `dtype: int4`, `input_tensors: null` → W4A16) |
| `amd/Qwen3.8-27B-Quark-AWQ-MXFP4` | 200 | 200 | **18.4** | 1 | `quark` (weight `fp4`, group 32, `scale_format: e8m0`) |
| `cyankiwi/Qwen3.8-27B-AWQ-INT4` | 200 | 200 | **19.6** | 5 | `compressed-tensors` (pack-quantized W4A16) |
| `Inferact/Qwen3.8-27B-MXFP4` | 200 | 200 | **25.8** | 7 | `mxfp4` (llm-compressor style) |
| `unsloth/Qwen3.8-27B-FP8` | 200 | 200 | **28.7** | 66 | (mirror of official layout) |

Official FP8 detail (ModelScope `/repo/files?Revision=master`, 82 files
total): per-layer shards `layers-0.safetensors` … `layers-63.safetensors`
(~0.36 GiB each), `outside.safetensors` 5.59 GiB (embed/lm_head etc.),
`mtp.safetensors` 0.44 GiB — i.e. **the MTP draft block ships inside the
official FP8 checkpoint**. Its `config.json` `quantization_config`:
`quant_method: fp8`, `fmt: e4m3`, `activation_scheme: dynamic`, plus 882
`modules_to_not_convert` entries (the entire vision tower per-layer list).
unsloth's FP8 has the identical 66-shard / 82-file / 28.7 GiB structure.

All six quant repos above keep `architectures:
['Qwen3_5ForConditionalGeneration']`, `model_type: qwen3_5` (verified from
each `config.json`) — they ride the arch Spike A confirmed registered in
vLLM main.

How the community variants were found (2026-08-16, hf-mirror API, top 20
rows printed per query): `?search=Qwen3.8-27B&filter=awq` (18 rows, top:
`cyankiwi/Qwen3.8-27B-AWQ-INT4` 21,015 downloads,
`philbert440/Qwen3.8-27B-W4A16-AWQ` 10,587,
`barrydeen/Qwen3.8-27B-AWQ-4bit` 11,874,
`soyrsoyr/Qwen3.8-27B-W4A16-AWQ-GPTQ` 12,655),
`&filter=gptq` (top: `Vishva007/…-W4A16-AutoRound-GPTQ` 3,748,
`btbtyler09/…-GPTQ-4bit` 2,433), `&filter=fp8` (incl.
`unsloth/Qwen3.8-27B-FP8` 7,744), `?search=Qwen3.8-27B-MXFP4` (19 rows,
incl. `Inferact/Qwen3.8-27B-MXFP4` 2,310; most others are `-mlx` Apple
builds). Notable: the **`amd` org itself publishes two Quark exports of this
exact model** (the `Quark-AWQ-*` rows above) — consistent with the Instinct
Day-0 Quark/MXFP4 recipe Spike A recorded, now applied to the 27B dense
model.

### Q1 conclusions

- **Safetensors quant variants available today: yes, many — but only FP8 is
  official.** `Qwen/Qwen3.8-27B-FP8` (28.7 GiB, e4m3 dynamic, MTP included)
  is the sole official quant; AWQ/GPTQ/MXFP4 from the Qwen org do not exist
  (404/401 on both hubs, absence recorded).
- Community W4A16 int4 exists in three loadable formats at ~18–20 GiB:
  AMD Quark (`quant_method: quark`, W4A16 int4 — see Q2 loadability caveat),
  compressed-tensors (`cyankiwi`, 19.6 GiB), and GPTQ/AutoRound variants.
- All dates probed: 2026-08-16.

## Q2 vLLM quant/KV on ROCm

All greps at vLLM `4d2a68d64d9e05921ed5c4099146e768a92d71d5`
(2026-08-16T11:09:23Z, HEAD re-confirmed this session).

### Docs index moved (brief URL 404 → new location recorded)

Brief's command verbatim:

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm/main/docs/features/quantization/index.md | grep -n -i 'awq\|gptq\|mxfp4\|fp8' | head
```

Output: `curl: (22) The requested URL returned error: 404`. The tree API at
the pinned SHA (`git/trees/4d2a68d…?recursive=1`, 7452 paths) shows the
directory exists but the index is now `README.md`:

```
docs/features/quantization/README.md        (moved index)
docs/features/quantization/auto_awq.md
docs/features/quantization/gptqmodel.md
docs/features/quantization/quark.md
docs/features/quantization/quantized_kvcache.md
docs/features/quantization/llm_compressor/{README,fp8,int4,int8_w4a8,int8_w8a8}.md
```

Grep of the moved index (same pattern):

```
6:    To get started with quantization, see [LLM Compressor](llm_compressor/README.md), a library ... supports FP8, INT8, INT4, and other quantization formats.
10:- [AutoAWQ](auto_awq.md)
12:- [GPTQModel](gptqmodel.md)
15:    - [FP8 W8A8](llm_compressor/fp8.md)
21:- [AMD Quark](quark.md)
24:- [FP8 ViT Encoder Attention](fp8_vit_attn.md)
```

The index's hardware matrix (`docs/features/quantization/README.md`,
"Implementation | Volta | Turing | Ampere | Ada | Hopper | AMD GPU | …")
rows relevant to us, verbatim:

```
| AWQ                       | ❌    | ✅︎     | ✅︎     | ✅︎  | ✅︎     | ❌      | ✅︎        | ✅︎      | ❌      |
| GPTQ                      | ✅︎    | ✅︎     | ✅︎     | ✅︎  | ✅︎     | ❌      | ✅︎        | ✅︎      | ❌      |
| Marlin (GPTQ/AWQ/FP8/FP4) | ❌    | ✅︎*    | ✅︎     | ✅︎  | ✅︎     | ❌      | ❌        | ❌      | ❌      |
| llm-compressor FP8 (W8A8) | ❌    | ❌     | ❌     | ✅︎  | ✅︎     | ✅︎      | ❌        | ❌      | ❌      |
| GGUF                      | ✅︎    | ✅︎     | ✅︎     | ✅︎  | ✅︎     | ✅︎      | ❌        | ❌      | ❌      |
```

Docs say AWQ ❌ / GPTQ ❌ on "AMD GPU". **The code at the same commit says
otherwise** — see next receipt; the discrepancy is recorded, not resolved.

### ROCm platform code: what is actually enforced

`vllm/platforms/rocm.py` (lines 513–537 at the pin) — the list the platform
actually verifies against:

```python
    supported_quantization: list[str] = [
        "awq",
        "auto_awq",
        "awq_marlin",  # will be overwritten with awq
        "gptq",
        "auto_gptq",
        "fp8",
        "deepseek_v4_fp8",
        "compressed-tensors",
        "fbgemm_fp8",
        "inc",
        "quark",
        "mxfp4",
        "mxfp8",
        "torchao",
        ...
        "gpt_oss_mxfp4",
    ]
```

Enforcement path: `vllm/config/model.py:1286` calls
`current_platform.verify_quantization(self.quantization)`;
`vllm/platforms/interface.py:960-967`:

```python
    def verify_quantization(cls, quant: str) -> None:
        if cls.supported_quantization and quant not in cls.supported_quantization:
            raise ValueError(
                f"{quant} quantization is currently not supported in {cls.device_name}."
            )
```

So at `4d2a68d` the ROCm platform code accepts **awq, gptq, fp8,
compressed-tensors, quark, mxfp4** — every method found in Q1 — while the
docs matrix still carries AWQ/GPTQ ❌ for AMD. Both facts recorded; the
platform list is what raises at load time.

### gfx1151-specific capability predicates — the load-bearing caveat

`vllm/platforms/rocm.py` (verbatim, at the pin):

```python
_ON_RDNA4 = any(arch in _GCN_ARCH for arch in ["gfx1200", "gfx1201"])

    def supports_mx(cls) -> bool:
        return any(gfx in _GCN_ARCH for gfx in ["gfx95", "gfx1250"])

    def supports_fp8(cls) -> bool:
        return on_cdna() or on_rdna4()
```

(`on_cdna()` = gfx9\*/gfx1250.) Consequences for **gfx1151 (RDNA3.5)**:

- `supports_fp8()` → **False** (not CDNA, not gfx1200/1201). vLLM's own
  platform predicate excludes gfx1151 from native FP8 weight paths. Among
  the files probed (`fp8.py`, `fp8_utils.py`, scaled-mm chooser files) the
  exact call site that consumes this predicate was **not found** — recorded
  as absence; the predicate itself and the docs below are the evidence.
- `supports_mx()` → **False** (gfx95/gfx1250 only).

### Per-method reality on ROCm at this commit

- **FP8 weights (the official 28.7 GiB repo)** — accepted by the platform
  list, but on gfx1151: `supports_fp8()` is False, `is_fp8_fnuz()` is
  False ("gfx94" only), and the ROCm-native scaled-mm kernel
  (`vllm/model_executor/kernels/linear/scaled_mm/rocm.py`, op
  `rocm_per_tensor_float_w8a8_scaled_mm_impl`) presumes CDNA-class hipBLASLt
  FP8. No public report of FP8-weights-on-gfx1151 in vLLM was found. Treat
  the official FP8 checkpoint as **CDNA/RDNA4 territory, not a gfx1151
  lever**. (AMD's own Instinct Day-0 FP8→MXFP4 Quark recipe Spike A recorded
  is MI355X-oriented.)
- **AWQ / GPTQ / compressed-tensors int4 W4A16** — this is the viable
  weight-quant class on gfx1151. Kernel dispatch: both `auto_awq.py` and
  `auto_gptq.py` route through `choose_mp_linear_kernel()`
  (`vllm/model_executor/kernels/linear/__init__.py:774`), with Marlin
  explicitly CUDA-gated (`use_marlin = … and current_platform.is_cuda()`).
  ROCm preference order (`_POSSIBLE_KERNELS[PlatformEnum.ROCM]`, verbatim):

```python
    PlatformEnum.ROCM: [
        RDNA3W4A16LinearKernel,
        RDNAHybridW4A16LinearKernel,
        TritonW4A16LinearKernel,
        ConchLinearKernel,
        ExllamaLinearKernel,
    ],
```

  - `RDNA3W4A16LinearKernel` (`…/mixed_precision/rdna3_w4a16.py`) is
    **gfx1100-only**: `if not on_gfx1100(): return False, "RDNA3 W4A16
    kernel requires gfx1100"` — rejects gfx1151.
  - `RDNAHybridW4A16LinearKernel` (`…/mixed_precision/rdna_hybrid_w4a16.py`)
    **targets `_on_gfx1x()` = gfx11/gfx12 — includes gfx1151**. Header:
    "Hybrid W4A16 kernel: Triton for prefill, HIP skinny for decode";
    `SUPPORTED_QUANT_TYPES = [uint4b8, uint4]`,
    `SUPPORTED_GROUP_SIZES = [32, 64, 128]`, `has_g_idx` not supported.
    This is upstream's dedicated W4A16 answer for our exact GPU class.
  - `TritonW4A16LinearKernel` remains the portable fallback.
- **Quark (`quant_method: quark`)** — `amd/Qwen3.8-27B-Quark-AWQ-INT4-W4A16`
  (W4A16 int4, `input_tensors: null`, per-group 128 symmetric) matches **no
  scheme** in `vllm/model_executor/layers/quantization/quark/quark.py`'s
  `_get_scheme_from_config()` (schemes at this commit: W8A8 fp8
  per-tensor/per-block, W8A8 int8 static + dynamic-per-token, W4A8
  MXFP4+FP8, NVFP4, OCP-MX — all require quantized `input_tensors` except
  OCP-MX which requires fp4/e8m0 weights) → falls to:

```python
        raise NotImplementedError(
            "No quark compatible scheme was found. "
            f"Weight config: {weight_config}, "
            f"Input config: {input_config}"
        )
```

  i.e. **the AMD Quark W4A16-int4 repo is NOT loadable by vLLM main at
  `4d2a68d`**. `amd/Qwen3.8-27B-Quark-AWQ-MXFP4` (fp4 per-group 32, e8m0,
  dynamic fp4 inputs) DOES match `_is_w_ocp_mx_a_x` → `QuarkOCP_MX`
  (min capability 70). gfx1151's mapped capability
  (`_capability_from_gcn_arch`: gfx1151 → (11,5) → 115) clears every quark
  floor (89/75/70). But on gfx1151 `supports_mx()` is False, so execution is
  emulated — verbatim warning from `quark/schemes/quark_ocp_mx.py`:

```
The current platform does not support native MXFP4/MXFP6 computation.
Simulated weight dequantization and activation QDQ (quantize and dequantize)
will be used, with the linear layers computed in high precision.
```

  (Weights stay fp4-packed in memory; compute dequantizes per-op — the 18.4
  GiB footprint holds, the MX speedup does not.)
- **`mxfp4` / llm-compressor (`Inferact`)** — `mxfp4` is in the ROCm
  supported list; `mxfp4.py` carries ROCm branches for `on_gfx1250` only;
  non-MX platforms use the emulation kernels
  (`kernels/linear/mxfp4/emulation.py`) with the same high-precision
  compute caveat.
- **Quark KV scales**: `QuarkKVCacheMethod.validate_kv_cache_config` accepts
  only `dtype=fp8_e4m3, qscheme=per_tensor` KV configs; both AMD repos ship
  `kv_cache_group: []` (no KV scales) — irrelevant for us.

### KV-cache dtype on ROCm — config, docs, kernels

`vllm/config/cache.py` (exists at the pin; brief's grep works):

```
19:CacheDType = Literal[
23:    "fp8",
24:    "fp8_e4m3",
25:    "fp8_e5m2",
26:    "fp8_inc",
27:    "fp8_ds_mla",
34:    "fp8_per_token_head",
38:MambaDType = Literal["auto", "float32", "float16", "bfloat16"]
77:    cache_dtype: CacheDType = "auto"
79:    CUDA 11.8+ supports fp8 (=fp8_e4m3) and fp8_e5m2. ROCm (AMD GPU) supports
```

Full docstring (lines 77–87): "Data type for kv cache storage. If "auto",
will use model data type. **CUDA 11.8+ supports fp8 (=fp8_e4m3) and
fp8_e5m2. ROCm (AMD GPU) supports fp8 (=fp8_e4m3).** Intel Gaudi (HPU)
supports fp8 (using fp8_inc)." — i.e. config-level: **ROCm supports fp8 KV
(e4m3 only); e5m2 is CUDA-only.**

Docs receipt, `docs/features/quantization/quantized_kvcache.md` (lines
40–41): `kv_cache_dtype="fp8_e4m3"`: Supported on CUDA 11.8+ **and ROCm
(AMD GPUs)**; `fp8_e5m2`: Supported on CUDA 11.8+ (CUDA-only, recorded).
CLI surface: `--kv-cache-dtype` and `--kv-cache-dtype-skip-layers`
(`vllm/engine/arg_utils.py:1213/1228` at the pin).

Kernel-level on gfx1151 (RDNA), at the pin:

- The ROCm custom paged-attention gate
  (`use_rocm_custom_paged_attention`, `rocm.py:386-422`) — the `_ON_GFX1X`
  branch (lines 410–424) requires **`head_size == 128`** (line 415) AND
  `kv_cache_dtype == "auto"` (line 420), plus block_size 16, gqa_ratio
  3–16, max_seq_len ≤ 128K. **Qwen3.8-27B's `head_dim` is 256, so
  `use_rocm_custom_paged_attention` returns False for this model on gfx1151
  regardless of KV dtype** — the head-size gate fails before the dtype gate
  is even reached. Custom paged attention therefore never fires for this
  model on gfx1151; backend selection falls through the ROCm priorities
  (`_get_backend_priorities`, `rocm.py:459-495`: ROCM_ATTN, AITER variants,
  **TRITON_ATTN**, TURBOQUANT) to Triton attention either way.
- `vllm/v1/attention/backends/triton_attn.py:296-306` —
  `supported_kv_cache_dtypes` includes `fp8`, `fp8_e4m3`, `fp8_e5m2`
  unconditionally. Its SM89+ fp8 guard (lines 540–548: "FP8 KV cache is not
  supported by the Triton attention backend on {dev} … requires SM89+") is
  inside `if current_platform.is_cuda():` — **it does not fire on ROCm**; no
  ROCm-side guard exists in this backend.
- AITER is no help on gfx1151: `is_rdna_aiter_enabled()` is RDNA4/gfx12-only
  (`vllm/_aiter_ops.py:1803-1807`).

So: **vLLM declares fp8 KV cache supported on ROCm, and on gfx1151 it routes
through the Triton attention backend with no explicit guard — but there is
no public gfx1151 runtime validation of that combination in-tree.**

Web receipts (searched 2026-08-16):

- vLLM blog, 2026-04-22, "The State of FP8 KV-Cache and Attention
  Quantization in vLLM":
  https://vllm-project.github.io/2026/04/22/fp8-kvcache.html — documents
  `--kv-cache-dtype fp8` quantizing KV storage and attention compute.
- AMD ROCm blog "Enhancing vLLM Inference on AMD GPUs":
  https://rocm.blogs.amd.com/artificial-intelligence/vllm-optimize/README.html
  — "With ROCm 6.2+, KV cache can be stored in FP8 in vLLM, significantly
  reducing memory footprint."
- vLLM issue **#13147** (fetched via API 2026-08-16):
  `[Bug]: Enabling fp8 KV cache quantization and prefix caching at the same
  time on Radeon (W7900/RDNA3) crashes the process` — state **closed
  (completed) 2025-02-18**, created 2025-02-12, repro used
  `--kv-cache-dtype fp8`. Evidence the fp8-KV path was exercised and fixed
  on RDNA3-class hardware historically; not gfx1151-specific.
- Community gfx1151 vLLM builds (context for "runs, but source-built"):
  https://community.frame.work/t/how-to-compiling-vllm-from-source-on-strix-halo/77241
  (`ROCM_ARCH=gfx1151` recipe),
  https://kyuz0.github.io/amd-strix-halo-vllm-toolboxes/ (Strix Halo vLLM
  benchmarks),
  https://lemonade-server.ai/docs/guide/configuration/vllm/ ("validated on
  gfx1151 (Strix Halo)" as experimental backend),
  https://www.reddit.com/r/ROCm/comments/1rur2ji/ (TheRock full stack;
  notes the shuffle KV cache layout doesn't work on gfx1151).

### Q2 conclusions

- Method acceptance on ROCm (`supported_quantization`): awq, gptq, fp8,
  compressed-tensors, quark, mxfp4 all present — contradicted by the docs
  matrix (AWQ/GPTQ ❌ AMD); the platform list is the enforced one.
- On **gfx1151 specifically**: W4A16 int4 (AWQ/GPTQ/compressed-tensors) is
  the supported weight-quant class, executing via
  `RDNAHybridW4A16LinearKernel` (gfx11/12-targeted, HIP skinny decode +
  Triton prefill) or TritonW4A16 fallback; **fp8 weights and MX compute are
  excluded by vLLM's own predicates** (`supports_fp8`/`supports_mx` =
  CDNA/RDNA4 only); **Quark W4A16-int4 checkpoints are unloadable** at this
  commit (no matching scheme → NotImplementedError); Quark MXFP4 loads but
  computes via high-precision emulation.
- KV cache: `--kv-cache-dtype fp8` (e4m3) is a supported lever on ROCm per
  config + docs; on gfx1151 **custom paged attention never fires for this
  model** (`use_rocm_custom_paged_attention`'s `_ON_GFX1X` branch requires
  `head_size == 128` at `rocm.py:415`; the model's `head_dim` is 256 —
  False regardless of KV dtype), so the KV-dtype choice routes between
  attention paths that are Triton-backed either way, with no in-tree guard
  and no public gfx1151 validation — an experiment with a bf16 fallback, not
  a given.

## Q3 llama.cpp KV quant

Greps pinned to llama.cpp master `4df29be4f4c3673f428170fda944a5b19f743bb8`
(2026-08-16T12:53:13Z). Brief's command re-pinned from `master` to the SHA
(HEAD moved past Spike B's `3cb7ffb` the same day):

```bash
curl -fsSL "https://raw.githubusercontent.com/ggml-org/llama.cpp/4df29be…/common/arg.cpp" \
  | grep -n -i 'cache-type\|f8\|q8_0' | head -10
```

```
309:    GGML_TYPE_Q8_0,
2427:        {"-ctk", "--cache-type-k"}, "TYPE",
2440:        {"-ctv", "--cache-type-v"}, "TYPE",
4023:        {"--spec-draft-type-k", "-ctkd", "--cache-type-k-draft"}, "TYPE",
```

(plus UTF-8 `f8` substring false-positives at lines 1250–1283). The complete
allowed cache-type list, `common/arg.cpp:305-314` verbatim:

```cpp
const std::vector<ggml_type> kv_cache_types = {
    GGML_TYPE_F32,
    GGML_TYPE_F16,
    GGML_TYPE_BF16,
    GGML_TYPE_Q8_0,
    GGML_TYPE_Q4_0,
    GGML_TYPE_Q4_1,
    GGML_TYPE_IQ4_NL,
    GGML_TYPE_Q5_0,
    GGML_TYPE_Q5_1,
};
```

- **`f8` is NOT an available cache type** — absence recorded twice: it is
  not in `kv_cache_types`, and `ggml/include/ggml.h` at this SHA contains
  **zero** occurrences of the string `F8` (`grep -c 'F8'` → `0`; no
  `GGML_TYPE_F8` exists). The brief's `q8_0|f8` lever is therefore
  **`q8_0` (and Q4_0/Q4_1/Q5_0/Q5_1/IQ4_NL/BF16) today; f8 does not exist
  upstream**.
- Option help text (`arg.cpp:2427-2437`): `-ctk/--cache-type-k TYPE` /
  `-ctv/--cache-type-v TYPE`, "allowed values: f32, f16, bf16, q8_0, q4_0,
  q4_1, iq4_nl, q5_0, q5_1" (default f16), env `LLAMA_ARG_CACHE_TYPE_K/V`;
  a separate `--cache-type-k-draft` exists for speculative drafts
  (line 4023).
- Constraints, `src/llama-context.cpp` at the pin — verbatim:

```cpp
        if (!cparams.flash_attn) {
            if (ggml_is_quantized(params.type_v)) {
                throw std::runtime_error("quantized V cache was requested, but this requires Flash Attention");
            }
        }
```

  and at init (lines 3595–3620): quantized V cache auto-enables flash attn
  (`enabling flash_attn since it is required for quantized V cache`) or
  hard-errors if FA was explicitly disabled; with FA on, quantized K/V
  require `n_embd_head_k/v % blck_size == 0` per layer — **Qwen3.8-27B's
  head_dim 256 % 32 (q8_0 block) == 0 passes**.
- Hybrid-arch note (from Spike B's receipts, unchanged): only the 16
  full-attention layers carry KV for `qwen35`; GDN layers hold small SSM
  state, and the MTP draft context uses a plain KV cache (1 layer).

Web receipts for HIP/RDMA caveats (searched 2026-08-16):

- llama.cpp issue **#23873** `[Misc. bug: ROCm backend leaks VRAM with
  quantized KV cache]` — repro `--cache-type-k q8_0 --cache-type-v q8_0`;
  state **closed (completed) 2026-06-12** (created 2026-05-29, fetched via
  API 2026-08-16). The known HIP-specific q8_0-KV defect class, already
  fixed before our probe commit.
- Discussion #21526 "TurboQuant KV Cache Compression — Full HIP/ROCm
  support" (fork tested on gfx1100/RDNA3):
  https://github.com/ggml-org/llama.cpp/discussions/21526
- AMD official llama.cpp-on-ROCm install guide:
  https://rocm.docs.amd.com/projects/llama-cpp/en/docs-25.09/install/llama-cpp-install.html
- Community guidance: `--flash-attn` + `-ctk/-ctv q8_0` recommended
  generically (https://xhinker.medium.com/the-5-llama-cpp-parameters-that-actually-matter-9f2c38b53755);
  RDNA3 tuning thread https://www.reddit.com/r/ROCm/comments/1vo9kxi/llamacpp_boosts_for_rdna3/.

### Q3 conclusions

**llama.cpp: KV quant is a first-class lever** — `-ctk/-ctv q8_0` (and
q4_0/q4_1/q5_0/q5_1/iq4_nl/bf16) with FA required for quantized V (head_dim
256 divides all block sizes). **`f8` does not exist** as a cache type at
master `4df29be` (absence recorded). The historical HIP VRAM-leak with
q8_0 KV (#23873) was closed/fixed 2026-06-12; no open HIP-specific KV-quant
blocker was found, but also no gfx1151-specific validation — same
experiment-with-fallback posture as vLLM.

## Impact — unified-memory math (validated 80 GiB pool; 32 GiB minimum-SKU envelope) and the benchmark sweep

### Closed-form KV bytes (for METHODOLOGY.md to lift directly)

Geometry from `Qwen/Qwen3.8-27B` `config.json` (ModelScope, fetched
2026-08-16): `num_hidden_layers = 64`, `full_attention_interval = 4` →
**16 full-attention layers** (the other 48 are GDN linear-attention layers
with small fixed state, not per-token KV); `num_key_value_heads = 4`;
`head_dim = 256`; `max_position_embeddings = 262144`.

```
KV_bytes(ctx) = ctx × 2 (K+V) × 16 layers × 4 kv-heads × 256 head_dim × bytes/elem
             = ctx × 32,768 × bytes/elem
```

Per-token, per-dtype (q8_0 = 34 B per 32 elems; q4_0 = 18 B per 32 elems):

| KV dtype | B/elem | B/token | @ 8,192 ctx | @ 131,072 | @ 262,144 (max) |
|---|---|---|---|---|---|
| bf16/f16 (default) | 2 | 65,536 | 0.50 GiB | 8.00 GiB | **16.00 GiB** |
| fp8 e4m3 (vLLM only) | 1 | 32,768 | 0.25 GiB | 4.00 GiB | **8.00 GiB** |
| q8_0 (llama.cpp) | 1.0625 | 34,816 | 0.27 GiB | 4.25 GiB | **8.50 GiB** |
| q4_0 (llama.cpp) | 0.5625 | 18,432 | 0.14 GiB | 2.25 GiB | **4.50 GiB** |

Check arithmetic: 262,144 tokens × 32,768 elems/token = 8,589,934,592
elems; × 2 B (bf16) = 17,179,869,184 B = 16.00 GiB exactly; fp8 halves it
to 8.00 GiB; q8_0 = 16 × (1.0625/2) = 8.50 GiB. MTP draft adds one extra
dense-attn block while speculating: 2 × 1 × 4 × 256 = 2,048 elems/token =
4 KiB/token bf16 (1/16 of main KV) — negligible-to-minor.

### Realistic combos on the validated host (80 GiB visible pool, c = 1 sequence)

The validated Strix Halo host (AMD Ryzen AI MAX+ PRO 395, 94 GiB system
RAM) exposes a **GPU-visible coarse-grained GLOBAL pool of 80 GiB** for
gfx1151 (`rocminfo`, measured 2026-08-16 — the same envelope muse-rocm
documented for this platform). Restating the budget for that pool (bf16
KV @ 262K = 16.0 GiB from the closed form above; weight sizes per Q1 and
Spike B — exact-byte GiB, see the note below the next table):

| weights (repo) | size | KV @ 262K | total | fits 80 GiB pool? |
|---|---|---|---|---|
| GGUF UD-Q4_K_XL (unsloth) | 16.69 GiB | bf16 16.0 GiB | ~32.7 GiB | **yes — comfortably** |
| vLLM `cyankiwi` AWQ-INT4 W4A16 | 19.6 GiB | bf16 16.0 GiB | ~35.6 GiB | **yes** |
| GGUF Q6_K (unsloth) | 21.31 GiB | bf16 16.0 GiB | ~37.3 GiB | **yes** |
| BF16 weights (base repo) | 51.7 GiB | bf16 16.0 GiB | ~67.7 GiB | **yes** |

Reading: **on the validated 80 GiB pool, KV quantization is NOT a
capacity requirement even at 262K** — UD-Q4_K_XL + bf16 KV ≈ 32.7 GiB
fits with ~47 GiB to spare, and even the 51.7 GiB BF16 weights fit the
visible pool (51.7 + 16.0 = 67.7 GiB, ~12 GiB to spare). The binding
constraint is performance, not capacity: the
pool is GTT-backed (shared system memory), so pressure past fast memory
means a **silent GTT spill** — throughput collapse with no load-time
error, the llama.cpp #26432 class Spike B recorded — and the remaining
headroom must absorb activations, long-context scratch, the vision
tower, and the OS. On this host KV quant at 262K is a throughput/quality
lever, not a gate.

### Minimum-SKU envelope — realistic combos on a 32 GiB-class pool, e.g. R9700/32 GB (c = 1 sequence)

Budget: 32 GiB total minus OS/carve-out (~2 GiB) minus activations +
fragmentation (~1.5–2 GiB at long ctx) → ~28 GiB of headroom for
weights + KV. Weight sizes from Q1 (GiB) and Spike B (GB as reported by
publisher APIs: UD-Q4_K_XL 17.92 GB = 16.69 GiB exact-byte
(17,923,394,224 B), Q4_K_M 17.11 GB = 15.93 GiB, Q6_K 22.88 GB =
21.31 GiB exact-byte (22,884,408,288 B)):

| weights (repo) | size | KV @ 262K | total | fits 32 GiB? |
|---|---|---|---|---|
| vLLM `cyankiwi` AWQ-INT4 W4A16 | 19.6 GiB | bf16 16.0 GiB | 35.6 GiB | **no** |
| vLLM `cyankiwi` AWQ-INT4 W4A16 | 19.6 GiB | **fp8 8.0 GiB** | 27.6 GiB | **yes (tight)** |
| vLLM official FP8 | 28.7 GiB | any | ≥ 29 GiB | no (and `supports_fp8`=False on gfx1151) |
| GGUF UD-Q4_K_XL (unsloth) | 16.69 GiB | bf16 16.0 GiB | 32.7 GiB | borderline-no |
| GGUF UD-Q4_K_XL (unsloth) | 16.69 GiB | **q8_0 8.5 GiB** | 25.2 GiB | **yes** |
| GGUF Q6_K (unsloth) | 21.31 GiB | q8_0 @128K 4.25 GiB | 25.6 GiB | **yes** |
| c=1 short ctx (8K): any Q4/Q5/Q6 weights | 16.7–21.3 GiB | 0.14–0.5 GiB | ≤ 22 GiB | **yes, roomy** |

Reading: **at max context on a 32 GiB-class pool, KV quantization is
mandatory** — bf16 KV (16 GiB) plus even the smallest W4 weights overflows; fp8
(vLLM) or q8_0 (llama.cpp) KV at ~8–8.5 GiB is what makes 262K reachable
at all. At short context everything down to Q6 fits comfortably.

> **Erratum 2026-08-16 (final whole-branch review).** This Impact
> section originally framed "32 GiB UMA" as the validated host's memory
> budget and concluded KV quant was mandatory at 262K. That 32 GiB
> framing was the design spec's error, not a measurement: the validated
> host's gfx1151 GPU-visible pool measures **80 GiB** (`rocminfo`, and
> `configs/validated-stack.json` `gpu_visible_pool_gib`), on which bf16
> KV @ 262K fits — see the corrected budget above. The 32 GiB table
> above is retained, relabeled as the **minimum-SKU envelope** (e.g.
> R9700/32 GB), where the mandatory-KV-quant conclusion does hold. No
> probe data elsewhere in this receipt changed; in the same pass two
> weight sizes were corrected to exact-byte GiB (UD-Q4_K_XL
> 16.68→16.69, Q6_K 21.30→21.31).

### What the follow-up benchmark plan must sweep

1. **GGUF path (AMD's validated route)**: UD-Q4_K_XL and Q4_K_M ×
   KV f16 vs `-ctk/-ctv q8_0` (FA on) × ctx 8K/128K/262K — expect ~8 GiB
   saved at 262K; watch correctness against the f16 baseline.
2. **vLLM path**: `cyankiwi/Qwen3.8-27B-AWQ-INT4` (compressed-tensors W4A16,
   the one int4 class with an upstream gfx1151 kernel — RDNAHybrid) ×
   `--kv-cache-dtype auto` vs `fp8` × ctx 128K/262K; **expect Triton
   attention under both settings — ROCM_ATTN (custom paged attention) never
   fires for this model on gfx1151 because its `_ON_GFX1X` gate requires
   `head_size == 128` (`rocm.py:415`) while the model's `head_dim` is 256
   (the `kv_cache_dtype == "auto"` condition at line 420 is moot)** — so
   record which Triton path is selected rather than hunting for a paged-attn
   cell, and watch the #13147-class fp8+prefix-caching interaction.
3. **Do not schedule**: official FP8 weights on gfx1151
   (`supports_fp8()=False` — CDNA/RDNA4 lever), `amd` Quark W4A16-int4
   (unloadable: no quark scheme at `4d2a68d`); Quark-MXFP4 only as a
   low-priority emulation datapoint (18.4 GiB, high-precision compute).
4. Every cell records tok/s vs AMD's Day-0 Vulkan anchors (Spike A: 39.9
   tok/s AI Max+ 395 no-MTP, 51.8 tok/s R9700) so a KV-quant-induced
   throughput loss is separable from backend differences.

All probes 2026-08-16; vLLM at `4d2a68d64d9e05921ed5c4099146e768a92d71d5`,
llama.cpp at `4df29be4f4c3673f428170fda944a5b19f743bb8`.
