# llama.cpp GGUF validation receipts — 2026-08-16T20:58Z
## Boot (baseline, ctx 131072, mmproj attached)
- server: http://127.0.0.1:8080
- health: ok
- boot wall time: 5s (measured nohup -> first healthy /health poll)
- flags: --ctx-size 131072 -ngl 99 --jinja (env: CTX_SIZE=131072)
- blk.64.nextn.* (MTP block): 4 tensors reported unused (skipped — expected without draft-mtp)
- post-boot memory: VRAM used 1135 MiB, GTT used 26550 MiB
Log evidence (`/tmp/llama-serve.log`):
    0.00.906.283 W model has unused tensor blk.64.attn_k.weight (size = 3604480 bytes) -- ignoring
    0.00.906.284 W model has unused tensor blk.64.attn_v.weight (size = 4300800 bytes) -- ignoring
    0.00.906.290 W model has unused tensor blk.64.attn_output.weight (size = 21626880 bytes) -- ignoring
    0.00.906.291 W model has unused tensor blk.64.attn_q_norm.weight (size = 1024 bytes) -- ignoring
    0.00.906.293 W model has unused tensor blk.64.attn_k_norm.weight (size = 1024 bytes) -- ignoring
    0.00.906.295 W model has unused tensor blk.64.ffn_gate.weight (size = 47349760 bytes) -- ignoring
    0.00.906.296 W model has unused tensor blk.64.ffn_down.weight (size = 61276160 bytes) -- ignoring
    0.00.906.298 W model has unused tensor blk.64.ffn_up.weight (size = 61276160 bytes) -- ignoring
    0.00.906.301 W model has unused tensor blk.64.nextn.eh_proj.weight (size = 43008000 bytes) -- ignoring
    0.00.906.303 W model has unused tensor blk.64.nextn.enorm.weight (size = 20480 bytes) -- ignoring
    0.00.906.305 W model has unused tensor blk.64.nextn.hnorm.weight (size = 20480 bytes) -- ignoring
    0.00.906.310 W model has unused tensor blk.64.nextn.shared_head_norm.weight (size = 20480 bytes) -- ignoring
    0.03.537.353 W load_hparams: Qwen-VL models require at minimum 1024 image tokens to function correctly on grounding tasks
    0.03.537.357 W load_hparams: if you encounter problems with accuracy, try adding --image-min-tokens 1024
    0.03.537.357 W load_hparams: more info: https://github.com/ggml-org/llama.cpp/issues/16842
    0.03.740.759 I srv    load_model: loaded multimodal model, 'models/Qwen3.8-27B-GGUF/mmproj-F16.gguf'
    0.03.960.671 I srv    load_model: initializing, n_slots = 4, n_ctx_slot = 131072, kv_unified = 'true'
    0.03.970.981 I srv  llama_server: model loaded

## Greedy smoke
- prompt: models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf, temperature=0, max_tokens=512 (wall 4s)
- finish_reason: stop
- usage: prompt_tokens=57 completion_tokens=32
- message keys: ['content', 'reasoning_content', 'role'] (reasoning split: separate reasoning_content)
- reasoning_content chars: 103
- content (tail 300): 'OK'
- greedy OK present (in visible content): True
## Boot (MTP, WITH_MTP=1 -> --spec-type draft-mtp, ctx 131072)
- server: http://127.0.0.1:8080
- health: ok
- boot wall time: 5s (measured nohup -> first healthy /health poll)
- flags: --ctx-size 131072 -ngl 99 --jinja (env: CTX_SIZE=131072 WITH_MTP=1)
- blk.64.nextn.* (MTP block): no skip warnings (MTP block tensors loaded)
- post-boot memory: VRAM used 1131 MiB, GTT used 29266 MiB
Log evidence (`/tmp/llama-serve-mtp.log`):
    ctx-size     : 131072  (override: CTX_SIZE=<n>)
    0.00.031.313 I srv    load_model: loading model 'models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf'
    0.03.955.185 W load_hparams: Qwen-VL models require at minimum 1024 image tokens to function correctly on grounding tasks
    0.03.955.189 W load_hparams: if you encounter problems with accuracy, try adding --image-min-tokens 1024
    0.03.955.189 W load_hparams: more info: https://github.com/ggml-org/llama.cpp/issues/16842
    0.04.158.323 I srv    load_model: loaded multimodal model, 'models/Qwen3.8-27B-GGUF/mmproj-F16.gguf'
    0.04.394.238 I srv    load_model: initializing, n_slots = 4, n_ctx_slot = 131072, kv_unified = 'true'
    0.04.442.364 I srv  llama_server: model loaded

## MTP
- server: http://127.0.0.1:8080 (relaunched with WITH_MTP=1 -> --spec-type draft-mtp)
- health: ok
### MTP greedy smoke
- prompt: models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf, temperature=0, max_tokens=512 (wall 3s)
- finish_reason: stop
- usage: prompt_tokens=57 completion_tokens=32
- message keys: ['content', 'reasoning_content', 'role'] (reasoning split: separate reasoning_content)
- reasoning_content chars: 103
- content (tail 300): 'OK'
- greedy OK present (in visible content): True
### MTP acceptance evidence from /tmp/llama-serve-mtp.log
    speculative  : draft-mtp (MTP head from the same GGUF)
    0.03.903.195 I common_speculative_init_result: creating MTP draft context against the target model 'models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf'
    0.07.693.941 I slot print_timing: id  3 | task 0 | draft acceptance = 0.66667 (   22 accepted /    33 generated), mean len =  3.00
