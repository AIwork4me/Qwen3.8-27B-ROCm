"""Guard for scripts/gen-matrix.py (2026-08-17; semantics extended
2026-08-18 by the backend-dimension id migration).

A regeneration re-emits the DECLARATION, but since the 2026-08-18
v0.1.2 (Vulkan×MTP) migration it CARRIES OVER the committed measurement
state instead of clobbering it: every committed `measured` cell (status +
`degraded` + `note`) is transferred onto its declared id via the baked-in
LEGACY→NEW mapping (legacy unprefixed gguf ids ARE hip). The refusal guard
therefore fires only when a measured cell would fall OUT of the declaration
entirely (lost evidence); `--force` still re-emits the bare declaration
deliberately. METHODOLOGY.md §8 documents both the guarded instruction and
the dated addendum.
"""

import importlib.util
import json
import re
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
    if status == "measured":
        m["cells"][0].pop("reason", None)  # the runners drop the reason on measure
    path.write_text(json.dumps(m, indent=2) + "\n")
    return m["cells"][0]["id"]


def test_declaration_is_deterministic():
    mod = load_module()
    assert mod.render_matrix(mod.build_matrix()) == mod.render_matrix(mod.build_matrix())
    cells = mod.build_matrix()["cells"]
    # 2026-08-18 declaration: previous 48 + 8 new v0.1.2 cells = 56
    # (fresh declaration: no measured yet — 48 planned + 8 dropped).
    # 2026-08-21 declaration: 56 + 2 new v0.1.9 dflash cells = 58.
    assert len(cells) == 58
    assert sum(1 for c in cells if c["status"] == "dropped") == 8
    assert all(c["status"] in ("planned", "dropped") for c in cells)


def test_declaration_declares_dflash2_pairing_cells_as_planned():
    """v0.1.9 DFlash2 integration (declared pre-measurement 2026-08-21,
    re-tiered same day): the block-diffusion draft
    (incoai/Qwen3.8-27B-DFlash2) on the vllm path — dflash x {c1,c8}
    @131072. Declared at ctx262144 first; the dflash boot at 262144 fails
    the KV budget on the 80 GiB pool (draft weights 3.6 GiB + draft KV
    group: 21.63 GiB KV needed vs 15.46 available, engine estimate max len
    181376 — boot receipt 2026-08-21), so the pairing re-tiers to 131072
    (the other declared vllm conf tier). The base/mtp same-session pairing
    partners run at the same tier."""
    mod = load_module()
    cells = mod.build_cells()
    new_ids = {
        "vllm-bf16-auto-dflash-c1-ctx131072",
        "vllm-bf16-auto-dflash-c8-ctx131072",
    }
    ids = {c["id"] for c in cells}
    assert new_ids <= ids, f"missing new cells: {sorted(new_ids - ids)}"
    by_id = {c["id"]: c for c in cells}
    for cid in sorted(new_ids):
        assert by_id[cid]["status"] == "planned"
        assert "DFlash2" in by_id[cid]["reason"]
        assert by_id[cid]["priority"] is True
        assert by_id[cid]["runner_hint"] == "scripts/run-cell-vllm.sh"
    # No other dflash tiers sneak in (c4/c16 stay undeclared, and the
    # KV-infeasible 262144 tier is not declared either).
    dflash_ids = {i for i in ids if "-dflash-" in i}
    assert dflash_ids == new_ids


def test_declaration_declares_the_8_new_v012_cells_as_planned():
    """v0.1.2 Vulkan×MTP experiment (METHODOLOGY §8 addendum, declared
    pre-measurement): vulkan×{base,mtp,mtp4}×c{1,4}@131072 (6) + hip
    mtp4-c1@131072 (1) + hip base-c4@131072-unified (1 rider)."""
    mod = load_module()
    cells = mod.build_cells()
    new_ids = {
        "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072",
        "gguf-vulkan-udq4kxl-auto-base-c4-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp-c1-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp-c4-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp4-c1-ctx131072",
        "gguf-vulkan-udq4kxl-auto-mtp4-c4-ctx131072",
        "gguf-hip-udq4kxl-auto-mtp4-c1-ctx131072",
        "gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified",
    }
    ids = {c["id"] for c in cells}
    assert new_ids <= ids, f"missing new cells: {sorted(new_ids - ids)}"
    by_id = {c["id"]: c for c in cells}
    for cid in sorted(new_ids):
        assert by_id[cid]["status"] == "planned"
        assert "Vulkan×MTP" in by_id[cid]["reason"]
        assert by_id[cid]["priority"] is True
    # The 8 new cells are the ONLY additions in v0.1.2: 56 - 48 previous = 8.
    # (v0.1.9 adds 2 dflash cells on top: 58 — see the dflash test above.)
    assert len(ids) == 58


