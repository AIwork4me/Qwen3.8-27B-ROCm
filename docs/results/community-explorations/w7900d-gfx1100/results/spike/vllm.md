# Spike A: vLLM + transformers support for qwen3_5 — 2026-08-16

Pure upstream recon. All probes run 2026-08-16 from the radeon-cloud host
via the Global-Constraints `fetch` retry helper (3 attempts, 30-60 s curl
timeouts). raw.githubusercontent.com was flaky (repeated mid-transfer
timeouts); every evidence item below eventually fetched intact — persistent
3-retry failures are recorded where they happened. huggingface.co is
unreachable from this host and was not needed for these probes; recorded
status for completeness:

```console
$ curl -s -o /dev/null -m 15 -w '%{http_code}\n' "https://huggingface.co/api/models/Qwen/Qwen3.8-27B"
000   (curl exit 28, timeout)
```

## Q1: transformers support

- Probe (brief Step 1, as written):

```console
$ fetch "https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/auto/configuration_auto.py" \
    | grep -n 'qwen3_5\|Qwen3_5' | head -20
(no matches)
```

  FINDING: this probe is stale, not evidence of absence. On transformers main
  the mapping tables moved out of `configuration_auto.py`:

```console
$ grep -n 'auto_mappings' /tmp/t_cfg_auto.py   # saved copy of the fetched file (19788 bytes)
26:from .auto_mappings import CONFIG_MAPPING_NAMES, SPECIAL_MODEL_TYPE_TO_MODULE_NAME
```

- Probe (corrected target, `auto_mappings.py` on main, pinned identical at
  SHA `95940bf8775059a42f047256f076e4f607bc43ec`):

```console
$ fetch "https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/auto/auto_mappings.py" \
    | grep -n 'qwen3_5\|Qwen3_5' | head -20
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

- Probe (model dir + latest commit on it):

```console
$ fetch "https://api.github.com/repos/huggingface/transformers/commits?path=src/transformers/models/qwen3_5&per_page=1" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date']) if d else print('no qwen3_5 model dir')"
95940bf8775059a42f047256f076e4f607bc43ec 2026-08-14T11:45:57Z
```

```console
$ fetch "https://api.github.com/repos/huggingface/transformers/contents/src/transformers/models/qwen3_5?ref=main" \
    | python3 -c "import json,sys; [print(x['name'], x['size']) for x in json.load(sys.stdin)]"
__init__.py 1035
configuration_qwen3_5.py 8266
modeling_qwen3_5.py 88546
modular_qwen3_5.py 28781
tokenization_qwen3_5.py 3127
```

  Key classes in main `modeling_qwen3_5.py` (grep '^class '):
  `Qwen3_5ForCausalLM` (line 1576) and `Qwen3_5ForConditionalGeneration`
  (line 1673), plus hybrid-attention plumbing `Qwen3_5GatedDeltaNet`
  (line 387) — the Qwen3-Next-style linear-attention lineage.

- Probe (release check at tag v5.8.0):

```console
$ fetch "https://raw.githubusercontent.com/huggingface/transformers/v5.8.0/src/transformers/models/auto/auto_mappings.py" \
    | grep -c 'qwen3_5'
10
$ fetch "https://raw.githubusercontent.com/huggingface/transformers/v5.8.0/src/transformers/models/auto/auto_mappings.py" \
    | grep -n '("qwen3_5", "Qwen3_5Config")'
474:        ("qwen3_5", "Qwen3_5Config"),
$ fetch "https://api.github.com/repos/huggingface/transformers/contents/src/transformers/models/qwen3_5?ref=v5.8.0" \
    | python3 -c "import json,sys; [print(x['name'], x['size']) for x in json.load(sys.stdin)]"
__init__.py 1035
configuration_qwen3_5.py 7572
modeling_qwen3_5.py 97465
modular_qwen3_5.py 27041
tokenization_qwen3_5.py 3127
$ fetch "https://raw.githubusercontent.com/huggingface/transformers/v5.8.0/src/transformers/models/auto/configuration_auto.py" \
    | grep -c 'qwen3_5'
