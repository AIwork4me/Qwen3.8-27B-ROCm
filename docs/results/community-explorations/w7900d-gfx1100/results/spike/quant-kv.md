# Spike C: official quantizations + KV-cache dtype levers — 2026-08-16

Pure recon, no GPU runs. All probes executed 2026-08-16 from the radeon-cloud
host via the Global-Constraints `fetch` retry helper (3 attempts, 30 s curl
timeout) unless a block quotes plain `curl` or `python3`. Pins:

- vLLM: `83f591d7f694a3ca3ae3bf22d646e818a1421872` (2026-08-16T15:24:14Z) —
  the SHA Task 6 recorded; per the pinning discipline every vLLM file below
  is fetched at this SHA (the brief's `/main/` URLs were substituted with the
  pinned-SHA form). Main moved during this spike (recorded in Q2), so the pin
  is load-bearing.
- llama.cpp: `4df29be4f4c3673f428170fda944a5b19f743bb8` (2026-08-16T12:53:13Z)
  — Task 7's pin, re-verified as still master HEAD today (Q3).

Host facts (consistent with Spikes A/B): huggingface.co is unreachable — every
HF probe records `000` (curl exit 28), a finding, not a skip.
raw.githubusercontent.com was flaky: one file (vllm/platforms/interface.py)
hit persistent 3-retry mid-transfer failures and was recovered via the
api.github.com contents endpoint (recorded in Q2); one re-probe of a 404 path
surfaced as timeouts before a paced plain-curl pass confirmed the real status
codes. ModelScope and api.github.com were reliable throughout.

## Q1 quant variants today

- Probe (brief Step 1, as written):

```console
$ for repo in Qwen/Qwen3.8-27B-AWQ Qwen/Qwen3.8-27B-GPTQ-Int4 Qwen/Qwen3.8-27B-FP8 Qwen/Qwen3.8-27B-MXFP4 unsloth/Qwen3.8-27B-AWQ; do
  for host in modelscope huggingface; do
    if [ "$host" = modelscope ]; then url="https://modelscope.cn/api/v1/models/$repo"; else url="https://huggingface.co/api/models/$repo"; fi
    printf '%s %s -> ' "$host" "$repo"; curl -s -o /dev/null -m 15 -w '%{http_code}\n' "$url"
  done
done
modelscope Qwen/Qwen3.8-27B-AWQ -> 404
huggingface Qwen/Qwen3.8-27B-AWQ -> 000
modelscope Qwen/Qwen3.8-27B-GPTQ-Int4 -> 404
huggingface Qwen/Qwen3.8-27B-GPTQ-Int4 -> 000
modelscope Qwen/Qwen3.8-27B-FP8 -> 200
huggingface Qwen/Qwen3.8-27B-FP8 -> 000
modelscope Qwen/Qwen3.8-27B-MXFP4 -> 404
huggingface Qwen/Qwen3.8-27B-MXFP4 -> 000
modelscope unsloth/Qwen3.8-27B-AWQ -> 404
huggingface unsloth/Qwen3.8-27B-AWQ -> 000
```

- The one Step-1 200 (official FP8), measured per the brief's command plus a
  file count and the checkpoint's own quant config:

```console
$ curl -s -m 20 "https://modelscope.cn/api/v1/models/Qwen/Qwen3.8-27B-FP8/repo/files?Revision=master" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); fs=d['Data']['Files']; print('Qwen/Qwen3.8-27B-FP8', 'GiB:', round(sum(f['Size'] for f in fs if f['Path'].endswith('.safetensors'))/2**30,1))"
Qwen/Qwen3.8-27B-FP8 GiB: 28.7

$ curl -s -m 20 "https://modelscope.cn/api/v1/models/Qwen/Qwen3.8-27B-FP8/repo/files?Revision=master" | python3 -c "
import json,sys
d=json.load(sys.stdin); fs=d['Data']['Files']
st=[f for f in fs if f['Path'].endswith('.safetensors')]
print('safetensors files:', len(st))
print('total safetensors bytes:', sum(f['Size'] for f in st))
"
safetensors files: 66
total safetensors bytes: 30866866928

$ curl -s -m 20 "https://modelscope.cn/api/v1/models/Qwen/Qwen3.8-27B-FP8/repo?Revision=master&FilePath=config.json" | python3 -c "
import json,sys
c=json.load(sys.stdin)
qc=c.get('quantization_config', {})
print('architectures:', c.get('architectures'))
print('model_type:', c.get('model_type'))
print('quant_method:', qc.get('quant_method'), '| fmt:', qc.get('fmt'), '| activation_scheme:', qc.get('activation_scheme'))
print('weight_block_size:', qc.get('weight_block_size'))
print('text_config.num_hidden_layers:', c.get('text_config',{}).get('num_hidden_layers'))
print('text_config.mtp_num_hidden_layers:', c.get('text_config',{}).get('mtp_num_hidden_layers'))
"
architectures: ['Qwen3_5ForConditionalGeneration']
model_type: qwen3_5
quant_method: fp8 | fmt: e4m3 | activation_scheme: dynamic
weight_block_size: [128, 128]
text_config.num_hidden_layers: 64
text_config.mtp_num_hidden_layers: 1
```

  I.e. block-wise (128x128) dynamic FP8-E4M3 on the qwen3_5 architecture,
  MTP weights included (mtp.safetensors + mtp_num_hidden_layers: 1), 64
  layer-sharded safetensors plus outside.safetensors/mtp.safetensors.

