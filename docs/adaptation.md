# Adaptation map — from MI-series / Day-0 recipes to RDNA `gfx1151`

What changes when you take an upstream (or AMD Day-0, Instinct-oriented)
recipe for Qwen3.8-27B onto the RDNA 3.5 APU this project validated — and how
long each delta can be trusted to stay true. Every row cites the committed
receipt that established it; nothing here is folklore.

**Durability classes:**

- **durable** — gated by hardware/architecture or by slow-moving upstream
  predicates; re-check only when the silicon or the model changes.
- **pin-local** — verified only at the pinned commits
  ([`configs/validated-stack.json`](../configs/validated-stack.json): vLLM
  `4d2a68d`, llama.cpp `4df29be4`, ROCm 7.14.0); re-verify when a pin moves.
- **host-class** — true of Strix-Halo-class APUs (unified memory), not of
  discrete boards.

## What carries over unchanged

The model-facing wiring is platform-agnostic and needed no patches:

- transformers supports `qwen3_5` in every release tag checked (v5.8.0 →
  v5.15.0) — no from-source install
  ([spike A](results/spike/vllm.md)).
- vLLM registers `Qwen3_5ForConditionalGeneration` (multimodal) and
  `Qwen3_5MTP` (speculative) in-tree
  ([spike A](results/spike/vllm.md));
  our build applied no upstream code changes beyond the two shim patches
  listed in [`configs/validated-stack.json`](../configs/validated-stack.json).
