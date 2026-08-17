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


def test_build_record_merges_and_never_replaces_llama_cpp():
    # The one-pass rehearsal (2026-08-17) caught the build script replacing
    # the whole llama_cpp dict, silently stripping llama_cpp.validated (the
    # gguf-quickstart ctx default + the validation receipt tests rely on)
    # and dirtying the tree on every re-run. It must merge build facts into
    # the existing dict and skip the write when nothing changed.
    src = (ROOT / "scripts" / "05-build-llama.sh").read_text()
    assert 'stack["llama_cpp"] = {' not in src, "whole-dict replace strips validated"
    assert 'setdefault("llama_cpp", {})' in src, "must merge into the existing dict"
    assert "if new_text !=" in src, "must be write-if-changed (idempotent clean tree)"
    stack = json.loads((ROOT / "configs" / "validated-stack.json").read_text())
    assert stack["llama_cpp"]["validated"]["ctx_size"] == 131072
