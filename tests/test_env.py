import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

FAKE_ROCMINFO = """Agent 1 - CPU
  Marketing Name: AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S
Agent 2 - AMD GFX Device
  Name:                    gfx1151
  Segment: GLOBAL; FLAGS: COARSE GRAINED
  Size: 33554432(32GiB)
"""

FAKE_ROCMINFO_NO_AMD = """Agent 1 - CPU
  Name:                    gfx1200
  Marketing Name: Other GPU
"""


def make_fake_rocm(tmp_path, version="7.14.0", rocminfo=FAKE_ROCMINFO):
    prefix = tmp_path / "rocm"
    (prefix / ".info").mkdir(parents=True)
    (prefix / ".info" / "version").write_text(version + "\n")
    bin_dir = prefix / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("hipcc", "#!/usr/bin/env bash\necho 'HIP version: %s'\n" % version),
        ("rocminfo", "#!/usr/bin/env bash\ncat <<'EOF'\n%sEOF\n" % rocminfo),
    ):
        f = bin_dir / name
        f.write_text(body)
        f.chmod(0o755)
    return prefix


def run_check_env(prefix):
    import os

    env = dict(os.environ, ROCM_PREFIX=str(prefix), KERNEL_RELEASE="6.17.0-1032-oem")
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / "00-check-env.sh")],
        capture_output=True,
        text=True,
        env=env,
    )


def test_check_env_passes_with_fake_714_gfx1151_prefix(tmp_path):
    r = run_check_env(make_fake_rocm(tmp_path))
    assert r.returncode == 0, f"STDOUT:{r.stdout}\nSTDERR:{r.stderr}"
    assert "OK: base environment ready for Qwen3.8-27B on gfx1151" in r.stdout


def test_check_env_fails_on_wrong_gpu(tmp_path):
    r = run_check_env(make_fake_rocm(tmp_path, rocminfo=FAKE_ROCMINFO_NO_AMD))
    assert r.returncode != 0
    assert "gfx1200" in r.stderr


def test_check_env_fails_on_unvalidated_rocm_version(tmp_path):
    r = run_check_env(make_fake_rocm(tmp_path, version="6.3.4"))
    assert r.returncode != 0
    assert "7.14" in r.stderr


@pytest.mark.gpu
def test_check_env_passes_on_this_host():
    r = subprocess.run(
        ["bash", str(ROOT / "scripts" / "00-check-env.sh")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"STDOUT:{r.stdout}\nSTDERR:{r.stderr}"
