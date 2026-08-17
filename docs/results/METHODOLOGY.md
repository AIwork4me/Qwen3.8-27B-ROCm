# Benchmark methodology — Qwen3.8-27B on gfx1151 (ROCm 7.14)

Pre-declared before any matrix measurement (2026-08-17). This file is the
single source of truth for how every cell of
`docs/results/matrix-714/matrix.json` is measured, judged, and demoted.
Verdict rules below are frozen BEFORE the first cell runs; if a rule must
change after measurements exist, the change is recorded here with a dated
erratum, never silently.

Pins and host (from `configs/validated-stack.json`):

| Component | Pin |
|---|---|
| Host | AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S, `gfx1151`, 94 GiB system RAM, **80 GiB GPU-visible GTT pool** (`rocminfo`, coarse-grained GLOBAL segment) |
| ROCm | 7.14.0 (`/home/amd/rocm-7.14.0`, SHA-verified installer) |
| vLLM | `4d2a68d64d9e05921ed5c4099146e768a92d71d5` (source build, editable, TRITON_ATTN) |
| llama.cpp | `4df29be4f4c3673f428170fda944a5b19f743bb8` (HIP build `build-714`) |
| PyTorch | `2.10.0+rocm7.13.0a20260513` (TheRock gfx1151 index) |
| Model | `Qwen/Qwen3.8-27B` — 64 layers, `full_attention_interval = 4` → **16 full-attention layers** (48 GDN linear-attention layers, constant state), 4 KV heads, `head_dim` 256, `max_position_embeddings` 262144 |

Validated context defaults that anchor the matrix: **gguf 131072**
(`CTX_SIZE` default; 262144 boots with a caution-grade GTT finding — see
Memory), **vllm 262144** (`--max-model-len` in both serve confs; boot + KV OK
per `docs/results/rocm-7.14/vllm-validation.md`, with the encoder-profiling
skip flag documented there).

## 1. Study definitions

Cell id grammar (shared verbatim by the matrix generator, the cell runners,
and `schemas/benchmark-verdicts.schema.json`):

```
{path}-{weight}-{kv}-{mtp}-c{N}-ctx{K}
path   ∈ {gguf, vllm}
weight ∈ {udq4kxl, bf16}        # path-bound, see §7
kv     =  auto                  # both validated paths serve KV at model dtype (bf16);
                                # fp8/q8_0 KV tiers are a declared non-goal this session
mtp    ∈ {base, mtp}
N      ∈ {1, 4, 8, 16}          # concurrency
K      ∈ {32768, 131072, 262144}  # vllm: {131072, 262144}; 32768 not offered (dropped, §7)
```

- **S1 — single-stream interactive (N=1).** One user, one chat completion,
  streaming. The judge is perceived latency: TTFT and per-stream TPOT. This
  is the quickstart's presentation; the 10 tok/s floor (§3) applies fully.
- **S2 — concurrency journeys.** N independent chat completions issued
  client-side in parallel (one thread per stream, same prompt set):
  - c=4 — light multi-user (small team / agent fan-out),
  - c=8 — sustained multi-tenant chat,
  - c=16 — batch/throughput presentation ("overnight jobs", not interactive).
  The journey framing matters: a configuration may be judged per tier — e.g.
  `recommended` at c=1 for interactive use, `caution` at c=16 with the
  aggregate reported honestly next to per-stream TPOT (§3 honesty clause).
- **S3 — context capacity.** Per configuration: `max_usable_context` via a
  boot ladder over K (32768 → 131072 → 262144; each rung records boot
  OK/abort + VRAM/GTT), then a **functional deep-prompt retrieval smoke** at
  the highest rung that boots: synthetic haystack (repeated filler
  paragraphs), a planted unique needle sentence — `The validation codename
  is STRIX-HALO-7741.` — at 80% depth, prompt asks for the codename,
  temperature 0, judged **pass/fail by exact substring `STRIX-HALO-7741`
  appearing in the output**. Purpose: guard against "boots but attention
  degraded" false positives that raw throughput cannot catch. Prompt sizes
  ~30K / ~120K / ~240K tokens for the 32768 / 131072 / 262144 rungs.

