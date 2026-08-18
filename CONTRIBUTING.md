# Contributing to Qwen3.8-27B-ROCm

Two tracks. Hardware evidence is the project's primary ask; code/docs
contributions keep the repository itself honest.

## Track 1 — Hardware evidence (the primary ask)

More validated platforms are worth more than any code change. The contract
is the [community hardware-validation protocol](docs/hardware-validation.md):

- **Start with the issue form** — open a
  [Hardware validation issue](https://github.com/AIwork4me/Qwen3.8-27B-ROCm/issues/new?template=hardware-validation.yml)
  (`.github/ISSUE_TEMPLATE/hardware-validation.yml`) and fill every field.
- **Use our runners** — `scripts/run-cell-gguf.sh` / `scripts/run-cell-vllm.sh`
  + `scripts/bench_client.py` — so numbers are comparable; other harnesses
  (llama-bench, vLLM benchmark_serving, vendor tools) are context, not
  evidence.
- **One platform per PR** — receipts under
  `docs/results/matrix-714/community/<platform-id>/` (env-check, rocm-smi,
  stack manifest, raw cell JSONs) plus the `configs/community/platforms.json`
  entry; the protocol has the full PR shape and the review criteria.

## Track 2 — Code and docs

Evidence-first rules:

- **Every number comes from a committed receipt** — no benchmark figure
  without the cell JSON / receipt it recomputes from.
- **Verdict tables and the README matrix/summary blocks are generated** —
  never hand-edit the `<!-- BEGIN/END GENERATED -->` blocks; change the
  generators or their inputs, then regenerate.
- **Run the loop locally before committing**:

  ```bash
  uv run --no-sync pytest
  python3 scripts/render-readme-blocks.py --check
  python3 scripts/render-hardware-matrix.py --check
  ```

- **Commit style** follows `git log`: `type(scope): summary`, e.g.
  `docs(readme): …`, `fix(scripts): …`, `community: …`.

## Talking to upstreams (llama.cpp / vLLM)

Issues, reviews, and comments posted to the llama.cpp and vLLM trackers are
written and submitted by a human — llama.cpp's CONTRIBUTING.md explicitly
prohibits AI-written posts, and for vLLM and any other upstream, check each
project's policy before posting. AI assistance may prepare the evidence
(receipts, reproductions, briefs), but the upstream submission itself is
human-authored, human-reviewed, and human-owned.
