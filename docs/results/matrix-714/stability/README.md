# Stability study — Vulkan cells under independent re-measurement

This directory holds **new-facts-new-receipts** stability evidence for the
Vulkan backend cells that the v0.1.2 ruling (2026-08-18) promoted to
recommended quickstart opt-in while explicitly caveating *"single-session
runtime, one ICD"*. Nothing here edits the project benchmark surfaces: the
matrix (`../matrix.json`), the verdicts (`configs/benchmark-verdicts.json`),
`README.md`, `docs/results/benchmark.md`, and `docs/results/matrix-714/cells/`
are **untouched by design** — session receipts are collected through the cell
runner's community `CELLS_DIR` mechanism (`scripts/run-cell-gguf.sh` with a
non-default `CELLS_DIR` skips the matrix flip), and the soak receipt is a
separate artifact from `scripts/stability-soak.sh`. Integrating these numbers
into verdicts/docs wording is a later step (S2); this directory is the raw
evidence.

Host: gfx1151 (Ryzen AI MAX+ PRO 395 / 8060S), RADV (Mesa 25.2.8) ICD,
llama.cpp pin `4df29be4` build `build-714-vk` — identical to the v0.1.2
session. Same machine later the same day = a second measurement session, not
a second host; the ICD dimension stays single (untested claim, by scope).

## Session index

| Session | Date (UTC) | Contents | Method |
|---|---|---|---|
| session 1 (= v0.1.2) | 2026-08-18 morning | the 3 Vulkan c1 cells in [`../cells/`](../cells/) | `scripts/run-cell-gguf.sh`, project `CELLS_DIR` |
| [session2-2026-08-18](session2-2026-08-18/) | 2026-08-18 ~12:40Z | 3 re-measured cells + one 30-min sustained-load soak | runner with `CELLS_DIR=<this session dir>` (matrix untouched); `scripts/stability-soak.sh` for the soak |

## Cell re-measurement: v0.1.2 vs session 2

Each run is one boot + one throughput bench + one greedy anchor. c1 cells
have a single stream, so the per-run median is that stream's value.
"stream tok/s" is `1000/tpot_ms` (the project's headline metric);
"aggregate tok/s" is `completion_tokens / wall_s` (TTFT included, hence lower).

| Cell | stream tok/s s1 | stream tok/s s2 | delta | aggregate s1 | aggregate s2 | delta | anchor s1 | anchor s2 |
|---|---|---|---|---|---|---|---|---|
| `gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072` (recommended) | 16.01 | 16.25 | +0.24 (+1.5%) | 10.42 | 10.52 | +0.10 (+0.9%) | ok | ok |
| `gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072` | 15.05 | 15.25 | +0.20 (+1.3%) | 9.76 | 10.11 | +0.35 (+3.6%) | ok | ok |
| `gguf-vulkan-udq4kxl-auto-base-c1-ctx131072` | 10.65 | 10.91 | +0.27 (+2.5%) | 7.81 | 8.07 | +0.26 (+3.3%) | ok | ok |

Reading: all three cells reproduce within **+0.9% to +3.6%** of the v0.1.2
numbers (session 2 slightly faster across the board — consistent with a
warmer machine rather than any regression), anchors clean **6/6** across both
sessions, load memory within 5–10 MiB of session 1 (VRAM 29453/31279/27870
MiB). No instability observed at single-boot granularity. Receipts:
[`session2-2026-08-18/gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json`](session2-2026-08-18/gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json),
[`...-mtp4-c1-ctx131072.json`](session2-2026-08-18/gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072.json),
[`...-base-c1-ctx131072.json`](session2-2026-08-18/gguf-vulkan-udq4kxl-auto-base-c1-ctx131072.json).

## Sustained-load soak (30 min, recommended config)

`SOAK_MINUTES=30` of back-to-back bench cycles (same prompt set and client
args as the cell bench) against ONE boot of the recommended config
(`BACKEND=vulkan WITH_MTP=1 SPEC_DEPTH=1 CTX_SIZE=131072`, default unified
boot), ending with one greedy anchor. Receipt:
[`session2-2026-08-18/soak-gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json`](session2-2026-08-18/soak-gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json).

- Cycles: **108/108 ok**, 0 failed streams, 0 mid-soak health flaps, 0
  anomalies; wall 30.1 min; server never restarted.
- Per-cycle aggregate tok/s: min **10.15** / median **15.22** / max **16.09**.
  The min is cycle 1 — a cold-prefix effect (the first request pays full
  prompt processing for the 1412-token prompt; later cycles hit the KV prefix
  cache), the same effect that makes single-shot cell aggregates (~10.4)
  lower than per-stream rates (~16.2). Cycles 2+: median 15.22.
- Per-cycle stream tok/s (1000/tpot, cache-independent): min **15.07** /
  median **16.23** / max **17.16** — every cycle within ±6% of the median.
- Drift trend: mild settle-down, **first-half 16.43 → second-half 16.00
  stream tok/s (-2.6%)** (aggregate -2.8%); monotone-ish decline consistent
  with thermal/scheduler settle, not progressive degradation.
- Anchor after 30 min of load: **ok** (`anchor_ok=true`, content tail `OK`).
- Exit hygiene: server torn down, GTT drained to the idle baseline, GPU-clean
  check passed (`exit_gpu_clean=true`).

Finding: **no instability**. A 30-minute sustained load on the recommended
Vulkan config reproduced the cell-run throughput band with every cycle
healthy and a clean post-load greedy anchor. The remaining untested
dimensions are unchanged: single host, single ICD (RADV 25.2.8), single
boot per cell — the soak covers exactly one of those (sustained load).
