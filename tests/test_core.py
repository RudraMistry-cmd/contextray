"""Basic API tests for the contextray package (runnable without pytest)."""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_THIS_DIR), "src"))

from contextray import InvalidMessageError, optimize_context, optimize_text  # noqa: E402

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


def _expect_invalid(messages, needle):
    try:
        optimize_context(messages)
    except InvalidMessageError as exc:
        assert needle in str(exc), f"{needle!r} not in {exc!r}"
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"expected InvalidMessageError, got {type(exc).__name__}: {exc}")
    else:
        raise AssertionError("expected InvalidMessageError, nothing raised")


def test_invalid_message_content_none():
    messages = [{"role": "user", "content": "ok"},
                {"role": "user", "content": "ok"},
                {"role": "user", "content": "ok"},
                {"role": "assistant", "content": None}]
    _expect_invalid(messages, "message[3]")
    _expect_invalid(messages, "'content' is None")
    _expect_invalid(messages, "tool-call-only turns are not supported")


def test_invalid_message_content_list():
    messages = [{"role": "assistant", "content": [{"type": "text", "text": "hi"}]}]
    _expect_invalid(messages, "message[0]")
    _expect_invalid(messages, "'content' is a list")
    _expect_invalid(messages, "typed content blocks are not supported")


def test_invalid_message_missing_role():
    _expect_invalid([{"content": "no role here"}], "message[0]")
    _expect_invalid([{"content": "no role here"}], "missing required key 'role'")


def test_invalid_message_missing_content():
    messages = [{"role": "user", "content": "a"},
                {"role": "assistant"}]
    _expect_invalid(messages, "message[1]")
    _expect_invalid(messages, "missing required key 'content'")


def test_invalid_message_not_a_dict():
    messages = [{"role": "user", "content": "a"}, "not a dict"]
    _expect_invalid(messages, "message[1]")
    _expect_invalid(messages, "expected a dict")


def test_invalid_message_non_str_role():
    _expect_invalid([{"role": ["user"], "content": "x"}], "message[0]")
    _expect_invalid([{"role": ["user"], "content": "x"}], "'role'")


def test_invalid_message_is_value_error():
    assert issubclass(InvalidMessageError, ValueError)


def test_token_estimator_default_unchanged():
    messages = [{"role": "user", "content": "hello world " * 150},
                {"role": "user", "content": "hello world " * 150}]
    result = optimize_context(messages)
    m = result["metrics"]
    assert m["est_tokens_in"] == m["total_chars_in"] / 4
    assert m["est_tokens_saved"] == m["chars_saved"] / 4
    assert "English heuristic" in result["report"]


def test_token_estimator_custom_value_in_metrics():
    messages = [{"role": "user", "content": "hello world " * 150},
                {"role": "user", "content": "hello world " * 150}]
    result = optimize_context(messages, token_estimator=lambda t: 123.5)
    assert result["metrics"]["est_tokens_in"] == 123.5
    assert result["metrics"]["est_tokens_saved"] == 123.5 - 123.5 == 0.0
    assert "custom token_estimator" in result["report"]


def test_token_estimator_receives_full_texts():
    calls = []
    messages = [{"role": "user", "content": "aaa " * 300},
                {"role": "user", "content": "aaa " * 300}]

    def estimator(text):
        calls.append(text)
        return len(text)  # trivial "tokenizer" for the assertions

    result = optimize_context(messages, token_estimator=estimator)
    joined = "".join(calls)
    assert calls[0] == "aaa " * 600, "original text must be the full reassembled input"
    assert calls[1] != calls[0], "optimized text differs (duplicate removed)"
    assert result["metrics"]["est_tokens_in"] == len(calls[0])
    assert result["metrics"]["est_tokens_saved"] == len(calls[0]) - len(calls[1])


def test_token_estimator_error_is_wrapped_with_context():
    def raiser(text):
        raise ValueError("tokenizer library exploded")

    try:
        optimize_context([{"role": "user", "content": "x"}], token_estimator=raiser)
    except RuntimeError as exc:
        assert "token_estimator raised on original text" in str(exc)
        assert "tokenizer library exploded" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_token_estimator_error_names_optimized_text():
    calls = []

    def raiser(text):
        calls.append(text)
        if len(calls) == 2:
            raise ValueError("bad tokens")
        return 4.0

    messages = [{"role": "user", "content": "a" * 300},
                {"role": "user", "content": "a" * 300}]
    try:
        optimize_context(messages, token_estimator=raiser)
    except RuntimeError as exc:
        assert "token_estimator raised on optimized text" in str(exc)
        assert "bad tokens" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_optimize_text_token_estimator():
    para = ("dedup me please " * 40).strip()
    text = "some prose " * 40 + "\n\n" + para + "\n\n" + para
    result = optimize_text(text, token_estimator=lambda t: 7.0)
    assert result["metrics"]["est_tokens_in"] == 7.0
    assert result["metrics"]["est_tokens_saved"] == 0.0  # constant estimator
    assert "token_estimator" in result["report"]

    plain = optimize_text(text)
    assert plain["metrics"]["est_tokens_in"] == plain["metrics"]["total_chars_in"] / 4
    assert "English heuristic" in plain["report"]


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