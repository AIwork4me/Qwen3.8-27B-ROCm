"""Explain-phase documentation contract (release-v0.1 plan, Task 2 + Task 4).

Guards the docs suite the way the verdict schema guards the benchmark:

(a) every ``docs/...`` path (with optional ``#anchor``) referenced from the
    shell scripts or the README must resolve to a real file, and anchors
    (e.g. ``docs/troubleshooting.md#uma-bug``) must exist in the target;
(b) every measured pit in ``docs/troubleshooting.md`` follows the spec §4.4
    format (symptom -> reproduction -> root cause/diagnosis state ->
    workaround -> upstream tracking);
(c) ``docs/adaptation.md`` cites at least six committed receipt paths;
(d) ``CITATION.cff`` parses, names the project, and stays consistent with
    the CHANGELOG version heading and the repository name;
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
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _expected_repo_name() -> str:
    """The repository name the CITATION title must match.

    Derived from the ``origin`` remote URL (basename, ``.git`` stripped) so a
    clone checked out under any directory name still cites the repository it
    tracks; falls back to the checkout dirname when no ``origin`` remote
    exists (the stranger-clone failure the verifier reproduced keyed off
    ``ROOT.name`` alone).
    """
    try:
        url = subprocess.run(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ROOT.name
    if not url:
        return ROOT.name
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[: -len(".git")]
    return name or ROOT.name

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
# Extended v0.1.5 (audit A-I3/M3): the upstream-controls and community-
# explorations READMEs are reader-reachable (README → results/README →
# them) and both carried a broken relative link at v0.1.4.
TASK2_DOCS = (
    "README.md",
    "docs/troubleshooting.md",
    "docs/getting-started.md",
    "docs/adaptation.md",
    "docs/results/README.md",
    "docs/upstream/llama-cpp-hip-greedy-degradation.md",
    "docs/results/upstream-controls/README.md",
    "docs/results/community-explorations/w7900d-gfx1100/README.md",
    "docs/results/dflash2/README.md",
    "docs/results/dflash2/experiments.md",
    "docs/results/dflash2/serving-receipt.md",
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
    # The public code-repo and page URLs (cff 1.2.0): the citation must point
    # readers at the GitHub repository that ships it.
    PUBLIC_URL = "https://github.com/AIwork4me/Qwen3.8-27B-ROCm"
    for url_field in ("repository-code", "url"):
        value = field(url_field)
        assert value, f"CITATION.cff lacks the {url_field} field"
        assert value.strip('"') == PUBLIC_URL, (
            f"CITATION.cff {url_field} is {value!r}, expected {PUBLIC_URL!r}")
    kw_line = field("keywords") or ""
    assert kw_line.startswith("["), f"keywords must be a flow list, got: {kw_line!r}"
    keywords = [k.strip() for k in kw_line.strip("[]").split(",") if k.strip()]
    for required in ("rocm", "amd", "llama.cpp", "vllm", "qwen"):
        assert required in keywords, f"keyword {required!r} missing from {keywords}"
    # authors block must exist (a name or family/given entries)
    assert re.search(r"(?m)^authors:", text), "authors block missing"


def test_citation_consistent_with_changelog_and_repo_name() -> None:
    """Plan Task 4 (explicit): the CITATION must describe the release it
    ships with — version equal to the CHANGELOG's version heading, title
    equal to the repository name (from the ``origin`` remote, checkout
    dirname only as the no-remote fallback)."""
    cff_text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

    def field(key: str) -> str:
        m = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", cff_text)
        assert m, f"CITATION.cff lacks the {key} field"
        return m.group(1).strip().strip('"')

    heading = re.search(r"(?m)^## v(\d+(?:\.\d+)+)\b",
                        CHANGELOG.read_text(encoding="utf-8"))
    assert heading, "CHANGELOG.md has no '## vX.Y.Z ...' version heading"
    changelog_version = heading.group(1)
    assert field("version") == changelog_version, (
        f"CITATION.cff version {field('version')!r} != CHANGELOG heading "
        f"version {changelog_version!r}")
    title = field("title")
    repo_name = _expected_repo_name()
    assert title == repo_name, (
        f"CITATION.cff title {title!r} != repository name {repo_name!r}")


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
    # Distribution pins RESTORED 2026-08-18 (Task 4 — the Task 3 subset
    # weakening is gone): exact, recomputed from the verdicts JSON —
    # 28 measured cells = 8 recommended / 14 caution / 6 avoid (20
    # v0.1.0/v0.1.1 cells + 8 v0.1.2 Vulkan×MTP/unified cells). The count
    # must DERIVE from the verdicts JSON, and the CHANGELOG line below is
    # what stays consistent with it.
    # v0.1.14 (2026-08-21): 30 measured cells = 9/15/6 (28 + the two
    # DFlash2 corpus cells — dflash-c1 recommended, dflash-c8 caution).
    assert len(cells) == 30, (
        f"measured-cell count drifted: {len(cells)} (expect 30)")
    assert dist == Counter({"caution": 15, "recommended": 9, "avoid": 6}), (
        f"verdict distribution drifted from the pinned v0.1.14 shape: {dist}")

    text = CHANGELOG.read_text(encoding="utf-8")
    # The distribution line, verbatim from the generated tables.
    dist_line = (f"{dist['recommended']} recommended / {dist['caution']} caution "
                 f"/ {dist['avoid']} avoid")
    assert dist_line in text, f"CHANGELOG lacks the recomputed verdict line {dist_line!r}"
    assert dist_line in (ROOT / "docs/results/benchmark.md").read_text(encoding="utf-8"), (
        "docs/results/benchmark.md headline drifted from the verdicts JSON")
    # v0.1.14 (docs-audit finding M1): the cell count / distribution also
    # appears on surfaces the generator does not own — pin them so the
    # "28-cell era" staleness class cannot recur.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{len(cells)}-cell measured benchmark matrix" in readme, (
        "README intro cell count drifted from the verdicts JSON")
    results_index = (ROOT / "docs/results/README.md").read_text(encoding="utf-8")
    assert dist_line in results_index, (
        "docs/results/README.md verdict distribution drifted")
    assert f"{len(cells)}/{len(cells)} measured" in results_index, (
        "docs/results/README.md measured-cell count drifted")
    assert f"{len(cells)}-cell" in (ROOT / "CITATION.cff").read_text(encoding="utf-8"), (
        "CITATION.cff cell count drifted")

    def metric(cid: str, key: str) -> float:
        return cells[cid]["metrics"][key]

    gguf_mtp = "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072"
    gguf_base = "gguf-hip-udq4kxl-auto-base-c1-ctx131072"
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


# ------------------------------- (g) README hand-written areas (readme-polish A)


def _readme_handwritten() -> str:
    """README.md with every ``<!-- BEGIN/END GENERATED -->`` block removed —
    the hand-written surface this task owns (generated text is Task B's)."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    stripped = re.sub(
        r"<!-- BEGIN GENERATED:[^\n]*-->\n.*?<!-- END GENERATED:[^\n]*-->\n?",
        "", text, flags=re.DOTALL)
    assert "<!-- BEGIN GENERATED:" not in stripped, "generated-block strip failed"
    return stripped