def test_every_declared_gguf_id_carries_an_explicit_backend_tag():
    mod = load_module()
    ids = [c["id"] for c in mod.build_cells()]
    gguf = [i for i in ids if i.startswith("gguf-")]
    assert len(gguf) == 32  # 24 migrated hip + 8 new (6 vulkan + hip mtp4 + hip unified)
    assert all(re.match(r"^gguf-(hip|vulkan)-udq4kxl-auto-", i) for i in gguf), (
        "every gguf id must carry an explicit backend tag (2026-08-18 "
        "migration; legacy unprefixed ids == hip)")
    # -unified marks ONLY the unified-default-boot c4 rider cell.
    unified = [i for i in gguf if i.endswith("-unified")]
    assert unified == ["gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified"]
    # vllm ids stay unprefixed (single-backend path, grammar unchanged).
    vllm = [i for i in ids if i.startswith("vllm-")]
    assert len(vllm) == 26  # 16 valid + 8 dropped ctx-32768 + 2 dflash (v0.1.9)
    assert all(re.match(r"^vllm-bf16-auto-", i) for i in vllm)


def test_regeneration_carries_over_measured_state_via_legacy_map(tmp_path):
    """The 2026-08-18 migration semantics: a plain regeneration transfers
    committed measured cells (status + degraded + note) onto the new ids —
    legacy unprefixed gguf ids ARE hip — so regeneration is no longer a
    clobber for declared cells."""
    mod = load_module()
    out = sandbox(mod, tmp_path)
    # Simulate the PRE-migration committed manifest: legacy-form ids, one
    # measured + degraded cell.
    legacy = {"generated_at": "2026-08-17", "generator": "scripts/gen-matrix.py",
              "cells": []}
    for c in mod.build_cells():
        c = dict(c)
        c["id"] = c["id"].replace("gguf-hip-", "gguf-", 1)
        legacy["cells"].append(c)
    target = legacy["cells"][1]  # base-c4-ctx32768: a degraded measured cell
    target.update(status="measured", degraded=True,
                  note="measured (degraded): anchor check failed (greedy byte-identity)")
    target.pop("reason", None)
    out.write_text(json.dumps(legacy, indent=2) + "\n")

    assert mod.main([]) == 0  # no refusal: nothing falls out of the declaration
    m = json.loads(out.read_text())
    migrated = {c["id"]: c for c in m["cells"]}
    new_id = "gguf-hip-udq4kxl-auto-base-c4-ctx32768"
    assert migrated[new_id]["status"] == "measured"
    assert migrated[new_id]["degraded"] is True
    assert migrated[new_id]["note"] == target["note"]
    assert "reason" not in migrated[new_id]
    # ...and the migrated manifest is idempotent under regeneration.
    assert mod.main(["--check"]) == 0


def test_guard_refuses_to_lose_a_measured_cell_that_leaves_the_declaration(
        tmp_path, capsys):
    mod = load_module()
    out = sandbox(mod, tmp_path)
    assert mod.main([]) == 0
    m = json.loads(out.read_text())
    # A measured cell whose id is NOT declared (c3) would be dropped entirely
    # by a regeneration: the guard must refuse and name it.
    m["cells"][0]["id"] = "gguf-hip-udq4kxl-auto-base-c3-ctx32768"
    m["cells"][0]["status"] = "measured"
    out.write_text(json.dumps(m, indent=2) + "\n")
    before = out.read_bytes()
    rc = mod.main([])
    err = capsys.readouterr().err
    assert rc == 1, "plain regeneration must refuse while a measured cell would be lost"
    assert out.read_bytes() == before, "the guard must not have written anything"
    assert "REFUSING" in err and "gguf-hip-udq4kxl-auto-base-c3-ctx32768" in err


def test_check_mode_reports_noop_vs_divergence(tmp_path, capsys):
    mod = load_module()
    out = sandbox(mod, tmp_path)
    assert mod.main(["--check"]) == 1  # nothing committed: not a no-op
    capsys.readouterr()
    assert mod.main([]) == 0
    assert mod.main(["--check"]) == 0  # byte-identical regeneration: no-op
    capsys.readouterr()
    # A measured status inside the declaration survives regeneration, so the
    # committed file stays fresh (carry-over reproduces it exactly).
    flip_one_measured(out)
    assert mod.main(["--check"]) == 0
    capsys.readouterr()
    # Any other divergence (a hand-edited reason) is still reported STALE.
    m = json.loads(out.read_text())
    m["cells"][0]["reason"] = "hand-edited"
    out.write_text(json.dumps(m, indent=2) + "\n")
    assert mod.main(["--check"]) == 1


def test_force_resets_measured_cells_deliberately(tmp_path):
    mod = load_module()
    out = sandbox(mod, tmp_path)
    mod.main([])
    cid = flip_one_measured(out)
    assert mod.main(["--force"]) == 0
    by_id = {c["id"]: c for c in json.loads(out.read_text())["cells"]}
    assert by_id[cid]["status"] == "planned", (
        "--force re-emits the bare declaration; statuses must then be "
        "re-flipped by the cell runners")


def test_committed_manifest_regeneration_is_a_noop():
    """The real committed matrix carries the 20 migrated measured cells: a
    plain regeneration (as documented) must carry them over byte-identically
    — the measurement manifest survives the id migration untouched."""
    before = MATRIX.read_bytes()
    r = subprocess.run([sys.executable, str(GEN_MATRIX)],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert r.returncode == 0, r.stderr
    assert MATRIX.read_bytes() == before
    r = subprocess.run([sys.executable, str(GEN_MATRIX), "--check"],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert r.returncode == 0, r.stderr
