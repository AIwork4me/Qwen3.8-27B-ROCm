# Upstream issue draft — llama.cpp (HIP) greedy-decoding degradation on gfx1151

**Status: draft, not yet filed.** Filing is an owner action (see the push
checklist); this document is written so the issue can be posted as-is, with
every claim traceable to a committed receipt in this repository.

---

**Proposed title:**

> [Bug] llama-server greedy decoding degenerates into `'////'` repetition
> after sustained multi-stream load (HIP backend, gfx1151)

## Summary

After a sustained multi-stream benchmark on a single `llama-server`
instance, all subsequent greedy (temperature 0) requests on that instance
degenerate into a `'////'` repetition loop. The server keeps serving (no
crash, no error in the log); a restart restores correct greedy decoding.
Reproduced on both KV modes (unified default boot and explicit `-np` split
boots). Not reproduced on the vLLM path serving the same model on the same
host (see Scope).

## Environment

| Component | Value |
|---|---|
| llama.cpp | `4df29be4f4c3673f428170fda944a5b19f743bb8` (server banner: `version: 0.1.0-dev (build 1, commit 4df29be4f)`) |
| Build | HIP backend, `-DGPU_TARGETS=gfx1151`, toolchain ROCm 7.14.0 (`~/rocm-7.14.0`) |
| Host | AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S (`gfx1151`), 94 GiB system RAM, 80 GiB GPU-visible GTT pool; kernel `6.17.0-1032-oem` |
| Model | `Qwen3.8-27B-UD-Q4_K_XL.gguf` (unsloth UD-Q4_K_XL, 16.69 GiB, arch `qwen35` — hybrid GDN linear attention + 16 full-attention layers + 1 MTP block) with `mmproj-F16.gguf` attached |
| Server flags (default boot) | `--ctx-size 131072 -ngl 99 --jinja` (+ `--mmproj mmproj-F16.gguf`) |
| Server flags (concurrency cells) | the above plus `-np 8` / `-np 16`; MTP variants add `--spec-type draft-mtp` |

Pins and build provenance: [`configs/validated-stack.json`](../../configs/validated-stack.json).

## Reproduction

