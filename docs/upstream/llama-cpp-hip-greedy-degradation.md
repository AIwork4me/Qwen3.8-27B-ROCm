# llama.cpp (HIP) greedy-degradation on gfx1151 — evidence pack + owner-action brief

**This is not a ready-to-file issue text.** llama.cpp's
[AI usage policy](https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md#ai-usage-policy)
prohibits AI-written bug reports and comments (undisclosed AI usage may result
in a permanent ban), so the text posted upstream must be written by the owner,
in the owner's words. This document is what the repo owes the owner instead:
the committed evidence, the links, the recommended action, and facts-only
source notes to write from. See "Policy" below before posting anything.

**Status (2026-08-18).** The pit measured at our pin ([METHODOLOGY §6]
(../results/METHODOLOGY.md), five `avoid` cells) is **live at llama.cpp master
HEAD `01818e495`** (2026-08-17) on gfx1151 / ROCm 7.14 — control E1 failed the
greedy anchor with the identical `'////'` tail. Open PR
[ggml-org/llama.cpp#25863](https://github.com/ggml-org/llama.cpp/pull/25863)
("ggml-cuda: avoid direct ROCm_Host compute on HIP integrated GPUs",
`fix/hip-apu-host-buffer`, +25/−2 in `ggml-cuda.cu`) is **differentially
verified as a candidate fix on this host**: with the PR applied, the anchor
passed 2/2 runs under the same load; without it, 3/3 FAILs across two upstream
commits (idle-host tally, E0/E1/E3 vs E2). Existing trackers cover our case —
**no new issue should be filed** (duplicate policy).

## Control-experiment receipts (E0–E3, 2026-08-18)

Same host, model, flags, and byte-identical load sequence across all four;
full narratives in [`../results/upstream-controls/README.md`](../results/upstream-controls/README.md).

| Exp | Build | mmproj | Anchor after 8-stream bench | Verdict | Receipt |
|---|---|---|---|---|---|
| E0 | build-714 @ `4df29be4` (the pin, no rebuild) | on | FAIL, tail `"////////////////"` | pit reproduced (reference) | [`../results/upstream-controls/e0-build714-4df29be4.json`](../results/upstream-controls/e0-build714-4df29be4.json) |
| E1 | master HEAD `01818e495` (fresh clone, HIP build) | on | FAIL, tail `"////////////////"` | **pit live at master** | [`../results/upstream-controls/e1-master-01818e49.json`](../results/upstream-controls/e1-master-01818e49.json) |
| E2 | master HEAD `01818e495` + PR #25863 patch (head `ce82541a`) | on | PASS `"OK"` — 2/2 runs | **pit absent with the PR** | [`../results/upstream-controls/e2-master-pr25863.json`](../results/upstream-controls/e2-master-pr25863.json) |
| E3 | master HEAD `01818e495` (patch reverted) | **off** | FAIL, tail `"////////////////"` | pit reproduces without mmproj | [`../results/upstream-controls/e3-master-nommproj.json`](../results/upstream-controls/e3-master-nommproj.json) |

## Recommended owner action

1. **Comment on [#25992](https://github.com/ggml-org/llama.cpp/issues/25992)
   (primary).** It is the same-host tracker: gfx1151 / Radeon 8060S, ROCm 7.14,
   parallel-slot corruption bisected to the HIP `prop.integrated` path
   (`c7d87229`), with `'////'` degeneration already logged in-thread as a
   secondary symptom. Its author (AMD contributor liminfei-amd) wrote PR #25863
   and explicitly invited affected gfx1150/gfx1151 users to test it and share
   results — E1/E2 are exactly that test, plus the master-HEAD liveness datum.
2. **Cross-link from [#23577](https://github.com/ggml-org/llama.cpp/issues/23577)**,
   the `////`-family tracker where ggerganov is collecting hardware /
   CUDA-ROCm / llama.cpp versions from sufferers: a short comment noting the
   gfx1151 + ROCm 7.14 data sits in the #25992 thread, with our receipts.
3. **Do NOT file a new issue.** CONTRIBUTING.md: duplicates are closed without
   questions, and both symptom families are already maintainer-attended. A new
   issue would also carry the AI-written-body risk this pack exists to avoid.

Sequencing: comment only **after the repo is public and pushed**
([PUSH-CHECKLIST.md](PUSH-CHECKLIST.md) steps 2/4) so the receipt links in
"Public receipt URLs" below resolve for maintainers.

## Source notes for an owner-written comment — FACTS ONLY

*(These are reference facts drawn from committed receipts, not comment prose.
llama.cpp prohibits AI-written reports/comments: the posted text must be the
owner's own writing; any AI assistance must be disclosed per the policy. No
ready-to-paste comment is provided here on purpose.)*

Host / stack (all experiments):

- AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S iGPU (`gfx1151`), 94 GiB RAM,
  ~80 GiB GPU-visible GTT pool; kernel `6.17.0-1032-oem`.
- ROCm 7.14.0 toolchain at `~/rocm-7.14.0` (pins in
  [`../../configs/validated-stack.json`](../../configs/validated-stack.json)).
- Model `Qwen3.8-27B-UD-Q4_K_XL.gguf` (unsloth UD-Q4_K_XL, 16.69 GiB, arch
  `qwen35` — hybrid GDN linear attention + 16 full-attention layers + MTP
  block), `mmproj-F16.gguf` attached except in E3.
- Server flags all runs: `--ctx-size 131072 -ngl 99 --jinja -np 8` (+ mmproj
  unless E3); every boot logged `n_slots = 8, n_ctx_slot = 16384,
  kv_unified = 'false'` (split mode).
- Load: 8 concurrent `/v1/chat/completions` streams, deterministic 8-prompt
  set (~1.3–1.5K prompt tokens/stream), generation capped at 256 tokens,
  temperature 0.7 / top_p 0.95, `--no-thinking`; gate afterwards = one greedy
  anchor `Reply with exactly: OK` (temperature 0), judged by the receipt's
  `anchor_ok` + verbatim `content_tail`.

Per experiment:

- **E0 (pin reference)** — existing `third_party/llama.cpp` build-714 binary
  at `4df29be4f4c3…` (fingerprinted `scripts/05-build-llama.sh` build; server
  banner `0.1.0-dev (build 1, commit 4df29be4f)`), no rebuild. Load shape:
  8/8 streams capped at 256 tokens (`finish_reason=length`), aggregate
  17.9 tok/s, 0 failed streams. Anchor FAIL, tail `"////////////////"`
  (16 `/` characters = the whole completion; the runner records the last 200).
  **Load-interference caveat:** attempt 1 ran while a 16-job HIP compile
  saturated the host and PASSED (6/8 capped, 2 early stops); attempt 2 on the
  idle host reproduced the pit. All FAIL verdicts cited are idle-host runs.
- **E1 (master HEAD)** — fresh clone at `/tmp/lc-master` (pin untouched),
  built with flags identical to `05-build-llama.sh`: `-DGGML_HIP=ON
  -DAMDGPU_TARGETS=gfx1151 -DGPU_TARGETS=gfx1151 -DCMAKE_BUILD_TYPE=Release
  -DROCM_PATH=…/rocm-7.14.0`; HEAD `01818e4956858…` (2026-08-17, banner
  `0.1.1-dev (build 10480, commit 01818e495)`). Load shape: 8/8 capped,
  aggregate 17.7 tok/s, 0 failed. Anchor FAIL, tail `"////////////////"` —
  the pit is NOT fixed at master.
- **E2 (candidate fix)** — the E1 tree with PR #25863 applied (`git apply`,
  clean tree verified first; hunks offset +148..+175; incremental rebuild;
  patch compiles into `libggml-hip.so`, `llama-server` binary is an unchanged
  launcher). PR state at test time: OPEN, unmerged, head `ce82541a`, branch
  `fix/hip-apu-host-buffer`, diffstat +25/−2, file `ggml/src/ggml-cuda/ggml-cuda.cu`.
  Load shape: 7/8 capped + 1 early stop (205 tok), aggregate 16.9 tok/s — the
  shape of the degraded `mtp-c8` matrix cell. Anchor PASS `"OK"` **2/2 runs**
  (attempt 2: 7/8 capped + 1 early stop at 190 tok, 16.2 tok/s; raw repeat at
  `/tmp/e2-repeat.json`, uncommitted).
- **E3 (attribution control)** — E1 build, patch reverted, tree verified
  clean, booted `WITH_MMPROJ=0` (no `--mmproj`). Load shape: 8/8 capped,
  aggregate 17.9 tok/s. Anchor FAIL, tail `"////////////////"` — the vision
  projector is not the trigger.

Idle-host tally: unpatched 3/3 FAIL across two upstream commits (`4df29be4`,
`01818e495`); patched 2/2 PASS. Samples are small; receipts carry per-attempt
bench shapes.

Original matrix evidence (the pin-era record the comment can point to):
five degraded cells — `base-c4-ctx32768` (unified default boot),
`base-c8`/`base-c16`, `mtp-c8`/`mtp-c16` @131072 — all anchors FAILED with
the same tail; clean cells the same day: every `c1` tier, `-np 4` @131072,
unified c4 @262144; vLLM path serving the same model: 8/8 cells anchor-clean
including anchors immediately after 16-stream benches. Cells in
[`../results/matrix-714/cells/`](../results/matrix-714/cells/), tables in
[`../results/benchmark.md`](../results/benchmark.md), pit entry in
[`../troubleshooting.md`](../troubleshooting.md) (#greedy-degradation).

Not claimed (keep this honesty in the owner's text): mechanism inside
llama.cpp is not analyzed beyond the patch-on/patch-off differential; no
CPU/CUDA/other-GPU/other-quant data; correlation between all-capped benches
and the pit is stated as correlation only; the all-capped observation is
confounded by the E0 load-interference caveat above.

## Policy

- [CONTRIBUTING.md — AI usage policy](https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md#ai-usage-policy):
  "It is strictly prohibited to use AI to write your posts for you (bug
  reports, feature requests, …)"; undisclosed AI usage may result in a
  permanent ban. The comment must be owner-written; disclose AI assistance if
  any was used in producing it.
- [CONTRIBUTING.md — duplicates](https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md):
  search first; duplicates are likely closed without questions — hence
  comment-on-trackers, not a new issue.
- Trackers/fix this pack concerns:
  [#25992](https://github.com/ggml-org/llama.cpp/issues/25992) (primary;
  same-host bisect → HIP `prop.integrated`; maintainer invited testing of the
  fix), [#23577](https://github.com/ggml-org/llama.cpp/issues/23577)
  (`////`-family; ggerganov collecting hardware/versions),
  [PR #25863](https://github.com/ggml-org/llama.cpp/pull/25863) (candidate
  fix, differentially verified here).

## Public receipt URLs (valid once `main` is pushed)

For pasting into the GitHub comments (verify they resolve from an incognito
session first, per PUSH-CHECKLIST step 6):

```text
https://raw.githubusercontent.com/AIwork4me/Qwen3.8-27B-ROCm/main/docs/results/upstream-controls/e0-build714-4df29be4.json
https://raw.githubusercontent.com/AIwork4me/Qwen3.8-27B-ROCm/main/docs/results/upstream-controls/e1-master-01818e49.json
https://raw.githubusercontent.com/AIwork4me/Qwen3.8-27B-ROCm/main/docs/results/upstream-controls/e2-master-pr25863.json
https://raw.githubusercontent.com/AIwork4me/Qwen3.8-27B-ROCm/main/docs/results/upstream-controls/e3-master-nommproj.json
```

Index with method and findings:
[`docs/results/upstream-controls/README.md`](../results/upstream-controls/README.md).
