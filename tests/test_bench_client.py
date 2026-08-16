"""Unit tests for scripts/bench_client.py — SYNTHETIC SSE fixtures, no server.

All parsing/metric paths are exercised through ``consume_stream`` with a
deterministic fake clock, so the tests are pure-unit and CI-safe. The client
module is loaded straight from its path (importlib) because scripts/ is not a
package.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLIENT_PATH = ROOT / "scripts" / "bench_client.py"
PROMPT_SET = ROOT / "scripts" / "prompt-sets" / "default.json"


def load_client():
    spec = importlib.util.spec_from_file_location("bench_client_under_test", CLIENT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def client():
    return load_client()


class FakeClock:
    """Deterministic clock: advances ``step`` seconds on every call.

    The consumer takes exactly one timestamp per parsed SSE event (never per
    network chunk), so clean and arbitrarily chunk-split streams of the same
    events produce identical metrics.
    """

    def __init__(self, start=1000.0, step=0.1):
        self.t = start
        self.step = step

    def __call__(self):
        now = self.t
        self.t += self.step
        return now


# ---------------------------------------------------------------- fixtures

def chunk_event(obj):
    return "data: " + json.dumps(obj) + "\n\n"


DONE = "data: [DONE]\n\n"


def delta(content=None, role=None, reasoning=None, finish=None):
    d = {}
    if role is not None:
        d["role"] = role
    if content is not None:
        d["content"] = content
    if reasoning is not None:
        d["reasoning_content"] = reasoning
    ch = {"index": 0, "delta": d}
    if finish is not None:
        ch["finish_reason"] = finish
    return {"id": "chatcmpl-x", "object": "chat.completion.chunk",
            "created": 0, "model": "m", "choices": [ch]}


def usage_event(prompt_tokens, completion_tokens):
    return {"id": "u", "object": "chat.completion.chunk", "choices": [],
            "usage": {"prompt_tokens": prompt_tokens,
                      "completion_tokens": completion_tokens}}


# Clean vLLM/llama.cpp-shaped stream: role-only delta, three content deltas,
# usage chunk, [DONE]. FakeClock timeline: t0=1000.0, role@1000.1,
# content@1000.2/1000.3/1000.4, usage@1000.5.
CLEAN = (
    chunk_event(delta(role="assistant"))
    + chunk_event(delta(content="The "))
    + chunk_event(delta(content="quick "))
    + chunk_event(delta(content="fox"))
    + chunk_event(usage_event(42, 4))
    + DONE
)


# ------------------------------------------------- (1) clean stream metrics

def test_clean_stream_metrics(client):
    m = client.consume_stream([CLEAN], now=FakeClock())
    assert m["prompt_tokens"] == 42
    assert m["completion_tokens"] == 4  # usage is authoritative
    assert m["content"] == "The quick fox"
    assert m["ttft_ms"] == pytest.approx(200.0)  # role-only delta must NOT start the clock
    assert m["tpot_ms"] == pytest.approx(200.0 / 3.0)  # (1000.4-1000.2)s / (4-1)
    assert m["reasoning_tokens"] == 0


# --------------------------------- (2) chunk-split mid-token framing safety

def test_every_two_piece_split_matches_clean(client):
    """The muse-rocm lesson: never assume one event per network chunk. Split
    the byte stream at EVERY position (including mid-`data:`, mid-JSON-string,
    and between the two newlines of the event terminator) — metrics must be
    identical to the clean single-chunk feed."""
    base = client.consume_stream([CLEAN], now=FakeClock())
    for cut in range(1, len(CLEAN)):
        pieces = [CLEAN[:cut], CLEAN[cut:]]
        got = client.consume_stream(pieces, now=FakeClock())
        assert got == base, f"stream split at byte {cut} diverged"


def test_tiny_chunks_matches_clean(client):
    base = client.consume_stream([CLEAN], now=FakeClock())
    tiny = [CLEAN[i:i + 3] for i in range(0, len(CLEAN), 3)]
    assert len(tiny) > 50  # genuinely fragmented
    assert client.consume_stream(tiny, now=FakeClock()) == base


# ----------------------------------------- (3) multi-data-line SSE event

def test_multi_data_line_event_joined(client):
    part1 = ('{"id":"m","object":"chat.completion.chunk",'
             '"choices":[{"index":0,"delta":{"content":"wor')
    part2 = 'ld"}}]}'
    text = f"data: {part1}\ndata: {part2}\n\n" + chunk_event(usage_event(7, 1)) + DONE
    m = client.consume_stream([text], now=FakeClock())
    assert m["content"] == "world"
    assert m["completion_tokens"] == 1
    assert m["prompt_tokens"] == 7


# ------------------------- (4) separate reasoning_content (llama.cpp shape)

def test_reasoning_content_separate_stream(client):
    text = (
        chunk_event(delta(role="assistant"))
        + chunk_event(delta(reasoning="Step one."))
        + chunk_event(delta(reasoning=" Step two."))
        + chunk_event(delta(reasoning=" Verify."))
        + chunk_event(delta(content="42"))
        + chunk_event(delta(content="."))
        + chunk_event(usage_event(99, 5))
        + DONE
    )
    m = client.consume_stream([text], now=FakeClock())
    # t0=1000.0; role@.1; reasoning@.2/.3/.4; content@.5/.6; usage@.7
    assert m["ttft_ms"] == pytest.approx(500.0)  # first CONTENT delta, not the reasoning deltas
    assert m["reasoning_tokens"] == 3  # counted separately
    assert m["completion_tokens"] == 5
    assert m["tpot_ms"] == pytest.approx(100.0 / 4.0)  # (1000.6-1000.5)s / (5-1)
    assert m["content"] == "42."


def test_inline_reasoning_ttft_is_first_delta(client):
    """vLLM no-reasoning-parser shape: reasoning arrives inline in `content`,
    so the first content-bearing delta still starts the TTFT clock."""
    text = (
        chunk_event(delta(role="assistant"))
        + chunk_event(delta(content="<think>compute 6*7"))
        + chunk_event(delta(content="</think>"))
        + chunk_event(delta(content="42"))
        + chunk_event(usage_event(10, 6))
        + DONE
    )
    m = client.consume_stream([text], now=FakeClock())
    assert m["ttft_ms"] == pytest.approx(200.0)
    assert m["reasoning_tokens"] == 0  # no separate field -> nothing split out


# ------------------------------------- (5) [DONE] sentinel + empty deltas

def test_done_sentinel_and_empty_deltas(client):
    text = (
        chunk_event(delta())               # empty delta {}
        + chunk_event(delta(content=""))   # empty-string content: not content-bearing
        + chunk_event(delta(content="OK"))
        + DONE
        # Anything after [DONE] must be ignored.
        + chunk_event(delta(content="IGNORED"))
    )
    chunks = [text[i:i + 5] for i in range(0, len(text), 5)]  # also fragmented
    m = client.consume_stream(chunks, now=FakeClock())
    assert m["saw_done"] is True
    assert m["completion_tokens"] == 1  # no usage -> fallback counts content deltas
    assert m["content"] == "OK"
    assert m["tpot_ms"] is None  # < 2 completion tokens
    assert m["ttft_ms"] == pytest.approx(300.0)  # t0=1000.0; {}@.1; ""@.2; OK@.3


def test_token_fallback_without_usage(client):
    text = (
        chunk_event(delta(content="a"))
        + chunk_event(delta(content="b"))
        + chunk_event(delta(content="c"))
        + DONE
    )
    m = client.consume_stream([text], now=FakeClock())
    assert m["completion_tokens"] == 3
    assert m["tpot_ms"] == pytest.approx(100.0)  # (1000.3-1000.1)s / 2
    assert m["prompt_tokens"] is None


# ------------------------------------------- (6) prompt-set loader + set

def test_prompt_set_loader_validates_shape(client, tmp_path):
    good = {
        "prompts": [{"id": "p1", "text": "hello"}],
        "anchor": {"id": "a", "text": "Reply with exactly: OK",
                   "expect_exact": "OK"},
    }
    gp = tmp_path / "good.json"
    gp.write_text(json.dumps(good))
    loaded = client.load_prompt_set(str(gp))
    assert loaded["anchor"]["expect_exact"] == "OK"

    bad_sets = [
        {"anchor": good["anchor"]},                                        # no prompts
        {"prompts": [], "anchor": good["anchor"]},                         # empty prompts
        {"prompts": "nope", "anchor": good["anchor"]},                     # not a list
        {"prompts": [{"id": "p", "text": 5}], "anchor": good["anchor"]},   # text not str
        {"prompts": [{"id": "p", "text": "x"}, {"id": "p", "text": "y"}],
         "anchor": good["anchor"]},                                        # duplicate ids
        {"prompts": good["prompts"]},                                      # no anchor
        {"prompts": good["prompts"], "anchor": {"id": "a", "text": "t"}},  # no expect_exact
    ]
    for i, bad in enumerate(bad_sets):
        bp = tmp_path / f"bad-{i}.json"
        bp.write_text(json.dumps(bad))
        with pytest.raises(client.PromptSetError):
            client.load_prompt_set(str(bp))


def test_default_prompt_set_shape_and_sizes(client):
    ps = client.load_prompt_set(str(PROMPT_SET))
    prompts = ps["prompts"]
    assert len(prompts) == 8
    ids = [p["id"] for p in prompts]
    assert len(set(ids)) == 8
    for p in prompts:
        # ~1500-2500 tokens approximated by chars/3.5 (slack at the edges).
        approx_tokens = len(p["text"]) / 3.5
        assert 1400 <= approx_tokens <= 2600, f"{p['id']}: {approx_tokens:.0f} tok"
    anchor = ps["anchor"]
    assert anchor["id"]
    assert anchor["text"] == "Reply with exactly: OK"
    assert anchor["expect_exact"] == "OK"
