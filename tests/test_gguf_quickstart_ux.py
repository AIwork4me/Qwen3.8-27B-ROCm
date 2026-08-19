import json
import os
import socket
import subprocess

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "gguf-quickstart.sh"


def test_quickstart_hardcodes_validated_defaults_only():
    src = SCRIPT.read_text()
    # Default quant and ctx come from the validated stack, not a guess.
    assert "validated-stack.json" in src or "artifact-manifest.json" in src
    assert "UD-Q4_K_XL" in src
    assert "--ctx-size" in src


def test_quickstart_server_contract():
    src = SCRIPT.read_text()
    assert "--port 8080" in src or "8080" in src
    assert "-ngl 99" in src
    # UX: the script must tell the user where to point their client and how to verify.
    assert "/health" in src or "health" in src
    assert "v1/chat/completions" in src


def test_quickstart_mtp_is_opt_in_and_labeled():
    src = SCRIPT.read_text()
    assert "WITH_MTP" in src
    assert "draft-mtp" in src or "spec-type" in src


def test_receipt_and_stack_record_vision():
    receipt = (ROOT / "docs" / "results" / "rocm-7.14" / "gguf-validation.md").read_text()
    assert "## Vision" in receipt
    stack = json.loads((ROOT / "configs" / "validated-stack.json").read_text())
    v = stack["llama_cpp"]["validated"]
    assert isinstance(v.get("vision"), bool)


def test_readme_gguf_row_is_measured_now():
    text = (ROOT / "README.md").read_text()
    assert "GGUF" in text and "llama.cpp" in text


# --------------------------------------------- v0.1.2 Task 2: Vulkan opt-in

def test_quickstart_backend_default_is_hip_unchanged():
    # DEFAULT UNCHANGED (plan Task 2): the stock boot still resolves the
    # pinned HIP build; Vulkan is strictly an explicit opt-in.
    src = SCRIPT.read_text()
    assert 'BACKEND="${BACKEND:-hip}"' in src
    # Default binary class is the HIP build-714, expressed as the default
    # branch of the backend case, and the hip miss hint points at 05-build.
    assert "build-714/bin/llama-server" in src
    assert "05-build-llama.sh" in src


def test_quickstart_backend_vulkan_opt_in():
    src = SCRIPT.read_text()
    assert "build-714-vk/bin/llama-server" in src
    # The opt-in is labeled experimental and defers to the verdicts.
    assert "experimental" in src.lower()
    assert "06-build-llama-vulkan.sh" in src
    # Unknown backend values are refused (no silent fallthrough to hip).
    assert "hip|vulkan" in src


def test_quickstart_backend_vulkan_opt_in_is_downgraded_2026_08_19():
    # CONTROLLER RULING (2026-08-19, v0.1.4, SUPERSEDES the 2026-08-18
    # promotion): the clean depth-1 same-day pairing (vulkan 14.53 vs hip
    # 13.86 tok/s = +4.81%; aggregate -13.31%) plus cross-day variance
    # removed the recommendation basis — the echo now presents BACKEND=vulkan
    # as an AVAILABLE experimental opt-in, NOT a recommendation, while hip
    # WITH_MTP=1 is called out as both the default and the recommended
    # path. The mapping behind the downgrade is enforced in
    # tests/test_verdicts.py.
    src = SCRIPT.read_text()
    assert "AVAILABLE experimental opt-in" in src
    assert "NOT recommended" in src
    assert "project ruling 2026-08-19 supersedes" in src
    assert "the 2026-08-18 promotion" in src
    assert "+4.81%" in src and "-13.31%" in src
    assert "14.53" in src and "13.86" in src
    # The promotion wording is gone everywhere.
    assert "RECOMMENDED OPT-IN" not in src
    assert "recommended OPT-IN" not in src
    # The hip default-branch echo names the recommended path.
    assert "default AND recommended path" in src
    assert "13.0 tok/s" in src
    # Conservative framing is kept: the downgrade never rewrites the
    # default or hides the caveats.
    assert "experimental" in src.lower()
    assert 'BACKEND="${BACKEND:-hip}"' in src


def test_quickstart_spec_depth_passthrough():
    # SPEC_DEPTH=<n> maps to the depth flag discovered at the pin
    # (--spec-draft-n-max; see configs/validated-stack.json
    # llama_cpp_vulkan.mtp_depth). Only valid with WITH_MTP=1.
    src = SCRIPT.read_text()
    assert "SPEC_DEPTH" in src
    assert "--spec-draft-n-max" in src


def test_quickstart_refuses_invalid_spec_depth(tmp_path):
    # The script's own SPEC_DEPTH validation, exercised end-to-end on its
    # refusal paths (2026-08-18, v0.1.3 debt fix). CI-safe: LLAMA_SERVER is
    # an executable stub and GGUF_FILE a scratch file (absolute path,
    # unknown to the manifest -> the size gate is skipped), so no build and
    # no model are needed; the validation fires before anything launches.
    # Values read from the script's validation: non-numeric ("abc") and <1
    # ("0") are refused; "5" is a legal depth (>= 1), so it is not used.
    stub = tmp_path / "llama-server-stub"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    gguf = tmp_path / "scratch.gguf"
    gguf.write_text("x")
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        port = str(sock.getsockname()[1])
    finally:
        sock.close()

    def run_with(value):
        env = dict(os.environ, WITH_MTP="1", SPEC_DEPTH=value,
                   LLAMA_SERVER=str(stub), GGUF_FILE=str(gguf), PORT=port)
        return subprocess.run(["bash", str(SCRIPT)], capture_output=True,
                              text=True, timeout=60, cwd=ROOT, env=env)

    r = run_with("abc")
    assert r.returncode == 1
    assert "SPEC_DEPTH must be a positive integer (got 'abc')" in \
        (r.stdout + r.stderr)

    r = run_with("0")
    assert r.returncode == 1
    assert "SPEC_DEPTH must be >= 1 (got 0)" in (r.stdout + r.stderr)

    # Boundary: a valid depth is NOT refused by the validation (the boot
    # proceeds to the stub, which exits 0).
    r = run_with("4")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SPEC_DEPTH must" not in (r.stdout + r.stderr)