### MTP-run backend warnings (verbatim; HIP sampler-op capability notes)
    0.04.394.502 W llama_sampler_backend_support: device 'ROCm0' does not have support for op TOP_K needed for sampler 'top-k'
    0.04.394.512 W llama_sampler_backend_support: device 'ROCm0' does not have support for op TOP_K needed for sampler 'top-k'
    0.04.394.518 W llama_sampler_backend_support: device 'ROCm0' does not have support for op TOP_K needed for sampler 'top-k'
    0.04.394.523 W llama_sampler_backend_support: device 'ROCm0' does not have support for op TOP_K needed for sampler 'top-k'

## Context ladder
- default attempt above used ctx 131072
### CTX_SIZE=262144 — BOOT OK (wall 5s)
- health: ok
- memory after boot: VRAM used 1131 MiB, GTT used 34740 MiB
- blk.64.nextn.* (MTP block): 4 tensors reported unused (skipped — expected without draft-mtp)
### Greedy smoke at CTX_SIZE=262144
- prompt: models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf, temperature=0, max_tokens=512 (wall 4s)
- finish_reason: stop
- usage: prompt_tokens=57 completion_tokens=32
- message keys: ['content', 'reasoning_content', 'role'] (reasoning split: separate reasoning_content)
- reasoning_content chars: 103
- content (tail 300): 'OK'
- greedy OK present (in visible content): True
rocm-smi samples during load + greedy (`/tmp/llama-262k-mem.log`, VRAM/GTT MiB every 2s; first 3 / last 3):
    04:59:14  VRAM 1131 MiB  GTT 215 MiB
    04:59:16  VRAM 1131 MiB  GTT 16489 MiB
    04:59:18  VRAM 1131 MiB  GTT 34736 MiB
    ...
    04:59:14  VRAM 1131 MiB  GTT 215 MiB
    04:59:16  VRAM 1131 MiB  GTT 16489 MiB
    04:59:18  VRAM 1131 MiB  GTT 34736 MiB

## Outcome
- text (boot + greedy at ctx 131072): true
- MTP (draft-mtp boot + greedy + acceptance lines): true
- vision: null until Task 4 (mmproj attached during the text boot: yes)
- ctx ladder: 262144 BOOT OK (receipt finding: mmap/KV observation above); default stays 131072


## Vision (Task 4)
- server: http://127.0.0.1:8080 via `scripts/gguf-quickstart.sh` defaults
  (UD-Q4_K_XL + mmproj-F16 attached, ctx 131072, -ngl 99, --jinja); log
  `/tmp/llama-serve-vision.log`; healthy after ~10s.
- request: inline-generated solid-red 64x64 PNG (rgb 200,30,30), sent as a
  data:image/png;base64 image_url content part with text "What is the
  dominant color of this image? Answer in one word.", temperature=0,
  max_tokens=512 (llama-server OpenAI-compatible /v1/chat/completions).
- finish_reason: stop (wall 13.8 s)
- usage: prompt_tokens=77 completion_tokens=133
  (the same text prompt alone costs 57 — the PNG entered the context as
  ~20 image tokens at the default projector settings)
- message keys: ['content', 'reasoning_content', 'role'] (reasoning split: separate reasoning_content)
- message.reasoning_content (verbatim tail):
    'perception here is red. Let me consider alternatives: "red," "brown," "maroon," "rust." The pixel value appears to be a deep red with some brown undertone. The simplest, most accurate one-word answer that captures the dominant hue is "Red." I\'ll go with that.\n'
- message.content (verbatim): 'Red'
- red-word present in content: True ("Red" — and the reasoning demonstrably
  reads the actual pixels: "not pure red—it has a slightly muted, brownish-red
  tone, like a brick or rust color", which is pixel-faithful for rgb(200,30,30))
- request-time log evidence (`/tmp/llama-serve-vision.log`):
    0.26.232.703 I slot print_timing: id  3 | task 0 | prompt eval time =     884.06 ms /    77 tokens (   11.48 ms per token,    87.10 tokens per second)
    0.26.232.709 I slot print_timing: id  3 | task 0 |        eval time =   12883.93 ms /   133 tokens (   97.61 ms per token,    10.25 tokens per second)
- post-boot memory (mmproj run): VRAM used 1132 MiB, GTT used 26749 MiB

### Boot warning evaluated: --image-min-tokens 1024
- the boot log warns (see both Boot sections above): "Qwen-VL models require
  at minimum 1024 image tokens to function correctly on grounding tasks ...
  if you encounter problems with accuracy, try adding --image-min-tokens 1024"
- the default answer above was NOT degraded, but the variant was measured
  anyway: relaunched with the identical quickstart flags + --image-min-tokens
  1024 (log `/tmp/llama-serve-vision-1024.log`, healthy after ~10s)
- usage: prompt_tokens=1092 completion_tokens=95
  (the image now costs ~1035 tokens — the flag demonstrably changes image
  tokenization), finish_reason stop (wall 14.7 s)
- message.content (verbatim): 'Red' — same correct answer;
  reasoning again pixel-faithful: "a solid field of a deep, saturated red hue"
    0.41.371.156 I slot print_timing: id  3 | task 0 | prompt eval time =    5410.06 ms /  1092 tokens (    4.95 ms per token,   201.85 tokens per second)
- outcome: both configurations answer "Red" correctly for this image, so the
  warning's accuracy concern did NOT manifest for a single-small-image color
  task. No flag added to the quickstart (default ~20 image tokens stands);
  operators doing grounding/bounding-box work should try WITH the flag per
  the upstream warning (issue 16842).

Conclusion: PASS — the mmproj vision path serves real images end-to-end on
gfx1151 (ROCm 7.14, HIP). This closes the "vision: null until Task 4" line
in ## Outcome above: vision = true, single 64x64 image scope (same scope
caveat as the vLLM vision receipt).

Cleanup: all llama-server processes killed after the runs; GPU clean
(GTT back to 211 MiB, VRAM at the 1131 MiB desktop baseline).
