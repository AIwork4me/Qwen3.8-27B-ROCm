# DFlash2 speculative decoding — Design Spec (Phase: dflash2)

Date: 2026-08-21
Status: Approved in brainstorming (autonomous session; scope fixed by the
tasking: sync upstream, upgrade with DFlash2, host-measured with/without
comparison, quick start)
Method: **Adapt → Validate → Benchmark → Explain → Reproduce**
Predecessor patterns: Muse-Glimmer-30B-ROCm DFlash v1 integration
(`WITH_DFLASH=1` quickstart gating, n-max = block_size − 1 physics,
greedy-equivalence check, `-np 16` pathology warning) and this repo's own
MTP plumbing (`WITH_MTP`/`SPEC_DEPTH`, cell-runner id grammar, receipts).

## 1. Goal

Let users of this repo serve Qwen3.8-27B GGUF with **DFlash 2** block-diffusion
speculative decoding on RDNA (ROCm/HIP), with:

- A **one-switch opt-in** (`WITH_DFLASH2=1`) on the existing quickstart —
  defaults and every non-DFlash2 boot stay byte-identical.
- A **host-measured, clean-paired** "with vs without DFlash2" comparison
  (same llama.cpp build for both arms, same day, same prompts) plus the
  existing MTP arm for context — the vendor table is cited, never
  substituted for local evidence.
- **Losslessness proven on-host**: greedy byte-identity between the
  baseline and DFlash2 boots (DFlash 2 is lossless by construction; the
  project verifies claims it repeats).
- Pits recorded: unmerged-upstream build status, the n-max cap
  (`block_size − 1 = 7`), DFlash2×high-concurrency behavior (the DFlash v1
  `-np 16` pathology is re-probed, not assumed either way).

## 2. Verified facts (input constraints, 2026-08-21)

DFlash 2 draft model (`incoai/Qwen3.8-27B-DFlash2`, mirrored at
`z-lab/…`; HF API + README):

- Draft-only checkpoint: `DFlash2DraftModel`, ~1.92 B params BF16,
  5 layers, reads target layers 5/19/33/47/61; `block_size: 8` →
  **7 draft tokens per verification step**; lossless (greedy exact,
  sampling distribution-preserving).
- Official engines: SGLang (`--speculative-algorithm DFLASH`), vLLM
  (PR #52816), oMLX, **llama.cpp PR #27342**.
- Official GGUF conversions `incoai/Qwen3.8-27B-DFlash2-GGUF`
  (ModelScope mirror live): Q4_K_M 1.1 GiB, Q8_0 2.0 GiB, BF16 3.8 GiB.
  llama.cpp usage per that README: `-hfd …:Q4_K_M --spec-type draft-dflash
  --spec-draft-n-max 7` against a PR-#27342 build.
- llama.cpp PR #27342 (`spec: add DFlash2 support`, state OPEN 2026-08-21,
  head `5ecbe1ac17ec0484c5b44af0bd580cdc9c428ed4`, branch `dflash2`):
  "DFlash2 is enabled when the checkpoint is DFlash2; no need to use extra
  flag" beyond the existing draft plumbing; server + speculative-simple +
  HF→GGUF conversion touched. Vendor-side eval (M5 Pro, Qwen3.8-27B
  Q4_K_M, c1): 1.81–1.85× decode, acceptance ≈ 5.0/7; draft quant
  Q8_0/Q4_K_M within noise of BF16.

This host (evidence host for this phase): AMD Radeon W7900-class
`gfx1100`, 48 GiB discrete VRAM (rocm-smi 51522830336 B), EPYC 9334,
kernel 6.8.0-79-generic — the same host class as the community
`w7900d-gfx1100-rocm721` submission (stack manifest: serving runtime
ROCm 7.2.1 `/opt/rocm`, llama.cpp commit pin 4df29be, GGUF path).
VRAM budget at ctx 131072: community base c4 measured 25.9 GiB resident;
+ draft Q8_0 ≈ 2.0 GiB + draft KV (5 layers) → fits 48 GiB with margin.
Network: huggingface.co direct unreachable from this host; ModelScope and
hf-mirror reachable — all artifacts therefore come from ModelScope
(`host: modelscope` in the manifest, no new host support needed).

## 3. Design

### 3.1 Artifacts (configs/artifact-manifest.json)

New set `dflash2` (ModelScope `incoai/Qwen3.8-27B-DFlash2-GGUF` @ master;
CDN LFS objects are content-addressed by sha256 and both files verify
against the manifest at fetch time): Q8_0 (default draft) + Q4_K_M
(memory-tight alternative). Fetched by the unchanged
`SET=dflash2 bash scripts/02-fetch-model.sh`.

