# Changelog

All notable changes to this project are documented here. Every number below
recomputes from committed artifacts: verdicts
[`configs/benchmark-verdicts.json`](configs/benchmark-verdicts.json), generated
tables [`docs/results/benchmark.md`](docs/results/benchmark.md), raw cell
receipts [`docs/results/matrix-714/cells/`](docs/results/matrix-714/cells/),
and the rehearsal receipt
[`docs/results/rocm-7.14/one-pass-rehearsal.md`](docs/results/rocm-7.14/one-pass-rehearsal.md).

## v0.1.13 — 2026-08-21

Docs UX pass after an independent review (GO-WITH-FIXES): the v0.1.12
guidance revision had not reached the surfaces users actually copy.

- **P0 — troubleshooting `#dflash2-nmax-cap` no longer steers to the
  config the sweep retired**: the workaround now recommends the
  measured-optimal 2–4 band (`SPEC_DEPTH=4`; n-max 7 costs 21–27%
  single-stream) instead of "request 7 directly".
- **All three copy-paste surfaces now show `SPEC_DEPTH=4`** (README boot
  table + 3-command quick start; dflash2/README quick start) with the
  parity-with-MTP figures; the stale "+13% vs base" row is gone.
- "Which serving path?" multi-user row now scopes the gfx1151 "Don't" and
  names DFlash2 as the measured gfx1100 c4 winner; README nav gains a
  DFlash 2 anchor; the sweep headline carries its scope tag
  (c1-only, 3-run medians, one host); roadmap gains the DFlash2
  follow-up items.
- Evidence discoverability: the results index
  ([`docs/results/README.md`](docs/results/README.md)) now lists the
  dflash2 namespace; getting-started "Where to go next" links it; the
  broken fp8-unlock link in dflash2/README is fixed
  (`community-explorations/…/spike/fp8-unlock.md`) and the link-guard
  test now covers the dflash2 namespace docs.
- Figures: "+6.9 GiB" VRAM (mixed bases) corrected to the exact
  +6918 MiB in three files; CITATION date-released updated to 2026-08-21.
- `gguf-quickstart.sh` --help/header/boot-echo texts updated (the echo
  no longer claims any n-max equals block_size−1). New guard test pins
  the corrected copy-paste surfaces.

## v0.1.12 — 2026-08-21

n-max sweep (the upstream-offer follow-up): the single-stream DFlash2
recommendation on gfx1100 changes — **n-max 2–4, not 7**.

### Measured

- `scripts/probe-dflash2-nmax-sweep.sh` +
  [`docs/results/dflash2/nmax-sweep.json`](docs/results/dflash2/nmax-sweep.json):
  fresh boot per config, the cells' exact bench command ×3 (median), Q8_0
  draft: n-max 2/4/5/7 → **41.59 / 40.02 / 38.64 / 31.64 tok/s** with
  acceptance 0.706/0.519/0.457/0.326 (monotone — shorter blocks accept
  more; n-max 7 pays draft+verify for rejected tails). Within-session
  4-vs-7: **+26.5%**; vs the published n-max-7 cell: +20.6%
  (conservative bound; session anchor measured −4.6% below the cell,
  recorded in the receipt). n-max 2 vs 4 within run-spread noise.
- **Q4_K_M drafter is not faster on gfx1100** (−3.2% at n-max 4, −11.6%
  at 7; opposite of the Volta report upthread) — Q8_0 stays the default.
- **Guidance revised:** `WITH_DFLASH2=1 SPEC_DEPTH=4` is the recommended
  DFlash2 boot on this host class — 40.0–41.6 tok/s single-stream,
  **parity with MTP depth 1** (41.34; the +0.6% gap is inside the run
  spread). Matrix cells stay n-max-7 (grammar-pinned, published); a c4
  n-max-4 re-pairing is future work. experiments.md F8; both READMEs
  updated; guard test recomputes the sweep claims from the receipt.

## v0.1.11 — 2026-08-21

Docs correction (no code, no new measurements): the two headline
with/without deltas are now computed from RAW cell medians, not from
rounded display values — **c1 +12.8%** (was +12.9%) and **c4 +23.3%**
(was +23.4%); MTP-c1 VRAM corrected to 27.4 GiB (was the c4 value,
27.2). The raw receipts were always correct and remain the source of
truth; the wrong figures lived only in derived prose (README,
dflash2/README, experiments, matrix notes, the two CHANGELOG sections
above — all corrected in place). The v0.1.9/v0.1.10 tag annotations and
commit messages are immutable history and still carry the earlier
figures. Guard added so this class of drift cannot recur silently:
`tests/test_dflash2.py` now recomputes the medians from the committed
cell receipts and asserts the exact claim strings in both READMEs
(`test_readme_claims_recompute_from_cell_receipts`).

## v0.1.10 — 2026-08-21

DFlash 2 evidence completion (same-day follow-up to v0.1.9): the 3-way
comparison table is closed and one hypothesis is retired by measurement.

### Added / Measured

- **c4 MTP arm** (`gguf-hip-udq4kxl-auto-mtp-c4-ctx131072`, clean-paired
  on the same PR-27342 binary): **16.4 tok/s median** (−5.0% vs base c4
  17.3; aggregate 43.6) — MTP-d1 inverts at c4 on this host, while
  DFlash2 holds 21.4 (+23.3%). The recommendation now **splits by load
  shape**: single-stream → `WITH_MTP=1 SPEC_DEPTH=1`; 2–4 concurrent
  streams → `WITH_DFLASH2=1`. Receipt in
  [`docs/results/dflash2/cells/`](docs/results/dflash2/cells/).
