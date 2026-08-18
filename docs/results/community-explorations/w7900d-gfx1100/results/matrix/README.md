# Phase 3 benchmark matrix cells

One JSON per cell (schema `schemas/bench-cell.schema.json`); SHA256SUMS
covers them all. Runner: `bash scripts/06-run-matrix.sh` (resumable).
Cells: {Q4_K_M,Q6_K,Q8_0} x c={1,4,16,32} + MTP (draft-mtp, 512-tok gens)
+ KV q8_0 on Q8_0. Failure cells carry their server-log tail in
identity.fail_log_tail. Parameters: temp 0, ctx 32768 total, 5 reps,
configs/bench-prompt.txt.

Also cell-vllm-c{1,4,16}.json: the FP8-unlock contingent cells (Task 6),
run manually per the probe's pattern against a vLLM 0.27.1+rocm723 server on
:8199 (enforce-eager, dual served names) — same driver/params/prompt; see
../spike/fp8-unlock.md for the one-time JIT-warmup caveat and c4/c16
--timeout 3600 disclosure.