### 3.2 Build (new scripts/07-build-llama-dflash2.sh)

- Clones `third_party/llama.cpp` if absent, fetches `pull/27342/head`
  → `pr-27342` (pinned full SHA recorded in validated-stack), builds HIP
  into `third_party/llama.cpp/build-714-dflash2` — the pinned
  `build-714` and `build-714-vk` are never touched, so every existing
  receipt stays reproducible.
- `AMDGPU_TARGETS` defaults to the GPU rocminfo reports (gfx1151 on the
  reference host, gfx1100 here); toolchain resolution mirrors
  05-build-llama.sh (ROCM_PREFIX override honored).
- Fingerprint-idempotent like 05 (same lib/llama_build.sh helpers).

### 3.3 Serving (scripts/gguf-quickstart.sh — additive WITH_DFLASH2=1)

- Default server for the mode: `build-714-dflash2/bin/llama-server`
  (`LLAMA_SERVER` stays the top-level override; `BACKEND` unchanged —
  the DFlash2 build IS a hip build).
- Flags appended: `-md <draft> --spec-type draft-dflash
  --spec-draft-n-max 7` — the 7 is the DFlash2 physics cap
  (`block_size − 1`; requesting more is clamped upstream with a warning —
  the muse-rocm F-18 lesson applied to v2 at the source).
- Draft resolution mirrors the target-GGUF pattern: manifest-driven
  (`DFLASH_FILE`, default Q8_0), presence + size-gated, fetch remedy
  printed with disk preflight. `WITH_MTP=1` + `WITH_DFLASH2=1` is
  refused (one drafter per boot; the receipt must not be ambiguous).
- `SPEC_DEPTH` is reused as the draft-length knob in this mode
  (default 7) so the cell-runner plumbing stays single-surface.

### 3.4 Evidence (clean pairing, community-style namespace)

- `docs/results/dflash2/`: matrix declaration + cells + receipt for this
  phase, host-labeled (gfx1100 / ROCm 7.2.1 serving / PR-27342 build).
  The project matrix (matrix-714) is NOT edited — same rule as community
  submissions; the runner is pointed via `MATRIX_FILE`/`CELLS_DIR`.
- Cells (id grammar gains the `dflash2` spec part):
  `gguf-hip-udq4kxl-auto-{base,dflash2,mtp}-c{1,4}-ctx131072`
  (split-KV at c4, matching the project c4@131072 semantics) plus a
  time-boxed `dflash2-c16-ctx32768` probe (the v1 `-np 16` pathology —
  measured, not assumed).
- **Both arms boot the SAME PR-27342 binary** (LLAMA_SERVER exported for
  the whole session): the delta isolates DFlash2, not the build — the
  v0.1.4 mixed-pairing lesson applied from the start.
- Greedy anchor (bench_client `--anchor-only`) gates every cell;
  full-prompt byte-identity A/B is done by the new
  `scripts/check-dflash2-equiv.sh` (greedy, thinking disabled, fixed
  prompts, baseline vs DFlash2 completions compared verbatim).

### 3.5 Docs & UX

- README: new `dflash2` generated block (comparison table + one-command
  opt-in) rendered by render-readme-blocks.py; quick-start boot table
  gains the DFlash2 row; Known-good/known-bad gains the DFlash2 rows.
- troubleshooting: unmerged-PR build risk + re-pin procedure, n-max cap,
  `-md` without `--spec-type` silent no-op trap (muse precedent), the
  HF-unreachable/ModelScope fact.
- CHANGELOG entry; validated-stack records the PR pin + n-max evidence
  (code refs into the PR tree, mtp_depth-style).

## 4. Non-goals

- No vLLM/SGLang DFlash2 path on this host (BF16 needs 51.7 GiB > 48 GiB;
  the FP8 vLLM path is a recorded 47×-slower capacity unlock, not a
  performance path). Documented as out-of-scope with pointers.
- No change to any default boot, pinned build, or existing receipt.
- No DFlash v1 (16-block) support — superseded by v2 for this model.

## 5. Risks

- **Unmerged upstream PR** — build may need re-pinning; the pin + fetch
  recipe in validated-stack makes that a one-line change and the receipt
  always records the exact head SHA + `--version` line.
- gfx1100 + PR-build interaction unknown until measured — first cell is
  the smoke gate; failure is recorded as a finding, never hidden.
- DFlash2 × c16 split-KV may reproduce the v1 pathology — time-boxed,
  aborted-cell protocol from muse applies (wall clock recorded).
