import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECEIPT = ROOT / "docs" / "results" / "rocm-7.14" / "vllm-validation.md"
STACK = ROOT / "configs" / "validated-stack.json"


def test_receipt_exists_with_required_sections():
    text = RECEIPT.read_text()
    for section in ("## Boot", "## Greedy smoke", "## MTP", "## Context probe"):
        assert section in text
    assert "OK" in text  # the greedy anchor appears verbatim


def test_stack_records_validation_outcome():
    vllm = json.loads(STACK.read_text())["vllm"]
    v = vllm["validated"]
    assert isinstance(v["text"], bool)
    assert isinstance(v["mtp"], bool)
    assert v["receipt"].endswith("vllm-validation.md")


def test_receipt_has_vision_section_and_stack_flag():
    text = RECEIPT.read_text()
    assert "## Vision" in text
    v = json.loads(STACK.read_text())["vllm"]["validated"]
    assert isinstance(v.get("vision"), bool)


def test_readme_serving_table_exists_and_is_honest():
    text = (ROOT / "README.md").read_text()
    assert "vLLM" in text
    assert "llama.cpp" in text or "GGUF" in text


def test_dflash2_receipt_exists_with_required_sections():
    # DFlash2 validation track (v0.1.9): boot receipts incl. the two failed
    # attempts (unpatched architecture refusal; 262144 KV infeasibility),
    # the patch port record, greedy smoke, and the KV/ctx finding.
    receipt = ROOT / "docs" / "results" / "rocm-7.14" / "dflash2-validation.md"
    text = receipt.read_text()
    for section in ("## Boot", "## Greedy smoke", "## Patch port",
                    "## KV budget"):
        assert section in text, f"{section} missing from the dflash2 receipt"
    assert "OK" in text  # the greedy anchor appears verbatim


def test_stack_records_dflash2_outcome():
    v = json.loads(STACK.read_text())["vllm"]["validated"]
    assert isinstance(v.get("dflash"), bool)
    assert v.get("dflash_receipt", "").endswith("dflash2-validation.md")
