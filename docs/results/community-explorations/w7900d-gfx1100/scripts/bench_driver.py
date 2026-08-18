#!/usr/bin/env python3
"""Zero-dependency (stdlib) bench driver for OpenAI-compatible chat endpoints.

Runs --reps waves of --concurrency non-streaming chat completions and writes
a bench-cell-v1 JSON (see schemas/bench-cell.schema.json). Temperature 0.
Metrics: per-request wall (p50/mean), aggregate decode tok/s per wave
(total completion tokens / wave wall). TTFT requires SSE and is deferred.
"""
import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def one_request(url, payload, timeout):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        wall = time.perf_counter() - t0
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        # Reasoning models (e.g. Qwen3 with <think>) can spend the whole
        # max_tokens budget in reasoning_content while content stays empty;
        # those completions are successful generations, not failures.
        reasoning = msg.get("reasoning_content") or ""
        usage = data.get("usage") or {}
        ok = bool((content + reasoning).strip())
        return {"ok": ok, "wall_s": round(wall, 3),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "error": None if ok else "empty content"}
    except Exception as exc:  # noqa: BLE001 - driver must record, not crash
        return {"ok": False, "wall_s": round(time.perf_counter() - t0, 3),
                "prompt_tokens": None, "completion_tokens": None,
                "error": f"{type(exc).__name__}: {exc}"}


def run_wave(url, conc, payload, timeout):
    with ThreadPoolExecutor(max_workers=conc) as pool:
        return list(pool.map(lambda _: one_request(url, payload, timeout), range(conc)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True)
    ap.add_argument("--concurrency", type=int, required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--identity", required=True, help="JSON file embedded verbatim")
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

    prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    payload = {"model": "qwen3.8-27b",
               "messages": [{"role": "user", "content": prompt}],
               "max_tokens": args.max_tokens, "temperature": 0}
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))

    reps = []
    for r in range(args.reps):
        wave = run_wave(args.url, args.concurrency, payload, args.timeout)
        ok_walls = [w["wall_s"] for w in wave if w["ok"]]
        wave_wall = max(ok_walls) if ok_walls else 0.0
        toks = sum(w["completion_tokens"] or 0 for w in wave)
        reps.append({"rep": r, "ok": sum(1 for w in wave if w["ok"]),
                     "requests": wave, "wave_wall_s": round(wave_wall, 3),
                     "agg_decode_tps": round(toks / wave_wall, 3) if wave_wall else 0.0})

    ok_total = sum(r["ok"] for r in reps)
    failed_total = args.reps * args.concurrency - ok_total
    all_ok_walls = [q["wall_s"] for r in reps for q in r["requests"] if q["ok"]]
    ok_waves = [r for r in reps if r["ok"] == args.concurrency]
    cell = {
        "schema_version": 1,
        "identity": identity,
        "params": {"concurrency": args.concurrency, "reps": args.reps,
                    "max_tokens": args.max_tokens, "temperature": 0,
                    "prompt_file": "configs/bench-prompt.txt"},
        "reps": reps,
        "aggregates": {
            "ok_requests": ok_total, "failed_requests": failed_total,
            "mean_decode_tps": round(statistics.fmean(r["agg_decode_tps"] for r in ok_waves), 3)
                                 if ok_waves else 0.0,
            "p50_request_wall_s": round(statistics.median(all_ok_walls), 3) if all_ok_walls else 0.0,
            "mean_request_wall_s": round(statistics.fmean(all_ok_walls), 3) if all_ok_walls else 0.0,
            "status": "OK" if failed_total == 0 else "FAIL",
        },
    }
    Path(args.out).write_text(json.dumps(cell, indent=2) + "\n", encoding="utf-8")
    print(f"cell -> {args.out} status={cell['aggregates']['status']} "
          f"tps={cell['aggregates']['mean_decode_tps']}")


if __name__ == "__main__":
    main()