0
```

  (`grep -c` prints 0 and exits 1 when there are no matches — at v5.8.0
  the brief's `configuration_auto.py` probe gives 0 hits because the tag
  already uses the `auto_mappings.py` layout, same as main.)
- Conclusion: **supported on transformers main AND released in v5.8.0** —
  `qwen3_5` config/tokenizer/modeling files ship in the tag, registered as
  `("qwen3_5", "Qwen3_5Config")` at line 474 of the v5.8.0
  `auto_mappings.py`.
- SHA/date probed: transformers main dir-commit
  `95940bf8775059a42f047256f076e4f607bc43ec` 2026-08-14T11:45:57Z;
  tag `v5.8.0`; probes run 2026-08-16.

## Q2: vLLM architecture registration

- Probe (registry at main, then byte-identical re-fetch pinned at the
  recorded HEAD):

```console
$ fetch "https://api.github.com/repos/vllm-project/vllm/commits?per_page=1" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date'])"
83f591d7f694a3ca3ae3bf22d646e818a1421872 2026-08-16T15:24:14Z

$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/model_executor/models/registry.py" \
    | grep -n -i 'qwen3_5\|qwen3_next' | head -20
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

$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/model_executor/models/registry.py" \
    | diff - /tmp/v_registry.py && echo IDENTICAL
IDENTICAL
```

  Dict placement in registry.py: lines 203-204 sit in
  `_TEXT_GENERATION_MODELS` (opens line 72); lines 592-595 sit in
  `_MULTIMODAL_MODELS` (opens line 347); lines 681-682 sit in
  `_SPECULATIVE_DECODING_MODELS` (opens line 618). Case-insensitive
  count: `grep -c -i 'qwen3_5'` = 9 (matches controller pre-knowledge;
  plain `grep -c 'qwen3_5'` = 7 module-name lines).

- Probe (model file existence):

```console
$ curl -s -o /dev/null -m 30 -w '%{http_code}\n' \
    "https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/model_executor/models/qwen3_5.py"
200
```

- FINDING (stale probe in brief): `vllm/config.py` is 404 on main — config
  became the `vllm/config/` package; MTP config lives in
  `vllm/config/speculative.py` (see Q3):

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/config.py"
curl: (22) The requested URL returned error: 404   (x3 retries)
```

- Release check (latest tag):

```console
$ fetch "https://api.github.com/repos/vllm-project/vllm/releases?per_page=3" \
    | python3 -c "import json,sys; [print(r['tag_name'], r['published_at']) for r in json.load(sys.stdin)]"
v0.27.1 2026-08-11T10:47:49Z
v0.27.0 2026-08-10T21:18:11Z
v0.26.0 2026-07-27T01:06:58Z

$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/v0.27.1/vllm/model_executor/models/registry.py" \
    | grep -n 'Qwen3_5ForConditionalGeneration\|"Qwen3_5'
201:    "Qwen3_5ForCausalLM": ("qwen3_5", "Qwen3_5ForCausalLM"),
202:    "Qwen3_5MoeForCausalLM": ("qwen3_5", "Qwen3_5MoeForCausalLM"),
581:    "Qwen3_5ForConditionalGeneration": ("qwen3_5", "Qwen3_5ForConditionalGeneration"),
582:    "Qwen3_5MoeForConditionalGeneration": (
584:        "Qwen3_5MoeForConditionalGeneration",
660:    "Qwen3_5MTP": ("qwen3_5_mtp", "Qwen3_5MTP"),
661:    "Qwen3_5MoeMTP": ("qwen3_5_mtp", "Qwen3_5MoeMTP"),
```

- Conclusion: **registered** — `Qwen3_5ForConditionalGeneration` maps to
  module `qwen3_5` in `_MULTIMODAL_MODELS`, `vllm/model_executor/models/qwen3_5.py`
  exists (HTTP 200), at probed commit
  `83f591d7f694a3ca3ae3bf22d646e818a1421872` (2026-08-16) AND already in
  released v0.27.1 (2026-08-11).
