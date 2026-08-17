# Push checklist — v0.1.0 (owner-only actions)

Everything on this page requires the owner's GitHub account or an owner
decision; the release-prep agent deliberately did none of it. Work top to
bottom: merge, tag, push, watch CI, then the upstream comments and the
verdicts update.

**No secrets.** Never put a token in this tree, in a command line, or in a
commit message. Authenticate once via `gh auth login` or the git credential
helper; if a credential ever lands in a commit, treat it as compromised and
rotate it.

## 0. Preconditions (read-only)

```bash
uv run --no-sync pytest -m "not gpu and not server" -v   # expect 123 passed, 2 deselected
python3 scripts/render-readme-blocks.py --check
python3 scripts/gen-verdicts.py --check
```

123 = the 117-passed pre-release baseline + the 5 release-artifact tests
added by the release-prep commit + the CITATION-consistency test added by
the verifier follow-up (`8539f5f`). The two `--check` gates prove the generated
README blocks and `configs/benchmark-verdicts.json` are fresh. Also confirm
the tree is clean (`git status`) and you are on `feature/release-v0.1` at the
release-prep commit.

## 1. Merge `feature/release-v0.1` into main — BEFORE tagging

The tag must point at the merged `main`, not at the branch tip. `main`
currently sits at the release-plan commit (`2540a80`); the release branch is
8+ commits ahead.

```bash
git switch main
git merge --no-ff feature/release-v0.1 -m "merge: feature/release-v0.1 (v0.1.0)"
```

`--no-ff` keeps the release branch visible in history; a fast-forward is also
acceptable if you prefer linear history.

## 2. Create the GitHub remote (suggestion — owner decides)

Suggested target, following the org precedent of
`AIwork4me/Muse-Glimmer-30B-ROCm`:

- **`AIwork4me/Qwen3.8-27B-ROCm`** — create it as an **empty** repository
  (no README, no .gitignore, no license — this tree already carries them, and
  a seeded README would collide with the push). Visibility is an owner
  decision; note that the upstream comments in step 6 link receipts by URL, so
  it presumes the repo is readable by the llama.cpp maintainers.

Then:

```bash
git remote add origin https://github.com/AIwork4me/Qwen3.8-27B-ROCm.git
```

## 3. Tag v0.1.0 (annotated, while still local)

```bash
git tag -a v0.1.0 -m "v0.1.0: dual-path Qwen3.8-27B serving on ROCm 7.14 (gfx1151) - 20-cell verdict matrix, community hardware-validation protocol, one-pass rehearsed"
```

Annotated, not lightweight: the release message and tagger are part of the
provenance. `CITATION.cff` already declares `version: 0.1.0`,
`date-released: 2026-08-17` — keep the tag consistent with it.

## 4. Push main and the tag together

```bash
git push -u origin main --follow-tags
```

`--follow-tags` ships exactly the annotated tag you just cut; verify on the
repo's *Tags* page that `v0.1.0` points at the merge commit from step 1.

## 5. Watch the FIRST GitHub Actions run — the never-exercised surface

This is unrehearsed-surface #2 in the [one-pass rehearsal
receipt](../results/rocm-7.14/one-pass-rehearsal.md): `.github/workflows/ci.yml`
(workflow `fast-ci`) has never run anywhere but this host. Open the
**Actions** tab immediately after the push and watch the `no-gpu` job.

What to expect:

- One job, `no-gpu`, on `ubuntu-latest`, `timeout-minutes: 10`; realistic
  wall **~1–2 min** warm (the uv cache is keyed on `uv.lock`), a few minutes
  cold on the first-ever run.
- Steps in order: checkout → install uv → `uv sync --only-group ci --locked`
  → assert `torch` is NOT installed → `bash -n` on `scripts/*.sh` →
  **shellcheck** → **actionlint** → **pytest** `-m "not gpu and not server"`.
- Expected pytest outcome: **122 passed, 1 skipped, 2 deselected** (the
  GPU/server-marked tests are the deselects; the job asserts no GPU runtime
  is present). One fewer pass than step 0's local count because
  `tests/test_cell_runner.py` skips its branch-base comparison when the
  shallow CI clone does not carry the `BRANCH_BASE` commit — locally, on a
  full clone, that test runs and the count is step 0's **123 passed,
  2 deselected**.