- The GGUF quant repos (probed in Spike B; totals measured fresh here for
  Task 9's manifest) and the BF16 base, via ModelScope's model-info
  `StorageSize`:

```console
$ for repo in Qwen/Qwen3.8-27B-FP8 unsloth/Qwen3.8-27B-GGUF bartowski/Qwen3.8-27B-GGUF Qwen/Qwen3.8-27B; do
  printf '%s ' "$repo"
  curl -s -m 20 "https://modelscope.cn/api/v1/models/$repo" | python3 -c "import json,sys; d=json.load(sys.stdin); print('StorageSize:', d['Data']['StorageSize'], 'bytes =', round(d['Data']['StorageSize']/2**30,1), 'GiB')"
done
Qwen/Qwen3.8-27B-FP8 StorageSize: 30890049500 bytes = 28.8 GiB
unsloth/Qwen3.8-27B-GGUF StorageSize: 423698792135 bytes = 394.6 GiB
bartowski/Qwen3.8-27B-GGUF StorageSize: 479757971711 bytes = 446.8 GiB
Qwen/Qwen3.8-27B StorageSize: 55586114768 bytes = 51.8 GiB

$ for repo in unsloth/Qwen3.8-27B-GGUF bartowski/Qwen3.8-27B-GGUF; do
  curl -s -m 30 "https://modelscope.cn/api/v1/models/$repo/repo/files?Revision=master" | python3 -c "
import json,sys
name='$repo'
d=json.load(sys.stdin); fs=d['Data']['Files']
quants=[f for f in fs if f['Path'].endswith('.gguf') and 'mmproj' not in f['Path'] and 'imatrix' not in f['Path']]
allgguf=[f for f in fs if f['Path'].endswith('.gguf')]
print(name+':', len(quants), 'quant files, span', round(min(f['Size'] for f in quants)/2**30,1), '-', round(max(f['Size'] for f in quants)/2**30,1), 'GiB; quant-file total', round(sum(f['Size'] for f in quants)/2**30,1), 'GiB; all .gguf total', round(sum(f['Size'] for f in allgguf)/2**30,1), 'GiB')
"
done
unsloth/Qwen3.8-27B-GGUF: 21 quant files, span 8.4 - 29.3 GiB; quant-file total 342.0 GiB; all .gguf total 343.7 GiB
bartowski/Qwen3.8-27B-GGUF: 26 quant files, span 8.7 - 27.1 GiB; quant-file total 394.2 GiB; all .gguf total 395.9 GiB
```

  (StorageSize exceeds the file-list sums for the GGUF repos — bartowski
  446.8 vs 395.9 GiB summed — consistent with additional content not in the
  master-revision listing, e.g. the mirrored BF16/ directory; both numbers
  recorded, per-file tables in [gguf.md](gguf.md).)

- Stability of the three 200s (3x fresh re-probe, Spike-B discipline):

```console
$ for repo in Qwen/Qwen3.8-27B-FP8 unsloth/Qwen3.8-27B-GGUF bartowski/Qwen3.8-27B-GGUF; do
  printf '%s -> ' "$repo"; for i in 1 2 3; do printf '%s ' "$(curl -s -o /dev/null -m 15 -w '%{http_code}' "https://modelscope.cn/api/v1/models/$repo")"; done; echo
done
Qwen/Qwen3.8-27B-FP8 -> 200 200 200
unsloth/Qwen3.8-27B-GGUF -> 200 200 200
bartowski/Qwen3.8-27B-GGUF -> 200 200 200
```

Summary table (method from the checkpoint's own config / GGUF quant naming):

| Repo id | Host | Code | Method | Total GiB (measured) |
|---|---|---|---|---|
| Qwen/Qwen3.8-27B-FP8 | ModelScope | 200 | fp8 e4m3, dynamic, block 128x128, MTP incl. | 28.7 safetensors sum (StorageSize 28.8) |
| Qwen/Qwen3.8-27B-AWQ | ModelScope / HF | 404 / 000 | awq | — (absent) |
| Qwen/Qwen3.8-27B-GPTQ-Int4 | ModelScope / HF | 404 / 000 | gptq | — (absent) |
| Qwen/Qwen3.8-27B-MXFP4 | ModelScope / HF | 404 / 000 | mxfp4 | — (absent) |
| unsloth/Qwen3.8-27B-AWQ | ModelScope / HF | 404 / 000 | awq | — (absent) |
| unsloth/Qwen3.8-27B-GGUF | ModelScope | 200 | gguf, 21 quants (UD-IQ2_XXS..UD-Q8_K_XL) | per-file 8.4–29.3; set total 342.0 |
| bartowski/Qwen3.8-27B-GGUF | ModelScope | 200 | gguf, 26 quants (IQ2_XXS..Q8_0) + imatrix | per-file 8.7–27.1; set total 394.2 |
| Qwen/Qwen3.8-27B (BF16 base, context) | ModelScope | 200 | bf16 | 51.8 (StorageSize) |

- Conclusion: the ONLY official (Qwen-published) weight-quantized variant of
  Qwen3.8-27B reachable today is **Qwen/Qwen3.8-27B-FP8 on ModelScope, 28.7
  GiB** (HF codes 000 = host unreachable, existence there unverifiable).
  No official AWQ / GPTQ / MXFP4 repos exist on ModelScope, and no
  community AWQ either; community quantization activity is entirely on the
  GGUF side (unsloth + bartowski, per Spike B).
- SHA/date probed: ModelScope API responses 2026-08-16; per-file GGUF sizes
  cross-consistent with Spike B's 2026-08-16 listing in [gguf.md](gguf.md).

## Q2 vLLM quant/KV on ROCm

All vLLM evidence at pinned SHA `83f591d7f694a3ca3ae3bf22d646e818a1421872`.
Main HEAD at re-probe time (note the drift — pin matters):

```console
$ fetch "https://api.github.com/repos/vllm-project/vllm/commits?per_page=1" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date'])"
1f0e0bf61210346a6bef4ad75172e62554d1b86c 2026-08-16T17:13:02Z
```

### Q2.1 Stale doc path finding

The brief's `docs/features/quantization/index.md` is 404 at the pinned SHA —
the quantization doc dir uses `README.md` (plus per-method files). The
retry-helper runs against the stale path failed in mixed modes across
attempts (a first pass returned clean HTTP 404s on all 3 tries; the
re-captured run below hit curl-28 timeouts) — raw.githubusercontent
flakiness, recorded. The definitive status pair came from paced plain curl:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/docs/features/quantization/index.md" > /tmp/t8/vllm-quant-index.md; echo "exit=$? bytes=$(stat -c %s /tmp/t8/vllm-quant-index.md)"
curl: (28) Operation timed out after 30001 milliseconds with 0 bytes received
retry 1 for https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/docs/features/quantization/index.md
curl: (28) Operation timed out after 30002 milliseconds with 0 bytes received
retry 2 for https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/docs/features/quantization/index.md
curl: (28) Connection timed out after 30002 milliseconds
retry 3 for https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/docs/features/quantization/index.md
exit=1 bytes=0
```

```console
$ for p in docs/features/quantization/index.md docs/features/quantization/README.md; do printf '%s -> ' "$p"; curl -s -o /dev/null -m 30 -w '%{http_code}' "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/$p" || true; echo; sleep 3; done
docs/features/quantization/index.md -> 404
docs/features/quantization/README.md -> 200
```

Current doc inventory at the pinned SHA (git-trees API):

```console
$ curl -fsSL -m 60 "https://api.github.com/repos/vllm-project/vllm/git/trees/83f591d7f694a3ca3ae3bf22d646e818a1421872?recursive=1" -o vllm-tree.json
$ python3 -c "
import json
d=json.load(open('vllm-tree.json'))
for t in d['tree']:
    p=t['path']
    if p.startswith('docs/features/quantization'):
        print(p, t['type'])
"
docs/features/quantization tree
docs/features/quantization/README.md blob
docs/features/quantization/auto_awq.md blob
docs/features/quantization/b12x.md blob
docs/features/quantization/bnb.md blob
docs/features/quantization/fp8_vit_attn.md blob
docs/features/quantization/gguf.md blob
docs/features/quantization/gptqmodel.md blob
docs/features/quantization/inc.md blob
docs/features/quantization/llm_compressor tree
docs/features/quantization/llm_compressor/README.md blob
docs/features/quantization/llm_compressor/fp8.md blob
docs/features/quantization/llm_compressor/int4.md blob
docs/features/quantization/llm_compressor/int8_w4a8.md blob
docs/features/quantization/llm_compressor/int8_w8a8.md blob
docs/features/quantization/modelopt.md blob
docs/features/quantization/online.md blob
docs/features/quantization/quantized_kvcache.md blob
docs/features/quantization/quark.md blob
docs/features/quantization/torchao.md blob
```

### Q2.2 Official hardware-support table (docs/features/quantization/README.md)

The brief's grep (corrected path), pinned:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/docs/features/quantization/README.md" \
    | grep -n -i 'awq\|gptq\|mxfp4\|fp8' | head
6:    To get started with quantization, see [LLM Compressor](llm_compressor/README.md), a library for optimizing models for deployment with vLLM that supports FP8, INT8, INT4, and other quantization formats.
10:- [AutoAWQ](auto_awq.md)
12:- [GPTQModel](gptqmodel.md)
15:    - [FP8 W8A8](llm_compressor/fp8.md)
24:- [FP8 ViT Encoder Attention](fp8_vit_attn.md)
52:| AWQ                       | ❌    | ✅︎     | ✅︎     | ✅︎  | ✅︎     | ❌      | ✅︎        | ✅︎      | ❌      |
53:| GPTQ                      | ✅︎    | ✅︎     | ✅︎     | ✅︎  | ✅︎     | ❌      | ✅︎        | ✅︎      | ❌      |
54:| Marlin (GPTQ/AWQ/FP8/FP4) | ❌    | ✅︎*    | ✅︎     | ✅︎  | ✅︎     | ❌      | ❌        | ❌      | ❌      |
57:| llm-compressor FP8 (W8A8) | ❌    | ❌     | ❌     | ✅︎  | ✅︎     | ✅︎      | ❌        | ❌      | ❌      |
66:- *Turing does not support Marlin MXFP4.
```

Column header from the same file: `| Implementation | Volta | Turing |
Ampere | Ada | Hopper | AMD GPU | Intel GPU | x86 CPU | Arm CPU |` — so in
the official table the **AMD GPU** column reads: AWQ ❌, GPTQ ❌, Marlin
(GPTQ/AWQ/FP8/FP4 — the only FP4/MXFP4-adjacent row) ❌, llm-compressor
INT8 W8A8 ❌, INT8 W4A8 ❌, **llm-compressor FP8 (W8A8) ✅**, bitsandbytes ❌,
DeepSpeedFP ❌, GGUF ✅. CUDA-only context: the Volta–Hopper columns are
NVIDIA-by-construction, and Marlin/nvfp4 are CUDA-only code paths.

### Q2.3 KV-cache dtype config (vllm/config/cache.py — exists at the pin)

Task 6 found `vllm/config.py` became the `vllm/config/` package;
`vllm/config/cache.py` DOES exist at the pinned SHA (13934 bytes). The
brief's grep, pinned:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/config/cache.py" | grep -n -i 'fp8\|dtype' | head
19:CacheDType = Literal[
23:    "fp8",
24:    "fp8_e4m3",
25:    "fp8_e5m2",
26:    "fp8_inc",
27:    "fp8_ds_mla",
34:    "fp8_per_token_head",
38:MambaDType = Literal["auto", "float32", "float16", "bfloat16"]
77:    cache_dtype: CacheDType = "auto"
79:    CUDA 11.8+ supports fp8 (=fp8_e4m3) and fp8_e5m2. ROCm (AMD GPU) supports
```

The load-bearing docstring, in full:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/config/cache.py" | grep -n -A7 'Data type for kv cache storage'
78:    """Data type for kv cache storage. If "auto", will use model data type.
79-    CUDA 11.8+ supports fp8 (=fp8_e4m3) and fp8_e5m2. ROCm (AMD GPU) supports
80-    fp8 (=fp8_e4m3). Intel Gaudi (HPU) supports fp8 (using fp8_inc).
81-    Some models (namely DeepSeekV3.2) default to fp8, set to bfloat16 to use
82-    bfloat16 instead, this is an invalid option for models that do not default
83-    to fp8.
84-    "nvfp4_4over6" uses the NVFP4 layout and selects between max/6 and max/4
85-    scales per 16 values by minimizing squared reconstruction error.
```

**CUDA-ONLY CLAIM FLAGGED**: per the config docstring, on ROCm only
fp8 (=e4m3) is a documented KV dtype; `fp8_e5m2` is CUDA-11.8+-only, and
`nvfp4_4over6` is an NVIDIA layout. The user-facing
`docs/features/quantization/quantized_kvcache.md` agrees:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/docs/features/quantization/quantized_kvcache.md" | grep -n -i 'fp8_e4m3\|fp8_e5m2\|only with\|flash attention'
7:> **Note:** When using the Flash Attention 3 backend with FP8 KV cache, attention operations are also performed in the quantized (FP8) domain. In this configuration, queries are quantized to FP8 in addition to keys and values.
19:> Per-attention-head quantization is currently available **only with the Flash Attention backend** and requires the calibration pathway provided by **llm-compressor**.
40:- `kv_cache_dtype="fp8_e4m3"`: Supported on CUDA 11.8+ and ROCm (AMD GPUs)
41:- `kv_cache_dtype="fp8_e5m2"`: Supported on CUDA 11.8+
```

**CUDA-ONLY CLAIMS FLAGGED**: (1) fp8_e5m2 KV = CUDA-only (line 41);
(2) per-attention-head KV scaling = "only with the Flash Attention backend"
(line 19) — FA3 is a CUDA backend, so on ROCm we are left with per-tensor
scales; (3) FP8-domain attention (line 7) is an FA3 feature, again CUDA.
The doc also documents `--kv-cache-dtype-skip-layers` (skip e.g.
sliding-window layers), which is platform-neutral.

### Q2.4 ROCm platform code (vllm/platforms/rocm.py)

The platform's accepted-methods list — which CONTRADICTS the Q2.2 doc
table's ❌ for AWQ/GPTQ on AMD (docs drift, both quoted):

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/platforms/rocm.py" | grep -n -A24 'supported_quantization: list'
513:    supported_quantization: list[str] = [
514-        "awq",
515-        "auto_awq",
516-        "awq_marlin",  # will be overwritten with awq
517-        "gptq",
518-        "auto_gptq",
519-        "fp8",
520-        "deepseek_v4_fp8",
521-        "compressed-tensors",
522-        "fbgemm_fp8",
523-        "inc",
524-        "quark",
525-        "mxfp4",
526-        "mxfp8",
527-        "torchao",
528-        "modelopt",
529-        "modelopt_fp4",
530-        "modelopt_mxfp8",
531-        "modelopt_mixed",
532-        "fp8_per_tensor",
533-        "fp8_per_block",
534-        "fp8_per_channel",
535-        "online",
536-        "gpt_oss_mxfp4",
537-    ]
```

AWQ on ROCm is force-routed to the Triton kernel path:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/platforms/rocm.py" | grep -n -A8 'def verify_quantization'
940:    def verify_quantization(cls, quant: str) -> None:
941-        super().verify_quantization(quant)
942-        if quant == "awq" and not envs.VLLM_USE_TRITON_AWQ:
943-            logger.warning(
944-                "Using AWQ quantization with ROCm, but VLLM_USE_TRITON_AWQ"
945-                " is not set, enabling VLLM_USE_TRITON_AWQ."
946-            )
947-        os.environ["VLLM_USE_TRITON_AWQ"] = "1"
948-
```

(The base-class check this feeds — "raise ValueError if the method is not in
the platform list" — lives in `vllm/platforms/interface.py`. Its raw
fetch corrupted mid-transfer on all 3 attempts — curl exit 28 with partial
bodies of 17870 and then 37428 of the 48586 expected bytes, leaving a
55298-byte mixed file — a recorded raw.githubusercontent failure; the
api.github.com contents endpoint was the recovery path, and all
interface.py quotes below come from that copy:)

```console
$ python3 -c "
import json, urllib.request, base64
url='https://api.github.com/repos/vllm-project/vllm/contents/vllm/platforms/interface.py?ref=83f591d7f694a3ca3ae3bf22d646e818a1421872'
req=urllib.request.Request(url, headers={'User-Agent':'probe'})
d=json.load(urllib.request.urlopen(req, timeout=30))
content=base64.b64decode(d['content']).decode()
open('/tmp/t8/vllm-interface-api.py','w').write(content)
print('blob sha:', d['sha'], 'size:', len(content))
"
blob sha: c3ade53ca139b1c40cf9250be0578eb6d3d5c744 size: 48584

$ diff -q /tmp/t8/vllm-interface-api.py /tmp/t8/vllm-interface.py && echo IDENTICAL || echo DIFFERS
Files /tmp/t8/vllm-interface-api.py and /tmp/t8/vllm-interface.py differ
DIFFERS

$ grep -n -A7 'def verify_quantization' /tmp/t8/vllm-interface-api.py
960:    def verify_quantization(cls, quant: str) -> None:
961-        """
962-        Verify whether the quantization is supported by the current platform.
963-        """
964-        if cls.supported_quantization and quant not in cls.supported_quantization:
965-            raise ValueError(
966-                f"{quant} quantization is currently not supported in {cls.device_name}."
967-            )
```

The silicon-level capability gates that matter for gfx1100:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/platforms/rocm.py" | grep -n -A4 'def supports_mx\|def supports_fp8\|def is_fp8_fnuz\|def fp8_dtype'
968:    def supports_mx(cls) -> bool:
969-        return any(gfx in _GCN_ARCH for gfx in ["gfx95", "gfx1250"])
970-
971-    @classmethod
972:    def supports_fp8(cls) -> bool:
973-        return on_cdna() or on_rdna4()
974-
975-    @classmethod
976:    def is_fp8_fnuz(cls) -> bool:
977-        # only device 0 is checked, this assumes MI300 platforms are homogeneous
978-        return "gfx94" in _GCN_ARCH
979-
980-    @classmethod
981:    def fp8_dtype(cls) -> torch.dtype:
982-        if cls.is_fp8_fnuz():
983-            return torch.float8_e4m3fnuz
984-        else:
985-            return torch.float8_e4m3fn
```

Operative facts for gfx1100 (RDNA3): it is neither CDNA nor RDNA4, so
**`supports_fp8()` is False**; it is not gfx95/gfx1250, so **`supports_mx()`
is False** (MXFP4/MXFP8 gated off); and its fp8 dtype would be `e4m3fn`
(not the gfx94x fnuz variant).

And the RDNA-specific constraint on the custom paged-attention kernel
(`use_rocm_custom_paged_attention`, the `_ON_GFX1X` return branch — whose
full condition also requires fp16/bf16 q dtype, head_size 128, block_size
16, gqa_ratio 3-16, max_seq_len at most 128k, no alibi/sinks, per the same
function; the character-clean excerpt of the decisive term):

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/platforms/rocm.py" | grep -n -B1 -A2 'kv_cache_dtype == "auto"'
419-            and alibi_slopes is None
420:            and kv_cache_dtype == "auto"
421-            and sinks is None
422-        )
```

I.e. on gfx1x the custom paged-attention kernel is only selected when the KV
cache dtype is `auto` — a quantized KV cache forces a different attention
path on RDNA.

### Q2.5 Attention backends that advertise fp8 KV on ROCm

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/v1/attention/backends/rocm_attn.py" | grep -n -A7 'supported_kv_cache_dtypes: ClassVar'
171:    supported_kv_cache_dtypes: ClassVar[list[CacheDType]] = [
172-        "auto",
173-        "float16",
174-        "bfloat16",
175-        "fp8",
176-        "fp8_e4m3",
177-        "fp8_e5m2",
178-    ]

$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/v1/attention/backends/rocm_attn.py" | grep -n -B1 -A4 'is_quantized_kv_cache(self.kv_cache_dtype)'
337-        # For encoder attention, process FP8 quantization if needed
338:        if is_quantized_kv_cache(self.kv_cache_dtype):
339-            raise NotImplementedError(
340-                "quantization is not supported for encoder attention"
341-            )
342-
--
427-
428:        if is_quantized_kv_cache(self.kv_cache_dtype):
429-            key_cache = key_cache.view(self.fp8_dtype)
430-            value_cache = value_cache.view(self.fp8_dtype)
431-            # q_scale only applies to an fp8 query; this path keeps the query
432-            # in full precision, so a non-1.0 q_scale is not applicable here.
--
542-
543:        is_fp8_kv_cache = is_quantized_kv_cache(self.kv_cache_dtype)
544-        if is_fp8_kv_cache:
545-            key_cache = key_cache.view(self.fp8_dtype)
546-            value_cache = value_cache.view(self.fp8_dtype)
547-
```

The Triton backend (the RDNA fallback per Spike A) also advertises fp8 KV:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/v1/attention/backends/triton_attn.py" | grep -n -B2 -A16 'supported_kv_cache_dtypes: ClassVar'
294-        torch.float32,
295-    ]
296:    supported_kv_cache_dtypes: ClassVar[list[CacheDType]] = [
297-        "auto",
298-        "float16",
299-        "bfloat16",
300-        "fp8",
301-        "fp8_e4m3",
302-        "fp8_e5m2",
303-        "int4_per_token_head",
304-        "int8_per_token_head",
305-        "fp8_per_token_head",
306-    ]
307-
308-    @staticmethod
309-    def get_supported_kernel_block_sizes() -> list[int | MultipleOf]:
310-        return [MultipleOf(16)]
311-
312-    @classmethod
```

Its FP8-KV hardware gate is **CUDA-only** — on ROCm it is not applied:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/v1/attention/backends/triton_attn.py" | sed -n '536,540p'
        if current_platform.is_cuda():
            cap = current_platform.get_device_capability()
            cap_str = cap.as_version_str() if cap is not None else "unknown"
            dev = current_platform.get_device_name()
            if self.kv_cache_dtype.startswith("fp8") and not (
```

(Lines 541-546, omitted from the excerpt, build a suggested fallback dtype
and open the `raise ValueError(` whose message text follows:) `native FP8
(fp8e4nv) requires SM89+` — but that whole raise sits inside the
`if current_platform.is_cuda():` block opened at line 536, so on ROCm it
never runs. The message and the analogous bf16 gate, same pinned fetch:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/v1/attention/backends/triton_attn.py" | grep -n -B2 -A9 'requires SM89+'
547-                    f"FP8 KV cache is not supported by the Triton attention backend "
548-                    f"on {dev} (compute capability {cap_str}); native FP8 (fp8e4nv) "
549:                    f"requires SM89+. Re-run with --kv-cache-dtype {suggested}."
550-                )
551-            if self.kv_cache_dtype == "bfloat16" and not (
552-                current_platform.has_device_capability(80)
553-            ):
554-                raise ValueError(
555-                    f"bfloat16 KV cache is not supported on {dev} (compute capability "
556-                    f"{cap_str}); bfloat16 requires SM80+. Re-run with "
557-                    f"--kv-cache-dtype float16."
558-                )
```

The KV-scale loader (`vllm/model_executor/layers/quantization/kv_cache.py`,
pinned) confirms per-tensor-only on our path and ROCm-aware fnuz handling:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/model_executor/layers/quantization/kv_cache.py" | grep -n -A2 'Only support per-tensor'
126:                    "Only support per-tensor scaling factor for fp8 KV cache"
127-                )
128-
--
174:                "Only support per-tensor scaling factorfor fp8-quantized Q/prob"
175-            )
176-

$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/model_executor/layers/quantization/kv_cache.py" | grep -n 'is_fp8_fnuz'
104:                if current_platform.is_fp8_fnuz():
120:                if current_platform.is_fp8_fnuz():
155:            if current_platform.is_fp8_fnuz():
161:            if current_platform.is_fp8_fnuz():
```