**Measured (Task 4, 2026-08-17 — receipts
`docs/results/matrix-714/long-context-smoke.json`, tool
`scripts/long-context-smoke.py`, GGUF path, default unified boot):**
recall is **non-monotonic in depth** — 30K tier PASS (29,614 prompt tokens,
TTFT 137 s), **120K tier FAIL** (120,305 tokens, TTFT 1,012 s; confident
wrong answer "No validation codename is mentioned in the documents.",
finish_reason=stop), 247K tier PASS (247,232 tokens, TTFT 3,457 s). All
tiers booted (GTT 20,406 / 26,546 / 34,736 MiB — matching the §4 ladder)
and answered cleanly; the miss is a retrieval failure, not a boot or
transport failure. Ruling for Task 5's context-capacity table: deep-context
retrieval on the GGUF path at the validated defaults is **unreliable, not
depth-capped** — max_usable_context for functional retrieval is not
established above ~30K by this smoke alone (one needle, one depth, one
seed); the honest presentation is the per-tier receipts + this caveat, and
a caution-grade verdict for deep-prompt interactive use.

Every cell additionally runs the **arithmetic anchor** (greedy, temperature
0, `expect_exact` byte check) so greedy decoding is byte-identical across
paths and configs — a drift there invalidates cross-path comparisons.

## 2. Metrics (per cell, recorded in `cells/<id>.json`)

| Metric | Definition |
|---|---|
| TTFT | Time from request sent to first content-bearing SSE delta (ms) |
| Per-stream TPOT | `(last_delta − first_delta) / (completion_tokens − 1)` (ms/token); also expressed as its inverse tok/s |
| Aggregate tok/s | Total completion tokens across streams / wall time |
| VRAM / GTT | `rocm-smi` MiB, sampled at **load** (server ready, no requests) and **steady** (mid-generation); VRAM and GTT recorded separately, never merged (§4) |
| Failures | Per-stream `ok=false` events, HTTP errors, server aborts, hangs (deadline: 2× the slowest prior cell) — a failure never silently drops the cell; it demotes it (§3) |

Client contract (Task 2's `scripts/bench_client.py`): OpenAI-compatible
`/v1/chat/completions` with `stream: true`, one thread per stream, SSE parse
that buffers on `\n\n` and never assumes one event per chunk (the muse-rocm
framing lesson). Prompt set is deterministic and committed
(`scripts/prompt-sets/default.json`: 8 varied prompts, ~1500–2500 tokens
each, generation capped at 256 tokens). Throughput runs sample at
temperature 0.7 / top_p 0.95; the anchor is greedy (temperature 0).

**Erratum (2026-08-17, recorded at first live-cell execution, Task 3):**
the Qwen3.8 chat template spends the ENTIRE generation budget in
`reasoning_content` before any visible content — the first live cell
measured 256/256 completion tokens as reasoning (`finish_reason=length`,
zero content deltas), leaving the frozen TTFT/TPOT definitions undefined,
and the greedy anchor cannot fit its think phase inside the anchor cap.
Instrument correction (metric definitions and verdict rules unchanged):
cells send `chat_template_kwargs {"enable_thinking": false}` per request
(bench client `--no-thinking`; honored by llama.cpp `--jinja` and by vLLM),
so every cell measures the visible-answer stream both paths share.
Thinking-mode latency remains a legitimate study — declared a non-goal for
this session rather than silently mixed into the cells.

**vLLM instrument probe (2026-08-17, Task 4, on-host against the validated
conf boot):** the pin accepts `chat_template_kwargs` — verified live, three
streaming probes on :8000 (`serve-args.conf` as committed). (a) Thinking ON
(no kwarg): the conf's `--reasoning-parser qwen3` splits the stream into
`delta.reasoning` first (field name at this pin is `reasoning`, NOT the
llama.cpp-style `reasoning_content`) with `delta.content` deferred until the
think phase completes — measured 10.5 s and 21.1 s to first content on two
trivial 65-token prompts, i.e. TTFT-to-content is dominated by thinking,
and a longer think consumes the whole 256-token budget before any content
(the exact GGUF erratum failure, now on the packaging level too).
(b) Thinking OFF (`enable_thinking: false`): accepted, `reasoning_tokens=0`,
first content delta at 0.5 s. (c) Greedy anchor with thinking off: content
delta `"OK"` as the very first delta (2 completion tokens,
`finish_reason=stop`). Ruling: **vLLM cells run the same `--no-thinking`
instrument mode as the GGUF cells** — cross-path comparability holds with no
mode divergence; the mode is recorded per cell in the cell JSON
(`instrument_mode`), and the bench client's TTFT clock (first
content-bearing delta) is correct in both shapes because `reasoning` deltas
are neither content nor `reasoning_content`.

