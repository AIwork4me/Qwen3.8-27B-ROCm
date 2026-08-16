import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_manifest_has_verified_rocm_tarball_fields():
    host = json.loads((ROOT / "configs" / "rocm-7.14.json").read_text())["host"]
    assert host["rocm_version"] == "7.14.0"
    assert host["archive"]["url"] == (
        "https://repo.amd.com/rocm/tarball-multi-arch/"
        "therock-dist-linux-gfx1151-7.14.0.tar.gz"
    )
    assert host["archive"]["size_bytes"] == 1713449440
    assert re.fullmatch(r"[0-9a-f]{64}", host["archive"]["sha256"])


def test_installer_reads_manifest_and_hardcodes_no_hash():
    src = (ROOT / "scripts" / "install-rocm-7.14.sh").read_text()
    assert "configs/rocm-7.14.json" in src
    assert "host.archive.sha256" in src
    # No literal hash in the script: the manifest is the single source of truth.
    assert not re.search(r"[0-9a-f]{64}", src)
