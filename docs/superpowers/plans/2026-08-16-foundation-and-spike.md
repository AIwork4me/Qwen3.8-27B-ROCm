# Qwen3.8-27B-ROCm Foundation + Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the repository foundation (CPU-safe CI, ROCm 7.14.0 installer, environment checker) and complete the upstream-support spike, producing an evidence-backed decision table that gates the follow-up vLLM/GGUF/benchmark plans.

**Architecture:** Reuse the proven Muse-Glimmer-30B-ROCm asset pattern (manifest-driven installer, fail-fast env checks, pytest-gated scripts) with content adapted for Qwen3.8-27B. The spike answers four upstream questions with downloadable receipts committed under `docs/results/spike/`; its machine-readable output (`configs/spike-findings.json`) is the contract consumed by the next plans.

**Tech Stack:** bash (shellcheck-clean), Python 3.12, uv, pytest, GitHub Actions (CPU-only CI), ModelScope/GitHub raw APIs for spike probes.

**Spec:** `docs/superpowers/specs/2026-08-16-qwen3.8-27b-rocm-design.md`

## Global Constraints

- Target model: `Qwen/Qwen3.8-27B`, architecture `Qwen3_5ForConditionalGeneration`, `model_type: qwen3_5`, vocab 248,320, max position embeddings 262,144, BF16 ≈ 52 GiB across 18 safetensors. Requires transformers 5.8.0.dev0 per its config.
- Validated platform: AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S, `gfx1151` only. W7900 (`gfx1100`) is 🚧 Planned, evidence-gated — never claim it.
- System ROCm at `/opt/rocm` is 7.2.1 and must remain untouched; ROCm 7.14.0 installs side-by-side at `~/rocm-7.14.0` from the official AMD gfx1151 tarball: URL `https://repo.amd.com/rocm/tarball-multi-arch/therock-dist-linux-gfx1151-7.14.0.tar.gz`, size `1713449440` bytes, SHA256 `2567d5e34e470db104a62a02c36aa770cb0430175e48c1c46df0eefc05e1d77c`.
- Kernel floor: `6.16.9` (host runs `6.17.0-1032-oem`).
- CI must be CPU-safe: no `torch` in the `ci` dependency group; GPU-requiring tests are marked `@pytest.mark.gpu` and excluded in CI.
- License: Apache-2.0. Evidence-first: every claim links to a receipt; negative results are kept as findings.
- Reusable source tree (read-only reference): `/home/amd/Desktop/muse-rocm/`. Copy files from there verbatim unless a step says otherwise; do not modify that tree.
- Repo: `/home/amd/Desktop/Qwen3.8-27B-ROCm`, git identity already set repo-locally (`AIwork4me <AIwork4me@qq.com>`), branch `main`.

---

### Task 1: Repository scaffold with CPU-safe CI

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `LICENSE` (copy from `/home/amd/Desktop/muse-rocm/LICENSE`)
- Create: `README.md`
- Create: `.github/workflows/ci.yml`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: none (first task).
- Produces: a pytest harness invoked as `uv run --no-sync pytest` (CI runs `uv run --no-sync pytest -m "not gpu and not server"`); markers `gpu` and `server` are registered; the `ci` dependency group is installable with `uv sync --only-group ci`.

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_smoke.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/amd/Desktop/Qwen3.8-27B-ROCm && python3 -m pytest tests/test_smoke.py -v 2>&1 | tail -5`
Expected: FAIL / collection error — `pyproject.toml` or files missing.

- [ ] **Step 3: Write the scaffold files**

`pyproject.toml`:

```toml
[project]
name = "qwen3-8-27b-rocm"
version = "0.1.0"
description = "Reproducible ROCm 7.14 reference for Qwen3.8-27B on AMD Radeon, gfx1151 first"
requires-python = ">=3.12"
license = "Apache-2.0"

[dependency-groups]
ci = [
    "pytest>=8",
    "shellcheck-py>=0.10",
    "actionlint-py>=1.7",
    "jsonschema>=4",
]

[tool.pytest.ini_options]
markers = [
    "gpu: requires a ROCm GPU on this host",
    "server: requires a running inference server",
]
addopts = "-m 'not gpu and not server'"
```

Copy the license and ignore file:

```bash
cp /home/amd/Desktop/muse-rocm/LICENSE /home/amd/Desktop/Qwen3.8-27B-ROCm/LICENSE
cp /home/amd/Desktop/muse-rocm/.gitignore /home/amd/Desktop/Qwen3.8-27B-ROCm/.gitignore
```

`README.md`:

```markdown
# Qwen3.8-27B-ROCm