## 3. Verdict rules — pre-declared, verbatim

The rule-bearing Global Constraints of
`docs/superpowers/plans/2026-08-17-benchmark-matrix.md`, quoted verbatim
(frozen 2026-08-17, before any measurement):

> - Verdict vocabulary: `recommended | caution | avoid`, each with `reason`,
>   optional `conditions`, `workaround`, `upstream`. Enforced by
>   `schemas/benchmark-verdicts.schema.json`; a cell without a verdict fails
>   tests.
> - Demotion rules (pre-declared in METHODOLOGY.md BEFORE any measurement):
>   per-stream TPOT < 10 tok/s (i.e. > 100 ms/token) when the configuration
>   is presented for interactive use → not `recommended`; aggregate
>   throughput that regresses vs lower concurrency → `avoid` candidate; any
>   abort/OOM/hang → `avoid`; single-stream UX destroyed by concurrency gains
>   → reported as the pit, never a headline.
> - Units convention (fixes the parked 8.2-vs-8.0 ruling): ALL committed
>   numbers are binary (GiB/MiB, /1024); MiB/1000 never appears. KV formula
>   from spike quant-kv.md: `KV_bytes = tokens × 2 × 16 full-attn layers × 4
>   kv-heads × 256 head_dim × bytes/elem` (= 64 KiB/token bf16, 32 KiB fp8,
>   34 KiB q8_0).
> - Memory methodology: record VRAM and GTT separately (rocm-smi) at load and
>   steady state; on this APU weights+KV live in GTT via the 80 GiB pool —
>   placement vs spill distinguished per upstream llama.cpp #26432 note.
> - Prompt set: deterministic, committed under `scripts/prompt-sets/` (8
>   varied prompts, ~1500-2500 tokens each; generation 256 tokens; one
>   arithmetic anchor for greedy byte-identity across paths).
> - Client contract: `scripts/bench_client.py --base-url URL --concurrency N
>   --prompts FILE --max-tokens 256 [--label X]` emits one JSON: per-stream
>   {ttft_ms, tpot_ms, tokens}, aggregate {tok_per_s, wall_s}, failures.
>   SSE-framing-safe (muse-rocm lesson: never assume one event per chunk).
> - Servers: GGUF `scripts/gguf-quickstart.sh` (port 8080; GGUF_FILE/CTX_SIZE/
>   WITH_MTP env; per-stream ctx for concurrency cells via llama.cpp `-np N`
>   semantics — discover and RECORD exact slot/ctx behavior at the pin in
>   METHODOLOGY); vLLM `scripts/03-serve-vllm.sh [--mtp]` (port 8000; flags
>   from confs; NO conf edits — per-cell overrides via documented env/args
>   only, confs stay the validated defaults).
> - Raw cells: `docs/results/matrix-714/cells/*.json` (committed; gitignore
>   pattern `docs/results/*.json` must be adjusted to not exclude the cells
>   dir — resolve deliberately); one manifest `docs/results/matrix-714/
>   matrix.json` mapping every declared cell → `measured | planned(reason) |
>   dropped(reason)`.
> - CI: CPU-safe; verdicts/matrix/README-block freshness all testable
>   without GPU; quickstart assertion parses `scripts/gguf-quickstart.sh` +
>   serve confs and asserts referenced configs are `recommended` in verdicts
>   JSON.

**Auto-verdict ladder** (mechanically applied by Task 5's generator, in
order; the first matching rung wins):

1. Any abort / OOM / hang / boot failure → **`avoid`**.
2. Per-stream TPOT < 10 tok/s at a tier the configuration is presented for
   interactively (S1 always; S2 tiers per the journey framing) → **`caution`
   or `avoid`** (severity by distance below the floor: 8–10 tok/s → caution
   with conditions; < 8 tok/s → avoid).
