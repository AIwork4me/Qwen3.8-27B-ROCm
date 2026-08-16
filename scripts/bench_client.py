#!/usr/bin/env python3
"""SSE-framing-safe streaming benchmark client for OpenAI-compatible servers.

Stdlib-only (urllib + threads — no aiohttp/requests) so the matrix cell
runners can invoke it from any venv. Adapted from muse-rocm's battle-tested
scripts/bench_client.py (copy+adapt, not imported); its two hard-won lessons
are load-bearing here:

* SSE events are separated by blank lines and MUST be re-assembled from
  arbitrary network chunks — one chunk may carry several events or half of
  one. Treating each chunk as one event silently drops every coalesced
  event (the muse-rocm np=16 cell that recorded 96 tokens where the server
  generated ~174k).
* ``stream_options.include_usage`` is required, otherwise the token-count
  chunk never arrives and token math degenerates to delta counting.

Metric definitions (binding, see docs/results/METHODOLOGY.md):

* ``ttft_ms`` — request start -> first content-bearing delta. Role-only
  deltas and separate-field reasoning deltas (llama.cpp ``reasoning_content``)
  do NOT start the clock; reasoning is counted separately as
  ``reasoning_tokens``. When reasoning arrives inline in ``content`` (vLLM
  with no reasoning parser), the first content delta still starts the clock.
* ``tpot_ms`` — (last_content_delta - first_content_delta) /
  (completion_tokens - 1), ``None`` when fewer than 2 completion tokens.
* ``completion_tokens`` — from the usage chunk when present (authoritative),
  otherwise ~1 per emitted delta as a fallback.

Usage:
  python3 scripts/bench_client.py --base-url http://127.0.0.1:8080 \
      --concurrency 4 --prompts scripts/prompt-sets/default.json \
      --max-tokens 256 --label gguf-x [--out FILE] [--anchor-only] [--timeout S] \
      [--no-thinking]

Emits one JSON object on stdout (and --out FILE):
  {"label", "concurrency", "started_utc",
   "streams": [{"ttft_ms", "tpot_ms", "completion_tokens", "prompt_tokens",
                "reasoning_tokens", "finish_reason", "ok", "error"}],
   "aggregate": {"tok_per_s", "wall_s", "ok_streams", "failed_streams"}}

Throughput runs sample at temperature 0.7 / top_p 0.95; ``--anchor-only``
forces concurrency 1 and greedy decoding (temperature 0) on the prompt-set
anchor and checks ``expect_exact`` as a substring of the completion,
reporting ``anchor_ok`` per stream.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

CHAT_PATH = "/v1/chat/completions"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 0.95
ANCHOR_TEMPERATURE = 0.0
ANCHOR_TOP_P = 1.0
ANCHOR_MAX_TOKENS_CAP = 16


class PromptSetError(ValueError):
    """Raised when a prompt-set file does not match the declared shape."""


def load_prompt_set(path):
    """Load and validate a prompt set.

    Shape (binding): {"prompts": [{"id": str, "text": str}, ...],
    "anchor": {"id": str, "text": str, "expect_exact": str}}.
    """
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise PromptSetError(f"{path}: invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise PromptSetError(f"{path}: top level must be a JSON object")
    prompts = data.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        raise PromptSetError(f"{path}: 'prompts' must be a non-empty list")
    seen_ids = set()
    for i, p in enumerate(prompts):
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not p["id"]:
            raise PromptSetError(f"{path}: prompts[{i}] needs a non-empty string 'id'")
        if not isinstance(p.get("text"), str) or not p["text"].strip():
            raise PromptSetError(f"{path}: prompts[{i}] needs a non-empty string 'text'")
        if p["id"] in seen_ids:
            raise PromptSetError(f"{path}: duplicate prompt id {p['id']!r}")
        seen_ids.add(p["id"])
    anchor = data.get("anchor")
    if not isinstance(anchor, dict):
        raise PromptSetError(f"{path}: missing 'anchor' object")
    for key in ("id", "text", "expect_exact"):
        if not isinstance(anchor.get(key), str) or not anchor[key]:
            raise PromptSetError(f"{path}: anchor.{key} must be a non-empty string")
    return data


class StreamConsumer:
    """Reassembles SSE events from arbitrary text chunks and records timings.

    Chunking-independent by construction: a timestamp is taken exactly once
    per parsed data event (never per fed chunk), so metrics are identical no
    matter how the byte stream was split across reads.
    """

    def __init__(self, now=time.perf_counter):
        self._now = now
        self._buf = ""
        self.done = False
        self.first_content_s = None
        self.last_content_s = None
        self.content_deltas = 0
        self.reasoning_deltas = 0
        self.usage_completion_tokens = None
        self.usage_prompt_tokens = None
        self.usage_reasoning_tokens = None
        self.finish_reason = None
        self.content = ""
        self.reasoning_text = ""

    # -- SSE framing ------------------------------------------------------
    def feed(self, text):
        """Feed one arbitrary chunk; True once the [DONE] sentinel was seen."""
        # Normalize line endings; a CRLF split across chunks still yields a
        # blank line (the extra empty event is skipped harmlessly below).
        self._buf += text.replace("\r\n", "\n").replace("\r", "\n")
        while "\n\n" in self._buf:
            event, self._buf = self._buf.split("\n\n", 1)
            if self._handle_event(event):
                return True
        return self.done

    def finish(self):
        """Flush a trailing unterminated event at EOF (pre-buffering parity)."""
        if self._buf.strip():
            self._handle_event(self._buf)
        self._buf = ""

    def _handle_event(self, event_text):
        data_lines = []
        for line in event_text.split("\n"):
            if line.startswith(":"):
                continue  # SSE comment / keep-alive
            if line.startswith("data:"):
                data_lines.append(line[len("data:"):].lstrip(" "))
            # other SSE fields (event:, id:, retry:) carry no payload here
        if not data_lines:
            return False
        if len(data_lines) == 1 and data_lines[0].strip() == "[DONE]":
            self.done = True
            return True
        obj = self._parse_payload(data_lines)
        if obj is None:
            return False  # partial/garbage JSON: skip, never assume
        self._record(obj, self._now())
        return False

    @staticmethod
    def _parse_payload(data_lines):
        """One event may carry several data: lines. Servers that split a JSON
        payload across lines need no-separator join; spec-style multi-line
        data joins with newline; failing both, try each line alone. Never
        raise on bad JSON."""
        candidates = ["".join(data_lines), "\n".join(data_lines)]
        candidates.extend(data_lines)
        for cand in candidates:
            try:
                obj = json.loads(cand)
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
        return None

    def _record(self, obj, ts):
        usage = obj.get("usage")
        if isinstance(usage, dict):
            if isinstance(usage.get("prompt_tokens"), int):
                self.usage_prompt_tokens = usage["prompt_tokens"]
            if isinstance(usage.get("completion_tokens"), int):
                self.usage_completion_tokens = usage["completion_tokens"]
            details = usage.get("completion_tokens_details")
            if (isinstance(details, dict)
                    and isinstance(details.get("reasoning_tokens"), int)):
                self.usage_reasoning_tokens = details["reasoning_tokens"]
        for choice in obj.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            if choice.get("finish_reason"):
                self.finish_reason = choice["finish_reason"]
            delta = choice.get("delta") or {}
            reasoning = delta.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                # Separate reasoning field (llama.cpp shape): does not start
                # the TTFT clock, counted on its own.
                self.reasoning_deltas += 1
                self.reasoning_text += reasoning
            content = delta.get("content")
            if isinstance(content, str) and content:
                if self.first_content_s is None:
                    self.first_content_s = ts
                self.last_content_s = ts
                self.content_deltas += 1
                self.content += content

    def metrics(self, t0_s):
        completion_tokens = self.usage_completion_tokens
        if completion_tokens is None:
            # No usage chunk: fall back to ~1 token per emitted delta.
            completion_tokens = self.content_deltas + self.reasoning_deltas
        reasoning_tokens = (self.usage_reasoning_tokens
                            if self.usage_reasoning_tokens is not None
                            else self.reasoning_deltas)
        ttft_ms = (None if self.first_content_s is None
                   else (self.first_content_s - t0_s) * 1000.0)
        tpot_ms = None
        if self.first_content_s is not None and completion_tokens >= 2:
            tpot_ms = ((self.last_content_s - self.first_content_s) * 1000.0
                       / (completion_tokens - 1))
        return {
            "ttft_ms": ttft_ms,
            "tpot_ms": tpot_ms,
            "completion_tokens": completion_tokens,
            "prompt_tokens": self.usage_prompt_tokens,
            "reasoning_tokens": reasoning_tokens,
            "finish_reason": self.finish_reason,
            "saw_done": self.done,
            "content": self.content,
        }


def consume_stream(chunks, now=time.perf_counter):
    """Parse an iterable of SSE text chunks into a metrics dict (pure, no I/O).

    ``now`` is called once before feeding (t0) and once per parsed data event,
    which makes timings injectable and chunking-independent for tests.
    """
    t0 = now()
    consumer = StreamConsumer(now=now)
    for chunk in chunks:
        if consumer.feed(chunk):
            break  # [DONE] seen: anything after the sentinel is ignored
    consumer.finish()
    return consumer.metrics(t0)


# --------------------------------------------------------------- network

def build_body(model, prompt_text, max_tokens, temperature, top_p,
               no_thinking=False):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": True,
        # Without include_usage, OpenAI-compatible servers omit the token
        # count chunk while streaming (muse-rocm lesson: metrics must be real).
        "stream_options": {"include_usage": True},
    }
    if no_thinking:
        # Per-request template switch (Qwen3 family). Task 3 live-cell erratum
        # (2026-08-17): with thinking on, the model spent the entire 256-token
        # budget in reasoning_content (finish_reason=length, zero visible
        # content), leaving the frozen TTFT/TPOT definitions undefined and the
        # anchor unable to answer within its cap. Disabling thinking per
        # request keeps the metric definitions binding and works on both
        # serving paths (llama.cpp --jinja and vLLM honor chat_template_kwargs).
        body["chat_template_kwargs"] = {"enable_thinking": False}
    return body


def run_one_stream(base_url, body, timeout):
    """POST one streaming chat completion. Returns (record, t0_s, t1_s).

    The record mirrors the consumer metrics plus ok/error; partial metrics
    are preserved when the stream dies mid-flight.
    """
    url = base_url.rstrip("/") + CHAT_PATH
    t0 = time.perf_counter()
    consumer = StreamConsumer()
    error = None
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Accept": "text/event-stream"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Iterating the response yields lines as they arrive; the
            # consumer re-buffers on blank lines, so read boundaries and
            # event boundaries stay decoupled.
            for raw_line in resp:
                if consumer.feed(raw_line.decode("utf-8", errors="ignore")):
                    break
        consumer.finish()
    except urllib.error.HTTPError as e:
        try:
            detail = e.read(200).decode("utf-8", errors="ignore").strip()
        except Exception:
            detail = ""
        error = f"HTTP {e.code}: {detail or e.reason}"
    except Exception as e:  # URLError, socket.timeout, ...
        error = f"{type(e).__name__}: {e}"
    t1 = time.perf_counter()
    m = consumer.metrics(t0)
    record = {
        "ttft_ms": m["ttft_ms"],
        "tpot_ms": m["tpot_ms"],
        "completion_tokens": m["completion_tokens"],
        "prompt_tokens": m["prompt_tokens"],
        "reasoning_tokens": m["reasoning_tokens"],
        "finish_reason": m["finish_reason"],
        "ok": error is None,
        "error": error,
        "_content": m["content"],
    }
    return record, t0, t1


def run_bench(args):
    """Fire the stream matrix per CLI args; returns the result JSON dict."""
    prompt_set = load_prompt_set(args.prompts)
    if args.anchor_only:
        prompts = [prompt_set["anchor"]]
        concurrency = 1
        temperature, top_p = ANCHOR_TEMPERATURE, ANCHOR_TOP_P
        max_tokens = min(args.max_tokens, ANCHOR_MAX_TOKENS_CAP)
        expect = prompt_set["anchor"]["expect_exact"]
    else:
        prompts = prompt_set["prompts"]
        concurrency = args.concurrency
        temperature, top_p = DEFAULT_TEMPERATURE, DEFAULT_TOP_P
        max_tokens = args.max_tokens
        expect = None

    records = [None] * concurrency
    spans = [[0.0, 0.0] for _ in range(concurrency)]

    def worker(i):
        body = build_body(args.model, prompts[i % len(prompts)]["text"],
                          max_tokens, temperature, top_p,
                          no_thinking=args.no_thinking)
        rec, t0, t1 = run_one_stream(args.base_url, body, args.timeout)
        content = rec.pop("_content", "")
        if expect is not None:
            rec["anchor_ok"] = bool(rec["ok"]) and expect in content
            rec["content"] = content.strip()
            if rec["ok"] and not rec["anchor_ok"]:
                rec["error"] = (f"anchor mismatch: expected {expect!r} "
                                f"as substring of completion")
        records[i] = rec
        spans[i][0], spans[i][1] = t0, t1

    started_utc = datetime.now(timezone.utc).isoformat()
    threads = [threading.Thread(target=worker, args=(i,), daemon=True)
               for i in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    starts = [s[0] for s in spans if s[0] or s[1]]
    ends = [s[1] for s in spans if s[0] or s[1]]
    wall_s = (max(ends) - min(starts)) if starts and ends else 0.0
    ok_streams = sum(1 for r in records if r and r["ok"])
    total_completion = sum((r["completion_tokens"] or 0)
                           for r in records if r and r["ok"])
    return {
        "label": args.label,
        "concurrency": concurrency,
        "started_utc": started_utc,
        "streams": records,
        "aggregate": {
            "tok_per_s": (total_completion / wall_s) if wall_s > 0 else 0.0,
            "wall_s": wall_s,
            "ok_streams": ok_streams,
            "failed_streams": concurrency - ok_streams,
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="SSE-framing-safe streaming benchmark client "
                    "(OpenAI-compatible /v1/chat/completions).")
    ap.add_argument("--base-url", required=True,
                    help="e.g. http://127.0.0.1:8080")
    ap.add_argument("--concurrency", type=int, default=1,
                    help="number of concurrent streams (ignored with --anchor-only)")
    ap.add_argument("--prompts", required=True,
                    help="prompt-set JSON (scripts/prompt-sets/default.json)")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--label", default="", help="run label echoed into the output JSON")
    ap.add_argument("--out", default=None, help="also write the result JSON to FILE")
    ap.add_argument("--anchor-only", action="store_true",
                    help="single greedy (temperature 0) run of the anchor prompt; "
                         "checks expect_exact as substring and reports anchor_ok")
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="per-read socket timeout in seconds")
    ap.add_argument("--model", default="default",
                    help="model name for the chat API (llama-server accepts any alias; "
                         "pass the served name for vLLM)")
    ap.add_argument("--no-thinking", action="store_true",
                    help="send chat_template_kwargs {enable_thinking: false} so the "
                         "model emits visible content deltas within the generation "
                         "budget (matrix cells measure the visible-answer stream)")
    args = ap.parse_args(argv)
    if args.concurrency < 1:
        ap.error("--concurrency must be >= 1")
    if args.max_tokens < 1:
        ap.error("--max-tokens must be >= 1")

    result = run_bench(args)
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if result["aggregate"]["failed_streams"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