### Q2.6 Web claims (primary-verified unless flagged)

- URL 1 — AMD "vLLM V1 performance optimization" guide
  (rocm.docs.amd.com, fetched 2026-08-16 with curl, HTML stripped for
  quotes):
  https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/optimization/vllm-v1-optimization.html
  - Scope: "This guide helps you maximize vLLM throughput and minimize
    latency on AMD Instinct MI300X, MI325X, MI350X, and MI355X GPUs." The
    quantization guidance (GPTQ/AWQ/Quark/FP8 KV) lives inside that scope.
  - FP8 KV claim: "ROCm supports FP8 KV-cache with both fp8_e4m3 and
    fp8_e5m2 formats on AMD Instinct MI300 series and other CDNA™ GPUs."
    **CDNA-SCOPED — says nothing about gfx1100/RDNA3**, and its e5m2-on-ROCm
    claim is broader than vLLM's own code docstring (ROCm = e4m3 only,
    Q2.3); the stricter first-party docstring wins for planning.
  - Radeon-relevant sentence: the Radeon/fallback attention backends are
    ROCM_ATTN (MHA) / TRITON_MLA (MLA), and "Both work on Radeon GPUs"
    (ROCM_ATTN and TRITON_ATTN).
- URL 2 — vLLM issue #11249 "[Bug]: ROCM with AWQ" (api.github.com,
  fetched 2026-08-16):

