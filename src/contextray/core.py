"""Pipeline orchestrator: the only public entry point of the package."""

from .chunking import chunk_and_hash
from .detection import detect_duplicates
from .optimization import optimize_chunks
from .reporting import generate_metrics_and_report


def optimize_context(messages: list[dict] | str, *, config: dict | None = None, **kwargs) -> dict:
    """Chunk, deduplicate and optimize a list of chat messages, then report savings.

    Parameters
    ----------
    messages : list of {"role": str, "content": str} dicts, or a plain str.
        A str is treated as a single "text"-role message, so free text is
        deduplicated exactly like a one-message transcript.
    config : optional dict reserved for future tuning knobs (chunk sizes, thresholds).
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
    report = generate_metrics_and_report(chunks, optimized)

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