3. Aggregate tok/s regresses vs a lower-concurrency cell of the same config
   family → **`avoid` candidate** (confirm against the raw cell before
   demotion).
4. Otherwise → **`recommended`** (with `conditions` whenever the win is
   tier-specific).

**Honesty clause (aggregate-vs-UX):** aggregate throughput that destroys
single-stream UX is reported as the pit, never a headline — a c=16 cell is
never showcased for tok/s while its per-stream TPOT is below the interactive
floor without the floor being the first sentence of the reason. The muse-rocm
lesson (`-np 16` pathological resource behavior, 5h16m class) is encoded
structurally: hangs are failures, not slow cells.

**Final authority:** the ladder proposes; the human/controller review
disposes — every generated verdict is reviewed for honesty (especially
`avoid`/`caution`: `reason` + `workaround` + `conditions` filled), and the
review is recorded in the verdicts JSON `reviewed_by` field
(`controller-<date>`). Auto-verdicts are never shipped unreviewed.

## 4. Memory methodology

- **VRAM vs GTT are recorded separately** (`rocm-smi`, MiB), at load and at
  steady state. On this APU the model weights and KV cache live in **GTT**
  (shared system memory) via the 80 GiB GPU-visible pool; VRAM at these
  boots is the small compute/desktop residue (~1131 MiB desktop baseline in
  the GGUF receipts). A number quoted as "memory" without the VRAM/GTT split
  is a defective cell record.
- **Placement vs spill:** resident-in-GTT is the *normal* placement on this
  host, not a defect. The defect class is a **silent spill beyond fast
  memory** — upstream llama.cpp #26432 (open): "Silent GTT fallback when
  context + MTP exceeds VRAM — no error at load, massive throughput
  collapse". A cell whose GTT grows past the pool's fast-memory envelope
  while throughput collapses (with no load-time error) is recorded as a
  #26432-class spill, `caution`/`avoid` with `upstream` filled — never as
  "slow hardware".
- **KV closed form** (from `docs/results/spike/quant-kv.md`; only the 16
  full-attention layers grow KV — the 48 GDN layers hold small constant
  state; MTP drafting adds one dense-attn block ≈ 4 KiB/token bf16,
  negligible-to-minor):

  ```
  KV_bytes = tokens × 2 (K+V) × 16 layers × 4 kv-heads × 256 head_dim × bytes/elem
           = tokens × 32,768 elems × bytes/elem
  ```

  | KV dtype | B/elem | B/token | @ 32768 | @ 131072 | @ 262144 |
  |---|---|---|---|---|---|
  | bf16/f16 (default, both paths) | 2 | 65,536 (**64 KiB/token**) | 2.00 GiB | 8.00 GiB | **16.00 GiB** |
  | fp8 e4m3 (vLLM lever; non-goal this session) | 1 | 32,768 (32 KiB/token) | 1.00 GiB | 4.00 GiB | **8.00 GiB** |
  | q8_0 (llama.cpp lever; non-goal this session) | 1.0625 | 34,816 (34 KiB/token) | 1.06 GiB | 4.25 GiB | **8.50 GiB** |

  Check: 262,144 × 32,768 = 2^33 elems; × 2 B = 16.00 GiB exactly.
- **GGUF measured increments corroborate the closed form** (UD-Q4_K_XL,
  mmproj attached, `-ngl 99`, HIP build at the pin; GTT MiB post-boot from
  `rocm-smi`): ctx 131072 → GTT 26,550 MiB; ctx 262144 → GTT 34,740 MiB;
  increment **8,190 MiB = 8.0 GiB binary** for +131,072 tokens = **64
  KiB/token bf16 KV**, exactly the closed form. The 262144 GGUF boot is
  therefore a *capacity-OK / caution-grade* finding (33.9 GiB total GTT =
  weights 16.69 GiB + KV 8.0 GiB + activations/buffers), not a failure.