```console
$ curl -fsSL -m 30 "https://api.github.com/repos/vllm-project/vllm/issues/11249" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d['number'], d['state'], '| created', d['created_at'], '| closed', d.get('closed_at'), '| labels', [l['name'] for l in d['labels']])
print(d['title'])
"
11249 closed | created 2024-12-17T03:37:54Z | closed 2024-12-18T02:57:04Z | labels ['bug', 'rocm']
[Bug]: ROCM with AWQ
```

  Reporter GPU: "Radeon RX 7900 XTX (gfx1100)"; error was a missing
  `awq_dequantize` CUDA-extension op on a source-built ROCm vLLM 0.6.4.
  AMD's hongxiayang, 2024-12-18: "your installation is fine. It is that the
  quantization now only support MI300x devices. Please run your inference
  with regular non-quantized models." Follow-up 2025-03-04 in the same
  thread: "can you try to use this environment variable: export
  VLLM_USE_TRITON_AWQ=1 — This will use Triton's awq dequantize". The
  pinned-SHA platform code now force-sets that env var (Q2.4), closing the
  historical gap in code — but the docs table still says ❌ (Q2.2).
- URL 3 — vLLM issue #39348 (re-probed fresh 2026-08-16; Spike A's
  correctness precedent):

```console
$ curl -fsSL -m 30 "https://api.github.com/repos/vllm-project/vllm/issues/39348" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d['number'], d['state'], '| created', d['created_at'], '| closed', d.get('closed_at'), '| labels', [l['name'] for l in d['labels']])
print(d['title'])
b=d.get('body') or ''
i=b.find('GPU:')
print(b[i:].split(chr(10))[1])
"
39348 open | created 2026-04-08T21:03:33Z | closed None | labels ['bug', 'rocm', 'stale']
[Bug]: Qwen3.5-9B-AWQ on ROCm/vLLM 0.19.0 can get stuck generating endless "!" inside JSON schema output
09:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Navi 31 [Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M] (rev cc)
```

  I.e. **still open** (bug, rocm, stale), an AWQ-on-ROCm correctness bug on
  a gfx1100-class card (Navi 31).
