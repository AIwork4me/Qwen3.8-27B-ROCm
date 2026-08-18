# FP8 unlock probe on gfx1100 — 2026-08-17

Follow-up to [fp8-smoke.md](fp8-smoke.md) (verdict GAP, 2026-08-17). The smoke
probe proved the FP8 loader accepts the quant on gfx1100 and the only observed
blocker was startup time; this probe tries two bounded levers against the warm
Phase 2 venv/cache, then — on UNLOCKED — runs the 3 contingent vLLM benchmark
cells. Probe code: `scripts/probe-fp8-unlock.sh`, test
`tests/test_fp8_unlock.py`. Verdict line at the bottom.

## Setup

- venv: `/root/venv-fp8probe` (uv, Python 3.12.3); vLLM `0.27.1+rocm723` on
  system ROCm 7.2.1; host GPU AMD Radeon W7900D (gfx1100, 48 GiB).
- Model snapshot: `/root/.cache/modelscope/models/Qwen--Qwen3.8-27B-FP8/snapshots/master`
  (66 shards, checkpoint 28.75 GiB; loaded weights 29.38 GiB per the smoke run).
- Server args (both levers and all cells): `--model SNAP
  --served-model-name Qwen/Qwen3.8-27B-FP8 qwen3.8-27b --max-model-len 8192
  --gpu-memory-utilization 0.90 --enforce-eager --port 8199`. The second served
  name (`qwen3.8-27b`) is required: `scripts/bench_driver.py` hardcodes that
  payload model name (llama-server's alias), and without it vLLM 404s every
  cell request. The probe script carries this fix; it was found during the
  first (failed) cell attempt on 2026-08-17 morning.
- Probe invocation: `bash scripts/probe-fp8-unlock.sh 2>&1 | tee
  /root/fp8probe/unlock-run.log`. Artifacts: `/root/fp8probe/unlock-l1-run1.log`,
  `/root/fp8probe/unlock-l1.log`, `/root/fp8probe/unlock.log`,
  `/root/fp8probe/cell2-c{1,4,16}.log`.

## Lever 1 — raise the engine-ready timeout (VLLM_ENGINE_READY_TIMEOUT_S=1800)

Mechanism: keep the stock binary and wheel untouched; give the engine core
1800 s instead of the default 600 s to finish startup, which on gfx1100
includes the untuned W8A8 block-FP8 config search (no tuned JSONs are shipped
for `device_name=AMD_Radeon_Graphics` — see fp8-smoke.md).

Verbatim from `/root/fp8probe/unlock-run.log`:

```
=== lever: lever1-timeout1800 (engine timeout 1800s) ===
PROBE-RESULT: UNLOCKED via lever 1 (engine timeout 1800s)
```

First 1800 s run (`/root/fp8probe/unlock-l1-run1.log`, 08:07–08:31): the
config search is what the extra budget pays for, verbatim:

```
(EngineCore pid=371418) WARNING 08-17 08:07:37 [fp8_utils.py:851] Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal! Config file not found at /root/venv-fp8probe/lib/python3.12/site-packages/vllm/model_executor/layers/quantization/utils/configs/N=16384,K=5120,device_name=AMD_Radeon_Graphics,dtype=fp8_w8a8,block_shape=[128,128].json
(EngineCore pid=371418) WARNING 08-17 08:31:17 [fp8_utils.py:851] Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal! Config file not found at /root/venv-fp8probe/lib/python3.12/site-packages/vllm/model_executor/layers/quantization/utils/configs/N=34816,K=5120,device_name=AMD_Radeon_Graphics,dtype=fp8_w8a8,block_shape=[128,128].json
(EngineCore pid=371418) INFO 08-17 08:31:42 [core.py:355] init engine (profile, create kv cache, warmup model) took 1474.26 s
(APIServer pid=371094) INFO:     127.0.0.1:33878 - "GET /health HTTP/1.1" 200 OK
```

The search spans 08:07:37 to 08:31:17 (~23.5 min) across five shapes
(N=16384/K=5120, N=5120/K=6144, N=34816/K=5120, N=5120/K=17408,
N=14336/K=5120); total engine init 1474.26 s — 2.5x the default 600 s budget,
comfortably inside 1800 s. Health returned 200 immediately after.

Immediate re-run (`/root/fp8probe/unlock-l1.log`, 08:38) — the search result
is cached on disk, so the second start is fast, verbatim:

```
(EngineCore pid=378832) INFO 08-17 08:38:28 [core.py:355] init engine (profile, create kv cache, warmup model) took 49.01 s
(APIServer pid=378511) INFO 08-17 08:38:45 [api_server.py:682] Starting vLLM server on http://0.0.0.0:8199
(APIServer pid=378511) INFO:     Application startup complete.
(APIServer pid=378511) INFO:     127.0.0.1:46230 - "GET /health HTTP/1.1" 200 OK
```

So the 1474 s cost is one-time per venv; every later start measured 49 s of
engine init (49.10 / 49.11 / 49.19 s in the three cell servers below).

## Lever 2 — pre-seed the tuned-config JSON: SKIPPED

Lever 2 (copy a wheel-shipped MI300X `N=16384,K=5120` config to an
`AMD_Radeon_Graphics` filename) was not attempted: lever 1 succeeded, and the
probe only falls through to lever 2 on lever-1 failure. Recorded for the
upstream issue anyway: the wheel's configs directory
(`/root/venv-fp8probe/lib/python3.12/site-packages/vllm/model_executor/layers/quantization/utils/configs`)
ships only `AMD_Instinct_MI300X`, `AMD_Instinct_MI325X` and
`AMD_Instinct_MI325_OAM` device configs, and contains no `N=16384,K=5120`
entry for any device — the lever-2 seed source does not exist in
vllm 0.27.1+rocm723.

## Contingent vLLM cells

### First attempt (2026-08-17 morning) and the driver-vs-server hurdle

The morning attempt inside the probe run reached a healthy server but produced
a failed c1 cell, verbatim from the run console:

```
cell -> /workspace/Qwen3.8-27B-ROCm/docs/results/matrix/cell-vllm-c1.json status=FAIL tps=0.0
```

with the driver ultimately killed mid-run, and a manual diagnostic against an
identical healthy server, verbatim from `/root/fp8probe/diag-curl.log`:

```
curl_rc=000 total_s=1500.001454
```

— a single completion request to a /health-200 server returning nothing for
25 minutes. The server log explains it: the FIRST inference triggers Triton
JIT compilation of the FP8/GDN kernel set, and on this host each big kernel
takes ~20+ minutes of single-threaded CPU to compile (GPU idle the whole
time), verbatim from `/root/fp8probe/diag.log`:

```
(EngineCore pid=385394) WARNING 08-17 09:28:29 [jit_monitor.py:135] Triton kernel JIT compilation during inference: _w8a8_triton_block_scaled_mm. This causes a latency spike; consider extending warmup to cover this shape/config.
(EngineCore pid=385394) WARNING 08-17 09:50:31 [jit_monitor.py:135] Triton kernel JIT compilation during inference: _triton_mrope_forward. This causes a latency spike; consider extending warmup to cover this shape/config.
(EngineCore pid=385394) WARNING 08-17 09:50:33 [jit_monitor.py:135] Triton kernel JIT compilation during inference: _fwd_kernel. This causes a latency spike; consider extending warmup to cover this shape/config.
(EngineCore pid=385394) WARNING 08-17 09:50:34 [chunked_prefill_paged_decode.py:419] Cannot use ROCm custom paged attention kernel, falling back to Triton implementation.
```

The bench driver's per-request timeout (default 300 s) is far shorter than
that staging, so every morning request timed out client-side — a
driver-vs-server interaction, not a server failure.

### Manual re-run (afternoon, this receipt)

Cells were run manually per the probe's `run_vllm_cells` pattern: per cell,
start the server on :8199 (same args as Setup), poll /health, warm the request
path, run `scripts/bench_driver.py --concurrency {c} --reps 5 --max-tokens
128 --prompt-file configs/bench-prompt.txt` with the brief's identity JSON
(engine "vllm"), kill the server, verify GPU idle, then next cell.

- c1 server: launched 13:30:30, health 200 at 13:34:09 (engine init 49.10 s).
  First request sent 13:34:18; the EngineCore stayed 100% CPU / 0% GPU while
  kernels compiled in ~22-minute steps (cache-hits for the four kernels the
  morning diag had already compiled, then fresh compiles for the GDN decode
  path, verbatim from `/root/fp8probe/cell2-c1.log`):

```
(EngineCore pid=434612) WARNING 08-17 13:55:59 [jit_monitor.py:135] Triton kernel JIT compilation during inference: _causal_conv1d_update_kernel. This causes a latency spike; consider extending warmup to cover this shape/config.
(EngineCore pid=434612) WARNING 08-17 13:55:59 [jit_monitor.py:135] Triton kernel JIT compilation during inference: fused_recurrent_gated_delta_rule_packed_decode_kernel. This causes a latency spike; consider extending warmup to cover this shape/config.
(EngineCore pid=434612) WARNING 08-17 13:55:59 [jit_monitor.py:135] Triton kernel JIT compilation during inference: layer_norm_fwd_kernel. This causes a latency spike; consider extending warmup to cover this shape/config.
```

  First fully-served response: `rc=200 total_s=608.536757` (issued 14:07:52,
  served ~14:17:41) — total first-request staging ~43 min from 13:34:18. The
  compiles persist in the on-disk Triton cache (`/root/.triton/cache`).
- c4 server: launched 14:41:43, health 200 at 14:43:48 (engine init 49.11 s).
  Warmup burst of 4 concurrent requests: all `rc=200` in 15.5–17.2 s — every
  kernel a cache hit, no new compiles.
- c16 server: launched 15:13:29, health 200 at 15:15:34 (engine init 49.19 s).
  Warmup burst of 16 concurrent requests: all `rc=200` in ~26–28 s.
- Driver deviation, disclosed: c4 and c16 were run with `--timeout 3600`
  (client ceiling only; identity/params unchanged) as a precaution against a
  repeat of the morning's client-side timeouts. In the event every request
  finished far inside even the default 300 s (max wall 234.8 s at c16), so the
  numbers are not affected; c1 ran with the default ceiling.

The three engine-init figures above, verbatim from the cell server logs
(`grep -h 'init engine'` on each of `/root/fp8probe/cell2-c{1,4,16}.log`):

```
(EngineCore pid=434612) INFO 08-17 13:33:48 [core.py:355] init engine (profile, create kv cache, warmup model) took 49.10 s
(EngineCore pid=455182) INFO 08-17 14:43:22 [core.py:355] init engine (profile, create kv cache, warmup model) took 49.11 s
(EngineCore pid=461472) INFO 08-17 15:15:08 [core.py:355] init engine (profile, create kv cache, warmup model) took 49.19 s
```

Server-start budget: all three starts were 2.1–3.6 min wall, far inside the
1800 s engine budget and the 35-min start cap.

### Results (all cells OK, 105/105 requests)

| Cell | status | ok/total | mean_decode_tps (aggregate) | p50 request wall s | max wall s |
|---|---|---|---|---|---|
| vllm-c1 | OK | 5/5 | 0.612 | 209.2 | 209.3 |
| vllm-c4 | OK | 20/20 | 2.301 | 222.4 | 222.9 |
| vllm-c16 | OK | 80/80 | 8.730 | 234.5 | 234.8 |

Every request: 100 prompt tokens, exactly 128 completion tokens, temp 0. The
c16 per-wave aggregate was flat at 8.722–8.733 tok/s across all 5 waves.
Files: `docs/results/matrix/cell-vllm-c{1,4,16}.json`;
`docs/results/matrix/SHA256SUMS` regenerated over all 19 cells and verified.

For scale on the same GPU: llama.cpp Q4_K_M measured 28.6 tok/s at c1 in this
matrix (`mean_decode_tps` in `docs/results/matrix/cell-q4km-c1.json`) —
FP8-on-gfx1100 vLLM (eager, Triton paged-attention fallback, untuned W8A8
configs) is ~47x slower per stream at c1 and only reaches 8.7 tok/s aggregate
at c16.

## Result: UNLOCKED

gfx1100 (W7900D) runs the official Qwen3.8-27B-FP8 on vLLM 0.27.1+rocm723:
lever 1 (`VLLM_ENGINE_READY_TIMEOUT_S=1800`) clears the startup gate, and all
3 contingent cells completed OK. Two one-time costs are now measured and
cached on disk: the W8A8 config search (1474 s inside engine init) and the
first-inference Triton JIT staging (~43 min); after both, server start is ~2
min and requests are steady.

## Impact

- The Phase 2 GAP is resolved as a timeout misconfiguration, not an arch
  refusal: the same wheel, unmodified, serves FP8 on a consumer RDNA3 card
  once the engine-ready budget covers the untuned config search. Decision
  table FP8 row updated to UNLOCKED (smoke).
- Practical ranking for Phase 3 conclusions: the FP8 vLLM path is a
  correctness/capacity unlock (29.38 GiB weights, 48 GiB card), not a
  performance one — aggregate decode tops out at 8.7 tok/s at c16 vs
  llama.cpp GGUF cells in the tens of tok/s on the same GPU.
- Upstream issue, ready to file with this receipt plus fp8-smoke.md as
  evidence: gfx1100 runs FP8 fine; only the default 600 s engine-ready
  timeout is too short, because vLLM ships no tuned W8A8 block-FP8 configs
  for `device_name=AMD_Radeon_Graphics` and the on-first-start search takes
  ~1475 s on a W7900D. Asks: ship Radeon tuned configs (or a documented
  fallback default set), and/or document `VLLM_ENGINE_READY_TIMEOUT_S` for
  large-FP8 cold starts. Secondary ask, same ticket or its own: first
  inference triggers ~20-minute-per-kernel Triton JIT compiles on gfx1100
  (w8a8 block-scaled MM, GDN recurrent/conv1d) with the jit monitor warning
  but no pre-warm; extending engine warmup to cover the serving shapes (or
  shipping the compiled kernels) would remove a ~43-minute first-request
  cliff that is invisible to /health and breaks naive clients.
