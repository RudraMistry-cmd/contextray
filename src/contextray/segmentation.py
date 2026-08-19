"""Structural Segmentation Layer (v0.2).

Deterministic, high-confidence pre-processing that runs BEFORE the existing
chunk / hash / dedup pipeline. Raw text is split into ordered, contiguous
segments; provably-structural regions are marked STRICT and masked with
placeholders so the pipeline can never split or modify them internally.

Rules are purely structural - no NLP, no guessing:

- ``code``  : ```-fenced block with a language tag on the opening fence
- ``block`` : ```-fenced block with no language tag
- ``json``  : one or more whole lines that form a single parseable JSON value
              (verified with ``json.loads`` - the value is real JSON, not
              guessed). Fences take precedence: a span that touches a fence is
              not promoted to ``json``.
- ``code`` (unfenced) : at least 3 whole lines that parse as valid Python
              (verified with ``ast.parse``). This covers code pasted without
              fences. Fences and JSON take precedence over it. To keep
              worst-case costs bounded, the unfenced Python scan is skipped
              entirely for inputs above ``max_lines_for_python_scan`` lines
              (default 20,000) - fence and JSON detection are cheaper and
              still run.
- ``text``  : everything else (FLEXIBLE)

STRICT segments are byte-for-byte identical after optimization. Masking
replaces a STRICT segment with a placeholder padded to the exact original
length, so the pipeline's chunking behavior and metrics are unchanged.
"""

import ast
import json
import re

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_PAD_CHAR = "\ufeff"  # not whitespace: cannot be cut by chunk splitting, folds in strip()
_PY_MIN_LINES = 3     # fewer lines can be valid Python by accident ("x = 5") - not a code block
_PY_HEAL_LINES = 24   # keep growing through at most this many failing lines (parens/docstrings)


class Segment:
    """One ordered slice of the input text."""

    def __init__(self, id, type, mode, content, start, end):
        self.id = id                # int
        self.type = type            # "code" | "json" | "block" | "text"
        self.mode = mode            # "STRICT" | "FLEXIBLE"
        self.content = content      # exact string (original bytes)
        self.start = start          # original start index
        self.end = end              # original end index

    @property
    def length(self):
        return self.end - self.start

    def __eq__(self, other):
        if not isinstance(other, Segment):
            return NotImplemented
        return (self.id, self.type, self.mode, self.content,
                self.start, self.end) == (other.id, other.type, other.mode,
                                          other.content, other.start, other.end)

    def __repr__(self):
        return (f"Segment(id={self.id}, type={self.type!r}, mode={self.mode!r}, "
                f"start={self.start}, end={self.end}, length={self.length})")


def _fenced_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, type) for every matched fence, in order."""
    spans = []
    for m in _FENCE_RE.finditer(text):
        inner = m.group(0)[3:-3]
        first_line = inner.split("\n", 1)[0]
        seg_type = "code" if first_line.strip() else "block"
        spans.append((m.start(), m.end(), seg_type))
    return spans


def _json_spans(text: str, fenced_spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Whole-line JSON values that do not touch any fence: (start, end, 'json')."""
    masked_chars = list(text)
    for fos, foe, _ in fenced_spans:
        for i in range(fos, foe):
            masked_chars[i] = " "
    working = "".join(masked_chars)

    line_offsets = []
    acc = 0
    for line in working.split("\n"):
        line_offsets.append(acc)
        acc += len(line) + 1

    spans = []
    i = 0
    lines = working.split("\n")
    n = len(lines)
    while i < n:
        stripped = lines[i].lstrip()
        if not stripped.startswith(("{", "[")):
            i += 1
            continue
        start_index = line_offsets[i] + (len(lines[i]) - len(stripped))
        joined = lines[i]
        found_at = -1
        for j in range(i, n):
            if j > i:
                joined += "\n" + lines[j]
            try:
                parsed = json.loads(joined)
            except (json.JSONDecodeError, ValueError, RecursionError):
                continue
            if isinstance(parsed, (dict, list)):
                found_at = j
                break
        if found_at == -1:
            i += 1
            continue
        # A fence inside the value wins: drop the json span entirely.
        end_index = start_index + len(joined)
        touches_fence = any(fos < end_index and foe > start_index
                            for fos, foe, _ in fenced_spans)
        if not touches_fence:
            spans.append((start_index, end_index, "json"))
        i = found_at + 1
    return spans


