# Spike B: llama.cpp / GGUF support for qwen3_5 — 2026-08-16

Pure upstream recon. All probes run 2026-08-16 from the radeon-cloud host
via the Global-Constraints `fetch` retry helper (3 attempts, 30 s curl
timeout) unless a command is quoted with plain `curl`. raw.githubusercontent.com
was flaky; two files hit persistent 3-retry failures and were recovered via
the api.github.com contents endpoint (recorded below). huggingface.co is
unreachable from this host — every HF probe below records HTTP `000`
(curl exit 28, timeout), which is a finding, not a skip:

```console
$ curl -s -o /dev/null -m 15 -w '%{http_code}\n' "https://huggingface.co/api/models/unsloth/Qwen3.8-27B-GGUF"
000   (curl exit 28, timeout)
```

All llama.cpp evidence is pinned at master HEAD
`4df29be4f4c3673f428170fda944a5b19f743bb8` (2026-08-16T12:53:13Z), recorded
via the commits API in Q1; files fetched at `master` were byte-verified
identical at that SHA unless noted. During the 2026-08-16 review fix, every
provenance probe (commits, releases, pulls, issue-comments APIs) was re-run
verbatim and quoted in place below; all returned values identical to the
original probe.

## Q1 llama.cpp arch support

- Master HEAD pin (brief Step 1, commits-API command; re-captured verbatim
  2026-08-16):

```console
$ fetch "https://api.github.com/repos/ggml-org/llama.cpp/commits?per_page=1" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date'])"
4df29be4f4c3673f428170fda944a5b19f743bb8 2026-08-16T12:53:13Z
```

- Probe (brief Step 1, as written — `grep -i 'qwen3_5\|qwen3_next\|qwen3n'`):

```console
$ fetch https://raw.githubusercontent.com/ggml-org/llama.cpp/master/src/llama-arch.cpp | grep -n -i 'qwen3_5\|qwen3_next\|qwen3n' | head -10
38:    { LLM_ARCH_QWEN3NEXT,        "qwen3next"        },

$ fetch https://raw.githubusercontent.com/ggml-org/llama.cpp/master/src/llama-model.cpp | grep -n -i 'qwen3_5\|qwen3_next\|qwen3n' | head -10
309:        case LLM_ARCH_QWEN3NEXT:
310:            return new llama_model_qwen3next(params);
530:        if (ud->model->arch == LLM_ARCH_QWEN3NEXT || ud->model->arch == LLM_ARCH_QWEN35 || ud->model->arch == LLM_ARCH_QWEN35MOE) {
541:            if (ud->model->arch == LLM_ARCH_QWEN3NEXT) {
643:                if (ud->model->arch == LLM_ARCH_QWEN3NEXT || ud->model->arch == LLM_ARCH_QWEN35 || ud->model->arch == LLM_ARCH_QWEN35MOE) {
1882:                arch == LLM_ARCH_QWEN3NEXT ||
2262:                    (arch == LLM_ARCH_QWEN3NEXT || arch == LLM_ARCH_QWEN35 || arch == LLM_ARCH_QWEN35MOE);
2292:                    } else if (arch == LLM_ARCH_QWEN3NEXT || arch == LLM_ARCH_QWEN35 || arch == LLM_ARCH_QWEN35MOE || arch == LLM_ARCH_MINIMAX_01) {
2721:        case LLM_ARCH_QWEN3NEXT:

$ fetch https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/mqmd/mqmd.cpp
curl: (22) The requested URL returned error: 404   (x3 retries; plain curl status 404)
```

  FINDING 1: the brief's third target `tools/mqmd/mqmd.cpp` 404s on master —
  layout drift, noted as the brief instructs.
  FINDING 2: the grep pattern itself is stale. `llama-model.cpp` at the same
  SHA contains `LLM_ARCH_QWEN35` references that the pattern
  `qwen3_5\|qwen3_next\|qwen3n` only catches when `QWEN3NEXT` rides along on
  the same line. The real arch name in llama.cpp is `qwen35` — **no
  underscore**. Corrected probe (same pinned file, saved locally at fetch
  time, byte-verified at HEAD SHA):

