# llama.cpp #25992 — discrete gfx1100 (W7900D) non-reproduction, evidence pack + owner-action brief

Same rules as [llama-cpp-hip-greedy-degradation.md](llama-cpp-hip-greedy-degradation.md):
llama.cpp's [AI usage policy](https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md#ai-usage-policy)
**prohibits AI-written posts** ("It is strictly prohibited to use AI to write
your posts for you" — bug reports, comments, replies; disclosure is not an
exemption). The upstream note must be the owner's own writing. This document
is what the repo owes the owner instead: committed evidence, public links,
facts-only source notes, and reproduction commands. No ready-to-paste comment
is provided here on purpose.

**Status (2026-08-18).** PR #1 review comment (2026-08-18T01:48:36Z) invited
a first-person note on
[ggml-org/llama.cpp#25992](https://github.com/ggml-org/llama.cpp/issues/25992):
the community W7900D batch is a clean non-reproduction of the greedy pit on a
**discrete** RDNA3 board, which is directly relevant to the maintainers
fixing #25992 via
[#25863](https://github.com/ggml-org/llama.cpp/pull/25863)
("ggml-cuda: avoid direct ROCm_Host compute on HIP **integrated** GPUs") —
the failing path is the `prop.integrated` host-buffer route, which only
activates on integrated GPUs.

## The one-line datum

The exact llama.cpp commit whose gfx1151 (integrated) builds fail the greedy
anchor after sustained multi-stream load (E0: `4df29be4`, FAIL with a
`"////"` tail; see
[llama-cpp-hip-greedy-degradation.md](llama-cpp-hip-greedy-degradation.md))
ran **7/7 clean greedy anchors on 7 fresh server instances** on a discrete
W7900D (`gfx1100`) — including the two instances that took the pit's trigger
shape: a sustained multi-stream bench immediately followed by a greedy
request on the same instance.

## Host / stack (all 7 cells)

- AMD Radeon Pro W7900D (`gfx1100`, 48 GiB discrete GDDR6; rocm-smi total
  51522830336 B), host AMD EPYC 9334, kernel `6.8.0-79-generic`.
- llama.cpp `4df29be4f4c3673f428170fda944a5b19f743bb8` (identical to the
  project pin and to control E0), HIP build:
  `cmake -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100` (`GGML_HIP_GRAPHS=ON`,
  `GGML_HIP_NO_VMM=ON`), toolchain ROCm 7.14.0 hipcc, serving runtime ROCm
  7.2.1 (`/opt/rocm`). Full detail:
  [`stack-manifest.md`](../results/matrix-714/community/w7900d-gfx1100-rocm721/stack-manifest.md).
- Model `Qwen3.8-27B-UD-Q4_K_XL.gguf` (unsloth @ `c882514e`, sha256
  `bee238bb…b1372`, 16.69 GiB) with `mmproj-F16.gguf` attached — same
  artifacts as the gfx1151 controls.
- Server: this repo's `scripts/gguf-quickstart.sh` (flags
  `--ctx-size N -ngl 99 --jinja` + `-np N` for the split-KV cells).

## Cell ledger (raw cell JSONs, runner-written, unedited)

Every cell = one fresh `llama-server` instance: boot → N-stream bench
(temperature 0.7, 256-token generations, project prompt set) → **greedy
anchor on the same instance** (`bench_client.py --anchor-only`: concurrency
1, temperature 0, `expect_exact` substring gate).

| cell | n_slots / n_ctx_slot / kv_unified | streams ok | greedy anchor |
|---|---|---|---|
| base-c1-ctx32768 | 4 / 32768 / true | 1/1 | PASS, tail `"OK"` |
| base-c1-ctx131072 | 4 / 131072 / true | 1/1 | PASS, tail `"OK"` |
| base-c1-ctx262144 | 4 / 262144 / true | 1/1 | PASS, tail `"OK"` |
| base-c4-ctx131072 | 4 / 32768 / **false** (split, `-np 4`) | 4/4 | **PASS, tail `"OK"`** |
| base-c16-ctx131072 | 16 / 8192 / **false** (split, `-np 16`) | 16/16 | **PASS, tail `"OK"`** |
| mtp-c1-ctx131072 (`--spec-type draft-mtp`) | 4 / 131072 / true | 1/1 | PASS, tail `"OK"` |
| mtp-c4-ctx131072 (`--spec-type draft-mtp`) | 4 / 32768 / false | 4/4 | PASS, tail `"OK"` |

The c4 and c16 rows are the trigger shape (sustained multi-stream → greedy
on the same instance, split-KV mode as in the gfx1151 controls' `-np 8`);
both anchors were byte-clean. Zero `'////'`-family tails in any of the 7
`anchor.content_tail` fields.

## Public receipt URLs (resolve once PR #1 is merged; branch links live now)

- Cell ledger + anchors:
  <https://github.com/AIwork4me/Qwen3.8-27B-ROCm/tree/community/w7900-gfx1100-rocm721/docs/results/matrix-714/community/w7900d-gfx1100-rocm721/cells>
- The two trigger-shape cells:
  [base-c4-ctx131072.json](https://github.com/AIwork4me/Qwen3.8-27B-ROCm/blob/main/docs/results/matrix-714/community/w7900d-gfx1100-rocm721/cells/gguf-udq4kxl-auto-base-c4-ctx131072.json),
  [base-c16-ctx131072.json](https://github.com/AIwork4me/Qwen3.8-27B-ROCm/blob/main/docs/results/matrix-714/community/w7900d-gfx1100-rocm721/cells/gguf-udq4kxl-auto-base-c16-ctx131072.json)
- Submission PR (reviewer criteria, receipts tree):
  <https://github.com/AIwork4me/Qwen3.8-27B-ROCm/pull/1>

## Reproduction (any discrete gfx1100 board)

With this repo (cells exactly as committed):

```bash
git clone https://github.com/AIwork4me/Qwen3.8-27B-ROCm && cd Qwen3.8-27B-ROCm
SET=gguf bash scripts/02-fetch-model.sh          # hash-verified UD-Q4_K_XL
export LLAMA_SERVER=/path/to/build/bin/llama-server   # 4df29be4, HIP/gfx1100
export CELLS_DIR=/tmp/my-cells
bash scripts/run-cell-gguf.sh gguf-udq4kxl-auto-base-c16-ctx131072   # bench → same-instance greedy anchor
cat /tmp/my-cells/gguf-udq4kxl-auto-base-c16-ctx131072.json | jq '.anchor'
```

Without this repo's tooling (the minimal manual shape):

```bash
llama-server -m Qwen3.8-27B-UD-Q4_K_XL.gguf --port 8080 -ngl 99 \
             --ctx-size 131072 --jinja -np 8
# 1) sustained load: 8 concurrent /v1/chat/completions streams,
#    ~1-1.5K prompt tokens each, max_tokens 256
# 2) immediately after, SAME instance (temperature 0):
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply with exactly: OK"}],"temperature":0,"max_tokens":512}'
# clean (W7900D, all 7 instances): completion contains "OK"
# gfx1151 pit (E0/E1/E3): completion degenerates to "////" tail
```

## Recommended owner action

Comment on #25992 in the owner's own words: same commit `4df29be4` that
fails on integrated gfx1151 is clean on discrete gfx1100 across 7 instances
and both KV modes, including the bench→greedy trigger shape — consistent
with #25863's integrated-only `prop.integrated` scoping. Link the two
trigger-shape cell JSONs above. Do not file a new issue (duplicate policy).