> Work in progress. Goal: the reproducible RDNA reference for
> [Qwen/Qwen3.8-27B](https://modelscope.cn/models/Qwen/Qwen3.8-27B) on
> AMD ROCm 7.14.0 — method: Adapt → Validate → Benchmark → Explain →
> Reproduce.
>
> Status: foundation + upstream-support spike phase. Validated platform:
> AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S (`gfx1151`). W7900 (`gfx1100`)
> is planned, evidence-gated.

Design spec: `docs/superpowers/specs/2026-08-16-qwen3.8-27b-rocm-design.md`
```

`.github/workflows/ci.yml`:

```yaml
name: fast-ci
on: [push, pull_request]

permissions:
  contents: read

jobs:
  no-gpu:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
          cache-dependency-glob: uv.lock

      - name: Sync lightweight CI dependencies
        run: uv sync --only-group ci --locked

      - name: Assert GPU runtime is not installed
        run: uv run --no-sync python -c "import importlib.util; assert importlib.util.find_spec('torch') is None"

      - name: Bash syntax
        run: find scripts -name '*.sh' -print0 | xargs -0 -r bash -n

      - name: ShellCheck
        run: find scripts -name '*.sh' -print0 | xargs -0 -r uv run --no-sync shellcheck -x

      - name: GitHub Actions semantics
        run: uv run --no-sync actionlint

      - name: No-GPU tests
        run: uv run --no-sync pytest -m "not gpu and not server" -v
```

- [ ] **Step 4: Lock dependencies and run tests**

```bash
cd /home/amd/Desktop/Qwen3.8-27B-ROCm
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv sync --only-group ci
uv run --no-sync pytest -v
uv run --no-sync actionlint
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore LICENSE README.md .github/workflows/ci.yml tests/test_smoke.py uv.lock
git commit -m "feat: repo scaffold with CPU-safe CI harness"
```

---

### Task 2: Manifest-driven ROCm 7.14.0 installer

**Files:**
- Create: `configs/rocm-7.14.json`
- Create: `scripts/install-rocm-7.14.sh` (copy from muse-rocm, two edits)
- Test: `tests/test_install_manifest.py`

**Interfaces:**
- Consumes: `ci` pytest group from Task 1.
- Produces: `bash scripts/install-rocm-7.14.sh [ROCM714_PREFIX]` installs ROCm 7.14.0 at `~/rocm-7.14.0` (default), reading URL/size/SHA256 from `configs/rocm-7.14.json` keys `host.archive.url`, `host.archive.size_bytes`, `host.archive.sha256`, `host.rocm_version`. Env overrides: `ROCM714_PREFIX`, `ROCM714_ARCHIVE`, `ROCM714_MANIFEST` (test seam).

- [ ] **Step 1: Write the failing test**

`tests/test_install_manifest.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_install_manifest.py -v`
Expected: FAIL — `configs/rocm-7.14.json` missing (FileNotFoundError).

- [ ] **Step 3: Create manifest and adapted installer**

`configs/rocm-7.14.json`:

```json
{
  "host": {
    "kernel": "6.17.0-1032-oem",
    "rocm_version": "7.14.0",
    "distribution_target": "gfx1151",
    "distribution_scope": "Official AMD gfx1151 tarball; AMD ROCm 7.14 release notes list AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S as gfx1151; Qwen3.8-27B workload validation is independent project evidence",
    "archive": {
      "url": "https://repo.amd.com/rocm/tarball-multi-arch/therock-dist-linux-gfx1151-7.14.0.tar.gz",
      "size_bytes": 1713449440,
      "sha256": "2567d5e34e470db104a62a02c36aa770cb0430175e48c1c46df0eefc05e1d77c"
    },
    "release_notes": {
      "url": "https://rocm.docs.amd.com/en/docs-7.14.0/about/release-notes.html",
      "date": "2026-07-15"
    }
  }
}
```

Copy the installer and point it at the new manifest:

```bash
mkdir -p scripts
cp /home/amd/Desktop/muse-rocm/scripts/install-rocm-7.14.sh \
   /home/amd/Desktop/Qwen3.8-27B-ROCm/scripts/install-rocm-7.14.sh
```

In the copy, apply exactly two edits:
1. Replace `MANIFEST="${ROCM714_MANIFEST:-$HERE/configs/rocm-7.14-gguf-validation.json}"` with `MANIFEST="${ROCM714_MANIFEST:-$HERE/configs/rocm-7.14.json}"`.
2. Update the header comment line 5 from `configs/rocm-7.14-gguf-validation.json` to `configs/rocm-7.14.json`.

- [ ] **Step 4: Run tests and lints**

```bash
mkdir -p scripts
uv run --no-sync pytest tests/test_install_manifest.py -v
uv run --no-sync shellcheck -x scripts/install-rocm-7.14.sh
find scripts -name '*.sh' -print0 | xargs -0 -r bash -n
```

Expected: 2 passed; shellcheck clean.

- [ ] **Step 5: Commit**

```bash
git add configs/rocm-7.14.json scripts/install-rocm-7.14.sh tests/test_install_manifest.py
git commit -m "feat: manifest-driven ROCm 7.14.0 gfx1151 installer"
```

---

### Task 3: Environment checker with fake-prefix test seam

**Files:**
- Create: `scripts/lib/version.sh` (copy from muse-rocm, verbatim)
- Create: `scripts/lib/rocm.sh` (copy from muse-rocm, verbatim)
- Create: `scripts/00-check-env.sh` (adapted, single `base` profile)
- Create: `configs/validated-stack.json`
- Test: `tests/test_env.py`

**Interfaces:**
- Consumes: `scripts/lib/rocm.sh` exports `ROCM_PREFIX`, `ROCM_PATH`, `ROCM_SELECTION_SOURCE` via `resolve_rocm_prefix`; `detect_rocm_version "$prefix"` prints the version (reads `$prefix/.info/version` first, falls back to `bin/hipcc --version`).
- Produces: `bash scripts/00-check-env.sh` exits 0 iff host tools (`git curl python3`) exist, ROCm resolves to 7.14.x (warn+pass on 7.2.x, fail otherwise), kernel ≥ 6.16.9, `rocminfo` reports `gfx1151`, and the GPU-visible pool is printed. Final line on success: `OK: base environment ready for Qwen3.8-27B on gfx1151`. Respects `ROCM_PREFIX` override for tests.

- [ ] **Step 1: Write the failing test**

`tests/test_env.py`:

```python
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

    env = dict(os.environ, ROCM_PREFIX=str(prefix))
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_env.py -v`
Expected: FAIL — `scripts/00-check-env.sh` missing (subprocess FileNotFoundError / non-zero).

- [ ] **Step 3: Copy libs and write the checker**

```bash
mkdir -p scripts/lib
cp /home/amd/Desktop/muse-rocm/scripts/lib/version.sh scripts/lib/version.sh
cp /home/amd/Desktop/muse-rocm/scripts/lib/rocm.sh scripts/lib/rocm.sh
```

`configs/validated-stack.json`:

```json
{
  "host": {
    "minimum_kernel": "6.16.9",
    "gpu_arch": "gfx1151",
    "validated_platform": "AMD Ryzen AI MAX+ PRO 395 / Radeon 8060S",
    "rocm_recommended": "7.14.0",
    "rocm_historical_fallback": "7.2.1"
  },
  "model": {
    "id": "Qwen/Qwen3.8-27B",
    "architecture": "Qwen3_5ForConditionalGeneration",
    "model_type": "qwen3_5",
    "max_position_embeddings": 262144,
    "bf16_safetensors_gib": 49.8
  }
}
```

`scripts/00-check-env.sh` (adapted from muse-rocm, `base` profile only):

```bash
#!/usr/bin/env bash
set -euo pipefail

fail() {
    echo "FAIL: $1" >&2
    echo "    see docs/troubleshooting.md" >&2
    exit 1
}
warn() { echo "WARNING: $1" >&2; }
missing_tool_fail() {
    echo "FAIL: required command not found: $1" >&2
    echo "  Debian/Ubuntu:  sudo apt-get install $1" >&2
    echo "  Fedora/RHEL:    sudo dnf install $1" >&2
    echo "  Arch:           sudo pacman -S $1" >&2
    echo "    see docs/troubleshooting.md" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: bash scripts/00-check-env.sh

Checks the base environment for Qwen3.8-27B on gfx1151: host tools,
ROCm toolchain (7.14.x recommended, 7.2.x historical fallback), kernel
floor, GPU arch, GPU-visible memory pool.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v python3 >/dev/null 2>&1 || missing_tool_fail python3
# shellcheck source=scripts/lib/version.sh
source "$ROOT/scripts/lib/version.sh"
# shellcheck source=scripts/lib/rocm.sh
source "$ROOT/scripts/lib/rocm.sh"

read_manifest() {
    python3 - "$ROOT/configs/validated-stack.json" "$1" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for key in sys.argv[2].split("."):
    value = value[key]
print(value)
PY
}

MIN_KERNEL="$(read_manifest host.minimum_kernel)"
GPU_ARCH="$(read_manifest host.gpu_arch)"

echo "Environment profile: base (Qwen3.8-27B, gfx1151)"

echo "host tools:"
for tool in git curl python3; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo "  tool $tool: $(command -v "$tool")"
    else
        missing_tool_fail "$tool"
    fi
done

resolve_rocm_prefix || exit 1
export PATH="$ROCM_PREFIX/bin:$PATH"
rocm_ver="$(detect_rocm_version "$ROCM_PREFIX")"
print_selected_rocm "$rocm_ver"

case "$rocm_ver" in
    7.14.*) ;;
    7.2.*) warn "using the historical ROCm $rocm_ver fallback; ROCm 7.14 is recommended." ;;
    *) fail "base profile expects ROCm 7.14.x (recommended) or historical 7.2.x; got '$rocm_ver'. Run scripts/install-rocm-7.14.sh to install 7.14, or set ROCM_PREFIX to an existing 7.14.x/7.2.x prefix." ;;
