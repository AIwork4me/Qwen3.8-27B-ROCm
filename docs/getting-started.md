# Getting started — Qwen3.8-27B on gfx1151 (ROCm 7.14)

Goal: one-pass success. Every command below is the exact command the
validated stack ran; every default points at a `recommended`-verdict cell
(CI-enforced). Two serving paths, pick by job:

| Path | Use it for | Default |
|---|---|---|
| **GGUF (llama.cpp HIP)** | interactive chat | UD-Q4_K_XL, ctx 131072 — 10.1 tok/s per stream (13.0 with MTP) |
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
fingerprinted build:

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

Optional +28% per-stream throughput (13.0 vs 10.1 tok/s, single stream):

```bash
WITH_MTP=1 bash scripts/gguf-quickstart.sh  # adds --spec-type draft-mtp (MTP head from the same GGUF)
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

MTP variant (+52.6% per-stream single-stream, 6.5 vs 4.3 tok/s — still below
the interactive floor; use GGUF for chat):

```bash
bash scripts/03-serve-vllm.sh --mtp         # conf: configs/serve-args-mtp.conf
```

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

**MTP.** On: `WITH_MTP=1` (GGUF, single stream, +28.2%) or
`bash scripts/03-serve-vllm.sh --mtp` (vLLM, beneficial through c8). Off: at
16-stream batching MTP *regresses* −19.4% aggregate — serve base instead
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

**Concurrency.** Single-user interactive: GGUF `WITH_MTP=1`. Multi-stream:
vLLM (the GGUF path's greedy decoding degrades after sustained multistream
load — restart or switch: [troubleshooting: greedy
degradation](troubleshooting.md#greedy-degradation)). Every measured
configuration with its verdict:
[`results/benchmark.md`](results/benchmark.md).

## Where to go next

- All receipts, one index: [`results/README.md`](results/README.md)
- Porting to other MI-series/RDNA setups: [`adaptation.md`](adaptation.md)
- Adding your GPU as evidence: [`hardware-validation.md`](hardware-validation.md)
- Method behind every number: [`results/METHODOLOGY.md`](results/METHODOLOGY.md)
