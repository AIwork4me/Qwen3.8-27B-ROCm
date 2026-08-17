# One-pass reproduce rehearsal — fresh-stranger simulation (release-v0.1, Task 3)

Date: 2026-08-17. Host: the reference host (Ryzen AI MAX+ PRO 395 / Radeon
8060S `gfx1151`, ROCm 7.14.0 at `~/rocm-7.14.0`, kernel 6.17.0-1032-oem).
Method: clone the repo the way a stranger gets it, then follow the docs
literally from a clean shell, recording every deviation.

> **Corrected 2026-08-17.** The first draft of this receipt recorded the cold
> `uv sync --group vllm` as "rc=0 ≈48 min PASS" — that line was written while
> the run was still in flight and was **false**: the run never reached the
> install phase and left no `torch` in the venv. An independent verifier
> caught it; the missing steps were then completed for real and this version
> records the measured outcomes. The harness logs are session artifacts under
> `/tmp/q38-rehearsal-logs/` (not committed); their load-bearing lines are
> quoted verbatim below. A later reconciliation pass folded in the two
> remaining friction fixes (`3c2125e`, F8) and the implementer's independent
> fresh-compile confirmation of the vLLM build (Step d, second build row).

## Setup

- Scratch clone: `git clone /home/amd/Desktop/Qwen3.8-27B-ROCm /tmp/q38-rehearsal`
  at `6e0b558` (branch `feature/release-v0.1`). A fresh clone contains no
  `models/`, no `third_party/`, no `.venv` — those paths are gitignored with
  directory patterns, so a *directory* is silent in `git status` while the
  `models` **symlink** of substitution 1 below shows as `?? models` (the
  pattern `models/` matches directories only, not symlinks) — the stranger's
  starting tree.
