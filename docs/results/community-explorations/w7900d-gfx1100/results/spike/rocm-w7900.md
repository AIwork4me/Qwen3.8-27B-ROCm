# Spike R: ROCm 7.14.0 on W7900 (gfx1100) — 2026-08-16

All probes run 2026-08-16 on this host (gfx1100, kernel 6.8.0-79-generic). Outputs are quoted verbatim; nothing is paraphrased or invented.

## Q1: does a W7900 have an official ROCm 7.14.0 channel?

- Probe:
  - `curl -sI -m 20 "https://repo.amd.com/rocm/tarball-multi-arch/therock-dist-linux-gfx110X-all-7.14.0.tar.gz" | grep -iE '^HTTP|content-length'`
  - `curl -s -m 20 "https://repo.radeon.com/rocm/apt/latest/dists/noble/main/binary-amd64/Packages.gz" | gunzip | grep -A2 '^Package: rocm-core$' | head -4`
  - `for f in gfx1100-dgpu gfx942 gfx120x; do printf '%s-7.14.0 -> ' "$f"; curl -s -o /dev/null -m 20 -w '%{http_code}\n' -I "https://repo.amd.com/rocm/tarball-multi-arch/therock-dist-linux-$f-7.14.0.tar.gz"; done`
- Evidence:
  ```
  HTTP/2 200
  content-length: 2313039793
  ```
  The exact Q1b grep fetches the Packages.gz successfully but its `-A2` window prints only the stanza's first lines; this repo's rocm-core stanza carries no `Version:` field, so the version was read from the same fetched stanza with a widened window (`grep -A16 '^Package: rocm-core$'`):
  ```
  Package: rocm-core
  Architecture: amd64
  Depends: python3, libc6
  Priority: optional
  Section: devel
  Filename: pool/main/r/rocm-core/rocm-core_7.2.4.70204-93~24.04_amd64.deb
  ...
  ```
  (elided: the stanza continues with Size/SHA256/SHA1/MD5sum/Description/Homepage/Maintainer lines, omitted here.)
  ```
  gfx1100-dgpu-7.14.0 -> 403
  gfx942-7.14.0 -> 403
  gfx120x-7.14.0 -> 403
  ```
- Conclusion: the official `gfx110X-all` tarball exists (HTTP 200, 2,313,039,793 bytes); the mainline apt repo (`rocm/apt/latest`, noble) tops out at the 7.2.4 train (rocm-core 7.2.4.70204-93~24.04); no single-arch gfx1100/gfx942/gfx120x tarball exists (403). The official ROCm 7.14.0 channel for a W7900 is therefore the multi-arch `gfx110X-all` tarball — not apt, not a single-arch tarball.

## Q2: does the sibling project's gfx1151 tarball work on W7900?

- Probe:
  - `printf 'gfx1151 prefix Tensile files: '; ls /root/rocm-7.14.0/lib/rocblas/library/ 2>/dev/null | grep -c TensileLibrary || echo 0`
  - `printf 'gfx110X-all prefix gfx1100 kernels: '; ls /root/rocm-7.14.0-gfx1100/lib/rocblas/library/ 2>/dev/null | grep -c 'gfx1100' || echo 0`
- Evidence (verbatim; the lone second `0` is the `|| echo 0` branch firing because `grep -c` exits 1 on zero matches):
  ```
  gfx1151 prefix Tensile files: 0
  0
  gfx110X-all prefix gfx1100 kernels: 150
  ```
  Supplementary counts (run 2026-08-16, quoted verbatim). gfx110X-all prefix:
  - `ls /root/rocm-7.14.0-gfx1100/lib/rocblas/library/ | wc -l` and `ls /root/rocm-7.14.0-gfx1100/lib/rocblas/library/ | grep -c Kernels.so` and `ls /root/rocm-7.14.0-gfx1100/lib/rocblas/library/ | grep -c TensileLibrary`:
    ```
    600
    4
    596
    ```
  - Per-arch counts — `for a in gfx1100 gfx1101 gfx1102 gfx1103; do printf '%s: ' "$a"; ls /root/rocm-7.14.0-gfx1100/lib/rocblas/library/ | grep -c "$a"; done`:
    ```
    gfx1100: 150
    gfx1101: 150
    gfx1102: 150
    gfx1103: 150
    ```
  gfx1151 prefix:
  - `ls /root/rocm-7.14.0/lib/rocblas/library/` then `ls /root/rocm-7.14.0/lib/rocblas/library/gfx1151/ | wc -l` then `find /root/rocm-7.14.0/lib/rocblas -name '*gfx1100*' | wc -l`:
    ```
    gfx1151
    150
    0
    ```
  Inference (derived from the quoted counts, not itself a command output): 600 total = 4 arches x 150 = 4 Kernels.so code objects + 596 TensileLibrary files, i.e. the design spec's "596 gfx1100/1101/1102 kernels" is the family-wide TensileLibrary count, while the brief's exact per-arch grep reports 150 for gfx1100. The gfx1151 prefix keeps its rocBLAS data under `library/gfx1151/` (150 files, gfx1151 only) and has 0 gfx1100 files anywhere in its rocBLAS tree.
