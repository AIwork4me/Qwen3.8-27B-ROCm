# Upstream control experiments — the greedy-degradation pit vs master HEAD (2026-08-18)

Decisive controls for the pit documented at
[`../../troubleshooting.md#greedy-degradation`](../../troubleshooting.md#greedy-degradation)
and [`../METHODOLOGY.md` §6](../METHODOLOGY.md): does it still exist at
current upstream master, and does open PR
[ggml-org/llama.cpp#25863](https://github.com/ggml-org/llama.cpp/pull/25863)
("ggml-cuda: avoid direct ROCm_Host compute on HIP integrated GPUs") change
it? Every verdict below is backed by the verbatim greedy-anchor
`content_tail` committed in the receipt JSON named in the last column.

## Verdicts

| Exp | Build | mmproj | Greedy anchor after 8-stream bench | Verdict | Receipt |
|---|---|---|---|---|---|
| E0 | build-714 @ `4df29be4` (the pin, no rebuild) | on | `anchor_ok: false`, tail `"////////////////"` | **pit reproduced** (reference) | [`e0-build714-4df29be4.json`](e0-build714-4df29be4.json) |
| E1 | master HEAD `01818e495` (2026-08-17, fresh clone + HIP build) | on | `anchor_ok: false`, tail `"////////////////"` | **pit still present at master** | [`e1-master-01818e49.json`](e1-master-01818e49.json) |
| E2 | master HEAD `01818e495` + PR #25863 patch (head `ce82541a`, +25/−2 in `ggml-cuda.cu`) | on | `anchor_ok: true`, tail `"OK"` — **2/2 runs** | **pit absent with the PR applied** | [`e2-master-pr25863.json`](e2-master-pr25863.json) |
| E3 | master HEAD `01818e495` (same as E1, patch reverted) | **off** | `anchor_ok: false`, tail `"////////////////"` | **pit reproduces without mmproj** | [`e3-master-nommproj.json`](e3-master-nommproj.json) |

## Method (byte-identical sequence across E0–E3)

Minimal repro derived from [`../METHODOLOGY.md` §6](../METHODOLOGY.md) and
the canonical degraded cell
[`../matrix-714/cells/gguf-udq4kxl-auto-base-c8-ctx131072.json`](../matrix-714/cells/gguf-udq4kxl-auto-base-c8-ctx131072.json):

1. boot `scripts/gguf-quickstart.sh` with `CTX_SIZE=131072 WITH_MTP=0
   EXTRA_ARGS="-np 8"` (E3 adds `WITH_MMPROJ=0`; E1–E3 point
   `LLAMA_SERVER` at `/tmp/lc-master/build/bin/llama-server`), health-polled;
2. `scripts/bench_client.py --concurrency 8 --max-tokens 256 --no-thinking`
   (sustained load, the same 8-prompt set);
3. `scripts/bench_client.py --anchor-only` (greedy, temperature 0, cap 16
   tokens, prompt `Reply with exactly: OK`); the gate is the JSON's
   `anchor_ok` field, never the client exit code — exactly the cell runner's
   rule.

Every E1–E3 boot logged the same slot semantics as the canonical cell
(`n_slots = 8, n_ctx_slot = 16384, kv_unified = 'false'`). The E1 build used
flags identical to `scripts/05-build-llama.sh`
(`GGML_HIP=ON`, `AMDGPU_TARGETS=gfx1151`, `ROCM_PATH=~/rocm-7.14.0`,
`Release`) in a separate clone at `/tmp/lc-master`; the pinned checkout
`third_party/llama.cpp` was never touched and still builds from `4df29be4`.

## Findings (stated as measured, mechanism not claimed beyond the data)

- **The pit is NOT fixed at master HEAD.** E1 failed the anchor with the
  same `"////////////////"` tail and the same all-capped bench shape
  (8/8 streams at the 256-token cap) as the five degraded matrix cells.
- **PR #25863 applied on top of master HEAD removed it in 2/2 runs**
  (anchors `"OK"`), under near-identical load (7/8 streams capped, one
  early stop each run — the bench shape of the degraded `mtp-c8` cell).
  The PR is OPEN, not merged, at the E1 master HEAD. What the data shows is
  the differential: identical host, model, flags and load, patch on vs off;
  the PR's own description names direct ROCm_Host compute on HIP integrated
  GPUs, which is consistent with the observed fix, but the mechanism inside
  llama.cpp is not further analyzed here.
- **mmproj is not the trigger.** E3 boots the E1 build (patch reverted,
  tree verified clean) without `--mmproj` and still fails the anchor with
  the slash tail — closing the attribution gap that all committed matrix
  evidence ran with the vision projector attached. This matches the §6 note
  that the pit reproduced "with and without mmproj" at the pin.
- **Reproducibility caveat (recorded, not smoothed over):** the pit is not
  single-attempt deterministic on a loaded host. E0 attempt 1 — run while a
  16-job HIP compile saturated the CPU — passed the anchor with 2 of 8
  streams early-stopping; E0 attempt 2 on the idle host reproduced the pit
  exactly (all-capped, slash tail). All FAIL verdicts above are idle-host
  runs; the E2 PASSes are also idle-host runs. Sample sizes are small
  (unpatched 3/3 FAIL on the idle host — E0 attempt 2, E1, E3, across two
  upstream commits; patched 2/2 PASS); the receipts carry per-attempt bench
  shapes so a reader can weigh them.

## Relation to the existing record

These experiments CHANGE nothing in the committed matrix or verdicts: the
`avoid` grades for the five degraded cells stand as measured at the pin
(`4df29be4`). They are the backbone of the upstream evidence pack +
owner-action brief
([`../../upstream/llama-cpp-hip-greedy-degradation.md`](../../upstream/llama-cpp-hip-greedy-degradation.md)):
the pit persists at master HEAD `01818e495` (2026-08-17) and is a candidate
differential for PR #25863, which was open at that HEAD.
