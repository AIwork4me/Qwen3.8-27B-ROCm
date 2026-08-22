import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_set():
    return json.loads((ROOT / "configs" / "artifact-manifest.json").read_text())["sets"]["bf16"]


def test_bf16_set_covers_all_18_shards_and_sum_is_measured_total():
    s = load_set()
    shards = [f for f in s["files"] if f["path"].startswith("model-") and f["path"].endswith(".safetensors")]
    assert len(shards) == 18
    assert all(f["path"].endswith(f"-of-00018.safetensors") for f in shards)
    total = sum(f["size_bytes"] for f in shards)
    # API fact (ModelScope repo/files API, master, queried 2026-08-16): the
    # 18 published shards sum to 55,563,006,776 bytes = 51.7 GiB, matching
    # the spike probe table in docs/results/spike/quant-kv.md (Q1 "Sizes and
    # formats", base-repo row). The 49.8 GiB figure used in earlier receipts
    # (validated-stack.json, quant-kv.md combos table) is a parameter-derived
    # estimate, not the published file-size sum. The manifest records API
    # sizes verbatim — record-not-invent — so the asserted total is 51.7.
    assert round(total / 2**30, 1) == 51.7


def test_bf16_set_has_repo_revision_dest_and_support_files():
    s = load_set()
    assert s["repository"] == "Qwen/Qwen3.8-27B"
    assert s["host"] == "modelscope"
    assert len(s["revision"]) == 40
    assert s["dest"] == "models/Qwen3.8-27B"
    paths = {f["path"] for f in s["files"]}
    for required in ("config.json", "tokenizer.json", "tokenizer_config.json",
                     "model.safetensors.index.json", "chat_template.jinja",
                     "preprocessor_config.json"):
        assert required in paths


def test_every_file_entry_has_size_and_sha256():
    s = load_set()
    for f in s["files"]:
        assert isinstance(f["size_bytes"], int) and f["size_bytes"] > 0
        sha = f["sha256"]
        assert isinstance(sha, str) and len(sha) == 64 and sha == sha.lower()


def test_gguf_set_has_default_quant_and_mmproj():
    s = json.loads((ROOT / "configs" / "artifact-manifest.json").read_text())["sets"]["gguf"]
    assert s["repository"] == "unsloth/Qwen3.8-27B-GGUF"
    assert s["host"] == "modelscope"
    assert len(s["revision"]) == 40
    assert s["dest"] == "models/Qwen3.8-27B-GGUF"
    paths = [f["path"] for f in s["files"]]
    assert any("UD-Q4_K_XL" in p and p.endswith(".gguf") for p in paths)
    assert any("mmproj" in p.lower() for p in paths)
    for f in s["files"]:
        assert f["size_bytes"] > 0 and len(f["sha256"]) == 64


def test_dflash2_set_is_the_speculative_draft_model():
    # DFlash2 draft (block-diffusion speculator for the vLLM path): ships as
    # exactly config.json + model.safetensors (HF repo incoai/Qwen3.8-27B-DFlash2,
    # mirrored on ModelScope; queried 2026-08-21). No tokenizer files — vLLM
    # uses the target model's tokenizer.
    s = json.loads((ROOT / "configs" / "artifact-manifest.json").read_text())["sets"]["dflash2-bf16"]
    assert s["repository"] == "incoai/Qwen3.8-27B-DFlash2"
    assert s["host"] == "modelscope"
    assert len(s["revision"]) == 40
    assert s["dest"] == "models/Qwen3.8-27B-DFlash2"
    paths = {f["path"] for f in s["files"]}
    assert paths == {"config.json", "model.safetensors"}
    for f in s["files"]:
        assert f["size_bytes"] > 0 and len(f["sha256"]) == 64
    # API fact (ModelScope repo/files API, master, queried 2026-08-21): the
    # two files sum to 3,848,819,135 bytes = 3.6 GiB.
    total = sum(f["size_bytes"] for f in s["files"])
    assert round(total / 2**30, 1) == 3.6