- **Acceptance probe** (`scripts/probe-dflash2-acceptance.sh` +
  [`acceptance-probe.json`](docs/results/dflash2/acceptance-probe.json)):
  same binary, same 8 prompts, only the sampling regime changes —
  project bench (0.7/0.95) acceptance **0.2855** vs vendor-recommended
  (1.0/0.95/k20) **0.2829**. Statistically identical → the acceptance
  gap vs the vendor evals is **workload-intrinsic, not a sampling
  artifact** (v0.1.9's F1 sampling hypothesis retired by measurement).
- **Upstream re-check**: llama.cpp PR #27342 still OPEN at the pinned
  head `5ecbe1ac` — no re-pin needed (recorded in experiments.md F7).
- Updated comparison tables in README + docs/results/dflash2/README.md;
  experiments.md F1/F3 refined, F7 added.

## v0.1.9 — 2026-08-21

DFlash 2 phase: **opt-in block-diffusion speculative decoding** for the
GGUF path, with a host-measured with/without comparison and a
losslessness proof. Defaults untouched — every boot without
`WITH_DFLASH2=1` is byte-identical to v0.1.8.

### Added

- `WITH_DFLASH2=1` quickstart mode (`scripts/gguf-quickstart.sh`):
  attaches the [`incoai/Qwen3.8-27B-DFlash2`](https://huggingface.co/incoai/Qwen3.8-27B-DFlash2)
  drafter via `-md … --spec-type draft-dflash --spec-draft-n-max 7`
  (7 = `block_size 8 − 1`, the checkpoint physics; higher requests are
  refused — the muse-rocm F-18 lesson applied to v2 at the source;
  pinned by `tests/test_dflash2.py`).
- `scripts/07-build-llama-dflash2.sh`: idempotent HIP build of llama.cpp
  PR [#27342](https://github.com/ggml-org/llama.cpp/pull/27342) (OPEN at
  pin `5ecbe1ac…`, recorded in `configs/validated-stack.json`
  `llama_cpp_dflash2`) into `build-714-dflash2` — the pinned `build-714`
  and `build-714-vk` are never touched. GPU arch auto-detected as the
  concrete 4-digit gfx target (`gfx11-generic` can never win).
- `dflash2` artifact set (`configs/artifact-manifest.json`,
  ModelScope mirror; huggingface.co is unreachable from the evidence
  host — pit `#dflash2-draft-fetch`): Q8_0 (default) + Q4_K_M drafts,
  SHA256-verified at fetch.
- `scripts/check-dflash2-equiv.sh`: greedy byte-identity A/B (same
  binary both arms) — **PASS 4/4 on-host**
  ([`docs/results/dflash2/equiv.json`](docs/results/dflash2/equiv.json)):
  the model card's losslessness claim is verified, not repeated.
- `dflash2` spec part in the cell-id grammar
  (`run-cell-gguf.sh`, shared with the schema/test pin) + `LLAMA_SERVER`
  honored in the runner preflight so an evidence run can boot BOTH arms
  from one binary (clean pairing).
- `docs/results/dflash2/`: host-labeled evidence namespace (project
  matrix untouched) — 6 measured cells, stack receipt, experiments.
- Three troubleshooting pits: unmerged-PR build/re-pin
  (`#dflash2-pr-build`), the n-max cap (`#dflash2-nmax-cap`), the
  draft-fetch/ModelScope fact (`#dflash2-draft-fetch`).
- `tests/test_dflash2.py` (15 contract tests) and the extended
  `test_cell_runner.py` grammar pin.

### Measured (the point of the phase)

Clean pairing — SAME PR-27342 binary both arms, same day, same prompts —
on a W7900-class `gfx1100` host (48 GiB, ROCm 7.2.1 serving, UD-Q4_K_XL
@ ctx 131072): **+12.8% single-stream** (29.4 → 33.2 tok/s), **+23.3%
c4 median** (17.3 → 21.4 tok/s), TTFT +0.42 s, VRAM +6918 MiB. MTP-d1
context arm: 41.3 tok/s (+40.5%) — on THIS host class MTP depth 1 stays
the faster single-stream choice; DFlash2's measured case is c4 and
losslessness. Vendor numbers (2.7–3.4× H200/SGLang, 1.8× M5 Pro) do not
transfer — draft acceptance measured 0.36 vs ≈ 5/7 on vendor evals; the
analysis is in
[`docs/results/dflash2/experiments.md`](docs/results/dflash2/experiments.md)
(F1–F4, including the c16 probe: the DFlash v1 `-np 16` hang does NOT
reproduce on v2).

## v0.1.8 — 2026-08-20

Decision release (closeout D1): the repository owner **DECIDED the OPEN
"re-recommend `BACKEND=vulkan`?" question — NO** (owner ruling
2026-08-20, recorded, not re-deliberated). Vulkan stays an **available
experimental opt-in, NOT recommended**; hip `WITH_MTP=1 SPEC_DEPTH=1`
stays **both the default and the recommended path** — the mapping of
record is confirmed, not changed. **No corpus data changed**: the 28
cells, `matrix.json`, every cell verdict, every metric, and the 8/14/6
distribution are untouched; the verdicts-JSON delta is the vulkan
mtp-c1 ruling note (dated OWNER DECISION addendum — resolution #4; the
v0.1.6/v0.1.7 "OPEN for the owner" phrasings stay visible, marked
resolved).

### The decision and its evidence

- **Rationale (all verifier-locked):** (1) end-to-end latency **parity
  at typical reply lengths** — vk's TTFT is consistently ~3 s higher
  (8.4–8.6 vs 5.4–5.6 s), offsetting the warm streaming gain
  (+15.88/+20.61/+19.90/+15.93% across 4 sessions); derived crossover
  **≈230–310 tokens (derived — arithmetic over the s4/s5/s6 receipts:
  2.91/0.00927≈314, 2.86/0.01227≈233, 3.05/0.00978≈312; labeled
  derived, not a measurement; at a 256-token reply the end-to-end delta
  is within ±0.6 s); (2) a cold-cache first boot (12.38 tok/s, TTFT
  12.45 s — worse than default hip on both) is the state a
  recommendation would systematically deliver to new users first;
  (3) 1-of-7 vk runs hit the unexplained slow state (s3 14.53, trigger
  unidentified after forensics); (4) the evidence base is
  single-host / single-ICD (RADV 25.2.8) / single-Mesa-point /
  2-days.
- **Selection guidance (user-facing, non-recommending — self-selection
  criteria, never promotion):** users generating long outputs
  (≳300-token replies, the derived crossover) or sensitive to GPU
  power/heat/noise (vk ~30–32 W vs hip ~52–53 W package) may
  reasonably self-select the vk opt-in; short-reply interactive users
  get no end-to-end benefit and a slower first token.
- **Pre-registered promotion criteria — ALL four must hold before any
  future upgrade to conditional-recommended:** (1) a daily warm series
  of at least 7 days with ZERO slow-state recurrence; (2) the vk c8/c16
  cells measured with anchors clean (pit coverage — currently
  unmeasured); (3) at least one independent host/ICD replication (a
  community submission is ideal); (4) the TTFT gap stated as an
  applicability condition (long-generation only), not a footnote.

### Surfaces

- `configs/benchmark-verdicts.json` — regenerated: the vulkan mtp-c1
  ruling note gains the dated OWNER DECISION addendum (selection
  guidance + promotion criteria included); zero metric/verdict
  changes; distribution 8/14/6 unchanged.
- `README.md` — the roadmap OPEN question becomes the **CLOSED decision
  entry** ("DECIDED 2026-08-20: NO") with the compact rationale pointer
  and the four criteria; the generated known-good vulkan bullet gains
  the one-sentence selection guidance (numbers interpolated from the
  stability loader); current release → v0.1.8.
- `docs/results/benchmark.md` — the quickstart-mapping row carries the
  guidance pointer; the ruling paragraph and the verdict-rule list
  carry the dated decision bullet.
- `scripts/gguf-quickstart.sh` — ONE new echo line (`selection    :`)
  in the vulkan branch; boot logic and defaults byte-identical; the
  "NOT recommended" framing unchanged.
- `docs/adaptation.md` §Vulkan — new **"Choosing the backend (owner
  ruling 2026-08-20)"** subsection: the end-to-end arithmetic
  (256-token parity ±0.6 s; crossover derived), power figures,
  cold-start facts, the guidance sentence, and the four criteria as the
  enumerated path to any future upgrade.
- `CITATION.cff` — 0.1.7 → 0.1.8.

## v0.1.7 — 2026-08-20

Evidence-integration release (H2): the trigger-hunt forensics
([`docs/results/matrix-714/stability/trigger-hunt-2026-08-19.md`](docs/results/matrix-714/stability/trigger-hunt-2026-08-19.md)
— read-only host-log hunt in the s2→s3 causal window, independently
reproduced) **refute the v0.1.6 "s3 partial-cold" reading** (dated
supersession #3 — the repo's third; history stays visible in the ruling
note), and the session-5/6 series
([`session5-2026-08-19T2321local/`](docs/results/matrix-714/stability/session5-2026-08-19T2321local/),
[`session6-2026-08-20T0712local/`](docs/results/matrix-714/stability/session6-2026-08-20T0712local/))
**strengthens the warm band to 4 sessions with overnight persistence**.
**No corpus data changed**: the 28 cells, `matrix.json`, every cell
verdict, every metric, and the 8/14/6 distribution are untouched; the
verdicts-JSON delta is the vulkan mtp-c1 ruling note plus the top-level
ruling-of-record attribution (→ `controller-2026-08-20`). **The
recommendation layer is UNCHANGED** (controller ruling 2026-08-20,
recorded, not re-deliberated); the warmup guidance stands.

### Supersession #3 — s3's cache was INTACT

- **The forensic finding:** the mesa cache was **INTACT at s3** — 866
  files pre-window / **0 written inside the causal window** / 1 post
  (session-4's marker at 06:32:54Z). "s3 = partial-cold cache" is
  **contradicted** as the explanation: s3 ran slow (14.53) with a warm
  untouched cache. The v0.1.6 wording stays visible in the ruling note,
  marked superseded 2026-08-20.
- **The cold-cache arm survives as the swing BOUND proof** (cold 12.38
  vs warm mean 17.03 = the +38% class) — a bound on the variance class,
  no longer offered as s3's explanation.
- **s3's vk-specific trigger: UNIDENTIFIED.** Cache ruled out; no
  suspend/resume, no amdgpu reset/errors, no power-profile switch in
  the causal window; the clock-stepping condition was ABSENT during
  s3's run; the only discrete in-window state change is the
  unattended-upgrade of linux-libc-dev/linux-tools-common
  6.8.0-137→138 (06:20 local 08-19) — recorded as fact, **no mechanism
  claimed**.

### New recorded findings (a)–(e)

- **(a) Chronic common-mode clock-stepping:** 883+ `Clock change
  detected` events since the 2026-08-12 boot (still accruing — count
  per the note, never frozen); present during s1 (×2), the s2 soak
  (×1), and s5 (×3); explicitly NOT s3-specific.
- **(b) Common-mode session drift ±5–6%:** session 5 (evening) measured
  BOTH backends slower than the session-4 morning runs — vk −4.6%, hip
  −6.0% vs the s4 means — shared host-state drift.
- **(c) Warm pairing band, 4 sessions:** **+15.88 / +20.61 / +19.90 /
  +15.93%** (s4 boots 1-2, s5, s6) — what v0.1.6 called ceiling context
  from "a single warm session" is now a 4-session band.
- **(d) Overnight warm persistence CONFIRMED:** session 6 ran **7 h
  50 m after s5** (receipts-derived — s5's last receipt to s6's first,
  same boot; not the "~20 h" a date-label reading suggests); the cache
  was **byte-identical** (7884 KiB / 867 files, zero writes, newest
  mtime still session-4 run 1's 06:32:54Z) and the pairing +15.93% is
  in band (vk 16.41 / TTFT 8.54 s; hip 14.15 / TTFT 5.49 s).
- **(e) Aggregate/TTFT consistently hip-favored:** TTFT vk 8.4–8.6 s vs
  hip 5.4–5.6 s every session; aggregate s5 +1.07% (hip 10.47 vs vk
  10.58), s6 −2.39% (hip 10.89 vs vk 10.63) — vulkan's edge is the
  single-stream median only.

### Recommendation unchanged; OPEN question restated both ways

- **Mapping unchanged:** vulkan stays an **available experimental
  opt-in, NOT recommended**; hip `WITH_MTP=1 SPEC_DEPTH=1` stays
  **default AND recommended**; warmup guidance stands. The +4.81% clean
  pairing keeps the conservative-floor-case label (basis refined: vk
  measured in the unidentified slow state, well below its warm band —
  arithmetic and the no-flip conclusion unchanged).
- **The OPEN "re-recommend vulkan?" question (README roadmap) is
  restated BOTH ways honestly, not decided:** FOR — the warm band is
  now 4 consistent sessions and overnight persistence is proven;
  AGAINST — the s3 trigger is MORE mysterious (cache ruled out),
  P(vk-specific slow state) is unquantified, and aggregate/TTFT stay
  hip-favored.
- **Surfaces updated:** the vulkan mtp-c1 ruling note
  (`configs/benchmark-verdicts.json`), the generated README blocks +
  [`docs/results/benchmark.md`](docs/results/benchmark.md) variance
  statements (both texts visible with supersession markers),
  [`docs/adaptation.md`](docs/adaptation.md) §Vulkan (variance
  paragraph rewritten to the four-part decomposition; warm/cold table
  gains s5+s6 rows), the quickstart header comment (echo/boot logic
  byte-identical), README current-release + roadmap. `CITATION.cff`
  0.1.7. Tests: the anchor tally extends to 19/19 across s1–s6 (20/20
  with the soak); a new test recomputes the 4-session band, the s5/s6
  pairings, the overnight-persistence facts (cache before==after on the
  s6 vk receipt), and the common-mode deltas from the loader; the
  quickstart-mapping test still asserts vulkan NOT recommended.

## v0.1.6 — 2026-08-19

Variance root-cause release (R2): the session-4 controlled runs
([`docs/results/matrix-714/stability/session4-2026-08-19/`](docs/results/matrix-714/stability/session4-2026-08-19/)
— two warm vulkan boots, two hip controls, one cache-aside arm, under the
R1 clock/power/temp + mesa-cache telemetry harness) **explain the v0.1.4
cross-day variance**: root-cause class is **Mesa shader-cache state
dependence**. **No corpus data changed**: the 28 cells, `matrix.json`,
every cell verdict, and the 8/14/6 distribution are untouched; the only
verdicts-JSON delta is the vulkan mtp-c1 cell's ruling note. **The
recommendation layer is UNCHANGED** (controller ruling 2026-08-19,
recorded, not re-deliberated).

### The finding (dated supersession of "cause not recorded")

- **Bounds, identical config/flags/pin:** warm vulkan mtp-c1 boots
  **17.10 / 16.96 tok/s** (cross-boot −0.79%, warm mean 17.03, warm
  TTFT 8.37–8.50 s); the cache-aside arm (cache moved aside) measures
  **12.38 tok/s / TTFT 12.45 s** (−27.3% vs the warm mean — reproducing
  and exceeding the s3 slow signature 14.53 / 9.94 s) and rebuilt
  **2136 KiB / 100 cache files** mid-run while the warm cache stayed
  stable at **7884 KiB / 867 files** across runs (one run touched
  nothing). **Cold→warm swing +38%.**
- **s3 explained:** 14.53 sits between cold (12.38) and warm (17.03) →
  a **partial-cold cache state is consistent**; the s3 **TRIGGER is
  unknown** (no Mesa upgrade, no reboot — host up since 2026-08-12, no
  cache-clear found) — stated honestly. The v0.1.4 "cause not recorded"
  sentence stays visible in the ruling note, marked superseded
  (2026-08-19 R2).
- **Telemetry rules out thermal/power:** post-bench envelopes vk
  1433–1533 MHz / 30–32 W / 54–57 °C, hip 1910–1929 MHz / 52–53 W /
  58 °C — each backend in its own normal envelope. Hip controls
  14.76 / 14.06 tok/s (cross-boot −4.7% — near-deterministic). Cell-run
  anchors now 15/15 across s1–s4 (16/16 with the soak anchor) — the
  pit non-reproduction finding is unaffected.
- **Floor/ceiling relabels (arithmetic unchanged):** the v0.1.4 clean
  d1 pairing **+4.81%** (aggregate −13.31%) gains the label
  **conservative floor case (vk measured in a partial-cold state)** —
  its arithmetic and the no-flip conclusion stand unchanged; the
  warm-cache, boot-paired, same-day pairings are recorded as
  **+15.9%** (17.10 vs 14.76) and **+20.6%** (16.96 vs 14.06), labeled
  warm-cache ceiling context from a single warm session.

### Recommendation unchanged + practical guidance

- **Mapping unchanged:** vulkan stays an **available experimental
  opt-in, NOT recommended**; hip `WITH_MTP=1 SPEC_DEPTH=1` stays
  **default AND recommended**. Recorded rationale: single warm session;
  trigger unknown (users cannot be guaranteed to stay warm); the
  warm/cold swing is a user-facing UX risk (first boot after a cache
  clear: ~12.4 tok/s / ~12.5 s TTFT until warm).
- **Warmup guidance (one line, non-recomminding):** the quickstart's
  vulkan echo and [`docs/adaptation.md`](docs/adaptation.md) §Vulkan
  now say — if vulkan feels slow, first-run cache warmup is the first
  suspect; re-run before concluding. Boot logic and defaults are
  byte-identical.
- **Open question for the human owner:** "re-recommend vulkan?" is
  recorded as OPEN in the README roadmap with the warm/cold numbers —
  no recommendation language either way.
- **Surfaces updated:** the vulkan mtp-c1 ruling note
  (`configs/benchmark-verdicts.json`), the generated README blocks +
  [`docs/results/benchmark.md`](docs/results/benchmark.md) variance
  statements, [`docs/adaptation.md`](docs/adaptation.md) §Vulkan
  (root-cause paragraph + warm/cold table), and the stability README's
  session-4 disclosures (run-5 mclk-null snippet provenance: pre-final
  parser revision, value unaffected, receipt immutable; hip cross-boot
  spread corrected −4.8% → −4.7%). `CITATION.cff` 0.1.6. Tests: the
  "cause not recorded" pins replaced by the cache-state story; new test
  pinning the cold/warm/floor/ceiling arithmetic recomputed from the
  session-4 loader; the quickstart-mapping test still asserts vulkan
  NOT recommended.

## v0.1.5 — 2026-08-19

Docs-accuracy & reproducibility release: fixes from three independent
read-only audits of v0.1.4 (docs freshness, reproducibility walkthrough,
community value/UX). **No data changes**: the 28 cells, `matrix.json`,
`configs/benchmark-verdicts.json` (byte-identical), every verdict, and the
8/14/6 distribution are untouched; the corpus receipts are untouched. The
quickstart's default boot logic is byte-identical (a new `--help` exits
before any boot logic; wording-only echo changes).

### Cluster 1 — depth-1 truth made consistent and expressible

- **METHODOLOGY dated erratum (2026-08-19)**: the frozen contract's
  "mtp = speculative depth 1 (the 2026-08-17 cells)" id-grammar note and
  the Motivation paragraph's "HIP, MTP depth 1" label are corrected by
  erratum — the canonical hip mtp-c1 receipt (13.00 tok/s, started
  2026-08-16T22:30:54Z) ran the implicit `--spec-draft-n-max` default 3;
  the clean depth-explicit hip d1 measurement is 13.86 tok/s (session 3,
  2026-08-19; +6.61% vs 13.00 is day-confounded, labeled).
- **The recommended depth is now expressible from the docs**: README
  quickstart + boot table and
  [`docs/getting-started.md`](docs/getting-started.md) document
  `WITH_MTP=1 SPEC_DEPTH=1` as the recommended invocation; a bare
  `WITH_MTP=1` is labeled implicit-depth-3 (the 13.0 corpus cell). The
  quickstart echo gains a one-line `SPEC_DEPTH=1` hint; the generated
  benchmark mapping row and the README recommended-table row carry the
  re-run drift note (re-running the corpus hip mtp cell today pins
  depth 1 explicitly and measures ~13.86 —
  [`docs/results/matrix-714/stability/session3-2026-08-19/`](docs/results/matrix-714/stability/session3-2026-08-19/)).
- **"Depth 1 beats depth 4" now cites correctly-labeled numbers**
  (generated template + adaptation.md): vulkan 16.00 vs 15.05 tok/s
  (2026-08-18 corpus cells, explicit d1 vs d4); hip 13.86 (2026-08-19,
  explicit d1) vs 12.76 (2026-08-18, explicit d4) — the implicit-d3
  13.00 receipt is never again the depth-1 side. Date labels for the
  historical hip receipt unified to "2026-08-16 UTC (08-17 local)".

### Cluster 2 — Vulkan opt-in prerequisites documented

README opt-in, [`docs/adaptation.md`](docs/adaptation.md) §Vulkan, and a
NEW [`docs/troubleshooting.md`](docs/troubleshooting.md) `#vulkan-build`
section now state: the 5 apt packages (`mesa-vulkan-drivers`,
`vulkan-tools`, `libvulkan-dev`, `glslc`, `spirv-headers`); the no-root
`VULKAN_DEPS_PREFIX` fallback (used on the reference host:
`~/.local/share/qwen38-vulkan-deps` — `vulkaninfo` exists ONLY there);
and that the build fingerprint pins the Mesa point version, so a
Mesa/loader upgrade forces a deliberate `build-714-vk` rebuild (backend
identity is evidence).

### Cluster 3 — README recommended-table verdict collision resolved

The generated "Recommended — interactive chat" table now renders two
labeled layers: a **Cell verdict** column (the mechanical, corpus-backed
verdict) and a separate **Quickstart mapping** column — the vulkan row no
longer shows "✅ recommended" unqualified next to a NOT-recommended
mapping inside one cell (benchmark.md's mapping table is the model). Both
layers stay visible; the dated-supersession story is unchanged.

### Cluster 4 — stale 🚧 claims reconciled

[`docs/hardware-validation.md`](docs/hardware-validation.md) no longer
says W7900 is "🚧 Planned" (it is 🧪 community-validated — GGUF — since
v0.1.1); the README roadmap's "every 🚧 invitation stands" line (the
matrix renders zero 🚧 rows since the W7900D community row landed) now
names the actual open invitations: any AMD gfx arch via the protocol,
with the gfx1100 vLLM path as the open ask.

### Cluster 5 — broken links fixed

[`docs/results/upstream-controls/README.md`](docs/results/upstream-controls/README.md)
→ the canonical degraded-cell receipt renamed to the `-hip-` grammar in
v0.1.2; [`docs/results/community-explorations/w7900d-gfx1100/README.md`](docs/results/community-explorations/w7900d-gfx1100/README.md)
→ one-directory-short community-cells link.

### Cluster 6 — measured memory prerequisite stated

README prerequisites and getting-started now state the measured minimum
for the recommended path: ~26.5 GiB GTT at default ctx 131072 (26,548 MiB
at load; 29,270 MiB for the `WITH_MTP=1` boot — cell receipts
`load.gtt_mib`), with a one-line signal for 32 GiB-RAM owners (the GTT
pool depends on BIOS/allocation; expect pressure).

### Folded minors

`gguf-quickstart.sh --help` now prints usage (env knobs, recommended
invocation) and exits 0 BEFORE any boot logic — previously `--help`
booted the server; getting-started's MTP bullet aligned with the
"recommended path (`WITH_MTP=1 SPEC_DEPTH=1`)" framing; the results-index
verdict-provenance line adds the file-level 2026-08-19 review;
`CITATION.cff` 0.1.5. Tests updated/added accordingly (quickstart
`--help` non-boot + no-args boot-neutrality pins; recommended-table
two-layer columns; SPEC_DEPTH documentation pins).

## v0.1.4 — 2026-08-19

Evidence-integration release: the session-3 receipts (clean depth-1 backend
pairing + cross-day re-runs; receipts
[`docs/results/matrix-714/stability/session3-2026-08-19/`](docs/results/matrix-714/stability/session3-2026-08-19/))
**supersede the published recommendation basis** of 2026-08-18. The
`BACKEND=vulkan` quickstart guidance is downgraded from "RECOMMENDED
OPT-IN" to an **available experimental opt-in** (dated supersession, not a
silent rewrite — both rulings on record); **hip `WITH_MTP=1` is both the
default and the recommended path**. **No corpus data changed**: the 28
cells, `matrix.json`, every cell verdict, and the 8/14/6 distribution are
unchanged — mechanical verdicts from their own receipts stand; what
changed is the quickstart recommendation-mapping layer (the controller
ruling layer), the generated docs wording, and the tests that pin them.

### The clean-pairing finding (the v0.1.2 headline asterisk, resolved)

- **The 2026-08-18 promotion rested on a depth-confounded pairing.** Its
  headline (+23.1%: vulkan d1 16.00 vs hip 13.00 tok/s) compared
  explicit-depth-1 vulkan against the **implicit depth-3** hip receipt —
  the cross-depth caveat was recorded but the recommendation stood on the
  mixed-depth number.
- **The clean same-day d1/d1 pairing (2026-08-19, both backends explicit
  `--spec-draft-n-max 1`, same pin/model/prompts/harness)**: vulkan 14.53
  vs hip 13.86 tok/s = **+4.81%** single-stream median (gap +0.67) —
  one-fifth of the mixed-depth headline.
- **The aggregate basis flips**: hip 10.74 vs vulkan 9.31 tok/s =
  **−13.31%** (TTFT-driven — vulkan TTFT 9.94–12.21 s that session vs
  8.36–8.83 s across the 2026-08-18 sessions; hip TTFT 5.43 s vs 5.47 s
  on its 2026-08-16 receipt).

### The cross-day variance finding

The three vulkan c1 cells re-run on the next UTC day dropped on every
cell — mtp-c1 16.00/16.25→14.53 (−9.21%/−10.56%, max spread 11.81%),
mtp4-c1 15.05/15.25→11.67 (−22.49%/−23.49%, spread 30.70%), base-c1
10.65/10.91→10.29 (−3.35%/−5.72%, spread 6.07%) — while hip was
same-session stable (its d1 13.86 vs implicit-d3 13.00 = +6.61% is
**day-confounded** and labeled as such, never a depth claim). **The
host-level cause is NOT recorded**: the receipts carry VRAM/GTT only, no
clock/thermal telemetry — stated honestly, and noted as known harness
debt (future stability runs should capture clocks/thermals).

### Recommendation downgrade, dated supersession recorded

- **Mapping (ruling 2026-08-19, SUPERSEDES ruling 2026-08-18 — both
  dates visible in the generated note)**:
  [`scripts/gguf-quickstart.sh`](scripts/gguf-quickstart.sh) echo +
  header now present `BACKEND=vulkan` as an **available experimental
  opt-in, NOT recommended** (mechanism and "experimental, see
  verdicts/stability" framing kept); hip `WITH_MTP=1` is called out as
  both the default and the recommended path. Default boot logic is
  byte-identical — wording only.
- **No-flip closed decisively on the clean arithmetic**: +4.81% << the
  >25% pre-registered flip threshold (the mixed-depth +23.1% and the
  exactly-+25.0% session-2 headline the v0.1.3 note guarded are both
  superseded by the clean pairing; the arithmetic is recorded in the
  verdicts and pinned in the tests).
- **Unchanged and still stated**: the greedy-degradation pit still does
  NOT reproduce on vulkan — cell-run anchors 10/10 across s1/s2/s3
  (11/11 with the soak anchor); depth 1 beats depth 4 on both backends
  (no mtp4 recommendation anywhere).

### Surfaces regenerated / updated (no data change)

- [`scripts/gen-verdicts.py`](scripts/gen-verdicts.py): the
  stability-evidence loader extends to the session-3 receipts (same
  fail-loud convention) and the vulkan mtp-c1 ruling note is now the
  dated-supersession note (v0.1.4); the vulkan base-c1 note drops its
  "recommended opt-in" phrasing. Top-level `reviewed_by`/`checked_at` =
  `controller-2026-08-19` (the ruling of record for this file state);
  the 8 v0.1.2 cells keep their per-cell `controller-2026-08-18`
  mechanical-review records. Verdicts regenerated: 2 cell reasons
  changed, 28 cells, **8 recommended / 14 caution / 6 avoid — the same
  distribution**.
- [`scripts/render-readme-blocks.py`](scripts/render-readme-blocks.py):
  the ruling paragraph (benchmark.md), the performance-highlights label +
  honesty clause, and the known-good Vulkan bullet carry the downgraded
  story with the clean-pairing numbers (all interpolated from the same
  session-3-aware loader). README hand-written quickstart/roadmap updated
  to match.
- [`docs/adaptation.md`](docs/adaptation.md): Vulkan section re-based —
  clean pairing numbers, the 3-cell × spread cross-day table, the TTFT
  observation, the aggregate flip, the downgraded recommendation, and the
  honest "cause not recorded (no clock/thermal telemetry)" note (known
  harness debt).
- [`docs/results/matrix-714/stability/README.md`](docs/results/matrix-714/stability/README.md):
  one-line footnote on the s1 mtp4 cell (its stream finished at 238
  tokens / `finish_reason=stop` vs 256/`length` elsewhere — pre-existing,
  noted by the S4 verifier).
- [`CITATION.cff`](CITATION.cff): version 0.1.4.
- Tests: the quickstart echo pins, the ruling-note pins, and the
  recommendation-mapping test assert the downgraded mapping (hip =
  recommended path; vulkan = available experimental, not recommended),
  the no-flip clean arithmetic (+4.81% << 25%), and the supersession
  dates (2026-08-19 supersedes 2026-08-18).

## v0.1.3 — 2026-08-18

Stability-confirmation release for the v0.1.2 Vulkan opt-in ruling: a
second, independent measurement session and a 30-minute sustained-load soak
reproduce the promoted numbers, so the "single-session runtime" caveat is
upgraded to two-session + soak wording on every living surface.
**No configuration changed** — the quickstart default stays `hip`,
`BACKEND=vulkan WITH_MTP=1` stays the recommended opt-in at unchanged
strength. Receipts:
[`docs/results/matrix-714/stability/`](docs/results/matrix-714/stability/)
(receipts-only; the 28-cell matrix and `matrix.json` are untouched).

### Stability confirmation (v0.1.2 → session 2, same day, hours apart)

- **Every Vulkan c1 cell reproduced** by an independent session (independent
  server boots, same host/model/prompts/harness): mtp-c1 16.00→16.25 tok/s
  (+1.5%), mtp4-c1 15.05→15.25 (+1.3%), base-c1 10.65→10.91 (+2.5%) —
  session 2 uniformly slightly faster, consistent with a warmer machine;
  anchors 7/7 across all runs.
- **30-min sustained soak** on the recommended config (one boot,
  runner-identical flags): 108/108 cycles clean, zero health flaps, mild
  settle (stream-rate halves 16.43→16.00 tok/s, -2.6%; aggregate halves
  -2.8%), clean post-soak greedy anchor — sustained load shows no
  progressive degradation.
- **No default flip — the arithmetic, recorded so +25.0% is never misread
  as a trigger**: the session-2 headline (16.25 vs hip 13.00 tok/s) is
  **exactly +25.0%**, and the pre-registered flip rule requires **>25% AND
  stability** — exactly +25.0% is not >25% — and the headline is still
  mixed-depth (the hip receipt ran implicit depth 3; the clean same-depth
  d4 pairing on session-2 numbers is 15.25 vs 12.76 tok/s, +19.5%).
- **Remaining limits, unchanged and still stated**: single host (gfx1151),
  single ICD (RADV, Mesa 25.2.8), same-day sessions, boot-per-cell — the
  soak covers sustained load only.

### Wording upgrades (no behavior change)

- [`scripts/gen-verdicts.py`](scripts/gen-verdicts.py) v0.1.2 ruling note:
  "single-session Vulkan runtime" → the two-session + soak wording with the
  evidence pointer and the no-flip arithmetic (numbers interpolate from the
  session-2/soak receipts, same never-drift convention as the cells).
  Verdicts, README blocks, and
  [`docs/results/benchmark.md`](docs/results/benchmark.md) regenerated;
  no verdict, metric, or cell changed.
- [`scripts/gguf-quickstart.sh`](scripts/gguf-quickstart.sh) echo: the
  "Experimental: single-session runtime, one ICD" note → two-session +
  soak phrasing, with the remaining limits kept (single host/ICD); the
  default boot is byte-identical (`BACKEND` default `hip`).
- [`docs/adaptation.md`](docs/adaptation.md): stability paragraph added to
  the Vulkan section (session-2 deltas, soak stats, remaining limits).
- [`docs/results/matrix-714/stability/README.md`](docs/results/matrix-714/stability/README.md):
  session-2 index timestamp corrected to the receipt-derived span
  (11:28:12Z–12:01:21Z), and the session-1 column aligned to the corpus
  2dp convention (mtp-c1 16.01 → 16.00, delta +0.24 → +0.25) so the
  v0.1.2-canonical and session-2 numbers cross-reference cleanly.
- [`CITATION.cff`](CITATION.cff): version 0.1.3 (matrix description
  unchanged — still the 28-cell corpus).

### Fixes (post-release debt batch — script/tests/docs only, no data change)

- Precision: the "+18.0%" hand literal on the same-depth depth-4 pairing
  (exact receipts math is +17.9%) is now interpolated from the same verdict
  metrics the ruling note uses, in both places it appeared
  ([`scripts/render-readme-blocks.py`](scripts/render-readme-blocks.py);
  [`docs/results/benchmark.md`](docs/results/benchmark.md) regenerated).
- The quickstart's `BACKEND=vulkan` echo now labels its "16.0 vs 13.0
  tok/s" pairing as mixed-depth inline, pointing at the same-depth +19.5%
  in the verdicts (the caveat previously lived one hop away).
- The benchmark.md vLLM table's empty Backend cells now render as "—",
  matching the MTP-effect table convention (renderer fix, regenerated).
- The cross-depth caveat states the date convention once: receipt
  timestamps are UTC, caveat dates before v0.1.2 use local (UTC+8)
  ([`scripts/gen-verdicts.py`](scripts/gen-verdicts.py); verdicts
  regenerated).
- The cell runner's own c4-only `-unified` enforcement is now pinned by a
  test that exercises it directly (a declared, grammatically c1-unified id
  via a scratch `MATRIX_FILE`) instead of riding the matrix "not declared"
  refusal ([`tests/test_cell_runner.py`](tests/test_cell_runner.py)).
- The quickstart's `SPEC_DEPTH` validation gained an automated refusal test
  (non-numeric and <1 values, run CI-safe against a stub server and scratch
  model — the values the script actually refuses)
  ([`tests/test_gguf_quickstart_ux.py`](tests/test_gguf_quickstart_ux.py)).
- The v0.1.2 summary-table header said "Cell (c1 @ctx131072)" while its
  last row covers c4 cells — corrected to "Cell @ctx131072" (controller
  factual-labeling fix; DATA untouched, this note records the correction).
- Stability README (S2 verifier minors): the stale "integrating these
  numbers is a later step (S2)" line is now a done-statement, and the Δ
  columns are exact-basis (recomputed from the receipts, 2dp display) so
  each Δ matches its pct column.
- Soak script telemetry (script-only; existing receipts never rewritten):
  `llama_server_version` verified to resolve from the stderr banner
  (both streams captured — CI-safe source contract added), and a
  `health_flaps` counter added to the receipt totals (0 in normal runs),
  both documented in the script header and pinned in
  [`tests/test_stability_soak.py`](tests/test_stability_soak.py).

## v0.1.2 — 2026-08-18

The Vulkan×MTP-depth comparison release: 8 new measured cells on the same
host, model, prompts, and harness answer the roadmap question "what do the
Vulkan backend and MTP depth >1 each contribute?" — plus the
unified-default-boot c4@131072 rider that closes the v0.1.0 bracketing gap.
Plan:
[`docs/superpowers/plans/2026-08-18-vulkan-mtp-comparison.md`](docs/superpowers/plans/2026-08-18-vulkan-mtp-comparison.md);
adaptation facts: [`docs/adaptation.md`](docs/adaptation.md).

### Highlights

- **Vulkan backend measured for the first time** — same llama.cpp pin
  `4df29be4`, separate build `build-714-vk` (`-DGGML_VULKAN=ON
  -DGGML_HIP=OFF`), Mesa RADV ICD (`RADV GFX1151`, Mesa 25.2.8 — no
  `VK_ICD_FILENAMES` forcing; identity recorded in
  [`configs/validated-stack.json`](configs/validated-stack.json)). 6 vulkan
  cells ({base, mtp, mtp4} × c{1,4} @ctx131072) + 2 hip cells (mtp4 c1
  with explicit `--spec-draft-n-max 4`, and the unified-default-boot c4
  rider). Raw receipts:
  [`docs/results/matrix-714/cells/`](docs/results/matrix-714/cells/).
- **`BACKEND=vulkan` is now the recommended quickstart opt-in for best
  single-stream tok/s** — vulkan `WITH_MTP=1` mtp-c1 measures **16.0 tok/s**
  per-stream median vs 13.0 on hip (+23% headline). Project ruling
  2026-08-18 (plan outcome (a), pre-registered rule: ≥15% win AND
  anchor-clean); the quickstart **default stays hip** (headline <25%,
  single-session Vulkan runtime, one ICD) and the "experimental, see
  verdicts" label is kept. Ruling recorded per cell in
  [`configs/benchmark-verdicts.json`](configs/benchmark-verdicts.json)
  (`metrics.reviewed_by` = `controller-2026-08-18`); CI-enforced
  ([`tests/test_verdicts.py`](tests/test_verdicts.py)).
- **Cross-depth caveat, stated everywhere the +23% appears** — the hip
  13.0 receipt (2026-08-17) ran the implicit `--spec-draft-n-max` default
  3; every v0.1.2 cell passes its depth explicitly. The clean same-depth
  cross-backend pairing is depth 4: vulkan mtp4 **15.05 vs hip mtp4 12.76
  tok/s (+18%)**.
- **MTP depth 1 beats depth 4 on both backends** — vulkan 16.00 vs 15.05,
  hip 13.00 vs 12.76 tok/s at c1: `WITH_MTP=1` at depth 1 stays the
  recommended variant; no mtp4 recommendation. Depth is configurable at
  the pin (`--spec-draft-n-max`, upstream default 3), not fixed by the
  checkpoint.
- **The greedy-degradation pit does NOT reproduce on Vulkan** — 6/6 vulkan
  cells anchor-clean (any measured depth and concurrency); hip mtp4-c1
  anchored clean the same day. The pit stays a hip-family (gfx1151/HIP)
  finding at this pin (5 avoid cells unchanged).
- **Unified-default-boot c4@131072 measured (rider) — degrades
  interactivity** — the stock quickstart's 4-slot unified default boot
  under 4 concurrent users: 6.7 tok/s healthy-stream median vs 7.5 for
  split-mode (`-np 4`); aggregate 5.0 vs 9.4 tok/s (3-of-4 streams stopped
  within 8 tokens — early EOS, aggregate not comparable).
  Measured-with-caveat, no config change; single-stream use unaffected.
  This closes the v0.1.0/v0.1.1 bracketing gap.

### Benchmark matrix

**28 measured cells: 8 recommended / 14 caution / 6 avoid** (20 planned —
time-boxed session, machinery complete; 8 dropped — vLLM ctx-32768 tier not
offered). Verdicts for the 8 new cells are the MECHANICAL ladder results,
confirmed by the controller-2026-08-18 review (zero overrides —
`controller_override` null on all 8; the quickstart ruling recorded in each
reason). Full tables:
[`docs/results/benchmark.md`](docs/results/benchmark.md).

| Cell @ctx131072 | Backend | Per-stream med | Verdict |
|---|---|---|---|
| `gguf-vulkan-…-mtp-c1` (depth 1) | vulkan | **16.0 tok/s** (+50.2% vs vulkan base) | ✅ recommended — quickstart opt-in |
| `gguf-vulkan-…-mtp4-c1` (depth 4) | vulkan | 15.05 tok/s (+41.3% vs base) | ✅ recommended |
| `gguf-hip-…-mtp4-c1` (depth 4) | hip | 12.76 tok/s (+25.8% vs base) | ✅ recommended |
| `gguf-vulkan-…-base-c1` | vulkan | 10.65 tok/s | ✅ recommended |
| c4 cells (all 4 new) | both | 6.1–6.7 tok/s median (below the floor; unified-boot aggregate 5.0) | ⚠️ caution — batch only |

At c4 on Vulkan, MTP is a REGRESSION vs the base counterpart (mtp −7.5%,
mtp4 −13.0% aggregate) — the c1 payoff inverts under concurrency on this
backend too (basis labeled in the verdicts).

### Verdict-system fixes

Two prose-template defects (disclosed by the independent verifier, frozen
RULES unchanged — only factually wrong wording fixed):

- The c4-caution MTP sentence now follows the actual numbers and basis
  (previously it hardcoded "Better than base c4 (...)" even when the cell
  was LOWER and labeled a c4-basis number "c1:").
- The "c8/c16 hit the anchor-degradation pit (avoid cells)" clause no
  longer leaks into vulkan conditions (no vulkan c8/c16 cells exist; that
  pit history is hip-family) — it now derives from the backend's own
  measured pit cells.
- Stale "all measured cells are hip" / "unified c4 was not measured" /
  single-reviewer attribution in the generated docs replaced with
  data-derived statements (per-family review attribution: 20 cells
  `controller-2026-08-17` frozen + 8 cells `controller-2026-08-18`).

### Housekeeping

- **Cell-id migration note** — legacy gguf ids without a backend tag are
  `hip` (historical v0.1.0/v0.1.1 entries stay interpretable under that
  rule).
- [`CITATION.cff`](CITATION.cff) description updated to the 28-cell,
  dual-backend matrix (version stays 0.1.2).
- New adaptation-map section "Vulkan backend × MTP depth (v0.1.2)":
  build facts, ICD identity, perf deltas with the cross-depth caveat, pit
  status, quickstart opt-in status, unified rider finding
  ([`docs/adaptation.md`](docs/adaptation.md)).

## v0.1.1 — 2026-08-18

- **Community hardware validation landed**
  ([PR #1](https://github.com/AIwork4me/Qwen3.8-27B-ROCm/pull/1)) — AMD
  Radeon Pro W7900D (`gfx1100`, 48 GiB discrete, ROCm 7.2.1 runtime): the
  first protocol submission. 7/7 healthy GGUF cells via the project runner
  (28/28 bench streams + 7/7 greedy anchors across the 7 cells
  (1+1+16+4+1+4+1 streams)), matched-context MTP pair 31.1 vs 24.7
  aggregate tok/s (+26.2% @ctx131072); the greedy-degradation pit NOT
  reproduced on discrete `gfx1100` (cross-architecture data point
  consistent with the `prop.integrated` hypothesis). Receipts:
  [`docs/results/matrix-714/community/w7900d-gfx1100-rocm721/`](docs/results/matrix-714/community/w7900d-gfx1100-rocm721/),
  [README hardware-matrix row](README.md#hardware-support).
- **Upstream engagement** — differential test of llama.cpp
  [PR #25863](https://github.com/ggml-org/llama.cpp/pull/25863) (fix for
  [#25992](https://github.com/ggml-org/llama.cpp/issues/25992)) reported by
  the owner in
  [#25992](https://github.com/ggml-org/llama.cpp/issues/25992#issuecomment-5321885979)
  (permalink comment id 5321885979, recorded in
  [`docs/upstream/llama-cpp-hip-greedy-degradation.md` § Reported](docs/upstream/llama-cpp-hip-greedy-degradation.md#reported));
  gfx1100 non-repro owner-action brief added
  ([`docs/upstream/llama-cpp-25992-w7900d-nonrepro.md`](docs/upstream/llama-cpp-25992-w7900d-nonrepro.md)).
- **Protocol** — community-profile kernel-floor relaxation (warn not fail;
  base profile unchanged, regression-tested); policy note recorded in the
  [PR #1 review](https://github.com/AIwork4me/Qwen3.8-27B-ROCm/pull/1).
- **Housekeeping** — CITATION repository URLs
  ([`CITATION.cff`](CITATION.cff)), repo topics
  ([repository](https://github.com/AIwork4me/Qwen3.8-27B-ROCm)), upstream
  permalink recorded
  ([§ Reported](docs/upstream/llama-cpp-hip-greedy-degradation.md#reported)).

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