- WebSearch (2026-08-16; secondary — leads, not evidence): query
  `vLLM kv cache fp8 ROCm gfx1100 RDNA3` surfaced llm-tracker.info's claim
  that vLLM FP8 weights generally do NOT run on RDNA3 stock builds while
  FP8 KV cache is the viable path, and a community fork
  (charlie12345/vLLM_for_AMD, unverified) claiming fp8-KV-on-gfx1100 in a
  Windows port; query `vLLM AWQ GPTQ ROCm gfx1100` surfaced Reddit reports
  of partial AWQ/GPTQ success on 7900 XTX and a Level1Techs MXFP4
  Triton-compile failure on RX 7900 XT. None of these are first-party;
  recorded as directions only.

### Q2.7 Per-method conclusion on gfx1100 (vLLM at `83f591d`)

| Method | Official table (AMD GPU) | Platform code | gfx1100 verdict |
|---|---|---|---|
| FP8 weights (W8A8, the Qwen FP8 repo) | ✅ | `supported_quantization` lists fp8; but `supports_fp8()` = CDNA-or-RDNA4 = **False on gfx1100** | Table ✅ is not gfx1100-specific; code capability gate says no. Unvalidated on RDNA3 — must smoke-test before trusting (Phase 1 gate) |
| KV cache fp8 (e4m3) | fp8_e4m3 "CUDA 11.8+ and ROCm" | ROCM_ATTN + TRITON_ATTN advertise and implement it; per-tensor scales only; RDNA custom paged-attn needs `auto` | Plausible-by-code, unproven on gfx1100; backend fallback expected; Phase 3 test |
| KV cache fp8_e5m2 | CUDA-only | docstring: ROCm = e4m3 only | **CUDA-only — excluded** |
| AWQ | ❌ | listed; auto-forced to Triton AWQ | No Qwen3.8-27B AWQ repo exists anyway (Q1); open bug #39348 on RX7900 — moot |
| GPTQ | ❌ | listed | No repo (Q1) — moot |
| MXFP4 | Marlin row ❌ AMD | `supports_mx()` = gfx95/gfx1250 = False on gfx1100 | Excluded |
| GGUF-as-weights | ✅ | — | Possible weight lever; qwen35-on-ROCm untested — stretch |

