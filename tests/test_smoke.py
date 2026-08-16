import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_declares_project_and_ci_group():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "qwen3-8-27b-rocm"
    ci_deps = data["dependency-groups"]["ci"]
    assert any(d.startswith("pytest") for d in ci_deps)


def test_license_and_readme_exist():
    assert (ROOT / "LICENSE").is_file()
    assert (ROOT / "README.md").is_file()