The exact sequence, quoted verbatim from the measurement methodology
([`results/METHODOLOGY.md`](../results/METHODOLOGY.md) §6, "Measured pit at
the pin"):

> after a sustained multi-stream bench, greedy decoding on the SAME server
> instance degenerates into a `'////…'` repetition loop — the byte-identity
> anchor fails persistently (every subsequent greedy request, streaming or
> not). Reproduced deterministically on `-np 8` (fresh boot → 8-stream bench
> → first greedy anchor fails; with and without mmproj) and measured in cells
> `base-c4-ctx32768` (unified boot — NOT split-specific), `base-c8`,
> `base-c16`, `mtp-c8`, `mtp-c16` @131072.

Concretely:

1. Boot `llama-server` with the flags above (fresh process).
2. Run a sustained multi-stream load: N concurrent `/v1/chat/completions`
   streams (N = 4/8/16 measured), deterministic prompt set — 8 prompts,
   ~1.3–1.5K prompt tokens per stream — generation capped at 256 tokens,
   temperature 0.7 / top_p 0.95 (instrument:
   [`scripts/bench_client.py`](../../scripts/bench_client.py), prompt set
   [`scripts/prompt-sets/default.json`](../../scripts/prompt-sets/default.json)).
3. After the bench completes, issue a single greedy request:
   `"Reply with exactly: OK"` with `temperature: 0`, `max_tokens: 256`.
4. Observed: the completion is a run of `/` characters instead of `OK`, on
   every subsequent greedy request, for the remainder of the server process's
   lifetime. Streaming and non-streaming behave the same.

**Slot semantics at this commit** (source-verified and confirmed by the boot
line `srv load_model: initializing, n_slots = …, n_ctx_slot = …,
kv_unified = '…'` recorded in every cell receipt; details in METHODOLOGY §6):
the default boot (no `-np`) resolves auto `n_parallel = 4` and forces
`kv_unified = true` — 4 slots each seeing the full `--ctx-size` window over
one shared KV pool. An explicit `-np N` keeps `kv_unified = false` — split
mode, each slot's window = `--ctx-size`/N. **The pit reproduces in both
modes**, so it is not specific to split KV.

## Observed (committed evidence)

All five degraded cells record `anchor: {ok: false, content_tail:
"////////////////"}` and `degraded: true` — the tail is the last 200
characters of the anchor completion as captured by the runner, so the entire
completion was 16 `/` characters. Throughput numbers are recorded but
secondary (correctness is untrustworthy):

| Cell | Boot (`n_slots`/`n_ctx_slot`/`kv_unified`) | Bench streams | Anchor | Receipt |
|---|---|---|---|---|
| `gguf-udq4kxl-auto-base-c4-ctx32768` | unified: 4 / 32768 / `'true'` | 4-of-4 hit the 256-token cap (`finish_reason=length`) | FAILED | [`../results/matrix-714/cells/gguf-udq4kxl-auto-base-c4-ctx32768.json`](../results/matrix-714/cells/gguf-udq4kxl-auto-base-c4-ctx32768.json) |
| `gguf-udq4kxl-auto-base-c8-ctx131072` | split: 8 / 16384 / `'false'` | 8-of-8 capped | FAILED | [`../results/matrix-714/cells/gguf-udq4kxl-auto-base-c8-ctx131072.json`](../results/matrix-714/cells/gguf-udq4kxl-auto-base-c8-ctx131072.json) |
| `gguf-udq4kxl-auto-base-c16-ctx131072` | split: 16 / 8192 / `'false'` | 16-of-16 capped | FAILED | [`../results/matrix-714/cells/gguf-udq4kxl-auto-base-c16-ctx131072.json`](../results/matrix-714/cells/gguf-udq4kxl-auto-base-c16-ctx131072.json) |
| `gguf-udq4kxl-auto-mtp-c8-ctx131072` | split + draft-mtp: 8 / 16384 / `'false'` | 7-of-8 capped (one stream stopped at 2 tokens, `finish_reason=stop`) | FAILED | [`../results/matrix-714/cells/gguf-udq4kxl-auto-mtp-c8-ctx131072.json`](../results/matrix-714/cells/gguf-udq4kxl-auto-mtp-c8-ctx131072.json) |
| `gguf-udq4kxl-auto-mtp-c16-ctx131072` | split + draft-mtp: 16 / 8192 / `'false'` | 16-of-16 capped | FAILED | [`../results/matrix-714/cells/gguf-udq4kxl-auto-mtp-c16-ctx131072.json`](../results/matrix-714/cells/gguf-udq4kxl-auto-mtp-c16-ctx131072.json) |

Clean cells on the same build/host same day (for contrast): every `c1` cell
at ctx 32768/131072/262144, `-np 4` @131072, and the unified c4 @262144 —
all anchors `OK`, and all of their benches had early-stopping streams.
Full tables: [`../results/benchmark.md`](../results/benchmark.md).

## Scope

- **Both KV modes affected** (unified default boot and `-np` split boots;
  see the table).
- **Server-lifetime persistence**: once degraded, every subsequent greedy
  request on that process fails the anchor; a fresh process is clean until
  the next sustained multistream load.
- **Correlation, stated as correlation**: the degraded cells' benches were
  all-capped (every stream hit the 256-token generation cap) in 4 of 5
  cells, 7-of-8 in the fifth, while every clean cell's bench had
  early-stopping streams. We make no claim about the mechanism.
- **Not reproduced on vLLM** serving the same model on the same host
  (different backend, so not an equivalence claim): all 8 vLLM cells'
  greedy anchors returned `OK`, including anchors run immediately after
  16-stream benches (METHODOLOGY §7).
- **Not investigated**: CPU/CUDA backends, other GPUs, other quants, other
  architectures — out of this session's scope.

## Environment artifacts available on request

Server boot logs and per-cell logs are retained by the reporter; the
committed evidence set (cell JSONs with verbatim boot lines, stream records,
anchor tails; methodology; validation receipts for the build) is in this
repository: [`../results/matrix-714/cells/`](../results/matrix-714/cells/),
[`../results/METHODOLOGY.md`](../results/METHODOLOGY.md),
[`../results/rocm-7.14/gguf-validation.md`](../results/rocm-7.14/gguf-validation.md).
Project-side tracking: [`../troubleshooting.md`](../troubleshooting.md)
(greedy-degradation section).
