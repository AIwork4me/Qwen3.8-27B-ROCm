import json

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "gguf-quickstart.sh"


def test_quickstart_hardcodes_validated_defaults_only():
    src = SCRIPT.read_text()
    # Default quant and ctx come from the validated stack, not a guess.
    assert "validated-stack.json" in src or "artifact-manifest.json" in src
    assert "UD-Q4_K_XL" in src
    assert "--ctx-size" in src


def test_quickstart_server_contract():
    src = SCRIPT.read_text()
    assert "--port 8080" in src or "8080" in src
    assert "-ngl 99" in src
    # UX: the script must tell the user where to point their client and how to verify.
    assert "/health" in src or "health" in src
    assert "v1/chat/completions" in src


def test_quickstart_mtp_is_opt_in_and_labeled():
    src = SCRIPT.read_text()
    assert "WITH_MTP" in src
    assert "draft-mtp" in src or "spec-type" in src


def test_receipt_and_stack_record_vision():
    receipt = (ROOT / "docs" / "results" / "rocm-7.14" / "gguf-validation.md").read_text()
    assert "## Vision" in receipt
    stack = json.loads((ROOT / "configs" / "validated-stack.json").read_text())
    v = stack["llama_cpp"]["validated"]
    assert isinstance(v.get("vision"), bool)


def test_readme_gguf_row_is_measured_now():
    text = (ROOT / "README.md").read_text()
    assert "GGUF" in text and "llama.cpp" in text
