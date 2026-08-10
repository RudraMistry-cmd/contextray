"""Basic API tests for the tokenlens package (runnable without pytest)."""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_THIS_DIR), "src"))

from tokenlens import optimize_context  # noqa: E402

CHUNK_KEYS = {"id", "role", "text", "length", "hash", "action", "duplicate_of"}


def test_optimize_context_basic():
    big = ("hello world " * 200).strip()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": big},
        {"role": "user", "content": big},
        {"role": "assistant", "content": "unique answer"},
        {"role": "assistant", "content": "unique answer"},
    ]

    result = optimize_context(messages)

    assert set(result) == {"optimized_context", "metrics", "top_waste_blocks", "report"}

    optimized = result["optimized_context"]
    assert isinstance(optimized, list) and optimized
    assert all(CHUNK_KEYS <= set(c) for c in optimized)
    assert [c["id"] for c in optimized] == list(range(len(optimized)))

    removed_chunks = [c for c in optimized if c["action"] == "REMOVED"]
    assert len(removed_chunks) > 0, "duplicate chunks should be removed"
    assert all(c["text"].startswith("[duplicate of chunk #") for c in removed_chunks)

    tiny_kept = [c for c in optimized if c["text"] == "unique answer"]
    assert len(tiny_kept) == 2, "tiny duplicates are detected but not replaced"

    assert result["report"] and "Impact:" in result["report"]
    assert len(result["top_waste_blocks"]) <= 5

    metrics = result["metrics"]
    assert metrics["total_chars_in"] == sum(len(m["content"]) for m in messages)
    assert metrics["chars_saved"] == metrics["total_chars_in"] - metrics["total_chars_out"]
    assert metrics["reduction_percentage"] > 0


def test_optimize_context_empty_input():
    result = optimize_context([])
    assert result["optimized_context"] == []
    assert result["metrics"]["total_chars_in"] == 0
    assert result["metrics"]["reduction_percentage"] == 0.0


def test_optimize_context_is_deterministic():
    messages = [
        {"role": "user", "content": "hello world " * 150},
        {"role": "user", "content": "hello world " * 150},
        {"role": "system", "content": "stay on topic"},
    ]
    assert optimize_context(messages) == optimize_context(messages)


def test_optimize_context_accepts_config():
    messages = [{"role": "user", "content": "x" * 2000}]
    plain = optimize_context(messages)
    with_config = optimize_context(messages, config={"future": "knob"})
    assert plain == with_config


def _run():
    failures = 0
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("test_")):
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
    print(f"RESULT: {sum(1 for n in globals() if n.startswith('test_')) - failures} passed, {failures} failed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    _run()