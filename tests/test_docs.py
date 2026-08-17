"""Explain-phase documentation contract (release-v0.1 plan, Task 2).

Guards the docs suite the way the verdict schema guards the benchmark:

(a) every ``docs/...`` path (with optional ``#anchor``) referenced from the
    shell scripts or the README must resolve to a real file, and anchors
    (e.g. ``docs/troubleshooting.md#uma-bug``) must exist in the target;
(b) every measured pit in ``docs/troubleshooting.md`` follows the spec §4.4
    format (symptom -> reproduction -> root cause/diagnosis state ->
    workaround -> upstream tracking);
(c) ``docs/adaptation.md`` cites at least six committed receipt paths;
(d) ``CITATION.cff`` parses and names the project;
(e) ``docs/getting-started.md`` quickstart commands literally match the
    scripts it documents, including both servers' verify curls.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A docs/ path as it appears in shell scripts (echo strings, comments) and in
# the README (prose or markdown links), optionally with a GitHub-style anchor.
DOC_REF = re.compile(r"(?<![\w/.-])docs/[A-Za-z0-9._\-/#]+")

# The measured pits (plan Task 2 Step 1b): spec §4.4 format required for each.
MEASURED_PIT_ANCHORS = (
    "greedy-degradation",
    "mtp-concurrency",
    "encoder-profiling",
    "gtt-growth",
    "kv-ceiling",
    "reasoning-field",
)

# Files created/modified by Task 2 whose every relative markdown link must
# resolve (relative links are resolved from each file's own directory).
TASK2_DOCS = (
    "README.md",
    "docs/troubleshooting.md",
    "docs/getting-started.md",
    "docs/adaptation.md",
    "docs/results/README.md",
    "docs/upstream/llama-cpp-hip-greedy-degradation.md",
)

FOUR_PART_LABELS = ("Symptom", "Reproduction", "Root cause", "Workaround", "Upstream")


def _github_slug(heading: str) -> str:
    """GitHub heading anchor: lowercase, drop punctuation, spaces -> hyphens."""
    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    return re.sub(r"\s", "-", slug)


def _anchors_of(md_path: Path) -> set[str]:
    """All anchors addressable in a markdown file (explicit ids + heading slugs)."""
    text = md_path.read_text(encoding="utf-8")
    found = {m.group(1) for m in re.finditer(r'<a id="([A-Za-z0-9_-]+)"', text)}
    for line in text.splitlines():
        m = re.match(r"^#{1,6}\s+(.*)$", line)
        if m:
            found.add(_github_slug(m.group(1)))
    return found


def _sections(md_text: str) -> list[str]:
    """Split into `## `-level sections; each item starts with its heading line."""
    return ["## " + part for part in md_text.split("\n## ")[1:]]


def _doc_refs() -> list[tuple[Path, str]]:
    refs: list[tuple[Path, str]] = []
    sources = sorted(ROOT.glob("scripts/*.sh")) + sorted(ROOT.glob("scripts/lib/*.sh"))
    sources.append(ROOT / "README.md")
    for src in sources:
        for m in DOC_REF.finditer(src.read_text(encoding="utf-8")):
            ref = m.group(0).rstrip(".,")
            refs.append((src.relative_to(ROOT), ref))
    return refs


# ---------------------------------------------------------------- (a) links


def test_scripts_and_readme_doc_references_resolve() -> None:
    refs = _doc_refs()
    assert refs, "no docs/ references found - the reference parser is broken"
    problems: list[str] = []
    for src, ref in sorted(set(refs)):
        path_part, _, anchor = ref.partition("#")
        target = ROOT / path_part.rstrip("/")
        if not target.exists():
            problems.append(f"{src}: {ref} -> file not found")
            continue
        if anchor and target.suffix == ".md":
            if anchor not in _anchors_of(target):
                problems.append(f"{src}: {ref} -> anchor #{anchor} missing in {path_part}")
    assert not problems, "unresolved doc references:\n  " + "\n  ".join(problems)


def test_readme_links_the_new_docs() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for doc in (
        "docs/getting-started.md",
        "docs/troubleshooting.md",
        "docs/adaptation.md",
        "docs/results/README.md",
    ):
        assert doc in readme, f"README does not link {doc}"
        assert (ROOT / doc).exists(), f"{doc} does not exist"


# ------------------------------------------- (b) troubleshooting pit format


def test_measured_pits_follow_spec_4_4_format() -> None:
    ts = ROOT / "docs/troubleshooting.md"
    assert ts.exists(), "docs/troubleshooting.md is missing"
    text = ts.read_text(encoding="utf-8")
    sections = _sections(text)
    problems: list[str] = []
    for anchor in MEASURED_PIT_ANCHORS:
        matches = [
            s for s in sections
            if f'id="{anchor}"' in s.splitlines()[0] + "\n" + (s.splitlines()[1] if len(s.splitlines()) > 1 else "")
            or _github_slug(s.splitlines()[0][3:].strip()) == anchor
        ]
        if not matches:
            problems.append(f"no troubleshooting section for pit #{anchor}")
            continue
        body = matches[0]
        for label in FOUR_PART_LABELS:
            if label not in body:
                problems.append(f"pit #{anchor}: section lacks the '{label}' part")
    assert not problems, "spec §4.4 format violations:\n  " + "\n  ".join(problems)


def test_troubleshooting_carries_script_referenced_anchors() -> None:
    ts = ROOT / "docs/troubleshooting.md"
    anchors = _anchors_of(ts)
    for anchor in ("uma-bug", "greedy-degradation", "mtp-concurrency",
                   "encoder-profiling", "gtt-growth", "kv-ceiling",
                   "reasoning-field", "amdsmi", "dirty-llama-cpp-checkout"):
        assert anchor in anchors, f"troubleshooting.md lacks anchor #{anchor}"


# ------------------------------------------------------- (c) adaptation map


def test_adaptation_cites_at_least_six_existing_receipts() -> None:
    ad = ROOT / "docs/adaptation.md"
    assert ad.exists(), "docs/adaptation.md is missing"
    text = ad.read_text(encoding="utf-8")
    md_link = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    receipt_roots = [ROOT / "docs/results", ROOT / "configs"]
    receipts = set()
    for target in md_link.findall(text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (ad.parent / target.partition("#")[0]).resolve()
        if any(str(resolved).startswith(str(r) + os.sep) for r in receipt_roots):
            receipts.add(resolved)
    assert len(receipts) >= 6, f"only {len(receipts)} receipt citations: {sorted(map(str, receipts))}"
    missing = sorted(str(p) for p in receipts if not p.exists())
    assert not missing, f"cited receipts do not exist: {missing}"


# ----------------------------------------------------------- (d) CITATION


def test_citation_cff_parses_and_names_the_project() -> None:
    cff = ROOT / "CITATION.cff"
    assert cff.exists(), "CITATION.cff is missing"
    text = cff.read_text(encoding="utf-8")

    def field(key: str) -> str | None:
        m = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", text)
        return m.group(1).strip() if m else None

    assert field("cff-version"), "cff-version missing"
    title = field("title") or ""
    assert "Qwen3.8-27B-ROCm" in title, f"title does not name the project: {title!r}"
    assert field("license") == "Apache-2.0"
    assert field("version"), "version missing"
    assert "AIwork4me" in text, "the AIwork4me organization is not named"
    kw_line = field("keywords") or ""
    assert kw_line.startswith("["), f"keywords must be a flow list, got: {kw_line!r}"
    keywords = [k.strip() for k in kw_line.strip("[]").split(",") if k.strip()]
    for required in ("rocm", "amd", "llama.cpp", "vllm", "qwen"):
        assert required in keywords, f"keyword {required!r} missing from {keywords}"
    # authors block must exist (a name or family/given entries)
    assert re.search(r"(?m)^authors:", text), "authors block missing"


def test_license_carries_dual_attribution() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Qwen3.8-27B-ROCm contributors" in text
    assert "Muse-Glimmer-30B-ROCm contributors" in text


# ------------------------------------------------- (e) getting-started cmds


def test_getting_started_quickstart_commands_match_scripts() -> None:
    gs_path = ROOT / "docs/getting-started.md"
    assert gs_path.exists(), "docs/getting-started.md is missing"
    gs = gs_path.read_text(encoding="utf-8")

    required_invocations = [
        "bash scripts/00-check-env.sh",
        "bash scripts/gguf-quickstart.sh",
        "WITH_MTP=1 bash scripts/gguf-quickstart.sh",
        "bash scripts/03-serve-vllm.sh",
        "bash scripts/03-serve-vllm.sh --mtp",
    ]
    missing = [c for c in required_invocations if c not in gs]
    assert not missing, f"getting-started lacks the literal commands: {missing}"

    # Verify curls must match the scripts' echoed contract: the GGUF port
    # default comes from scripts/gguf-quickstart.sh, the vLLM port from the
    # serve conf (parsed by scripts/03-serve-vllm.sh).
    gguf = (ROOT / "scripts/gguf-quickstart.sh").read_text(encoding="utf-8")
    assert 'PORT="${PORT:-8080}"' in gguf and "/health" in gguf and "/v1/chat/completions" in gguf
    conf = (ROOT / "configs/serve-args.conf").read_text(encoding="utf-8")
    assert "--port 8000" in conf
    for curl in (
        "curl -s http://127.0.0.1:8080/health",
        "curl -s http://127.0.0.1:8080/v1/chat/completions",
        "curl -s http://127.0.0.1:8000/health",
        "curl -s http://127.0.0.1:8000/v1/chat/completions",
    ):
        assert curl in gs, f"getting-started lacks verify curl: {curl}"

    # Every script path getting-started mentions must exist.
    for name in sorted(set(re.findall(r"scripts/[A-Za-z0-9._\-]+", gs))):
        assert (ROOT / name).exists(), f"getting-started references missing script {name}"


# --------------------------------------- link integrity for the Task-2 docs


def test_task2_docs_markdown_links_resolve() -> None:
    md_link = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    problems: list[str] = []
    for rel in TASK2_DOCS:
        doc = ROOT / rel
        assert doc.exists(), f"{rel} is missing"
        for target in md_link.findall(doc.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, _, anchor = target.partition("#")
            resolved = (doc.parent / path_part) if path_part else doc
            if not resolved.exists():
                problems.append(f"{rel}: link '{target}' -> path not found")
                continue
            if anchor and resolved.suffix == ".md" and anchor not in _anchors_of(resolved):
                problems.append(f"{rel}: link '{target}' -> anchor #{anchor} missing")
    assert not problems, "broken markdown links:\n  " + "\n  ".join(problems)
