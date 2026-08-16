import json
import re
from pathlib import Path

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
