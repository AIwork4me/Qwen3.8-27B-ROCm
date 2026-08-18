import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_platform_index_entries_validate_and_receipts_exist():
    schema = json.loads((ROOT / "schemas" / "community-platform.schema.json").read_text())
    index = json.loads((ROOT / "configs" / "community" / "platforms.json").read_text())
    # The planned shape used a file:// $ref to the schema file; embedding the
    # loaded schema as `items` is the equivalent validation without a
    # resolution base (permitted simplification, same coverage: every entry
    # must validate against schemas/community-platform.schema.json).
    jsonschema.validate(index, {"type": "object", "required": ["platforms"],
                                "properties": {"platforms": {"type": "array",
                                "items": schema}}})
    # The index is designed to grow (docs/hardware-validation.md: one entry
    # per platform); what must hold for EVERY entry is that the committed
    # receipts tree actually backs it — env-check receipt present and at
    # least one raw runner-written cell JSON under the listed directories.
    for entry in index["platforms"]:
        env_check = ROOT / entry["receipts"]["env_check"]
        assert env_check.is_file(), f"{entry['id']}: missing env-check receipt {env_check}"
        n_cells = 0
        for listed in entry["receipts"]["cells"]:
            listed_dir = ROOT / listed
            assert listed_dir.is_dir(), f"{entry['id']}: missing receipts dir {listed_dir}"
            cells_dir = listed_dir / "cells"
            n_cells += len(list(cells_dir.glob("*.json"))) if cells_dir.is_dir() else 0
        assert n_cells > 0, f"{entry['id']}: no raw cell JSONs under the listed receipts dirs"


def test_platform_schema_requires_full_evidence_packet():
    schema = json.loads((ROOT / "schemas" / "community-platform.schema.json").read_text())
    good = {
        "id": "w7900-gfx1100-rocm714", "submitter": "colleague", "submitted": "2026-09-01",
        "gpu": {"arch": "gfx1100", "marketing_name": "Radeon PRO W7900", "vram_gib": 48},
        "stack": {"rocm": "7.14.0", "kernel": "6.17.0", "pytorch_source": "official rocm wheel 2.9",
                  "vllm_source": "upstream main @<sha>", "llama_cpp_commit": "<40-hex>"},
        "validated": {"gguf": True, "vllm": False},
        "receipts": {"env_check": "docs/results/matrix-714/community/w7900/env-check.txt",
                     "cells": ["docs/results/matrix-714/community/w7900/"]},
    }
    jsonschema.validate(good, schema)
    for missing in ("gpu", "stack", "validated", "receipts", "submitter"):
        bad = {k: v for k, v in good.items() if k != missing}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


def test_community_profile_accepts_foreign_gpu_via_seam(tmp_path):
    fake = tmp_path / "rocm"
    (fake / ".info").mkdir(parents=True)
    (fake / ".info" / "version").write_text("7.14.0\n")
    (fake / "bin").mkdir()
    (fake / "bin" / "hipcc").write_text("#!/usr/bin/env bash\necho 'HIP version: 7.14.0'\n")
    (fake / "bin" / "hipcc").chmod(0o755)
    (fake / "bin" / "rocminfo").write_text(
        "#!/usr/bin/env bash\ncat <<'EOF'\nName: gfx1100\nMarketing Name: AMD Radeon PRO W7900\n"
        "Segment: GLOBAL; FLAGS: COARSE GRAINED\nSize: 50331648(48GiB)\nEOF\n")
    (fake / "bin" / "rocminfo").chmod(0o755)
    import os
    r = subprocess.run(["bash", str(ROOT / "scripts" / "00-check-env.sh"), "--profile", "community"],
                       capture_output=True, text=True,
                       env=dict(os.environ, ROCM_PREFIX=str(fake), KERNEL_RELEASE="6.17.0-1032-oem"))
    assert r.returncode == 0, r.stderr
    assert "COMMUNITY-PROFILE: arch=gfx1100" in r.stdout
    assert "NOT project-validated" in r.stdout


def test_hardware_matrix_block_generated():
    text = (ROOT / "README.md").read_text()
    assert "<!-- BEGIN GENERATED: hardware-matrix -->" in text
    assert "🧪" in text or "Community" in text
    assert "gfx1151" in text and "gfx1100" in text  # gfx1100 as planned row label


def test_hardware_matrix_renderer_handles_community_entries(tmp_path):
    """Beyond the brief: the renderer must render 🧪 rows (with receipt
    links) from configs/community/platforms.json when entries appear, and
    drop the static 🚧 planned row for an arch that has community evidence."""
    spec = importlib.util.spec_from_file_location(
        "render_hardware_matrix", ROOT / "scripts" / "render-hardware-matrix.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    entry = {
        "id": "w7900-gfx1100-rocm714", "submitter": "colleague",
        "submitted": "2026-09-01",
        "gpu": {"arch": "gfx1100", "marketing_name": "Radeon PRO W7900",
                "vram_gib": 48},
        "stack": {"rocm": "7.14.0", "kernel": "6.17.0",
                  "pytorch_source": "official rocm wheel 2.9",
                  "vllm_source": "upstream main @<sha>",
                  "llama_cpp_commit": "<40-hex>"},
        "validated": {"gguf": True, "vllm": False},
        "receipts": {
            "env_check": "docs/results/matrix-714/community/w7900-gfx1100-rocm714/env-check.txt",
            "cells": ["docs/results/matrix-714/community/w7900-gfx1100-rocm714/"]},
    }
    index = tmp_path / "platforms.json"
    index.write_text(json.dumps({"platforms": [entry]}))
    renderer.PLATFORMS = index
    block = renderer.render_block()
    assert "🧪 Community validated — GGUF" in block
    assert "gfx1100" in block
    assert "[env-check.txt](docs/results/matrix-714/community/w7900-gfx1100-rocm714/env-check.txt)" in block
    assert "🚧 Planned" not in block, (
        "a community entry for an arch must supersede its planned row")


def test_render_readme_blocks_check_covers_hardware_matrix():
    """The plan's verification gate calls render-readme-blocks.py --check;
    one regen must cover ALL README blocks including hardware-matrix."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "render-readme-blocks.py"),
         "--check"],
        capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stderr + r.stdout
