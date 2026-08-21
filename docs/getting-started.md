# Getting started — Qwen3.8-27B on gfx1151 (ROCm 7.14)

Goal: one-pass success. Every command below is the exact command the
validated stack ran; every default points at a `recommended`-verdict cell
(CI-enforced). Two serving paths, pick by job:

| Path | Use it for | Default |
|---|---|---|
| **GGUF (llama.cpp HIP)** | interactive chat | UD-Q4_K_XL, ctx 131072 — 10.1 tok/s per stream (13.0 with MTP at the implicit depth 3; 13.86 at the recommended depth 1) |
| **vLLM (source build)** | 262144 context, vision, aggregate batch throughput (to 38.6 tok/s) | BF16, `--max-model-len 262144` |

Measured evidence for every number: [`results/benchmark.md`](results/benchmark.md);
verdicts in [`configs/benchmark-verdicts.json`](../configs/benchmark-verdicts.json).

## Prerequisites

**Validated platform:** AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S (`gfx1151`),
94 GiB system RAM with an 80 GiB GPU-visible unified-memory pool
([`configs/validated-stack.json`](../configs/validated-stack.json)). Other AMD
GPUs: see [`hardware-validation.md`](hardware-validation.md) — community
evidence, never a project claim.

- **Kernel ≥ 6.16.9** (Strix Halo UMA floor — older kernels break the memory
  pool this stack needs; details in
  [troubleshooting: kernel floor](troubleshooting.md#uma-bug)). The check
  below fails fast if you are below it.
- **ROCm 7.14.0** at `~/rocm-7.14.0` (side-by-side; system `/opt/rocm` 7.2.1
  is a historical fallback). Install it with the manifest-driven installer:
  `bash scripts/install-rocm-7.14.sh` (URL/size/SHA256 come from
  [`configs/rocm-7.14.json`](../configs/rocm-7.14.json)).
- **Host tools:** `git`, `curl`, `python3`, and `cmake` for the llama.cpp
  build (the build script prints the distro package for whichever command
  is missing). The vLLM path self-installs its build tools (`cmake`, `ninja`)
  into the venv — no host install needed.
- **GPU-visible memory (GTT), measured floor:** the default GGUF boot at
  ctx 131072 loads **26,548 MiB (~26.5 GiB)** and the recommended
  `WITH_MTP=1` boot loads **29,270 MiB (~28.6 GiB)** — per-stream numbers
  traced to the cell receipts in
  [`results/matrix-714/cells/`](results/matrix-714/cells/) (`load.gtt_mib`).
  On 32 GiB-RAM hosts the GTT pool depends on BIOS/allocation — expect
  pressure at the default ctx (lower it with `CTX_SIZE=<n>`).
- **uv** (the vLLM path): https://docs.astral.sh/uv/ — `uv` manages the venv
  the serve scripts run through.

**Disk budget** (sizes are the verified manifest values,
[`configs/artifact-manifest.json`](../configs/artifact-manifest.json)):

| Item | Size | Needed for |
|---|---|---|
| BF16 checkpoint set (`models/Qwen3.8-27B`, 18 shards) | 51.77 GiB | vLLM path |
| GGUF set (`models/Qwen3.8-27B-GGUF`: UD-Q4_K_XL + mmproj-F16 + config) | 17.56 GiB | GGUF path |
| ROCm 7.14 SDK at `~/rocm-7.14.0` | ≈10 GiB (1.6 GiB verified archive + ~8.3 GiB extracted tree) | both paths |
| llama.cpp checkout + HIP build (`third_party/llama.cpp`) | ≈1.3 GiB + build dir | GGUF path |
| vLLM checkout + venv (`third_party/vllm`, `.venv`) | ≈0.4 GiB checkout + ≈5.7 GiB venv after `uv sync` (TheRock torch; ≈7.5 GiB after the vLLM build) | vLLM path |

GGUF-only start: ~29 GiB plus the SDK. Both paths: ~69 GiB of models plus
the SDK, the ≈7.5 GiB venv, and the build directories.

## Step 0 — environment check (both paths)

```bash
bash scripts/00-check-env.sh
```

Expected tail: `OK: base environment ready for Qwen3.8-27B on gfx1151`. No
exports are needed for the validated layout — the scripts find the SDK at
`~/rocm-7.14.0` first (then `/opt/rocm` as the historical fallback) without
any environment setup. Only if your ROCm install lives somewhere else,
point the checker at it:

```bash
export ROCM_PREFIX=/path/to/your/rocm
bash scripts/00-check-env.sh
```

Any FAIL line names its remedy; background for every failure mode is in
[`troubleshooting.md`](troubleshooting.md).

## Path A — GGUF (interactive chat, llama.cpp HIP)

Three commands; the quickstart serves the validated quant with the pinned,
fingerprinted build (DFlash 2 drafter opt-in on this path:
`WITH_DFLASH2=1 SPEC_DEPTH=4` after
[scripts/07-build-llama-dflash2.sh](../scripts/07-build-llama-dflash2.sh) +
`SET=dflash2` — measured on gfx1100; see the README's
[DFlash 2 section](../README.md#dflash-2-speculative-decoding-opt-in-withwithout-measured)):

```bash
bash scripts/05-build-llama.sh              # pinned HIP build @ 4df29be4 for gfx1151 (compile ~7 min; source download on first run)
SET=gguf bash scripts/02-fetch-model.sh     # UD-Q4_K_XL + mmproj-F16, SHA256-verified against the manifest
bash scripts/gguf-quickstart.sh             # serves on http://127.0.0.1:8080/v1
```

First run of the build downloads the llama.cpp source from GitHub (a
≈60 MiB blobless clone with automatic retry and a tarball fallback). On
throttled GitHub links that download — not the ~7 min compile — dominates:
measured ≈14 min at ≈45 KiB/s during the one-pass rehearsal on this host's
network.

Recommended path — the MTP opt-in (+28% per-stream throughput, 13.0 vs
10.1 tok/s single stream on the corpus cell, which ran the implicit
upstream depth 3; the 2026-08-19 clean depth-1 pairing measures 13.86 —
[`results/matrix-714/stability/`](results/matrix-714/stability/)):

```bash
WITH_MTP=1 SPEC_DEPTH=1 bash scripts/gguf-quickstart.sh  # recommended: --spec-type draft-mtp + depth pinned to 1 (--spec-draft-n-max 1)
WITH_MTP=1 bash scripts/gguf-quickstart.sh               # same MTP head at the implicit upstream depth 3 — the 13.0 tok/s corpus cell
```

Verify (the exact curls the quickstart prints — keep `max_tokens` ≥ 512; this
model thinks before answering and a low cap truncates it):

```bash
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply with exactly: OK"}],"temperature":0,"max_tokens":512}'
```

Point any OpenAI-compatible client at `http://127.0.0.1:8080/v1`. `Ctrl-C`
stops the server. A full scripted validation of this path (boot, greedy, MTP
acceptance, ctx ladder): `bash scripts/06-validate-gguf.sh`.

## Path B — vLLM (262144 context, vision, batch throughput)

```bash
uv sync --group vllm                        # TheRock gfx1151 torch pin (see pyproject.toml)
bash scripts/01-build-vllm.sh               # source build @ 4d2a68d, patches + triton_kernels pinned
SET=bf16 bash scripts/02-fetch-model.sh     # 18-shard BF16 checkpoint, SHA256-verified
bash scripts/03-serve-vllm.sh               # serves on http://127.0.0.1:8000/v1 (conf: configs/serve-args.conf)
```

First-run downloads to budget time for: `uv sync` pulls ≈5.6 GiB (fast from
the AMD nightly index) plus a small PyPI tail, and the build clones vLLM
from GitHub (≈0.4 GiB checkout) — on throttled GitHub/CDN links budget an
hour or more for acquisition before the compile itself starts.

One measured first-run trap on constrained networks: the cold sync can
loop-fail forever on a few small PyPI packages (`numpy`, `transformers`,
`pillow`) — repeated `Downloading …` lines, no install — while the ~2 GiB
of large wheels in the same run succeed. It does not resolve on its own;
route uv through a proxy (`export http_proxy=… https_proxy=…`) or set
`UV_INDEX_URL` to a reachable mirror, and the tail finishes in seconds
([troubleshooting: cold uv sync loop-fail](troubleshooting.md#uv-sync-loop-fail)).

MTP variant (+52.6% per-stream single-stream, 6.5 vs 4.3 tok/s — still below
the interactive floor; use GGUF for chat):

```bash
bash scripts/03-serve-vllm.sh --mtp         # conf: configs/serve-args-mtp.conf
```

DFlash2 variant (v0.1.14 — block-diffusion speculative decoding; 10.2 tok/s
single-stream, +150.1% vs base / +65.3% vs MTP, same-session 2026-08-21;
the first vLLM cell at the interactive floor — for pure interactive speed
the GGUF MTP path at 13.86 tok/s is still faster). `MAX_MODEL_LEN=131072`
below is required, not optional — with the draft loaded the conf's ctx
262144 exceeds the KV budget and the boot refuses (details under the
commands):

```bash
SET=dflash2-bf16 bash scripts/02-fetch-model.sh  # ~3.6 GiB draft, SHA256-verified (models/Qwen3.8-27B-DFlash2)
MAX_MODEL_LEN=131072 bash scripts/03-serve-vllm.sh --dflash2   # conf: configs/serve-args-dflash2.conf
```

`MAX_MODEL_LEN=131072` is required, not optional: with the draft loaded,
ctx 262144 exceeds the KV budget on the 80 GiB pool (21.63 needed vs
15.46 GiB available — the boot refuses; receipt
[`results/rocm-7.14/dflash2-validation.md`](results/rocm-7.14/dflash2-validation.md)).
The draft needs the upstream PR #52816 patch. A fresh `bash
scripts/01-build-vllm.sh` applies it with the build; an existing install from
before the GGUF DFlash2 series (v0.1.8 or earlier) can apply it directly — it is pure Python, no rebuild (the editable
install picks it up):

```bash
git -C third_party/vllm apply ../../patches/vllm-dflash2-pr52816.diff   # from the repo root
```

Boot ~330 s to first healthy poll on a cold compile cache (the corpus
cell's warm boot is 258 s — both real, different cache states).

Verify (boot takes ~171 s base / ~226 s MTP to first healthy poll — that is
measured normal, not a hang):

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"Reply with exactly: OK"}],"temperature":0,"max_tokens":512}'
```

Notes that matter:
- Both confs carry `--skip-mm-profiling` — mandatory at `--max-model-len
  262144` (boot otherwise OOMs demanding 256 GiB; with the flag, budgeting
  the vision-encoder peak is the operator's job:
  [troubleshooting: encoder profiling](troubleshooting.md#encoder-profiling)).
- Never drop `--no-sync` semantics: the serve script runs
  `uv run --no-sync` because a bare `uv run` would re-sync and DELETE the
  editable vLLM (`scripts/03-serve-vllm.sh` header).
- A full scripted validation of this path: `bash scripts/04-validate-vllm.sh`
  (see [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md)).

## Guidance: MTP, vision, context, concurrency

**MTP.** On (the recommended path): `WITH_MTP=1 SPEC_DEPTH=1` (GGUF,
single stream, +28.2% on the corpus cell — depth 1 is the recommended
depth; a bare `WITH_MTP=1` boots the implicit upstream depth 3) or
`bash scripts/03-serve-vllm.sh --mtp` (vLLM, beneficial through c8). Off:
at 16-stream batching MTP *regresses* −19.4% aggregate — serve base instead
([troubleshooting: MTP at concurrency](troubleshooting.md#mtp-concurrency)).

**Vision.** Both paths serve single-small-image input end-to-end (validated
with one 64×64 PNG each; receipts:
[`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md) ## Vision,
[`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md) ## Vision).
Anything beyond that is unbudgeted: on vLLM the encoder peak is not reserved
under `--skip-mm-profiling`; on llama.cpp the boot warns about
`--image-min-tokens 1024` for grounding tasks (measured: not needed for the
color task; try it for bounding-box work).

**Context tiers.**
<a id="context-tiers"></a>

| Tier | GGUF (`CTX_SIZE=<n>`) | vLLM |
|---|---|---|
| 32768 | ✅ recommended (c1) | not offered (conf pins 262144) |
| 131072 | ✅ recommended (c1) — validated default | — |
| 262144 | boots, +8.0 GiB GTT over 131072 (33.9 GiB total) — capacity-OK | ✅ serves; KV budget ≈ one full-depth request |

GGUF deep-prompt retrieval is **not depth-reliable** (120K tier confident
miss): treat deep-context answers as unverified
([`results/matrix-714/long-context-smoke.json`](results/matrix-714/long-context-smoke.json)).
Details: [GTT growth](troubleshooting.md#gtt-growth),
[vLLM KV ceiling](troubleshooting.md#kv-ceiling),
[retrieval caveat](troubleshooting.md#deep-context-retrieval).

**Concurrency.** Single-user interactive: GGUF `WITH_MTP=1 SPEC_DEPTH=1`
(the recommended path). Multi-stream:
vLLM (the GGUF path's greedy decoding degrades after sustained multistream
load — restart or switch: [troubleshooting: greedy
degradation](troubleshooting.md#greedy-degradation)). Every measured
configuration with its verdict:
[`results/benchmark.md`](results/benchmark.md).

## Where to go next

- DFlash 2 speculative decoding (gfx1100/W7900-class evidence, opt-in `WITH_DFLASH2=1`): [`results/dflash2/`](results/dflash2/README.md)

- All receipts, one index: [`results/README.md`](results/README.md)
- Porting to other MI-series/RDNA setups: [`adaptation.md`](adaptation.md)
- Adding your GPU as evidence: [`hardware-validation.md`](hardware-validation.md)
- Method behind every number: [`results/METHODOLOGY.md`](results/METHODOLOGY.md)
