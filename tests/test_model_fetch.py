from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "02-fetch-model.sh"


def test_script_wires_manifest_and_modelscope_endpoint():
    src = SCRIPT.read_text()
    assert "configs/artifact-manifest.json" in src
    assert "modelscope.cn" in src
    # Verification must check both size and sha256 from the manifest.
    assert "size_bytes" in src and "sha256" in src


def test_script_is_resumable_and_idempotent():
    src = SCRIPT.read_text()
    assert "--continue-at -" in src or "-C -" in src
    assert "already verified" in src or "skip" in src.lower()


def test_manifest_fetch_file_list_matches():
    src = SCRIPT.read_text()
    assert '["sets"][set_name]["files"]' in src


def test_fetch_script_is_set_aware():
    src = SCRIPT.read_text()
    assert 'SET="${SET:-bf16}"' in src
    assert '"sets"' in src and '["sets"]' in src
