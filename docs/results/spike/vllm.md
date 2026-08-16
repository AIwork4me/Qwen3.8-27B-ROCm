# Spike A: vLLM + transformers support for qwen3_5 — 2026-08-16

Probed 2026-08-16. Every quoted block below is verbatim probe output recorded
at the stated commit. Absence of matches is recorded as absence.
Revised 2026-08-16 (fix round 1): Q4/Impact corrected after review — two
AMD Qwen3.8 Day-0 publications added, vllm#37151 closed-state fixed, radeon
URL slug fixed. Q1–Q3 unchanged.

## Q1: transformers support

- Probe (brief's command, verbatim):

```bash
curl -fsSL https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/auto/configuration_auto.py \
  | grep -n 'qwen3_5\|Qwen3_5' | head -20
```

- Evidence: **empty output (0 matches)**. This is a *false negative*: on
  current `main`, `configuration_auto.py` no longer holds the mapping tables —
  line 26 now reads `from .auto_mappings import CONFIG_MAPPING_NAMES, ...`
  (the file shrank to 456 lines with zero `qwen` entries). The mapping lives in
  `auto_mappings.py`, so the probe was adapted (one hop, same repo/path):

```bash
curl -fsSL https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/auto/auto_mappings.py | grep -n 'qwen3_5\|Qwen3_5'
```

- Evidence (adapted probe, `main`):

```
530:        ("qwen3_5", "Qwen3_5Config"),
531:        ("qwen3_5_moe", "Qwen3_5MoeConfig"),
532:        ("qwen3_5_moe_text", "Qwen3_5MoeTextConfig"),
533:        ("qwen3_5_moe_vision", "Qwen3_5MoeVisionConfig"),
534:        ("qwen3_5_text", "Qwen3_5TextConfig"),
535:        ("qwen3_5_vision", "Qwen3_5VisionConfig"),
895:        ("qwen3_5_moe_text", "qwen3_5_moe"),
896:        ("qwen3_5_moe_vision", "qwen3_5_moe"),
897:        ("qwen3_5_text", "qwen3_5"),
898:        ("qwen3_5_vision", "qwen3_5"),
```

- Model-class wiring (config + multimodal head), probe:

```bash
curl -fsSL https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/auto/modeling_auto.py | grep -n 'qwen3_5'
```

- Evidence (excerpt; line 1138 sits inside `MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES`, which begins at line 1067):

```
431:        ("qwen3_5", "Qwen3_5Model"),
825:        ("qwen3_5", "Qwen3_5ForCausalLM"),  # VLM compatibility
828:        ("qwen3_5_text", "Qwen3_5ForCausalLM"),
1138:        ("qwen3_5", "Qwen3_5ForConditionalGeneration"),
1139:        ("qwen3_5_moe", "Qwen3_5MoeForConditionalGeneration"),
1671:        ("qwen3_5", "Qwen3_5ForTokenClassification"),
```

- Model dir probe (brief's command, verbatim):

```bash
curl -fsSL "https://api.github.com/repos/huggingface/transformers/commits?path=src/transformers/models/qwen3_5&per_page=1" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date']) if d else print('no qwen3_5 model dir')"
```

- Evidence:

```
95940bf8775059a42f047256f076e4f607bc43ec 2026-08-14T11:45:57Z
```

- Release check (brief's command shape, tag adjusted — latest release is v5.15.0; v5.8.0 does exist). `grep -c 'qwen3_5'` on `auto_mappings.py` per tag:

```
v5.15.0: auto_mappings.py qwen3_5 count = 10
v5.14.1: auto_mappings.py qwen3_5 count = 10
v5.13.1: auto_mappings.py qwen3_5 count = 10
v5.12.1: auto_mappings.py qwen3_5 count = 10
v5.11.0: auto_mappings.py qwen3_5 count = 10
v5.10.3: auto_mappings.py qwen3_5 count = 10
v5.9.0:  auto_mappings.py qwen3_5 count = 10
v5.8.0:  auto_mappings.py qwen3_5 count = 10
```

- Conclusion: **supported on `main` AND already released** — `qwen3_5` config
  classes and `Qwen3_5ForConditionalGeneration` (image-text-to-text mapping)
  are present in every release tag checked, v5.8.0 through v5.15.0 (latest).
  Any current transformers release is sufficient; no from-source install
  needed.
- SHA/date probed: transformers `main` HEAD
  `a61d5f9e4fc184cff66938ff6c521cc358b5e024` 2026-08-15T19:59:27Z;
  qwen3_5 model dir latest `95940bf8775059a42f047256f076e4f607bc43ec`
  2026-08-14T11:45:57Z.

## Q2: vLLM architecture registration

- Probe (brief's command, verbatim):

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/model_executor/models/registry.py \
  | grep -n -i 'qwen3_5\|qwen3_next' | head -20
```

- Evidence:

```
113:    "Qwen3NextForCausalLM": ("qwen3_next", "Qwen3NextForCausalLM"),
203:    "Qwen3_5ForCausalLM": ("qwen3_5", "Qwen3_5ForCausalLM"),
204:    "Qwen3_5MoeForCausalLM": ("qwen3_5", "Qwen3_5MoeForCausalLM"),
287:    "ColQwen3_5": ("colqwen3_5", "ColQwen3_5Model"),
592:    "Qwen3_5ForConditionalGeneration": ("qwen3_5", "Qwen3_5ForConditionalGeneration"),
593:    "Qwen3_5MoeForConditionalGeneration": (
594:        "qwen3_5",
595:        "Qwen3_5MoeForConditionalGeneration",
679:    "Qwen3NextMTP": ("qwen3_next_mtp", "Qwen3NextMTP"),
681:    "Qwen3_5MTP": ("qwen3_5_mtp", "Qwen3_5MTP"),
682:    "Qwen3_5MoeMTP": ("qwen3_5_mtp", "Qwen3_5MoeMTP"),
```

  Dict membership (from the same file): lines 203–204 are in
  `_TEXT_GENERATION_MODELS` (starts line 72); line 592 is in
  `_MULTIMODAL_MODELS` (starts line 347); lines 679–682 are in
  `_SPECULATIVE_DECODING_MODELS` (starts line 618). All roll up into
  `_VLLM_MODELS` (line 745).

- Multimodal implementation file exists (brief's raw-fetch probe; 404 would mean absent):

```bash
curl -s -o /dev/null -w '%{http_code}' https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/model_executor/models/qwen3_5.py
```

```
qwen3_5.py -> HTTP 200
qwen3_5_mtp.py -> HTTP 200
```

  `qwen3_5.py` (732 lines), class evidence:

```
105:class Qwen3_5ProcessingInfo(Qwen3VLProcessingInfo):
438:class Qwen3_5ForCausalLM(Qwen3_5ForCausalLMBase):
460:class Qwen3_5ForConditionalGeneration(Qwen3VLForConditionalGeneration, IsHybrid):
461:    supports_multimodal_pruning = True
681:class Qwen3_5MoeForConditionalGeneration(
```

- Dated commits touching the files (receipts):

```
vllm/model_executor/models/qwen3_5.py     80d6d557f307448fdad46995b5e237817b31144e 2026-08-13T15:10:09Z - Standardise weight tying on `ParallelLMHead.tie_weights` (#52147)
vllm/model_executor/models/qwen3_5_mtp.py c05d75aaa95cf89f547503044c1921625905085d 2026-08-14T03:58:32Z - [Bugfix][Refactor] Keep QwenNext layer boundaries sequence parallel (#50685)
```

- Conclusion: **registered at the probed commit** — `Qwen3_5ForConditionalGeneration` is in `_MULTIMODAL_MODELS` (the multimodal registry dict), with a concrete implementation at `vllm/model_executor/models/qwen3_5.py` that subclasses vLLM's `Qwen3VLForConditionalGeneration` and sets `supports_multimodal_pruning = True`. The file is under active maintenance (touched 2026-08-13/14).
- SHA/date probed: vLLM `main` HEAD `4d2a68d64d9e05921ed5c4099146e768a92d71d5` 2026-08-16T11:09:23Z.

## Q3: MTP support in vLLM for qwen3_5

- Evidence 1 — registry (Q2 output, lines 681–682):

```
681:    "Qwen3_5MTP": ("qwen3_5_mtp", "Qwen3_5MTP"),
682:    "Qwen3_5MoeMTP": ("qwen3_5_mtp", "Qwen3_5MoeMTP"),
```

  in `_SPECULATIVE_DECODING_MODELS`.

- Evidence 2 — draft-model implementation exists, `vllm/model_executor/models/qwen3_5_mtp.py` (HTTP 200, 319 lines):

```
64:class Qwen3_5MultiTokenPredictor(nn.Module):
211:class Qwen3_5MTP(LocalArgmaxMixin, nn.Module, SupportsMultiModal):
316:class Qwen3_5MoeMTP(Qwen3_5MTP, QwenNextMixtureOfExperts):
```

  Note `SupportsMultiModal` on the MTP draft class, plus quantization handling
  for MTP layers (lines 106–111: "GPTQ: quantized checkpoints may exclude MTP
  from quantization via quantization_config.dynamic ...").

- Evidence 3 — spec-decode config wiring. The brief's `vllm/config.py` grep
  404s (connection-level: the single file was refactored into the
  `vllm/config/` package; directory listing confirmed). The spec-decode config
  now lives at `vllm/config/speculative.py`:

```
37:MTPModelTypes = Literal[
49:    "qwen3_next_mtp",
50:    "qwen3_5_mtp",
```

  and `EagleModelTypes = Literal["eagle", "eagle3", "extract_hidden_states", MTPModelTypes, ...]`
  feeds `SpeculativeMethod`, i.e. `speculative_config.method = "qwen3_5_mtp"`
  is a valid user-facing path. `vllm/v1/spec_decode/` has no qwen3_5-specific
  proposer file (listing: eagle.py, medusa.py, draft_model.py, ngram..., but no
  qwen3_5.py) — the MTP path routes through the generic draft-model machinery
  keyed by the model-type literal above.

- Conclusion: **MTP is wired end-to-end in vLLM main for qwen3_5** — registered
  draft arch (`Qwen3_5MTP`), implementation file, and `qwen3_5_mtp` in the
  `MTPModelTypes` speculative-config literal, for both dense and MoE variants.
  What upstream does NOT show: any ROCm/RDNA runtime validation of this MTP
  path (see Q4) — wiring exists, platform-specific execution is unproven
  publicly.

## Q4: ROCm/gfx1151 angle

Official AMD coverage exists at three levels — Qwen 3.5/Instinct (Feb),
Qwen 3.8/Instinct (Aug 12), and **Qwen 3.8 27B on Ryzen AI Max + Radeon
(Aug 14)** — all three probed below.

- AMD Day-0 article, Qwen 3.5 on Instinct (official):
  https://www.amd.com/en/developer/resources/technical-articles/2026/day-0-support-for-qwen-3-5-on-amd-instinct-gpus.html
  — "Day 0 Support for Qwen 3.5 on AMD Instinct GPUs", published 2026-02-16
  (updated 2026-02-19). What it claims: Day-0 support for "Qwen 3.5, the
  newest generation of LLMs from Alibaba" on **Instinct MI300X, MI325X, and
  MI35X**; optimized Triton kernel for gated-delta-net, hipBLASLt shared-expert
  GEMMs, AITER FusedMoE, MIOpen mRoPE/Conv3d/DeepStack-ViT; "Qwen 3.5
  multimodal native support"; "The next upstream released SGLang and vLLM
  docker image will run Qwen 3.5 out-of-the-box." This article does **not**
  pin a vLLM version/image and does not mention **MTP**, **Radeon/RDNA/
  gfx1151**, or **Qwen3.8** (it predates the 2026-08-08 ModelScope release by
  ~6 months). AITER is an Instinct-focused kernel library. (Its Step-3
  "pinned vLLM version" gap is closed by the Qwen 3.8 article below.)
- AMD Day-0 article, Qwen 3.8 on Instinct (official, probed 2026-08-16):
  https://www.amd.com/en/developer/resources/technical-articles/2026/day-0-support-for-qwen-3-8-on-amd-instinct-gpus.html
  — "Day 0 Support for Qwen 3.8 on AMD Instinct GPUs", published
  2026-08-12. Key verbatim lines:
  - "AMD is excited to announce Day-0 support for Alibaba's latest Qwen 3.8 model family on AMD Instinct™ MI300X, MI325X, and MI355X GPUs. Developers can immediately deploy and evaluate Qwen 3.8 using the AMD ROCm™ software together with SGLang and vLLM."
  - Pinned vLLM image (this answers the brief's Step-3 "pinned vLLM
    version/image" ask — a tag, not a version number): "vLLM Docker:
    `docker pull vllm/vllm-openai-rocm:qwen38`"
  - MTP + MXFP4: "Starting from the FP8 checkpoint, Quark selectively quantizes the MoE routed experts in both the main model and MTP layers to MXFP4, while keeping the remaining layers in BF16."
  - SGLang images also pinned (rocm/sgl-dev:v0.5.8.post1-rocm720-mi35x-20260808, rocm/sgl-dev:v0.5.8.post1-rocm720-mi30x-20260215) and ATOM nightly (rocm/atom-dev:nightly_qwen3.8_day0).
  - Flagship covered is the 2.4T MoE (Qwen/Qwen3.8-2.4T-A95B-FP8; MXFP4
    variant) on MI355X — not the 27B. Notable lineage receipt: the article's
    Quark recipe uses `model_type="qwen3_5_moe_text"` — AMD's own tooling
    confirms Qwen 3.8 checkpoints ride the `qwen3_5*` config family.
  - Still **Instinct (CDNA) only**; no gfx1151/RDNA/Radeon mention.
- AMD Day-0 blog, **Qwen 3.8 27B on Ryzen AI Max + Radeon** (official,
  probed 2026-08-16 — this is AMD's official Day-0 for our EXACT model and
  platform class):
  https://www.amd.com/en/blogs/2026/run-qwen-3-8-27b-on-amd-ryzen-ai-max-and-radeon-graphics-cards-day-0.html
  — "Run Qwen 3.8 27B on AMD Ryzen™ AI Max Agentic PCs and Radeon™ GPUs",
  published 2026-08-14. Key verbatim lines:
  - "Qwen3.8 27B arrives with Day 0 support on AMD Ryzen™ AI processors and Radeon™ graphics cards. Run the latest Qwen model locally with LM Studio on supported AMD hardware."
  - Path is llama.cpp/Vulkan via LM Studio, NOT vLLM-on-ROCm: "As noted above, only the llama.cpp based Vulkan backend is supported." / "M:", and "GGUF is the only local file format option on LM Studio" (Qwen/Qwen3.8-27B-Instruct-GGUF:Qwen3.8-27B-Instruct-UD-Q4_K_XL). "Ollama and MLX were ruled out" / "as they do not support Qwen3.8".
  - Why not ROCm (Windows): "LM Studio's ROCm python requirements are not currently met by the Windows release, so the default runtime remains Vulkan."
  - MTP on gfx1151, with numbers: "we used an MTP setting of 4 (24.5 tok/s output vs 39.9 tok/s without)" — i.e. on Ryzen AI Max+ 395 (GMKtec EVO-X2, 128GB unified) **MTP=4 was net-negative** (24.5 vs 39.9 tok/s output), while Radeon AI PRO R9700 (32GB) reached 51.8 tok/s output (MTP not supported there).
  - Conclusion from this piece: AMD's official Qwen3.8-27B-on-gfx1151 path is
    **llama.cpp/Vulkan (LM Studio) with MTP=4**, explicitly not vLLM-on-ROCm.
- gfx1151 community evidence (web search `vLLM qwen3_5 ROCm gfx1151`,
  2026-08-16):
  - AMD official Radeon build guide (gfx1151/gfx1150 vLLM Docker image, build-it-yourself):
    https://rocm.docs.amd.com/projects/radeon-ryzen/en/docs-7.1/docs/advanced/advancedryz/linux/llm/build-docker-image.html
    — search-indexed as "AMD ROCm official vLLM Docker guide ... supports gfx1151 and gfx1150". Direct fetch returned **HTTP 429 (rate-limited)** on two attempts (initial + one retry after 20 s with browser UA), so the quote above is the search-indexed one; slug corrected from `radeon-ryz` (dead) to `radeon-ryzen` per the search index. Absence-of-verification recorded as such.
  - gfx1151 multimodal crash-class issue, **re-verified 2026-08-16 via
    `https://api.github.com/repos/vllm-project/vllm/issues/37151`**:
    ```
    number: 37151
    title: [Bug]: [ROCm][gfx1151] Engine Core segfaults in libhsa-runtime64.so when loading Qwen3-VL-32B-AWQ on AMD Ryzen AI MAX+ 395
    state: closed
    state_reason: completed
    closed_at: 2026-07-30T10:57:49Z
    labels: ['bug', 'rocm', 'stale']
    ```
    It is **closed, not open** (closed 2026-07-30, before our probe date).
    No fix PR/commit is linked (closed event has no `commit_id`); the close
    followed the stale bot (2026-07-27: "automatically marked as stale ...
    will be automatically closed if no further activity occurs within 30
    days"). The fix-relevant maintainer guidance in-thread (2026-04-22,
    vllmellm): "please use ROCm 7.2.1 as in the docker image
    vllm/vllm-openai-rocm:0.19.1 and tested working with gfx1151, as ROCm 7.1
    doesn't support gfx1151" — i.e. the crash class was attributed to ROCm
    7.1-era stacks and the working reference is vLLM image 0.19.1 / ROCm
    7.2.1 (both older than this project's ROCm 7.14 baseline).
  - Re-check for OTHER open issues tracking qwen3_5 MTP on ROCm
    (`api.github.com/search/issues`, `repo:vllm-project/vllm qwen3_5 mtp rocm
    state:open`, 2026-08-16): **no open issue is ROCm-specific for qwen3_5
    MTP**. Closest open qwen3_5-MTP issues (platform-agnostic):
    https://github.com/vllm-project/vllm/issues/52480 ("qwen3_5_mtp fails to
    load at tensor-parallel-size >= 2 (drafter weight shape mismatch)") and
    https://github.com/vllm-project/vllm/issues/52481 ("MTP speculative
    decoding on Qwen3.5-family models logs misleading multimodal warnings
    ('treated as multimodal but has no registered multimodal processor')").
    Absence of a ROCm-specific MTP issue is recorded as absence.
  - Source-build recipe, Qwen3-Next reported working on Strix Halo: https://community.frame.work/t/how-to-compiling-vllm-from-source-on-strix-halo/77241
  - EVO-X2 (gfx1151) ROCm + vLLM build/benchmark running Qwen3.5-9B: https://note.com/zephel01/n/n686593376d85
  - Full vLLM stack from source for Strix Halo via TheRock builds: https://www.reddit.com/r/ROCm/comments/1rur2ji/full_vllm_inference_stack_built_from_source_for/
  - TheRock nightly ROCm SDK + Strix Halo patches, no prebuilt image: https://github.com/hec-ovi/vllm-qwen
- Conclusion: official AMD coverage of **Qwen3.8 exists and is current** —
  Instinct (CDNA) via ROCm SGLang/vLLM with a pinned image
  (`vllm/vllm-openai-rocm:qwen38`, published 2026-08-12), and gfx1151/Radeon
  via **llama.cpp/Vulkan + LM Studio with MTP=4** (2026-08-14), the latter
  being AMD's official route for this exact model on this exact platform.
  What no official AMD piece covers is **vLLM-on-ROCm on gfx1151 for
  Qwen3.8**: all public evidence for that remains community source builds
  (TheRock / AMD Dockerfile.rocm route), one Qwen3.5-class model (9B dense)
  confirmed on EVO-X2, and no public report of
  Qwen3_5ForConditionalGeneration (multimodal) or vLLM MTP running on
  gfx1151. The prior draft's "nothing official exists for Qwen3.8 on
  gfx1151" was wrong and is corrected here.

## Impact

- transformers: **full-validation-now** — `qwen3_5` config/model classes,
  including `Qwen3_5ForConditionalGeneration`, are in every release tag from
  v5.8.0 to v5.15.0 (latest); no from-source install and no upstream action
  needed for config/processor loading.
- vLLM arch registration + multimodal impl: **full-validation-now** — at
  probed main `4d2a68d` (2026-08-16) the arch is registered in
  `_MULTIMODAL_MODELS` with a maintained implementation file; no upstream
  patching required for the arch itself. AMD's own Instinct Day-0 (2026-08-12)
  ships a pinned vLLM ROCm image (`vllm/vllm-openai-rocm:qwen38`) for the
  Qwen 3.8 family, confirming the arch is production-routed on CDNA. Our
  remaining work is a vLLM source build against the ROCm 7.14 gfx1151
  toolchain, not upstream code changes.
- vLLM MTP wiring: **full-validation-now for wiring, recorded-gap for
  platform** — registry + `qwen3_5_mtp` spec-decode literal + draft model all
  exist upstream, and AMD's Instinct Day-0 quantizes "the MoE routed experts
  in both the main model and MTP layers", so MTP layers are exercised
  officially on CDNA. What is absent is any public ROCm/gfx1151 runtime
  evidence for this vLLM MTP path — validate locally. Open upstream issues to
  watch (found on re-check, neither ROCm-specific):
  vllm#52480 (qwen3_5_mtp fails to load at TP >= 2) and vllm#52481
  (misleading multimodal-processor warnings on Qwen3.5-family MTP). With TP=1
  on a single gfx1151 iGPU, #52480 should not bite; file a new ROCm-specific
  issue only if a local reproduction warrants it (none exists today).
- AMD Day-0 / gfx1151: **recorded-gap, but narrower than first recorded** —
  official AMD Qwen3.8 coverage exists on both fronts as of 2026-08-12/14:
  Instinct via ROCm SGLang/vLLM (pinned image `vllm/vllm-openai-rocm:qwen38`,
  CDNA + AITER only), and gfx1151/Radeon via **llama.cpp/Vulkan + LM Studio
  with MTP=4** — explicitly NOT vLLM-on-ROCm (AMD: "LM Studio's ROCm python
  requirements are not currently met by the Windows release, so the default
  runtime remains Vulkan"). The gap that remains is precisely
  **vLLM-on-ROCm on gfx1151 for Qwen3.8-27B**: no official AMD validation,
  community source builds only (TheRock / AMD Dockerfile.rocm route). The
  gfx1151 multimodal crash-class issue vllm#37151 is **closed** (completed,
  2026-07-30, stale-bot path; in-thread working reference: vLLM image
  0.19.1 / ROCm 7.2.1, with the maintainer note that "ROCm 7.1 doesn't
  support gfx1151" — our ROCm 7.14 baseline clears that floor). Do not count
  on AITER-optimized paths (Instinct-only), and treat vLLM MTP-on-gfx1151 as
  an experiment with a fallback to non-speculative decoding.
- Benchmark anchor for the GGUF path (feeds Spike B/C): AMD's published
  Day-0 numbers for this exact model on this exact platform are the
  methodology-relevant reference — Ryzen AI Max+ 395 (GMKtec EVO-X2, 128GB
  unified): **39.9 tok/s output without MTP vs 24.5 tok/s with MTP=4** (MTP
  net-negative on the 395 per AMD), and Radeon AI PRO R9700 32GB:
  **51.8 tok/s** — all via llama.cpp/Vulkan (LM Studio, Q4_K_XL GGUF). Any
  vLLM-on-ROCm result this project produces should be compared against these
  Vulkan baselines, and our MTP experiments should expect MTP to cost
  throughput on gfx1151 unless vLLM's implementation changes that picture.
