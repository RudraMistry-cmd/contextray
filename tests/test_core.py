"""Basic API tests for the contextray package (runnable without pytest)."""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_THIS_DIR), "src"))

from contextray import optimize_context  # noqa: E402

MESSAGE_KEYS = {"role", "content"}


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
    assert all(set(m) == MESSAGE_KEYS for m in optimized), "output must be plain messages"
    assert all(isinstance(m["role"], str) and isinstance(m["content"], str) for m in optimized)

    markers = [m["content"] for m in optimized if m["content"].startswith("[duplicate of chunk #")]
    assert markers, "duplicate chunks should be replaced with markers"
    assert sum(m["content"] == "unique answer" for m in optimized) == 2, \
        "tiny duplicates are detected but not replaced"

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


def test_optimize_context_accepts_plain_text():
    para = ("repeat me please " * 50).strip()  # two identical paragraphs
    text = para + "\n\n" + para

    result = optimize_context(text)
    assert set(result) == {"optimized_context", "metrics", "top_waste_blocks", "report"}

    optimized = result["optimized_context"]
    assert isinstance(optimized, list) and len(optimized) == 2, \
        "kept paragraph plus marker chunk"
    assert all(set(m) == MESSAGE_KEYS for m in optimized)
    assert optimized[0]["role"] == "text" and optimized[0]["content"] == para + "\n\n", \
        "the kept paragraph keeps its \n\n delimiter attached"
    assert optimized[1]["content"].startswith("[duplicate of chunk #"), \
        "the repeated paragraph should be replaced with a marker"
    assert result["metrics"]["chars_saved"] > 0


def test_optimize_context_accepts_config():
    messages = [{"role": "user", "content": "x" * 2000}]
    plain = optimize_context(messages)
    with_config = optimize_context(messages, config={"future": "knob"})
    assert plain == with_config


def _run():
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
    print(f"RESULT: {len(tests) - failures} passed, {failures} failed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    _run()