# Changelog

All notable changes to this project are documented here. Every number below
recomputes from committed artifacts: verdicts
[`configs/benchmark-verdicts.json`](configs/benchmark-verdicts.json), generated
tables [`docs/results/benchmark.md`](docs/results/benchmark.md), raw cell
receipts [`docs/results/matrix-714/cells/`](docs/results/matrix-714/cells/),
and the rehearsal receipt
[`docs/results/rocm-7.14/one-pass-rehearsal.md`](docs/results/rocm-7.14/one-pass-rehearsal.md).

## v0.1.0 — 2026-08-17

First public release: the reproducible RDNA reference for serving
[Qwen/Qwen3.8-27B](https://modelscope.cn/models/Qwen/Qwen3.8-27B) on AMD ROCm
7.14, validated end-to-end on the reference host (AMD Ryzen AI MAX+ PRO 395 /
Radeon 8060S, `gfx1151`, 80 GiB unified GTT pool). Method: Adapt → Validate →
Benchmark → Explain → Reproduce. Design spec:
`docs/superpowers/specs/2026-08-16-qwen3.8-27b-rocm-design.md`.

## Highlights

- **Both serving paths validated on real hardware** — vLLM (source build @
  `4d2a68d`, BF16) and llama.cpp (HIP build @ `4df29be`, UD-Q4_K_XL): text,
  MTP speculative decoding, 262144-token context, and single-small-image
  vision, each with committed receipts
  ([vLLM](docs/results/rocm-7.14/vllm-validation.md),
  [GGUF](docs/results/rocm-7.14/gguf-validation.md)).
- **A 20-cell benchmark matrix with UX-first verdicts** — 4 recommended /
  10 caution / 6 avoid, generated from the raw cells by a pre-declared ladder
  plus a dated controller-review layer
  ([`configs/benchmark-verdicts.json`](configs/benchmark-verdicts.json),
  [`docs/results/benchmark.md`](docs/results/benchmark.md)). The quickstart
  can never point at a pit: CI-enforced
  ([`tests/test_verdicts.py`](tests/test_verdicts.py)).
- **Interactive chat headline** — GGUF path, `WITH_MTP=1`: 13.0 tok/s
  per-stream median (TPOT 76.9 ms) at ctx 131072, **+28.2%** per-stream over
  the 10.1 tok/s default boot (aggregate basis +20.8%; both bases labeled in
  the verdict).
- **Honesty clauses shipped as data, not prose** — every verdict carries
  reason/conditions/workaround; the best aggregate on this host (vLLM
  base-c16, 38.6 tok/s) is explicitly batch-only (3.0 tok/s per-stream
  median); deep-context retrieval is reported non-monotonic (30K PASS / 120K
  confident miss / 247K PASS), so `max_usable_context` above ~30K is declared
  **not established**
  ([`docs/results/matrix-714/long-context-smoke.json`](docs/results/matrix-714/long-context-smoke.json)).
- **Community hardware-validation protocol, PR-ready** — first target: AMD
  Radeon PRO W7900 (`gfx1100`, 48 GiB discrete GDDR6); evidence schema,
  checker profile, generated README matrix row, and GitHub issue template
  ([§ Community hardware validation](#community-hardware-validation) below).
- **One-pass reproduce rehearsal** — a stranger's first run rehearsed in a
  fresh clone from a clean shell; 1 blocker + 6 annoyances found and fixed, 2
  cosmetics ledgered; unrehearsed surfaces listed honestly
  ([§ One-pass rehearsal](#one-pass-rehearsal) below).

## Serving paths

Measured status on the reference host (`gfx1151`, ROCm 7.14) — honest, not
marketing:

| Path | Measured status | Evidence |
|---|---|---|
| llama.cpp / GGUF (HIP @ `4df29be`, UD-Q4_K_XL) | **The interactive path.** All 3 ctx tiers recommended at c1 (10.1 tok/s median; 10.0 @32768; 10.1 @262144); `WITH_MTP=1` lifts c1 to 13.0 tok/s (+28.2% per-stream). c4 below the 10 tok/s interactive floor (caution); c8/c16 degraded by the greedy-degradation pit (avoid). | [`docs/results/rocm-7.14/gguf-validation.md`](docs/results/rocm-7.14/gguf-validation.md), [`docs/results/benchmark.md`](docs/results/benchmark.md) |
| vLLM (source build @ `4d2a68d`, BF16, ctx 262144) | **The capacity/batch/vision path — not interactive on this host.** All 8 measured cells below the 10 tok/s interactive floor (controller ruling 2026-08-17); best aggregate measured 38.6 tok/s @base-c16; MTP +52.6% per-stream @c1 (6.5 vs 4.3 tok/s) but still below the floor, and **inverts at c16** (-19.4% aggregate: 31.1 vs 38.6 tok/s — the avoid cell). All 8 greedy anchors clean — the llama.cpp pit does not reproduce here. | [`docs/results/rocm-7.14/vllm-validation.md`](docs/results/rocm-7.14/vllm-validation.md), [`docs/results/benchmark.md`](docs/results/benchmark.md) |

Redirect rule (recorded in every vLLM verdict's conditions): interactive chat
→ GGUF path; 262144 context, vision, aggregate batch throughput → vLLM.

## Benchmark matrix

**20 measured cells — 4 recommended / 10 caution / 6 avoid** (of 48 declared:
20 planned not run — time-boxed session, machinery complete; 8 dropped — the
vLLM ctx-32768 tier is not offered by the engine). Declaration manifest
[`docs/results/matrix-714/matrix.json`](docs/results/matrix-714/matrix.json);
frozen measurement contract
[`docs/results/METHODOLOGY.md`](docs/results/METHODOLOGY.md); verdicts
reviewed and recorded by `controller-2026-08-17` ("the ladder proposes; the
controller disposes").

Headline numbers (full tables with per-cell links in
[`docs/results/benchmark.md`](docs/results/benchmark.md); every cell links its
raw receipt under
[`docs/results/matrix-714/cells/`](docs/results/matrix-714/cells/)):

| Cell | Verdict | Per-stream med | Aggregate | Note |
|---|---|---|---|---|
| `gguf-udq4kxl-auto-mtp-c1-ctx131072` | ✅ recommended | 13.0 tok/s (TPOT 76.9 ms) | 10.2 tok/s | +28.2% per-stream vs base; the quickstart's `WITH_MTP=1` |
| `gguf-udq4kxl-auto-base-c1-ctx131072` | ✅ recommended | 10.1 tok/s (TPOT 98.6 ms) | 8.4 tok/s | the quickstart default boot |
| `gguf-udq4kxl-auto-base-c1-ctx32768` / `…ctx262144` | ✅ recommended | 10.0 / 10.1 tok/s | 8.3 / 8.4 tok/s | all ctx tiers clean at c1 |
| `vllm-bf16-auto-base-c16-ctx262144` | ⚠️ caution | 3.0 tok/s (min 2.58) | **38.6 tok/s** | best batch cell measured; batch presentation only |
| `vllm-bf16-auto-mtp-c1-ctx262144` | ⚠️ caution | 6.5 tok/s | 5.8 tok/s | +52.6% per-stream vs base — still below the floor |
| `vllm-bf16-auto-mtp-c16-ctx262144` | ❌ avoid | 2.98 tok/s (min 1.85) | 31.1 tok/s | MTP inverts at c16: -19.4% aggregate vs base |
| 5 × `gguf-…-{base,mtp}-c{4,8,16}-…` | ❌ avoid | 1.4–5.8 tok/s | 10.7–27.5 tok/s | greedy-degradation pit (anchor FAILED); throughput secondary |

## Known good and known bad

The full, always-current lists live in the README's generated block
([Known good / known bad](README.md#known-good--known-bad)) with the
machine-readable source of truth in
[`configs/benchmark-verdicts.json`](configs/benchmark-verdicts.json). Shape:

- **Known good** — GGUF interactive at c1 (all ctx tiers); vLLM
  anchor-clean in all 8 cells (including anchors run immediately after
  16-stream benches); boot reliability (zero failed streams across all 20
  cells; GGUF boots 4–6 s warm, vLLM 171/226 s).
- **Known bad** — the llama.cpp HIP greedy-degradation pit (`'////'`
  repetition after sustained multi-stream load; 5 avoid cells; workaround:
  restart, multi-stream loads → vLLM; upstream issue drafted:
  [`docs/upstream/llama-cpp-hip-greedy-degradation.md`](docs/upstream/llama-cpp-hip-greedy-degradation.md));
  MTP inversion at vLLM c16; vLLM encoder-profiling OOM without
  `--skip-mm-profiling`; +8.0 GiB GTT growth per 131,072 tokens of GGUF KV
  (64 KiB/token bf16); vLLM KV ceiling at 262144 (one full-depth stream
  fits, two don't); deep-context retrieval unverified above ~30K.
- Every pit is documented in the standard symptom → repro → diagnosis →
  workaround → upstream format in
  [`docs/troubleshooting.md`](docs/troubleshooting.md).

## Community hardware validation

This release ships the contract for adding other AMD GPUs as **community
evidence** — never as project verdicts (separate namespace:
[`configs/community/`](configs/community/),
`docs/results/matrix-714/community/`):

- Protocol doc: [`docs/hardware-validation.md`](docs/hardware-validation.md)
  — what a submission MUST include (filled issue template, community-profile
  env-check receipt, rocm-smi receipts at idle/under load, exact commands,
  raw cells from this repo's own runners, stack manifest, schema-valid index
  entry; one PR per platform), review criteria, and what community status
  does NOT grant.
- Issue template:
  [`.github/ISSUE_TEMPLATE/hardware-validation.yml`](.github/ISSUE_TEMPLATE/hardware-validation.yml);
  entry schema:
  [`schemas/community-platform.schema.json`](schemas/community-platform.schema.json);
  empty starting index:
  [`configs/community/platforms.json`](configs/community/platforms.json).
- `bash scripts/00-check-env.sh --profile community` accepts any AMD gfx arch
  with ROCm present (host tools + kernel floor still enforced) and prints
  `COMMUNITY-PROFILE: arch=<gfxNNNN> … NOT project-validated`.
- First target: **AMD Radeon PRO W7900 (`gfx1100`, 48 GiB discrete GDDR6,
  no UMA/GTT pool)** — shown as 🚧 Planned in the README hardware matrix.
  The protocol prescribes the evidence format, NOT a stack: the TheRock
  nightly index used on the reference host has no gfx1100 builds (404,
  verified 2026-08-17), so submitters document their own PyTorch/vLLM
  sources. Community runners write to their own `CELLS_DIR` and cannot touch
  the project matrix.

## One-pass rehearsal

Receipt:
[`docs/results/rocm-7.14/one-pass-rehearsal.md`](docs/results/rocm-7.14/one-pass-rehearsal.md)
(corrected version — the first draft's false cold-sync claim is documented,
not silently rewritten). Summary, per the corrected receipt:

- **GGUF path: one-pass clean.** The literal README → getting-started flow
  completed in a fresh clone from a clean shell; every fail-fast error was
  actionable; 173/173 markdown links resolved. The stranger-path llama.cpp
  build was done for real: 1232 s wall (≈14 min source acquisition at
  throttled GitHub ~45 KiB/s + ≈6.5 min compile), smoke
  `version: 0.1.0-dev (build 1, commit 4df29be4f)`.
- **vLLM build path: rehearsed for real** — cold sync to a complete venv
  (<1 min once correctly routed; ~2 GiB of TheRock wheels already pulled by
  the failed direct attempt) + a 6-minute source build with passing registry
  smoke (`REGISTRY-OK`). **Network pit documented** (this host's network):
  the no-proxy cold `uv sync` hard loop-fails on three small PyPI packages
  (numpy/transformers/pillow) after ~60 min while every large wheel
  succeeds; workaround `http_proxy`/`https_proxy` or `UV_INDEX_URL`
  ([pit entry](docs/troubleshooting.md#uv-sync-loop-fail)).
- **Friction found and fixed:** 1 blocker (F5: build script stripped the
  committed `validated` block — `373c9d7`) + 6 annoyances (F1 `acb8507`,
  F2/F4 `aacd9ab`, F3 `7e7511e`, F8 `3c2125e`, F9 `0420a11`); 2 cosmetics
  ledgered (F6, F7). No blockers outstanding.
- **Unrehearsed surfaces (honest list):** cold OS/ROCm install,
  GitHub-hosted CI first run, fresh 51.77 GiB BF16 + 17.56 GiB GGUF model
  downloads, the stranger's actual vLLM GitHub clone (substituted; the
  patch/build machinery itself was rehearsed), vLLM serving scripts, 262K
  smoke reruns, uv cache-warm vs cold, the unmeasured unified-boot
  c4@131072 cell.

## Full commit log

The complete history ships in this first release — from a clean tree, run:

```bash
git log --oneline            # full history up to the v0.1.0 tag
git log --oneline main..feature/release-v0.1   # the release branch delta
```

Release-branch highlights (full messages in the log): dual-path serving
configs + source builds (`77aaeb9`, `48b85a0`, `f77932d`, `3362579`),
GGUF/vLLM validation receipts (`aeeb560`, `50f54ac`, `f17732a`), benchmark
methodology + verdict system + 20 measured cells (`cac69b3`, `05763cc`,
`c484e5c`, `1a1c697`), community hardware-validation protocol (`98d98c6`),
Explain docs + upstream issue draft (`6e0b558`), one-pass rehearsal +
friction fixes (`acb8507`, `aacd9ab`, `7e7511e`, `373c9d7`, `3c2125e`,
`0420a11`).
