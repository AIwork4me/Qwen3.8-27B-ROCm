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
