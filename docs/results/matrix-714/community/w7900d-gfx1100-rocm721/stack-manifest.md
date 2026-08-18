# Stack manifest — w7900d-gfx1100-rocm721

Community submission (docs/hardware-validation.md). Platform: **AMD Radeon
Pro W7900D** (`gfx1100`, 48 GiB discrete GDDR6 — rocm-smi total
51522830336 B = 47.98 GiB), host AMD EPYC 9334 32-Core (128 threads),
1 TiB system RAM, kernel `6.8.0-79-generic` (Ubuntu).

The kernel is below the project floor 6.16.9. That floor guards the Strix
Halo UMA/GTT bug (docs/troubleshooting.md#uma-bug) and its documented
reproduction is scoped to Ryzen AI MAX+ PRO 395 / Radeon 8060S hosts; this
is a discrete-VRAM server board. Recorded here per the community protocol
(the env-check receipt carries the matching WARNING).

## ROCm

- Serving runtime: **7.2.1** at `/opt/rocm` — the libraries the
  llama-server binary actually resolves (`ldd`: `libamdhip64.so.7`,
  `libhipblas.so.3`, `librocblas.so.5` from `/opt/rocm-7.2.1/lib`). The
  env-check receipt was run with `ROCM_PREFIX=/opt/rocm` so the receipt
  reports the same runtime that served the cells.
- Compile toolchain: **ROCm 7.14.0** hipcc at `/root/rocm-7.14.0-gfx1100`
  (build prefix; `CMAKE_CXX_COMPILER=/root/rocm-7.14.0-gfx1100/bin/hipcc`).
  gfx1100 has no TheRock nightly index — this prefix is submitter-built and
  documented here, as the protocol requires.

## llama.cpp

- Commit `4df29be4f4c3673f428170fda944a5b19f743bb8` — identical to the
  project pin (`configs/validated-stack.json`, `llama_cpp.commit`).
- Build: `cmake -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100` (plus
  `GGML_HIP_GRAPHS=ON`, `GGML_HIP_NO_VMM=ON` per CMakeCache), ninja, ~6 min
  on this host; build dir `/root/llama.cpp/build-714gfx1100`.
- `llama-server --version`: `0.1.0-dev (build 10454, commit 4df29be4f)`,
  built with Clang 23.0.0.
- Serving used `scripts/gguf-quickstart.sh` unmodified except the binary
  location: `LLAMA_SERVER=/root/llama.cpp/build-714gfx1100/bin/llama-server`
  (the quickstart's documented override). No server flag changes; the model
  resolved from the repo's own artifact manifest.

## PyTorch / vLLM

- Not used for the evidence cells — this is a GGUF-path submission
  (`validated.vllm=false`; BF16 vLLM serving needs ~51.7 GiB of weights and
  cannot fit this 48 GiB board, per docs/hardware-validation.md).
- Context only (not evidence; run 2026-08-17, separate exploration on this
  same host): vLLM `0.27.1+rocm723` wheel on system ROCm 7.2.1 with the
  official `Qwen/Qwen3.8-27B-FP8` checkpoint (28.75 GiB) boots and serves
  once `VLLM_ENGINE_READY_TIMEOUT_S=1800` covers the untuned W8A8
  config search (~1474 s); decode then measures 0.6 / 2.3 / 8.7 tok/s at
  c1 / c4 / c16 (eager, Triton paged-attention fallback). Upstream issue:
  vllm-project/vllm#52663.

## Model artifacts

Set `gguf` of `configs/artifact-manifest.json`, fetched by
`SET=gguf bash scripts/02-fetch-model.sh` (ModelScope mirror), SHA256
verified at fetch time:

| file | bytes | sha256 |
|---|---:|---|
| Qwen3.8-27B-UD-Q4_K_XL.gguf | 17923394624 | `bee238bbeb3dc0a34bde4d0dedbaee1f98c009e8bb4226f03070054c12fb1372` |
| mmproj-F16.gguf | 927607488 | `cbb841a9ee0636b2ec172f5bb8df2ea8dfeb01e90fe7c6126581d662a0b4e43e` |
| config.json | 3760 | `45d9009888b40b71af58ac82f7151393c113b4eabb870ca3c3bbd237667d18cc` |

Source: `unsloth/Qwen3.8-27B-GGUF` @ `c882514ed737f384900d3cb294be58b7edc2ceb4`.

## Exact commands (build + serve)

```bash
# one-time: llama.cpp at the pinned commit, HIP build for gfx1100
git clone https://github.com/ggml-org/llama.cpp /root/llama.cpp
git -C /root/llama.cpp checkout 4df29be4f4c3673f428170fda944a5b19f743bb8
cmake -S /root/llama.cpp -B /root/llama.cpp/build-714gfx1100 \
      -DCMAKE_CXX_COMPILER=/root/rocm-7.14.0-gfx1100/bin/hipcc \
      -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100
cmake --build /root/llama.cpp/build-714gfx1100 -j

# artifacts
SET=gguf bash scripts/02-fetch-model.sh

# evidence receipts
ROCM_PREFIX=/opt/rocm bash scripts/00-check-env.sh --profile community | \
  tee docs/results/matrix-714/community/w7900d-gfx1100-rocm721/env-check.txt

# every cell (the runner boots/kills the server itself via gguf-quickstart.sh)
export LLAMA_SERVER=/root/llama.cpp/build-714gfx1100/bin/llama-server
export CELLS_DIR=docs/results/matrix-714/community/w7900d-gfx1100-rocm721/cells
bash scripts/run-cell-gguf.sh gguf-udq4kxl-auto-base-c1-ctx32768
bash scripts/run-cell-gguf.sh gguf-udq4kxl-auto-base-c4-ctx131072
bash scripts/run-cell-gguf.sh gguf-udq4kxl-auto-base-c16-ctx131072
bash scripts/run-cell-gguf.sh gguf-udq4kxl-auto-mtp-c1-ctx131072
bash scripts/run-cell-gguf.sh gguf-udq4kxl-auto-mtp-c4-ctx131072
bash scripts/run-cell-gguf.sh gguf-udq4kxl-auto-base-c1-ctx262144
```

The rocm-smi receipts (`rocm-smi-idle.txt`, `rocm-smi-loaded.txt`) were
captured with `rocm-smi --showproductname`, `--showmeminfo vram`,
`--showmeminfo gtt`, `--showuse --showpower --showtemp`; the loaded capture
was taken during the `base-c4-ctx131072` cell with the model resident
(VRAM used 27769556992 B = 25.9 GiB).
