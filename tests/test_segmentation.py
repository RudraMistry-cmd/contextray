"""Tests for the Structural Segmentation Layer (runnable without pytest)."""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_THIS_DIR), "src"))

from contextray import optimize_context, optimize_text, segment_text  # noqa: E402

FENCE_PY = "```python\ndef f(x):\n    return x + 1\n```"
FENCE_RAW = "```\nplain fenced content\n```"
FENCE_BIG = "```python\n# " + "y" * 120 + "\ndef f(x):\n    return x + 1\n```"


def test_segments_are_contiguous_and_byte_exact():
    text = ("intro paragraph\n\n"
            + FENCE_PY + "\n\n"
            + '{\n  "name": "n",\n  "items": [1, 2]\n}\n\n'
            + "tail paragraph")
    segments = segment_text(text)

    cursor = 0
    for seg in segments:
        assert seg.start == cursor, "no gaps or overlaps"
        assert seg.content == text[seg.start:seg.end], "content must be byte-exact"
        assert seg.length == len(seg.content)
        cursor = seg.end
    assert cursor == len(text), "segments must cover the whole input"


def test_fence_with_language_is_code():
    segments = segment_text("before\n" + FENCE_PY + "\nafter")
    fenced = [s for s in segments if s.type in ("code", "block")]
    assert len(fenced) == 1
    assert fenced[0].type == "code"
    assert fenced[0].mode == "STRICT"
    assert fenced[0].content == FENCE_PY


def test_fence_without_language_is_block():
    segments = segment_text("x\n" + FENCE_RAW + "\ny")
    fenced = [s for s in segments if s.type in ("code", "block")]
    assert len(fenced) == 1
    assert fenced[0].type == "block"
    assert fenced[0].mode == "STRICT"


def test_whole_line_json_is_strict_but_inline_json_is_text():
    text = ('here is a mapping: {"a": 1} and more prose\n'
            '{\n  "users": [1, 2, 3]\n}\n'
            'still prose')
    segments = segment_text(text)

    jsons = [s for s in segments if s.type == "json"]
    assert len(jsons) == 1, "only the standalone block must be detected"
    assert jsons[0].mode == "STRICT"
    assert jsons[0].content == '{\n  "users": [1, 2, 3]\n}'

    texts = [s for s in segments if s.type == "text"]
    assert any('{"a": 1}' in s.content for s in texts), "inline JSON stays flexible text"


def test_optimize_text_preserves_strict_bytes():
    para = ("dedup me please " * 60).strip()
    text = ("header\n\n" + FENCE_PY + "\n\n" + '{"ok": [1, 2]}\n\n' + para + "\n\n" + para)
    result = optimize_text(text)

    joined = "\n".join(m["content"] for m in result["optimized_context"])
    assert FENCE_PY in joined, "fenced code must survive byte-for-byte"
    assert '{"ok": [1, 2]}' in joined, "json must survive byte-for-byte"
    assert joined.count(para) == 1, "flexible duplicate must be collapsed"
    assert joined.count("[duplicate of chunk #") == 1


def test_metrics_are_exact_with_masking():
    text = ("a\n" + FENCE_PY + "\nb\n" + '{"x": 1}\n' + ("repeat " * 300))
    result = optimize_text(text)
    assert result["metrics"]["total_chars_in"] == len(text), \
        "length-preserving masks keep metrics exact"
    out_chars = sum(len(m["content"]) for m in result["optimized_context"])
    assert result["metrics"]["total_chars_out"] == out_chars


def test_marker_never_lands_inside_strict():
    long_line = "word " * 80 + " " + FENCE_PY + " " + "tail " * 80
    text = long_line + "\n\n" + "word " * 80 + " " + FENCE_PY + " " + "tail " * 80
    result = optimize_text(text)
    for m in result["optimized_context"]:
        assert "__SEG_" not in m["content"], "no placeholder may leak"
    joined = "\n".join(m["content"] for m in result["optimized_context"])
    assert joined.count(FENCE_PY) == 1, "reference copy restored byte-exact"


def test_optimize_text_is_deterministic():
    text = ("h\n" + FENCE_RAW + "\n" + '{"a": [1, 2]}\n' + ("same " * 200) + "\n" + ("same " * 200))
    assert optimize_text(text) == optimize_text(text)


def test_empty_and_text_only_inputs():
    assert optimize_text("")["metrics"]["total_chars_in"] == 0
    segments = segment_text("")
    assert segments == []

    text = "plain prose with no structure at all"
    result = optimize_text(text)
    assert [m["content"] for m in result["optimized_context"]] == ["plain prose with no structure at all"]


def test_duplicate_strict_segments_keep_reference_copy():
    filler = ("unique filler prose. " * 60).strip()  # pushes the text over MAX_CHUNK_SIZE
    text = FENCE_BIG + "\n\n" + filler + "\n\n" + FENCE_BIG
    result = optimize_text(text)
    joined = "\n".join(m["content"] for m in result["optimized_context"])
    assert joined.count(FENCE_BIG) == 1, "first occurrence stays, later copies elided"
    assert "[duplicate of chunk #" in joined


def test_fence_takes_precedence_over_json():
    text = '{"prompt": "```\nnot really json\n```"}'
    segments = segment_text(text)
    assert any(s.type in ("code", "block") for s in segments), "fence wins over json"
    assert not any(s.type == "json" for s in segments)


BARE_PY = (
    "import sys\n"
    "import time\n"
    "\n"
    "_THIS_DIR = os.path.dirname(os.path.abspath(__file__))\n"
    "sys.path.insert(0, _THIS_DIR)"
)