- SHA/date probed: vLLM main `83f591d7f694a3ca3ae3bf22d646e818a1421872`
  2026-08-16T15:24:14Z; tag `v0.27.1`.

## Q3: MTP support in vLLM for qwen3_5

- Evidence 1 — speculative-decoding registry entries (same pinned commit;
  `_SPECULATIVE_DECODING_MODELS`, registry.py lines 681-682, quoted in Q2):

```text
681:    "Qwen3_5MTP": ("qwen3_5_mtp", "Qwen3_5MTP"),
682:    "Qwen3_5MoeMTP": ("qwen3_5_mtp", "Qwen3_5MoeMTP"),
```

- Evidence 2 — draft model implementation file exists (existence check via
  the moving `main` ref; class listing fetched at the pinned commit):

```console
$ curl -s -o /dev/null -m 30 -w '%{http_code}\n' \
    "https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/model_executor/models/qwen3_5_mtp.py"
200

$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/model_executor/models/qwen3_5_mtp.py" \
    | grep -n '^class '
64:class Qwen3_5MultiTokenPredictor(nn.Module):
211:class Qwen3_5MTP(LocalArgmaxMixin, nn.Module, SupportsMultiModal):
316:class Qwen3_5MoeMTP(Qwen3_5MTP, QwenNextMixtureOfExperts):
```

- Evidence 3 — speculative config auto-wiring
  (`vllm/config/speculative.py`; note the `vllm/config.py` 404 finding in
  Q2). `MTPModelTypes` membership (full `head -10` output):

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/config/speculative.py" \
    | grep -n -i 'mtp' | head -10
