# Spike receipts

Upstream-support reconnaissance for Qwen3.8-27B (`Qwen3_5ForConditionalGeneration`).
Each probe's command and raw evidence lives in the linked file; conclusions
feed `configs/spike-findings.json` and the decision table.

- `vllm.md` — vLLM + transformers support for qwen3_5 (Spike A)
- `gguf.md` — llama.cpp / GGUF support and existing quants (Spike B)
- `quant-kv.md` — official quantizations + KV-cache dtype levers on gfx1151 (Spike C)

Method: probe at a recorded commit/date; quote the exact evidence; absence
of evidence is recorded as absence, never assumed away.
