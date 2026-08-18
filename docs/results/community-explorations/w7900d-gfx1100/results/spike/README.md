# Spike receipts

Upstream-support reconnaissance for Qwen3.8-27B (`Qwen3_5ForConditionalGeneration`)
on Radeon W7900 (`gfx1100`). Each probe's command and raw evidence lives in
the linked file; conclusions feed `configs/spike-findings.json` and the
decision table.

- `rocm-w7900.md` — ROCm 7.14.0 availability + local prefix verification on W7900 (Spike R)
- `vllm.md` — vLLM + transformers support for qwen3_5 (Spike A)
- `gguf.md` — llama.cpp / GGUF support and existing quants (Spike B)
- `quant-kv.md` — official quantizations + KV-cache dtype levers on gfx1100 (Spike C)

Method: probe at a recorded commit/date; quote the exact evidence; absence
of evidence is recorded as absence, never assumed away. huggingface.co is
unreachable from this host — every HF probe records its HTTP code.