```console
$ fetch https://raw.githubusercontent.com/ggml-org/llama.cpp/4df29be4f4c3673f428170fda944a5b19f743bb8/src/llama-arch.cpp | grep -n 'QWEN35\|QWEN3NEXT'
38:    { LLM_ARCH_QWEN3NEXT,        "qwen3next"        },
41:    { LLM_ARCH_QWEN35,           "qwen35"           },
42:    { LLM_ARCH_QWEN35MOE,        "qwen35moe"        },
997:        case LLM_ARCH_QWEN3NEXT:
1000:        case LLM_ARCH_QWEN35:
1001:        case LLM_ARCH_QWEN35MOE:
1024:        case LLM_ARCH_QWEN35:
1025:        case LLM_ARCH_QWEN35MOE:
(diff vs the master fetch: IDENTICAL)

$ grep -n -B2 -A3 'case LLM_ARCH_QWEN35' /tmp/lcpp_model_pinned.cpp   # saved copy at HEAD SHA
309-        case LLM_ARCH_QWEN3NEXT:
310-            return new llama_model_qwen3next(params);
311:        case LLM_ARCH_QWEN35:
312-            return new llama_model_qwen35(params);
313:        case LLM_ARCH_QWEN35MOE:
314:            return new llama_model_qwen35moe(params);
--
2735-        case LLM_ARCH_QWEN3VL:
2736-        case LLM_ARCH_QWEN3VLMOE:
2737:        case LLM_ARCH_QWEN35:
2738:        case LLM_ARCH_QWEN35MOE:
2739-        case LLM_ARCH_QWEN3TTS:
2740-            return LLAMA_ROPE_TYPE_IMROPE;
```

  The loader treats QWEN35 as a hybrid recurrent (linear-attention) arch —
  `llm_arch_is_recurrent` returns true for `LLM_ARCH_QWEN35`/`QWEN35MOE`
  (llama-arch.cpp lines 1000-1001, in the switch that also lists
  QWEN3NEXT and NEMOTRON_H), per-layer attention/recurrent filters exist
  (llama-model.cpp line 2292), and MTP context plumbing is wired
  (`mtp_on_hybrid_qwen`, llama-model.cpp lines 2260-2262). gguf-py agrees —
  `MODEL_ARCH.QWEN35: "qwen35"` with full tensor-name tables:

```console
$ fetch "https://api.github.com/repos/ggml-org/llama.cpp/contents/gguf-py/gguf/constants.py?ref=4df29be4f4c3673f428170fda944a5b19f743bb8" \
    | python3 -c "import json,sys,base64; sys.stdout.write(base64.b64decode(json.load(sys.stdin)['content']).decode())" \
    | grep -n -i 'qwen35\|qwen3next'
484:    QWEN3NEXT        = auto()
487:    QWEN35           = auto()
488:    QWEN35MOE        = auto()
702:    SSM_BETA_ALPHA       = auto() # qwen3next
1199:    MODEL_ARCH.QWEN3NEXT:        "qwen3next",
1202:    MODEL_ARCH.QWEN35:           "qwen35",
1203:    MODEL_ARCH.QWEN35MOE:        "qwen35moe",
2628:    MODEL_ARCH.QWEN3NEXT: [
2699:    MODEL_ARCH.QWEN35: [
2731:    MODEL_ARCH.QWEN35MOE: [
```

  (The raw.githubusercontent.com fetch of this file at the pinned SHA hit a
  persistent 3-retry failure — 6 timeouts total — during the original probe;
  the api.github.com contents endpoint shown above is the recovery path,
  base64-decoded to 215324 bytes. Re-captured verbatim 2026-08-16, output
  identical.)

- Release containment (support is not master-only):

```console
$ fetch https://api.github.com/repos/ggml-org/llama.cpp/contents/src/llama-arch.cpp?ref=b10453 | grep QWEN35
41 { LLM_ARCH_QWEN35,           "qwen35"           },
42 { LLM_ARCH_QWEN35MOE,        "qwen35moe"        },
```

  Release timestamps (releases API, re-captured verbatim 2026-08-16):