def _quick_start_section(handwritten: str) -> str:
    """The `## Quick start` section (heading line through the next `## `)."""
    parts = handwritten.split("## Quick start", 1)
    assert len(parts) == 2, "README has no '## Quick start' section"
    return parts[1].split("\n## ", 1)[0]


def test_readme_carries_ci_license_and_release_badges() -> None:
    """(a) Badges above the fold: CI, License (shields), GitHub release."""
    head = _readme_handwritten().split("\n## ", 1)[0]
    assert ("https://github.com/AIwork4me/Qwen3.8-27B-ROCm/actions/workflows/"
            "ci.yml/badge.svg") in head, "CI badge missing from the header"
    assert "img.shields.io/badge/License-Apache" in head, "license badge missing"
    assert ("https://img.shields.io/github/v/release/"
            "AIwork4me/Qwen3.8-27B-ROCm") in head, "release badge missing"


def test_readme_quickstart_block_is_complete() -> None:
    """(b) The copy-paste happy path: clone -> env check -> (install) -> build
    -> fetch -> serve, plus the verify curls the quickstart itself echoes."""
    hand = _readme_handwritten()
    for cmd in (
        "git clone https://github.com/AIwork4me/Qwen3.8-27B-ROCm.git",
        "bash scripts/00-check-env.sh",
        "bash scripts/install-rocm-7.14.sh",
        "SET=gguf bash scripts/02-fetch-model.sh",
        "WITH_MTP=1 bash scripts/gguf-quickstart.sh",
        "curl -s http://127.0.0.1:8080/health",
        "curl -s http://127.0.0.1:8080/v1/chat/completions",
    ):
        assert cmd in hand, f"README quickstart lacks the literal command: {cmd}"
    # The verify curl payload matches scripts/gguf-quickstart.sh's own UX echo.
    assert '"content":"Reply with exactly: OK"' in hand
    assert '"max_tokens":512' in hand