- SHA/date probed: vLLM `83f591d7f694a3ca3ae3bf22d646e818a1421872` (all
  quoted code/doc content pinned here; main had moved to
  `1f0e0bf61210346a6bef4ad75172e62554d1b86c` by 2026-08-16T17:13:02Z);
  AMD guide + issues fetched 2026-08-16.

## Q3 llama.cpp KV quant

Pinned at Task 7's SHA — re-verified today as still master HEAD:

```console
$ fetch "https://api.github.com/repos/ggml-org/llama.cpp/commits?per_page=1" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date'])"
4df29be4f4c3673f428170fda944a5b19f743bb8 2026-08-16T12:53:13Z
```

- Probe (brief Step 3 pattern; the raw output is dominated by Windows-argv
  `utf8` noise — lines 1250-1283, three of which contain C++ template
  brackets that this receipt series does not embed — so the same pipeline is
  quoted with that noise filtered out):

```console
$ fetch "https://raw.githubusercontent.com/ggml-org/llama.cpp/4df29be4f4c3673f428170fda944a5b19f743bb8/common/arg.cpp" \
  | grep -n -i 'cache-type\|f8\|q8_0' | grep -v -i utf8 | head -10
309:    GGML_TYPE_Q8_0,
2427:        {"-ctk", "--cache-type-k"}, "TYPE",
2440:        {"-ctv", "--cache-type-v"}, "TYPE",
4023:        {"--spec-draft-type-k", "-ctkd", "--cache-type-k-draft"}, "TYPE",
4036:        {"--spec-draft-type-v", "-ctvd", "--cache-type-v-draft"}, "TYPE",
4484:            params.model.hf_repo = "ggml-org/Qwen2.5-Coder-1.5B-Q8_0-GGUF";
4485:            params.model.hf_file = "qwen2.5-coder-1.5b-q8_0.gguf";
4498:            params.model.hf_repo = "ggml-org/Qwen2.5-Coder-3B-Q8_0-GGUF";
4499:            params.model.hf_file = "qwen2.5-coder-3b-q8_0.gguf";
4512:            params.model.hf_repo = "ggml-org/Qwen2.5-Coder-7B-Q8_0-GGUF";
```

  (Lines 4484+ are Qwen2.5-Coder example-preset hits, not cache types.)
  The allowed type set — members of the `kv_cache_types` vector initialized
  at common/arg.cpp lines 305-315 — and its validation:

