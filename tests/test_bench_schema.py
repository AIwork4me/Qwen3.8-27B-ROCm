import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(p):
    return json.loads((ROOT / p).read_text())


def test_verdict_schema_rejects_missing_fields():
    schema = load("schemas/benchmark-verdicts.schema.json")
    good = {"checked_at": "2026-08-17", "cells": [{
        "id": "gguf-hip-udq4kxl-auto-base-c1-ctx131072",
        "verdict": "recommended", "reason": "fast", "metrics": {}}]}
    jsonschema.validate(good, schema)
    for bad in ({"checked_at": "2026-08-17", "cells": [{"id": "x", "verdict": "nope", "reason": "r"}]},
                {"checked_at": "2026-08-17", "cells": [{"id": "x", "verdict": "avoid"}]}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


# --------------------------- 2026-08-18 grammar: backend dim + mtp4 + unified
#
# v0.1.2 Vulkan×MTP experiment (declared pre-measurement): gguf ids carry an
# explicit backend tag (hip|vulkan) and an mtp4 depth variant; vllm ids are
# unchanged (single-backend path — no tag, no mtp4 this round). The optional
# -unified suffix marks the unified-default-boot (no -np) c4 rider cell and
# is legal ONLY on c4 gguf ids.

def _validate_id(schema, cid):
    doc = {"checked_at": "2026-08-18", "cells": [{
        "id": cid, "verdict": "recommended", "reason": "r", "metrics": {}}]}
    jsonschema.validate(doc, schema)


def test_schema_accepts_backend_tagged_gguf_ids():
    schema = load("schemas/benchmark-verdicts.schema.json")
    for cid in ("gguf-hip-udq4kxl-auto-base-c1-ctx131072",
                "gguf-hip-udq4kxl-auto-mtp-c4-ctx131072",
                "gguf-vulkan-udq4kxl-auto-mtp4-c4-ctx131072",
                "gguf-vulkan-udq4kxl-auto-base-c1-ctx131072",
                "gguf-hip-udq4kxl-auto-base-c4-ctx131072-unified",
                # vllm grammar unchanged
                "vllm-bf16-auto-base-c1-ctx262144",
                "vllm-bf16-auto-mtp-c16-ctx262144"):
        _validate_id(schema, cid)  # accept


def test_schema_rejects_invalid_backend_grammar():
    schema = load("schemas/benchmark-verdicts.schema.json")
    bad_ids = (
        # vllm is single-backend: a backend tag on vllm is not a thing
        "vllm-vulkan-bf16-auto-base-c1-ctx262144",
        # mtp4 is gguf-only this round
        "vllm-bf16-auto-mtp4-c1-ctx262144",
        # c3 was and stays outside the declared N set
        "gguf-hip-udq4kxl-auto-base-c3-ctx131072",
        # -unified is the unified-default-boot c4 rider marker ONLY
        "gguf-hip-udq4kxl-auto-base-c1-ctx131072-unified",
        "gguf-hip-udq4kxl-auto-base-c8-ctx131072-unified",
        "gguf-hip-udq4kxl-auto-base-c16-ctx131072-unified",
        # legacy unprefixed form: migrated to gguf-hip-* on 2026-08-18
        "gguf-udq4kxl-auto-base-c1-ctx131072",
        # unknown backend tag
        "gguf-cuda-udq4kxl-auto-base-c1-ctx131072",
        # unknown ctx tier
        "gguf-hip-udq4kxl-auto-base-c1-ctx65536",
    )
    for cid in bad_ids:
        with pytest.raises(jsonschema.ValidationError):
            _validate_id(schema, cid)


def test_matrix_declares_all_cells_with_status():
    m = load("docs/results/matrix-714/matrix.json")
    ids = [c["id"] for c in m["cells"]]
    assert len(ids) == len(set(ids))
    assert all(c["status"] in {"measured", "planned", "dropped"} for c in m["cells"])
    assert all("reason" in c for c in m["cells"] if c["status"] != "measured")
    # Declared-priority subset must exist as ids (2026-08-18 id migration:
    # gguf ids carry the explicit -hip- backend tag).
    for pid in ("gguf-hip-udq4kxl-auto-base-c1-ctx131072",
                "gguf-hip-udq4kxl-auto-mtp-c4-ctx131072",
                "vllm-bf16-auto-mtp-c16-ctx262144"):
        assert pid in ids


def test_units_convention_is_binary_only():
    text = (ROOT / "docs" / "results" / "METHODOLOGY.md").read_text()
    assert "MiB / 1000" in text or "never MiB/1000" in text or "binary" in text.lower()
    assert "64 KiB/token" in text  # KV formula constant present