def _python_spans(text: str, protected_spans: list[tuple[int, int, str]],
                  max_lines: int | None) -> list[tuple[int, int, str]]:
    """Whole-line regions that verifiably parse as valid Python: (start, end, 'code').

    Verification only - a region is protected only if ``ast.parse`` accepts it.
    Growth heals through a few failing lines (multi-line parens, docstrings),
    and a span extends to the LAST line where the whole region still parses,
    so one code block never splits into adjacent spans. Regions touching a
    fence or a JSON value are dropped (they win).

    The scan restarts from every candidate line, which is superlinear on
    fence-free prose; ``max_lines`` (None = unlimited) caps it - inputs with
    more lines are returned unchanged, relying on fence/JSON detection.
    """
    if max_lines is not None and text.count("\n") + 1 > max_lines:
        return []
    lines = text.split("\n")
    line_offsets = []
    acc = 0
    for line in lines:
        line_offsets.append(acc)
        acc += len(line) + 1

    spans = []
    i = 0
    n = len(lines)
    while i < n:
        if not lines[i].strip():
            i += 1
            continue
        start_index = line_offsets[i]
        region = lines[i]
        last_success = -1
        non_blank = 1
        failures = 0
        j = i
        while j < n:
            if j > i:
                region += "\n" + lines[j]
                if lines[j].strip():
                    non_blank += 1
            try:
                ast.parse(region)
            except (SyntaxError, ValueError, RecursionError):
                failures += 1
                if failures >= _PY_HEAL_LINES:
                    break
                j += 1
                continue
            failures = 0
            if non_blank >= _PY_MIN_LINES:
                last_success = j
            j += 1
        if last_success == -1:
            i += 1
            continue
        while lines[last_success] == "" and last_success > i:
            last_success -= 1  # trim trailing blank lines from the span
        end_index = line_offsets[last_success] + len(lines[last_success])
        touches = any(s < end_index and e > start_index for s, e, _ in protected_spans)
        if not touches:
            spans.append((start_index, end_index, "code"))
        i = last_success + 1
    return spans


def segment_text(text: str, *, max_lines_for_python_scan: int | None = 20000) -> list[Segment]:
    """Split ``text`` into ordered, contiguous, byte-exact segments.

    Guarantees: segments cover the whole input without gaps or overlaps;
    ``Segment.content`` is byte-identical to ``text[start:end]``.

    ``max_lines_for_python_scan`` bounds the unfenced-Python detection cost:
    inputs with more lines are scanned for fences and JSON only. Pass None
    to scan at any size.
    """
    if not isinstance(text, str):
        raise TypeError(f"segment_text() expects str, got {type(text).__name__}")

    fenced = _fenced_spans(text)
    json_spans = _json_spans(text, fenced)
    python_spans = _python_spans(text, fenced + json_spans, max_lines_for_python_scan)
    spans = sorted(fenced + json_spans + python_spans)

    segments = []
    cursor = 0
    next_id = 0
    for start, end, seg_type in spans:
        if start > cursor:
            segments.append(Segment(next_id, "text", "FLEXIBLE", text[cursor:start], cursor, start))
            next_id += 1
        segments.append(Segment(next_id, seg_type, "STRICT", text[start:end], start, end))
        next_id += 1
        cursor = end
    if cursor < len(text):
        segments.append(Segment(next_id, "text", "FLEXIBLE", text[cursor:], cursor, len(text)))
    return segments


def _placeholder_prefix(text: str) -> str:
    prefix = "__SEG_"
    for variant in range(2, 12):
        if prefix not in text:
            return prefix
        prefix = f"__SEG{variant}_"
    raise ValueError("could not pick a collision-free placeholder prefix")


def mask_strict_segments(text: str, segments: list[Segment]) -> tuple[str, list[tuple[str, str]]]:
    """Replace STRICT segments with length-preserving placeholders.

    Returns ``(masked_text, mapping)`` where mapping is a list of
    ``(placeholder_token, original_content)`` pairs. ``masked_text`` has the
    same length as ``text``, so the downstream pipeline behaves exactly as it
    would on the original bytes.

    Byte-identical STRICT segments share the same token: they collapse like
    any other duplicate, while the first occurrence is restored
    byte-for-byte.
    """
    prefix = _placeholder_prefix(text)
    pieces = []
    mapping = []
    token_by_content = {}
    cursor = 0
    for seg in segments:
        if seg.mode != "STRICT":
            continue
        pieces.append(text[cursor:seg.start])
        if seg.content not in token_by_content:
            token = f"{prefix}{len(mapping)}__"
            pad_len = max(0, seg.length - len(token))
            token += _PAD_CHAR * pad_len
            token_by_content[seg.content] = token
            mapping.append((token, seg.content))
        pieces.append(token_by_content[seg.content])
        cursor = seg.end
    pieces.append(text[cursor:])
    return "".join(pieces), mapping


def restore_strict_segments(text: str, mapping: list[tuple[str, str]]) -> str:
    """Replace placeholder tokens back with the original STRICT content."""
    for token, content in mapping:
        text = text.replace(token, content)
    return text


SEGMENT_TYPE_ORDER = ("code", "json", "block", "text")


def segment_type_breakdown(segments: list[Segment]) -> dict:
    """Per-type segment counts for optimize_text() reporting.

    Each type gets one mode: "protected" (every segment of that type was
    STRICT and masked out of the dedup pipeline) or "processed" (FLEXIBLE,
    deduplicated like ordinary text). Only types with count > 0 are included,
    in the fixed order code / json / block / text.
    """
    breakdown = {}
    for seg_type in SEGMENT_TYPE_ORDER:
        matching = [s for s in segments if s.type == seg_type]
        if not matching:
            continue
        mode = "protected" if all(s.mode == "STRICT" for s in matching) else "processed"
        breakdown[seg_type] = {"count": len(matching), "mode": mode}
    return breakdown