```console
$ fetch "https://raw.githubusercontent.com/ggml-org/llama.cpp/4df29be4f4c3673f428170fda944a5b19f743bb8/common/arg.cpp" | grep -n 'GGML_TYPE_F32\|GGML_TYPE_F16\|GGML_TYPE_BF16\|GGML_TYPE_Q8_0\|GGML_TYPE_Q4_0\|GGML_TYPE_Q4_1\|GGML_TYPE_IQ4_NL\|GGML_TYPE_Q5_0\|GGML_TYPE_Q5_1'
306:    GGML_TYPE_F32,
307:    GGML_TYPE_F16,
308:    GGML_TYPE_BF16,
309:    GGML_TYPE_Q8_0,
310:    GGML_TYPE_Q4_0,
311:    GGML_TYPE_Q4_1,
312:    GGML_TYPE_IQ4_NL,
313:    GGML_TYPE_Q5_0,
314:    GGML_TYPE_Q5_1,

$ fetch "https://raw.githubusercontent.com/ggml-org/llama.cpp/4df29be4f4c3673f428170fda944a5b19f743bb8/common/arg.cpp" | grep -n 'static ggml_type kv_cache_type_from_str\|Unsupported cache type'
317:static ggml_type kv_cache_type_from_str(const std::string & s) {
323:    throw std::runtime_error("Unsupported cache type: " + s);

$ fetch "https://raw.githubusercontent.com/ggml-org/llama.cpp/4df29be4f4c3673f428170fda944a5b19f743bb8/common/arg.cpp" | sed -n '2427,2438p'
        {"-ctk", "--cache-type-k"}, "TYPE",
        string_format(
            "KV cache data type for K\n"
            "allowed values: %s\n"
            "(default: %s)",
            get_all_kv_cache_types().c_str(),
            ggml_type_name(params.cache_type_k)
        ),
        [](common_params & params, const std::string & value) {
            params.cache_type_k = kv_cache_type_from_str(value);
        }
    ).set_env("LLAMA_ARG_CACHE_TYPE_K"));
```

  FINDING: the brief's `--cache-type-k/v q8_0|f8` expectation is HALF
  stale. `q8_0` (and q4_0, q4_1, q5_0, q5_1, iq4_nl, bf16) are real
  `--cache-type-k`/`--cache-type-v` values at pinned master — K and V are
  set independently (`-ctk`/`-ctv`, env `LLAMA_ARG_CACHE_TYPE_K`/`_V`,
  plus draft-context variants `--spec-draft-type-k`/`-v` a.k.a.
  `-ctkd`/`-ctvd`, `--cache-type-k/v-draft` — relevant to MTP speculative
  decoding) — but there is NO `f8` cache type upstream at all:

```console
$ fetch "https://raw.githubusercontent.com/ggml-org/llama.cpp/4df29be4f4c3673f428170fda944a5b19f743bb8/common/arg.cpp" | grep -c -i 'f8_e4m3\|f8_e5m2\|F8E4M3\|F8E5M2'
0
$ fetch "https://raw.githubusercontent.com/ggml-org/llama.cpp/4df29be4f4c3673f428170fda944a5b19f743bb8/src/llama-kv-cache.cpp" | grep -c -i 'f8'
0
```

  Any f8 KV idea in llama.cpp lives outside upstream. The RDNA3-specific
  KV-compression effort is TurboQuant, and it is a community port, not
  upstream:

```console
$ curl -fsSL -m 30 "https://api.github.com/repos/ggml-org/llama.cpp/discussions/21526" | python3 -c "import json,sys; d=json.load(sys.stdin); print('title:', d.get('title')); print('created:', d.get('created_at')); print((d.get('body') or '')[:220])"
title: TurboQuant KV Cache Compression — Full HIP/ROCm Port (gfx1100)
created: 2026-04-06T18:48:41Z

I ported TurboQuant KV cache compression (Zandieh et al., ICLR 2026) to HIP/ROCm on clean llama.cpp HEAD (`b8680`). The original fork hung for me on HIP; this clean port onto mainline HEAD does not.

**Repo:** https://g

$ curl -fsSL -m 30 "https://api.github.com/repos/domvox/llama.cpp-turboquant-hip" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['full_name'], '| pushed', d['pushed_at'], '| fork:', d['fork']); print('description:', d['description'])"
domvox/llama.cpp-turboquant-hip | pushed 2026-04-26T06:20:06Z | fork: False
description: TurboQuant KV cache compression for llama.cpp — HIP/ROCm port for AMD RDNA3 (gfx1100)
```

  Cross-check from Q2's pinned vLLM tree: AMD's TurboQuant KV work shows up
  in vLLM's ROCm platform as `turboquant_*` per-layer KV dtypes — i.e.
  AMD's KV-compression investment is vLLM/Instinct-side, not
  llama.cpp-upstream-side:

```console
$ fetch "https://raw.githubusercontent.com/vllm-project/vllm/83f591d7f694a3ca3ae3bf22d646e818a1421872/vllm/platforms/rocm.py" | grep -n -B4 -A4 'turboquant'
639-                    "Using %s backend (selected via --attention-backend).",
640-                    selected_backend.name,
641-                )
642-                return selected_backend.get_path()
643:            # Only tolerate the mismatch for turboquant_* KV-cache layers:
644-            # boundary layers keep the native dtype (served by the selected
645:            # backend) while turboquant_* layers need TURBOQUANT, so no single
646-            # --attention-backend can serve every layer. For any other dtype
647-            # the explicit selection is genuinely invalid -> fail loud.
648-            kv_dtype = attn_selector_config.kv_cache_dtype
649:            if not (kv_dtype is not None and str(kv_dtype).startswith("turboquant")):
650-                raise ValueError(
651-                    f"Selected backend {selected_backend} is not valid for "
652-                    f"this configuration. Reason: {sel_invalid_reasons}"
653-                )
654-            # NOTE: pass a str (not the list) -- info_once hashes its args.
655-            logger.info_once(
656:                "Selected backend %s is incompatible with this turboquant "
657-                "layer (%s); using the auto-selected per-layer backend. "
658-                "Reason: %s",
659-                selected_backend.name,
660-                attn_selector_config.attn_type,
```

- WebSearch (2026-08-16; secondary — leads, not evidence): query
  `llama.cpp --cache-type-k f8_ ROCm HIP` returned summaries claiming
  integer KV types (q8_0/q4_0) work on the HIP backend while fp8 KV is
  CUDA-oriented in llama.cpp forks; consistent with the primary findings
  above (no f8 upstream; q8_0 is a stock type) but HIP-side execution of
  quantized KV was NOT validated by this spike (no GPU run) — Phase 2/3
  must confirm on gfx1100 (HIP or Vulkan backend).
- Conclusion: **upstream llama.cpp (pinned master = HEAD, in release b10453)
  exposes integer/f16-family KV quantization only: f32, f16, bf16, q8_0,
  q4_0, q4_1, iq4_nl, q5_0, q5_1 for K and V independently, unknown strings
  throw "Unsupported cache type". No f8 KV path exists upstream; RDNA3
  TurboQuant KV is a standalone community port (domvox, last push
  2026-04-26) not in mainline.**
- SHA/date probed: llama.cpp `4df29be4f4c3673f428170fda944a5b19f743bb8`
  (2026-08-16); discussion #21526 and domvox repo metadata 2026-08-16.

## Impact

Budget frame: W7900 = gfx1100, 48 GiB VRAM class; measured repo sizes from
Q1. The model is hybrid — 16 attention layers of 64 (48 Gated-DeltaNet
recurrent layers carry fixed-size state, not per-token KV; per Spike B's
config/README quotes), so KV-cache pressure is roughly a quarter of a
same-size pure-attention model, and KV quantization is a second-order lever.

Realistic weight+KV combos for 48 GiB:

1. **llama.cpp route (primary, best-covered)**: every ready-made quant fits —
   Q8_0-class 27.1-29.3 GiB leaves ~19 GiB for KV+ctx even unquantized-KV;
   Q4_K_M-class 15.9-16.6 GiB leaves ~31 GiB. KV lever = `--cache-type-k/v
   q8_0|q4_0` (halves/quarters the 16-layer KV; no f8 upstream). The
   unknown that remains is HIP/Vulkan backend execution of quantized KV on
   gfx1100 — a Phase 2 smoke item, not a blocker to plan around.
2. **vLLM route**: the BF16 base at 51.8 GiB does NOT fit 48 GiB — weight
   quantization is mandatory. The only official quant is the FP8 repo at
   28.7 GiB (~19 GiB headroom), and it is exactly the method whose
   platform capability gate (`supports_fp8()` = CDNA-or-RDNA4) is False on
   gfx1100 while the docs table's AMD ✅ is CDNA-flavored (AMD's own guide
   scopes FP8 to Instinct/CDNA). So Phase 1 must treat "does
   Qwen/Qwen3.8-27B-FP8 even load on gfx1100" as a gating smoke test; if it
   fails, the vLLM weight levers collapse to GGUF-loading (docs ✅ AMD,
   qwen35-on-ROCm untested) or leaving vLLM for llama.cpp.
3. **vLLM KV fp8 (e4m3)**: advertised by both ROCM_ATTN and TRITON_ATTN and
   wired for per-tensor scales, but AMD scopes it to CDNA and the RDNA
   custom paged-attention kernel requires `auto` — expect backend fallback
   and treat as an experiment, not a plan dependency. e5m2 KV and
   per-attention-head scaling are CUDA-only (excluded).

Phase 3 benchmark sweep (what the matrix must cover, minimum):

- llama.cpp: {UD-Q4_K_XL or Q4_K_M, Q6_K, Q8_0-class} x {f16, q8_0, q4_0}
  K/V cache (K and V separately where time allows) x {-fa on/off}, fixed
  context ladder (e.g. 32k/128k/262k) — record max capacity, decode tok/s,
  and a correctness smoke (JSON/structured output, cf. bug #39348's
  failure mode).
- vLLM (contingent on the FP8-load gate): {FP8 weights} x {auto, fp8}
  kv-cache-dtype x {ROCM_ATTN, TRITON_ATTN} — record whether fp8 KV
  actually engages on gfx1100 and at what accuracy cost (per-tensor scale
  1.0 vs `--calculate-kv-scales`).
- Record as gaps, not blockers: MXFP4/AWQ/GPTQ on gfx1100 (unsupported
  platform-gated), fp8_e5m2 KV (CUDA-only), llama.cpp f8 KV (does not
  exist upstream), TurboQuant (community fork only).