def test_readme_decision_table_rows_and_anchors_exist() -> None:
    """(c) The three-row decision table lives in the Quick start section and
    points at the sections that carry the evidence."""
    quick = _quick_start_section(_readme_handwritten())
    # Row 1: interactive chat -> GGUF WITH_MTP=1 on hip (the recommended
    # path; the vulkan opt-in stays visible but not recommended — v0.1.4).
    assert "WITH_MTP=1" in quick and "gguf-quickstart.sh" in quick
    assert "BACKEND=vulkan" in quick, (
        "the (downgraded, experimental) vulkan opt-in must stay visible in "
        "the quickstart decision table")
    # Row 2: long context / vision / batch -> vLLM on :8000.
    assert "bash scripts/03-serve-vllm.sh" in quick
    assert "8000" in quick
    # Row 3: multi-user GGUF loads -> don't; link to the pit evidence.
    assert "[Known good / known bad](#known-good--known-bad)" in quick
    # Updated 2026-08-18 (Task 4): the unified-default-boot c4@131072 rider
    # MEASURED the configuration — the caveat line now cites the measured
    # finding instead of the old "not measured" bracketing.
    assert "not measured" not in quick, (
        "the unified c4@131072 cell is measured; drop the stale caveat")
    assert "6.7 tok/s" in quick and "7.5" in quick, (
        "the measured unified-vs-split numbers are missing")
    # Hand-written anchor links resolve inside the README (see also the
    # generic link tests): Performance and Known good / known bad.
    assert "[Performance](#performance)" in quick


def test_readme_has_no_work_in_progress() -> None:
    """(d) The 'Work in progress' blockquote is gone (whole file)."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Work in progress" not in text


def test_readme_has_no_controller_ruling() -> None:
    """(e) Jargon sweep, global since Task B (the generated blocks adopted
    the wording): 'controller ruling' is absent from the ENTIRE README, and
    the hand-written sentence says 'project ruling (2026-08-17)'."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "controller ruling" not in text, (
        "jargon regression: 'controller ruling' must read 'project ruling "
        "(2026-08-17)' everywhere in the README")
    assert "project ruling (2026-08-17)" in _readme_handwritten()


# -------------------------- (h) OSS completeness: CONTRIBUTING/SECURITY/roadmap
#
# readme-polish Task C (P2): the standard community-facing surfaces —
# CONTRIBUTING.md (two tracks), SECURITY.md (private reporting), and the
# README's hand-written Status & roadmap / Contributing / License areas.