```console
$ fetch "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=3" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); [print(r['tag_name'], r['published_at']) for r in d]"
b10453 2026-08-16T12:54:19Z
b10452 2026-08-16T11:21:52Z
b10451 2026-08-16T07:24:37Z
```

  (b10453 = latest release, published 2026-08-16T12:54:19Z. The raw fetch of
  the tag timed out 3x, curl exit 28; api.github.com fallback used. Support
  originally merged in PR #19435 "[Model] Qwen3.5 dense and MoE support
  (no vision)", created and closed 2026-02-08 — merge state quoted in Q3.)

- Conclusion: **YES — llama.cpp master supports the qwen3_5 architecture,
  under the GGUF arch string `qwen35` (plus `qwen35moe`, and `qwen3next` for
  the Qwen3-Next lineage)**. There is no `qwen3_5` alias and no `qwen3n`
  alias in llama.cpp — the underscore spelling exists only on the HF side
  (class names, `model_type`). The earlier "greps 0 for qwen3_5" result was
  a naming artifact, not absence of support: hybrid linear-attention
  (Gated DeltaNet), recurrent-layer filters, MRoPE, and MTP draft contexts
  are all present in the loader at the probed commit.
- SHA/date probed: llama.cpp master
  `4df29be4f4c3673f428170fda944a5b19f743bb8` 2026-08-16T12:53:13Z; release
  `b10453` 2026-08-16; PR #19435 merged 2026-02-08T23:24:08Z.

## Q2 existing quants

- Probe (brief Step 2, as written; re-run verbatim 2026-08-16):

```console
$ for repo in Qwen/Qwen3.8-27B-GGUF Qwen/Qwen3.8-27B-MXFP4-GGUF unsloth/Qwen3.8-27B-GGUF bartowski/Qwen3.8-27B-GGUF; do
  echo "== $repo =="
  printf 'modelscope -> '; curl -s -o /dev/null -m 15 -w '%{http_code}\n' "https://modelscope.cn/api/v1/models/$repo"
  printf 'huggingface -> '; curl -s -o /dev/null -m 15 -w '%{http_code}\n' "https://huggingface.co/api/models/$repo"
done
== Qwen/Qwen3.8-27B-GGUF ==
modelscope -> 404
huggingface -> 000
== Qwen/Qwen3.8-27B-MXFP4-GGUF ==
modelscope -> 404
huggingface -> 000
== unsloth/Qwen3.8-27B-GGUF ==
modelscope -> 200
huggingface -> 000
== bartowski/Qwen3.8-27B-GGUF ==
modelscope -> 200
huggingface -> 000
```

  Both 200s were re-probed 3x fresh and were stable (200/200/200 each;
  re-verified once more during the 2026-08-16 fix round, again 3x200 each) —
  they are real repos, not CDN ghosts. Note: controller pre-knowledge said
  bartowski 404; the fresh probe disagrees, and the file listing below
  confirms the repo is populated. HF is unreachable from this host (000,
  curl exit 28) so HF-side existence could not be re-verified; both repos'
  READMEs link huggingface.co paths (unsloth README omitted, bartowski
  README mirrors `bartowski/Qwen3.8-27B-GGUF` on HF), consistent with
  ModelScope being a mirror.

- File listing (ModelScope `repo/files?Revision=master` API, sizes in bytes,
  GiB = bytes / 2^30 rounded):

**unsloth/Qwen3.8-27B-GGUF** (200; 21 model quants + 2 mmproj):

| File | Bytes | GiB |
|---|---|---|
| Qwen3.8-27B-UD-IQ2_XXS.gguf | 9010048064 | 8.4 |
| Qwen3.8-27B-UD-IQ2_M.gguf | 10319907904 | 9.6 |
| Qwen3.8-27B-UD-Q2_K_XL.gguf | 10676423744 | 9.9 |
| Qwen3.8-27B-UD-IQ3_XXS.gguf | 11913559104 | 11.1 |
| Qwen3.8-27B-Q3_K_S.gguf | 12574489568 | 11.7 |
| Qwen3.8-27B-UD-Q3_K_XL.gguf | 13441059904 | 12.5 |
| Qwen3.8-27B-Q3_K_M.gguf | 13818690528 | 12.9 |
| Qwen3.8-27B-IQ4_XS.gguf | 15705861088 | 14.6 |
| Qwen3.8-27B-Q4_0.gguf | 16056478688 | 15.0 |
| Qwen3.8-27B-Q4_K_S.gguf | 16121359328 | 15.0 |
| Qwen3.8-27B-IQ4_NL.gguf | 16337628128 | 15.2 |
| Qwen3.8-27B-Q4_K_M.gguf | 17106775008 | 15.9 |
| Qwen3.8-27B-Q4_1.gguf | 17540705248 | 16.3 |
| Qwen3.8-27B-UD-Q4_K_XL.gguf | 17923394624 | 16.7 |
| Qwen3.8-27B-Q5_K_S.gguf | 19270036448 | 17.9 |
| Qwen3.8-27B-Q5_K_M.gguf | 19834055648 | 18.5 |
| Qwen3.8-27B-UD-Q5_K_XL.gguf | 20218178624 | 18.8 |
| Qwen3.8-27B-Q6_K.gguf | 22884408288 | 21.3 |
| Qwen3.8-27B-UD-Q6_K_XL.gguf | 25924152384 | 24.1 |
| Qwen3.8-27B-Q8_0.gguf | 29047086048 | 27.1 |
| Qwen3.8-27B-UD-Q8_K_XL.gguf | 31457991680 | 29.3 |
| mmproj-F16.gguf | 927607488 | 0.9 |
| mmproj-BF16.gguf | 931146432 | 0.9 |

  (Plus non-GGUF entries: `BF16` directory (size 0), `.gitattributes`,
  `configuration.json`, `README.md` 6640, `config.json` 3760.)

**bartowski/Qwen3.8-27B-GGUF** (200; 26 model quants + 2 mmproj + 1 imatrix):

| File | Bytes | GiB |
|---|---|---|
| Qwen3.8-27B-IQ2_XXS.gguf | 9393043040 | 8.7 |
| Qwen3.8-27B-IQ2_XS.gguf | 9986799200 | 9.3 |
| Qwen3.8-27B-IQ2_S.gguf | 10295330400 | 9.6 |
| Qwen3.8-27B-IQ2_M.gguf | 10873357920 | 10.1 |
| Qwen3.8-27B-Q2_K.gguf | 11839440480 | 11.0 |
| Qwen3.8-27B-IQ3_XXS.gguf | 12626773600 | 11.8 |
| Qwen3.8-27B-Q2_K_L.gguf | 13081040480 | 12.2 |
| Qwen3.8-27B-IQ3_XS.gguf | 13330404960 | 12.4 |
| Qwen3.8-27B-IQ3_M.gguf | 13903517280 | 13.0 |
| Qwen3.8-27B-Q3_K_S.gguf | 13720344160 | 12.8 |
| Qwen3.8-27B-Q3_K_M.gguf | 14605735520 | 13.6 |
| Qwen3.8-27B-Q3_K_L.gguf | 15279445600 | 14.2 |
| Qwen3.8-27B-Q3_K_XL.gguf | 16391919200 | 15.3 |
| Qwen3.8-27B-Q4_0.gguf | 16348767840 | 15.2 |
| Qwen3.8-27B-IQ4_NL.gguf | 16325830240 | 15.2 |
| Qwen3.8-27B-IQ4_XS.gguf | 15567824480 | 14.5 |
| Qwen3.8-27B-Q4_K_S.gguf | 16713148000 | 15.6 |
| Qwen3.8-27B-Q4_K_M.gguf | 17772537440 | 16.6 |
| Qwen3.8-27B-Q4_1.gguf | 17825457760 | 16.6 |
| Qwen3.8-27B-Q4_K_L.gguf | 18716153440 | 17.4 |
| Qwen3.8-27B-Q5_K_S.gguf | 19680945760 | 18.3 |
| Qwen3.8-27B-Q5_K_M.gguf | 20752787040 | 19.3 |
| Qwen3.8-27B-Q5_K_L.gguf | 21537478240 | 20.1 |
| Qwen3.8-27B-Q6_K.gguf | 23463130720 | 21.9 |
| Qwen3.8-27B-Q6_K_L.gguf | 24078964320 | 22.4 |
| Qwen3.8-27B-Q8_0.gguf | 29116388960 | 27.1 |
| Qwen3.8-27B-imatrix.gguf | 13642688 | 0.01 |
| mmproj-Qwen3.8-27B-f16.gguf | 927607008 | 0.9 |
| mmproj-Qwen3.8-27B-bf16.gguf | 931145952 | 0.9 |

Summary table:

| Repo | Host | Code | GGUF files + sizes |
|---|---|---|---|
| Qwen/Qwen3.8-27B-GGUF | ModelScope | 404 | none (repo absent) |
| Qwen/Qwen3.8-27B-GGUF | HF | 000 | unreachable (curl exit 28) |
| Qwen/Qwen3.8-27B-MXFP4-GGUF | ModelScope | 404 | none (repo absent) |
| Qwen/Qwen3.8-27B-MXFP4-GGUF | HF | 000 | unreachable |
| unsloth/Qwen3.8-27B-GGUF | ModelScope | 200 | 21 quants 8.4–29.3 GiB (UD-IQ2_XXS → UD-Q8_K_XL) + 2 mmproj ~0.9 GiB |
| unsloth/Qwen3.8-27B-GGUF | HF | 000 | unreachable |
| bartowski/Qwen3.8-27B-GGUF | ModelScope | 200 | 26 quants 8.7–27.1 GiB (IQ2_XXS → Q8_0) + imatrix + 2 mmproj |
| bartowski/Qwen3.8-27B-GGUF | HF | 000 | unreachable |

- Runtime determination (the central tension: repos exist while naive
  `qwen3_5` greps of llama.cpp master return 0). Three independent probes:

  1. GGUF header of the actual artifact (Range request, first 128/512 bytes,
     parsed offline — HTTP 206, `content-range: bytes 0-127/17106775008`):

```console
$ curl -sL -m 30 -r 0-127 "https://modelscope.cn/api/v1/models/unsloth/Qwen3.8-27B-GGUF/repo?Revision=master&FilePath=Qwen3.8-27B-Q4_K_M.gguf"
(first 4 bytes: 47 47 55 46 = "GGUF"; version 3, tensor_count 866, kv_count 51)
kv[0] general.architecture = qwen35
kv[1] general.type = model
kv[5] general.name = Qwen3.8-27B
kv[8] general.quantized_by = Unsloth
```

     The embedded arch string is `qwen35` — exactly what llama.cpp master
     registers as `LLM_ARCH_QWEN35` (Q1). The quants target **upstream
     llama.cpp**, not a fork, and not any underscore alias.

  2. bartowski README (ModelScope raw, 14768 bytes), verbatim quotes
     (HTML link markup stripped, text otherwise unchanged):

```text
Using llama.cpp release b10419 for quantization.
...
These quants were made with llama.cpp release b10419 - if this model's
architecture is newly supported, you'll need that release or newer to run them.
They also work in: LM Studio · koboldcpp · ramalama · Jan AI ·
Text Generation Web UI · LoLLMs · Atomic Chat
```

     b10419 release timestamp (releases API, re-captured verbatim
     2026-08-16):

```console
$ fetch "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b10419" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['tag_name'], d['published_at'])"
b10419 2026-08-13T22:11:34Z
```

     The same README documents mmproj usage (`--mmproj`, auto-fetched with `-hf`) and
     MTP: "MTP layers act as a built-in draft model, letting llama.cpp run
     speculative decoding for faster generation. To use them, add the
     following flag to your llama.cpp command: `--spec-type draft-mtp`".

  3. unsloth README (ModelScope raw, 6640 bytes): "This GGUF uses Unsloth
     Dynamic V3.0 (preview) for SOTA quantization performance." and "MTP for
     fast inference is available." — no fork/runtime instructions, no
     non-llama.cpp runtime mentioned; it links unsloth.ai docs. The repo's
     `config.json` says `"architectures": ["Qwen3_5ForConditionalGeneration"]`,
     `"model_type": "qwen3_5"`, `mtp_num_hidden_layers: 1`, 64 layers,
     `full_attention_interval: 4`, `rope_parameters.mrope_section:
     [11, 11, 10]` — matching the converter defaults in Q3. The README
     (mirroring Qwen's model card) confirms the hybrid layout:
     "Hidden Layout: 16 x (3 x (Gated DeltaNet -> FFN) -> 1 x
     (Gated Attention -> FFN))", i.e. 48 linear-attention + 16 attention
     layers, native vision-language, 262,144-token context.

- Conclusion: **YES — ready-made Qwen3.8-27B GGUF quants exist on ModelScope
  from two independent quantizers (unsloth: 21 quants; bartowski: 26), with
  mmproj vision projectors, and they target upstream llama.cpp** (bartowski:
  release b10419 or newer, explicitly; unsloth: no fork instructions and the
  artifacts carry the upstream `qwen35` arch string). No official
  Qwen/Qwen3.8-27B-GGUF repo exists on ModelScope (404); HF codes are 000
  (host unreachable).
- SHA/date probed: probes run 2026-08-16; bartowski build release b10419
  2026-08-13T22:11:34Z; GGUF header read 2026-08-16.

## Q3 converter viability

- Probe (brief Step 3, as written — layout drift caveat applies):

```console
$ fetch https://raw.githubusercontent.com/ggml-org/llama.cpp/master/convert_hf_to_gguf.py | grep -n -i 'qwen3_5\|Qwen3_5ForConditionalGeneration\|qwen3_next'
(no matches — file is 12798 bytes; the monolithic converter was refactored
into a conversion/ package: `from conversion import (...)` at its top)
```

  Corrected target — `conversion/qwen.py` at the pinned SHA (32668 bytes;
  first raw fetch needed its 3rd retry):

```console
$ fetch https://raw.githubusercontent.com/ggml-org/llama.cpp/4df29be4f4c3673f428170fda944a5b19f743bb8/conversion/qwen.py | grep -n -i 'qwen35\|qwen3_5\|qwen3next\|qwen3_next'
364:@ModelBase.register("Qwen3NextForCausalLM")
365:class Qwen3NextModel(_QwenMtpMixin, Qwen2MoeModel):
366:    model_arch = gguf.MODEL_ARCH.QWEN3NEXT
438:class _LinearAttentionVReorderBase(Qwen3NextModel):
439:    model_arch = gguf.MODEL_ARCH.QWEN3NEXT  # overridden by subclasses
606:class _Qwen35MRopeMixin:
622:@ModelBase.register("Qwen3_5ForConditionalGeneration", "Qwen3_5ForCausalLM")
623:class Qwen3_5TextModel(_Qwen35MRopeMixin, _LinearAttentionVReorderBase):
624:    model_arch = gguf.MODEL_ARCH.QWEN35
627:@ModelBase.register("Qwen3_5MoeForConditionalGeneration", "Qwen3_5MoeForCausalLM")
628:class Qwen3_5MoeTextModel(_Qwen35MRopeMixin, _LinearAttentionVReorderBase):
629:    model_arch = gguf.MODEL_ARCH.QWEN35MOE
```

  So `convert_hf_to_gguf.py` (via `conversion/qwen.py`) recognizes
  `Qwen3_5ForConditionalGeneration` — exactly the architecture string in
  Qwen3.8-27B's config — and maps it to GGUF arch `qwen35`. The MRoPE mixin
  comment in the same file even documents the interlock with our model:
  "llama.cpp's QWEN35 / QWEN35MOE loaders treat
  qwen35.rope.dimension_sections as required" with default `[11, 11, 10, 0]`
  — and the unsloth repo config carries `mrope_section: [11, 11, 10]`.
  Hybrid tensor handling (`in_proj_qkvz`, `in_proj_z`, `in_proj_a`,
  `in_proj_b`, split/reorder) is present at lines 465-468, 525-539, 563-577.

- Issue-thread search (GitHub API — WebSearch unavailable in this session;
  pipeline reformats JSON to `number [state] title`, re-captured verbatim
  2026-08-16, output identical to the original probe):

```console
$ fetch "https://api.github.com/search/issues?q=repo:ggml-org/llama.cpp+qwen3_5&per_page=10" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('total_count:', d['total_count']); [print('#%d [%s] %s' % (i['number'], i['state'], i['title'])) for i in d['items']]"
total_count: 7
#27019 [open] convert_hf_to_gguf: Qwen3.5 (qwen3_5) hybrid linear-attention tensors fail - ssm_conv1d kernel dim + in_proj_a/b expansion not handled
#27132 [open] fix(convert): qwen3_5 hybrid linear-attention tensors - ssm_conv1d kernel dim + in_proj_a/b layout
#26916 [open] Eval bug: Qwen3.5-Hybrid model (qwen3_5, SSM+Attention) fails to load — "tensor 'blk.32.attn_norm.weight' not found"
#24541 [closed] Eval bug: EAGLE3 with Qwen3.6 (qwen3_5 hybrid) target — missing t_layer_inp hooks, and llama_decode(ctx_dft) rc=-1 once context exceeds ~700 tokens
#24492 [open] Eval bug: Gemma 4 31B MTP (draft-mtp) crashes on Vulkan backend, pre-allocated tensor cannot run operation NONE
#19435 [closed] [Model] Qwen3.5 dense and MoE support (no vision)
#20143 [closed] Eval bug: ggml_repeat_4d undefined at runtime despite being exported in libggml-base.so
```

  Status of the load-bearing items. Pulls-API state for both PRs first
  (re-captured verbatim 2026-08-16; `[closed]` in the search listing above
  does not by itself establish a merge — the pulls API's `merged` field does):

```console
$ fetch "https://api.github.com/repos/ggml-org/llama.cpp/pulls/19435" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['number'], d['state'], 'merged:', d['merged'], d['merged_at'], '|', d['title'])"
19435 closed merged: True 2026-02-08T23:24:08Z | [Model] Qwen3.5 dense and MoE support (no vision)

$ fetch "https://api.github.com/repos/ggml-org/llama.cpp/pulls/27132" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['number'], d['state'], 'merged:', d['merged'], d['merged_at'], '|', d['title'])"
27132 open merged: False None | fix(convert): qwen3_5 hybrid linear-attention tensors - ssm_conv1d kernel dim + in_proj_a/b layout
```

  - #19435 (the support PR, merged 2026-02-08T23:24:08Z): "It's mostly
    based on Qwen3Next, but it's rebased on the common-delta-net PR
    ( #19125 )".
  - #27019 (open, filed 2026-08-13, conversion RuntimeError on
    Qwen/Qwen3.5-9B at master and b10333): latest comment (2026-08-15)
    gives root cause and workaround — the derived MTP/nextn block inflates
    the layer count ("33 blocks vs the 32 in the reference GGUF. Use
    `--no-mtp`"); in_proj_a/b was the secondary symptom (already expanded
    in HF — a transpose, not an expansion, is needed).
  - #27132 (open PR, 2026-08-15, labels conversion): "Fixes #27019 ...
    I have tested the changes locally (Qwen3.5-9B converted and loaded
    successfully with llama-server)". NOT merged at probed HEAD
    4df29be (2026-08-16T12:53:13Z).
  - #26916 (open, 2026-08-11, load failure "tensor 'blk.32.attn_norm.weight'
    not found"): maintainer reply — "this is a model issue. You can work
    around it with `--no-mtp` though."
  - Context: bartowski produced the full set (26 quants + imatrix + 2 mmproj,
    per the Q2 listing) with release b10419 (2026-08-13), so conversion with
    that upstream release demonstrably worked for at least one quantizer by
    that date.

  The fetches behind the two quoted issue comments (issue-comments API,
  re-captured verbatim 2026-08-16; full comment bodies, unedited):

```console
$ fetch "https://api.github.com/repos/ggml-org/llama.cpp/issues/27019/comments" \
    | python3 -c "import json,sys; [print(c['created_at'], c['user']['login'], '('+c['author_association']+'):\n'+c['body']) for c in json.load(sys.stdin)]"
2026-08-15T13:20:42Z nurdilesbek (NONE):
## Update (2026-08-14) - root cause found, workaround works

After deep debugging I can add the full diagnosis:

1. **The MTP block**: Qwen3.5 configs lack `num_hidden_layers`; the `_QwenMtpMixin` derives it and can add a speculative (nextn) block, producing 33 blocks vs the 32 in the reference GGUF. Use `--no-mtp`.
2. **in_proj_a/b are ALREADY expanded in HF**: `[32, 4096]` (num_v_heads x dim), not `[k_heads*dim, 1]`. The GGUF wants `[dim, num_v_heads]` with k-major v ordering (v = k*v_per_k + j, per `llama-model.cpp` get_tensor_meta_split grouping `{{n_k_heads, head_ratio}}`). So the a/b transform is a simple transpose `[32,4096] -> [4096,32]`, no expansion.
3. **ssm_conv1d**: `[8192, 1, 4]` (qk+v rows, kernel 4); the V-reorder must preserve the kernel dim.
4. **gguf-py lazy gotcha**: `torch.transpose` on LazyTorchTensor does not survive the write path (numpy materialization loses the op; `--no-lazy` fixes it but OOMs on 18GB models in RAM-constrained environments). For small-memory machines a post-process mmap patch (swap dims in header + in-place transpose) works.

With `--no-mtp` + the a/b transpose + the conv kernel fix (or the post-process patch), the conversion succeeds and the GGUF loads in llama-server. I'll open a PR with the converter-side fixes.

Reference layouts from the working unsloth GGUF: ssm_alpha/ssm_beta `[4096,32]`, ssm_conv1d `[4,8192]`.

$ fetch "https://api.github.com/repos/ggml-org/llama.cpp/issues/26916/comments" \
    | python3 -c "import json,sys; [print(c['created_at'], c['user']['login'], '('+c['author_association']+'):\n'+c['body']) for c in json.load(sys.stdin)]"
2026-08-12T07:12:28Z CISC (MEMBER):
If the model does not include MTP layers it must say so in it's config (`mtp_num_hidden_layers` must be 0), this is a model issue.

You can work around it with `--no-mtp` though.
```

- Conclusion: **viable with a caveat.** The converter registers
  `Qwen3_5ForConditionalGeneration` and emits arch `qwen35` upstream, and
  two independent parties have produced complete quant sets from upstream
  releases (bartowski explicitly with b10419). But there are OPEN, recent
  (Aug 2026) bug reports against conversion (#27019) and loading (#26916)
  of hybrid qwen3_5 checkpoints at master, both diagnosed as MTP-block
  layer-count handling with `--no-mtp` as the documented workaround, and a
  fix PR (#27132) that was still unmerged at the probed HEAD. If we convert
  locally we should build from master + #27132 (or newer release once it
  lands) and be ready to pass `--no-mtp` / exclude draft layers; if we
  consume the existing quants, none of this matters.
- SHA/date probed: converter file at
  `4df29be4f4c3673f428170fda944a5b19f743bb8` (2026-08-16); issue states as
  of the 2026-08-16 API fetches.

## Impact

The Phase 2 GGUF plan is in better shape than the controller's initial
`qwen3_5` grep suggested — that grep missed support that ships under the
name `qwen35`. Upstream llama.cpp has supported the architecture since
2026-02-08 (PR #19435: dense + MoE, Gated-DeltaNet hybrid, MRoPE, MTP
draft), it is in the current release line (verified in b10453, and bartowski
built with b10419), and there is no fork requirement of any kind: both
existing quant sets carry the plain upstream `general.architecture=qwen35`
string, verified by parsing the GGUF header bytes ourselves. Concretely for
Phase 2: (1) prefer consuming ready-made quants — on this host only
ModelScope is reachable, and it hosts unsloth (21 quants, 8.4-29.3 GiB) and
bartowski (26 quants, 8.7-27.1 GiB), both including mmproj vision
projectors and MTP-inclusive weights (`--spec-type draft-mtp`); no official
Qwen GGUF repo exists (404) and HF is unreachable from here (000), so
downloads must go through ModelScope; (2) the 48 GB W7900 fits every quant
up to and including UD-Q8_K_XL (29.3 GiB) fully in VRAM, with Q4_K_M-class
(15.9-16.6 GiB) leaving ample room for KV/ctx — noting the recurrent
Gated-DeltaNet layers reduce KV pressure vs a pure-attention model; (3) if
local conversion from the BF16 base is ever needed, expect the open
MTP-layer-count conversion bugs (#27019/#26916, fix #27132 unmerged at the
probed HEAD) and plan for `--no-mtp` or a post-#27132 build; (4) the ROCm/
gfx1100 viability of llama.cpp itself (Vulkan vs ROCm/HIP backend on
RDNA3) remains untested by this spike and is the actual next unknown —
nothing probed here gates on it.
