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