def test_bare_python_block_is_strict():
    text = "some prose first\n\n" + BARE_PY + "\n\nand prose after"
    segments = segment_text(text)

    codes = [s for s in segments if s.type == "code"]
    assert len(codes) == 1, "unfenced python must be detected"
    assert codes[0].mode == "STRICT"
    assert codes[0].content == BARE_PY, "must be byte-exact"

    assert any("some prose first" in s.content for s in segments), "prose stays text"


def test_bare_python_survives_optimization_byte_exact():
    para = ("dedup me please " * 60).strip()
    text = BARE_PY + "\n\n" + para + "\n\n" + para
    result = optimize_text(text)

    joined = "\n".join(m["content"] for m in result["optimized_context"])
    assert BARE_PY in joined, "bare code must survive byte-for-byte"
    assert joined.count(para) == 1, "flexible duplicate still collapses"
    assert "__SEG_" not in joined, "no placeholder leaks"


def test_short_python_lines_are_not_code():
    text = "x = 5\n\ny = 6"
    segments = segment_text(text)
    assert not any(s.type == "code" for s in segments), \
        "single-expression 'code' is prose until proven a block"


def test_json_wins_over_python():
    text = '{"a": 1}\n\n{"b": 2}'
    segments = segment_text(text)
    jsons = [s for s in segments if s.type == "json"]
    assert len(jsons) == 2
    assert not any(s.type == "code" for s in segments), "json spans beat python parsing"


def test_bare_python_is_deterministic():
    assert segment_text("x\n" + BARE_PY + "\ny") == segment_text("x\n" + BARE_PY + "\ny")


_PY_PAD_LINE = "plain prose filler line with a few words\n"
PY_BLOCK = "import os\nimport sys\n\nx = 1\n"


def test_python_scan_skipped_above_default_line_threshold():
    big = _PY_PAD_LINE * 20005 + PY_BLOCK  # 20009 lines > 20000 default
    segments = segment_text(big)
    assert not any(s.type == "code" for s in segments), \
        "unfenced python scan must be skipped above the default threshold"
    assert any(s.type == "text" for s in segments), "rest of the input still segments"


def test_fences_and_json_still_detected_above_threshold():
    big = _PY_PAD_LINE * 20005
    assert any(s.type == "code" for s in segment_text(big + "```python\nx = 1\n```")), \
        "fenced code must survive the python-scan guard"
    assert any(s.type == "json" for s in segment_text(big + '{"k": 1}')), \
        "whole-line JSON must survive the python-scan guard"


def test_python_scan_threshold_is_configurable():
    text = _PY_PAD_LINE * 12 + PY_BLOCK  # 16 lines total
    assert any(s.type == "code" for s in segment_text(text)), "default scans small inputs"
    assert any(s.type == "code" for s in segment_text(text, max_lines_for_python_scan=30))
    assert not any(s.type == "code" for s in segment_text(text, max_lines_for_python_scan=15)), \
        "tighter threshold must skip the scan"
    assert any(s.type == "code" for s in segment_text(text, max_lines_for_python_scan=None)), \
        "None disables the guard entirely"


def test_optimize_text_falls_back_when_segmentation_raises():
    import contextray.core as core
    original = core.segment_text

    def exploding_segmenter(text):
        raise RuntimeError("segmentation exploded on purpose")

    core.segment_text = exploding_segmenter
    try:
        text = ("ordinary prose " * 80) + "\n\n" + ("repeated line " * 40)
        result = optimize_text(text)
    finally:
        core.segment_text = original

    assert result["metrics"]["segmentation_fallback"] is True
    joined = "\n".join(m["content"] for m in result["optimized_context"])
    assert "ordinary prose" in joined, "fallback output must still carry the input text"
    assert result["report"].startswith("Segmentation failed"), \
        "fallback note must be prepended to the report"
    assert "segments" not in result, "no segmentation breakdown on the fallback path"


def test_optimize_text_marks_segmentation_success():
    result = optimize_text("some prose " + FENCE_PY)
    assert result["metrics"]["segmentation_fallback"] is False


def test_optimize_text_segments_breakdown():
    json_blob = '{"k": [1, 2]}'
    para = ("plain paragraph prose " * 40).strip()
    text = FENCE_PY + "\n\n" + json_blob + "\n\n" + FENCE_RAW + "\n\n" + para
    result = optimize_text(text)
    assert result["segments"] == {
        "code": {"count": 1, "mode": "protected"},
        "json": {"count": 1, "mode": "protected"},
        "block": {"count": 1, "mode": "protected"},
        "text": {"count": 3, "mode": "processed"},
    }
    assert "Segments:" in result["report"]
    assert "  code: 1 (protected)" in result["report"]
    assert "  json: 1 (protected)" in result["report"]
    assert "  block: 1 (protected)" in result["report"]
    assert "  text: 3 (processed)" in result["report"]
    assert result["report"].index("Segments:") < result["report"].index("Impact:"), \
        "Segments section must precede the Impact line"


def test_optimize_context_has_no_segments_key():
    result = optimize_context([{"role": "user", "content": "hello world"}])
    assert "segments" not in result
    assert "Segments:" not in result["report"]


def main():
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as exc:
                failures.append(f"{name}: {exc}")
    if failures:
        print("\n".join(f"FAIL  {f}" for f in failures))
        print(f"RESULT: {len(failures)} failed")
        raise SystemExit(1)
    print("RESULT: all segmentation tests passed")


if __name__ == "__main__":
    main()
