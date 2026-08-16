import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent


def load(p):
    return json.loads((ROOT / p).read_text())


def test_verdict_schema_rejects_missing_fields():
    schema = load("schemas/benchmark-verdicts.schema.json")
    good = {"checked_at": "2026-08-17", "cells": [{
        "id": "gguf-udq4kxl-auto-base-c1-ctx131072",
        "verdict": "recommended", "reason": "fast", "metrics": {}}]}
    jsonschema.validate(good, schema)
    for bad in ({"checked_at": "2026-08-17", "cells": [{"id": "x", "verdict": "nope", "reason": "r"}]},
                {"checked_at": "2026-08-17", "cells": [{"id": "x", "verdict": "avoid"}]}):
        try:
            jsonschema.validate(bad, schema)
            raise AssertionError("should have failed")
        except jsonschema.ValidationError:
            pass


def test_matrix_declares_all_cells_with_status():
    m = load("docs/results/matrix-714/matrix.json")
    ids = [c["id"] for c in m["cells"]]
    assert len(ids) == len(set(ids))
    assert all(c["status"] in {"measured", "planned", "dropped"} for c in m["cells"])
    assert all("reason" in c for c in m["cells"] if c["status"] != "measured")
    # Declared-priority subset must exist as ids.
    for pid in ("gguf-udq4kxl-auto-base-c1-ctx131072",
                "gguf-udq4kxl-auto-mtp-c4-ctx131072",
                "vllm-bf16-auto-mtp-c16-ctx262144"):
        assert pid in ids


def test_units_convention_is_binary_only():
    text = (ROOT / "docs" / "results" / "METHODOLOGY.md").read_text()
    assert "MiB / 1000" in text or "never MiB/1000" in text or "binary" in text.lower()
    assert "64 KiB/token" in text  # KV formula constant present