37:MTPModelTypes = Literal[
38:    "deepseek_mtp",
39:    "dots3_note_mtp",
40:    "mimo_mtp",
41:    "mimo_v2_mtp",
42:    "glm4_moe_mtp",
43:    "glm4_moe_lite_mtp",
44:    "glm_ocr_mtp",
45:    "ernie_mtp",
46:    "nemotron_h_mtp",
```

  (`head -10` truncates inside the same Literal. The exact
  `"qwen3_5_mtp"` line matches in the pinned file:)

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/config/speculative.py" \
    | grep -n '"qwen3_5_mtp"'
50:    "qwen3_5_mtp",
561:            hf_config.model_type = "qwen3_5_mtp"
580:            hf_config.model_type = "qwen3_5_mtp"
```

  (line 580 is the analogous remap for Intern-S2/Mobius checkpoints that
  embed a `qwen3_5_moe_text` draft; line 561 is the direct qwen3_5 path.)
  The auto-remap block in full, with its own command:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/config/speculative.py" \
    | grep -n -B11 -A6 'n_predict = getattr(hf_config, "mtp_num_hidden_layers"'
551-        if hf_config.model_type in (
552-            "qwen3_5",
553-            "qwen3_5_moe",
554-            "qwen3_5_text",
555-            "qwen3_5_moe_text",
556-        ):
557-            # Checkpoints that ship only the text config resolve to the
558-            # `qwen3_5_text` / `qwen3_5_moe_text` model types and carry the
559-            # same `mtp_num_hidden_layers` field as the multimodal ones.
560-            is_moe = hf_config.model_type in ("qwen3_5_moe", "qwen3_5_moe_text")
561-            hf_config.model_type = "qwen3_5_mtp"
562:            n_predict = getattr(hf_config, "mtp_num_hidden_layers", None)
563-            hf_config.update(
564-                {
565-                    "n_predict": n_predict,
566-                    "architectures": ["Qwen3_5MoeMTP" if is_moe else "Qwen3_5MTP"],
567-                }
568-            )
```

- Conclusion: **MTP is fully wired upstream** for qwen3_5: a draft
  architecture is registered in `_SPECULATIVE_DECODING_MODELS`, the draft
  module `qwen3_5_mtp.py` implements `Qwen3_5MTP`/`Qwen3_5MoeMTP`, and the
  speculative config auto-remaps any `qwen3_5*` draft checkpoint to the MTP
  path, reading `n_predict` from `mtp_num_hidden_layers`. Present in
  released v0.27.1 as well (registry lines 660-661 above).
- Pinning note: Evidence 1 (registry.py) was fetched at `main` and
  byte-verified at `83f591d` (see Q2). Evidence 2 (qwen3_5_mtp.py) and
  Evidence 3 (speculative.py) were originally fetched at
  main-at-probe-time, minutes before HEAD `83f591d` was recorded; in fix
  round 1 both were re-fetched at the pinned SHA and were byte-identical
  to the originals, and the quoted outputs above come from those pinned
  re-fetches. The only remaining moving-ref item is the HTTP-200 existence
  check on `main`.
- SHA/date probed: vLLM main `83f591d7f694a3ca3ae3bf22d646e818a1421872`
  2026-08-16 (all quoted Q3 content pinned at this SHA).

## Q4: ROCm/gfx1100 angle

- URL 1 — vLLM install docs (fetched 2026-08-16):
  https://docs.vllm.ai/en/stable/getting_started/installation/gpu/
  - Claims: "vLLM supports AMD GPUs with ROCm 6.3 or above." and
    "Pre-built wheels are available for ROCm 7.0 and ROCm 7.2.1."
  - Supported-GPU list explicitly includes "Radeon RX 7900 series
    (gfx1100/1101)" — i.e. our W7900's ASIC family is a first-class target
    of the generic ROCm story — but W7900 is not named specifically.
  - Does NOT mention Qwen3.5/Qwen3.8 anywhere (only Qwen3-0.6B as a Docker
    example).
- URL 2 — AMD Day-0 article (fetched 2026-08-16 with curl + browser UA):
  https://www.amd.com/en/developer/resources/technical-articles/2026/day-0-support-for-qwen-3-8-on-amd-instinct-gpus.html
  - "Aug 12, 2026 AMD is excited to announce Day-0 support for Alibaba's
    latest Qwen 3.8 model family on AMD Instinct™ MI300X, MI325X, and
    MI355X GPUs. Developers can immediately deploy and evaluate Qwen 3.8
    using the AMD ROCm™ software together with SGLang and vLLM."
  - Runbook is Instinct-scale: `docker pull vllm/vllm-openai-rocm:qwen38`,
    `export VLLM_ROCM_USE_AITER=1`, TP=8/PP=2 across two MI355X nodes.
  - Qwen3.8-2.4T MTP is quantized via Quark with template
    `LLMTemplate.get("qwen3_5_moe_text")` — confirming Qwen3.8 checkpoints
    ride the `qwen3_5` architecture family.
  - Zero occurrences of RDNA / gfx11 / gfx9 / W7900 / 7900 in the article.
- URL 3 — AMD Radeon/Qwen3.8-27B blog (fetched 2026-08-16 with curl):
  https://www.amd.com/en/blogs/2026/run-qwen-3-8-27b-on-amd-ryzen-ai-max-and-radeon-graphics-cards-day-0.html
  - "Aug 14, 2026 Today, AMD is delivering Day 0 support for Qwen3.8 27B,
    giving developers a path to run this state-of-the-art dense model
    locally on AMD-powered PCs and workstations" — measured "up to 51.8
    tokens per second on a single AMD Radeon™ AI PRO R9700".
  - BUT the vehicle is LM Studio / Lemonade, not vLLM; the tested Radeon
    card is RDNA4 (R9700); zero occurrences of gfx1100 / RDNA / W7900 /
    7900 / GGUF.
- URL 4 — vLLM ROCm attention blog (fetched 2026-08-16):
  https://vllm.ai/blog/2026-02-27-rocm-attention-backend
  - Targets "AMD CDNA™ 3 architecture hardware (AMD Instinct™ MI300X,
    Instinct MI325X, Instinct MI355X GPUs)"; all headline speedups
    (ROCM_AITER_FA 2.7-4.4x etc.) are AITER/MI-class numbers.
  - For us the operative quote: TRITON_ATTN and ROCM_ATTN have "Radeon GPU
    support," "useful for consumer hardware deployments where AITER
    primitives aren't available" — i.e. gfx1100 runs the non-AITER path.
- URL 5 — vLLM platform source, `vllm/platforms/rocm.py` at probed commit
  `83f591d7f694a3ca3ae3bf22d646e818a1421872`:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/platforms/rocm.py" \
    | grep -n 'gfx1100\|RDNA'
219:_ON_GFX1100 = "gfx1100" in _GCN_ARCH
230:# RDNA = gfx11/gfx12 minus the CDNA-classified gfx1250.
231:_ON_RDNA = _ON_GFX1X and not _ON_CDNA
451:                "Flash Attention Triton backend on RDNA."
```

  Gating quote from the same file: on RDNA the Flash Attention Triton
  backend logs "Set FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE to enable Flash
  Attention Triton backend on RDNA." and is disabled by default; MHA
  backend priority without AITER falls through to ROCM_ATTN / TRITON_ATTN.
- URL 6 — open gfx1100 correctness precedent (GitHub API, fetched
  2026-08-16): https://github.com/vllm-project/vllm/issues/39348
  - `[Bug]: Qwen3.5-9B-AWQ on ROCm/vLLM 0.19.0 can get stuck generating
    endless "!" inside JSON schema output` — state: open, labels
    `bug, rocm, stale`, created 2026-04-08, reporter GPU: "Navi 31
    [Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M]" (gfx1100).
- Conclusion: vLLM's generic ROCm path lists gfx1100 (RX 7900 series) and
  ships ROCm 7.2.1 pre-built wheels (matching this host's ROCm 7.2.1), but
  NOBODY — not AMD Day-0, not vLLM docs/blogs — validates Qwen3.8/qwen3_5
  on RDNA3; AMD's Qwen3.8-27B Radeon Day-0 is LM Studio on RDNA4. On
  gfx1100 we run the non-AITER attention path with at least one open
  Qwen3.5-on-RDNA3 correctness bug in the wild.
- SHA/date probed: vLLM `83f591d` 2026-08-16; docs/blogs fetched
  2026-08-16; AMD articles dated 2026-08-12 (Instinct) and 2026-08-14
  (Radeon/LM Studio).

## Impact

The Phase 1 vLLM path needs no fork and no day-0 port: transformers v5.8.0
and vLLM v0.27.1/main (probed at `83f591d`, 2026-08-16) both ship
`qwen3_5` end-to-end — including `Qwen3_5ForConditionalGeneration`, the
`Qwen3_5MTP`/`Qwen3_5MoeMTP` speculative-decoding draft with
config-driven `mtp_num_hidden_layers` auto-wiring — and vLLM publishes
ROCm 7.2.1 wheels that match this host's ROCm 7.2.1 stack. The risk is not
registration, it is silicon coverage: every AMD/vLLM Qwen3.8 validation is
CDNA3 (MI300X/MI325X/MI355X + AITER) or RDNA4-via-LM-Studio; gfx1100 gets
the generic TRITON_ATTN/ROCM_ATTN fallback path, the RDNA Flash Attention
Triton backend is opt-in behind `FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`,
and issue #39348 shows a real open Qwen3.5-on-RX7900 degeneration bug. So
Phase 1 should pin vLLM v0.27.1 (or main-at-`83f591d`) + transformers
v5.8.0, plan attention-backend env-var experiments explicitly, treat MTP
speculative decoding as a stretch goal behind a correctness smoke test
(structured/JSON output) that must pass before any throughput tuning, and
budget a llama.cpp fallback (Spike B) if gfx1100 kernels misbehave.
