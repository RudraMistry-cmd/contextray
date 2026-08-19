"""Pipeline orchestrator: the only public entry point of the package."""

from collections.abc import Callable

from .chunking import chunk_and_hash
from .detection import detect_duplicates
from .optimization import optimize_chunks
from .reporting import _call_estimator, generate_metrics_and_report
from .segmentation import (
    mask_strict_segments,
    restore_strict_segments,
    segment_text,
    segment_type_breakdown,
)


def optimize_context(messages: list[dict] | str, *, config: dict | None = None,
                     token_estimator: Callable[[str], float] | None = None, **kwargs) -> dict:
    """Chunk, deduplicate and optimize a list of chat messages, then report savings.

    Parameters
    ----------
    messages : list of {"role": str, "content": str} dicts, or a plain str.
        A str is treated as a single "text"-role message, so free text is
        deduplicated exactly like a one-message transcript.
    config : optional dict reserved for future tuning knobs (chunk sizes, thresholds).
    token_estimator : optional callable ``str -> float`` replacing the
        default chars/4 token heuristic. Receives the full original text and
        the full optimized text; its return value is used directly. Default
        None keeps the chars/4 heuristic exactly.
    **kwargs : reserved for future parameters; accepted so callers are not broken.

    Returns
    -------
    dict with keys:
        optimized_context : list of {"role", "content"} messages with deduplicated text
        metrics           : character/token impact numbers
        top_waste_blocks  : worst duplicate blocks (hash, role, count, chars wasted)
        report            : human-readable summary
    """
    config = dict(config or {})  # reserved: future tuning knobs plug in here
    if isinstance(messages, str):
        messages = [{"role": "text", "content": messages}]

    chunks = chunk_and_hash(messages)
    marked = detect_duplicates(chunks)
    optimized = optimize_chunks(marked)
    report = generate_metrics_and_report(chunks, optimized, token_estimator=token_estimator)

    optimized_messages = [
        {"role": c["role"], "content": c["text"]}
        for c in optimized
    ]

    return {
        "optimized_context": optimized_messages,
        "metrics": report["metrics"],
        "top_waste_blocks": report["top_waste_blocks"],
        "report": report["report"],
    }


def optimize_text(text: str, *, config: dict | None = None,
                  token_estimator: Callable[[str], float] | None = None, **kwargs) -> dict:
    """Pre-process raw text with the Structural Segmentation Layer, then optimize.

    STRICT segments (fenced code, fenced blocks, whole-line JSON values) are
    masked with length-preserving placeholders before the existing pipeline
    runs, and restored byte-for-byte afterwards. Everything else (FLEXIBLE
    text) flows through the pipeline unchanged.

    If the segmentation step itself fails for any reason, the function falls
    back to optimizing the raw text directly (the pipeline still runs, but
    without protection); ``metrics["segmentation_fallback"]`` is True in that
    case and the report is prefixed with a note. Errors raised by the
    pipeline itself are never swallowed.

    Returns the same 4-key contract as :func:`optimize_context`, plus a
    ``segments`` key with per-type counts (segmentation path only).
    ``token_estimator`` behaves exactly as in :func:`optimize_context`.
    """
    try:
        segments = segment_text(text)
        masked, mapping = mask_strict_segments(text, segments)
    except Exception:
        result = optimize_context(text, config=config,
                                  token_estimator=token_estimator, **kwargs)
        result["metrics"]["segmentation_fallback"] = True
        result["report"] = ("Segmentation failed \u2014 processed as plain text (safe fallback).\n"
                            + result["report"])
        return result

    result = optimize_context(masked, config=config,
                              token_estimator=token_estimator, **kwargs)
    restored = [
        {"role": message["role"], "content": restore_strict_segments(message["content"], mapping)}
        for message in result["optimized_context"]
    ]
    result["optimized_context"] = restored

    result["segments"] = segment_type_breakdown(segments)

    # Tiny STRICT segments can be shorter than their placeholder, so correct
    # the character metrics (and the report's impact line) against the exact
    # restored bytes. Same arithmetic as reporting.generate_metrics_and_report.
    total_in = len(text)
    total_out = sum(len(message["content"]) for message in restored)
    chars_saved = total_in - total_out
    reduction = round(chars_saved / total_in * 100, 2) if total_in else 0.0
    if token_estimator is None:
        est_tokens_in = total_in / 4
        est_tokens_saved = chars_saved / 4
    else:
        restored_text = "".join(message["content"] for message in restored)
        est_tokens_in = _call_estimator(token_estimator, text, "original text")
        est_tokens_saved = est_tokens_in - _call_estimator(
            token_estimator, restored_text, "optimized text")
    result["metrics"].update({
        "total_chars_in": total_in,
        "total_chars_out": total_out,
        "chars_saved": chars_saved,
        "reduction_percentage": reduction,
        "est_tokens_in": est_tokens_in,
        "est_tokens_saved": est_tokens_saved,
        "segmentation_fallback": False,
    })
    report_lines = result["report"].split("\n")
    impact_prefix = "Impact: "
    for i, line in enumerate(report_lines):
        if line.startswith(impact_prefix):
            section = ["Segments:"]
            section += [f"  {seg_type}: {info['count']} ({info['mode']})"
                        for seg_type, info in result["segments"].items()]
            report_lines[i:i] = section
            report_lines[i + len(section)] = (
                f"{impact_prefix}{total_in} chars in -> {total_out} chars out "
                f"({chars_saved} chars saved, {reduction}% reduction)")
            break
    result["report"] = "\n".join(report_lines)
    return result