- **vLLM memory accounting:** `--gpu-memory-utilization 0.92` of the 80 GiB
  pool caps the engine's budget (weights 51.7 GiB bf16 + KV within the
  remainder); the boot log's KV-cache block line is recorded per cell. The
  encoder-peak caveat under `--skip-mm-profiling` (no measurement/reservation
  of ViT activation peak — operator budgets image traffic) carries over
  verbatim from `configs/serve-args.conf` and
  `docs/results/rocm-7.14/vllm-validation.md`.

## 5. Units — binary only

All committed numbers are binary: KiB/MiB/GiB, divide by 1024. **MiB/1000
never appears** — a "GiB" computed by /1000 is a defect and fails review.

**Recorded ruling (the parked 8.2-vs-8.0 slip, resolved 2026-08-17):** an
earlier draft divided by 1000 and parked the GGUF ctx-262144 KV increment as
"≈ 8.2 GiB". The measured increment is 34,740 − 26,550 = 8,190 MiB, which is
**8.0 GiB binary** (8,190/1024 = 7.998) — and 8.0 GiB is what the closed
form predicts for 131,072 tokens of bf16 KV (64 KiB/token). The correct
figure everywhere is **8.0 GiB**; the total at 262144 is **33.9 GiB**
(34,740 MiB). The pre-ruling "≈ 8.2 GiB" string still visible in README.md's
serving-paths table is scheduled for correction by Task 5's README
regeneration and must not be copied anywhere new.

## 6. llama.cpp slot semantics at the pin (`4df29be`)

The `-np`/`--ctx-size` interaction has two possible semantics and **at this
pin both exist**, selected by `kv_unified`. Source lines verified in the
built tree (`third_party/llama.cpp` @ `4df29be4`, the exact build-714
source):

- `common/arg.cpp:1401` — `params.n_parallel = -1` (**auto**) by default;
  the server flag is `-np/--parallel`, "number of server slots (default: %d,
  -1 = auto)" (`arg.cpp:2535`).