def _readme_section(handwritten: str, title: str) -> str:
    """A named `## ` section (heading line through the next `## ` heading)."""
    parts = handwritten.split(f"## {title}", 1)
    assert len(parts) == 2, f"README has no '## {title}' section"
    return parts[1].split("\n## ", 1)[0]


def test_contributing_md_documents_both_tracks() -> None:
    """CONTRIBUTING.md exists, names the hardware-evidence track as the
    primary ask, points at the validation protocol + its issue form, and
    spells the evidence-first rules for code/docs work — including the two
    generated-block freshness gates contributors must run locally."""
    contrib = ROOT / "CONTRIBUTING.md"
    assert contrib.exists(), "CONTRIBUTING.md is missing"
    text = contrib.read_text(encoding="utf-8")
    # Track 1: the protocol + its issue form.
    assert "docs/hardware-validation.md" in text, (
        "CONTRIBUTING does not reference the hardware-validation protocol")
    assert "hardware-validation.yml" in text, (
        "CONTRIBUTING does not reference the hardware-validation issue form")
    assert "uv run --no-sync pytest" in text, "the test loop is not documented"
    # Track 2: the two --check gates, named verbatim.
    assert "scripts/render-readme-blocks.py --check" in text, (
        "CONTRIBUTING lacks the render-readme-blocks.py --check gate")
    assert "scripts/render-hardware-matrix.py --check" in text, (
        "CONTRIBUTING lacks the render-hardware-matrix.py --check gate")
    # Evidence-first rules: receipts behind numbers, generated blocks are
    # never hand-edited.
    assert "receipt" in text.lower(), "the receipt rule is not stated"
    assert "GENERATED" in text, "generated blocks are not declared off-limits"
    # Upstream-interaction policy (llama.cpp / vLLM posts are human-written).
    assert "llama.cpp" in text and "vLLM" in text, (
        "upstream-interaction policy does not name llama.cpp/vLLM")
    assert "human" in text, "the human-submission policy note is missing"


def test_security_md_documents_private_reporting() -> None:
    """SECURITY.md exists and says: report privately (GitHub security
    advisories / repo owner), never as public issues; scope is the repo's
    scripts/configs — model artifacts are Qwen's, under their own license."""
    sec = ROOT / "SECURITY.md"
    assert sec.exists(), "SECURITY.md is missing"
    text = sec.read_text(encoding="utf-8")
    assert "privately" in text or "private" in text, (
        "SECURITY.md does not ask for private reporting")
    assert "security/advisories" in text or "security advisories" in text.lower(), (
        "SECURITY.md does not point at GitHub security advisories")
    assert "issue" in text.lower(), "SECURITY.md does not steer away from public issues"
    assert "modelscope.cn/models/Qwen/Qwen3.8-27B" in text, (
        "SECURITY.md scope does not name the model artifacts' origin")


def test_readme_status_and_roadmap_section() -> None:
    """'Status & roadmap' (hand-written, after Documentation): names the
    current release (derived from the CHANGELOG's top version heading so it
    can never drift) with CHANGELOG + Releases links, and lists the roadmap
    as evidence-gated intentions — community vLLM, the ANSWERED
    Vulkan-vs-HIP + MTP depth question (v0.1.2), the FILLED c4@131072
    bracketing gap, the remaining planned cells, more community
    platforms."""
    section = _readme_section(_readme_handwritten(), "Status & roadmap")
    changelog_headings = re.findall(
        r"^## (v\d+\.\d+\.\d+)",
        CHANGELOG.read_text(encoding="utf-8"), re.M)
    assert changelog_headings, "CHANGELOG has no version headings"
    assert changelog_headings[0] in section, (
        f"the current release ({changelog_headings[0]}, the CHANGELOG top "
        f"entry) is not stated in Status & roadmap")
    assert "[CHANGELOG](CHANGELOG.md)" in section, "CHANGELOG is not linked"
    assert ("https://github.com/AIwork4me/Qwen3.8-27B-ROCm/releases"
            in section), "Releases are not linked"
    # Evidence-gated framing, not promises.
    low = section.lower()
    assert "not promises" in low or "evidence-gated" in low, (
        "roadmap is not framed as evidence-gated intentions")
    # The roadmap bullets.
    assert "vLLM" in section and ("gfx1100" in section or "W7900" in section), (
        "community-platform vLLM bullet missing")
    assert "Vulkan" in section and "HIP" in section and "24.5" in section, (
        "Vulkan-vs-HIP anchor bullet missing")
    assert "131072" in section, "the c4@131072 bracketing-gap bullet missing"
    assert "matrix.json" in section, "the planned-cells bullet does not cite matrix.json"
    # Every matrix.json citation must resolve to the real file.
    assert (ROOT / "docs/results/matrix-714/matrix.json").exists()


