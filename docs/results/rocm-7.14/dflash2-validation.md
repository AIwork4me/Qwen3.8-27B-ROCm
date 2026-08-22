# DFlash2 validation receipts — 2026-08-21
## Boot

Attempt 1 (unpatched vLLM, ctx 262144) FAILED at config validation: the
pinned tree (`4d2a68d` + the two stack patches) has DFlash **v1** support
only. Verbatim from `/tmp/dflash-boot.log`:

    pydantic_core._pydantic_core.ValidationError: 1 validation error for SpeculativeConfig
      Value error, Model architectures ['DFlash2DraftModel'] are not supported for now. Supported architectures: dict_keys([..., 'DFlashDraftModel', ..., 'DSparkDraftModel', ...])

Root cause: the draft checkpoint (incoai/Qwen3.8-27B-DFlash2, fetched via
`SET=dflash2-bf16 scripts/02-fetch-model.sh`, SHA256-verified) declares
`architectures: ["DFlash2DraftModel"]` (config.json, `is_causal: false`,
5 layers, sliding_window 2048, `dflash_config` with selector/conv params);
DFlash2 upstream support is vLLM PR
[#52816](https://github.com/vllm-project/vllm/pull/52816) ("[Spec Decode]
DFlash2: local convolution + candidate selector", OPEN at port time), based
on a main newer than our pin. See "## Patch port".

Attempt 2 (patched, ctx 262144) FAILED at the KV budget on the 80 GiB pool:
the draft's 3.6 GiB weights + its non-causal KV group shrink the usable KV
below the 262144 requirement. Verbatim from `/tmp/dflash-boot2.log`:

    (EngineCore pid=24446) INFO 08-21 10:02:34 [model_runner.py:380] Model loading took 54.84 GiB memory and 40.216174 seconds
    (EngineCore pid=24446) ERROR 08-21 10:03:35 [core.py:1346] ValueError: To serve at least one request with the model's max seq len (262144), (21.63 GiB KV cache is needed, which is larger than the available KV cache memory (15.46 GiB). Based on the available memory, the estimated maximum model length is 181376.

For comparison the base boot budgets 19.54 GiB KV at 262144
(vllm-validation.md) — DFlash2 both consumes ~3.7 GiB more at load
(54.84 vs 51.1 GiB) and needs ~2.1 GiB more KV (21.63 vs 19.54 GiB) for
the same tier. `gpu_memory-utilization` headroom cannot cover the gap (the
engine's own suggestion is max-len 181376 — between the declared tiers).

Attempt 3 (patched, ctx 131072 via the documented `MAX_MODEL_LEN`
pass-through) SUCCEEDED:

- server: http://127.0.0.1:8000
- health: ok (first healthy poll ~330 s — comparable to base/mtp boots)
- conf: configs/serve-args-dflash2.conf (baseline flags +
  `--speculative-config {"method":"dflash","model":"models/Qwen3.8-27B-DFlash2","num_speculative_tokens":7}`)
- env: MAX_MODEL_LEN=131072

Log evidence (`/tmp/dflash-boot3.log`):
    (APIServer pid=30952) INFO 08-21 10:16:02 [model.py:672] Resolved architecture: DFlash2DraftModel
    (EngineCore pid=31298) INFO 08-21 10:17:00 [speculator.py:182] WARNING Draft model DFlash2Qwen3ForCausalLM does not support external multimodal embeddings. Embeddings from the target model will not be passed to the drafter; using text-only draft inputs instead.
    (EngineCore pid=31298) INFO 08-21 10:17:02 [model_runner.py:380] Model loading took 54.84 GiB memory and 42.380348 seconds
    (EngineCore pid=31298) INFO 08-21 10:17:50 [kv_cache_utils.py:1869] GPU KV cache size: 174,643 tokens, Maximum concurrency for 131,072 tokens per request: 1.33x
    (EngineCore pid=31298) INFO 08-21 10:20:16 [speculator.py:140] Capturing model for DFlash2 speculator...
    (EngineCore pid=31298) INFO 08-21 10:20:23 [model_runner.py:906] Graph capturing finished in 151 secs, took 1.42 GiB
    (EngineCore pid=31298) INFO 08-21 10:20:23 [gpu_worker.py:804] Free memory on device (79.99/80.0 GiB) on startup. Desired GPU memory utilization is (0.92, 73.6 GiB). Actual usage is 55.62 GiB for consumed memory (weights + non-torch), 2.53 GiB for peak activation, and 1.42 GiB for CUDAGraph memory. ... Current kv cache memory in use is 15.46 GiB.

ROCm note (the open feasibility question answered): the DFlash2 speculator
runs on gfx1151 with the conf's `--attention-backend TRITON_ATTN` — the
non-causal draft attention needs no separate draft backend on this stack.

## Patch port

`patches/vllm-dflash2-pr52816.diff` carries upstream PR
[#52816](https://github.com/vllm-project/vllm/pull/52816) (OPEN at port
time, 2026-08-21) onto the pin `4d2a68d`: the `DFlash2DraftModel` registry
entry (`qwen3_dflash2.DFlash2Qwen3ForCausalLM`), the V2-forcing config hook
(`_is_dflash2_draft` — the candidate selector exists only in the V2
speculator), the dflash2 worker (`v1/worker/gpu/spec_decode/dflash2/`), and
the routing insertion. Two deviations from the PR, both mechanical: the
routing hunk is hand-ported (the PR's base has an `extract_hidden_states`
branch the pin lacks) and upstream test churn (`tests/test_config.py`,
`tests/models/registry.py`) is not carried — the patch contains only the
`vllm/` production files. Pure Python: no C++/Triton rebuild; the editable
install picks it up directly. Roundtrip-verified (reverse-apply → pristine
→ forward-apply → byte-identical); listed in
`configs/validated-stack.json` vllm.patches; applied idempotently by
`scripts/01-build-vllm.sh` (whose tracked-modification guard now also
enumerates untracked files — patches may create files).

## Greedy smoke

- prompt: qwen3.8-27b, temperature=0, max_tokens=512 (wall 2.2 s)
- finish_reason: stop
- reasoning: 'We need to respond to user: "Reply with exactly: OK". Need final exactly OK. No extra.\n'
- content: '\n\nOK'

Byte-identical to the base/mtp greedy anchor recorded in
`configs/serve-args.conf` (same reasoning text, same content) — the
lossless-speculation claim holds on this smoke; the corpus cells' greedy
anchor gate (`run-cell-vllm.sh --anchor-only`, byte-identity vs the stored
anchor) is the formal check.

## KV budget

- dflash @262144: 21.63 GiB KV needed vs 15.46 available → boot refuses
  (engine max-len estimate 181376 — between declared tiers; not offered)
- dflash @131072: boots; KV 15.46 GiB = 174,643 tokens = 1.33x the tier
  (a single full-depth 131072 stream fits; two do not — the same
  KV-budget-bound concurrency shape as the base path at 262144)
- consequence recorded in the matrix: the dflash pairing cells are
  re-tiered to ctx131072 (`gen-matrix.py` NEW_CELLS_V019, reason carries
  these numbers); the corpus base/mtp cells remain the 262144 story

## n-max sweep (2026-08-22)

`scripts/probe-vllm-dflash2-nmax-sweep.sh` — 6 fresh boots (base, mtp,
dflash at SPEC_N 2/3/4/7), all @131072, the cells' exact bench command;
dflash arms = median of 3 runs. Receipt:
`../matrix-714/stability/dflash-nmax-sweep-2026-08-22/`.

| Arm | Median tok/s | Runs |
|---|---|---|
| base-c1 (control) | 4.15 | single |
| mtp-c1 (control) | 6.22 | single |
| dflash n=2 | 7.68 | 7.68 / 7.53 / 7.75 |
| dflash n=3 | 7.37 | 7.62 / 7.37 / 7.30 |
| dflash n=4 | 9.53 | 9.77 / 9.53 / 9.08 |
| dflash n=7 | 9.79 | 10.60 / 9.47 / 9.79 |

All anchors clean. Findings (recorded as the dated verdict addendum):

1. **7 confirmed, n=4 statistically tied** — the 4-vs-7 gap (+2.7%) is
   inside n=7's own run spread (9.47–10.60); n=2–3 are ~22% lower, and
   the ordering is NOT monotonic (n=2 beats n=3). The GGUF-path optimum
   (2–4, gfx1100) does NOT transfer to the vLLM path on this host; the
   conf keeps 7 — now as a swept choice, not an unexamined default.
2. **The floor-crossing is day-dependent** — dflash-7 re-measures 9.79
   (below the 10 tok/s floor) vs the corpus cell's 10.23 (above), −4.3%,
   inside the documented ±5–6% common-mode band; the same-session
   controls replicated tightly (base +1.5%, mtp +0.5% vs the 2026-08-21
   pairing), so this is host-state drift, not a config regression.
   Same-session pairing ratios today: +136.1% vs base, +57.4% vs MTP
   (2026-08-21: +150.1% / +65.3%).

Sibling integration: the GGUF path serves the same drafter via
`WITH_DFLASH2=1` (llama.cpp PR #27342), measured on a gfx1100-class host —
see [`../dflash2/`](../dflash2/) and
[`../../troubleshooting.md`](../../troubleshooting.md) DFlash 2 pits.
Different engine + host class; numbers do not transfer.

Upstream context (NOT a measurement on this host): the draft repo reports
up to 3.43x single-stream speedup vs autoregressive on an NVIDIA H200
(SGLang, FlashAttention 3), beating the built-in MTP head; concurrency
erodes the gain. This repository's own numbers: the pairing session
receipts under `matrix-714/stability/dflash-pairing-2026-08-21/` and the
dflash corpus cells under `matrix-714/cells/`.
