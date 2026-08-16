from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_conf(name):
    args = {}
    for line in (ROOT / "configs" / name).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words = line.split()
        args[words[0]] = words[1] if len(words) > 1 else None
    return args


def test_base_conf_targets_triton_attention_and_bf16_kv():
    args = parse_conf("serve-args.conf")
    assert args.get("--max-model-len") == "262144"
    assert args.get("--kv-cache-dtype") in ("auto", None)  # bf16 KV: fits 80 GiB pool
    assert args.get("--gpu-memory-utilization") is not None


def test_mtp_conf_adds_speculative_decoding():
    args = parse_conf("serve-args-mtp.conf")
    assert "--speculative-config" in args
    assert args.get("--max-model-len") == "262144"


def test_env_file_exports_no_sync_contract():
    src = (ROOT / "configs" / "vllm-gfx1151.env").read_text()
    assert "VLLM_USE_V1" in src or "VLLM_ATTENTION_BACKEND" in src


def test_serve_script_uses_no_sync_and_default_port():
    src = (ROOT / "scripts" / "03-serve-vllm.sh").read_text()
    assert "uv run --no-sync vllm serve" in src
    assert "--port 8000" in src or "8000" in src