esac

krel="$(uname -r)"
echo "kernel: $krel"
version_at_least "$krel" "$MIN_KERNEL" ||
    fail "project Strix Halo host floor is kernel >= $MIN_KERNEL (docs/troubleshooting.md#uma-bug); got $krel"

# Buffer rocminfo output. A live rocminfo piped to grep -q can receive SIGPIPE
# under pipefail, so parsing always uses the complete captured output.
rocminfo_out="$("$ROCM_PREFIX/bin/rocminfo" 2>/dev/null || true)"
if ! grep -q "$GPU_ARCH" <<<"$rocminfo_out"; then
    observed_gpus="$( { grep -oE 'gfx[0-9]+' <<<"$rocminfo_out" || true; } | sort -u | paste -sd' ' -)"
    fail "$GPU_ARCH not found in $ROCM_PREFIX/bin/rocminfo output; observed GPU id(s): ${observed_gpus:-none}. This project is validated on gfx1151 (AMD Strix Halo) only — see docs/hardware-validation.md for non-gfx1151 platforms."
fi

vram_kb="$(awk -v arch="$GPU_ARCH" '
  $0 ~ ("Name:[[:space:]]+" arch) { gpu = 1 }
  gpu && /Segment:[[:space:]]+GLOBAL; FLAGS: COARSE GRAINED/ { coarse = 1; next }
  coarse && /Size:/ { size = $2; sub(/\(.*/, "", size); print size; exit }
' <<<"$rocminfo_out")"
[[ "$vram_kb" =~ ^[0-9]+$ ]] ||
    fail "could not read $GPU_ARCH global memory pool from rocminfo"
pool_gib=$(( vram_kb / 1024 / 1024 ))
echo "GPU-visible pool: ${pool_gib} GiB (quantized-weights serving targets need a large share of this; BF16 weights ~49.8 GiB do not fit — see README)"

echo "OK: base environment ready for Qwen3.8-27B on gfx1151"
```

- [ ] **Step 4: Run tests and lints**

```bash
uv run --no-sync pytest tests/test_env.py -v
uv run --no-sync shellcheck -x scripts/00-check-env.sh scripts/lib/*.sh
```

Expected: 3 passed, 1 skipped (`test_check_env_passes_on_this_host` runs only with `-m gpu`); shellcheck clean.

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/version.sh scripts/lib/rocm.sh scripts/00-check-env.sh configs/validated-stack.json tests/test_env.py
git commit -m "feat: fail-fast environment checker with fake-prefix test seam"
```

---

### Task 4: Install ROCm 7.14.0 on the host and record validated-stack evidence

**Files:**
- Modify: `configs/validated-stack.json` (add `install` evidence block)
- Create: `docs/results/spike/README.md`

**Interfaces:**
- Consumes: `scripts/install-rocm-7.14.sh` (Task 2), `scripts/00-check-env.sh` (Task 3).
- Produces: `~/rocm-7.14.0` populated (bin/hipcc, bin/rocminfo, `.info/version` = `7.14.0`); `configs/validated-stack.json["install"]` with prefix, verified sha256, date, kernel; `docs/results/spike/README.md` index for spike receipts. Follow-up tasks read `install.prefix` as the ROCm 7.14 location.

- [ ] **Step 1: Install (host, ~1.6 GiB download; needs ≥ 10.7 GiB free on $HOME and $TMPDIR)**

```bash
cd /home/amd/Desktop/Qwen3.8-27B-ROCm
bash scripts/install-rocm-7.14.sh
```

Expected output ends with `Installed ROCm 7.14.0 at /home/amd/rocm-7.14.0` and a `HIP version: 7.14.0` line. If disk preflight fails, free space or set `ROCM714_ARCHIVE`/`ROCM714_PREFIX` per the script's error message.

- [ ] **Step 2: Verify the install through the checker**

```bash
export ROCM_PREFIX="$HOME/rocm-7.14.0"
bash scripts/00-check-env.sh
uv run --no-sync pytest -m gpu tests/test_env.py -v
```

Expected: `OK: base environment ready for Qwen3.8-27B on gfx1151`; gpu test passes.

- [ ] **Step 3: Record evidence**

Append to `configs/validated-stack.json` (new top-level key after `host`):

```json
"install": {
  "prefix": "/home/amd/rocm-7.14.0",
  "verified_sha256": "2567d5e34e470db104a62a02c36aa770cb0430175e48c1c46df0eefc05e1d77c",
  "installed_on": "2026-08-16",
  "kernel_at_install": "6.17.0-1032-oem"
}
```

(Adjust `installed_on` to the actual date and `prefix` to `$HOME/rocm-7.14.0` expansion if different.)

Create `docs/results/spike/README.md`:

```markdown
# Spike receipts

Upstream-support reconnaissance for Qwen3.8-27B (`Qwen3_5ForConditionalGeneration`).
Each probe's command and raw evidence lives in the linked file; conclusions
feed `configs/spike-findings.json` and the decision table.

- `vllm.md` — vLLM + transformers support for qwen3_5 (Spike A)
- `gguf.md` — llama.cpp / GGUF support and existing quants (Spike B)
- `quant-kv.md` — official quantizations + KV-cache dtype levers on gfx1151 (Spike C)

Method: probe at a recorded commit/date; quote the exact evidence; absence
of evidence is recorded as absence, never assumed away.
```

- [ ] **Step 4: Verify JSON still parses and suite is green**

Run: `uv run --no-sync pytest -v`
Expected: all previous tests pass (JSON loads fine).

- [ ] **Step 5: Commit**

```bash
git add configs/validated-stack.json docs/results/spike/README.md
git commit -m "feat: host ROCm 7.14.0 install evidence + spike receipts index"
```

---

### Task 5: Spike A — vLLM + transformers upstream support

**Files:**
- Create: `docs/results/spike/vllm.md`

**Interfaces:**
- Consumes: none (pure recon).
- Produces: `docs/results/spike/vllm.md` answering: (1) does transformers main support `qwen3_5`? (2) does vLLM main/nightly register `Qwen3_5ForConditionalGeneration`? (3) is MTP wired for it in vLLM? Each answer cites a commit SHA or dated raw-file URL with quoted evidence. Task 8 consumes the conclusions.

- [ ] **Step 1: Probe transformers support**

```bash
curl -fsSL https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/auto/configuration_auto.py \
  | grep -n 'qwen3_5\|Qwen3_5' | head -20
curl -fsSL "https://api.github.com/repos/huggingface/transformers/commits?path=src/transformers/models/qwen3_5&per_page=1" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date']) if d else print('no qwen3_5 model dir')"
```

Record: model dir exists or not, latest commit SHA, and whether a release (vs main-only) contains it (`curl -fsSL https://raw.githubusercontent.com/huggingface/transformers/v5.8.0/src/transformers/models/auto/configuration_auto.py | grep -c qwen3_5` — adjust tag if v5.8.0 does not exist yet).

- [ ] **Step 2: Probe vLLM registry**

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/model_executor/models/registry.py \
  | grep -n -i 'qwen3_5\|qwen3_next' | head -20
```

Also check the multimodal mix-in path (`vllm/model_executor/models/qwen3_5.py` raw fetch — 404 means absent) and MTP wiring (`grep -n -i 'mtp\|qwen3_5' vllm/config.py` style on `vllm/spec_decode/` if the arch exists). Record the vLLM commit SHA probed:

```bash
curl -fsSL "https://api.github.com/repos/vllm-project/vllm/commits?per_page=1" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date'])"
```

- [ ] **Step 3: Probe the AMD ROCm angle**

Check whether vLLM's ROCm docs / AMD Day-0 article covers `Qwen3.8` or only `Qwen3.5/3.6` (web search: `vLLM qwen3_5 ROCm gfx1151`), and note the latest vLLM version that AMD's Day-0 Qwen 3.5 support references. Record URLs.

- [ ] **Step 4: Write the receipt document**

`docs/results/spike/vllm.md` template (fill with actual evidence; keep every quoted line verbatim):

```markdown
# Spike A: vLLM + transformers support for qwen3_5 — DATE

## Q1: transformers support
- Probe: <exact curl command>
- Evidence: <quoted grep output>
- Conclusion: <supported on main / released in vX.Y / absent>
- SHA/date probed: <sha> <date>

## Q2: vLLM architecture registration
- Probe: <exact curl command>
- Evidence: <quoted grep output>
- Conclusion: <registered as ... / absent at probed commit>

## Q3: MTP support in vLLM for qwen3_5
- Evidence + conclusion.

## Q4: ROCm/gfx1151 angle
- URLs + what they do/don't claim about Qwen3.8-27B on RDNA.

## Impact
- <one paragraph: what this means for the vLLM path plan>
```

- [ ] **Step 5: Commit**

```bash
git add docs/results/spike/vllm.md
git commit -m "docs(spike): vLLM/transformers qwen3_5 support receipts"
```

---

### Task 6: Spike B — llama.cpp / GGUF support

**Files:**
- Create: `docs/results/spike/gguf.md`

**Interfaces:**
- Consumes: none.
- Produces: `docs/results/spike/gguf.md` answering: (1) does llama.cpp master support the `qwen3_5` architecture (linear attention + MTP + vision)? (2) do Qwen3.8-27B GGUF quants exist on ModelScope/HF already? (3) is `convert_hf_to_gguf.py` viable for it? Cites commit SHA / repo URLs with quoted evidence. Task 8 consumes the conclusions.

- [ ] **Step 1: Probe llama.cpp architecture tables**

```bash
for f in src/llama-arch.cpp src/llama-model.cpp tools/mqmd/mqmd.cpp; do
  echo "== $f =="
  curl -fsSL "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/$f" \
    | grep -n -i 'qwen3_5\|qwen3_next\|qwen3n' | head -10 || true
done
curl -fsSL "https://api.github.com/repos/ggml-org/llama.cpp/commits?per_page=1" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['sha'], d[0]['commit']['committer']['date'])"
```

(If any file 404s, note it and continue — layout drift is itself evidence of the commit to quote.)

- [ ] **Step 2: Probe existing GGUF quants**

```bash
for repo in Qwen/Qwen3.8-27B-GGUF Qwen/Qwen3.8-27B-MXFP4-GGUF unsloth/Qwen3.8-27B-GGUF bartowski/Qwen3.8-27B-GGUF; do
  echo "== $repo =="
  curl -s -o /dev/null -w '%{http_code}\n' "https://modelscope.cn/api/v1/models/$repo" 
  curl -s -o /dev/null -w '%{http_code}\n' "https://huggingface.co/api/models/$repo"
done
curl -s "https://modelscope.cn/api/v1/dolphin/models?PageSize=10&PageNumber=1&Search=Qwen3.8-27B%20GGUF" | head -c 1500
```

(HTTP 200 = exists; 404 = absent. Record every code.)

- [ ] **Step 3: Probe convert + quantize viability signals**

Check `convert_hf_to_gguf.py` for the arch:

```bash
curl -fsSL "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/convert_hf_to_gguf.py" \
  | grep -n -i 'qwen3_5\|Qwen3_5ForConditionalGeneration' | head -10 || echo "no qwen3_5 in converter"
```

Search llama.cpp issues for qwen3_5 / Qwen3.8 support threads (web search `site:github.com ggml-org llama.cpp qwen3_5 OR Qwen3.8`); record issue numbers and status.

- [ ] **Step 4: Write the receipt document**

Use the same section style as Task 5 (`docs/results/spike/gguf.md`): `## Q1 llama.cpp arch support`, `## Q2 existing quants`, `## Q3 converter viability`, `## Impact` — each with probe command, quoted evidence, conclusion, SHA/date.

- [ ] **Step 5: Commit**

```bash
git add docs/results/spike/gguf.md
git commit -m "docs(spike): llama.cpp/GGUF qwen3_5 support receipts"
```

---

### Task 7: Spike C — official quantizations + KV-cache dtype levers

**Files:**
- Create: `docs/results/spike/quant-kv.md`

**Interfaces:**
- Consumes: none.
- Produces: `docs/results/spike/quant-kv.md` answering: (1) official/community AWQ/GPTQ/FP8/MXFP4 quant variants of Qwen3.8-27B available today (exact repo ids + sizes); (2) vLLM support status for that quant method on ROCm/gfx1151; (3) KV-cache `fp8` support on gfx1151 in vLLM and llama.cpp (`--cache-type-k/v q8_0|f8` etc.). Task 8 consumes the conclusions.

- [ ] **Step 1: Probe quant variant repositories**

```bash
for repo in Qwen/Qwen3.8-27B-AWQ Qwen/Qwen3.8-27B-GPTQ-Int4 Qwen/Qwen3.8-27B-FP8 Qwen/Qwen3.8-27B-MXFP4; do
  for host in modelscope huggingface; do
    if [ "$host" = modelscope ]; then url="https://modelscope.cn/api/v1/models/$repo"; else url="https://huggingface.co/api/models/$repo"; fi
    printf '%s %s -> ' "$host" "$repo"; curl -s -o /dev/null -w '%{http_code}\n' "$url"
  done
done
```

For each 200, capture the file list and total size:

```bash
curl -s "https://modelscope.cn/api/v1/models/Qwen/Qwen3.8-27B-AWQ/repo/files?Revision=master" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); fs=d['Data']['Files']; print('GiB:', round(sum(f['Size'] for f in fs if f['Path'].endswith('.safetensors'))/2**30,1))"
```

- [ ] **Step 2: Probe vLLM quant + KV-dtype support on ROCm**

Fetch and grep the vLLM docs/code probed in Task 5 (same commit):

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm/main/docs/features/quantization/index.md | grep -n -i 'awq\|gptq\|mxfp4\|fp8' | head
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/config/cache.py | grep -n -i 'fp8\|dtype' | head
```

Plus a web search: `vLLM kv cache fp8 ROCm gfx1151 RDNA3` and `vLLM AWQ GPTQ ROCm gfx1151`. Record claims + URLs; note explicitly which claims are CUDA-only.

- [ ] **Step 3: Probe llama.cpp KV quant path**

```bash
curl -fsSL "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/common/arg.cpp" \
  | grep -n -i 'cache-type\|f8\|q8_0' | head -10
```

(Web-search `llama.cpp --cache-type-k f8_ ROCm HIP` for any RDNA caveats; record.)

- [ ] **Step 4: Write the receipt document**

`docs/results/spike/quant-kv.md`, sections: `## Q1 quant variants today` (table: repo id, host, status code, total GiB), `## Q2 vLLM quant/KV on ROCm`, `## Q3 llama.cpp KV quant`, `## Impact` (which weight+KV combos are realistic for 32 GiB UMA and what the follow-up benchmark plan must sweep).

- [ ] **Step 5: Commit**

```bash
git add docs/results/spike/quant-kv.md
git commit -m "docs(spike): quant variants + KV-cache dtype receipts"
```

---

### Task 8: Spike decision table + machine-readable findings

**Files:**
- Create: `schemas/spike-findings.schema.json`
- Create: `configs/spike-findings.json`
- Create: `docs/results/spike/decision-table.md`
- Test: `tests/test_spike_findings.py`

**Interfaces:**
- Consumes: the three receipt docs from Tasks 5–7.
- Produces: `configs/spike-findings.json` validated by `schemas/spike-findings.schema.json`; the follow-up plans (vLLM path, GGUF path, benchmark matrix) read its `paths.vllm.status`, `paths.gguf.status`, `quant_variants[]`, `kv_cache_fp8` fields to decide full-validation vs recorded-gap tasks.

- [ ] **Step 1: Write the failing test**

`tests/test_spike_findings.py`:

```python
import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    return json.loads((ROOT / name).read_text())


def iter_strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_strings(value)
    elif isinstance(node, str):
        yield node


def test_findings_validate_against_schema():
    jsonschema.validate(load("configs/spike-findings.json"), load("schemas/spike-findings.schema.json"))


def test_findings_cover_all_four_questions():
    findings = load("configs/spike-findings.json")
    for path in ("vllm", "gguf"):
        entry = findings["paths"][path]
        assert entry["status"] in {"supported", "partial", "absent"}
        assert entry["evidence"].startswith("docs/results/spike/")
    assert isinstance(findings["quant_variants"], list)
    assert findings["kv_cache_fp8"]["status"] in {"supported", "partial", "absent"}
    assert len(findings["receipts"]) >= 3


def test_no_unfilled_placeholders_committed():
    for value in iter_strings(load("configs/spike-findings.json")):
        assert "<" not in value, f"unfilled placeholder value committed: {value!r}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_spike_findings.py -v`
Expected: FAIL — schema/findings files missing.

- [ ] **Step 3: Write schema, findings, and decision table**

`schemas/spike-findings.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Spike findings",
  "type": "object",
  "required": ["checked_at", "paths", "quant_variants", "kv_cache_fp8", "receipts"],
  "properties": {
    "checked_at": {"type": "string", "format": "date"},
    "paths": {
      "type": "object",
      "required": ["vllm", "gguf"],
      "properties": {
        "vllm": {"$ref": "#/$defs/pathStatus"},
        "gguf": {"$ref": "#/$defs/pathStatus"}
      },
      "additionalProperties": false
    },
    "quant_variants": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["repo_id", "host", "method", "total_gib"],
        "properties": {
          "repo_id": {"type": "string"},
          "host": {"enum": ["modelscope", "huggingface"]},
          "method": {"enum": ["awq", "gptq", "fp8", "mxfp4", "gguf", "other"]},
          "total_gib": {"type": "number", "exclusiveMinimum": 0}
        },
        "additionalProperties": false
      }
    },
    "kv_cache_fp8": {
      "type": "object",
      "required": ["status", "evidence"],
      "properties": {
        "status": {"enum": ["supported", "partial", "absent"]},
        "evidence": {"type": "string"}
      },
      "additionalProperties": false
    },
    "receipts": {
      "type": "array",
      "minItems": 1,
      "items": {"type": "string"}
    }
  },
  "additionalProperties": false,
  "$defs": {
    "pathStatus": {
      "type": "object",
      "required": ["status", "evidence", "implication"],
      "properties": {
        "status": {"enum": ["supported", "partial", "absent"]},
        "evidence": {"type": "string"},
        "implication": {"type": "string"}
      },
      "additionalProperties": false
    }
  }
}
```

`configs/spike-findings.json` — fill every field from the Tasks 5–7 receipts; the structure (values below are placeholders-in-form-only: replace each `<...>` with real evidence, do not commit `<` characters):

```json
{
  "checked_at": "<YYYY-MM-DD>",
  "paths": {
    "vllm": {
      "status": "<supported|partial|absent>",
      "evidence": "docs/results/spike/vllm.md",
      "implication": "<one sentence: full validation now | recorded gap + upstream issue>"
    },
    "gguf": {
      "status": "<supported|partial|absent>",
      "evidence": "docs/results/spike/gguf.md",
      "implication": "<one sentence>"
    }
  },
  "quant_variants": [
    {"repo_id": "<org/name>", "host": "modelscope", "method": "awq", "total_gib": 0.0}
  ],
  "kv_cache_fp8": {
    "status": "<supported|partial|absent>",
    "evidence": "docs/results/spike/quant-kv.md"
  },
  "receipts": [
    "docs/results/spike/vllm.md",
    "docs/results/spike/gguf.md",
    "docs/results/spike/quant-kv.md"
  ]
}
```

`docs/results/spike/decision-table.md`:

```markdown
# Spike decision table — DATE

| Path / lever | Status | Evidence | Plan implication |
|---|---|---|---|
| vLLM | <status> | [vllm.md](vllm.md) | <full validation / recorded gap + upstream issue N> |
| GGUF / llama.cpp | <status> | [gguf.md](gguf.md) | <...> |
| Official quants | <count found> | [quant-kv.md](quant-kv.md) | <which variant the benchmark plan sweeps first> |
| KV fp8 | <status> | [quant-kv.md](quant-kv.md) | <swept as matrix variable / recorded gap> |

## Next plans gated on this table

1. vLLM path plan — scope per row 1.
2. GGUF path plan — scope per row 2.
3. Benchmark matrix plan — variables per rows 3–4.
```

- [ ] **Step 4: Run tests and lints**

Run: `uv run --no-sync pytest tests/test_spike_findings.py -v && uv run --no-sync pytest -v`
Expected: all pass; whole suite green.

- [ ] **Step 5: Commit**

```bash
git add schemas/spike-findings.schema.json configs/spike-findings.json docs/results/spike/decision-table.md tests/test_spike_findings.py
git commit -m "feat: spike decision table + machine-readable findings"
```

---

## Verification (whole plan)

After Task 8, on the host:

```bash
uv run --no-sync pytest -v                      # CPU suite green
uv run --no-sync pytest -m gpu tests/ -v        # host GPU tests green
uv run --no-sync shellcheck -x scripts/*.sh scripts/lib/*.sh
bash scripts/00-check-env.sh                    # OK line on ROCm 7.14 + gfx1151
git log --oneline                               # ≥ 8 commits, one per task
```

All five commands green ⇒ this plan is complete; write the follow-up plans from `configs/spike-findings.json`.
