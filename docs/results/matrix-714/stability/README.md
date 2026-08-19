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
separate artifact from `scripts/stability-soak.sh`. These numbers were
integrated into the verdicts/docs wording by S2 (v0.1.3); this directory
remains the raw evidence.

Host: gfx1151 (Ryzen AI MAX+ PRO 395 / 8060S), RADV (Mesa 25.2.8) ICD,
llama.cpp pin `4df29be4` build `build-714-vk` — identical to the v0.1.2
session. Same machine later the same day = a second measurement session, not
a second host; the ICD dimension stays single (untested claim, by scope).
Session 3 (2026-08-19 UTC) is a third session on the next day — same host,
same pin, hip `build-714` + vulkan `build-714-vk`, same runner and prompt
set — adding the cross-day dimension and the depth-explicit hip side of the
backend pairing (see its section below).

## Session index

| Session | Date (UTC) | Contents | Method |
|---|---|---|---|
| session 1 (= v0.1.2) | 2026-08-18 morning (cells started 05:41–05:43Z) | the 3 Vulkan c1 cells in [`../cells/`](../cells/) | `scripts/run-cell-gguf.sh`, project `CELLS_DIR` |
| [session2-2026-08-18](session2-2026-08-18/) | 2026-08-18, receipt timestamps span 11:28:12Z–12:01:21Z | 3 re-measured cells + one 30-min sustained-load soak | runner with `CELLS_DIR=<this session dir>` (matrix untouched); `scripts/stability-soak.sh` for the soak |
| [session3-2026-08-19](session3-2026-08-19/) | 2026-08-19, receipt timestamps span 00:56:51Z–00:59:50Z | 4 re-measured cells: hip mtp-c1 with explicit depth 1 (the depth-matched pairing side) + the 3 Vulkan c1 cells (cross-day re-run); no soak | runner with `CELLS_DIR=<this session dir>` (matrix untouched) |

## Cell re-measurement: v0.1.2 vs session 2

Each run is one boot + one throughput bench + one greedy anchor. c1 cells
have a single stream, so the per-run median is that stream's value.
"stream tok/s" is `1000/tpot_ms` (the project's headline metric);
"aggregate tok/s" is `completion_tokens / wall_s` (TTFT included, hence lower).
The s1 column is the **v0.1.2-canonical cell** (the receipts in
[`../cells/`](../cells/) behind the 28-cell matrix and the verdicts); s2 is
this session's receipt. Both sides print at the corpus 2dp convention, so
the numbers cross-reference cleanly with
[`benchmark.md`](../../benchmark.md) — the
s1 values are exactly the canonical cell medians (16.00 / 15.05 / 10.65,
not re-roundings). Delta columns are exact-basis (s2 − s1 computed from the
receipts before rounding, displayed at 2dp) so each Δ matches its pct, which
is also exact-basis.

| Cell | stream tok/s s1 | stream tok/s s2 | delta | aggregate s1 | aggregate s2 | delta | anchor s1 | anchor s2 |
|---|---|---|---|---|---|---|---|---|
| `gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072` (recommended) | 16.00 | 16.25 | +0.24 (+1.5%) | 10.42 | 10.52 | +0.10 (+0.9%) | ok | ok |
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

## Session 3 (2026-08-19): cross-day re-runs + the depth-1 pairing side

Four cells, one boot each, serial, GPU clean between cells, no soak. Same
runner, same prompt set, same pin; `CELLS_DIR` pointed at
[`session3-2026-08-19/`](session3-2026-08-19/) so the matrix stayed
untouched. Receipts:
[`gguf-hip-udq4kxl-auto-mtp-c1-ctx131072.json`](session3-2026-08-19/gguf-hip-udq4kxl-auto-mtp-c1-ctx131072.json),
[`gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json`](session3-2026-08-19/gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json),
[`gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072.json`](session3-2026-08-19/gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072.json),
[`gguf-vulkan-udq4kxl-auto-base-c1-ctx131072.json`](session3-2026-08-19/gguf-vulkan-udq4kxl-auto-base-c1-ctx131072.json).

Run facts: 4/4 boot ok (health wall 6 s each), 0 failed streams, anchors
ok 4/4, no degraded receipts. The hip receipt's `server_flags` carry
`--spec-draft-n-max 1` verbatim (binary `build-714`, log line "depth 1 via
--spec-draft-n-max") — unlike the canonical hip mtp-c1 cell of 2026-08-16
(implicit depth default 3, no depth flag in its `server_flags`), this is a
depth-explicit hip measurement. Same-day receipt pair for the backend
comparison: hip 00:56:51Z, vulkan 00:57:37Z.

### Cross-day stability: per-stream medians s1 / s2 / s3

The same three Vulkan c1 cells as the table above; s1 = the v0.1.2
canonical cell, s2 = the 2026-08-18 re-run, s3 = this session (next UTC
day). Tok/s medians at the corpus 2dp convention; spread is exact-basis
(max − min)/min over the three exact medians, shown at 2dp.

| Cell | s1 (08-18) | s2 (08-18) | s3 (08-19) | max spread |
|---|---|---|---|---|
| `gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072` | 16.00 | 16.25 | 14.53 | 11.81% |
| `gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072` | 15.05 | 15.25 | 11.67 | 30.70% |
| `gguf-vulkan-udq4kxl-auto-base-c1-ctx131072` | 10.65 | 10.91 | 10.29 | 6.07% |

Footnote (s1 mtp4 cell, pre-existing, noted for S5 by the S4 verifier):
its single stream finished at 238 tokens with `finish_reason=stop`, where
every other re-measured c1 stream hit the 256-token cap
(`finish_reason=length`) — a one-stream finish-reason outlier in the
v0.1.2 corpus receipt, not a session-3 artifact.

Cross-session facts from the receipts (numbers only): the same-day pair
s1→s2 moved +1.3%…+2.5% (table above); s3 sits below both prior sessions
on all three cells — vs s1/s2 respectively: mtp −9.21%/−10.56%, mtp4
−22.49%/−23.49%, base −3.35%/−5.72% — and s3 TTFT is higher on all three
(9.94 / 12.21 / 11.78 s vs 8.36–8.83 s across s1/s2). In the same session
the hip mtp-c1 run shows TTFT 5.43 s, in line with the 2026-08-16 hip
receipt (5.47 s). Cell-run anchors are now 10/10 across s1/s2/s3 (11/11
including the soak anchor).

### Backend pairing at matched depth 1 (session 3, same day)

Per-stream medians at 2dp; gap = vulkan − hip, exact-basis (computed from
the exact medians before rounding, displayed at 2dp), % = gap / hip side.

| Pairing | hip mtp-c1 | vulkan mtp-c1 | gap | % of hip |
|---|---|---|---|---|
| depth-matched d1 — both session 3 (2026-08-19), both explicit `--spec-draft-n-max 1` | 13.86 | 14.53 | +0.67 | +4.81% |
| mixed-depth (context only) — hip implicit d3 (canonical cell, 2026-08-16) vs vulkan d1 (s1 cell, 2026-08-18) | 13.00 | 16.00 | +3.00 | +23.07% |

Aggregate basis for the same rows: depth-matched d1 — hip 10.74 vs vulkan
9.31 tok/s (gap −1.43, −13.31% of hip); mixed-depth context — hip 10.21 vs
vulkan 10.42 (gap +0.21, +2.11% of hip). Depth note on the hip side
(different days, so depth is confounded with session): hip mtp-c1 implicit
d3 (2026-08-16) 13.00 vs explicit d1 (session 3) 13.86 tok/s (+0.86,
+6.61%). Anchors ok on all receipts involved.