- Cited evidence: muse-rocm committed finding — Finding 1 of `/workspace/Muse-Glimmer-30B-ROCm/docs/results/hardware-validation/w7900-gfx1100/cells-rocm-7.14.0/README.md`, quoted verbatim:
  > 1. **The gfx1151 tarball cannot serve a W7900 beyond single-stream.** The
  >    repo's pinned `therock-dist-linux-gfx1151-7.14.0.tar.gz` ships rocBLAS
  >    Tensile data for gfx1151 only. Batched (multi-slot) decode calls rocBLAS
  >    and dies: `rocBLAS error: Cannot read .../TensileLibrary.dat ... for GPU
  >    arch : gfx1100` → `llama-server` core-dumps; c=1 cells appear healthy.
  >    W7900 hosts must use the **`gfx110X-all`** tarball (or distro packages
  >    covering gfx1100). Observed 2026-08-16; the four c=1 cells first measured
  >    under the gfx1151 tarball were discarded and re-measured under gfx110X.
- Conclusion: gfx1151 tarball unusable on W7900; gfx110X-all required. The local counts corroborate the mechanism behind the muse core-dump: 0 gfx1100 Tensile files in the gfx1151 prefix vs 150 gfx1100 TensileLibrary/Kernels entries in the gfx110X-all prefix on this very host.

## Q3: does the local 7.14.0-gfx1100 prefix drive this GPU?

- Probe:
  - `PATH=/root/rocm-7.14.0-gfx1100/bin:$PATH /root/rocm-7.14.0-gfx1100/bin/rocminfo 2>/dev/null | grep -m2 -E 'Name: *gfx1100|Marketing Name'` (plus a follow-up grep on the same rocminfo output filtered to the GPU agent)
  - Source `/root/spike_r.hip` (trivial scale-by-2 HIP kernel, exactly as specified in the task brief), then:
    `PATH=/root/rocm-7.14.0-gfx1100/bin:$PATH LD_LIBRARY_PATH=/root/rocm-7.14.0-gfx1100/lib /root/rocm-7.14.0-gfx1100/bin/hipcc --offload-arch=gfx1100 /root/spike_r.hip -o /root/spike_r` followed by running `/root/spike_r` under the same `PATH`/`LD_LIBRARY_PATH`.
- Evidence (verbatim):
  - The brief's exact rocminfo grep stops (`-m2`) at the two CPU entries:
    ```
      Marketing Name:          AMD EPYC 9334 32-Core Processor
      Marketing Name:          AMD EPYC 9334 32-Core Processor
    ```
  - The same rocminfo, filtered to the GPU agent — `PATH=/root/rocm-7.14.0-gfx1100/bin:$PATH /root/rocm-7.14.0-gfx1100/bin/rocminfo 2>/dev/null | grep -E 'Name: *gfx1100|Marketing Name' | grep -v EPYC; echo "rc=$?"`:
    ```
      Name:                    gfx1100
      Marketing Name:          AMD Radeon Pro W7900D
    rc=0
    ```
  - hipcc compile: silent, exit 0 (`compile rc=0`; the anticipated [[nodiscard]] warnings did not appear).
  - Run:
    ```
    spike-r kernel result: 2 4 6 8
    kernel rc=0
    ```
- Conclusion: supported — verified locally, corroborated by the sibling project's 14/14-cell matrix on the same kernel (6.8.0-79-generic). The prefix compiles for gfx1100 and executes a kernel on this GPU; rocminfo under the prefix reports the GPU as `gfx1100` / "AMD Radeon Pro W7900D" (the W7900-family 48 GiB gfx1100 card on this host).

## Impact

The serving and benchmark phases build on the validated `/root/rocm-7.14.0-gfx1100` prefix — the official `gfx110X-all` 7.14.0 tarball, verified end-to-end on this GPU by Spike R's compile-and-run and corroborated by the muse project's 14/14-cell matrix; the system `/opt/rocm` 7.2.1 stack stays untouched as the warn+pass fallback for CPU-only work; and the sibling `/root/rocm-7.14.0` gfx1151 prefix is a documented trap on this host (0 gfx1100 Tensile files locally, multi-slot-decode core dumps per the cited muse finding), so no script may ever select it.
