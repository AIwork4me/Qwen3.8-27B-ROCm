# Spike B: llama.cpp / GGUF support for Qwen3.8-27B — 2026-08-16

Probed 2026-08-16. Every quoted block below is verbatim probe output recorded
against the pinned commit. Absence of matches is recorded as absence. Where a
brief probe URL 404'd due to upstream refactor, the moved location was found
and probed — both are recorded. Network-level failures (timeouts, unresolvable
hosts) are recorded as such, one retry each.

llama.cpp `master` HEAD for this entire probe (all raw-file fetches re-pinned
to this SHA):

```bash
curl -s "https://api.github.com/repos/ggml-org/llama.cpp/commits?per_page=1" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date'])"
```

```
3cb7ffb1a1f612d5e4a46244ae5a3c77ad934a70 2026-08-16T12:12:55Z
```

## Q1: llama.cpp arch support

- Probe (brief's command, verbatim):

```bash
for f in src/llama-arch.cpp src/llama-model.cpp tools/mqmd/mqmd.cpp; do
  echo "== $f =="
  curl -fsSL "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/$f" \
    | grep -n -i 'qwen3_5\|qwen3_next\|qwen3n' | head -10 || true
done
```

- Evidence: `tools/mqmd/mqmd.cpp` → **HTTP 404** (fetch failed, `curl: (22) The
  requested URL returned error: 404`) — file absent at this commit. The other
  two files fetched, and the pattern `qwen3_5`/`qwen3n` matched **nothing**;
  only `qwen3next` appears. The registered arch NAME is neither `qwen3_5` nor
  `qwen3n` — it is **`qwen35`** (plus `qwen35moe`). Pinned-SHA grep of
  `src/llama-arch.cpp`:

```
== llama-arch.cpp grep -n -i 'qwen3_5\|qwen3_next\|qwen3n' ==
38:    { LLM_ARCH_QWEN3NEXT,        "qwen3next"        },
997:        case LLM_ARCH_QWEN3NEXT:
```

  Full Qwen arch-name table (`sed -n '30,45p' src/llama-arch.cpp`, pinned
  `3cb7ffb`):

```
    { LLM_ARCH_QWEN,             "qwen"             },
    { LLM_ARCH_QWEN2,            "qwen2"            },
    { LLM_ARCH_QWEN2MOE,         "qwen2moe"         },
    { LLM_ARCH_QWEN2VL,          "qwen2vl"          },
    { LLM_ARCH_QWEN3,            "qwen3"            },
    { LLM_ARCH_QWEN3MOE,         "qwen3moe"         },
    { LLM_ARCH_QWEN3NEXT,        "qwen3next"        },
    { LLM_ARCH_QWEN3VL,          "qwen3vl"          },
    { LLM_ARCH_QWEN3VLMOE,       "qwen3vlmoe"       },
    { LLM_ARCH_QWEN35,           "qwen35"           },
    { LLM_ARCH_QWEN35MOE,        "qwen35moe"        },
```

- Layout drift receipt: `llama_model_qwen35` implementations live in a new
  `src/models/` split (this is why the probe's `llama-model.cpp` fetch is only
  3004 lines — per-arch code moved out). `src/models` listing at the pinned
  SHA includes `qwen35.cpp` (28474 bytes) and `qwen35moe.cpp` (33068 bytes),
  alongside `qwen3next.cpp`, `qwen3vl.cpp`, `delta-net-base.cpp`. Factory
  dispatch in `src/llama-model.cpp` (lines 309–312, pinned):

```
        case LLM_ARCH_QWEN3NEXT:
            return new llama_model_qwen3next(params);
        case LLM_ARCH_QWEN35:
            return new llama_model_qwen35(params);
        case LLM_ARCH_QWEN35MOE:
            return new llama_model_qwen35moe(params);
```

- Evidence — linear attention (GDN) handled: `src/models/qwen35.cpp` lines
  6–19 (pinned `3cb7ffb`) load the gated-delta-net hparams and the NextN/MTP
  block:

```
    // Load linear attention (gated delta net) parameters
    ml.get_key(LLM_KV_SSM_CONV_KERNEL,    hparams.ssm_d_conv);
    ml.get_key(LLM_KV_SSM_INNER_SIZE,     hparams.ssm_d_inner);
    ml.get_key(LLM_KV_SSM_STATE_SIZE,     hparams.ssm_d_state);
    ml.get_key(LLM_KV_SSM_TIME_STEP_RANK, hparams.ssm_dt_rank);
    ml.get_key(LLM_KV_SSM_GROUP_COUNT,    hparams.ssm_n_group);

    // NextN/MTP (Qwen3.5/3.6): extra decoder block appended beyond the main stack
    ml.get_key(LLM_KV_NEXTN_PREDICT_LAYERS, hparams.n_layer_nextn, false);
```

  plus a linear-attention graph builder
  (`llama_model_qwen35::graph::build_layer_attn_linear`, line 339) and fused
  GDN control flags (line 441: `if (num_k_heads != num_v_heads && (!cparams.fused_gdn_ar || !cparams.fused_gdn_ch))`).
  The arch is registered as hybrid in `src/llama-arch.cpp`
  (`llm_arch_is_hybrid`, lines 995–1001: `case LLM_ARCH_QWEN35:` /
  `case LLM_ARCH_QWEN35MOE:` return true), and `llm_arch_supports_rs_rollback`
  (lines 1022–1025) lists both. `src/llama-model.cpp` lines 529–560 contain
  dedicated tensor-parallel split segmentation for the GDN qkv/conv1d tensors
  with an explicit Qwen 3.5 note:

```
            // both Qwen 3 Next and Qwen 3.5 support n_v_heads > n_k_heads but the broadcasting pattern is different:
            //   - Qwen 3 Next: [k0_v0, k0_v1, k1_v2, k1_v3] (this is the default split pattern)
            //   - Qwen 3.5:    [k0_v0, k1_v1, k0_v2, k1_v3] (needs segmenting of V on the scale of K to get the correct pattern)
```

  The 27B size is explicitly enumerated in `qwen35.cpp` lines 34–37:
  `case 64: type = LLM_TYPE_27B; break;`. Cross-check against the actual
  checkpoint (ModelScope `Qwen/Qwen3.8-27B` `config.json`, fetched this probe):
  `architectures: ['Qwen3_5ForConditionalGeneration']`, `model_type:
  qwen3_5`, `text_config.num_hidden_layers = 64`,
  `text_config.full_attention_interval = 4`,
  `text_config.linear_num_key_heads = 16`, `text_config.linear_num_value_heads
  = 48` (v_per_k = 3), `text_config.linear_key_head_dim = 128`,
  `text_config.linear_conv_kernel_dim = 4` — every field consumed by the
  qwen35 loader.

- Evidence — MTP handled end-to-end (load, graph, public API, spec-decode):

  - Tensor loading: `qwen35.cpp` lines 97–126 define `load_block_mtp` with
    `LLM_TENSOR_NEXTN_EH_PROJ / ENORM / HNORM / EMBED_TOKENS /
    SHARED_HEAD_HEAD / SHARED_HEAD_NORM`.
  - Draft graph: `qwen35.cpp` line 488 onward —
    `// LLM_GRAPH_TYPE_DECODER_MTP draft head for Qwen3.5/3.6 dense series`,
    with `GGML_ASSERT(hparams.n_layer_nextn == 1 && "QWEN35 MTP currently only
    supports a single MTP block");` (line 492). The checkpoint has
    `text_config.mtp_num_hidden_layers = 1` — match.
  - Public API: `include/llama.h` (moved from `src/llama.h`, which now 404s —
    both recorded) lines 217–219 and 341:

```
    enum llama_context_type {
        LLAMA_CONTEXT_TYPE_DEFAULT = 0,
        LLAMA_CONTEXT_TYPE_MTP     = 1,
```
```
        bool load_mtp;        // whether to load MTP layers
```

  - Spec-decode driver: `common/speculative.cpp` line 36 registers
    `{"draft-mtp", COMMON_SPECULATIVE_TYPE_DRAFT_MTP}`; line 1274 defines
    `common_speculative_impl_draft_mtp`; lines 1286–1289 enumerate modes
    including `// neither (qwen35 / qwen35moe): a single trained MTP head.`
    `common/arg.cpp` plans/auto-downloads an MTP sidecar
    (`plan_spec.mtp`, `download_mtp`). `tools/server/server.cpp` at this
    commit contains **zero** matches for `mtp|speculative|draft` (grep empty)
    — the draft-mtp path is exercised via `examples/speculative*`, not a
    stock `llama-server` flag, at `3cb7ffb`.
  - Hybrid/MTP KV-cache interaction: `src/llama-model.cpp` lines 2262–2266 —
    `const bool mtp_on_hybrid_qwen = params.ctx_type == LLAMA_CONTEXT_TYPE_MTP
    && (arch == LLM_ARCH_QWEN3NEXT || arch == LLM_ARCH_QWEN35 || arch ==
    LLM_ARCH_QWEN35MOE);` with the comment "The MTP head is dense-attention
    only on hybrid Qwen3-Next/3.5/3.6, so use a plain attention KV cache for
    the MTP context instead of the hybrid wrapper."

- Evidence — vision (mmproj) handled: the vision tower converts via
  `conversion/qwen3vl.py` line 16 (pinned `3cb7ffb`):

```python
@ModelBase.register("Qwen3VLForConditionalGeneration", "Qwen3VLMoeForConditionalGeneration", "Qwen3_5ForConditionalGeneration", "Qwen3_5MoeForConditionalGeneration")
class Qwen3VLVisionModel(MmprojModel):
```

  writing `self.gguf_writer.add_clip_projector_type(gguf.VisionProjectorType.QWEN3VL)`
  (line 46) — i.e. the Qwen3.5/3.8 vision projector rides the existing
  Qwen3-VL clip runtime in `tools/mtmd/`. Practical confirmation: all three
  third-party GGUF repos probed in Q2 ship `mmproj-*.gguf` files (~0.93 GB
  each). The runtime clip code itself has no `qwen35` string
  (`grep -i 'qwen35\|qwen3_5' tools/mtmd/clip-impl.h` → empty) because the
  projector is keyed by `VisionProjectorType.QWEN3VL`, not by arch string.

- Evidence — gguf-py constants (`gguf-py/gguf/constants.py`, pinned):

```
487:    QWEN35           = auto()
488:    QWEN35MOE        = auto()
1202:    MODEL_ARCH.QWEN35:           "qwen35",
1203:    MODEL_ARCH.QWEN35MOE:        "qwen35moe",
2699:    MODEL_ARCH.QWEN35: [
```

  The `MODEL_ARCH.QWEN35` tensor list (lines 2699–2727) includes
  `MODEL_TENSOR.SSM_A / SSM_CONV1D / SSM_DT / SSM_NORM / SSM_BETA / SSM_ALPHA
  / SSM_OUT` and, under the comment `# NextN/MTP tensors - preserved but
  unused`, all six `MODEL_TENSOR.NEXTN_*` entries.

- Maturity receipt
  (`https://api.github.com/repos/ggml-org/llama.cpp/commits?path=src/models/qwen35.cpp`):
  the file has 27 commits; oldest and latest:

```
oldest: fc0fe4004985 2026-02-10T16:00:26Z - models : support qwen3.5 series (#19468)
latest: 82dbc4f017a7b005f993ac2e7af9c048ad686c04 2026-07-31T12:57:02Z - llama : load MTP tensors only if they are really used (#26296)
```

  Six months of continuous maintenance.

- Conclusion: **supported** — llama.cpp master at `3cb7ffb` (2026-08-16)
  registers the architecture under the name **`qwen35`** (dense) /
  **`qwen35moe`** (not `qwen3_5`, not `qwen3n`), with a dedicated model
  implementation covering gated-delta-net linear-attention layers (hybrid
  memory, fused GDN kernels, TP split segmentation), a single-block MTP draft
  head (load + graph + `LLAMA_CONTEXT_TYPE_MTP` API + draft-mtp speculative
  driver), and vision via an mmproj that rides the Qwen3-VL projector type.
  The 27B size is an enumerated model type.
- SHA/date probed: `3cb7ffb1a1f612d5e4a46244ae5a3c77ad934a70`
  2026-08-16T12:12:55Z.

## Q2: existing GGUF quants

- Probe (brief's command shape, ModelScope + HF; probed 2026-08-16). NOTE on
  network: `huggingface.co` is unreachable from this host at TCP level (curl
  exit 000; verbose shows DNS resolving to unrelated addresses
  `104.244.43.128` / `2a03:2880:f112:83:face:b00c:0:25de`, connection timed
  out) — recorded as a network limitation after one retry. `hf-mirror.com`
  (a public HF API mirror) was used as the alternate route for HF-truth; a
  200 there mirrors an existing public HF repo, a 401 `{"error":"Invalid
  username or password."}` mirrors HF's response for a repo that is not
  publicly readable (nonexistent or gated).

```bash
for repo in Qwen/Qwen3.8-27B-GGUF Qwen/Qwen3.8-27B-MXFP4-GGUF Qwen/Qwen3.8-27B-Instruct-GGUF unsloth/Qwen3.8-27B-GGUF bartowski/Qwen3.8-27B-GGUF lmstudio-community/Qwen3.8-27B-GGUF; do
  ms=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "https://modelscope.cn/api/v1/models/$repo")
  hf=$(curl -s -o /dev/null -w '%{http_code}' --max-time 35 "https://hf-mirror.com/api/models/$repo")
  echo "$repo  ModelScope=$ms  hf-mirror=$hf"
done
```

```
Qwen/Qwen3.8-27B-GGUF           ModelScope=404  hf-mirror=401
Qwen/Qwen3.8-27B-MXFP4-GGUF     ModelScope=404  hf-mirror=401
Qwen/Qwen3.8-27B-Instruct-GGUF  ModelScope=404  hf-mirror=401
unsloth/Qwen3.8-27B-GGUF        ModelScope=200  hf-mirror=200
bartowski/Qwen3.8-27B-GGUF      ModelScope=200  hf-mirror=200
lmstudio-community/Qwen3.8-27B-GGUF  ModelScope=200  hf-mirror=200
```

  (The `huggingface.co` column of the brief's original command returned 000 —
  connection timeout — for every repo on both attempts; see the network note
  above. `Qwen/Qwen3.8-27B-Instruct-GGUF` hf-mirror body:
  `{"error":"Invalid username or password."}`; ModelScope body:
  `{"Code":10010205001,"Message":"获取模型信息失败，信息：record not
  found","RequestId":"3f52db02-6379-426f-a21e-727bb130885f","Success":false}`.)
  Additional naming probe: `Qwen/Qwen3.8-27B-Instruct` ModelScope=404 /
  hf-mirror=401, while `Qwen/Qwen3.8-27B` ModelScope=200 / hf-mirror=200 —
  there is no separate "-Instruct" repo; the AMD Day-0 blog's repo reference
  `Qwen/Qwen3.8-27B-Instruct-GGUF:Qwen3.8-27B-Instruct-UD-Q4_K_XL` does not
  resolve as a repo on either hub, but the exact quant it names
  (`UD-Q4_K_XL`) exists as `Qwen3.8-27B-UD-Q4_K_XL.gguf` (17.92 GB) inside
  `unsloth/Qwen3.8-27B-GGUF` (file list below).

- Official Qwen org publishes **no GGUF**: the base repo
  `Qwen/Qwen3.8-27B` (ModelScope 200) file list
  (`https://modelscope.cn/api/v1/models/Qwen/Qwen3.8-27B/repo/files?Recursive=true`,
  33 entries) contains `model-00001-of-00018.safetensors` … safetensors only;
  `gguf files: NONE`.

- Quant ladder evidence, `unsloth/Qwen3.8-27B-GGUF` on ModelScope
  (`/api/v1/models/unsloth/Qwen3.8-27B-GGUF/repo/files?Recursive=true`,
  30 entries; sizes as reported):

```
mmproj-BF16.gguf  0.93 GB   mmproj-F16.gguf  0.93 GB
BF16/Qwen3.8-27B-BF16-00001-of-00002.gguf  49.99 GB
BF16/Qwen3.8-27B-BF16-00002-of-00002.gguf   4.67 GB
Qwen3.8-27B-IQ4_NL.gguf  16.34 GB    Qwen3.8-27B-IQ4_XS.gguf  15.71 GB
Qwen3.8-27B-Q3_K_M.gguf  13.82 GB    Qwen3.8-27B-Q3_K_S.gguf  12.57 GB
Qwen3.8-27B-Q4_0.gguf   16.06 GB     Qwen3.8-27B-Q4_1.gguf   17.54 GB
Qwen3.8-27B-Q4_K_M.gguf  17.11 GB    Qwen3.8-27B-Q4_K_S.gguf  16.12 GB
Qwen3.8-27B-Q5_K_M.gguf  19.83 GB    Qwen3.8-27B-Q5_K_S.gguf  19.27 GB
Qwen3.8-27B-Q6_K.gguf   22.88 GB     Qwen3.8-27B-Q8_0.gguf   29.05 GB
Qwen3.8-27B-UD-IQ2_M.gguf    10.32 GB   Qwen3.8-27B-UD-IQ2_XXS.gguf   9.01 GB
Qwen3.8-27B-UD-IQ3_XXS.gguf  11.91 GB   Qwen3.8-27B-UD-Q2_K_XL.gguf  10.68 GB
Qwen3.8-27B-UD-Q3_K_XL.gguf  13.44 GB   Qwen3.8-27B-UD-Q4_K_XL.gguf  17.92 GB
Qwen3.8-27B-UD-Q5_K_XL.gguf  20.22 GB   Qwen3.8-27B-UD-Q6_K_XL.gguf  25.92 GB
Qwen3.8-27B-UD-Q8_K_XL.gguf  31.46 GB
```

  Repo metadata (via hf-mirror API): `createdAt: 2026-08-13T08:28:40.000Z`,
  `downloads: 867963`. README (ModelScope `/repo?FilePath=README.md`)
  states: `<li>MTP for fast inference is available.</li>` and
  `MTP (Multi-Token Prediction): trained with multiple steps` — the MTP block
  ships inside the main GGUFs.

- `bartowski/Qwen3.8-27B-GGUF` on ModelScope (36 entries): 26 single-file
  quants IQ2_M 10.87 GB through Q8_0 29.12 GB (incl. Q2_K_L/Q3_K_XL/Q4_K_L/
  Q5_K_L/Q6_K_L variants), `Qwen3.8-27B-imatrix.gguf`, calibration file,
  BF16 split (39.96 + 14.70 GB), and `mmproj-Qwen3.8-27B-bf16.gguf` /
  `mmproj-Qwen3.8-27B-f16.gguf` (0.93 GB each). Metadata: `createdAt:
  2026-08-14T15:48:06.000Z`, `downloads: 21238`.

- LM Studio angle: the stock registry hosts
  (`registry.lms-with-permissions.lmstudio.ai/v0/models`,
  `registry.lmstudio.ai/v1/model/find`) are not reachable from this host
  (`Could not resolve host` / HTTP 000 after one retry) — recorded as
  absence. The discoverable LM Studio-side artifact is
  `lmstudio-community/Qwen3.8-27B-GGUF` (LM Studio's community publisher
  org), ModelScope 200 + hf-mirror 200, `createdAt: 2026-08-14T15:00:39.000Z`
  (same day as AMD's Day-0 blog), `downloads: 171518`, file list:

```
Qwen3.8-27B-Q4_K_M.gguf  16.81 GB
Qwen3.8-27B-Q6_K.gguf    22.43 GB
Qwen3.8-27B-Q8_0.gguf    29.05 GB
mmproj-Qwen3.8-27B-BF16.gguf  0.93 GB
```

- MTP sidecar: `unsloth/Qwen3.8-27B-MTP-GGUF` ModelScope=404 /
  hf-mirror=401 (**absent**); for comparison `unsloth/Qwen3.6-27B-MTP-GGUF`
  (the separate draft-file variant referenced in llama.cpp issue #23577)
  is ModelScope=200 / hf-mirror=200. For Qwen3.8-27B, MTP tensors ride the
  main GGUF (see unsloth README quote above), matching llama.cpp's
  `load_mtp`-from-target-GGUF path.

- Brief's ModelScope search endpoint probe:
  `https://modelscope.cn/api/v1/dolphin/models?PageSize=10&PageNumber=1&Search=Qwen3.8-27B%20GGUF`
  → `404 page not found` (and the `www.` variant, and
  `/api/v1/models?...Search=...`, also 404) — the dolphin search API has
  moved or been retired; its replacement was not discoverable by probing, so
  repo-level file-list APIs (above) were used instead. Recorded as moved /
  undiscoverable.

- Conclusion: **quants exist today** — a full ladder from UD-IQ2_XXS 9.01 GB
  to Q8_0 ~29 GB (plus BF16 split), with mmproj vision files, from three
  publishers (unsloth 2026-08-13, lmstudio-community and bartowski
  2026-08-14), mirrored on ModelScope (directly reachable) and HF (reachable
  via hf-mirror from this host). No official `Qwen/*GGUF` repo exists; the
  AMD Day-0 blog's `UD-Q4_K_XL` reference resolves to
  unsloth/Qwen3.8-27B-GGUF. No separate MTP-sidecar repo for 3.8 yet.
- Dates probed: all HTTP probes 2026-08-16.

## Q3: converter viability

- Probe (brief's command, verbatim):

```bash
curl -fsSL "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/convert_hf_to_gguf.py" \
  | grep -n -i 'qwen3_5\|Qwen3_5ForConditionalGeneration' | head -10 || echo "no qwen3_5 in converter"
```

- Evidence: **empty output** — again a *false negative* from layout drift:
  `convert_hf_to_gguf.py` is now a 307-line CLI shim whose imports are
  `from conversion import (ModelBase, ModelType, get_model_architecture,
  get_model_class, ...)`. The model classes moved to the `conversion/`
  package; the Qwen ones are in `conversion/qwen.py` (718 lines). Grep of the
  moved location (pinned `3cb7ffb`):

```
606:class _Qwen35MRopeMixin:
622:@ModelBase.register("Qwen3_5ForConditionalGeneration", "Qwen3_5ForCausalLM")
623:class Qwen3_5TextModel(_Qwen35MRopeMixin, _LinearAttentionVReorderBase):
624:    model_arch = gguf.MODEL_ARCH.QWEN35
627:@ModelBase.register("Qwen3_5MoeForConditionalGeneration", "Qwen3_5MoeForCausalLM")
628:class Qwen3_5MoeTextModel(_Qwen35MRopeMixin, _LinearAttentionVReorderBase):
629:    model_arch = gguf.MODEL_ARCH.QWEN35MOE
```

  `Qwen3_5ForConditionalGeneration` — the exact `architectures[0]` string in
  Qwen/Qwen3.8-27B's config.json (quoted in Q1) — is registered, mapping to
  `MODEL_ARCH.QWEN35`, which is the arch string `qwen35` that the runtime
  loads. The class chain provides the rest:
  `_Qwen35MRopeMixin` (line 606: always writes
  `qwen35.rope.dimension_sections`, default `[11, 11, 10, 0]`) →
  `_LinearAttentionVReorderBase(Qwen3NextModel)` (line 438: reorders V-heads
  of the GDN tensors — `in_proj_qkv`, `in_proj_z`, `in_proj_b`, `in_proj_a`,
  `A_log/dt_bias/dt_proj`, `conv1d`, `out_proj`) →
  `Qwen3NextModel(_QwenMtpMixin, Qwen2MoeModel)` (line 364) →
  `_QwenMtpMixin` (line 271: `supports_mtp_export = True`; reads
  `mtp_num_hidden_layers` from the HF config, extends `block_count`, emits
  the nextn metadata key, remaps `mtp.*` tensors to layer-indexed nextn
  names) → `Qwen2MoeModel` → `Qwen2Model(TextModel)` (line 54) for standard
  Qwen BPE vocab handling. CLI surface (convert_hf_to_gguf.py line 126):

```
help="Exclude NextN speculative draft tensors from the converted GGUF. Pair with --mtp or --dspark on a second run to publish target and draft as two files."
```

- Known open defect in this exact path (issue search
  `repo:ggml-org/llama.cpp qwen3_5 in:title`, 2026-08-16, total_count 4):
  - **#27019** [open, created 2026-08-13]
    `convert_hf_to_gguf: Qwen3.5 (qwen3_5) hybrid linear-attention tensors fail - ssm_conv1d kernel dim + in_proj_a/b expansion not handled`
    — converting `Qwen/Qwen3.5-9B` fails with
    `RuntimeError: shape '[16, 2, 1, 1]' is invalid for input of size 65536`
    inside `conversion/qwen.py _reorder_v_heads` (the `in_proj_a`/`in_proj_b`
    branch); the issue's "expected GGUF layout" reference is a working
    `unsloth/Qwen3.5-9B-GGUF`.
  - **#27132** [open PR, created 2026-08-15, label `conversion`]
    `fix(convert): qwen3_5 hybrid linear-attention tensors - ssm_conv1d kernel dim + in_proj_a/b layout`
    — fixes #27019; author states "I have tested the changes locally
    (Qwen3.5-9B converted and loaded successfully with llama-server)". **Not
    merged** at probed commit `3cb7ffb` (the failing code paths quoted above
    are still master's).
  - Relevance to the 27B: Qwen3.8-27B has `linear_num_value_heads = 48` vs
    `linear_num_key_heads = 16` (v_per_k = 3), so the same V-head reorder
    machinery (`_reorder_v_heads` on conv1d / in_proj_a/b) is exercised;
    whether the 3.8 checkpoint layout hits the same reshape failure is not
    determinable without a local conversion run — and third-party GGUFs of
    3.8-27B demonstrably exist since 2026-08-13, so upstream (or unsloth's
    pipeline) has produced working conversions regardless.
- Related load-side issue: **#26916** [open, 2026-08-11]
  `Eval bug: Qwen3.5-Hybrid model (qwen3_5, SSM+Attention) fails to load — "tensor 'blk.32.attn_norm.weight' not found"`.
- Conclusion: **viable and registered, with one open converter bug to watch**
  — `Qwen3_5ForConditionalGeneration` converts to `qwen35` GGUFs with GDN
  tensor reordering, MTP export, and standard Qwen vocab, via
  `conversion/qwen.py`; but a same-family conversion crash (#27019) has an
  unmerged fix (#27132) at the probed commit. For this project the converter
  is a fallback only: prebuilt quants (Q2) cover every size class we need.
- SHA/date probed: `3cb7ffb1a1f612d5e4a46244ae5a3c77ad934a70`
  2026-08-16T12:12:55Z; issues fetched via
  `https://api.github.com/repos/ggml-org/llama.cpp/issues/27019` (and /27132,
  /26916) on 2026-08-16.

## Q4: HIP/ROCm (gfx1151) buildability — beyond Vulkan

Established context from Spike A (`docs/results/spike/vllm.md`, commit
`ac38630`): AMD's official Day-0 route for this exact model on this exact
platform is "only the llama.cpp based Vulkan backend is supported" with "GGUF
is the only local file format option" (AMD blog, 2026-08-14). This probe asks
whether the HIP backend itself is viable for gfx1151 on our ROCm 7.14 stack.

- No hardcoded gfx list anymore: `grep -i gfx` on `ggml/src/ggml-hip/CMakeLists.txt`
  (pinned `3cb7ffb`) matches only the forwarding logic — arch selection is
  via `-DGPU_TARGETS` / `-DAMDGPU_TARGETS` / `CMAKE_HIP_ARCHITECTURES`:

```
35:    # Forward (AMD)GPU_TARGETS to CMAKE_HIP_ARCHITECTURES.
36:    if(AMDGPU_TARGETS AND NOT GPU_TARGETS)
37:        set(GPU_TARGETS ${AMDGPU_TARGETS})
39:    if(GPU_TARGETS AND NOT CMAKE_HIP_ARCHITECTURES)
40:        set(CMAKE_HIP_ARCHITECTURES ${GPU_TARGETS})
```

  plus `if (${hip_VERSION} VERSION_LESS 6.1) message(FATAL_ERROR "At least
  ROCM/HIP V6.1 is required")` — ROCm 7.14 clears that floor. The root
  `CMakeLists.txt` and `ggml/src/ggml-cuda/CMakeLists.txt` contain **zero**
  `gfx` matches (defaults defer to CMake's HIP detection or user targets).
  `docs/build.md` (line 385) documents the mechanism: "If necessary, adapt
  `GPU_TARGETS` to the GPU arch you want to compile for. The above example
  uses `gfx1100` … You can find a list of targets [here]
  (https://llvm.org/docs/AMDGPUUsage.html#processors)" — no gfx1151-specific
  mention.
- Source-level gfx1151 awareness: `ggml/src/ggml-cuda/vendors/hip.h` lines
  219–221 (pinned):

```
#if defined(__gfx1150__) || defined(__gfx1151__) || defined(__gfx1152__) || defined(__gfx1153__)
#define RDNA3_5
#endif // defined(__gfx1150__) || defined(__gfx1151__) || defined(__gfx1152__) || defined(__gfx1153__)
```

  (`__gfx1151__` also rolls up under `__GFX11__` → `RDNA3`, lines 211–213.)
- CI coverage: `.github/workflows/hip-quality-check.yml` builds only
  `-DGPU_TARGETS=gfx942` (line 66) and `-DGPU_TARGETS=gfx908` (line 79) —
  **gfx1151 is not in CI**.
- Issue landscape (search `repo:ggml-org/llama.cpp qwen35 rocm|hip|vulkan`,
  2026-08-16):
  - **#21284** [open, 2026-04-02, bug-unconfirmed]
    `Misc. bug: Inefficient defaults for gfx1151 cost substantial performance for prefill (ROCm)`
    — "There's some prefill performance to be eked out for llama.cpp running
    on AMD Strix Halo." Confirms the HIP path *runs* on gfx1151 but with
    suboptimal default dispatch configs.
  - **#26199** [closed (merged) 2026-07-29]
    `HIP: MMQ Dispatch config modification - separation of RDNA3, 3.5 from 4 and tune 4.`
    — "adds mmq configurations for host and device for RDNA3 and 3.5
    separating them from RDNA4"; author's RDNA4 testbed was "a MinisForum
    MS-S1 over TB5 with a R9700" (the same Radeon AI PRO R9700 as AMD's
    Day-0 blog). RDNA3.5 (= gfx1150–1153) kernels are actively tuned.
  - **#26001** [open PR] `CUDA: Support of GDN chunked kernel for prefill`
    — GDN prefill acceleration in flight (shared CUDA/HIP source).
  - **#26220** [open] Native MMA FA kernel prompt-processing regression
    "on RDNA4 (gfx1201)" — adjacent-family watch item.
- Qwen3.8-27B-specific runtime issues (search
  `repo:ggml-org/llama.cpp Qwen3.8-27B`, total_count 34; most relevant):
  - **#27122** [open, 2026-08-15] `Eval bug: MTP triggers reproducible CUDA
    lockups with Qwen3.8-27B while --split-mode tensor` — model
    `Qwen3.8-27B-UD-Q4_K_XL` (unsloth); "The problem does seem to only occur
    with using --split-mode tensor and --spec-type draft-mtp together …
    With --split-mode layer the problem doesn't occur at all." (Windows,
    CUDA, 2 GPUs — not our stack, but the only MTP-lockup report for this
    model.)
  - **#27090** [open, 2026-08-14] `Qwen3.8-27B (qwen35 hybrid) llama-server
    crashes silently at ~520K prefill tokens with YaRN rope-scale 4`.
  - **#23577** [open, 2026-05-23] `Eval bug: MTP with Qwen3.6 27B outputs
    repeated //// after long session` (unsloth/Qwen3.6-27B-MTP-GGUF, same
    qwen35 arch family, CUDA/Windows) — long-session MTP correctness
    watch item.
  - **#26432** [open] `Silent GTT fallback when context + MTP exceeds VRAM —
    no error at load, massive throughput collapse` — directly relevant to a
    27B on a 128 GB-but-shared gfx1151 APU.
  - **#27107** [closed] / **#27139** [open] — chat-template/tool-call issues
    (Claude Code / Codex), one resolved by using the Qwen3.6 template file.
- Conclusion: **HIP-on-gfx1151 is buildable in master** (explicit
  `-DGPU_TARGETS=gfx1151`; source carries `__gfx1151__` → RDNA3_5 handling;
  merged RDNA3.5 MMQ tuning as of 2026-07-29) but it is the *unvalidated*
  route: no CI coverage, an open prefill-performance issue on Strix Halo
  (#21284), and AMD's own Day-0 blessing covers Vulkan only. Treat HIP as
  our experiment and Vulkan (per AMD) as the reference path.

## Impact

- llama.cpp arch support: **full-validation-now** — `qwen35`/`qwen35moe`
  registered at master `3cb7ffb` (2026-08-16) with GDN linear attention,
  hybrid memory, single-block MTP draft head (load + graph +
  `LLAMA_CONTEXT_TYPE_MTP` + draft-mtp spec-decode driver), and Qwen3-VL-type
  mmproj vision; the 27B size is an enumerated type; six months of upkeep
  since #19468 (2026-02-10). Upstream action needed from us: none for
  loading/inference. The registered arch NAME is `qwen35` — greps for
  `qwen3_5`/`qwen3n` in the probed C++ sources (`src/llama-arch.cpp`,
  `src/llama-model.cpp`, `src/models/qwen35.cpp`, `common/chat.cpp`,
  `src/llama-chat.cpp`) all return nothing; the underscore form appears only
  in the Python converter registrations and in the HF config's `model_type`.
  Quote the `qwen35` name correctly in any issue reports.
- Existing quants: **download-now** — unsloth (21 single-file quants 9.01 GB
  UD-IQ2_XXS → 29.05 GB Q8_0 plus BF16 split and mmproj; the AMD-referenced
  UD-Q4_K_XL is 17.92 GB), lmstudio-community (Q4_K_M/Q6_K/Q8_0 + mmproj),
  bartowski (26 quants + imatrix + mmproj), on ModelScope (directly
  reachable) and HF (via hf-mirror here). No official Qwen GGUF; no 3.8 MTP
  sidecar repo (MTP tensors are inside the main files, per unsloth README).
  Self-conversion is a fallback and currently carries open bug #27019 /
  unmerged fix #27132 in the very code path (GDN V-head reorder) the 27B
  exercises (v_per_k = 3).
- Vision: **present end-to-end in the ecosystem** — mmproj files ship with
  all three publishers' repos and ride `VisionProjectorType.QWEN3VL`; not
  part of AMD's Day-0 benchmark recipe, so validate separately if we use it.
- Backend choice on gfx1151: **Vulkan is AMD's validated path (per Spike A
  Day-0 receipts); HIP is our preferred experiment** — buildable via
  `-DGPU_TARGETS=gfx1151` on ROCm ≥ 6.1 (7.14 clears it), RDNA3.5-aware
  kernels and merged MMQ tuning (#26199), but zero CI coverage and an open
  Strix Halo prefill-perf issue (#21284). Budget a Vulkan fallback build in
  any GGUF benchmark matrix.
- MTP on the GGUF path: **wired but treat as experimental** — the runtime
  path exists (draft-mtp + in-file nextn), but open issues #27122 (MTP
  lockups with tensor split; layer split reportedly fine), #23577 (long-
  session "////" repetition on the sibling 27B), and #26432 (silent GTT
  fallback when context+MTP exceeds VRAM) all counsel guarded expectations;
  this matches AMD's own Day-0 finding (Spike A) that MTP=4 was
  net-negative on Ryzen AI Max+ 395 (24.5 vs 39.9 tok/s) and unsupported on
  R9700 (51.8 tok/s plain). Note also `llama-server` at this commit exposes
  no draft-mtp flag of its own — MTP experiments need `examples/speculative*`
  or LM Studio's bundled runtime.
- Benchmark anchors for our gfx1151 runs (established in Spike A, AMD
  Day-0, llama.cpp/Vulkan, UD-Q4_K_XL): 39.9 tok/s output (no MTP) on
  Ryzen AI Max+ 395 128 GB; 51.8 tok/s on Radeon AI PRO R9700 32 GB. A
  HIP-on-ROCm-7.14 result materially below these on the same quant would
  indicate our build/config, not the model.
