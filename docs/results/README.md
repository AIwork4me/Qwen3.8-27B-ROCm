# Results index — every validation track, one line each

All evidence in this tree is committed, frozen, and receipt-linked; the
measurement contract that froze the rules BEFORE any number existed is
[`METHODOLOGY.md`](METHODOLOGY.md). Start from the top when auditing a claim:
verdict → table → raw cell → method.

| Track | What it is | Status |
|---|---|---|
| [`METHODOLOGY.md`](METHODOLOGY.md) | The frozen measurement contract: study definitions, metrics, pre-declared verdict ladder, memory methodology, llama.cpp slot semantics (§6), vLLM concurrency (§7) | Frozen 2026-08-17 before any cell ran; dated errata only, never silent edits |
| [`rocm-7.14/vllm-validation.md`](rocm-7.14/vllm-validation.md) | vLLM path validation receipts: boot (incl. the 256 GiB encoder-profiling OOM and its `--skip-mm-profiling` remedy), greedy, context probe, MTP with acceptance metrics, reasoning parser, vision | **Validated** — text, MTP, 262144 context, single-small-image vision (vLLM `4d2a68d`, BF16) |
| [`rocm-7.14/gguf-validation.md`](rocm-7.14/gguf-validation.md) | llama.cpp GGUF path validation receipts: boot, greedy, MTP (`--spec-type draft-mtp`) with acceptance lines, ctx ladder to 262144 with a GTT sampler, vision incl. the `--image-min-tokens 1024` variant | **Validated** — text, MTP, vision; ctx 262144 boots (+8.0 GiB GTT, default stays 131072) (llama.cpp `4df29be4` HIP, UD-Q4_K_XL) |
| [`matrix-714/matrix.json`](matrix-714/matrix.json) | The declared cell universe: 56 cells — 28 measured (20 v0.1.0/v0.1.1 priority + 8 v0.1.2 Vulkan×MTP/unified), 20 planned (time-boxed), 8 dropped (vLLM ctx-32768 tier not offered) | Complete for the session; guarded regeneration (`gen-matrix.py --check`) |
| [`matrix-714/cells/`](matrix-714/cells/) | The 28 raw measured cells — every boot line, stream record, anchor result, engine args verbatim | 28/28 measured; 5 GGUF-hip cells recorded `measured(degraded)` (the greedy-degradation pit — not reproducing on Vulkan) |
| [`matrix-714/long-context-smoke.json`](matrix-714/long-context-smoke.json) | S3 deep-prompt retrieval smoke (needle at ~80% depth, exact-substring judge), all three GGUF ctx tiers | Non-monotonic vs depth: 30K PASS / 120K confident miss / 247K PASS — deep retrieval unverified above ~30K |
| [`benchmark.md`](benchmark.md) | Generated result tables (quickstart mapping, both paths + both llama.cpp backends, MTP effect, context capacity, rule application) | Generated from the cells by `gen-verdicts.py` + `render-readme-blocks.py`; verdicts reviewed `controller-2026-08-17` (20 cells, frozen) + `controller-2026-08-18` (8 v0.1.2 cells, per-cell) + file-level `controller-2026-08-19` review (v0.1.4 mapping ruling) re-dated `controller-2026-08-20` (v0.1.7 H2 refinement — verdicts `checked_at`/`reviewed_by`; mapping unchanged) — 8 recommended / 14 caution / 6 avoid |
| [`rocm-7.14/one-pass-rehearsal.md`](rocm-7.14/one-pass-rehearsal.md) | Fresh-clone stranger simulation of README+getting-started (clean shell): every step's outcome, friction ledger, fixes, honest unrehearsed-surfaces list | One-pass clean after 6 friction fixes (1 blocker); vLLM fresh compile confirmed live at ~6 min |
| [`spike/`](spike/README.md) | Pre-validation upstream reconnaissance: vLLM/transformers support (A), llama.cpp/GGUF support (B), quant + KV levers (C), decision table | Decided the dual-path scope 2026-08-16; all conclusions pin-dated |
| [`upstream-controls/`](upstream-controls/README.md) | Upstream control experiments (2026-08-18): the greedy-degradation pit re-run at build-714 vs master HEAD `01818e495` vs master+PR #25863 vs no-mmproj — one receipt JSON per experiment | Pit reproduced at the pin and at master HEAD (also without mmproj); absent in 2/2 runs with PR #25863 applied |
| [`matrix-714/community/`](matrix-714/community/) | Community hardware-validation submissions (docs/hardware-validation.md): raw runner-written cells + receipts per platform — first entry `w7900d-gfx1100-rocm721` (PR #1, 2026-08-18) | 🧪 W7900D GGUF path: 7/7 cells healthy, anchors clean, weights VRAM-resident; `validated.vllm=false` (BF16 cannot fit 48 GiB) |
| [`community-explorations/w7900d-gfx1100/`](community-explorations/w7900d-gfx1100/) | The W7900D submitter's local-lineage working record (own harness): spike, GGUF serving receipt, 16-cell local matrix, FP8-vLLM unlock + vllm#52663 evidence pack, repro scripts | **Context, not evidence** (local harness per the protocol); GGUF conclusions confirmed by the official cells, FP8 path documented as capacity-unlock only |
| [`dflash2/`](dflash2/README.md) | DFlash 2 speculative decoding on gfx1100 (llama.cpp PR #27342): 6 clean-paired cells + c16 probe, losslessness proof (equiv.json 4/4 byte-identical), acceptance probe, n-max sweep | Host-labeled namespace (project matrix untouched) — single-stream SPEC_DEPTH 2–4 ≫ 7 (parity with MTP-d1); DFlash2 wins at c4 |

Machine-readable companions (repo root): verdicts
[`configs/benchmark-verdicts.json`](../../configs/benchmark-verdicts.json),
pins and host facts [`configs/validated-stack.json`](../../configs/validated-stack.json),
spike findings [`configs/spike-findings.json`](../../configs/spike-findings.json).

For the pits behind the `avoid`/`caution` grades, see
[`../troubleshooting.md`](../troubleshooting.md); for reproducing a run,
[`../getting-started.md`](../getting-started.md).
