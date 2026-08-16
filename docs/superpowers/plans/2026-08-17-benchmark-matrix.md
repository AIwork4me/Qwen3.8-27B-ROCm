# Qwen3.8-27B-ROCm Benchmark Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute the evidence-first benchmark matrix over both validated serving paths, with the UX-first verdict system (✅ Recommended / ⚠️ Caution / ❌ Avoid), generated README blocks, and the quickstart-can-never-point-at-a-pit CI guarantee.

**Architecture:** A declared-full-but-evidence-gated matrix (spec §4.3: "path coverage may be reduced; every dropped cell is recorded with reason"). One bench client (OpenAI-compatible, SSE-framing-safe, adapted from muse-rocm's battle-tested `bench_client.py`) serves both paths. Cell runners boot the right server config per path, emit raw JSON cells; a verdict generator applies pre-declared demotion rules to produce `configs/benchmark-verdicts.json`; README blocks are GENERATED from that JSON (never hand-edited); a CI test asserts every quickstart-referenced config is ✅-verdict. Executed this session: the pre-declared priority subset (GGUF: full c×MTP sweep + ctx tiers — fast boots; vLLM: c×MTP at the validated ctx — slow boots); every unexecuted cell lands as `planned` with reason.

**Tech Stack:** bash, python3 (uv venv, no torch needed for client), pytest, JSON schema, both validated servers (llama-server build-714, vLLM editable).

**Spec:** `docs/superpowers/specs/2026-08-16-qwen3.8-27b-rocm-design.md` (§4.3, §4.4 binding)
**Inputs:** `configs/validated-stack.json` (both paths validated), receipts `docs/results/rocm-7.14/*.md`, spike `quant-kv.md` (KV formula).

## Global Constraints

- Verdict vocabulary: `recommended | caution | avoid`, each with `reason`, optional `conditions`, `workaround`, `upstream`. Enforced by `schemas/benchmark-verdicts.schema.json`; a cell without a verdict fails tests.
- Demotion rules (pre-declared in METHODOLOGY.md BEFORE any measurement): per-stream TPOT < 10 tok/s (i.e. > 100 ms/token) when the configuration is presented for interactive use → not `recommended`; aggregate throughput that regresses vs lower concurrency → `avoid` candidate; any abort/OOM/hang → `avoid`; single-stream UX destroyed by concurrency gains → reported as the pit, never a headline.
- Units convention (fixes the parked 8.2-vs-8.0 ruling): ALL committed numbers are binary (GiB/MiB, /1024); MiB/1000 never appears. KV formula from spike quant-kv.md: `KV_bytes = tokens × 2 × 16 full-attn layers × 4 kv-heads × 256 head_dim × bytes/elem` (= 64 KiB/token bf16, 32 KiB fp8, 34 KiB q8_0).
- Memory methodology: record VRAM and GTT separately (rocm-smi) at load and steady state; on this APU weights+KV live in GTT via the 80 GiB pool — placement vs spill distinguished per upstream llama.cpp #26432 note.
- Prompt set: deterministic, committed under `scripts/prompt-sets/` (8 varied prompts, ~1500-2500 tokens each; generation 256 tokens; one arithmetic anchor for greedy byte-identity across paths).
- Client contract: `scripts/bench_client.py --base-url URL --concurrency N --prompts FILE --max-tokens 256 [--label X]` emits one JSON: per-stream {ttft_ms, tpot_ms, tokens}, aggregate {tok_per_s, wall_s}, failures. SSE-framing-safe (muse-rocm lesson: never assume one event per chunk).
- Servers: GGUF `scripts/gguf-quickstart.sh` (port 8080; GGUF_FILE/CTX_SIZE/WITH_MTP env; per-stream ctx for concurrency cells via llama.cpp `-np N` semantics — discover and RECORD exact slot/ctx behavior at the pin in METHODOLOGY); vLLM `scripts/03-serve-vllm.sh [--mtp]` (port 8000; flags from confs; NO conf edits — per-cell overrides via documented env/args only, confs stay the validated defaults).
- Raw cells: `docs/results/matrix-714/cells/*.json` (committed; gitignore pattern `docs/results/*.json` must be adjusted to not exclude the cells dir — resolve deliberately); one manifest `docs/results/matrix-714/matrix.json` mapping every declared cell → `measured | planned(reason) | dropped(reason)`.
- CI: CPU-safe; verdicts/matrix/README-block freshness all testable without GPU; quickstart assertion parses `scripts/gguf-quickstart.sh` + serve confs and asserts referenced configs are `recommended` in verdicts JSON.
- Baseline suite: 37 passed, 2 deselected. Branch: `feature/benchmark-matrix` off main (@2bb00ba).

---

### Task 1: METHODOLOGY.md + verdict schema + matrix declaration

**Files:**
- Create: `docs/results/METHODOLOGY.md`
- Create: `schemas/benchmark-verdicts.schema.json`
- Create: `docs/results/matrix-714/matrix.json` (declaration: all cells `planned` or `measured-pending`)
- Modify: `.gitignore` (un-ignore `docs/results/matrix-714/` JSONs)
- Test: `tests/test_bench_schema.py`

**Interfaces:**
- Consumes: spike quant-kv.md formula; validated-stack ctx values (gguf 131072, vllm 262144).
- Produces: schema for `configs/benchmark-verdicts.json` (Task 5's generator output + CI target); matrix.json cell ids: `{path}-{weight}-{kv}-{mtp}-c{N}-ctx{K}` with path ∈ {gguf,vllm}, weight ∈ {udq4kxl,bf16}, kv ∈ {auto}, mtp ∈ {base,mtp}, N ∈ {1,4,8,16}, K ∈ {32768,131072,262144} (vllm K ∈ {131072,262144} — 32768 not offered). DECLARED-PRIORITY subset for this session: gguf all N × {base,mtp} @131072 + {base} × {32768,262144} @N=1,4; vllm {base,mtp} × all N @262144; everything else planned(reason="time-boxed session; machinery complete").

- [ ] **Step 1: Write the failing test**

`tests/test_bench_schema.py`:

```python
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
```

- [ ] **Step 2: Verify failure** → `uv run --no-sync pytest tests/test_bench_schema.py -v` FAIL (files missing).

- [ ] **Step 3: Implement**

`docs/results/METHODOLOGY.md` — sections: Study definitions (S1 single-stream interactive; S2 concurrency journeys c=4 light multi-user, c=8, c=16 batch; S3 context-capacity: per-config max_usable_context via boot ladder + deep-prompt functional retrieval smoke — needle sentence at 80% depth, judged by exact substring in output); Metrics (TTFT, per-stream TPOT, aggregate tok/s, VRAM/GTT at load+steady, failures); Verdict rules (the Global Constraints bullets verbatim, incl. 10 tok/s interactive floor; aggregate-tpot-vs-UX honesty clause; auto-verdict ladder: abort/OOM → avoid; TPOT<10 at interactive presentation → caution or avoid; else recommended; final human/controller review recorded in verdicts JSON `reviewed_by`); Memory methodology (VRAM vs GTT split, APU GTT placement via 80 GiB pool, #26432 spill distinction, KV closed-form table bf16 16 GiB/fp8 8 GiB/q8_0 8.5 GiB @262144 + GGUF measured 64 KiB/token increments); Units (binary only, the parked 8.2-decimal → 8.0-binary ruling recorded); llama.cpp slot semantics at pin 4df29be4 (`-np` vs `--ctx-size` split — fill with the actual discovered behavior + source line); vLLM concurrency (client-parallel against default max-num-seqs; record engine args from log).

`schemas/benchmark-verdicts.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Benchmark verdicts",
  "type": "object",
  "required": ["checked_at", "cells"],
  "properties": {
    "checked_at": {"type": "string"},
    "reviewed_by": {"type": "string"},
    "cells": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "verdict", "reason", "metrics"],
        "properties": {
          "id": {"type": "string", "pattern": "^(gguf|vllm)-(udq4kxl|bf16)-auto-(base|mtp)-c(1|4|8|16)-ctx(32768|131072|262144)$"},
          "verdict": {"enum": ["recommended", "caution", "avoid"]},
          "reason": {"type": "string", "minLength": 10},
          "conditions": {"type": "string"},
          "workaround": {"type": "string"},
          "upstream": {"type": "string"},
          "metrics": {"type": "object"}
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

`docs/results/matrix-714/matrix.json`: `{"generated_at": ..., "cells": [{"id", "status": "planned", "reason", "runner_hint"}...]}` generated by a small committed generator script `scripts/gen-matrix.py` (deterministic: full cross-product minus documented exclusions, priority flags per the Interfaces block) — so the declaration itself is reproducible. Run it, commit output.

`.gitignore`: change `docs/results/*.json` to not match `docs/results/matrix-714/` (e.g. keep the pattern but add `!docs/results/matrix-714/**` and `!docs/results/METHODOLOGY.md` is a .md already fine).

- [ ] **Step 4: Run tests** — new pass; full suite green (40 passed, 2 deselected).

- [ ] **Step 5: Commit** — `git add docs/results/METHODOLOGY.md schemas/benchmark-verdicts.schema.json docs/results/matrix-714/ scripts/gen-matrix.py .gitignore tests/test_bench_schema.py && git commit -m "feat: benchmark methodology, verdict schema, declared matrix"`

---

### Task 2: Bench client + prompt set

**Files:**
- Create: `scripts/bench_client.py`
- Create: `scripts/prompt-sets/default.json`
- Test: `tests/test_bench_client.py`

**Interfaces:**
- Consumes: muse-rocm `/home/amd/Desktop/muse-rocm/scripts/bench_client.py` (read it; reuse its SSE parsing and metric math approach — do not import, copy+adapt).
- Produces: `python3 scripts/bench_client.py --base-url http://127.0.0.1:8080 --concurrency 4 --prompts scripts/prompt-sets/default.json --max-tokens 256 --label gguf-x` → prints one JSON object (also `--out FILE`): `{"label", "concurrency", "streams": [{"ttft_ms", "tpot_ms", "completion_tokens", "prompt_tokens", "ok"}], "aggregate": {"tok_per_s", "wall_s", "ok_streams", "failed_streams"}}`. Prompt-set format: `{"prompts": [{"id", "text"}], "anchor": {"id", "text", "expect_exact": "OK"}}`.

- [ ] **Step 1: Write the failing test** — `tests/test_bench_client.py` with SYNTHETIC SSE fixtures (no server): craft two fake streamed responses (one clean, one with chunk-split mid-token SSE framing — the muse-rocm lesson), run the client's parsing/metrics functions directly (import via importlib from path), assert ttft/tpot/tokens computed correctly and framing-splitting handled. Include a prompt-set loader test (default.json: 8 prompts, sizes 1500-2500 tokens approx by chars/3.5, anchor present with expect_exact "OK").

- [ ] **Step 2: Verify failure** → FAIL.

- [ ] **Step 3: Implement** — adapt muse-rocm's bench_client.py: urllib/http.client (no external deps) against `/v1/chat/completions` with `stream: true`; threads for N streams; TTFT = first content-bearing delta; TPOT = (last_delta - first_delta)/(completion_tokens-1); SSE parse buffers on `\n\n` and splits `data:` lines, joining partial JSON gracefully; anchor mode (`--anchor-only`) runs the greedy arithmetic prompt with temperature 0 and checks `expect_exact` substring. Write `scripts/prompt-sets/default.json` (8 prompts: varied domains, each ~5-8 KB text; anchor = "Reply with exactly: OK").

- [ ] **Step 4: Run tests** — green (44-ish passed total).

- [ ] **Step 5: Commit** — `feat: SSE-safe bench client + deterministic prompt set`

---

### Task 3: Cell runners + host execution (GGUF sweep)

**Files:**
- Create: `scripts/run-cell-gguf.sh`
- Create: `docs/results/matrix-714/cells/*.json` (raw cells as measured)
- Modify: `docs/results/matrix-714/matrix.json` (statuses → measured)
- Test: `tests/test_cell_runner.py`

**Interfaces:**
- Consumes: bench_client (Task 2), gguf-quickstart env (GGUF_FILE/CTX_SIZE/WITH_MTP; plus runner-discovered `-np` flag pass-through — the quickstart gains `EXTRA_ARGS` env if needed for `-np N --ctx-size N×8192` concurrency semantics; any quickstart change must keep its UX tests green and defaults unchanged).
- Produces: per-cell raw JSON `{"id", "label", "base_url", "started_utc", "server_flags", "load": {"vram_mib", "gtt_mib"}, "client": <bench_client JSON>, "log_excerpt": [...]}`; matrix statuses updated. `- [ ]` semantics recorded in METHODOLOGY (llama.cpp slot split at pin).

- [ ] **Step 1: Failing test** — `tests/test_cell_runner.py`: runner script exists, references bench_client + matrix.json + rocm-smi, asserts id format, refuses unknown cell ids (reads matrix.json), `--dry-run` prints plan without launching.

- [ ] **Step 2: Verify failure** → FAIL.

- [ ] **Step 3: Implement + EXECUTE on host** — runner: resolve cell → server env (ctx per cell; MTP; `-np` concurrency semantics: record actual per-slot ctx from server log `n_ctx_slot`), boot quickstart (nohup), poll health, rocm-smi snapshot, run bench_client, kill server, write cell JSON + matrix update. Execute the declared GGUF priority subset: {base,mtp} × {1,4,8,16} @131072 + base × {32768,262144} × {1,4}. Anchor byte-identity check per config (greedy "OK"). Failures → cell still written with failures + matrix `measured(degraded)` note. 16 cells expected; ~1-2 min each warm.

- [ ] **Step 4: Run tests** — green; matrix.json shows measured cells with cell files present (add a consistency test: every matrix `measured` cell has a cells/*.json file and vice versa — put it in test_bench_schema.py or the runner test).

- [ ] **Step 5: Commit** — `feat: GGUF matrix cells (c×MTP sweep + ctx tiers) with raw receipts`

---

### Task 4: Host execution (vLLM sweep) + long-context smoke

**Files:**
- Create: `scripts/run-cell-vllm.sh`
- Create: `docs/results/matrix-714/cells/vllm-*.json`
- Modify: `docs/results/matrix-714/matrix.json`
- Test: extend `tests/test_cell_runner.py`

**Interfaces:**
- Consumes: bench_client; `scripts/03-serve-vllm.sh [--mtp]` (confs untouched; overrides only via documented env: the serve script gains `MAX_MODEL_LEN` env pass-through if needed — minimal change, UX tests stay green).
- Produces: vllm cells {base,mtp} × {1,4,8,16} @262144 (8 cells; ~6-10 min each incl. boot) + long-context retrieval smoke receipts (S3): needle-in-haystack at 100K and 200K context on ONE path (gguf — cheap boots; ctx via CTX_SIZE; judge exact-substring recall; record as `docs/results/matrix-714/long-context-smoke.json`).

- [ ] **Step 1: Failing test** — runner test extended for vllm ids + conf-untouched assertion (serve-args.conf byte-stable across the branch).

- [ ] **Step 2: Verify failure** → FAIL.

- [ ] **Step 3: Implement + EXECUTE** — same pattern as Task 3 (vLLM boot ~5 min per config; total session ~1-1.5 h GPU). Long-context smoke: build synthetic haystack (repeated filler paragraphs + planted unique sentence "The validation codename is STRIX-HALO-7741." at 80% depth), prompt asks for the codename, temperature 0; run at ctx 32768 (sanity), 131072, 262144 with prompts ~30K/120K/240K tokens; record recall + TTFT + memory. vLLM cells first (slow), gguf smoke after.

- [ ] **Step 4: Run tests** — green.

- [ ] **Step 5: Commit** — `feat: vLLM matrix cells + long-context retrieval smoke receipts`

---

### Task 5: Verdict generator + generated README blocks + anti-pit CI

**Files:**
- Create: `scripts/gen-verdicts.py`
- Create: `configs/benchmark-verdicts.json` (generated)
- Create: `scripts/render-readme-blocks.py`
- Modify: `README.md` (generated blocks: performance highlights, context-capacity table, known good and known bad)
- Create: `docs/results/benchmark.md` (human report)
- Test: `tests/test_verdicts.py`

**Interfaces:**
- Consumes: cells/*.json + matrix.json + METHODOLOGY rules.
- Produces: verdicts JSON (schema-valid, every measured cell verdicted, auto-ladder applied + `reviewed_by: "controller-<date>"`); README blocks between `<!-- BEGIN GENERATED: ... -->` markers (regeneration idempotent); `docs/results/benchmark.md` headline tables; CI test `test_quickstart_configs_are_recommended`: parses gguf-quickstart defaults (UD-Q4_K_XL, ctx 131072, MTP opt-in) + serve confs (262144, mtp num_spec 1) and asserts each referenced config maps to a `recommended` cell verdict in verdicts JSON (map: quickstart-default → gguf-udq4kxl-auto-base-c1-ctx131072 must be recommended; WITH_MTP → mtp-c1 recommended-or-caution-with-conditions; vllm baseline → vllm-bf16-auto-base-c1-ctx262144 recommended; vllm --mtp likewise) — if a measured cell is NOT recommendable, the test FAILS and the controller must change the quickstart default (or record a justified ruling) — that is the UX guarantee working as designed.

- [ ] **Step 1: Failing test** — `tests/test_verdicts.py`: schema-validate verdicts; every matrix `measured` cell has a verdict; auto-ladder unit tests on synthetic cells (abort→avoid; tpot 8 tok/s c1→not recommended; c16 aggregate up but per-stream 3 tok/s→caution/avoid; clean c4→recommended); README markers exist and regeneration is a no-op diff; quickstart-mapping assertions.

- [ ] **Step 2: Verify failure** → FAIL.

- [ ] **Step 3: Implement + RUN + human review** — generator applies the ladder; controller (you, implementer) review each verdict reason for honesty (especially ❌/⚠️ cells: reason + workaround + conditions filled); render README blocks: Performance highlights (both paths, best recommended configs), Context capacity (per config: max_usable_context + verdict from smoke + boot findings), Known good and known bad (every avoid cell + the recorded pits: vLLM encoder-profiling OOM without skip flag → conditions; gguf 262144 GTT growth → caution-with-conditions). Write benchmark.md with the full tables + links to raw cells. NO hand-editing inside markers.

- [ ] **Step 4: Run tests** — full suite green (50+ passed).

- [ ] **Step 5: Commit** — `feat: verdict system + generated README blocks + anti-pit CI guarantee`

---

## Verification (whole plan)

```bash
uv run --no-sync pytest -v                     # CPU suite green incl. anti-pit test
uv run --no-sync shellcheck -x scripts/*.sh scripts/lib/*.sh
python3 scripts/render-readme-blocks.py && git diff --exit-code   # blocks fresh
python3 scripts/gen-verdicts.py --check        # verdicts fresh vs cells
pgrep -fE "llama-server|vllm" || echo clean
git log --oneline main..HEAD                   # ≥ 5 commits
```

All green ⇒ the Adapt→Validate→Benchmark phases are complete; remaining Explain/Reproduce polish (full docs suite, getting-started, troubleshooting dead links, hardware-validation protocol) is the final release plan.