def test_readme_contributing_section_links_out() -> None:
    """The 2-sentence Contributing section links CONTRIBUTING.md, the
    hardware-validation protocol, and the hardware-validation issue form."""
    section = _readme_section(_readme_handwritten(), "Contributing")
    assert "[CONTRIBUTING.md](CONTRIBUTING.md)" in section
    assert "docs/hardware-validation.md" in section
    assert "issues/new?template=hardware-validation.yml" in section


def test_readme_model_license_note() -> None:
    """A License note (hand-written): repo code is Apache-2.0; the model
    artifacts carry their own license on ModelScope (stated factually with
    the model link) — downloading them means accepting it."""
    section = _readme_section(_readme_handwritten(), "License")
    assert "Apache-2.0" in section
    assert "modelscope.cn/models/Qwen/Qwen3.8-27B" in section
    assert "own license" in section, (
        "the model's own-license governance is not stated")


def test_readme_toc_lists_the_new_sections() -> None:
    """The mini-TOC carries the new sections, and each TOC anchor resolves
    to a real heading in the README (the generic link test double-checks)."""
    hand = _readme_handwritten()
    toc = hand.split("\n## ", 1)[0]
    for anchor in ("#status--roadmap", "#contributing", "#license"):
        assert anchor in toc, f"mini-TOC lacks {anchor}"
        slug = anchor[1:]
        assert slug in _anchors_of(ROOT / "README.md"), (
            f"README lacks the heading for TOC anchor {anchor}")
    # Ordering: Status & roadmap after Documentation in the TOC.
    assert toc.index("#documentation") < toc.index("#status--roadmap") < (
        toc.index("#contributing")) < toc.index("#license"), (
        "mini-TOC section order drifted")


def test_taskc_docs_markdown_links_resolve() -> None:
    """The link-sweep contract extended to the Task-C files (CONTRIBUTING.md
    and SECURITY.md live at the repo root, so relative links resolve from
    there)."""
    md_link = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    problems: list[str] = []
    for rel in ("CONTRIBUTING.md", "SECURITY.md"):
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


# ------------------- (i) v0.1.5 audit-F1 docs-accuracy pins
#
# Fixes from the three v0.1.4 audits (A docs-freshness, B reproducibility,
# C community-UX) that live in hand-written docs; the generated-surface
# pins are in tests/test_verdicts.py section 6b.


def test_methodology_carries_the_depth_label_erratum() -> None:
    """Audit A-I2 (v0.1.5): METHODOLOGY is frozen — the mislabeled depth
    notes ('mtp = speculative depth 1 (the 2026-08-17 cells)'; 'HIP, MTP
    depth 1') are corrected by a DATED ERRATUM, never a silent edit: the
    canonical hip mtp-c1 receipt ran implicit depth 3; the clean
    depth-explicit hip d1 is 13.86 (session 3, 2026-08-19, day-confounded
    vs 13.00)."""
    text = (ROOT / "docs/results/METHODOLOGY.md").read_text(encoding="utf-8")
    assert "Erratum (2026-08-19, depth-label correction" in text, (
        "the dated depth-label erratum is missing from METHODOLOGY.md")
    assert "implicit `--spec-draft-n-max` upstream default" in text
    assert "13.86 tok/s" in text and "+6.61%" in text
    assert "day-confounded" in text
    assert "2026-08-16T22:30:54Z" in text, (
        "the erratum must trace to the receipt's own timestamp")