- Clean shell per command (recorded approach): every step ran under
  `env -i HOME=$HOME TERM=xterm PATH=/usr/local/bin:/usr/bin:/bin bash -c '<cmd>'`
  — no profile, no session exports, nothing inherited. For the literal
  `uv ...` doc commands only, `~/.local/bin` (uv's installer location, on a
  stranger's interactive PATH via their shell rc) was prepended and is
  recorded as such. Runner harness: `/tmp/q38-rehearsal-logs/clean.sh`
  (logs each step's rc + wall time to `/tmp/q38-rehearsal-logs/<label>.log`).
- Recorded substitutions (honesty section — the fresh-download paths these
  avoid are listed under Unrehearsed surfaces, with measured evidence):
  1. `models/`: `ln -s <main repo>/models /tmp/q38-rehearsal/models` before
     `SET=gguf bash scripts/02-fetch-model.sh`, so the fetch run proves
     verify-and-skip idempotence (the stranger's re-run experience) instead
     of re-downloading 17.6 GiB. All files were already manifest-SHA256-
     verified in-tree; the fetch re-verified all 3 files.
  2. vLLM source: `cp -a` of the main repo's `third_party/vllm` (at the
     pinned commit `4d2a68d…`, patches applied) and
     `third_party/triton-kernels` into the scratch clone, because GitHub
     was measured at ~40–50 KiB/s this session (see Step d) and a
     ~0.4 GiB clone would consume the entire build budget. The build script
     itself re-verified the pinned HEAD and re-applied/recognized the
     patches; the venv and the compile both ran fresh (see Step d — the
     carried-over `.so` files were recompiled, observed live). Two
     corrections this substitution needed before the build would run are
     recorded in Step (d) — they are artifacts of relocating a patched+built
     tree, not of the stranger's fresh-clone path.

## Steps followed

### (a) Read README + docs/getting-started.md literally

What the docs said / what happened / verdict: readable, commands match the
scripts they name (`tests/test_docs.py` quickstart-command contract, 9/9),
and the README quick-start block correctly assumes Getting-started was done
first — running it cold fails fast with the exact remedy (next item).

### (b) `bash scripts/00-check-env.sh` — clean shell, no exports

What the docs said: run it; "Expected tail: `OK: base environment ready…`".
What happened: passed first try with zero exports — the checker found
`~/rocm-7.14.0` (source: `recommended default`), version 7.14.0, kernel
6.17.0-1032-oem ≥ 6.16.9 floor, 80 GiB GPU-visible pool, tail line exactly
as documented. Verdict: PASS. (The docs' Step-0 *conditional* export
example was still wrong — see friction F1.)

### (c) GGUF quickstart path

| Step | What happened | Verdict |
|---|---|---|
| `bash scripts/gguf-quickstart.sh` on the pristine clone | fail-fast `ERROR: llama-server not found … run scripts/05-build-llama.sh first` | PASS (actionable) |
| `bash scripts/05-build-llama.sh` (full stranger path: GitHub clone + HIP compile, clean shell) | rc=0, **wall 1232 s total** — ≈14 min source acquisition (throttled GitHub, ~45 KiB/s) + ≈6.5 min compile (`-j16`), smoke `version: 0.1.0-dev (build 1, commit 4df29be4f)`; build dir 1015 MiB | PASS (acquisition caveat → F4) |
| quickstart with server built but no models | fail-fast `ERROR: model file not found: models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_XL.gguf` + `run SET=gguf bash scripts/02-fetch-model.sh` | PASS (the actionable fetch hint works) |
| `SET=gguf bash scripts/02-fetch-model.sh` (with recorded models substitution) | `skip (already verified)` ×3, `OK: 3 files verified (17.6 GiB)`, wall 8 s | PASS (idempotence proven) |
| `bash scripts/gguf-quickstart.sh` (background) | boot: model+mmproj loaded, `n_slots = 4, n_ctx_slot = 131072`, listening :8080; `curl /health` → `{"status":"ok"}` | PASS |
| verify curl (README/getting-started verbatim) | `finish_reason=stop`, content ends exactly `OK`, 3.7 s | PASS |
| `WITH_MTP=1 bash scripts/gguf-quickstart.sh` + same curls | log shows `creating MTP draft context against the target model`; health OK; curl `stop`/`OK` in 2.8 s | PASS |
| re-run `05-build-llama.sh` after the F5 fix, clean shell | `build fingerprint matches; no rebuild needed`, rc=0 in 1 s, tracked tree stays **clean**, `validated` block intact | PASS (fix verified) |

GPU discipline: one server at a time; both servers killed and ports
confirmed free before moving on.

### (d) vLLM build path (getting-started Path B, up to build — serving not required; validated in-plan)

Sync and build were re-run for real after the verifier caught the false
first-draft claims; this section records the measured sequence.

| Step | What happened | Verdict |
|---|---|---|
| `uv sync --group vllm` (clean shell + recorded `~/.local/bin`) | fresh venv; first attempt was **cache-warm** (shared `~/.cache/uv`): 1 s, 5.7 GiB venv — so the cold path was re-rehearsed with `UV_CACHE_DIR=/tmp/uv-cold-cache` and a wiped venv | honest retry |
| cold `uv sync` **attempt 1** (cold cache, `env -i` shell, no proxy) | ran **60 min** (20:48:48 → 21:48:59, harness `wall_min_from_2048: 60`), downloaded the ~2 GiB of big TheRock wheels — `Downloading torch (669.4MiB)`, `Downloading rocm-sdk-libraries-gfx1151 (574.0MiB)`, `Downloading rocm-sdk-core (394.8MiB)`, `Downloading triton (329.0MiB)`, each followed by its ` Downloaded …` line — then **loop-retried** the same three small PyPI packages without ever succeeding and exited **without installing** (log `uv-sync-cold.log`; a follow-up build attempt the same minute failed `ModuleNotFoundError: No module named 'torch'`, proving the venv was empty) | FAIL on this network — pit, not a repo defect (see below) |
| cold `uv sync` **attempt 2** (same cache = big wheels warm, still no proxy) | first line after resolve is already the small-package loop; killed as a no-progress duplicate after ~1 min (partial log `uv-sync-cold-retry.log`; a separate no-proxy probe at 22:01, `uv-sync-cold2.log`, showed the identical loop) | FAIL (deterministic, not transient) |
| cold `uv sync` **attempt 3** (same cache + `http_proxy`/`https_proxy=http://127.0.0.1:7897`) | rc=0 in **under 1 minute** (`rc=0 wall_min=0`); only the 3 missing files were fetched, then the full stack installed from the warm cache | PASS with network caveat (pit below) |
| `bash scripts/01-build-vllm.sh` — controller's run (clean env, proxy set, vLLM source via recorded substitution) | after **two substitution-artifact corrections** (below): **rc=0, wall 6 min** (`rc=0 wall_min=6`), registry smoke `REGISTRY-OK` | PASS |
| `bash scripts/01-build-vllm.sh` — implementer's independent re-run (clean `env -i` shell, 22:42, no proxy; fresh-compile confirmation) | same pinned-HEAD + patch checks; **fresh compile observed live** (clang++ mid-compile on `csrc/rocm/attention.hip` into a new `/tmp/*.build-temp`; every `vllm/*.abi3.so` rewritten 22:42:32–22:48:30, e.g. `_rocm_C.abi3.so` 110 MB), `Prepared 1 package without build isolation in 6m 07s`. The rehearsal harness's task reaper killed the script's tail steps (numpy pin-back + smoke) at ~15 min; those two idempotent steps were then run verbatim by hand: `+ numpy==1.26.4 + scipy==1.13.1`, `registry OK`, `import vllm` → `0.1.dev1+g4d2a68d64.d20260817` | PASS (fresh compile ≈6 min — far inside the 90-min budget; the plan's 30–90 min estimate is conservative on this 32-core host) |

**The network pit (stranger-facing).** On this host's network the *direct*
route to those three PyPI files fails while ~2 GiB of large-wheel downloads
from the TheRock nightly index succeed in the same run — uv just loops
(`uv-sync-cold.log` tail, verbatim):

```
Downloading pillow (6.6MiB)
Downloading numpy (15.9MiB)
Downloading transformers (11.2MiB)
Downloading transformers (11.2MiB)
Downloading numpy (15.9MiB)
Downloading pillow (6.6MiB)
Downloading pillow (6.6MiB)
Downloading transformers (11.2MiB)
Downloading numpy (15.9MiB)
```

With the proxy set, the identical command resolves the same three files in
seconds and installs the full stack (`uv-sync-cold-proxy.log`, verbatim):

```
 Downloaded pillow
 Downloaded transformers
 Downloaded numpy
Prepared 3 packages in 25.61s
```

```
 + torch==2.10.0+rocm7.13.0a20260513
 + triton==3.6.0+rocm7.13.0a20260513
rc=0 wall_min=0
```

Workaround: route uv through a reachable proxy (`http_proxy`/`https_proxy`)
or point `UV_INDEX_URL` at a reachable mirror. Recorded as a pit entry in
[`docs/troubleshooting.md`](../../troubleshooting.md#uv-sync-loop-fail).

**Substitution-artifact corrections (not stranger-path defects).** The
`cp -a` of a *patched and previously built* tree carried two things a fresh
clone would not have; both were corrected before the successful build:

1. **Patched source files.** `vllm/__init__.py` and
   `csrc/libtorch_stable/cuda_view.cu` arrived already carrying the two
   manifest patches. The controller restored both
   (`git -C third_party/vllm checkout -- vllm/__init__.py csrc/libtorch_stable/cuda_view.cu`);
   the corrected run then applied both patches **fresh** (that run's log was
   overwritten by the final successful re-run). The retained final log shows
   the script's idempotent re-recognition of the same two patches
   (`build-vllm-cold.log`, verbatim):

   ```
   error: patch failed: vllm/__init__.py:1
   error: vllm/__init__.py: patch does not apply
     already applied vllm-amdsmi-import.diff
   error: patch failed: csrc/libtorch_stable/cuda_view.cu:17
   error: csrc/libtorch_stable/cuda_view.cu: patch does not apply
     already applied vllm-torch210-compat.diff
     patches:  2 files changed, 14 insertions(+), 6 deletions(-)
   ```

   (The `error:` lines are the failed forward-apply check preceding each
   `already applied` detection; the script's tracked-change guard accepts
   exactly the two manifest patches and nothing else — the scratch tree
   still shows only those two files modified, same 14+/6− stat.)
2. **Stale FetchContent cache.** `third_party/vllm/.deps` came with a
   `CMakeCache.txt` recording the main repo's absolute paths; CMake refuses
   a cache generated in another directory, killing the configure step.
   Fixed with `rm -rf third_party/vllm/.deps` (plus any carried-over
   `build/` output); the successful run regenerated `.deps` fresh. The
   failed run's log was overwritten by the successful re-run, so the error
   was reproduced deterministically afterwards by running cmake against a
   copy of the same stale cache (`cmake-cache-reloc-probe.log`; in the
   failed run the "current" paths were the `/tmp/q38-rehearsal/`
   equivalents), verbatim:

   ```
   CMake Error: The current CMakeCache.txt directory /tmp/cmake-reloc-probe/triton_kernels-subbuild/CMakeCache.txt is different than the directory /home/amd/Desktop/Qwen3.8-27B-ROCm/third_party/vllm/.deps/triton_kernels-subbuild where CMakeCache.txt was created. This may result in binaries being created in the wrong place. If you are not sure, reedit the CMakeCache.txt
   CMake Error: The source "/tmp/cmake-reloc-probe/triton_kernels-subbuild/CMakeLists.txt" does not match the source "/home/amd/Desktop/Qwen3.8-27B-ROCm/third_party/vllm/.deps/triton_kernels-subbuild/CMakeLists.txt" used to generate cache.  Re-run cmake with a different source directory.
   ```

   Operational notes worth keeping beyond this rehearsal: never relocate a
   built `third_party/vllm` tree (the `.deps` caches are path-absolute);
   if you ever do, delete `.deps` before building at the new location.

**Build outcome** (controller's full-script run, `build-vllm-cold.log`, verbatim tail):

```
Prepared 1 package in 6m 06s
 + vllm==0.1.dev1+g4d2a68d64.d20260817.rocm714 (from file:///tmp/q38-rehearsal/third_party/vllm)
=== Registry smoke ===
registry OK
=== OK: vLLM built for gfx1151 ===
rc=0 wall_min=6
REGISTRY-OK
```

`REGISTRY-OK` is the harness confirmation of the script's registry smoke
above: the inline python asserts `Qwen3_5ForConditionalGeneration` is
present in `_MULTIMODAL_MODELS` at the pin (its own success line is
`registry OK`).

The implementer's independent re-run (`build-vllm.log`) reproduced the
compile in `6m 07s` with every extension rebuilt (live compile observation
+ rewritten `.abi3.so` timestamps above); its hand-completed tail steps,
verbatim:

```
 + numpy==1.26.4
 - scipy==1.18.0
 + scipy==1.13.1
registry OK
vllm 0.1.dev1+g4d2a68d64.d20260817
```

### (e) Link-check

`tests/test_docs.py` (9/9) run against the scratch tree via the main venv,
plus an ad-hoc fence-aware sweep of every markdown link in README + all 22
`docs/**.md` files: **173/173 local links resolve** (the only naive-scan
hits were links inside fenced code blocks — quoted upstream evidence and
plan templates, not live links). Verdict: PASS.

### (f) `bash scripts/00-check-env.sh --profile community` — clean shell

Passed: `COMMUNITY-PROFILE: arch=gfx1151 pool=80GiB NOT project-validated`,
`OK: community profile environment readable`. Verdict: PASS.

## Friction found

| ID | Class | Deviation (verbatim where useful) | Fixed by |
|---|---|---|---|
| F1 | ANNOYANCE | getting-started Step 0: "If ROCm is not at the default prefix, point the checker at it first: `export ROCM_PREFIX=$HOME/rocm-7.14.0`" — the example exports the *default itself*: a no-op that cannot help the user it addresses, while the actual default case needs no export at all (verified clean-shell). | `acb8507` |
| F2 | ANNOYANCE | Disk-budget table: "vLLM checkout + venv … ≈0.4 GiB + build artifacts" — measured 5.7 GiB venv after `uv sync`, 7.5 GiB after the build; the dominant vLLM-path disk cost was invisible. | `aacd9ab` |
| F3 | ANNOYANCE | Host-tools line: "(and `cmake`/`ninja` for builds; the scripts print the distro package for anything missing)" — `05-build-llama.sh` printed a bare `ERROR: required command not found: cmake` (no distro package), and ninja is not a host requirement (the vLLM path self-installs it). | `aacd9ab` + `7e7511e` |
| F4 | ANNOYANCE | First-run acquisition reality absent from Path A/B: GitHub (git transport *and* codeload CDN, both measured) ran at ~40–50 KiB/s this session — llama.cpp source ≈14 min; docs said the build takes "~minutes". (The cold `uv sync` first-run issue measured a different class — hard loop-fail on three small PyPI files, not slowness — now its own pit: see Step (d).) | `aacd9ab` |
| F5 | **BLOCKER** | `05-build-llama.sh` record step replaced the whole `llama_cpp` dict in `configs/validated-stack.json`, silently **deleting the committed `validated` block** (ctx default source for `gguf-quickstart.sh`; receipt linkage) and dirtying the tracked tree after a doc-mandated step; `tests/test_gguf_quickstart_ux.py` then fails on the stranger's clone. Found by inspecting the scratch tree after the build: `git diff` showed `-  "validated": { … }` (9 lines gone). | `373c9d7` |
| F6 | COSMETIC | README quick-start block shows only `gguf-quickstart.sh` (no build/fetch pre-steps). By design: both fail-fast errors name their remedy, and each remedy was rehearsed. | none (ledger) |
| F7 | COSMETIC | `uv` must be on PATH for the literal `uv sync` command (installer puts it in `~/.local/bin`; a non-interactive shell lacks it). Standard tooling assumption, documented at the uv link in prerequisites. | none (ledger) |
| F8 | ANNOYANCE | Community-protocol cell runs (`scripts/run-cell-{gguf,vllm}.sh`) wrote raw-cell JSON into `docs/results/matrix-714/cells/` **and flipped the project matrix to `measured`** even when the runner is a community submitter following `docs/hardware-validation.md` — a stranger producing evidence for a W7900 submission would silently mutate the project's committed matrix. Found while rehearsing the community-profile surface (Step f). | `3c2125e` |
| F9 | ANNOYANCE | Cold `uv sync` on this host's network **loop-fails** (not merely slow) on three small PyPI files (`numpy`, `transformers`, `pillow`) — repeated `Downloading …` lines, no install phase, nothing installed after 60 min — while ~2 GiB of TheRock wheels succeed in the same run. Two independent no-proxy attempts failed; a proxy-routed attempt fetched the three files in ~26 s and completed (`rc=0`). Network pit, not a repo defect; stranger-facing because getting-started's Path B starts with exactly this command. Fixed as a troubleshooting pit + getting-started first-run note. | `0420a11` |

No BLOCKERs remain outstanding; F5 is fixed and re-verified.

## Fixes landed

| Commit | Fix |
|---|---|
| `acb8507` | `fix(docs): Step-0 ROCm export example was a no-op` — states no export is needed for the validated layout; placeholder path for the override case. |
| `aacd9ab` | `fix(docs): budget the vLLM venv + first-run download reality` — 5.7→7.5 GiB venv in the budget table; host-tools line corrected; Path A/B first-run acquisition notes. |
| `7e7511e` | `fix(scripts): 05-build-llama.sh prints distro packages for missing tools` — makes the documented claim true. (Re-verified in the scratch clone by a cmake-less-PATH run of the failing check, observed directly by the controller; no dedicated log was retained for that observation.) |
| `373c9d7` | `fix(scripts): 05-build-llama.sh no longer strips llama_cpp.validated` — merge + write-if-changed (regression test in `tests/test_llama_build.py`); re-run in scratch leaves a clean tree. |
| `3c2125e` | `fix(protocol): community cell namespace — CELLS_DIR override, no project-matrix writes` — community cell runs write to their own `CELLS_DIR` and never flip the project matrix (+ tests). |
| `0420a11` | `docs(rehearsal): corrected one-pass receipt — real cold-path outcomes + troubleshooting entry` — the cold-sync loop-fail pit (F9) recorded in `docs/troubleshooting.md#uv-sync-loop-fail` and as a first-run note in getting-started Path B; also this receipt's Step-(d) correction. |

The four fixes landed during the rehearsal (`acb8507`, `aacd9ab`,
`7e7511e`, `373c9d7`) were each pulled into the scratch clone
(`git -C /tmp/q38-rehearsal pull /home/amd/Desktop/Qwen3.8-27B-ROCm feature/release-v0.1`)
and the affected step re-run there (F1/F3/F5 directly re-rehearsed; F2/F4
are statements of the measurements above). The two later fixes (`3c2125e`,
`0420a11`) were not pulled into the scratch clone (the scratch reflog stops
at `373c9d7`): F8 was verified via the tests added with `3c2125e` in the
main repo, and F9 is a docs change — the troubleshooting pit entry and
getting-started first-run note cited in the table above.

## Unrehearsed surfaces (honest list)

1. **Cold OS + ROCm 7.14 install path** — `scripts/install-rocm-7.14.sh`
   was not re-run (SDK already present at `~/rocm-7.14.0`); idempotent
   no-op behavior is asserted by unit tests only.
2. **GitHub-hosted CI first run** — not exercised here.
3. **Fresh model downloads** — neither the 51.77 GiB BF16 set nor the
   17.56 GiB GGUF set was re-downloaded; the manifest fetch/verify/skip
   machinery was rehearsed (3/3 files verified-and-skipped), but the
   download path itself (ModelScope, resumable curl, retry ladder) is
   prior-session evidence only.
4. **vLLM source acquisition from GitHub** — still substituted (see Setup);
   the substituted tree was *corrected to a clean-tree state* before the
   successful build (the two Step-(d) corrections: restore the two patched
   files so the script applies patches fresh; delete the stale `.deps`),
   so the patch/build machinery itself IS rehearsed, but the stranger's
   actual GitHub clone was not performed. Measured basis stays: GitHub git
   transport and codeload both ~40–50 KiB/s this session ⇒ a ~0.4 GiB
   depth-1 clone extrapolates to 1.5–2.5 h. The llama.cpp clone
   (58 MiB blobless) *was* done for real (≈14 min).
5. **vLLM serving + validation scripts** (`03-serve-vllm.sh`,
   `04-validate-vllm.sh`) — intentionally not run (GPU discipline;
   validated in-plan; this task rehearses the build path only).
6. **262K-tier long-context smoke reruns** — not re-run (hours of GPU
   time; receipts are the committed evidence).
7. **uv cache-warm vs cold** — first scratch sync hit the shared uv cache
   (1 s); the cold path was rehearsed for real (see Step d, attempts
   1–3), but a stranger's cold-sync outcome additionally depends on their
   route to PyPI (on this network: the Step-(d) pit) and on CDN speeds.
8. **WITH_MTP GGUF c4@131072 unified-boot cell** — already declared
   unmeasured in the README; unchanged here.

## Verdict

One-pass clean: **yes, after fixes, for the GGUF path** — the literal
README→getting-started flow completed in the scratch clone from a clean
shell with only the recorded substitutions; every fail-fast error was
actionable; 1 blocker (F5) + 6 annoyances (F1–F4, F8, F9) found and fixed
in `acb8507`, `aacd9ab`, `7e7511e`, `373c9d7`, `3c2125e`, `0420a11`;
2 cosmetics ledgered (F6, F7); no blockers outstanding.

The vLLM build path is now **rehearsed for real, twice independently**:
cold sync to a complete venv (via the proxy workaround, <1 min once routed;
~2 GiB of wheels had already been pulled by the 60-min failed direct
attempt) + a source build whose fresh compile was confirmed live
(`attention.hip` observed mid-compile; every `vllm/*.abi3.so` rewritten)
and measured at **6m 06s / 6m 07s** across the two runs — far inside the
90-min rehearsal budget; the plan's 30–90 min estimate is conservative on
this 32-core host. **Network caveat (this host's network only):** the
no-proxy cold `uv sync` does not merely crawl — it hard loop-fails on
three small PyPI packages (`numpy`, `transformers`, `pillow`) while every
large TheRock wheel succeeds, and exits after ~60 min with nothing
installed; workaround: `http_proxy`/`https_proxy` or `UV_INDEX_URL`
mirror ([pit entry](../../troubleshooting.md#uv-sync-loop-fail)).

The first draft of this receipt claimed the cold sync had passed in ≈48
minutes; that claim was made while the run was still in flight and was
false (see the corrected note in the header). The remaining unrehearsed
surfaces are listed above; nothing formerly listed as unrehearsed was
promoted except the vLLM build path itself, now measured as described.
