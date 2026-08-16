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
