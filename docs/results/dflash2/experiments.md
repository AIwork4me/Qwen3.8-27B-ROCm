# DFlash 2 experiments & findings — gfx1100, 2026-08-21

Working notes for the dflash2 phase. Negative results are results; every
claim links to its receipt.

## F1 — The win is real but host-bound (+13% c1 / +23% c4, not 1.8–3.4×)

Vendor numbers (H200/SGLang 2.7–3.4× at c1; M5 Pro/llama.cpp 1.81–1.85×;
[`model card`](https://huggingface.co/incoai/Qwen3.8-27B-DFlash2)) do not
transfer to W7900/gfx1100. Clean-paired measurement (same PR build both
arms): 29.4 → 33.2 tok/s at c1 (+12.9%), 17.3 → 21.4 tok/s median at c4
(+23.4%). Receipts: `cells/gguf-hip-udq4kxl-auto-{base,dflash2}-c{1,4}-ctx131072.json`.

Two compounding causes, both measured or derivable:

1. **Acceptance 0.36** on this bench (server log: `draft acceptance =
   0.36255 (182 accepted / 502 generated), mean len = 3.53`) — versus the
   vendor's ≈ 5/7 on GSM8K-class reasoning prompts. The project bench is
   8 generic professional prompts at temperature 0.7; vendor evals use
   the model's recommended sampling (temperature 1.0, top-p 0.95, top-k
   20) on reasoning-heavy tasks where a drafter trained on those
   distributions accepts more.
2. **Verification is not free on a compute-limited card**: at ~3.5
   accepted tokens per step the target runs batch-8 forwards; gfx1100
   (~61 TFLOPs class, bandwidth 864 GB/s) gains less per weight-pass
   than an H200 before the drafter's own per-step cost (dynamic conv +
   selector) is subtracted.

Follow-up candidates (NOT measured this phase, deliberately — the corpus
bench must stay comparable): a temperature-1.0/top-k-20 acceptance probe
to separate cause 1 from cause 2; a Q4_K_M-draft cell (vendor says
quant-invariant, table in the PR).

## F2 — DFlash 2 is lossless on-host: greedy byte-identity 4/4 PASS

`equiv.json`: baseline vs DFlash2 boots (same binary), greedy,
thinking-off, 4 prompt surfaces (arithmetic / code / factual / exact
instruction) — content byte-identical, token counts identical, all
finish `stop`. The model-card claim is verified, not just repeated.

## F3 — MTP depth-1 beats DFlash 2 on THIS host at c1

Same clean pairing: `mtp-c1` 41.3 tok/s (+40.5% vs base) vs DFlash2 33.2
(+12.9%). MTP-d1 verifies 2 tokens per step (batch 2) with no external
model; its acceptance/cost ratio suits a compute-limited card better
than an 8-token block drafter. **The single-stream recommendation for
this host class therefore stays MTP d1**; DFlash2's case is c4
concurrency (+23.4%, where MTP-d1 was not re-measured this phase — see
the project corpus for MTP concurrency behavior) and
acceptance-friendly/bandwidth-rich workloads. Receipt:
`cells/gguf-hip-udq4kxl-auto-mtp-c1-ctx131072.json`.

## F4 — The DFlash v1 `-np 16` hang does NOT reproduce on v2

Muse-Glimmer recorded a pathological DFlash v1 + `-np 16` cell (aborted
after 5 h 16 m; reported upstream as ggml-org/llama.cpp#27117). The v2
probe at this scale — c16 split-KV, ctx 32768, time-boxed at 360 s —
**completed in 93 s, 16/16 streams OK, 43.1 tok/s aggregate**
(per-stream median 13.9, spread 8.4–25.0; TTFT median 40.5 s — poor QoS
but not pathological). Receipt:
`cells/gguf-hip-udq4kxl-auto-dflash2-c16-ctx32768.json`. Scope: one
prompt-round at 256 tokens; this retires the "hang" fear at v2's default
scale, not a general c16 endorsement (serve c ≤ 4 with DFlash2).

## F5 — Toolchain deltas recorded honestly

- The PR build compiled cleanly against **ROCm 7.2.1** (the community
  stack used a 7.14 gfx1100 toolchain, lost to the host rebuild);
  serving and compiling are both 7.2.1 here — recorded in
  `serving-receipt.md`, not hidden.
- One benign load-time warning:
  `[spec] failed to measure draft model memory: failed to create
  llama_context from model` — the draft loads and runs anyway
  (`common_speculative_init_result: loading draft model ...` follows
  immediately). Not measured as an impact; noted so nobody panics.
- Build-script lesson folded in at the source: `rocminfo` lists
  `gfx11-generic` alongside `gfx1100`; matching exactly four digits is
  what keeps `--offload-arch=gfx11` ("unsupported HIP gpu
  architecture") out of the configure step (`07-build-llama-dflash2.sh`,
  pinned by `tests/test_dflash2.py`).

## F6 — Environment gotchas hit during the phase (for the record)

- Each long-lived driver process on this host runs inside a
  per-invocation sandbox: cross-shell localhost probes cannot reach a
  server started by another invocation (diagnosed with a live orphan
  server; `ss -ltnp` shows nothing from a sibling shell). The cell
  runner and the equiv script keep boot + client in one invocation by
  construction — that is the supported shape here.
- An `llama-server` wedged mid-teardown (SIGTERM ×2, holding ~27 GiB
  VRAM) can outlive its wrapper; the equiv script now escalates to
  SIGKILL after a 60 s grace (observed once, receipt: WARN line in the
  first equiv attempt's log).
