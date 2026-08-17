"""Final-review guard for scripts/gen-matrix.py (2026-08-17).

A plain regeneration re-emits the DECLARATION — every cell back to
`planned`/`dropped` — which would silently clobber the measurement manifest
(20 committed `measured` cells). The generator therefore refuses to write
while any committed cell is `measured` (naming the cells it would reset),
offers `--check` (regeneration a no-op vs committed file -> exit 0, else 1),
and `--force` for a deliberate reset. METHODOLOGY.md §8 documents the guarded
instruction.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN_MATRIX = ROOT / "scripts" / "gen-matrix.py"
MATRIX = ROOT / "docs" / "results" / "matrix-714" / "matrix.json"


def load_module():
    spec = importlib.util.spec_from_file_location("gen_matrix", GEN_MATRIX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sandbox(mod, tmp_path):
    """Point the generator's OUT at a sandbox copy so tests never touch the
    committed manifest."""
    out = tmp_path / "matrix.json"
    mod.OUT = out
    return out


def flip_one_measured(path, status="measured"):
    m = json.loads(path.read_text())
    m["cells"][0]["status"] = status
    path.write_text(json.dumps(m, indent=2) + "\n")
    return m["cells"][0]["id"]


def test_declaration_is_deterministic():
    mod = load_module()
    assert mod.render_matrix(mod.build_matrix()) == mod.render_matrix(mod.build_matrix())
    cells = mod.build_matrix()["cells"]
    assert len(cells) == 48  # 20 priority, 8 dropped (METHODOLOGY §8)
    assert sum(1 for c in cells if c["status"] == "dropped") == 8
    assert all(c["status"] in ("planned", "dropped") for c in cells)


def test_guard_refuses_to_reset_measured_cells(tmp_path, capsys):
    mod = load_module()
    out = sandbox(mod, tmp_path)
    assert mod.main([]) == 0  # no committed file yet: plain write is fine
    cid = flip_one_measured(out)
    before = out.read_bytes()
    rc = mod.main([])
    err = capsys.readouterr().err
    assert rc == 1, "plain regeneration must refuse while measured cells exist"
    assert out.read_bytes() == before, "the guard must not have written anything"
    assert "REFUSING" in err and cid in err, (
        "the refusal must name the cell(s) it would reset")


def test_check_mode_reports_noop_vs_divergence(tmp_path, capsys):
    mod = load_module()
    out = sandbox(mod, tmp_path)
    assert mod.main(["--check"]) == 1  # nothing committed: not a no-op
    capsys.readouterr()
    assert mod.main([]) == 0
    assert mod.main(["--check"]) == 0  # byte-identical regeneration: no-op
    capsys.readouterr()
    flip_one_measured(out)
    assert mod.main(["--check"]) == 1  # committed file diverged from declaration


def test_force_resets_measured_cells_deliberately(tmp_path):
    mod = load_module()
    out = sandbox(mod, tmp_path)
    mod.main([])
    flip_one_measured(out)
    assert mod.main(["--force"]) == 0
    statuses = {c["status"] for c in json.loads(out.read_text())["cells"]}
    assert statuses == {"planned", "dropped"}, (
        "--force re-emits the declaration; statuses must be re-flipped by the "
        "cell runners")


def test_committed_manifest_refuses_plain_regeneration():
    """The real committed matrix carries 20 measured cells: running the
    generator as-documented must refuse AND leave the manifest byte-identical
    (end-to-end through the CLI, in the repo)."""
    before = MATRIX.read_bytes()
    r = subprocess.run([sys.executable, str(GEN_MATRIX)],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert r.returncode == 1, r.stderr
    assert "REFUSING" in r.stderr and "measured" in r.stderr
    assert "gguf-udq4kxl-auto-base-c1-ctx32768" in r.stderr
    assert MATRIX.read_bytes() == before
