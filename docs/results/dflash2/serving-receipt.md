# DFlash 2 serving receipt — gfx1100 host, 2026-08-21

Stack manifest for every DFlash2 cell in this namespace. Format follows
the community stack-manifest pattern (`docs/results/matrix-714/community/`);
this host is the same machine class as the `w7900d-gfx1100-rocm721`
community submission (AMD EPYC 9334, 1 TiB RAM, kernel 6.8.0-79-generic,
W7900-class gfx1100 48 GiB discrete).

## Serving binary (BOTH comparison arms — clean pairing)

- llama.cpp **PR #27342** head `5ecbe1ac17ec0484c5b44af0bd580cdc9c428ed4`
  ("spec : add DFlash2 support", OPEN at measurement time), fetched as
  `refs/pull/27342/head`, verified `git rev-parse HEAD` == pin.
- Build: `MAX_JOBS=64 bash scripts/07-build-llama-dflash2.sh`
  → `third_party/llama.cpp/build-714-dflash2` (fingerprint-idempotent).
- `llama-server --version`: `version: 0.1.2-dev (build 1, commit 5ecbe1ac1)`.
- CMake: `-DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100 -DGPU_TARGETS=gfx1100
  -DCMAKE_BUILD_TYPE=Release -DROCM_PATH=/opt/rocm` (auto-detected
  gfx1100; `rocminfo` also lists `gfx11-generic` — the build script pins
  the concrete 4-digit arch by construction).

## ROCm

- Serving runtime **7.2.1** at `/opt/rocm` (the only install on this
  host; also the compile toolchain — hipcc from the same prefix).
- Historical note: the community w7900d stack compiled with a ROCm 7.14
  gfx1100 prefix; that prefix did not survive the host rebuild. The
  project records 7.2.1 as `rocm_historical_fallback` — this receipt's
  build+serve both ran on 7.2.1 and say so in every cell.

## Model artifacts (SHA256-verified at fetch time)

- Target: `Qwen3.8-27B-UD-Q4_K_XL.gguf` (17.9 GiB,
  `unsloth/Qwen3.8-27B-GGUF` via ModelScope — the repo's `gguf` set).
- Draft: `Qwen3.8-27B-DFlash2-Q8_0.gguf` (2.05 GiB, sha256
  `7f1c9a31a6ed40044c69f6508b50fd63b87abd8e1fb7fe4290303df549153751`)
  — the repo's new `dflash2` set, `incoai/Qwen3.8-27B-DFlash2-GGUF` on
  ModelScope (huggingface.co is unreachable from this host; see
  troubleshooting `#dflash2-draft-fetch`).
- Host disk note: the repo's `models/` is a symlink into the persistent
  host cache mount on this machine; the manifest paths are unchanged.

## Exact commands (every cell)

```bash
export LLAMA_SERVER=$PWD/third_party/llama.cpp/build-714-dflash2/bin/llama-server
export MATRIX_FILE=docs/results/dflash2/matrix.json
export CELLS_DIR=docs/results/dflash2/cells

bash scripts/run-cell-gguf.sh gguf-hip-udq4kxl-auto-base-c1-ctx131072
bash scripts/run-cell-gguf.sh gguf-hip-udq4kxl-auto-dflash2-c1-ctx131072
bash scripts/run-cell-gguf.sh gguf-hip-udq4kxl-auto-mtp-c1-ctx131072
bash scripts/run-cell-gguf.sh gguf-hip-udq4kxl-auto-base-c4-ctx131072
bash scripts/run-cell-gguf.sh gguf-hip-udq4kxl-auto-dflash2-c4-ctx131072
BENCH_TIMEOUT_S=360 HEALTH_TIMEOUT_S=240 \
  bash scripts/run-cell-gguf.sh gguf-hip-udq4kxl-auto-dflash2-c16-ctx32768

# losslessness (greedy byte-identity, same binary both arms)
bash scripts/check-dflash2-equiv.sh --arm baseline
bash scripts/check-dflash2-equiv.sh --arm dflash2
bash scripts/check-dflash2-equiv.sh --arm compare   # → equiv.json, PASS 4/4
```

`LLAMA_SERVER` exported for **every** cell (base/mtp/dflash2 alike) is
the clean-pairing mechanism: one binary, one day, one prompt set — the
with/without delta is the drafter, not the build.

## Boot flags that differ per arm

- base: `-m <UD-Q4_K_XL> --ctx-size 131072 -ngl 99 --jinja --mmproj <F16>`
- dflash2: base + `-md models/Qwen3.8-27B-DFlash2-GGUF/Qwen3.8-27B-DFlash2-Q8_0.gguf
  --spec-type draft-dflash --spec-draft-n-max 7`
- mtp: base + `--spec-type draft-mtp --spec-draft-n-max 1`
- c4 cells add `-np 4` (split KV); the c16 probe adds `-np 16` at ctx 32768.

## Environment receipts

- Load VRAM per cell: recorded in each `cells/*.json` (`load.vram_mib`):
  base 26 485 / dflash2-c1 33 403 / mtp 28 065 MiB — the drafter costs
  ≈ +6.9 GiB (weights 2.0 GiB + draft KV + speculative buffers).
- Telemetry blocks (clocks/temp at load and post-bench) are in every
  cell; `powerprofilesctl` is absent on this host (recorded as null per
  the telemetry-tolerant rule; raw rocm-smi output is verbatim).
- GPU idle at session start (rocm-smi VRAM ≈ 28 MiB residual);
  cells ran sequentially 2026-08-21, no other GPU workload.
