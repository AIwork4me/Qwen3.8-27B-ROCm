#!/usr/bin/env python3
"""Release-v0.1 Task 1: README hardware-support matrix renderer.

Renders the GENERATED hardware-matrix block inside README.md, replaced
between `<!-- BEGIN GENERATED: hardware-matrix -->` /
`<!-- END GENERATED: hardware-matrix -->` markers, from:

  * configs/validated-stack.json     — the ✅ project row (reference host,
    evidence links from the manifest's own receipt fields);
  * configs/community/platforms.json — 🧪 community rows (submitter
    evidence, schema-validated per schemas/community-platform.schema.json);
  * a static planned-platforms list  — 🚧 placeholder rows for platforms
    with a protocol invitation but no submissions yet. A planned row is
    dropped as soon as the community index gains an entry for the same gfx
    arch (the 🧪 row supersedes the 🚧 placeholder).

Also imported by scripts/render-readme-blocks.py so one regen covers every
README block; this file remains runnable standalone with identical --check
semantics. Regeneration is idempotent (byte-identical).

Usage:
    python3 scripts/render-hardware-matrix.py         # write the block
    python3 scripts/render-hardware-matrix.py --check # exit 1 if stale

Hand-editing inside the markers is forbidden: the next regen destroys it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STACK = ROOT / "configs" / "validated-stack.json"
PLATFORMS = ROOT / "configs" / "community" / "platforms.json"
README = ROOT / "README.md"

BLOCK = "hardware-matrix"
PROTOCOL = "docs/hardware-validation.md"

# Platforms invited to submit evidence, shown as 🚧 Planned until the first
# community entry for that arch lands in configs/community/platforms.json.
PLANNED_PLATFORMS = (
    {"arch": "gfx1100", "marketing_name": "AMD Radeon PRO W7900",
     "memory_model": "48 GiB discrete GDDR6 (no UMA/GTT pool)"},
)


def short_commit(value: str) -> str:
    """First 7 hex chars of a commit sha (best effort on free-form text)."""
    hexrun = re.sub(r"[^0-9a-f]", "", value.lower())
    return hexrun[:7] if len(hexrun) >= 7 else value


def load_community() -> list[dict]:
    if not PLATFORMS.exists():
        return []
    return json.loads(PLATFORMS.read_text()).get("platforms", [])


def project_row() -> str:
    stack = json.loads(STACK.read_text())
    host = stack["host"]
    vllm = stack["vllm"]
    llama = stack["llama_cpp"]
    evidence = ", ".join(
        f"[{label}]({receipt})"
        for label, receipt in (("vLLM", vllm["validated"]["receipt"]),
                               ("GGUF", llama["validated"]["receipt"])))
    return (f"| {host['validated_platform']} (reference host) | "
            f"`{host['gpu_arch']}` | "
            f"{host['gpu_visible_pool_gib']} GiB unified GTT pool | "
            f"ROCm {host['rocm_recommended']} — vLLM "
            f"@`{short_commit(vllm['commit'])}`, llama.cpp "
            f"@`{short_commit(llama['commit'])}` | ✅ Project-validated | "
            f"{evidence} |")


def community_row(platform: dict) -> str:
    gpu, st = platform["gpu"], platform["stack"]
    paths = " + ".join(label for label, ok in
                       (("GGUF", platform["validated"]["gguf"]),
                        ("vLLM", platform["validated"]["vllm"])) if ok)
    paths = paths or "no path validated"
    # env_check first (always present per schema), then the cell paths,
    # de-duplicated in order.
    receipts = list(dict.fromkeys(
        [platform["receipts"]["env_check"], *platform["receipts"]["cells"]]))
    links = ", ".join(f"[{r.rstrip('/').rsplit('/', 1)[-1]}]({r})"
                      for r in receipts)
    return (f"| {gpu['marketing_name']} | `{gpu['arch']}` | "
            f"{gpu['vram_gib']} GiB discrete VRAM (submitter's rocm-smi) | "
            f"ROCm {st['rocm']} (kernel {st['kernel']}) — submitter stack, "
            f"see {PROTOCOL} | 🧪 Community validated — {paths} | {links} |")


def planned_row(planned: dict) -> str:
    return (f"| {planned['marketing_name']} | `{planned['arch']}` | "
            f"{planned['memory_model']} | — (submitter stack per protocol) | "
            f"🚧 Planned | [requires protocol submission]({PROTOCOL}) |")


def render_block() -> str:
    community = load_community()
    committed_archs = {p["gpu"]["arch"] for p in community}
    rows = ([project_row()]
            + [community_row(p) for p in community]
            + [planned_row(p) for p in PLANNED_PLATFORMS
               if p["arch"] not in committed_archs])
    return "\n".join([
        "| Platform | GPU arch | Memory model | Stack | Status | Evidence |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        "✅ project-validated on the reference host; 🧪 community-validated — "
        "a submitter's receipts, schema-checked and reviewed per "
        f"[{PROTOCOL}]({PROTOCOL}); 🚧 planned — invited, no evidence yet. "
        "Community status never changes project verdicts or quickstart "
        "defaults (`configs/community/` and the community receipts tree are "
        "a separate namespace).",
    ])


def update_readme(write: bool = True) -> bool:
    """Replace the generated block; returns whether anything would change.
    With write=False (check mode) nothing is written."""
    text = README.read_text()
    begin = f"<!-- BEGIN GENERATED: {BLOCK} -->"
    end = f"<!-- END GENERATED: {BLOCK} -->"
    if begin not in text or end not in text:
        raise SystemExit(f"README.md missing generated-block markers for "
                         f"{BLOCK!r} — add the marker pair by hand once, "
                         f"then regenerate.")
    pattern = re.compile(re.escape(begin) + r"\n(?:.*?\n)?" + re.escape(end),
                         re.S)
    replacement = begin + "\n" + render_block() + "\n" + end
    new_text, n = pattern.subn(replacement, text, count=1)
    if n != 1:
        raise SystemExit(f"README.md: could not substitute block {BLOCK!r}")
    changed = new_text != text
    if changed and write:
        README.write_text(new_text)
    return changed


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    check = "--check" in args
    changed = update_readme(write=not check)
    if check:
        if changed:
            print("STALE: README.md hardware-matrix block differs from a "
                  "fresh render — rerun scripts/render-hardware-matrix.py",
                  file=sys.stderr)
            return 1
        print("fresh: README hardware-matrix block")
        return 0
    print(f"README hardware-matrix block "
          f"{'updated' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
