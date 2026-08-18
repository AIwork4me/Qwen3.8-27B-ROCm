# Troubleshooting — Qwen3.8-27B on gfx1151 (ROCm 7.14)

Every pit below is a measured finding backed by a committed receipt — nothing
here is guessed. The format is the design-spec §4.4 standard: **Symptom →
Reproduction conditions → Root cause / diagnosis state → Workaround →
Upstream tracking**, so any pit is routable in under 30 seconds. Per-cell
verdicts (reason / conditions / workaround / upstream) live in
[`configs/benchmark-verdicts.json`](../configs/benchmark-verdicts.json); the
method behind every number in [`results/METHODOLOGY.md`](results/METHODOLOGY.md);
the full tables in [`results/benchmark.md`](results/benchmark.md).

## Pit index

| Pit | One-liner | Anchor |
|---|---|---|
| llama.cpp HIP greedy degradation | `'////'` tails after sustained multistream load; restart or use vLLM | [#greedy-degradation](#greedy-degradation) |
| MTP inverts at high concurrency | vLLM c16: −19.4% aggregate vs base; serve base when batching | [#mtp-concurrency](#mtp-concurrency) |
| vLLM encoder profiling OOM | 256 GiB demand at boot without `--skip-mm-profiling` | [#encoder-profiling](#encoder-profiling) |
| GGUF ctx 262144 GTT growth | +8.0 GiB KV over the 131072 boot; capacity-OK, default stays 131072 | [#gtt-growth](#gtt-growth) |
| vLLM KV ceiling at 262144 | 1.06–1.20x max-len: one full-depth request, not two | [#kv-ceiling](#kv-ceiling) |
| Reasoning field differs per path | llama.cpp `reasoning_content` vs vLLM `message.reasoning` | [#reasoning-field](#reasoning-field) |
| Deep-context retrieval unreliable | 120K tier confident miss; non-monotonic vs depth | [#deep-context-retrieval](#deep-context-retrieval) |
| Kernel floor (UMA) | kernels < 6.16.9 fail env-check on Strix Halo | [#uma-bug](#uma-bug) |
| vLLM amdsmi import | source builds need the pinned patch + `.pth` shim | [#amdsmi](#amdsmi) |
| Dirty llama.cpp checkout | rebuild refuses to discard your uncommitted changes | [#dirty-llama-cpp-checkout](#dirty-llama-cpp-checkout) |
| Cold `uv sync` loop-fail | 3 small PyPI packages retry forever while ~2 GiB of wheels succeed | [#uv-sync-loop-fail](#uv-sync-loop-fail) |

## llama.cpp HIP greedy degradation (`'////'` tails)
<a id="greedy-degradation"></a>

Measured 2026-08-17 ([METHODOLOGY.md §6](results/METHODOLOGY.md)). Five of the
20 measured cells are `avoid` because of this pit.

**Symptom.** After a sustained multi-stream bench on a *single* llama-server
instance, every subsequent greedy request (temperature 0, streaming or not)
degenerates into a `'////…'` repetition loop. The bench instrument's echo
anchor (prompt `Reply with exactly: OK`, judged by the literal `OK` substring,
[`scripts/prompt-sets/default.json`](../scripts/prompt-sets/default.json))
records `anchor_ok: false` with the committed `content_tail`
`"////////////////"` — 16 `/` characters; the runner records the last 200
characters of the completion, so the *entire* completion was slashes.

**Reproduction conditions.** The METHODOLOGY §6 sequence: fresh server boot →
N-stream throughput bench (deterministic 8-prompt set, ~1.3–1.5K prompt
tokens per stream, generation capped at 256 tokens, temperature 0.7 / top_p
0.95) → the first greedy anchor afterwards fails, and keeps failing for the
rest of the server's lifetime. Reproduced deterministically on `-np 8`, with
and without mmproj attached. It is NOT split-KV-specific: it hits the
explicit `-np` split boots at ctx 131072 (c8/c16) AND the unified default
boot at ctx 32768 (c4). Cell receipts:

| Cell | Boot mode | Per-stream med / aggregate | Receipt |
|---|---|---|---|
| `gguf-udq4kxl-auto-base-c4-ctx32768` | unified default (`kv_unified='true'`, n_ctx_slot 32768) | 5.8 / 15.7 tok/s | [`cells/…c4-ctx32768.json`](results/matrix-714/cells/gguf-udq4kxl-auto-base-c4-ctx32768.json) |
| `gguf-udq4kxl-auto-base-c8-ctx131072` | split (`-np 8`, n_ctx_slot 16384) | 3.6 / 18.4 tok/s | [`cells/…c8.json`](results/matrix-714/cells/gguf-udq4kxl-auto-base-c8-ctx131072.json) |
| `gguf-udq4kxl-auto-base-c16-ctx131072` | split (`-np 16`, n_ctx_slot 8192) | 3.2 / 27.5 tok/s | [`cells/…c16.json`](results/matrix-714/cells/gguf-udq4kxl-auto-base-c16-ctx131072.json) |
| `gguf-udq4kxl-auto-mtp-c8-ctx131072` | split + `--spec-type draft-mtp` | 2.1 / 10.7 tok/s | [`cells/…mtp-c8.json`](results/matrix-714/cells/gguf-udq4kxl-auto-mtp-c8-ctx131072.json) |
| `gguf-udq4kxl-auto-mtp-c16-ctx131072` | split + `--spec-type draft-mtp` | 1.4 / 16.3 tok/s | [`cells/…mtp-c16.json`](results/matrix-714/cells/gguf-udq4kxl-auto-mtp-c16-ctx131072.json) |

Slot semantics at the pin (METHODOLOGY §6, source-verified and confirmed by
every cell's boot line): the default boot resolves auto `n_parallel=4` and
forces `kv_unified=true` — 4 slots each seeing the full `--ctx-size` window
over one shared KV pool; an explicit `-np N` keeps `kv_unified=false` — each
slot's window is `--ctx-size`/N. The pit reproduces in both modes.

**Root cause / diagnosis state.** Exact mechanism unresolved at session close
(METHODOLOGY §6). The recorded correlation: the degraded cells' benches were
all-capped (every stream hit the 256-token length cap) in 4 of the 5 cells,
and 7-of-8 in the fifth (`mtp-c8`: stream s1 stopped at 2 tokens,
`finish_reason=stop`), while every clean cell (`c1` at all ctx tiers,
`-np 4` @131072, unified c4 @262144) had early-stopping streams. The
corrected erratum in METHODOLOGY §6 records that an earlier draft overstated
this correlation to "all streams, every cell" — the cell JSONs are the source
of truth.

**Workaround.** Restart llama-server — greedy decoding is restored on a fresh
boot. For multi-stream loads use the vLLM path: all 8 vLLM cells' greedy
anchors stayed `OK`, including anchors run immediately after 16-stream
benches (METHODOLOGY §7). Single-stream interactive use of the GGUF
quickstart is unaffected (all `c1` cells anchor-clean,
[`results/benchmark.md`](results/benchmark.md)).

**Upstream tracking.** llama.cpp HIP on gfx1151 (ROCm 7.14, toolchain per
[`configs/validated-stack.json`](../configs/validated-stack.json)): reproduced
at the pin `4df29be4` and **live at master HEAD `01818e495`** (2026-08-17) —
control receipts in [`results/upstream-controls/`](results/upstream-controls/README.md).
Candidate fix [PR #25863](https://github.com/ggml-org/llama.cpp/pull/25863)
(avoid direct ROCm_Host compute on HIP integrated GPUs, OPEN) removes it on
this host: patched 2/2 greedy-anchor PASS vs unpatched 3/3 FAIL on the idle
host. Tracked upstream in [#25992](https://github.com/ggml-org/llama.cpp/issues/25992)
(primary — same-host gfx1151 bisect to the HIP `prop.integrated` path; the
AMD maintainer invited testing of the fix) and [#23577](https://github.com/ggml-org/llama.cpp/issues/23577)
(`'////'`-family tracker); cross-linked there, **no new issue** (llama.cpp
closes duplicates without questions; its AI policy requires owner-written
posts). Evidence pack + owner-action brief:
[`upstream/llama-cpp-hip-greedy-degradation.md`](upstream/llama-cpp-hip-greedy-degradation.md).

## MTP speculative decoding inverts at high concurrency
<a id="mtp-concurrency"></a>

**Symptom.** With MTP enabled, throughput at 16 concurrent streams is *worse*
than the base configuration: vLLM `mtp-c16-ctx262144` measured 31.11 vs
38.58 tok/s aggregate (−19.4%) with per-stream min 1.85 tok/s — the only
rung-3 `avoid` cell of the matrix
([verdicts](../configs/benchmark-verdicts.json),
[`results/benchmark.md`](results/benchmark.md)).

**Reproduction conditions.** vLLM: `bash scripts/03-serve-vllm.sh --mtp`
(`configs/serve-args-mtp.conf`, `--speculative-config {"method":"mtp",…}`),
then bench at concurrency 16 — client-side parallel streams, engine
multiplexing (METHODOLOGY §7). GGUF: `WITH_MTP=1 bash scripts/gguf-quickstart.sh`
with `EXTRA_ARGS='-np 16'`. Note: the GGUF mtp-c8/c16 negative deltas
(−42% per-stream) are artifacts of the
[greedy-degradation](#greedy-degradation) pit, not MTP evidence — stated as
such in the verdicts.

**Root cause / diagnosis state.** The speculative win inverts at high
concurrency: at c16 the drafter's extra work outweighs acceptance under full
batching (rung-3 regression confirmed against the raw cell by controller
review; the muse-rocm DFlash lesson mirrored,
[`results/benchmark.md`](results/benchmark.md)). MTP remains beneficial
through c8 on the vLLM path (+33.0% / +27.3% per-stream at c4/c8; +21.4% /
+9.4% aggregate) and is the interactive win on the GGUF path (+28.2%
per-stream at c1: 13.0 vs 10.1 tok/s).

**Workaround.** Serve the base config when batching at 16 streams —
`bash scripts/03-serve-vllm.sh` (`configs/serve-args.conf`) is the best cell
measured (38.6 tok/s aggregate). Keep MTP for c ≤ 8 and for interactive
single-stream use (`WITH_MTP=1`).

**Upstream tracking.** None filed — this is recorded behavior of the
speculative path under saturation, not a claimed defect; the verdict cell
(`vllm-bf16-auto-mtp-c16-ctx262144`) carries the full reason and conditions.

## vLLM boot OOM: encoder profiling demands 256 GiB at max-model-len 262144
<a id="encoder-profiling"></a>

**Symptom.** vLLM boot dies before serving with:

```
torch.OutOfMemoryError: HIP out of memory. Tried to allocate 256.00 GiB.
GPU 0 has a total capacity of 80.00 GiB of which 25.38 GiB is free.
```

(verbatim in [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md) ## Boot, attempt 1).

**Reproduction conditions.** `vllm serve` with `--max-model-len 262144` and
NO `--skip-mm-profiling`, on this checkpoint
(`Qwen3_5ForConditionalGeneration` ships a vision tower, so vLLM profiles it
as multimodal by default). Hit on the very first boot attempt of the
validation run.

**Root cause / diagnosis state.** Boot-time multimodal encoder profiling
(`profile_run` → `embed_multimodal` → ViT SDPA): the profiling dummy batch's
item count scales with `max_model_len`
(`vllm/multimodal/encoder_budget.py:168-170`), so at 262144 the ViT profile
demands 256 GiB against an 80 GiB pool. The text-path KV cache was NOT the
failure — the conf's documented 262144 risk did not materialize on the text
side (receipt, attempt 2 boots healthy at 262144).

**Workaround.** `--skip-mm-profiling` — a first-class CLI flag at the pin
`4d2a68d` (`vllm/engine/arg_utils.py:1354` → `MultiModalConfig.skip_mm_profiling`).
It is committed in BOTH serve confs
([`configs/serve-args.conf`](../configs/serve-args.conf),
[`configs/serve-args-mtp.conf`](../configs/serve-args-mtp.conf)) and skips
only the MM encoder + encoder-cache profiling; text-path profiling and
serving are untouched. **Operator contract:** with profiling skipped, the
encoder's activation peak is neither measured nor reserved at boot — budget
image traffic yourself (headroom under `--gpu-memory-utilization`, image
size/count limits, or a lower `--max-model-len`) before enabling image
workloads beyond the validated single-small-image receipt case.

**Upstream tracking.** None needed — the upstream flag is the remedy; the
scaling behavior and the operator contract are recorded in the receipt's
## Boot and ## Vision sections.

## GGUF ctx 262144 grows total GTT by +8.0 GiB
<a id="gtt-growth"></a>

**Symptom.** Booting the GGUF quickstart with `CTX_SIZE=262144` lands at
total GTT 34,740 MiB (33.9 GiB: weights 16.69 GiB + KV 8.0 GiB +
activations/buffers) vs 26,550 MiB at the default 131072 — an increment of
8,190 MiB = **8.0 GiB binary**
([`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md) ## Context ladder,
METHODOLOGY §4/§5).

**Reproduction conditions.** `CTX_SIZE=262144 bash scripts/gguf-quickstart.sh`,
then read `rocm-smi` (the receipt carries a 2-second VRAM/GTT sampler log
during load; VRAM stays at the ~1131 MiB desktop baseline — on this APU the
weights+KV live in GTT via the 80 GiB pool).

**Root cause / diagnosis state.** Expected, not a leak: only the 16
full-attention layers grow KV, at 64 KiB/token bf16
(`2 × 16 layers × 4 KV heads × 256 head_dim × 2 B`) — so +131,072 tokens of
KV is exactly +8.0 GiB. The measured GTT ladder corroborates the closed form
at every rung (METHODOLOGY §4/§5: 32768 → 131072 → 262144 = 20,406 / 26,550 /
34,740 MiB; per-cell ladder in §6). Classified capacity-OK / caution-grade.

**Workaround.** None required on the validated host — 33.9 GiB fits the
80 GiB pool with headroom — but the validated default stays
[`CTX_SIZE=131072`](getting-started.md#context-tiers) (config value in
[`configs/validated-stack.json`](../configs/validated-stack.json)). On
32 GiB-class SKU envelopes, bf16 KV at 262K does NOT fit even beside Q4
weights — KV quant (fp8 on vLLM / `q8_0` on llama.cpp) becomes mandatory
there ([`results/spike/quant-kv.md`](results/spike/quant-kv.md)).

**Upstream tracking.** None — arithmetic, not a defect. Watch item for
spill-class behavior: llama.cpp #26432 (silent GTT fallback) per
METHODOLOGY §4.

## vLLM KV ceiling at 262144: one full-depth request, not two
<a id="kv-ceiling"></a>

**Symptom.** The vLLM boot log budgets KV for barely one max-length request:

```
GPU KV cache size: 313,650 tokens, Maximum concurrency for 262,144 tokens per request: 1.20x
```

(MTP conf: 279,146 tokens, 1.06x). Verbatim in
[`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md) ## Boot / ## MTP
and in every vLLM cell's engine excerpt.

**Reproduction conditions.** Boot either serve conf (both pin
`--max-model-len 262144`, `--gpu-memory-utilization 0.92`); read the
`kv_cache_utils.py` line quoted above.

**Root cause / diagnosis state.** Budget arithmetic on this host: 0.92 × the
80 GiB pool, minus BF16 weights (51.1 GiB), activations and CUDA-graph pools,
leaves KV 19.57 GiB (MTP: 18.59 — the drafter costs ~1.0 GiB). A single
262,144-token request fits (1.06–1.20x); two concurrent full-depth streams
do not. Deep-context concurrency is KV-budget-bound long before the
scheduler matters — `max_num_seqs` was never overridden and the pin default
(1024, METHODOLOGY §7) never comes into play at these depths.

**Workaround.** Treat full-depth (262K) context as single-tenant on this
host: one full-depth stream at a time, or cap concurrent request depth so
the sum fits the ~19.6 GiB KV budget (64 KiB/token bf16 — see the
[growth arithmetic](#gtt-growth)).

**Upstream tracking.** None — engine memory design, recorded as a
capacity fact (METHODOLOGY §7, `results/benchmark.md` ## Context capacity).

## The reasoning field has a different name on each path
<a id="reasoning-field"></a>

**Symptom.** A client reading the thinking channel works against one server
and silently gets nothing against the other: llama.cpp returns
`message.reasoning_content`; vLLM (at this pin) returns `message.reasoning`
and NO `reasoning_content` key.

**Reproduction conditions.** Send the same greedy request
(`"Reply with exactly: OK"`, temperature 0) to both servers. llama.cpp
message keys: `['content', 'reasoning_content', 'role']` with 103 chars of
reasoning ([`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md) ## Greedy smoke);
vLLM with `--reasoning-parser qwen3` splits into
`reasoning: 'We need to respond …'` / `content: '\n\nOK'`
([`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md) ## Reasoning parser).

**Root cause / diagnosis state.** Packaging, not generation: the pinned vLLM
commit serves the pre-`</think>` text as `message.reasoning` — the older
DeepSeek-style `reasoning_content` stays absent (`.get()` returns None),
verified on-host at the pin. Generation is identical with or without the
parser (57/27 tokens, same text — receipt). llama.cpp's split is native and
uses the `reasoning_content` spelling.

**Workaround.** Read `message.reasoning` on vLLM and
`message.reasoning_content` on llama.cpp — or ignore the channel and consume
`message.content`, which is identical on both paths. Streaming clients: on
vLLM the first delta carries `reasoning` and `content` deltas begin only
after the reasoning stream ends (receipt); on llama.cpp the split is
field-parallel. The validated benchmark cells sidestep this entirely via the
shared `--no-thinking` instrument mode (METHODOLOGY §2 erratum).

**Upstream tracking.** None filed — a pin-local naming difference, recorded
per receipt. Re-check the field name whenever the vLLM pin moves.

## Deep-context retrieval is not depth-reliable on the GGUF path
<a id="deep-context-retrieval"></a>

**Symptom.** At the 131072 tier, a needle planted at ~80% depth was answered
with a *confident miss* — "No validation codename is mentioned in the
documents." (`finish_reason=stop`) — while the 32768 and 262144 tiers
recalled it correctly.

**Reproduction conditions.** `scripts/long-context-smoke.py`: synthetic
haystack, unique needle `The validation codename is STRIX-HALO-7741.` at
~80% depth, temperature 0, judged by exact substring recall. Receipt:
[`results/matrix-714/long-context-smoke.json`](results/matrix-714/long-context-smoke.json)
(30K PASS / 120K FAIL / 247K PASS; all tiers booted and answered cleanly).

**Root cause / diagnosis state.** Recall is non-monotonic in depth — this is
a retrieval failure, not a boot/transport failure. One needle, one depth,
one seed: a reliable `max_usable_context` for deep-prompt retrieval is NOT
established above ~30K by this smoke (METHODOLOGY §1 ruling).

**Workaround.** Treat deep-context answers as unverified until re-tested for
your prompt shape; keep deep-prompt interactive use at caution grade. Booting
large ctx is fine (see [#gtt-growth](#gtt-growth) for the memory cost).

**Upstream tracking.** None — an honest limitation of the measured smoke,
recorded in the context-capacity tables
([`results/benchmark.md`](results/benchmark.md)).

## Kernel floor: UMA pool needs kernel ≥ 6.16.9 (Strix Halo)
<a id="uma-bug"></a>

**Symptom.** `bash scripts/00-check-env.sh` fails with
`project Strix Halo host floor is kernel >= 6.16.9 (docs/troubleshooting.md#uma-bug)`.
With `--profile community` the same condition is a WARNING instead (evidence
for a non-Strix-Halo platform is recorded in the submission's stack manifest,
not gated — docs/hardware-validation.md).

**Reproduction conditions.** Run the env check on a Ryzen AI MAX+ PRO 395 /
Radeon 8060S host whose kernel is older than 6.16.9.

**Root cause / diagnosis state.** Inherited finding from the predecessor
project (Muse-Glimmer-30B-ROCm): kernels below 6.16.9 break the UMA/GTT
pool this whole stack depends on (the 80 GiB GPU-visible pool that makes
51.7 GiB BF16 weights loadable). The floor is recorded as
`host.minimum_kernel` in [`configs/validated-stack.json`](../configs/validated-stack.json);
the validated host runs `6.17.0-1032-oem` (same file,
`install.kernel_at_install`).

**Workaround.** Upgrade the kernel to ≥ 6.16.9 and re-run the check. The
floor is enforced (not advisory) for the base profile; the community profile
keeps the same kernel sanity gate
([`hardware-validation.md`](hardware-validation.md)).

**Upstream tracking.** None open here — the floor is a recorded host fact,
not an upstream regression report.

## vLLM source build: amdsmi must be importable at platform init
<a id="amdsmi"></a>

**Symptom.** A vLLM source build against TheRock torch fails during ROCm
platform detection because the TheRock-bundled `amdsmi` is not visible
(vLLM's ROCm platform plugin calls `amdsmi.amdsmi_init()` there).

**Reproduction conditions.** Build vLLM from source
(`uv sync --group vllm` + `scripts/01-build-vllm.sh`) but skip the pinned
patch / shim steps — e.g. a hand-rolled `pip install -e` outside this repo's
build script.

**Root cause / diagnosis state.** Two-part fix, both committed and listed in
[`configs/validated-stack.json`](../configs/validated-stack.json)
(`vllm.patches`): (1) `patches/vllm-amdsmi-import.diff` prepends
`import amdsmi` to `vllm/__init__.py` (the lazy import misses the shim);
(2) the build script writes a `.pth` into the venv site dir exposing the
TheRock-bundled amdsmi — whose wrapper resolves its `.so` via a path
RELATIVE TO THE PACKAGE FILE, so it must stay at its original location (a
`pip install` copy breaks it).

**Workaround.** Always build through `bash scripts/01-build-vllm.sh`: it
applies the manifest-listed patches idempotently and writes
`_amdsmi_therock.pth`. Never drop `--no-sync` from serve invocations — a
bare `uv run` re-sync would delete the editable vLLM
(`scripts/03-serve-vllm.sh` header).

**Upstream tracking.** None filed — TheRock-shim interaction, inherited
workaround pattern from the muse-rocm predecessor.

## Dirty llama.cpp checkout refuses to rebuild
<a id="dirty-llama-cpp-checkout"></a>

**Symptom.** `bash scripts/05-build-llama.sh` stops with
`third_party/llama.cpp has uncommitted tracked changes; refusing to …`.

**Reproduction conditions.** Any local edits inside
`third_party/llama.cpp` (tracked files) followed by a rebuild or a pin
change (`LLAMA_COMMIT=…`).

**Root cause / diagnosis state.** Deliberate guard, not a failure: the build
pinned to `configs/validated-stack.json` (`llama_cpp.commit` = `4df29be4`)
never discards your changes automatically; it refuses to move HEAD over
them.

**Workaround.** Keep them: `git -C third_party/llama.cpp stash`, rerun the
script, `git stash pop` later. Discard them:
`git -C third_party/llama.cpp checkout -- .` and rerun. (Exact guidance is
echoed by the failing message itself, `scripts/lib/llama_build.sh`.)

**Upstream tracking.** None — project-side safety behavior.

## Cold `uv sync` loop-fails on small PyPI packages while large wheels succeed
<a id="uv-sync-loop-fail"></a>

**Symptom.** A cold-cache `uv sync --group vllm` downloads every large
TheRock wheel cleanly — `Downloading torch (669.4MiB)`,
`Downloading rocm-sdk-libraries-gfx1151 (574.0MiB)`,
`Downloading rocm-sdk-core (394.8MiB)`, `Downloading triton (329.0MiB)`,
each with its ` Downloaded …` confirmation (~2 GiB total) — then loops
endlessly on the same three small PyPI files:

```
Downloading pillow (6.6MiB)
Downloading numpy (15.9MiB)
Downloading transformers (11.2MiB)
Downloading transformers (11.2MiB)
Downloading numpy (15.9MiB)
Downloading pillow (6.6MiB)
```

No error is printed and no install phase ever starts; after ~60 min the
command exits having installed **nothing** (the venv has no `torch`).

**Reproduction conditions.** Cold uv cache (`UV_CACHE_DIR` pointing at an
empty dir), `uv sync --group vllm`, no `http_proxy`/`https_proxy` in the
environment, on this host's constrained network. Deterministic here: two
independent no-proxy attempts loop-failed on exactly these three files
while a third attempt with a proxy fetched all three in ~26 s and completed
the full install (`+ torch==2.10.0+rocm7.13.0a20260513`,
`+ triton==3.6.0+rocm7.13.0a20260513`, `rc=0`) in under a minute.

**Root cause / diagnosis state.** Network route failure on specific PyPI
CDN files, not a uv or package defect: the direct route to those three
files' CDN endpoints stalls while every large-wheel download from the AMD
nightly index (a different host) succeeds in the same run. uv's retry loop
restarts the file from zero each time, so it never converges. Which files
loop depends on the network; the pattern (few small PyPI files fail,
everything else succeeds) is the signature.

**Workaround.** Route uv through a reachable proxy —
`export http_proxy=http://… https_proxy=http://…` — or point uv at a
reachable mirror with `UV_INDEX_URL=https://mirror/…`. Either resolves the
loop immediately (the three files then download in seconds and the cached
~2 GiB of wheels installs without refetching). If you hit this, kill the
looping sync first; it will not succeed on its own.

**Upstream tracking.** None filed — local network path issue, recorded as
first-run reality in
[getting-started Path B](getting-started.md) and measured in the one-pass
rehearsal receipt
([`results/rocm-7.14/one-pass-rehearsal.md`](results/rocm-7.14/one-pass-rehearsal.md) ## Steps followed (d)).
