from pathlib import Path

import json

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_has_vllm_group_with_therock_index():
    src = (ROOT / "pyproject.toml").read_text()
    # NOTE: the task brief asserted the literal "[dependency-groups.vllm]",
    # but a dotted table header is invalid for PEP 735 groups (they must be
    # arrays; uv rejects the header with a TOML parse error — verified). Parse
    # the declared group instead: same intent, satisfiable by valid TOML.
    data = __import__("tomllib").loads(src)
    assert "vllm" in data["dependency-groups"]
    assert "therock-gfx1151" in src
    assert "https://rocm.nightlies.amd.com/v2/gfx1151/" in src


def test_ci_group_stays_cpu_only():
    data = __import__("tomllib").loads((ROOT / "pyproject.toml").read_text())
    ci = data["dependency-groups"]["ci"]
    assert not any("torch" in d for d in ci)


def test_build_script_pins_repo_commit_and_patches():
    src = (ROOT / "scripts" / "01-build-vllm.sh").read_text()
    assert "vllm-project/vllm" in src
    assert "validated-stack.json" in src
    assert "PYTORCH_ROCM_ARCH=gfx1151" in src
    assert "--no-build-isolation" in src
    assert "amdsmi" in src


@pytest.mark.gpu
def test_vllm_imports_and_registers_qwen3_5():
    import vllm  # noqa: F401
    from vllm.model_executor.models.registry import _MULTIMODAL_MODELS
    assert "Qwen3_5ForConditionalGeneration" in _MULTIMODAL_MODELS


def test_dflash2_patch_is_listed_in_the_stack_manifest():
    stack = json.loads((ROOT / "configs" / "validated-stack.json").read_text())
    assert "patches/vllm-dflash2-pr52816.diff" in stack["vllm"]["patches"]


def test_dflash2_patch_file_exists_and_ports_the_pr():
    # Upstream PR vllm-project/vllm#52816 ("[Spec Decode] DFlash2: local
    # convolution + candidate selector"; OPEN at port time 2026-08-21, based
    # on a main newer than our pin 4d2a68d) ported onto the pin: the new
    # draft module + V2 speculator, the registry entry (the bare pin rejects
    # DFlash2DraftModel), the V2-forcing config, and the worker routing.
    p = ROOT / "patches" / "vllm-dflash2-pr52816.diff"
    assert p.is_file()
    text = p.read_text()
    assert "DFlash2DraftModel" in text
    for f in ("vllm/model_executor/models/qwen3_dflash2.py",
              "vllm/v1/worker/gpu/spec_decode/dflash2/speculator.py",
              "vllm/model_executor/models/registry.py",
              "vllm/config/vllm.py",
              "vllm/v1/worker/gpu/spec_decode/__init__.py"):
        assert f in text, f"{f} missing from the dflash2 patch"
    # The port deviates from the PR only where the PR's base is newer than
    # the pin: the routing insertion is hand-ported (documented in the patch
    # header); upstream test churn (tests/test_config.py) is not carried.
    assert "tests/test_config.py" not in text


def test_build_script_makes_patch_created_files_visible_to_the_guard():
    # The build script's tracked-modification guard compares the tree's
    # changed files against the union of patch numstats. Files CREATED by a
    # patch land as untracked — invisible to `git diff --name-only` — so the
    # dflash2 patch (3 new files) would trip the guard on a fresh clone.
    # The guard must also enumerate untracked files (ls-files --others,
    # exclude-standard keeps build artifacts out via vLLM's own .gitignore).
    src = (ROOT / "scripts" / "01-build-vllm.sh").read_text()
    assert "ls-files --others --exclude-standard" in src