def test_hardware_validation_has_no_stale_planned_w7900_claim() -> None:
    """Audit A-I1 / C-I4 (v0.1.5): the protocol doc must not claim W7900 is
    'currently shown as 🚧 Planned' — it is 🧪 community-validated (GGUF)
    since v0.1.1; the open invitation is stated honestly instead."""
    text = (ROOT / "docs/hardware-validation.md").read_text(encoding="utf-8")
    assert "🚧" not in text and "Planned" not in text, (
        "the stale '🚧 Planned' current-state claim survived")
    assert "🧪" in text and "v0.1.1" in text, (
        "the community-validated state (since v0.1.1) must be stated")


def test_vulkan_optin_prerequisites_are_documented() -> None:
    """Audit B-I1 (v0.1.5): the Vulkan opt-in prerequisites — the 5 apt
    packages, the no-root VULKAN_DEPS_PREFIX fallback (reference host:
    ~/.local/share/qwen38-vulkan-deps, where vulkaninfo lives ONLY), and
    the Mesa-point fingerprint rebuild — must be stated on the three
    user-facing surfaces: README opt-in, adaptation.md §Vulkan, and a
    troubleshooting #vulkan-build section."""
    ts = (ROOT / "docs/troubleshooting.md").read_text(encoding="utf-8")
    assert 'id="vulkan-build"' in ts, (
        "troubleshooting.md lacks the #vulkan-build anchor")
    vulkan_section = ts.split('id="vulkan-build"', 1)[1]
    for pkg in ("mesa-vulkan-drivers", "vulkan-tools", "libvulkan-dev",
                "glslc", "spirv-headers"):
        assert pkg in vulkan_section, f"#vulkan-build lacks package {pkg}"
    assert "VULKAN_DEPS_PREFIX" in vulkan_section
    assert "qwen38-vulkan-deps" in vulkan_section, (
        "the reference-host no-root prefix must be named")
    assert "Mesa" in vulkan_section and "rebuild" in vulkan_section, (
        "the Mesa-pin rebuild behavior must be stated")
    for surface in (ROOT / "README.md",
                    ROOT / "docs" / "adaptation.md"):
        text = surface.read_text(encoding="utf-8")
        assert "mesa-vulkan-drivers" in text and "VULKAN_DEPS_PREFIX" in text, (
            f"{surface.name}: Vulkan opt-in prerequisites missing")


def test_measured_memory_floor_is_stated_in_prerequisites() -> None:
    """Audit C-I2 (v0.1.5): README prerequisites and getting-started state
    the measured GTT floor for the recommended path, receipt-backed
    (load.gtt_mib: 26,548 MiB default boot / 29,270 MiB WITH_MTP boot at
    ctx 131072), with the 32 GiB-RAM signal."""
    cells = ROOT / "docs/results/matrix-714/cells"
    base = json.loads((cells / "gguf-hip-udq4kxl-auto-base-c1-ctx131072.json")
                      .read_text(encoding="utf-8"))["load"]["gtt_mib"]
    mtp = json.loads((cells / "gguf-hip-udq4kxl-auto-mtp-c1-ctx131072.json")
                     .read_text(encoding="utf-8"))["load"]["gtt_mib"]
    assert (base, mtp) == (26548, 29270), (
        f"receipt GTT drift: base={base} mtp={mtp} — update the docs numbers")
    for name, rel in (("README.md", "README.md"),
                      ("getting-started.md", "docs/getting-started.md")):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "26,548" in text and "29,270" in text, (
            f"{name}: measured GTT floor numbers missing")
        assert "32 GiB-RAM" in text and "BIOS/allocation" in text, (
            f"{name}: the 32 GiB-RAM pressure signal is missing")
