# MTP + KV experiments — 2026-08-17

Both experiments ran on the Task 5 serving path (same host: AMD Radeon
W7900 / gfx1100, ROCm 7.14.0 at /root/rocm-7.14.0-gfx1100, same model
Qwen3.8-27B-Q4_K_M.gguf, same ctx 32768, same -ngl 999), using the new
EXTRA_SERVER_ARGS passthrough added to scripts/03-serve-llamacpp.sh in this
task (appended after the fixed args, word-split guarded). Every quoted line
below is verbatim from the /root/*.log capture named in its section. The
comparison baseline is docs/results/gguf-serving/serving-receipt.md
(smoke x3: 24.1/25.8/28.3 tok/s, mean 26.1 tok/s; 19274985472 bytes =
17.95 GiB VRAM while serving). The server was stopped and VRAM returned to
the 27987968-byte idle baseline after each experiment.

## KV cache q8_0

- Command: `PORT=8080 EXTRA_SERVER_ARGS="--cache-type-k q8_0 --cache-type-v q8_0" bash scripts/03-serve-llamacpp.sh`
- Passthrough verified via /proc/PID/cmdline, verbatim:
  `/root/llama.cpp/build-714gfx1100/bin/llama-server -m /root/models/Qwen3.8-27B-Q4_K_M.gguf --host 0.0.0.0 --port 8080 -ngl 999 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0`
- Evidence, verbatim from /root/smoke-kv.log (two consecutive runs) vs
  baseline (three runs, /root/smoke.log quoted in serving-receipt.md):

```console
KV q8_0 (this experiment):
SMOKE: 200 ok, prompt=59 completion=64 tokens, 23.6 tok/s decode (wall 2.7s)
SMOKE: 200 ok, prompt=59 completion=64 tokens, 25.6 tok/s decode (wall 2.5s)
Baseline (f16 KV, serving-receipt.md):
SMOKE: 200 ok, prompt=59 completion=64 tokens, 24.1 tok/s decode (wall 2.7s)
SMOKE: 200 ok, prompt=59 completion=64 tokens, 25.8 tok/s decode (wall 2.5s)
SMOKE: 200 ok, prompt=59 completion=64 tokens, 28.3 tok/s decode (wall 2.3s)
```

VRAM while serving (after the two smoke runs), verbatim from
/root/vram-kv.log vs baseline /root/vram-serving.log:

```console
# KV q8_0:
GPU[0]		: VRAM Total Used Memory (B): 18359181312
# Baseline:
GPU[0]		: VRAM Total Used Memory (B): 19274985472
```

- Outcome: measured — KV q8_0 decodes at 23.6/25.6 tok/s (mean 24.6 tok/s)
  vs the f16-KV baseline 24.1/25.8/28.3 tok/s (mean 26.1 tok/s), i.e.
  -1.5 tok/s (about 5 percent slower, and inside the baseline's own
  24.1-28.3 spread), while VRAM drops from 17.95 GiB to 17.10 GiB
  (-915804160 bytes = -0.85 GiB, about 4.8 percent). Not a throughput win
  on this model; a modest VRAM saving only. Expected magnitude: this is a
  Gated-DeltaNet hybrid, so the recurrent layers hold no KV at all and only
  the attention subset benefits from KV quantization. Remedy if throughput
  matters more than the 0.85 GiB: keep f16 KV.

## MTP drafting

- Upstream flags at this pin (llama.cpp 4df29be4f4c3673f428170fda944a5b19f743bb8),
  from `/root/llama.cpp/build-714gfx1100/bin/llama-server --help 2>&1 | grep -iE 'spec|draft|mtp'`
  — the key lines are excerpted and reordered below; the full, untouched
  capture lives at /root/mtp-flags.txt:

```console
--spec-type none,draft-simple,draft-eagle3,draft-mtp,draft-dflash,draft-dspark,ngram-simple,ngram-map-k,ngram-map-k4v,ngram-mod,ngram-cache
                                        comma-separated list of types of speculative decoding to use (default:
                                        (env: LLAMA_ARG_SPEC_TYPE)
--spec-draft-n-max N                    number of tokens to draft for speculative decoding (default: 3)
                                        (env: LLAMA_ARG_SPEC_DRAFT_N_MAX)
--spec-draft-model, -md, --model-draft FNAME
                                        draft model for speculative decoding (default: unused)
                                        (env: LLAMA_ARG_SPEC_DRAFT_MODEL)
--draft, --draft-n, --draft-max N       the argument has been removed. use --spec-draft-n-max or
                                        --spec-ngram-mod-n-max
```

- Attempt: `PORT=8080 EXTRA_SERVER_ARGS="--spec-type draft-mtp" bash scripts/03-serve-llamacpp.sh`
  — the first launch was transiently refused by the GPU-contention preflight
  (a monitoring shell whose command line merely contained the string
  "llama-server-8080.log"; verbatim: `FAIL: another llama-server/vllm
  process is running (GPU contention).`); the one retry started cleanly.
  The ready-made unsloth GGUF ships the nextn/MTP block (blk.64.nextn.*,
  logged as unused tensors on a plain load), so draft-mtp drafts from the
  same file with no separate draft model. Verbatim from
  /root/llama-server-8080.log and /root/smoke-mtp.log:

```console
common_speculative_init_result: creating MTP draft context against the target model '/root/models/Qwen3.8-27B-Q4_K_M.gguf'
READY: llama-server on :8080 (OpenAI-compatible)
SMOKE: 200 ok, prompt=59 completion=64 tokens, 30.6 tok/s decode (wall 2.1s)
slot print_timing: id  3 | task 0 | draft acceptance = 0.74138 (   43 accepted /    58 generated), mean len =  3.15
```

VRAM while serving, verbatim from /root/vram-mtp.log:

```console
GPU[0]		: VRAM Total Used Memory (B): 21746409472
```

- Outcome: measured — draft-mtp works at this pin and is the fastest
  configuration tried: 30.6 tok/s on the single smoke run vs the f16-KV
  baseline mean 26.1 tok/s (+4.5 tok/s, +17.2 percent; also above the
  baseline's best single run of 28.3 tok/s), at a draft acceptance of
  0.74138 (43/58) and mean draft length 3.15, for +2471424000 bytes
  (+2.30 GiB, 20.25 GiB total). Caveats: n=1 smoke run, and the 64-token
  smoke favors nothing in particular — Phase 3 should re-measure at longer
  generations before adopting. No gap to record: the open upstream
  converter bugs #27019/#26916 documented in docs/results/spike/gguf.md
  (MTP-layer-count inflation on local BF16 conversion of hybrid qwen3_5
  checkpoints, `--no-mtp` workaround, fix PR #27132 unmerged at probed
  HEAD) are conversion-side only and do not affect consuming the ready-made
  unsloth quant, whose nextn block loads and drafts as shown above.
