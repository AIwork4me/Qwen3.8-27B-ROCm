#!/usr/bin/env python3
"""Long-context retrieval smoke (study S3, METHODOLOGY.md §1) — GGUF path.

Needle-in-a-haystack functional smoke for the context-capacity tiers:
synthetic haystack (repeated deterministic filler paragraphs), one planted
unique needle sentence — ``The validation codename is STRIX-HALO-7741.`` —
at ~80% depth, a prompt that asks ONLY for the codename, temperature 0,
max_tokens 64. Judge: exact substring ``STRIX-HALO-7741`` in the output.

Purpose (METHODOLOGY §1 S3): guard against "boots but attention degraded"
false positives that raw throughput cannot catch. A tier that fails to boot
or to answer is recorded as a FAILED TIER — a finding, never a task failure.

Boots the validated GGUF quickstart per tier (cheap boots; CTX_SIZE per
tier; default unified boot — exactly what a quickstart user gets), health
polls, snapshots load VRAM/GTT (rocm-smi, MiB binary), sizes the haystack
via the server's /tokenize endpoint (exact, not a chars-per-token guess),
fires ONE streaming request through bench_client's SSE consumer (same
framing-safe instrument as the matrix cells), records recall + TTFT +
prompt_tokens + memory, kills the server, waits for GTT drain.

Instrument mode: same as the matrix cells — chat_template_kwargs
{"enable_thinking": false} — so the 64-token budget goes to the ANSWER, not
to reasoning (METHODOLOGY §2 erratum).

Usage (host only; the default out path is committed evidence):
  python3 scripts/long-context-smoke.py [--out docs/results/matrix-714/long-context-smoke.json]

Output JSON shape:
  {"description", "needle", "judge", "path", "argv", "generated_utc",
   "tiers": [{"ctx_size", "target_prompt_tokens", "prompt_tokens", "recall",
              "ttft_ms", "completion_tokens", "finish_reason",
              "answer_excerpt", "haystack", "load": {"vram_mib", "gtt_mib"},
              "boot_wall_s", "ok", "error"}]}

``argv`` is the verbatim ``sys.argv`` of the invocation, so every future
receipt self-documents its exact tier/timeout flags (the committed 247K-tier
receipt predates this field — its run had to raise --request-timeout above
the default; METHODOLOGY §1 records the finding, do not re-run to backfill).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import bench_client  # noqa: E402  (same SSE-safe instrument as the matrix cells)

NEEDLE_DEFAULT = "The validation codename is STRIX-HALO-7741."
JUDGE_SUBSTRING = "STRIX-HALO-7741"
QUESTION = "What is the validation codename mentioned in the documents above? Reply with the codename only."
# Filler paragraph: deterministic, inert maintenance-log prose. The {i} makes
# paragraphs non-identical (no trivially-compressible wall of copies) while
# staying token-count-stable (digit count varies by 1-2 tokens/paragraph).
FILLER_PARAGRAPH = (
    "Facility note {i}: the maintenance log for sector {i} records a routine "
    "calibration of the coolant manifold and a visual inspection of the belt "
    "tensioner assembly. Flow readings stayed within the usual tolerance band "
    "and no replacement parts were ordered. The technician signed the entry, "
    "archived the pressure chart, and scheduled the next inspection window "
    "for the following quarter without raising any advisory flags."
)

# ctx tier -> target prompt tokens (leaves headroom for the chat template,
# the 64-token answer cap, and tokenizer drift; tiers are "~30K/120K/240K").
DEFAULT_TIERS = [(32768, 28000), (131072, 112000), (262144, 228000)]
TEMPLATE_MARGIN_TOKENS = 64


def build_haystack(target_tokens, count_tokens, needle=NEEDLE_DEFAULT,
                   question=QUESTION, template_margin=TEMPLATE_MARGIN_TOKENS):
    """Deterministically build the needle prompt for ~target_tokens.

    ``count_tokens(text) -> int`` is an exact counter (the server's
    /tokenize endpoint in production; any deterministic function in tests).
    Returns (prompt, meta). The needle paragraph is inserted after ~80% of
    the filler; the question is the final sentence.
    """
    para = FILLER_PARAGRAPH.format(i=1)
    para_tokens = max(1, count_tokens(para))
    overhead = count_tokens(needle) + count_tokens(question) + template_margin
    repeats = max(2, (target_tokens - overhead) // para_tokens)
    paragraphs = [FILLER_PARAGRAPH.format(i=i) for i in range(1, repeats + 1)]
    needle_at = max(1, round(repeats * 0.8))
    paragraphs.insert(needle_at, needle)
    prompt = "\n\n".join(paragraphs) + "\n\n" + question
    estimated = count_tokens(prompt)
    depth = prompt.index(JUDGE_SUBSTRING) / max(1, len(prompt))
    meta = {
        "filler_paragraphs": repeats,
        "filler_paragraph_tokens": para_tokens,
        "needle_after_paragraph": needle_at,
        "needle_depth_fraction": round(depth, 4),
        "estimated_prompt_tokens": estimated,
    }
    return prompt, meta


def http_json(url, payload=None, timeout=600):
    if payload is None:
        req = urllib.request.Request(url, method="GET")
    else:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tokenize_count(base_url, text):
    """Exact token count via llama-server POST /tokenize."""
    out = http_json(base_url + "/tokenize", {"content": text}, timeout=300)
    return len(out["tokens"])


def rocm_smi_mib(kind):
    out = subprocess.run(["rocm-smi", "--showmeminfo", kind],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if f"{kind.upper()} Total Used" in line:
            return int(line.split()[-1]) // 1048576
    return None


def wait_health(base_url, timeout_s, log_tail=None):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/health", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(2)
    return False


def run_tier(ctx, target_tokens, port, health_timeout_s, request_timeout_s):
    """Boot → probe → ask → kill for one tier. Returns the tier record."""
    base_url = f"http://127.0.0.1:{port}"
    log_path = f"/tmp/longctx-smoke-{ctx}.log"
    record = {"ctx_size": ctx, "target_prompt_tokens": target_tokens,
              "ok": False, "error": None}
    server = None
    try:
        env_ctx = {"PORT": str(port), "CTX_SIZE": str(ctx)}
        import os
        env = dict(os.environ, **env_ctx)
        log = open(log_path, "w")
        server = subprocess.Popen(
            ["bash", str(ROOT / "scripts" / "gguf-quickstart.sh")],
            stdout=log, stderr=subprocess.STDOUT, env=env,
            start_new_session=True)
        t0 = time.monotonic()
        if not wait_health(base_url, health_timeout_s):
            record["error"] = (f"health poll timed out after {health_timeout_s}s "
                               f"(boot log: {log_path})")
            return record
        record["boot_wall_s"] = round(time.monotonic() - t0, 1)
        time.sleep(3)
        record["load"] = {"vram_mib": rocm_smi_mib("vram"),
                          "gtt_mib": rocm_smi_mib("gtt")}

        prompt, meta = build_haystack(target_tokens,
                                      lambda t: tokenize_count(base_url, t))
        record["haystack"] = meta
        # Guard the ctx budget: prompt + template + 64 answer tokens must fit.
        if meta["estimated_prompt_tokens"] > ctx - 128:
            shrink = target_tokens * (ctx - 256) // meta["estimated_prompt_tokens"]
            prompt, meta = build_haystack(shrink,
                                          lambda t: tokenize_count(base_url, t))
            record["haystack"] = meta
            record["target_prompt_tokens"] = shrink

        body = bench_client.build_body(
            "default", prompt, max_tokens=64, temperature=0.0, top_p=1.0,
            no_thinking=True)
        t0 = time.monotonic()
        rec, _, _ = bench_client.run_one_stream(base_url, body, request_timeout_s)
        record["request_wall_s"] = round(time.monotonic() - t0, 1)
        content = rec.get("_content") or (rec.get("content") or "")
        record.update({
            "prompt_tokens": rec.get("prompt_tokens"),
            "completion_tokens": rec.get("completion_tokens"),
            "finish_reason": rec.get("finish_reason"),
            "ttft_ms": (round(rec["ttft_ms"], 1)
                        if rec.get("ttft_ms") is not None else None),
            "recall": JUDGE_SUBSTRING in content,
            "answer_excerpt": content.strip()[-160:],
        })
        if rec.get("error"):
            record["error"] = str(rec["error"])
            return record
        record["ok"] = True
        return record
    except Exception as e:  # boot/transport/tokenize failures: failed tier
        record["error"] = f"{type(e).__name__}: {e}"
        return record
    finally:
        if server is not None:
            try:
                server.terminate()
                server.wait(timeout=60)
            except Exception:
                subprocess.run(["pkill", "-KILL", "-P", str(server.pid)],
                               capture_output=True)
                server.kill()
        # GTT drain before the next tier's boot (weights+KV live in GTT).
        for _ in range(100):
            g = None
            try:
                raw = subprocess.run(["rocm-smi", "--showmeminfo", "gtt"],
                                     capture_output=True, text=True).stdout
                for line in raw.splitlines():
                    if "GTT Total Used" in line:
                        g = int(line.split()[-1])
            except Exception:
                pass
            if g is not None and g < 4 * 1024 * 1024 * 1024:
                break
            time.sleep(3)


def result_skeleton(argv=None):
    """Top-level receipt fields, including the verbatim invocation argv so
    every future receipt self-documents its exact tier/timeout flags."""
    return {
        "description": ("S3 long-context retrieval smoke: needle 'The validation "
                        "codename is STRIX-HALO-7741.' at ~80% depth of a synthetic "
                        "filler haystack; prompt asks only for the codename; "
                        "temperature 0, max_tokens 64; judge = exact substring "
                        "'STRIX-HALO-7741' in the answer (METHODOLOGY.md S1/S3)."),
        "needle": NEEDLE_DEFAULT,
        "judge": f"exact substring '{JUDGE_SUBSTRING}' in the completion",
        "path": "gguf (scripts/gguf-quickstart.sh, default unified boot, CTX_SIZE per tier)",
        "instrument_mode": "no-thinking (chat_template_kwargs enable_thinking=false; METHODOLOGY 2 erratum)",
        "argv": list(sys.argv if argv is None else argv),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tiers": [],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Long-context needle-in-haystack smoke (S3) on the GGUF path.")
    ap.add_argument("--out", default=str(
        ROOT / "docs/results/matrix-714/long-context-smoke.json"))
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--tiers", default=",".join(f"{c}:{t}" for c, t in DEFAULT_TIERS),
                    help="comma list of ctx:target_prompt_tokens")
    ap.add_argument("--health-timeout", type=int, default=420)
    ap.add_argument("--request-timeout", type=int, default=1800,
                    help="per-read socket timeout for the needle request "
                         "(240K-token prefill is minutes, not seconds)")
    args = ap.parse_args(argv)

    tiers = []
    for spec in args.tiers.split(","):
        ctx, target = spec.split(":")
        tiers.append((int(ctx), int(target)))

    result = result_skeleton()
    for ctx, target in tiers:
        print(f"== tier ctx={ctx} target~{target} tokens ==", flush=True)
        rec = run_tier(ctx, target, args.port, args.health_timeout,
                       args.request_timeout)
        result["tiers"].append(rec)
        print(json.dumps(rec, indent=2)[:800], flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(f"wrote {out}")
    failed = [t for t in result["tiers"] if not t.get("ok")]
    print(f"tiers ok: {len(result['tiers']) - len(failed)}/{len(result['tiers'])}"
          + (f"; FAILED: {[t['ctx_size'] for t in failed]}" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
