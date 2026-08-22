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
| [session4-2026-08-19](session4-2026-08-19/) | 2026-08-19, receipt timestamps span 06:32:54Z–06:41:10Z | 5 runs, serial: vulkan mtp-c1 ×3 (boot #1, boot #2 within-day cross-boot, cache-aside arm) interleaved with hip mtp-c1 ×2 (controls); first session with clock/power/temp + mesa-cache telemetry (root-cause step R1) | runner with `CELLS_DIR=<per-run subdirectory of this session dir>` (matrix untouched); the cache-aside arm is orchestrated outside the runner (see its note below) |
| [session5-2026-08-19T2321local](session5-2026-08-19T2321local/) | 2026-08-19, receipt timestamps 15:20:34Z–15:21:45Z (23:20–23:21 local) | 2 runs, serial (first daily warm pair): vulkan mtp-c1 + hip mtp-c1, GPU clean between; same-run telemetry + mesa-cache readings; accompanied by the host-log trigger-hunt evidence note [`trigger-hunt-2026-08-19.md`](trigger-hunt-2026-08-19.md) | runner with `CELLS_DIR=<per-run subdirectory of this session dir>` (matrix untouched) |
| [session6-2026-08-20T0712local](session6-2026-08-20T0712local/) | 2026-08-20 local date (UTC 2026-08-19), receipt timestamps 23:12:02Z–23:13:01Z (07:12–07:13 local) | 2 runs, serial (daily warm pair #2, first after an idle night): vulkan mtp-c1 + hip mtp-c1, GPU clean between; same-run telemetry + mesa-cache readings | runner with `CELLS_DIR=<per-run subdirectory of this session dir>` (matrix untouched) |
| [dflash-pairing-2026-08-21](dflash-pairing-2026-08-21/) | 2026-08-21, UTC | the v0.1.14 DFlash2 pairing: {base,mtp} @131072 re-run cells (6 boots total incl. the dflash corpus boot) — the with-vs-without-DFlash2 same-session basis | runner with `CELLS_DIR=<this session dir>` (matrix untouched); dflash cells in `../cells/` |

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

## Session 4 (2026-08-19): cross-boot / elapsed-time / cache-arm telemetry study

Five runs, serial, one boot per run, GPU verified clean between runs (no
`llama-server` process, GTT at the ~220 MiB idle baseline before every
boot). This is the first session recorded with the R1 telemetry harness:
every receipt carries `load.telemetry` (rocm-smi sclk/mclk/package
power/edge temp from `--showclocks`/`--showpower`/`--showtemp` with the raw
command output verbatim, plus host state) and a NEW `post_bench.telemetry`
block (same fields, captured right after the bench/anchor, before
teardown); the vulkan receipts additionally carry `load.telemetry.mesa_cache`
(du -s KiB / file count / newest mtime of `~/.cache/mesa_shader_cache`,
read before boot and after teardown). Host state identical across all five
runs: boot time `2026-08-12 09:42:40` (`uptime -s`, i.e. the same boot as
s1/s2/s3), power profile `balanced` (`powerprofilesctl get`), GPU
`power_dpm_force_performance_level` `auto` (card1). One telemetry-tolerance
case: run 5's post-bench `--showclocks` output (rc 0) carried no mclk line
— recorded as `mclk_mhz: null` with the snippet in `telemetry.errors`; the
run was unaffected.

Run order (fixed by design, not reordered): vk boot #1 → hip control #1 →
vk boot #2 → hip control #2 → vk cache-aside arm. Receipts (the same cell
id is measured more than once in this session, so each run writes into its
own subdirectory — receipts never overwrite):
[run1-vk-boot1](session4-2026-08-19/run1-vk-boot1/gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json),
[run2-hip-ctrl1](session4-2026-08-19/run2-hip-ctrl1/gguf-hip-udq4kxl-auto-mtp-c1-ctx131072.json),
[run3-vk-boot2](session4-2026-08-19/run3-vk-boot2/gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json),
[run4-hip-ctrl2](session4-2026-08-19/run4-hip-ctrl2/gguf-hip-udq4kxl-auto-mtp-c1-ctx131072.json),
[run5-vk-cacheaside](session4-2026-08-19/run5-vk-cacheaside/gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json).

Disclosures (R2, 2026-08-19): (1) run 5's `mclk_mhz: null` diagnostic
snippet (the `"--showclocks: no rocm-smi output captured"` message text in
`post_bench.telemetry.errors`) was produced by a PRE-FINAL parser revision
— the committed parser (`scripts/run-cell-gguf.sh`) would label that raw
output (sclk line present, no mclk line) "pattern not found"; the recorded
VALUE (null) and the receipt are unaffected and stay immutable. (2) The
hip cross-boot spread printed in the narrative below was corrected
−4.8% → **−4.7%** (exact-basis `(14.06/14.76 − 1)` at 1dp; the −4.8%
was a rounding slip, corrected here — the receipts were always exact).

This README is the numbers index for the sessions — interpretation of
session 4 (the Mesa shader-cache state-dependence root-cause class, the
warm/cold bounds, the floor/ceiling relabels of the pairings, and the
recommendation ruling) lives in the generated ruling note of
[`configs/benchmark-verdicts.json`](../../../../configs/benchmark-verdicts.json)
(the vulkan mtp-c1 cell) and in
[`docs/adaptation.md`](../../../adaptation.md) §Vulkan.

### Per-run table

c1 cells have a single stream, so the per-run median is that stream's value
("stream tok/s" = 1000/tpot_ms, the corpus 2dp convention; "aggregate" =
completion_tokens / wall_s). Telemetry columns show sclk/mclk (MHz) ·
package power (W) · edge temp (°C) at the load snapshot and at the
post-bench snapshot. Boot wall = server health-poll time.

| Run | backend | boot # | stream tok/s | TTFT (s) | aggregate tok/s | anchor | boot wall (s) | load sclk/mclk · power · temp | post-bench sclk/mclk · power · temp | mesa cache before boot → after teardown |
|---|---|---|---|---|---|---|---|---|---|---|
| run1 | vulkan | 1 | 17.10 | 8.37 | 10.99 | ok | 4 | 1350/1000 · 13.06 · 46.0 | 1433/1000 · 31.05 · 57.0 | 7884 KiB / 867 files → 7884 KiB / 867 files (newest mtime moved to the run time) |
| run2 | hip | 1 | 14.76 | 5.46 | 11.26 | ok | 6 | 1374/1000 · 13.03 · 49.0 | 1929/1000 · 53.05 · 58.0 | not captured (vulkan-only field) |
| run3 | vulkan | 2 | 16.96 | 8.50 | 10.88 | ok | 3 | 1355/1000 · 13.03 · 48.0 | 1533/1000 · 32.00 · 57.0 | 7884 KiB / 867 files → 7884 KiB / 867 files (unchanged, newest mtime still run1's) |
| run4 | hip | 2 | 14.06 | 5.46 | 10.82 | ok | 6 | 1350/1000 · 13.04 · 49.0 | 1910/1000 · 52.07 · 58.0 | not captured (vulkan-only field) |
| run5 (cache-aside arm) | vulkan | 3 | 12.38 | 12.45 | 7.75 | ok | 6 | 1332/1000 · 12.06 · 47.0 | 1484/null · 30.04 · 54.0 | (dir absent) → 2136 KiB / 100 files, newest mtime at the run time |

Load memory: run1/run3/run5 VRAM 29080/29080/29082 MiB with GTT
1225/1223/1225 MiB (vulkan splits); run2/run4 VRAM 1185/1183 MiB with GTT
28058/28062 MiB (hip splits). Run 4's stream finished at 253 tokens with
`finish_reason=stop`; every other session-4 stream hit the 256-token cap
(`finish_reason=length`). Within-run deltas: vk boot #1 vs boot #2
(≈2 min apart, separate server processes) 17.10 vs 16.96 (−0.8%);
hip control #1 vs #2 14.76 vs 14.06 (−4.7%, corrected per the
disclosure above); cache-aside vs the mean of the two warm vk runs
12.38 vs 17.03 (−27.3%), TTFT 12.45 s vs 8.37/8.50 s.

### Reference values (same two cells, prior sessions)

| Cell | s1 (08-18) | s2 (08-18) | s3 (08-19) |
|---|---|---|---|
| `gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072` | 16.00 tok/s · TTFT 8.63 s | 16.25 · 8.64 | 14.53 · 9.94 |
| `gguf-hip-udq4kxl-auto-mtp-c1-ctx131072` (explicit d1) | — (not run; the 08-16 canonical hip cell is implicit d3: 13.00 · 5.47) | — | 13.86 · 5.43 |

Session-4 runs against those references: vulkan 17.10/16.96/12.38 (runs
1/3/5) vs s1/s2/s3 = 16.00/16.25/14.53; hip 14.76/14.06 (runs 2/4) vs the
s3 d1 value 13.86 (TTFT 5.46 s in both session-4 hip runs vs 5.43 s in s3).
The host was not rebooted between s1 and session 4 (same boot since
2026-08-12, recorded in every session-4 receipt's `telemetry.env`).

### Cache-aside arm — orchestration note (runner-external)

The runner does not know about this arm; it was orchestrated outside it,
between runs 4 and 5, exactly as follows: (1) the cache stats were recorded
(7884 KiB / 867 files, matching run 3's after-teardown reading); (2) the
directory was moved aside (`mv ~/.cache/mesa_shader_cache
~/.cache/mesa_shader_cache.aside-20260819T064054Z`) — no
`MESA_SHADER_CACHE_DIR` or `MESA_SHADER_CACHE_DISABLE` variables are set on
this host (checked before the run), so Mesa/RADV resolved the cache at the
default path, found nothing there (run 5's receipt records
`"not a directory"` at the before-boot reading) and recreated the directory
during the run; (3) after the run and teardown the fresh cache measured
2136 KiB / 100 files (newest mtime at the run time) and was preserved at
`~/.cache/mesa_shader_cache.fresh-20260819T064054Z`; (4) the original cache
was moved back and verified: du 7884 KiB / 867 files — an exact match to
the before-aside reading.

## Session 5 (2026-08-19 23:20–23:22 local): warm pair #1 of the daily series

Two runs, serial, one boot per run, GPU verified clean before each (no
`llama-server` process; GTT 223–231 MiB idle baseline). Same runner, prompt
set, pin, and telemetry harness as session 4; host state identical (boot
since 2026-08-12 09:42, power profile `balanced`, dpm `auto`). Receipts:
[run1-vk](session5-2026-08-19T2321local/run1-vk/gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json),
[run2-hip](session5-2026-08-19T2321local/run2-hip/gguf-hip-udq4kxl-auto-mtp-c1-ctx131072.json).
The mesa cache read 7884 KiB / 867 files before run 1 — unchanged since the
session-4 morning readings (zero new cache entries today before this session).
Host-log trigger-hunt forensics for the s2→s3 causal window (facts only):
[`trigger-hunt-2026-08-19.md`](trigger-hunt-2026-08-19.md).

### Per-run table

Same column conventions as the session-4 table (c1 single stream; stream
tok/s = 1000/tpot_ms at the corpus 2dp convention; aggregate =
completion_tokens / wall_s).

| Run | backend | stream tok/s | TTFT (s) | aggregate tok/s | anchor | boot wall (s) | load sclk/mclk · power · temp | post-bench sclk/mclk · power · temp | mesa cache before boot → after teardown |
|---|---|---|---|---|---|---|---|---|---|
| run1 (15:20:34Z) | vulkan | 16.25 | 8.49 | 10.58 | ok | 6 | 1424/1000 · 15.07 · 47.0 | 1569/1000 · 33.03 · 56.0 | 7884 KiB / 867 files → 7884 KiB / 867 files (unchanged, newest mtime still session-4 run 1's 06:32:54Z) |
| run2 (15:21:45Z) | hip | 13.55 | 5.63 | 10.47 | ok | 6 | 1186/1000 · 16.03 · 51.0 | 1882/1000 · 53.03 · 59.0 | not captured (vulkan-only field) |

Load memory: run1 VRAM 29460 MiB / GTT 1221 MiB (vulkan split); run2 VRAM
1560 MiB / GTT 28062 MiB (hip split). Run 1's stream finished at 256 tokens
with `finish_reason=stop`; run 2's hit the 256-token cap
(`finish_reason=length`). Cell-run anchors are now 17/17 across
s1/s2/s3/s4/s5.

### Reference values (same two cells, prior sessions)

| Cell | s1 (08-18) | s2 (08-18) | s3 (08-19) | s4 warm runs (08-19) | s5 (this, 08-19 evening) |
|---|---|---|---|---|---|
| `gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072` | 16.00 · TTFT 8.63 | 16.25 · 8.64 | 14.53 · 9.94 | 17.10 · 8.37 / 16.96 · 8.50 | 16.25 · 8.49 |
| `gguf-hip-udq4kxl-auto-mtp-c1-ctx131072` (explicit d1) | — | — | 13.86 · 5.43 | 14.76 · 5.46 / 14.06 · 5.46 | 13.55 · 5.63 |

Exact-basis deltas from the receipts: vulkan vs the two s4 warm runs
−4.98% / −4.22% (vs their mean −4.60%), vs s1/s2/s3 +1.51% / +0.00% /
+11.81%; hip vs the two s4 runs −8.17% / −3.66% (vs their mean −5.97%), vs
the s3 d1 value −2.26%. Same-session pairing (both this session, warm cache):
vulkan − hip = +2.70 tok/s = +19.90% of hip; aggregate basis hip 10.47 vs
vulkan 10.58 (gap +0.11, +1.07% of hip).

## Session 6 (2026-08-20 07:12–07:13 local): warm pair #2 of the daily series — first after an idle night

Two runs, serial, one boot per run, GPU verified clean before each (no
`llama-server` process; GTT 224–232 MiB idle baseline). Same runner, prompt
set, pin, and telemetry harness as sessions 4/5; host state identical (boot
since 2026-08-12 09:42, power profile `balanced`, dpm `auto`). Receipts:
[run1-vk](session6-2026-08-20T0712local/run1-vk/gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072.json),
[run2-hip](session6-2026-08-20T0712local/run2-hip/gguf-hip-udq4kxl-auto-mtp-c1-ctx131072.json).
Before run 1 — after the idle night following session 5 (session-5 last
receipt 15:21:45Z, this session's run 1 starts 23:12:02Z, same boot
throughout) — the mesa cache read 7884 KiB / 867 files with the newest mtime
still session-4 run 1's 06:32:54Z: zero new cache files and zero size growth
across the night. After both runs the cache measured the same 7884 KiB /
867 files (0 files with an mtime after session 5's runs).

### Per-run table

Same column conventions as the session-4/5 tables (c1 single stream; stream
tok/s = 1000/tpot_ms at the corpus 2dp convention; aggregate =
completion_tokens / wall_s).

| Run | backend | stream tok/s | TTFT (s) | aggregate tok/s | anchor | boot wall (s) | load sclk/mclk · power · temp | post-bench sclk/mclk · power · temp | mesa cache before boot → after teardown |
|---|---|---|---|---|---|---|---|---|---|
| run1 (23:12:02Z) | vulkan | 16.41 | 8.54 | 10.63 | ok | 6 | 1353/1000 · 15.10 · 46.0 | 1544/1000 · 33.03 · 56.0 | 7884 KiB / 867 files → 7884 KiB / 867 files (unchanged, newest mtime still session-4 run 1's 06:32:54Z) |
| run2 (23:13:01Z) | hip | 14.15 | 5.49 | 10.89 | ok | 6 | 1397/1000 · 16.09 · 51.0 | 1932/1000 · 54.03 · 58.0 | not captured (vulkan-only field) |

Load memory: run1 VRAM 29454 MiB / GTT 1226 MiB (vulkan split); run2 VRAM
1556 MiB / GTT 28064 MiB (hip split). Both streams hit the 256-token cap
(`finish_reason=length`). Cell-run anchors are now 19/19 across
s1/s2/s3/s4/s5/s6.

### Reference values (same two cells, prior sessions)

| Cell | s1 (08-18) | s2 (08-18) | s3 (08-19) | s4 warm runs (08-19) | s5 (08-19 evening) | s6 (this, 08-20 morning) |
|---|---|---|---|---|---|---|
| `gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072` | 16.00 · TTFT 8.63 | 16.25 · 8.64 | 14.53 · 9.94 | 17.10 · 8.37 / 16.96 · 8.50 | 16.25 · 8.49 | 16.41 · 8.54 |
| `gguf-hip-udq4kxl-auto-mtp-c1-ctx131072` (explicit d1) | — | — | 13.86 · 5.43 | 14.76 · 5.46 / 14.06 · 5.46 | 13.55 · 5.63 | 14.15 · 5.49 |

Exact-basis deltas from the receipts: vulkan vs the two s4 warm runs
−4.04% / −3.27% (vs their mean −3.65%), vs s1/s2/s3/s5 +2.52% / +0.99% /
+12.92% / +0.99%; hip vs the two s4 runs −4.08% / +0.63% (vs their mean
−1.78%), vs the s3 d1 value +2.08%, vs s5 +4.45%. Same-session pairing
(both this session, warm cache): vulkan − hip = +2.25 tok/s = +15.93% of
hip; aggregate basis hip 10.89 vs vulkan 10.63 (gap −0.26, −2.39% of hip).
Warm-pair series so far (exact-basis, % of hip): s4 +15.88% / +20.61%,
s5 +19.90%, s6 +15.93%.

## dflash floor series (pre-registered 2026-08-22)

Closes the vLLM dflash-c1 floor-crossing day-dependence (verdict addendum
2026-08-22). One installment per UTC day, one command (3 boots ≈ 25 min,
host must be idle):

    ARMS="7" bash scripts/probe-vllm-dflash2-nmax-sweep.sh

Receipts land in `dflash-nmax-sweep-<date>/` (same driver/date convention
as the 2026-08-22 sweep — `base.json`, `mtp.json`, `dflash-7.json`,
`nmax-sweep.json`); commit them receipts-only. One installment per UTC
day: a same-day rerun OVERWRITES that day's receipts — run it once,
commit it once (the ruling counts committed installments only). Ruling criteria are
pre-registered in the README roadmap decision entry (≥5 sessions on ≥5
distinct UTC days; dflash-7 median ≥ 10.0 in ≥5-of-5 with clean anchors
upgrades the "at/near the floor" wording to "stably at/above the floor";
any anchor failure or ≥3 missed days voids the series; the mapping does
not change under any outcome). The ruling integrates as a dated verdict
addendum, never a metric rewrite.