- llama.cpp registers the arch as `qwen35` (GDN linear attention + single-block
  MTP + Qwen3-VL-type mmproj vision) since 2026-02
  ([spike B](results/spike/gguf.md)) — prebuilt GGUF quants exist from three
  publishers, so self-conversion (open bug #27019 at spike time) is a fallback
  only.

## Delta table

| # | Area | MI-series / Day-0 assumption | RDNA `gfx1151` reality (measured) | Durability | Receipts |
|---|---|---|---|---|---|
| 1 | Toolchain | One ROCm stack serves all data-center GPUs | PyTorch comes from the TheRock **per-arch** nightly index (`https://rocm.nightlies.amd.com/v2/gfx1151/`); the index has **no gfx1100 builds** (404, verified 2026-08-17), and it tops out at torch 2.10.0 for cp312 — vLLM then needs the torch-2.13-API compat shim to build | pin-local (nightly index drift) | [`configs/validated-stack.json`](../configs/validated-stack.json), [`hardware-validation.md`](hardware-validation.md), [spike A](results/spike/vllm.md) |
| 2 | Memory model | HBM VRAM sized in 10s of GiB, GPU-only | **UMA/GTT**: an 80 GiB GPU-visible pool carved from 94 GiB system RAM; weights+KV live in GTT, VRAM stays ~1.1 GiB (desktop residue). Budgeting must read the GTT number, and a "silent GTT spill" (throughput collapse with no load error, llama.cpp #26432 class) is the failure mode to watch | host-class (durable per host SKU; 32 GiB-class SKUs change every conclusion) | [`configs/validated-stack.json`](../configs/validated-stack.json), [METHODOLOGY §4](results/METHODOLOGY.md), [spike C](results/spike/quant-kv.md) |
| 3 | Quant surface | FP8 weights everywhere (Instinct Day-0 ships an FP8 checkpoint + Quark MXFP4 recipe) | vLLM's own predicates exclude gfx1151 from native FP8 (`supports_fp8()` = CDNA/RDNA4-only) and from MX compute; the official FP8 repo (28.7 GiB) is CDNA/RDNA4 territory. AMD's Quark W4A16-int4 export is **unloadable** at `4d2a68d` (no matching scheme); Quark MXFP4 loads but computes via high-precision **emulation**. The viable weight-quant class is W4A16 int4 (AWQ/GPTQ/compressed-tensors) via the RDNAHybrid/Triton kernels — `cyankiwi` AWQ-INT4 (19.6 GiB) is the candidate | predicates durable; quark-scheme availability pin-local | [spike C](results/spike/quant-kv.md), [decision table](results/spike/decision-table.md), [`configs/spike-findings.json`](../configs/spike-findings.json) |
| 4 | Attention | CDNA custom paged attention paths | The ROCm custom paged-attention gate requires `head_size == 128`; this model's `head_dim` is **256**, so custom paged attention never fires on gfx1151 regardless of KV dtype — everything routes to **Triton attention** (`--attention-backend TRITON_ATTN` pinned in the confs to protect against auto-select drift) | durable for this model+arch | [spike C](results/spike/quant-kv.md), [`configs/serve-args.conf`](../configs/serve-args.conf), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md) |
| 5 | MTP wiring | One flag, one behavior | **Syntax differs per path and per pin**: llama.cpp `--spec-type draft-mtp` (stock server flag at `4df29be4`; MTP head loads from the same GGUF — no `-md`; **depth configurable** via `--spec-draft-n-max`, upstream default 3 — measured: depth 1 beats depth 4 on both backends, see the Vulkan section below); vLLM `--speculative-config {"method":"mtp","num_speculative_tokens":1}`. **Behavior is concurrency-dependent** (measured): +28.2% per-stream at GGUF c1, +52.6% at vLLM c1, beneficial through vLLM c8, **inverts at c16** (−19.4% aggregate) and at GGUF-vulkan c4 (−7.5% aggregate). AMD's own Vulkan Day-0 measured MTP=4 net-negative on this platform class — depth-sensitive AND backend-sensitive | behavior durable-ish (re-measure per pin); flags pin-local | [`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md), [`configs/serve-args-mtp.conf`](../configs/serve-args-mtp.conf), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md), [`results/benchmark.md`](results/benchmark.md), [troubleshooting](troubleshooting.md#mtp-concurrency) |
| 6 | Vision | Encoder memory profiled/reserved by default | llama.cpp: attach `mmproj-F16` (default ~20 image tokens; `--image-min-tokens 1024` for grounding work, ~1035 tokens). vLLM: **encoder profiling must be skipped** at 262144 (`--skip-mm-profiling`) because the profiling dummy batch scales with `max_model_len` (256 GiB demand vs the 80 GiB pool) — and with it skipped, encoder-peak budgeting becomes the operator's contract | host-class + pin-local | [`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md), [troubleshooting](troubleshooting.md#encoder-profiling) |
| 7 | Kernel floor | N/A on servers | Strix Halo UMA needs kernel ≥ 6.16.9 (muse-rocm heritage finding; enforced by the env check) | host-class | [`configs/validated-stack.json`](../configs/validated-stack.json), [troubleshooting](troubleshooting.md#uma-bug) |
| 8 | Output packaging | DeepSeek-style `reasoning_content` everywhere | llama.cpp emits `message.reasoning_content`; the vLLM `qwen3` parser at `4d2a68d` emits `message.reasoning` (generation identical) | pin-local | [`results/rocm-7.14/gguf-validation.md`](results/rocm-7.14/gguf-validation.md), [`results/rocm-7.14/vllm-validation.md`](results/rocm-7.14/vllm-validation.md), [troubleshooting](troubleshooting.md#reasoning-field) |

## Vulkan backend × MTP depth (v0.1.2, measured 2026-08-18; re-based v0.1.4, cross-day variance root-caused v0.1.6, refined v0.1.7, decision closed v0.1.8)

The second llama.cpp backend measured on the same host, model, prompts, and
harness (8 cells; plan
[`superpowers/plans/2026-08-18-vulkan-mtp-comparison.md`](superpowers/plans/2026-08-18-vulkan-mtp-comparison.md),
tables [`results/benchmark.md`](results/benchmark.md)). All facts below are
**pin-local**. The v0.1.4 re-base (2026-08-19): the session-3 clean
depth-1 pairing and the cross-day re-runs
([`results/matrix-714/stability/`](results/matrix-714/stability/))
supersede the mixed-depth headline the original promotion rested on. The
v0.1.6 root-cause step (same day): session 4's controlled runs explain
the cross-day variance class as Mesa shader-cache state dependence. The
v0.1.7 refinement (2026-08-20): the trigger-hunt forensics
([`results/matrix-714/stability/trigger-hunt-2026-08-19.md`](results/matrix-714/stability/trigger-hunt-2026-08-19.md))
plus the session-5/6 series decompose the variance picture further
(the cross-day bullet below) — dated supersession #3, history visible.
The v0.1.8 closeout (2026-08-20): the repository owner DECIDED the
"re-recommend vulkan?" question — NO ("Choosing the backend" below).

- **Build** — the same llama.cpp pin as the HIP build (`4df29be4`), separate
  tree `third_party/llama.cpp/build-714-vk` via
  [`06-build-llama-vulkan.sh`](../scripts/06-build-llama-vulkan.sh)
  (`-DGGML_VULKAN=ON -DGGML_HIP=OFF`); the HIP `build-714` is untouched.
  **Build prerequisites** (the script checks each and refuses with the
  exact remedy): 5 system packages — `mesa-vulkan-drivers` (the RADV ICD),
  `vulkan-tools` (`vulkaninfo`), `libvulkan-dev`, `glslc` (shaderc's
  compiler; llama.cpp does NOT vendor shaderc at this pin) and
  `spirv-headers`:
  `sudo apt-get install -y mesa-vulkan-drivers vulkan-tools libvulkan-dev glslc spirv-headers`.
  No-root fallback: `VULKAN_DEPS_PREFIX` pointing at a `dpkg-deb -x`
  extraction of the build-side packages (that is how the reference host
  did it — `~/.local/share/qwen38-vulkan-deps`; `vulkaninfo` exists ONLY
  there, not on the system PATH). Note: the build fingerprint pins the
  Mesa point version (the ICD `driverInfo` is part of backend identity),
  so a Mesa/loader upgrade forces a deliberate `build-714-vk` rebuild —
  see [troubleshooting: Vulkan build](troubleshooting.md#vulkan-build).
- **ICD identity** — Mesa RADV, no `VK_ICD_FILENAMES` forcing needed (the
  loader picks it on this host): `AMD Radeon Graphics (RADV GFX1151)`,
  `DRIVER_ID_MESA_RADV`, Mesa `25.2.8-0ubuntu0.24.04.2`, Vulkan 1.4.318
  device / 1.3.275 instance — recorded verbatim in
  [`configs/validated-stack.json`](../configs/validated-stack.json)
  (`llama_cpp_vulkan.icd_details`). Backend identity is part of the
  evidence; the whole ruling rests on ONE ICD.
- **Perf deltas (c1, ctx 131072, single-stream median)** — base: vulkan
  10.65 vs hip 10.14 tok/s (+5%: the backend alone is a small lever, not
  the AMD 24.5 anchor gap). MTP depth 1, v0.1.2 cells: vulkan 16.00 vs
  hip 13.00 tok/s — the **+23% MIXED-DEPTH headline** (see the caveat),
  superseded 2026-08-19 by the **clean d1/d1 pairing** (session 3, both
  backends explicit `--spec-draft-n-max 1`, same day/pin/prompts/harness):
  vulkan 14.53 vs hip 13.86 tok/s = **+4.81%** (gap +0.67) — and the
  **aggregate basis flips**: hip 10.74 vs vulkan 9.31 tok/s = **−13.31%**
  (TTFT-driven: vulkan TTFT 9.94–12.21 s that session vs 8.36–8.83 s
  across the 2026-08-18 sessions; hip TTFT 5.43 s vs 5.47 s on its
  2026-08-16 receipt). The v0.1.2 same-depth pairing (depth 4: vulkan
  mtp4 15.05 vs hip mtp4 12.76 tok/s, +17.9%) stands as measured but is
  itself a 2026-08-18 single-day snapshot — the cross-day table below is
  the stability context for all of these.
- **Cross-depth caveat** — the historical hip mtp receipts (started
  2026-08-16 UTC — 08-17 local) ran the **implicit `--spec-draft-n-max` default 3** (discovered
  post-hoc; [`configs/validated-stack.json`](../configs/validated-stack.json)
  `llama_cpp_vulkan.mtp_depth.note`); every v0.1.2 cell passes its depth
  explicitly and records it in `server_flags`. So 16.00-vs-13.00 is
  depth-1-explicit vs depth-3-implicit — which is why the 2026-08-18
  promotion ruling (built on that headline) was superseded: its hip side
  was depth-confounded. The clean fixed-depth cross-backend numbers are
  the d1 pairing (+4.81%, aggregate −13.31%) and the d4 pairing (+17.9%,
  same day).
- **MTP depth** — depth 4 never beats depth 1 on either backend, on
  depth-explicit receipts with dates labeled (basis fix 2026-08-19):
  vulkan 16.00 vs 15.05 tok/s (2026-08-18 corpus cells, explicit d1 vs
  d4); hip 13.86 (2026-08-19, explicit d1 — session 3) vs 12.76
  (2026-08-18, explicit d4). The corpus hip mtp cell (13.00, 2026-08-16
  UTC) ran implicit depth 3 and is never the depth-1 side of a depth
  comparison. The recommended variant on hip is **`WITH_MTP=1
  SPEC_DEPTH=1`** — the depth pinned explicitly; a bare `WITH_MTP=1`
  boots the implicit upstream depth 3. Depth is configurable at the pin
  (`--spec-draft-n-max`, upstream default 3), NOT fixed by the checkpoint
  (row 5).
- **Cross-day variance (v0.1.4, session 3 = 2026-08-19 vs sessions 1/2 =
  2026-08-18) — root-cause CLASS v0.1.6: Mesa shader-cache state
  dependence; REFINED v0.1.7 into a four-part decomposition (dated
  supersessions of the v0.1.4 "cause not recorded" statement and then of
  the v0.1.6 "s3 partial-cold" reading, both kept visible for history)**
  — the same three vulkan c1 cells re-run on the next UTC day dropped on
  every cell, while hip was same-session stable:

  | Cell (stream tok/s) | s1 08-18 | s2 08-18 | s3 08-19 | s3 vs s1/s2 | max spread |
  |---|---|---|---|---|---|
  | mtp-c1 (depth 1) | 16.00 | 16.25 | 14.53 | −9.21% / −10.56% | 11.81% |
  | mtp4-c1 (depth 4) | 15.05 | 15.25 | 11.67 | −22.49% / −23.49% | 30.70% |
  | base-c1 | 10.65 | 10.91 | 10.29 | −3.35% / −5.72% | 6.07% |

  Same session, the hip side: mtp-c1 explicit d1 13.86 tok/s vs the
  canonical implicit-d3 cell 13.00 (+6.61%) — **day-confounded**
  (different days), so it is labeled, never read as a depth claim; hip
  TTFT 5.43 s vs 5.47 s historical. The v0.1.4 statement was: *the
  host-level cause of the vulkan cross-day drop is NOT recorded — the
  receipts carry VRAM/GTT only, no clock/thermal telemetry (known
  harness debt)*. Session 4 (2026-08-19, R1 telemetry harness: 5
  controlled runs — two warm vulkan boots, two hip controls, one
  cache-aside arm; receipts
  [`results/matrix-714/stability/session4-2026-08-19/`](results/matrix-714/stability/session4-2026-08-19/))
  **supersedes it**: the root-cause CLASS is **Mesa shader-cache state
  dependence** — with the cache moved aside (identical
  config/flags/pin/host state) vulkan mtp-c1 drops to 12.38 tok/s /
  TTFT 12.45 s (reproducing and exceeding the s3 slow signature) and
  rebuilds a fresh cache mid-run (2136 KiB / 100 files), while the warm
  cache stays stable at 7884 KiB / 867 files across runs (one run
  touched nothing). v0.1.6 then read s3 as "partial-cold consistent";
  v0.1.7 **retires that reading** (the trigger-hunt forensics below).

  | Mesa cache state | mtp-c1 stream tok/s | TTFT | measured where |
  |---|---|---|---|
  | cold (cache moved aside) | 12.38 | 12.45 s | session 4, cache-aside arm — the swing **BOUND** |
  | warm — cache forensically INTACT (v0.1.7 finding) | 14.53 | 9.94 s | session 3: slow with an untouched cache — **vk-specific residual, trigger UNIDENTIFIED** |
  | warm | 16.96–17.10 (mean 17.03) | 8.37–8.50 s | session 4 morning, boots 1/2 |
  | warm | 16.00–16.25 | 8.36–8.83 s | sessions 1/2 (2026-08-18) |
  | warm | 16.25 | 8.49 s | session 5 (08-19 evening) |
  | warm | 16.41 | 8.54 s | session 6 (08-20 local morning, after an idle night) |

  Cold→warm swing **+38%** (cold is −27.3% vs the warm mean) — the
  BOUND proof of the cache-state class, NOT s3's explanation. The v0.1.7
  decomposition, each part receipt- or note-backed:

  1. **Cache forensics (trigger hunt, 2026-08-20 integration of
     [`trigger-hunt-2026-08-19.md`](results/matrix-714/stability/trigger-hunt-2026-08-19.md),
     independently reproduced):** the mesa cache was **INTACT at s3** —
     866 files pre-window / **0 written inside the causal window** / 1
     post (session-4's marker). The v0.1.6 sentence *s3's 14.53 sits
     between cold and warm → a partial-cold cache state is consistent;
     the s3 TRIGGER is UNKNOWN (no Mesa upgrade, no reboot — host up
     since 2026-08-12 per every session-4 receipt's `telemetry.env`, no
     cache-clear found)* stays visible as history but is SUPERSEDED:
     s3 ran slow with a warm untouched cache, so **the vk-specific s3
     trigger is UNIDENTIFIED** — cache ruled out; no suspend/resume, no
     amdgpu reset/errors, no power-profile switch in the causal window;
     the clock-stepping condition was ABSENT during s3's run; the only
     discrete in-window state change is the unattended-upgrade of
     linux-libc-dev/linux-tools-common 6.8.0-137→138 (06:20 local
     08-19) — recorded as fact, **no mechanism claimed**.
  2. **Chronic common-mode clock-stepping (not s3-specific):** 883+
     `Clock change detected` events since the 2026-08-12 boot (still
     accruing — count per the note, not frozen); present during s1 (×2),
     the s2 soak (×1), and s5 (×3); ABSENT during s3's run. A common-mode
     condition, not an s3 cause.
  3. **Common-mode session drift ±5–6%:** session 5 (evening) measured
     BOTH backends slower than the session-4 morning runs — vk −4.6%, hip
     −6.0% vs the s4 means — shared host-state drift that moves both
     backends together.
  4. **Warm band + overnight persistence:** the warm pairing band
     (vulkan−hip, same session, warm cache) spans 4 sessions —
     **+15.88 / +20.61 / +19.90 / +15.93%** (s4 boots 1-2, s5, s6).
     Session 6 ran **7 h 50 m after s5** (receipts-derived; same boot
     throughout) with the cache **byte-identical** (7884 KiB / 867
     files, zero writes, newest mtime still session-4 run 1's
     06:32:54Z) and the pairing in band — overnight warm persistence
     CONFIRMED (vk 16.41 / TTFT 8.54 s; hip 14.15 / TTFT 5.49 s).
     Aggregate/TTFT are consistently **hip-favored** (TTFT vk 8.4–8.6 s
     vs hip 5.4–5.6 s every session; aggregate s5 +1.07%, s6 −2.39%) —
     vulkan's edge is the single-stream median only.

  Telemetry (session 4) rules out thermal/power: post-bench envelopes
  are vk 1433–1533 MHz / 30–32 W / 54–57 °C and hip 1910–1929 MHz /
  52–53 W / 58 °C — each backend in its own normal envelope, no anomaly
  (vk cross-boot −0.79%, hip controls 14.76/14.06 tok/s = −4.7%
  cross-boot, near-deterministic). RELABEL (v0.1.6, arithmetic
  unchanged; basis refined v0.1.7): the v0.1.4 clean d1 pairing
  **+4.81% is the conservative floor case** — vk measured well below
  its warm band (14.53 vs 16.0–17.1) in the unidentified slow state —
  so its arithmetic and the no-flip conclusion stand unchanged; the
  warm pairings are ceiling context, now a 4-session band rather than a
  single warm session.

  **Warmup guidance (practical, non-recommending):** if vulkan feels
  slow, first-run cache warmup is the first suspect — re-run before
  concluding; the first boot after a cache clear runs ~12.4 tok/s /
  ~12.5 s TTFT until warm. (v0.1.7 note: warmup explains the cold-cache
  bound; it does NOT explain s3 — the cache was warm there.)
- **Greedy pit status** — the §6 HIP greedy-degradation pit does **NOT
  reproduce on Vulkan**: 6/6 vulkan corpus cells anchor-clean
  (base/mtp/mtp4 × c1/c4), and across the stability sessions the
  cell-run anchors are 19/19 (s1–s6; 20/20 with the soak anchor).
  The pit remains a hip-family (gfx1151/HIP) finding at this pin;
  Vulkan c8/c16 are unmeasured.
- **Quickstart status (project ruling 2026-08-19 SUPERSEDES the
  2026-08-18 promotion; v0.1.4) — UNCHANGED by the v0.1.6 root-cause
  finding and by the v0.1.7 refinement** — `BACKEND=vulkan` is an
  **available experimental opt-in, NOT recommended**: the 08-18
  promotion rested on the mixed-depth headline, and the clean d1
  pairing (+4.81% single-stream, aggregate −13.31%; the conservative
  floor case — vk measured in the unidentified slow state, well below
  its warm band) plus the variance decomposition above do not support a
  recommendation. **hip `WITH_MTP=1 SPEC_DEPTH=1` is BOTH the default
  and the recommended path** (13.0 tok/s on the corpus cell; 13.86
  depth-explicit). No-flip closed on the clean arithmetic: +4.81% <<
  the >25% pre-registered flip threshold. The recorded rationale,
  updated v0.1.7 both ways (controller ruling 2026-08-20, not
  re-deliberated): FOR re-recommending — the warm band is now 4
  consistent sessions (+15.88/+20.61/+19.90/+15.93%) and overnight
  persistence is proven; AGAINST — the s3 trigger is MORE mysterious
  with the cache ruled out, P(vk-specific slow state) is unquantified,
  and aggregate/TTFT stay hip-favored (vk's edge is the single-stream
  median only). The warm/cold swing remains a user-facing UX risk
  (~12.4 tok/s / ~12.5 s TTFT after a cache clear, until warm) — so
  the mapping layer does not move; the "re-recommend vulkan?" question
  was explicitly OPEN for the human owner (README roadmap) until the
  owner ruling 2026-08-20 closed it — NO (the "Choosing the backend"
  bullet below). Recorded per cell in
  [`configs/benchmark-verdicts.json`](../configs/benchmark-verdicts.json)
  (the vulkan mtp-c1 ruling note carries all three dated supersessions
  plus the dated OWNER DECISION addendum; the cell's mechanical verdict
  is unchanged — what changed is the mapping layer).
- **Choosing the backend (owner ruling 2026-08-20, v0.1.8 — the OPEN
  question closed: NO)** — NOT re-recommending `BACKEND=vulkan`; the
  guidance below is self-selection criteria, never promotion. The
  end-to-end arithmetic, from the s4/s5/s6 warm pairings: vulkan's warm
  streaming gain (band +15.88/+20.61/+19.90/+15.93%) is repaid only on
  LONG replies because its first token is ~3 s slower (TTFT vk
  8.49–8.54 s vs hip 5.49–5.63 s on s5/s6) — at a 256-token reply the
  end-to-end delta is within **±0.6 s** (s4 +0.54 s vk-slower, s5
  −0.28 s vk-faster, s6 +0.55 s vk-slower), and the derived crossover
  is **≈230–310 tokens (derived)** — TTFT gap ÷ per-token gain:
  2.91/0.00927≈314, 2.86/0.01227≈233, 3.05/0.00978≈312 — arithmetic
  over the receipts, labeled derived, not a measurement. Power
  (session-4 post-bench package telemetry): vk **~30–32 W** vs hip
  **~52–53 W** — the real power/heat/noise argument for vk. Cold
  start (the state a recommendation would systematically deliver to
  new users first): **12.38 tok/s, TTFT 12.45 s** — worse than default
  hip on both. **Guidance (self-selection, non-recommending):**
  self-select the vk opt-in for long outputs (≳300-token replies, the
  derived crossover) or power-sensitive setups; short-reply
  interactive users get no end-to-end benefit and a slower first
  token. **Pre-registered promotion criteria — ALL four must hold
  before any future upgrade to conditional-recommended:**
  (1) a daily warm series of at least 7 days with ZERO slow-state recurrence;
  (2) the vk c8/c16 cells measured with anchors clean (pit coverage — currently unmeasured);
  (3) at least one independent host/ICD replication (a community submission is ideal);
  (4) the TTFT gap stated as an applicability condition (long-generation only), not a footnote.
- **Stability (v0.1.3, measured 2026-08-18)** — a second, independent
  measurement session (hours after the v0.1.2 session, independent server
  boots, same host/pin/harness) reproduced every Vulkan c1 cell: mtp-c1
  16.00→16.25 tok/s (+1.5%), mtp4-c1 15.05→15.25 (+1.3%), base-c1
  10.65→10.91 (+2.5%) — session 2 uniformly slightly faster, consistent
  with a warmer machine. A 30-min sustained-load soak on the then-promoted
  config (one boot, runner-identical flags) ran 108/108 clean cycles with
  zero health flaps, a mild settle (stream-rate halves 16.43→16.00 tok/s,
  -2.6%; aggregate halves -2.8%) and a clean post-soak greedy anchor.
  Receipts: [`results/matrix-714/stability/`](results/matrix-714/stability/)
  (receipts-only — they do not enter the 28-cell matrix). **Revised
  v0.1.4:** the same-day picture was stable, but the next-day session-3
  re-runs (the cross-day table above) dropped every vulkan cell — the
  same-day-stability conclusion did not carry across days, which is part
  of why the 2026-08-19 ruling downgraded the opt-in. **Revised again
  v0.1.6:** session 4 added the clock/thermal telemetry and root-caused
  the cross-day drop to Mesa shader-cache state (see the cross-day
  bullet) — the same-day stability reading is now understood as
  warm-cache stability. **Revised once more v0.1.7:** the daily series
  (sessions 5/6) shows the warm-cache state persisting overnight
  unchanged (byte-identical cache, pairing in band) and quantifies a
  common-mode ±5–6% session drift on both backends — while s3's slow
  run remains unexplained (cache forensically intact). **Remaining
  limits, still true:** single host (gfx1151), single ICD (RADV, Mesa
  25.2.8), boot-per-cell — the soak covers sustained load only (and the
  pit finding is unaffected: anchors 19/19 across s1–s6).
- **Unified rider (hip)** — `gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified`
  (the stock 4-slot unified default boot under 4 concurrent users): 6.7
  tok/s healthy-stream median / 5.0 aggregate (3-of-4 streams stopped
  within 8 tokens — early EOS, aggregate not comparable) vs split-mode c4
  7.5 / 9.4 — **unified-default-boot degrades interactivity on the
  8060S**; measured-with-caveat, no config change (single-stream use
  unaffected; light multi-user already steers to vLLM).

## Porting checklists by durability

**Re-verify when a pin moves (pin-local):** TheRock index contents and torch
cap (row 1); quark scheme coverage (row 3); MTP flag spelling and reasoning
field name (rows 5, 8); encoder-profiling behavior (row 6).

**Re-verify per host (host-class):** GTT pool size and the spill watch-point
(row 2); kernel floor (row 7); encoder-peak headroom (row 6). Discrete boards
(W7900, `gfx1100`, 48 GiB GDDR6) have no GTT pool at all — memory evidence
must come from the submitter's own `rocm-smi` receipts per
[`hardware-validation.md`](hardware-validation.md), and the protocol
prescribes evidence format, not a stack.

**Trust as-is (durable):** Triton attention routing for `head_dim` 256
(row 4); the arch registration facts in "What carries over unchanged"; the
KV closed form (64 KiB/token bf16 — only the 16 full-attention layers grow
KV; [METHODOLOGY §4](results/METHODOLOGY.md)).

## Non-goals carried from the spike

FP8 weights on gfx1151 (`supports_fp8`=False), the AMD Quark W4A16-int4
checkpoint (unloadable), and Quark MXFP4 as anything more than an emulation
datapoint were **deliberately not scheduled** for validation
([decision table](results/spike/decision-table.md),
[spike C](results/spike/quant-kv.md)). KV-cache dtype sweeps (fp8/q8_0) were
declared non-goals of the measured session (METHODOLOGY §1) — on the
validated 80 GiB pool they are a throughput/quality lever, not a capacity
gate; on 32 GiB-class envelopes they are mandatory
([spike C impact tables](results/spike/quant-kv.md)).
