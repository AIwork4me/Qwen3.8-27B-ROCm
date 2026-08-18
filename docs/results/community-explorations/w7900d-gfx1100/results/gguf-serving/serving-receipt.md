# GGUF serving receipt — 2026-08-17

All commands run on this host (AMD Radeon W7900, gfx1100, kernel
6.8.0-79-generic, ROCm 7.14.0 at the private prefix
/root/rocm-7.14.0-gfx1100), session 2026-08-17 00:37–00:51 UTC (phase
started 2026-08-16). Every quoted line below is verbatim from the
/root/*.log capture named in its section. (An earlier identical capture
at 00:44–00:47 UTC measured 24.0/25.1/28.4 tok/s; a concurrent process
overwrote those logs, so Step 3 was re-run cleanly to produce the
self-consistent capture quoted here.)

## Build identity
- Command: bash scripts/01-build-llamacpp.sh
- llama.cpp commit: 4df29be4f4c3673f428170fda944a5b19f743bb8  cmake flags: -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100  ROCm prefix: /root/rocm-7.14.0-gfx1100
- llama-server sha256: c4c409bff0d2966121c993b131fd53fba698f3c1f814c521c9f49984dda9adcd

Verbatim from /root/build-llamacpp.log (clone, checkout, configure, link):

```console
Cloning llama.cpp -> /root/llama.cpp (retry x3, codeload fallback) ...
Checking out 4df29be4f4c3673f428170fda944a5b19f743bb8 ...
Configuring /root/llama.cpp/build-714gfx1100 (flags: -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100) ...
-- HIP and hipBLAS found
-- Including HIP backend
-- ggml version: 0.20.0
-- ggml commit:  4df29be4f
[464/464] Linking CXX executable bin/llama-server
Built llama-server at /root/llama.cpp/build-714gfx1100/bin/llama-server (commit 4df29be4f4c3673f428170fda944a5b19f743bb8).
```

Full build (clone + configure + 464 ninja targets) took ~6 min wall on this
128-core host.

## Serving identity
- Model: unsloth/Qwen3.8-27B-GGUF :: Qwen3.8-27B-Q4_K_M.gguf (17106775008 bytes, verified by 02-fetch)
- Server args: --host 0.0.0.0 --port 8080 -ngl 999 -c 32768
- VRAM while serving: 19274985472 bytes = 17.95 GiB of 51522830336 total

Fetch evidence, verbatim from /root/fetch-model.log (15.9 GiB from
ModelScope, avg 33.7 MB/s, 8m03s):

```console
Fetching https://modelscope.cn/api/v1/models/unsloth/Qwen3.8-27B-GGUF/repo?Revision=master&FilePath=Qwen3.8-27B-Q4_K_M.gguf
  -> /root/models/Qwen3.8-27B-Q4_K_M.gguf (17106775008 bytes)
100 15.9G  100 15.9G    0     0  33.7M      0  0:08:03  0:08:03 --:--:-- 28.7M
Fetched /root/models/Qwen3.8-27B-Q4_K_M.gguf (17106775008 bytes, verified).
```

Server start/stop, verbatim from /root/serve.log:

```console
llama-server starting (pid 266790), log: /root/llama-server-8080.log
READY: llama-server on :8080 (OpenAI-compatible)
Verify:  bash scripts/04-smoke-chat.sh
Chat:    curl http://127.0.0.1:8080/v1/chat/completions ...
Stopped llama-server (pid 266790, port 8080).
```

VRAM while serving (server up, after the three smoke runs), verbatim from
/root/vram-serving.log:

```console
============================ ROCm System Management Interface ============================
================================== Memory Usage (Bytes) ==================================
GPU[0]		: VRAM Total Memory (B): 51522830336
GPU[0]		: VRAM Total Used Memory (B): 19274985472
==========================================================================================
================================== End of ROCm SMI Log ===================================
```

After stop, VRAM returned to the 27987968-byte idle baseline.

## Smoke runs (3x)

Verbatim from /root/smoke.log (three consecutive runs of
bash scripts/04-smoke-chat.sh against the live server):

```console
SMOKE: 200 ok, prompt=59 completion=64 tokens, 24.1 tok/s decode (wall 2.7s)
SMOKE: 200 ok, prompt=59 completion=64 tokens, 25.8 tok/s decode (wall 2.5s)
SMOKE: 200 ok, prompt=59 completion=64 tokens, 28.3 tok/s decode (wall 2.3s)
```

Mean single-stream decode across the three runs: 26.1 tok/s.

## Conclusion
- The three-command GGUF serving path works end-to-end on this W7900:
  build, fetch, and serve all completed with the expected terminal lines,
  the server reached READY: llama-server on :8080 (OpenAI-compatible),
  and all three smoke requests returned HTTP 200 with non-empty content,
  at 24.1/25.8/28.3 tok/s single-stream decode (mean 26.1 tok/s) with
  17.95 GiB VRAM in use at ctx 32768. Next steps: the KV q8_0 and MTP
  experiments against this baseline in
  docs/results/gguf-serving/experiments.md (Task 7) and the Phase 3
  benchmark plan.
