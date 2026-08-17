"""Explain-phase documentation contract (release-v0.1 plan, Task 2 + Task 4).

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
    scripts it documents, including both servers' verify curls;
(f) the v0.1.0 release artifacts (Task 4): ``CHANGELOG.md`` has the required
    sections, every headline number recomputes from the committed verdicts,
    every markdown link resolves, ``docs/upstream/PUSH-CHECKLIST.md`` carries
    the owner-only steps in the right order (merge before tag), and neither
    release doc contains credential material.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
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


# ------------------------------------------- (f) v0.1.0 release artifacts (T4)

CHANGELOG = ROOT / "CHANGELOG.md"
PUSH_CHECKLIST = ROOT / "docs" / "upstream" / "PUSH-CHECKLIST.md"
RELEASE_DOCS = (CHANGELOG, PUSH_CHECKLIST)

# Sections the release plan (Task 4) requires in the v0.1.0 CHANGELOG entry.
CHANGELOG_REQUIRED_SECTIONS = (
    "## Highlights",
    "## Serving paths",
    "## Benchmark matrix",
    "## Known good and known bad",
    "## Community hardware validation",
    "## One-pass rehearsal",
    "## Full commit log",
)

# Credential material that must never land in release docs.
SECRET_PATTERNS = ("ghp_", "github_pat_", "AKIA")


def test_changelog_exists_with_required_sections() -> None:
    assert CHANGELOG.exists(), "CHANGELOG.md is missing"
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "## v0.1.0" in text, "CHANGELOG has no '## v0.1.0' entry"
    missing = [s for s in CHANGELOG_REQUIRED_SECTIONS if s not in text]
    assert not missing, f"CHANGELOG v0.1.0 lacks sections: {missing}"


def test_changelog_headline_numbers_recompute_from_verdicts() -> None:
    """Every headline number in the CHANGELOG must recompute from the
    committed verdicts JSON (and stay consistent with the generated
    benchmark tables)."""
    verdicts = json.loads((ROOT / "configs" / "benchmark-verdicts.json")
                          .read_text(encoding="utf-8"))
    cells = {c["id"]: c for c in verdicts["cells"]}
    dist = Counter(c["verdict"] for c in cells.values())
    assert len(cells) == 20, f"expected 20 cells, got {len(cells)}"
    assert dist == {"recommended": 4, "caution": 10, "avoid": 6}, dist

    text = CHANGELOG.read_text(encoding="utf-8")
    # The distribution line, verbatim from the generated tables.
    dist_line = (f"{dist['recommended']} recommended / {dist['caution']} caution "
                 f"/ {dist['avoid']} avoid")
    assert dist_line in text, f"CHANGELOG lacks the recomputed verdict line {dist_line!r}"
    assert dist_line in (ROOT / "docs/results/benchmark.md").read_text(encoding="utf-8"), (
        "docs/results/benchmark.md headline drifted from the verdicts JSON")

    def metric(cid: str, key: str) -> float:
        return cells[cid]["metrics"][key]

    gguf_mtp = "gguf-udq4kxl-auto-mtp-c1-ctx131072"
    gguf_base = "gguf-udq4kxl-auto-base-c1-ctx131072"
    vllm_mtp = "vllm-bf16-auto-mtp-c1-ctx262144"
    vllm_mtp16 = "vllm-bf16-auto-mtp-c16-ctx262144"
    vllm_base16 = "vllm-bf16-auto-base-c16-ctx262144"

    def fmt1(x: float) -> str:
        return f"{x:.1f}"

    recomputed = {
        # GGUF interactive headline pair
        fmt1(metric(gguf_mtp, "per_stream_tok_s_median")): "gguf mtp-c1 med tok/s",
        fmt1(metric(gguf_base, "per_stream_tok_s_median")): "gguf base-c1 med tok/s",
        # MTP gains, both paths (verdicts mtp_gain_vs_base, basis labeled)
        f"+{cells[gguf_mtp]['metrics']['mtp_gain_vs_base']['per_stream_pct']}%":
            "gguf mtp-c1 per-stream gain",
        f"+{cells[vllm_mtp]['metrics']['mtp_gain_vs_base']['per_stream_pct']}%":
            "vllm mtp-c1 per-stream gain",
        f"{cells[vllm_mtp16]['metrics']['mtp_gain_vs_base']['aggregate_pct']}%":
            "vllm mtp-c16 aggregate regression",
        # vLLM batch headline
        fmt1(metric(vllm_base16, "aggregate_tok_s")): "vllm base-c16 aggregate tok/s",
    }
    missing = [f"{label} ({numeral})" for numeral, label in recomputed.items()
               if numeral not in text]
    assert not missing, "CHANGELOG numbers that no longer recompute: " + ", ".join(missing)


def test_release_docs_markdown_links_resolve() -> None:
    """The link-sweep contract extended to the release artifacts."""
    md_link = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    problems: list[str] = []
    for doc in RELEASE_DOCS:
        assert doc.exists(), f"{doc.relative_to(ROOT)} is missing"
        for target in md_link.findall(doc.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, _, anchor = target.partition("#")
            resolved = (doc.parent / path_part) if path_part else doc
            if not resolved.exists():
                problems.append(f"{doc.relative_to(ROOT)}: link '{target}' -> path not found")
                continue
            if anchor and resolved.suffix == ".md" and anchor not in _anchors_of(resolved):
                problems.append(f"{doc.relative_to(ROOT)}: link '{target}' -> anchor #{anchor} missing")
    assert not problems, "broken markdown links:\n  " + "\n  ".join(problems)


def test_push_checklist_documents_owner_steps_in_order() -> None:
    assert PUSH_CHECKLIST.exists(), "docs/upstream/PUSH-CHECKLIST.md is missing"
    text = PUSH_CHECKLIST.read_text(encoding="utf-8")

    # The pre-tag merge step: feature/release-v0.1 lands on main BEFORE the
    # tag is cut (the tag must point at the merged main).
    assert "feature/release-v0.1" in text, "checklist does not name the release branch"
    assert "git merge" in text, "checklist lacks the merge step"
    assert "git tag -a v0.1.0" in text, "checklist lacks the annotated tag command"
    assert "git push" in text, "checklist lacks the push step"

    merge_at = text.index("git merge")
    tag_at = text.index("git tag -a v0.1.0")
    push_at = text.index("git push")
    assert merge_at < tag_at < push_at, (
        "checklist order is wrong: merge main, then tag, then push")

    # The never-exercised surface gets an explicit first-run watch step.
    assert "ci.yml" in text or "fast-ci" in text, (
        "checklist does not point at the workflow to watch")

    # Upstream issue filing + the REAL verdict-update mechanism: the upstream
    # string is the GGUF_PIT_UPSTREAM constant in scripts/gen-verdicts.py
    # (verified 2026-08-17 — no env var / configs wiring exists), then the
    # generators are rerun and the freshness gates re-checked.
    assert "docs/upstream/llama-cpp-hip-greedy-degradation.md" in text
    assert "scripts/gen-verdicts.py" in text
    assert "GGUF_PIT_UPSTREAM" in text
    gen = (ROOT / "scripts" / "gen-verdicts.py").read_text(encoding="utf-8")
    assert "GGUF_PIT_UPSTREAM" in gen, (
        "scripts/gen-verdicts.py no longer carries GGUF_PIT_UPSTREAM — "
        "update this test to the new mechanism")

    # Every docs/... path the checklist references must exist.
    for ref in sorted(set(DOC_REF.findall(text))):
        assert (ROOT / ref.partition("#")[0].rstrip("/")).exists(), (
            f"PUSH-CHECKLIST references missing path {ref}")


def test_release_docs_contain_no_secrets() -> None:
    problems: list[str] = []
    for doc in RELEASE_DOCS:
        assert doc.exists(), f"{doc.relative_to(ROOT)} is missing"
        text = doc.read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            if pattern in text:
                problems.append(f"{doc.relative_to(ROOT)}: secret pattern {pattern!r}")
    assert not problems, "credential material in release docs:\n  " + "\n  ".join(problems)
