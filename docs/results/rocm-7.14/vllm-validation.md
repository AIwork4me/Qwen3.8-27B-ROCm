# vLLM validation receipts — 2026-08-16T19:00Z
## Boot
Attempt 1 (before --skip-mm-profiling was added) FAILED at boot on the
multimodal encoder profiling path (not the text KV cache — the conf's
documented 262144 risk did NOT materialize; see Attempt 2). Verbatim from
/tmp/vllm-serve-attempt1-262144-mmprof.log (profile_run -> embed_multimodal ->
ViT SDPA; dummy batch item count scales with max_model_len via
vllm/multimodal/encoder_budget.py:168-170):

    torch.OutOfMemoryError: HIP out of memory. Tried to allocate 256.00 GiB. GPU 0 has a total capacity of 80.00 GiB of which 25.38 GiB is free. Of the allocated memory 54.35 GiB is allocated by PyTorch, and 51.48 MiB is reserved by PyTorch but unallocated. If reserved but unallocated memory is large try setting PYTORCH_ALLOC_CONF=expandable_segments:True to avoid fragmentation.  See documentation for Memory Management  (https://pytorch.org/docs/stable/notes/cuda.html#environment-variables)

Remedy: --skip-mm-profiling (first-class CLI flag at 4d2a68d,
vllm/engine/arg_utils.py:1354 -> MultiModalConfig.skip_mm_profiling,
vllm/config/multimodal.py:217) added to BOTH confs; text-path profiling and
serving are untouched. This checkpoint ships a vision tower
(Qwen3_5ForConditionalGeneration + vision_config), so vLLM profiles it as
multimodal by default. max-model-len stayed at 262144 — no reduction needed.

Attempt 2 (below, successful):
- server: http://127.0.0.1:8000
- health: ok
- boot wall time: 309s (measured nohup -> first healthy /health poll)
- conf: /home/amd/Desktop/Qwen3.8-27B-ROCm/configs/serve-args.conf
- flags: --served-model-name qwen3.8-27b --max-model-len 262144 --gpu-memory-utilization 0.92 --kv-cache-dtype auto --attention-backend TRITON_ATTN --dtype bfloat16 --port 8000 --skip-mm-profiling 

Log evidence (`/tmp/vllm-serve.log`):
    (EngineCore pid=3403212) INFO 08-17 02:57:00 [gpu_worker.py:578] Available KV cache memory: 19.54 GiB
    (EngineCore pid=3403212) INFO 08-17 02:57:00 [kv_cache_utils.py:1869] GPU KV cache size: 313,650 tokens, Maximum concurrency for 262,144 tokens per request: 1.20x
    (EngineCore pid=3403212) INFO 08-17 02:54:36 [gpu_model_runner.py:6563] Skipping memory profiling for multimodal encoder and encoder cache.
    (EngineCore pid=3403212) INFO 08-17 02:54:36 [gpu_model_runner.py:5515] Model loading took 51.1 GiB memory and 41.914650 seconds
    (EngineCore pid=3403212) INFO 08-17 02:57:58 [gpu_worker.py:741] CUDA graph pool memory: 0.71 GiB (actual), 1.55 GiB (estimated), difference: 0.84 GiB (119.3%).
    (EngineCore pid=3403212) INFO 08-17 02:57:58 [gpu_worker.py:804] Free memory on device (79.99/80.0 GiB) on startup. Desired GPU memory utilization is (0.92, 73.6 GiB). Actual usage is 51.66 GiB for consumed memory (weights + non-torch), 2.4 GiB for peak activation, and 0.71 GiB for CUDAGraph memory. Replace gpu_memory_utilization config with `--kv-cache-memory=20064085607` (18.69 GiB) to fit into requested memory, or `--kv-cache-memory=26927570944` (25.08 GiB) to fully utilize gpu memory. Current kv cache memory in use is 19.54 GiB.
    (EngineCore pid=3403212) INFO 08-17 02:57:59 [core.py:347] init engine (profile, create kv cache, warmup model) took 203.23 s (compilation: 52.75 s)
    (APIServer pid=3402897) INFO 08-17 02:59:34 [loggers.py:310] Engine 000: Avg prompt throughput: 5.7 tokens/s, Avg generation throughput: 1.5 tokens/s, Running: 1 reqs, Waiting: 0 reqs, GPU KV cache usage: 1.0%, Prefix cache hit rate: 0.0%
    (APIServer pid=3402897) INFO 08-17 02:59:44 [loggers.py:310] Engine 000: Avg prompt throughput: 0.0 tokens/s, Avg generation throughput: 1.2 tokens/s, Running: 0 reqs, Waiting: 0 reqs, GPU KV cache usage: 0.0%, Prefix cache hit rate: 0.0%
    (APIServer pid=3402897) INFO 08-17 02:59:54 [loggers.py:310] Engine 000: Avg prompt throughput: 0.0 tokens/s, Avg generation throughput: 0.0 tokens/s, Running: 0 reqs, Waiting: 0 reqs, GPU KV cache usage: 0.0%, Prefix cache hit rate: 0.0%

## Greedy smoke
- prompt: qwen3.8-27b, temperature=0, max_tokens=512 (wall 7s)
- finish_reason: stop
- usage: prompt_tokens=57 completion_tokens=27
- reasoning chars (hidden reasoning_content): 0
- content: 'We need to respond to user: "Reply with exactly: OK". Need final exactly OK. No extra.\n</think>\n\nOK'
- greedy OK present (in content): True

## Context probe
- filler ~2000 tokens, max_tokens=32, stream=True
- TTFT (first data chunk): 12.08s; stream wall: 19.68s
- non-stream repeat: prompt_tokens=4088 completion_tokens=32 finish_reason=length content='The user wants me to reply with exactly "OK". This is a simple instruction. I should just output "OK" and nothing else.\n</think>\n\nOK'

## MTP
- server: http://127.0.0.1:8000 (relaunched with configs/serve-args-mtp.conf)
- health: ok
- conf: /home/amd/Desktop/Qwen3.8-27B-ROCm/configs/serve-args-mtp.conf
- flags: --served-model-name qwen3.8-27b --max-model-len 262144 --gpu-memory-utilization 0.92 --kv-cache-dtype auto --attention-backend TRITON_ATTN --dtype bfloat16 --port 8000 --skip-mm-profiling --speculative-config {"method":"mtp","num_speculative_tokens":1} 
MTP boot evidence from /tmp/vllm-serve-mtp.log (wall 280s nohup -> healthy):
    INFO [model.py:672] Resolved architecture: Qwen3_5MTP
    INFO [gpu_model_runner.py:5443] Loading drafter model...
    INFO [llm_base_proposer.py:1484] Detected MTP model. Sharing target model embedding weights with the draft model.
    INFO [llm_base_proposer.py:1564] Detected MTP model. Sharing target model lm_head weights with the draft model.
    INFO [gpu_model_runner.py:5515] Model loading took 51.89 GiB memory and 41.490624 seconds
    INFO [gpu_worker.py:578] Available KV cache memory: 18.53 GiB
    INFO [kv_cache_utils.py:1869] GPU KV cache size: 278,230 tokens, Maximum concurrency for 262,144 tokens per request: 1.06x
MTP on/off comparison: identical greedy content on both passes (see ## Greedy smoke
vs the block above); both finish_reason=stop at completion_tokens=27.
- prompt: same greedy prompt, temperature=0, max_tokens=512 (wall 11s)
- finish_reason: stop
- usage: prompt_tokens=57 completion_tokens=27
- reasoning chars (hidden): 0
- content: 'We need to respond to user: "Reply with exactly: OK". Need final exactly OK. No extra.\n</think>\n\nOK'
- greedy OK present (in content): True
Acceptance / spec-decode evidence from /tmp/vllm-serve-mtp.log:
    (APIServer pid=3407168) INFO 08-17 03:01:22 [api_utils.py:272] non-default args: {'model_tag': '/home/amd/Desktop/Qwen3.8-27B-ROCm/models/Qwen3.8-27B', 'model': '/home/amd/Desktop/Qwen3.8-27B-ROCm/models/Qwen3.8-27B', 'dtype': 'bfloat16', 'max_model_len': 262144, 'served_model_name': ['qwen3.8-27b'], 'attention_backend': 'TRITON_ATTN', 'skip_mm_profiling': True, 'speculative_config': {'method': 'mtp', 'num_speculative_tokens': 1}}
    (APIServer pid=3407168) WARNING 08-17 03:01:23 [vllm.py:1845] max_num_scheduled_tokens is set to 2048 based on the speculative decoding settings. This may lead to suboptimal performance. Consider increasing max_num_batched_tokens to accommodate the additional draft token slots, or decrease num_speculative_tokens.
    (EngineCore pid=3407488) INFO 08-17 03:01:38 [core.py:122] Initializing a V1 LLM engine (v0.1.dev1+g4d2a68d64.d20260816) with config: model='/home/amd/Desktop/Qwen3.8-27B-ROCm/models/Qwen3.8-27B', speculative_config=SpeculativeConfig(method='mtp', model='/home/amd/Desktop/Qwen3.8-27B-ROCm/models/Qwen3.8-27B', num_spec_tokens=1), tokenizer='/home/amd/Desktop/Qwen3.8-27B-ROCm/models/Qwen3.8-27B', skip_tokenizer_init=False, tokenizer_mode=auto, revision=None, tokenizer_revision=None, trust_remote_code=False, dtype=torch.bfloat16, max_seq_len=262144, download_dir=None, load_format=auto, tensor_parallel_size=1, pipeline_parallel_size=1, data_parallel_size=1, decode_context_parallel_size=1, dcp_comm_backend=ag_rs, disable_custom_all_reduce=True, quantization=None, quantization_config=None, enforce_eager=False, enable_return_routed_experts=False, kv_cache_dtype=auto, device_config=cuda, structured_outputs_config=StructuredOutputsConfig(backend='auto', disable_any_whitespace=False, disable_additional_properties=False, reasoning_parser='', reasoning_parser_plugin='', enable_in_reasoning=False), observability_config=ObservabilityConfig(show_hidden_metrics_for_version=None, otlp_traces_endpoint=None, collect_detailed_traces=None, kv_cache_metrics=False, kv_cache_metrics_sample=0.01, cudagraph_metrics=False, enable_layerwise_nvtx_tracing=False, enable_mfu_metrics=False, enable_mm_processor_stats=False, enable_logging_iteration_details=False, jit_monitor_mode='warn', jit_monitor_verbose=False), seed=0, served_model_name=qwen3.8-27b, enable_prefix_caching=True, enable_chunked_prefill=True, pooler_config=None, compilation_config={'mode': <CompilationMode.VLLM_COMPILE: 3>, 'debug_dump_path': None, 'cache_dir': '', 'compile_cache_save_format': 'binary', 'backend': 'inductor', 'custom_ops': ['+sparse_attn_indexer', 'none'], 'ir_enable_torch_wrap': True, 'splitting_ops': ['vllm::unified_attention_with_output', 'vllm::unified_mla_attention_with_output', 'vllm::mamba_mixer2', 'vllm::mamba_mixer', 'vllm::short_conv', 'vllm::linear_attention', 'vllm::qwen_gdn_attention_core', 'vllm::qwen_gdn_attention_core_fused_norm_packed', 'vllm::gdn_attention_core_xpu', 'vllm::olmo_hybrid_gdn_full_forward', 'vllm::sparse_attn_indexer', 'vllm::rocm_aiter_sparse_attn_indexer', 'vllm::deepseek_v4_attention', 'vllm::hpc_rope_norm_forward', 'vllm::unified_kv_cache_update', 'vllm::unified_mla_kv_cache_update'], 'compile_mm_encoder': False, 'cudagraph_mm_encoder': False, 'encoder_cudagraph_token_budgets': [], 'encoder_cudagraph_max_vision_items_per_batch': 0, 'encoder_cudagraph_max_frames_per_batch': None, 'compile_sizes': [], 'compile_ranges_endpoints': [2048], 'inductor_compile_config': {'enable_auto_functionalized_v2': False, 'size_asserts': False, 'alignment_asserts': False, 'scalar_asserts': False, 'combo_kernels': True, 'benchmark_combo_kernel': True}, 'inductor_passes': {}, 'cudagraph_mode': <CUDAGraphMode.FULL_AND_PIECEWISE: (2, 1)>, 'cudagraph_num_of_warmups': 1, 'cudagraph_capture_sizes': [1, 2, 4, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 128, 136, 144, 152, 160, 168, 176, 184, 192, 200, 208, 216, 224, 232, 240, 248, 256, 272, 288, 304, 320, 336, 352, 368, 384, 400, 416, 432, 448, 464, 480, 496, 512], 'cudagraph_copy_inputs': False, 'cudagraph_specialize_lora': True, 'use_inductor_graph_partition': False, 'pass_config': {'fuse_norm_quant': False, 'fuse_act_quant': False, 'fuse_attn_quant': False, 'enable_sp': False, 'fuse_gemm_comms': False, 'enable_qk_norm_rope_fusion': False, 'fuse_rope_kvcache_cat_mla': False, 'fuse_act_padding': False, 'fuse_qk_norm_rope_kvcache': False}, 'max_cudagraph_capture_size': 512, 'dynamic_shapes_config': {'type': <DynamicShapesType.BACKED: 'backed'>, 'evaluate_guards': False, 'assume_32_bit_indexing': False}, 'local_cache_dir': None, 'fast_moe_cold_start': False, 'static_all_moe_layers': []}, kernel_config=KernelConfig(ir_op_priority=IrOpPriorityConfig(rms_norm=['native'], fused_add_rms_norm=['native']), enable_flashinfer_autotune=True, enable_cutedsl_warmup=True, enable_jit_warmup=True, enable_bf16x3_router_gemm=False, moe_backend='auto', linear_backend='auto')
    (EngineCore pid=3407488) WARNING 08-17 03:01:40 [__init__.py:205] min_p and logit_bias parameters won't work with speculative decoding.
    (EngineCore pid=3407488) WARNING 08-17 03:02:23 [vllm.py:1845] max_num_scheduled_tokens is set to 2048 based on the speculative decoding settings. This may lead to suboptimal performance. Consider increasing max_num_batched_tokens to accommodate the additional draft token slots, or decrease num_speculative_tokens.

Longer-decode acceptance evidence (max_tokens=400 counting request, then
periodic SpecDecoding metrics logger; acceptance lines only appear once
enough decode steps have run, which the short greedy prompt alone did not
trigger):
    INFO 08-17 03:06:10 [metrics.py:120] SpecDecoding metrics: Mean acceptance length: 1.93, Accepted throughput: 0.35 tokens/s, Drafted throughput: 0.38 tokens/s, Accepted: 13 tokens, Drafted: 14 tokens, Per-position acceptance rate: 0.929, Avg Draft acceptance rate: 92.9%
    INFO 08-17 03:06:30 [metrics.py:120] SpecDecoding metrics: Mean acceptance length: 1.91, Accepted throughput: 1.05 tokens/s, Drafted throughput: 1.15 tokens/s, Accepted: 21 tokens, Drafted: 23 tokens, Per-position acceptance rate: 0.913, Avg Draft acceptance rate: 91.3%
    INFO 08-17 03:06:40 [metrics.py:120] SpecDecoding metrics: Mean acceptance length: 2.00, Accepted throughput: 3.70 tokens/s, Drafted throughput: 3.70 tokens/s, Accepted: 37 tokens, Drafted: 37 tokens, Per-position acceptance rate: 1.000, Avg Draft acceptance rate: 100.0%
    INFO 08-17 03:06:50 [metrics.py:120] SpecDecoding metrics: Mean acceptance length: 2.00, Accepted throughput: 3.60 tokens/s, Drafted throughput: 3.60 tokens/s, Accepted: 36 tokens, Drafted: 36 tokens, Per-position acceptance rate: 1.000, Avg Draft acceptance rate: 100.0%
    INFO 08-17 03:07:00 [metrics.py:120] SpecDecoding metrics: Mean acceptance length: 2.00, Accepted throughput: 1.30 tokens/s, Drafted throughput: 1.30 tokens/s, Accepted: 13 tokens, Drafted: 13 tokens, Per-position acceptance rate: 1.000, Avg Draft acceptance rate: 100.0%

## Reasoning parser (Task 6 review follow-up)
`--reasoning-parser qwen3` added to BOTH confs after on-host verification
(2026-08-17, /tmp/vllm-serve.log). The parser exists at the pin: registered
as "qwen3" at vllm/reasoning/__init__.py:127 -> Qwen3ParserReasoningAdapter
(vllm/reasoning/qwen3_engine_reasoning_parser.py -> make_adapters(
vllm.parser.qwen3.Qwen3Parser)).

- boot with the flag: healthy in ~187 s (nohup -> first healthy poll);
  `'reasoning_parser': 'qwen3'` appears in api_utils non-default args and
  `reasoning_parser='qwen3'` in the StructuredOutputsConfig of the engine
  init line. No new warnings beyond the pre-existing transformers
  Qwen3VL docstring notices.
- greedy (same prompt as ## Greedy smoke, temperature=0, max_tokens=512,
  wall 7 s): finish_reason=stop, usage prompt_tokens=57
  completion_tokens=27 — token-identical to the no-parser baseline above,
  i.e. the parser changes OUTPUT PACKAGING ONLY, not generation.
- split verified; NOTE the field at this commit is message."reasoning"
  (the older DeepSeek-style "reasoning_content" stays absent — .get()
  returns None):
    reasoning: 'We need to respond to user: "Reply with exactly: OK". Need final exactly OK. No extra.\n'
    content:   '\n\nOK'
  The pre-</think> text lands verbatim in "reasoning"; content keeps the
  post-tag separator plus the answer ('OK' present, no '</think>' residue).
- streaming (stream=True, same prompt): first delta carries
  "reasoning" ('We'); content deltas begin only after the reasoning stream
  ends (first content delta '\n\n').
- MTP combo (serve-args-mtp.conf WITH the parser; boot ~255 s -> healthy;
  /tmp/vllm-serve-mtp.log, wall 4.5 s): same split, same 57/27 tokens,
  finish_reason=stop, drafter loaded as before ('Resolved architecture:
  Qwen3_5MTP'). Parser and speculative decoding coexist.

## Vision (Task 6)
- server: http://127.0.0.1:8000, baseline conf INCLUDING the reasoning
  parser above (i.e. the final configs/serve-args.conf state); log
  /tmp/vllm-serve.log. --skip-mm-profiling was still set — it skips only
  boot-time PROFILING, not image serving, and the forward path below ran
  the real image through preprocessor -> ViT encoder -> LLM.
- request: inline-generated solid-red 64x64 PNG (rgb 200,30,30), sent as a
  data:image/png;base64 image_url content part with text "What is the
  dominant color of this image? Answer in one word.", temperature=0,
  max_tokens=512. Wall: 29.3 s (includes first-use Triton JIT of the
  vision kernels, see evidence below).
- finish_reason: stop
- usage: prompt_tokens=132 completion_tokens=117 (the same text prompt
  alone costs 57 — the PNG really entered the context as ~75 image tokens)
- message.reasoning (verbatim):
  'The user wants the dominant color of the image, answered in a single word. The image is a uniform field of a deep, saturated red hue. There are no other colors, gradients, or objects present. The instruction is strict: one word. Possible candidates include "red," "crimson," or "maroon." The shade is a strong, classic red, not leaning heavily toward purple (maroon) or pink (crimson). The most accurate and simplest single-word descriptor is "Red." I will provide just that word to satisfy the constraint.\n'
- message.content (verbatim): '\n\nRed'
- color word present in content: True ("Red" — correct for the solid-red
  input; the encoder demonstrably processed the actual pixels, per the
  reasoning text describing a uniform saturated red field with no gradients)

Encoder-forward log evidence (/tmp/vllm-serve.log, at the vision request):
    (EngineCore pid=3415174) INFO 08-17 03:16:25 [mm_encoder_attention.py:375] Using AttentionBackendEnum.TORCH_SDPA for MMEncoderAttention.
    (EngineCore pid=3415174) WARNING 08-17 03:20:49 [jit_monitor.py:141] Triton kernel JIT compilation during inference: _bilinear_pos_embed_kernel. This causes a latency spike; consider extending warmup to cover this shape/config.
    (EngineCore pid=3415174) .../third_party/vllm/vllm/v1/attention/ops/vit_attn_wrappers.py:246: UserWarning: Flash Efficient attention on Current AMD GPU is still experimental. Enable it with TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1.
    (APIServer pid=3414818) INFO 08-17 03:21:10 [loggers.py:310] Engine 000: ... Running: 1 reqs, Waiting: 0 reqs, GPU KV cache usage: 1.0%, Prefix cache hit rate: 0.0%, MM cache hit rate: 0.0%

Conclusion: PASS — the multimodal forward path serves real images end-to-end
on gfx1151 (ROCm 7.14, TORCH_SDPA MM-encoder attention). Scope caveat,
mirrored in both confs: with --skip-mm-profiling the encoder's activation
peak is not measured or reserved at boot, so encoder-peak memory budgeting
for image workloads is the operator's job; this receipt covers a single
64x64 image only.
