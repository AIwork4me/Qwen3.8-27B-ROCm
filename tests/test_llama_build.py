import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_build_script_pins_toolchain_and_arch():
    src = (ROOT / "scripts" / "05-build-llama.sh").read_text()
    assert "ggml-org/llama.cpp" in src
    assert "GPU_TARGETS=gfx1151" in src or "AMDGPU_TARGETS=gfx1151" in src
    assert "GGML_HIP=ON" in src
    assert "validated-stack.json" in src
    assert "llama_build_fingerprint" in src


def test_stack_records_llama_cpp_after_build():
    stack = json.loads((ROOT / "configs" / "validated-stack.json").read_text())
    lc = stack.get("llama_cpp")
    assert lc and len(lc["commit"]) == 40
    assert lc["build_arch"] == "gfx1151"
    assert lc["backend"] == "HIP"
