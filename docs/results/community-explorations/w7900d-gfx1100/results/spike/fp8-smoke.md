# FP8 load smoke on gfx1100 — 2026-08-17

Two runs, per controller ruling R5: a cold run via `scripts/probe-fp8-vllm.sh`
and a warm re-run with `--enforce-eager` against the then-hot model and
compile caches. Both outcomes are recorded verbatim below. Artifacts:
`/root/fp8probe/vllm.log`, `/root/fp8probe/server.log`,
`/root/fp8probe/server-warm.log`, `/root/fp8probe/fetch.log`,
`/root/fp8probe/completion.json`.

## Setup
- venv: `/root/venv-fp8probe` (uv, Python 3.12.3)
- vLLM version: `import vllm; vllm.__version__` = 0.27.1; installed wheel line from the probe log: `vllm==0.27.1+rocm723`
- Wheel install line (parsed by the probe from the pinned docs page https://docs.vllm.ai/en/stable/getting_started/installation/gpu/): `uv pip install vllm --extra-index-url https://wheels.vllm.ai/rocm/ --upgrade`
- Extraction adaptation (R3, recorded per ruling): the docs page renders install commands inside syntax-highlighted HTML code blocks, so the probe strips the tags from those blocks before grepping the pip line — the method lives in `scripts/probe-fp8-vllm.sh`.
- Model: Qwen/Qwen3.8-27B-FP8 (28.7 GiB), fetched with `modelscope snapshot_download` to `/root/.cache/modelscope/models/Qwen--Qwen3.8-27B-FP8/snapshots/master` and served from that local path under `--served-model-name Qwen/Qwen3.8-27B-FP8` — vllm 0.27.1 rejects the bare ModelScope repo id (see notes in `scripts/probe-fp8-vllm.sh`)
- Stack: system ROCm 7.2.1 (the rocm wheels match it); arch question: gfx1100/RDNA3
- Server args, cold run: `--model /root/.cache/modelscope/models/Qwen--Qwen3.8-27B-FP8/snapshots/master --served-model-name Qwen/Qwen3.8-27B-FP8 --max-model-len 8192 --gpu-memory-utilization 0.90 --port 8199`
- Server args, warm re-run (R5): same as cold plus `--enforce-eager` (skips torch.compile and CUDA/HIP graph capture)

## Result: GAP

### Cold run (probe script, 01:41–02:31)

The loader ACCEPTED the FP8 quant — no supports_fp8 refusal; architecture
resolved and all 66 shards loaded onto the GPU (29.38 GiB). The verdict
driver, verbatim from `/root/fp8probe/server.log` (the trailing value
placeholder rewritten as SECONDS-PLACEHOLDER — receipts contain no angle
brackets):

```
(APIServer pid=279547) TimeoutError: Timed out waiting for engine core processes to start. This is often caused by slow weight loading for large models. Waited 600s (configured by VLLM_ENGINE_READY_TIMEOUT_S). To increase the timeout, set the environment variable: VLLM_ENGINE_READY_TIMEOUT_S=SECONDS-PLACEHOLDER
```

What happened before the timeout, verbatim:

```
(EngineCore pid=280186) INFO 08-17 01:42:46 [default_loader.py:430] Loading weights took 16.33 seconds
(EngineCore pid=280186) INFO 08-17 01:42:46 [gpu_model_runner.py:5405] Model loading took 29.38 GiB memory and 17.353099 seconds
(EngineCore pid=280186) INFO 08-17 01:44:23 [monitor.py:53] torch.compile took 67.53 s in total
(EngineCore pid=280186) WARNING 08-17 01:44:23 [fp8_utils.py:851] Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal! Config file not found at /root/venv-fp8probe/lib/python3.12/site-packages/vllm/model_executor/layers/quantization/utils/configs/N=16384,K=5120,device_name=AMD_Radeon_Graphics,dtype=fp8_w8a8,block_shape=[128,128].json
(EngineCore pid=280186) WARNING 08-17 02:07:49 [fp8_utils.py:851] Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal! Config file not found at /root/venv-fp8probe/lib/python3.12/site-packages/vllm/model_executor/layers/quantization/utils/configs/N=5120,K=6144,device_name=AMD_Radeon_Graphics,dtype=fp8_w8a8,block_shape=[128,128].json
```

The 23 m 26 s gap between the two fp8_utils warnings is the W8A8 block-FP8
config search running with no shipped tuned config for `AMD_Radeon_Graphics`;
it consumed the startup budget and the APIServer gave up at its 600 s
engine-ready limit while the EngineCore was still searching. No completion
was possible: `completion curl rc=7` (connection refused), `completion.json`
empty; `vllm.log` ends with `PROBE-RESULT: GAP — see /root/fp8probe/server.log
for the verbatim refusal/exception`. No tuned config JSON for
`AMD_Radeon_Graphics` was ever written to the wheel's configs directory.

### Warm re-run (R5, 02:53–03:14)

Same venv and snapshot path, caches hot, `--enforce-eager`. Startup was
indeed fast through weight load — then froze at the identical first warning:

```
(APIServer pid=292522) WARNING 08-17 02:53:14 [vllm.py:1194] Enforce eager set, disabling torch.compile and CUDAGraphs. This is equivalent to setting -cc.mode=none -cc.cudagraph_mode=none
(EngineCore pid=292853) INFO 08-17 02:53:54 [default_loader.py:430] Loading weights took 17.04 seconds
(EngineCore pid=292853) INFO 08-17 02:53:55 [gpu_model_runner.py:5405] Model loading took 29.38 GiB memory and 17.541787 seconds
(EngineCore pid=292853) WARNING 08-17 02:54:24 [fp8_utils.py:851] Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal! Config file not found at /root/venv-fp8probe/lib/python3.12/site-packages/vllm/model_executor/layers/quantization/utils/configs/N=16384,K=5120,device_name=AMD_Radeon_Graphics,dtype=fp8_w8a8,block_shape=[128,128].json
```

Those four lines are the whole story: no further log output for 19 m 43 s
(02:54:24 until the protocol kill), `/health` never returned 200 within the
R5 20-minute budget (60 polls at 20 s, through 03:14:07), so no completion
request was sent and the server was killed per protocol. No TimeoutError
traceback appeared in `server-warm.log` inside the capture window — the
APIServer was still alive, waiting on the engine, when the budget expired.
GPU returned to idle (27.9 MB) after the kill.

### Verdict (R5 formula)

GAP — internal 600 s startup timeout on the cold run; on the warm
(`--enforce-eager`) run the engine never became ready within the 20-minute
budget, frozen in the same W8A8 Block FP8 config search (no TimeoutError
line captured before the protocol kill). Arch gate NOT the blocker: the
loader accepted FP8 (weights loaded, 29.38 GiB; architecture resolved as
Qwen3_5ForConditionalGeneration) — the blocker is startup time from the
missing `AMD_Radeon_Graphics` tuned-config search, not an FP8 refusal.

## Impact
- GAP: vLLM path recorded as upstream-gated on gfx1100 — by startup time, not arch. vLLM 0.27.1+rocm723 ships no tuned W8A8 block-FP8 config for `device_name=AMD_Radeon_Graphics`, so the engine runs a per-shape config search that blows the default 600 s engine-ready timeout (cold, with compile 67.53 s) and did not finish within 20 min even warm and eager.
- Upstream issue candidate with this receipt as evidence; the two concrete levers for a Phase 1 retry: raise `VLLM_ENGINE_READY_TIMEOUT_S` far above 600 s, and/or pre-seed the missing tuned config JSONs (filenames verbatim above) for `AMD_Radeon_Graphics`.
- Capacity is not the problem: 29.38 GiB of FP8 weights on the 48 GiB card leaves roughly 19 GiB KV headroom once the startup gate is cleared.