If a step fails, every step maps to a local equivalent you can run before
pushing a fix: `bash -n scripts/<x>.sh`, `uv run --no-sync shellcheck -x
scripts/*.sh scripts/lib/*.sh`, `uv run --no-sync actionlint`,
`uv run --no-sync pytest -m "not gpu and not server" -v`. Fix, commit, and
push again — nothing here needs a workflow edit unless actionlint flags the
YAML itself.

## 6. Post upstream (owner account, owner-written text only)

**Do not file a new issue.** The control experiments
(`docs/results/upstream-controls/`) showed the pit is live at master HEAD
`01818e495` and disappears with candidate fix PR #25863 applied — i.e. our
bug belongs to the already-tracked #25992/#25863 cluster, and llama.cpp
closes duplicates without questions. The action is:

1. Comment on [ggml-org/llama.cpp#25992](https://github.com/ggml-org/llama.cpp/issues/25992)
   (primary — same host; the AMD maintainer invited affected users to test
   the fix PR and share results).
2. Cross-link from [#23577](https://github.com/ggml-org/llama.cpp/issues/23577)
   (the `'////'`-family tracker) pointing at your #25992 comment.

The evidence pack is `docs/upstream/llama-cpp-hip-greedy-degradation.md` —
receipts table, recommended action, facts-only source notes, and the public
receipt URLs. **Write the comment yourself**: llama.cpp's
[AI usage policy](https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md#ai-usage-policy)
prohibits AI-written bug reports and comments (undisclosed AI usage may mean
a permanent ban); disclose any AI assistance if you used it. Pre-flight:

- Verify the receipt links in the pack resolve from an incognito session
  (they point into this repository — step 2's visibility decision matters).
- Keep the pack's honesty: correlation stated as correlation; the
  "not claimed" list stays; small samples stay small.

Record the posted comment URLs — step 7's constant already points at the
trackers, but any future wording change follows the same mechanism.

## 7. The verdicts' `upstream` fields — the actual mechanism

How it is wired (verified against the code at release prep, in
`scripts/gen-verdicts.py`): the per-cell `upstream` string emitted into
`configs/benchmark-verdicts.json` (and the README known-bad block, which
renders it verbatim from the verdicts) is the module-level constant
**`GGUF_PIT_UPSTREAM`** in `scripts/gen-verdicts.py`. Updated at step 2c
(2026-08-18): it now points at #25992 (primary tracker), #23577 (family),
PR #25863 (candidate fix, differentially verified), and the receipts path
`docs/results/upstream-controls/` — no filed-issue URL exists because no new
issue is filed. If you ever need to update it again:

1. Edit `GGUF_PIT_UPSTREAM` in `scripts/gen-verdicts.py`.
2. Regenerate: `python3 scripts/gen-verdicts.py` (rewrites
   `configs/benchmark-verdicts.json`).
3. Propagate: `python3 scripts/render-readme-blocks.py` (README blocks +
   `docs/results/benchmark.md`).
4. Gate: both `--check` runs from step 0 plus
   `uv run --no-sync pytest -m "not gpu and not server"`.
5. Commit and push. A commit after the tag is fine — it records post-filing
   status.

## 8. Announce (optional)

If you announce, link the README quickstart and the benchmark tables, and
keep every claim scoped to the reference host — community platforms enter
only through the [hardware-validation protocol](../hardware-validation.md)
(W7900 / `gfx1100` is the invited first submission; the GitHub issue
template is live once the repo exists). Candidate venues: r/ROCm, the AMD
community forums, Qwen discussions/discord.

## Owner decision points (recap)

| Decision | Default in this checklist |
|---|---|
| Remote name / org | `AIwork4me/Qwen3.8-27B-ROCm` (suggested; muse-rocm precedent) |
| Repo visibility | Owner call; step 6 presumes maintainers can read the receipts |
| Merge style | `--no-ff` (fast-forward acceptable) |
| Upstream comments | After push (links must resolve); on #25992 + #23577, no new issue; re-tag not needed |
| Announcement | Optional, host-scoped claims only |