- `tools/server/server.cpp:151-155` — when `-np` is auto (default boot), the
  server resolves it to `n_parallel = 4` **and forces `kv_unified = true`**
  (trace: "n_parallel is set to auto, using n_parallel = 4 and kv_unified =
  true"). When `-np N` is passed **explicitly**, `kv_unified` keeps its
  struct default **false** (`common/common.h:563`) unless `-kvu` is given
  (`arg.cpp:1712-1718`).
- `src/llama-context.cpp:288-302` — `n_ctx` is padded to 256, then:
  - **unified (`kv_unified = true`): `n_ctx_seq = n_ctx`** — every slot's
    context window is the **full `--ctx-size`**, and the sequences share one
    KV pool (per-slot window K is an upper bound; the shared pool holds K
    tokens *total* across all sequences).
  - **split (`kv_unified = false`): `n_ctx_seq = n_ctx / n_seq_max`** —
    **`--ctx-size` is the TOTAL, divided across slots** (each slot's window
    = ctx/N, rounded down to a 256 multiple, with the warning "n_ctx is not
    divisible by n_seq_max - rounding down" when lossy).
- `src/llama-kv-cache.cpp:82` + tensor allocation (~:246) —
  `n_stream = unified ? 1 : n_seq_max`; the K/V tensors are 3-D
  `(n_embd_gqa, kv_size = n_ctx_seq, n_stream)`. **In both modes the total
  KV allocation equals `--ctx-size` tokens** — the mode changes the
  distribution (one shared full-K pool vs N dedicated ctx/N windows), not
  the total bytes. The §4 closed form therefore scales with the *total*
  `--ctx-size` in both modes.
- `tools/server/server-context.cpp:1199-1219,1255` — each slot's window is
  `n_ctx_slot = llama_n_ctx_seq(ctx)` (capped at `n_ctx_train`), logged at
  boot as `srv load_model: initializing, n_slots = %d, n_ctx_slot = %d,
  kv_unified = '%s'`.

Observed on this host (receipt `docs/results/rocm-7.14/gguf-validation.md`):
the default boot (`--ctx-size 131072`, no `-np`) logged
`n_slots = 4, n_ctx_slot = 131072, kv_unified = 'true'` — the auto default
gives **4 slots each seeing the full 131072 window over a shared 131072-token
KV pool**. Source-level expectations for the concurrency cells:

| Cell flags | Expected semantics (source-derived) |
|---|---|
| default boot (no `-np`) | 4 slots, unified, per-slot window = full `--ctx-size` |
| `-np 4` (explicit) | split: per-slot window = ctx/4, unless `-kvu` added |
| `-np 8` / `-np 16` | split: per-slot window = ctx/8 / ctx/16, unless `-kvu` added |

Runner consequence: to guarantee each of N streams a K-token window in split
mode, pass `--ctx-size N×K` (total KV then N×K tokens = N × the §4 KV
bytes); to keep one shared K-token pool with full-K windows, pass `-kvu`.

**Measured (Task 3, 2026-08-17 — the dated obligation fulfilled).** The GGUF
cell runner (`scripts/run-cell-gguf.sh`) records the actual boot line
(`srv load_model: initializing, n_slots = …, n_ctx_slot = …, kv_unified = '…'`)
into every cell JSON. Every source-derived row above is CONFIRMED at the pin:

| Boot flags (measured cell) | n_slots | n_ctx_slot | kv_unified | GTT @ load |
|---|---|---|---|---|
| default @32768 (base-c1-ctx32768) | 4 | 32768 | 'true' | 20,406 MiB |
| `-np 4` @131072 (base-c4-ctx131072) | 4 | 32768 | 'false' | 26,550 MiB |
| `-np 8` @131072 (base-c8-ctx131072) | 8 | 16384 | 'false' | 27,148 MiB |
| `-np 16` @131072 (base-c16-ctx131072) | 16 | 8192 | 'false' | 28,392 MiB |
| default @131072 (base-c1-ctx131072) | 4 | 131072 | 'true' | 26,548 MiB |
| default @262144 (base-c1-ctx262144) | 4 | 262144 | 'true' | 34,742 MiB |

Notes from the measured rows: (a) explicit `-np N` flips to split semantics
exactly as derived — per-slot window = `--ctx-size`/N, `kv_unified='false'`;
(b) the default boot is auto `n_parallel = 4`, unified, at every ctx tier;
(c) GTT corroborates the §4 closed form at every rung (131072→262144:
+8,194 MiB ≈ 8.0 GiB for +131,072 tokens = 64 KiB/token; 32768→131072:
+6,142 MiB ≈ 6.0 GiB for +98,304 tokens); (d) split mode carries a small
per-stream tensor overhead on top of the same total KV (c8 +~600 MiB,
c16 +~1.8 GiB vs the unified boot at the same `--ctx-size`).

**Measured pit at the pin (anchor degradation, 2026-08-17):** after a
sustained multi-stream bench, greedy decoding on the SAME server instance
degenerates into a `'////…'` repetition loop — the byte-identity anchor
fails persistently (every subsequent greedy request, streaming or not).
Reproduced deterministically on `-np 8` (fresh boot → 8-stream bench → first
greedy anchor fails; with and without mmproj) and measured in cells
`base-c4-ctx32768` (unified boot — NOT split-specific), `base-c8`,
`base-c16`, `mtp-c8`, `mtp-c16` @131072. Clean cells all passed the anchor
(`c1` everywhere, `-np 4` @131072, unified c4 @262144). Correlation noted
for upstream reporting: the degraded cells' benches were all-capped (every
stream hit the 256-token length cap) in 4 of the 5 degraded cells, and
7-of-8 in the fifth (`mtp-c8`: stream s1 stopped at 2 tokens,
`finish_reason=stop`), while clean c4 benches had early-stopping streams.
(Erratum, 2026-08-17, Task 3 review: an earlier draft of this note claimed
ALL streams capped in every degraded cell; the mtp-c8 cell JSON is the
source of truth.) These cells are recorded `measured(degraded)` with the
reason verbatim;
per §1 the anchor drift invalidates cross-path comparison for them, and
per §3 the ladder demotes (upstream: llama.cpp `4df29be4` HIP build on
gfx1151; exact mechanism unresolved at session close).

## 7. vLLM concurrency (client-parallel)

vLLM has no `-np` analog: concurrency is applied **client-side** (Task 2's
bench client opens N parallel SSE streams), and the engine multiplexes them
through continuous batching up to the scheduler's `max_num_seqs`. Cells do
NOT set `--max-num-seqs`: the serve confs (`configs/serve-args.conf`,
`serve-args-mtp.conf`) stay the validated defaults, and N ∈ {1,4,8,16} is far
below the scheduler cap in any case — at the pin, for this host class
(device_memory ≥ 70 GiB, non-A100), the default for the OpenAI server is
`max_num_seqs = 1024` and `max_num_batched_tokens = 8192`
(`vllm/engine/arg_utils.py:2592-2601`); the validated boot log's non-default
args contain no `max_num_seqs` entry, i.e. the default applied
(`docs/results/rocm-7.14/vllm-validation.md`).

Per-cell recording obligation: capture the engine args **verbatim from the
boot log** — the `api_utils.py` "non-default args" line and the `core.py`
"Initializing a V1 LLM engine … with config:" line — into the cell JSON, so
each verdict is auditable against the exact engine configuration that
produced it (attention backend, KV dtype, prefix caching, chunked prefill,
speculative config).

**Measured (Task 4, 2026-08-17 — the recording obligation fulfilled).** All
8 priority vLLM cells ran via `scripts/run-cell-vllm.sh` in BATCH MODE (one
boot per server config serving all four concurrency cells sequentially — 2
boots total instead of 8; wall: base batch ≈ 13 min, mtp batch ≈ 16 min):
`max_num_seqs` appears in NO boot's non-default args line → the pin default
(1024, §7 above) applied, exactly as declared; every cell JSON carries the
verbatim `non_default_args`, an `engine_init_excerpt`, and the KV-cache
lines. Boot receipts: base healthy in 171 s, load **GTT 75,040 MiB**
(weights 51.1 GiB + KV 19.57 GiB = 313,650 KV tokens = 1.20x the 262,144
max-len); mtp healthy in 226 s, **GTT 76,072 MiB** (MTP head +~1.0 GiB;
KV 18.59 GiB = 279,146 tokens = 1.06x). Note the engine's own concurrency
ceiling at max-len: a SINGLE 262,144-token request fits (1.06–1.20x), but
two full-depth streams cannot — deep-context concurrency is KV-budget-bound
long before `max_num_seqs` matters. All 8 greedy anchors returned `OK`
(including anchors run immediately after 16-stream benches) — the GGUF
greedy-degeneration pit of §6 does NOT reproduce on the vLLM path.

## 8. Matrix declaration (this session)

Declared by `scripts/gen-matrix.py` (deterministic: fixed iteration order,
`generated_at` is a date, no timestamps inside cells) into
`docs/results/matrix-714/matrix.json`; regenerate with
`python3 scripts/gen-matrix.py` — output is byte-stable.

- **Universe:** the §1 id grammar with the path-bound weight dimension
  applied by construction — `gguf↔udq4kxl` (UD-Q4_K_XL is a GGUF-only
  quant; the GGUF path is validated on it) and `vllm↔bf16` (the vLLM path
  serves the BF16 safetensors checkpoint). Cross pairs (`gguf-bf16`,
  `vllm-udq4kxl`) are invalid by construction and are never emitted.
- **Dropped (recorded with reason):** `vllm-*-*-ctx32768` — 32768 is not a
  supported conf tier for the vllm path (the validated conf serves
  `--max-model-len 262144`; no tier below it is offered).
- **Declared-priority subset (this session):** gguf `{base,mtp} ×
  {1,4,8,16} @131072` + `base × {32768,262144} × {1,4}`; vllm
  `{base,mtp} × {1,4,8,16} @262144`. Everything else valid is
  `planned(reason="time-boxed session; machinery complete")`.
- **Statuses:** `measured` (a `cells/<id>.json` exists; a consistency test
  enforces the pairing), `planned` (reason required), `dropped` (reason
  required).
- Raw cells live in `docs/results/matrix-714/cells/*.json` (committed; the
  `docs/results/*.json` gitignore pattern does not reach into the
  subdirectory, and an explicit negation documents the intent).

Cell counts emitted by the generator: gguf 24 (12 priority), vllm 16 (8
priority) + 8 dropped ctx-32768 = **48 declared cells, 20 priority**.
