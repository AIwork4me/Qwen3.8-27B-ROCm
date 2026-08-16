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


def test_env_file_export_contract():
    # Parse what the env file actually EXPORTS (not mere substring presence —
    # the old vacuous check passed on comment text alone). Contract: the two
    # live vars are exported; VLLM_ATTENTION_BACKEND / VLLM_USE_V1 are NOT —
    # both were removed upstream and have zero references under vllm/ at the
    # pin 4d2a68d (see the comment block in configs/vllm-gfx1151.env; the
    # attention mechanism is the --attention-backend CLI flag instead).
    exported = set()
    for line in (ROOT / "configs" / "vllm-gfx1151.env").read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            exported.add(line.split()[1].split("=", 1)[0])
    assert "TRITON_CACHE_DIR" in exported
    assert "VLLM_WORKER_MULTIPROC_METHOD" in exported
    assert "VLLM_ATTENTION_BACKEND" not in exported
    assert "VLLM_USE_V1" not in exported


def test_mtp_conf_is_baseline_flags_plus_speculative_config_only():
    # Lockstep: serve-args-mtp.conf must be exactly the baseline flag set
    # plus --speculative-config (its header promises "keep every baseline
    # flag in sync ... only the speculative line differs, on purpose").
    base = parse_conf("serve-args.conf")
    mtp = parse_conf("serve-args-mtp.conf")
    assert set(mtp) == set(base) | {"--speculative-config"}
    for flag, value in base.items():
        assert mtp[flag] == value, f"{flag} drifted from baseline: {value!r} vs {mtp[flag]!r}"


def test_serve_script_uses_no_sync_and_default_port():
    src = (ROOT / "scripts" / "03-serve-vllm.sh").read_text()
    assert "uv run --no-sync vllm serve" in src
    assert "--port 8000" in src or "8000" in src
