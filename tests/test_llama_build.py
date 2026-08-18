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


# --------------------------------------------------- Vulkan build (v0.1.2 T2)

VK_SCRIPT = ROOT / "scripts" / "06-build-llama-vulkan.sh"


def test_vulkan_build_script_contract():
    src = VK_SCRIPT.read_text()
    # Backend selection is explicit: Vulkan on, HIP off, separate build dir.
    assert "-DGGML_VULKAN=ON" in src
    assert "-DGGML_HIP=OFF" in src
    assert "build-714-vk" in src
    # Same source tree + commit pin as the HIP build, read from the stack
    # (never a hardcode), and the HIP build dir must not be configured.
    assert '["llama_cpp"]["commit"]' in src
    assert "ROCM_PATH" not in src and "AMDGPU_TARGETS" not in src
    # Prereq checks with actionable apt hints (docs/build.md at the pin:
    # libvulkan-dev glslc spirv-headers + mesa-vulkan-drivers vulkan-tools
    # for the runtime ICD / vulkaninfo).
    for token in ("vulkaninfo", "vulkan-tools", "libvulkan-dev", "glslc",
                  "spirv-headers", "mesa-vulkan-drivers"):
        assert token in src, f"vk build must check/hint {token!r}"
    # Post-build verification: version smoke + device listing + ICD record.
    assert "--version" in src
    assert "--list-devices" in src
    # Fingerprint (idempotence) records the vulkan backend + active ICD.
    assert "write_llama_vulkan_build_fingerprint" in src
    assert "llama-build-fingerprint.json" in src


def test_vulkan_build_record_merges_and_never_replaces():
    # Same merge/write-if-changed discipline as the HIP build record: the
    # llama_cpp_vulkan dict must survive rebuilds and re-runs must leave a
    # clean tree (the mtp_depth discovery record is not rebuild evidence —
    # it must never be clobbered).
    src = VK_SCRIPT.read_text()
    assert 'stack["llama_cpp_vulkan"] = {' not in src
    assert 'setdefault("llama_cpp_vulkan", {})' in src
    assert "if new_text !=" in src


def test_stack_records_vulkan_build_and_mtp_depth_discovery():
    # Host-execution record (written by 06-build-llama-vulkan.sh): backend
    # identity, the same commit pin as HIP, the build dir, the ACTIVE ICD
    # (RADV vs AMD proprietary is part of the evidence), and the MTP depth
    # discovery at the pin.
    stack = json.loads((ROOT / "configs" / "validated-stack.json").read_text())
    vk = stack["llama_cpp_vulkan"]
    assert vk["backend"] == "vulkan"
    assert vk["commit"] == stack["llama_cpp"]["commit"]
    assert vk["build_dir"].endswith("build-714-vk")
    assert vk["icd"] and isinstance(vk["icd"], str)  # e.g. "RADV"
    assert vk["built_at"]
    depth = vk["mtp_depth"]
    assert depth["flag"] == "--spec-draft-n-max"
    assert isinstance(depth["default"], int)
    # The depth finding is recorded EITHER way (expressible or fixed):
    # "mtp4_expressible" is the branch point the runner + matrix rely on.
    assert isinstance(depth["mtp4_expressible"], bool)
    assert depth["evidence"]
