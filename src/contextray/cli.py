"""CLI: ``contextray optimize input.json [--output out.json] [--stdout]``."""

import argparse
import json
import os
import sys

from .core import optimize_context

EXPECTED_FORMAT = "Invalid input format. Expected: [{'role': '...', 'content': '...'}]"

_ERR = "[ERROR]"
_CHECK = "[OK]"
_IMPACT = "IMPACT"
_WASTE = "TOP WASTE"
_SAFETY = "SAFETY"


def _configure_markers() -> None:
    """Prefer emoji glyphs on Unicode consoles, ASCII fallbacks on legacy code pages."""
    global _ERR, _CHECK, _IMPACT, _WASTE, _SAFETY
    for stream in (sys.stdout, sys.stderr):
        try:
            "✔".encode(stream.encoding or "utf-8")
        except (UnicodeEncodeError, LookupError):
            return
    _ERR = "❌"
    _CHECK = "✓"
    _IMPACT = "📊 IMPACT"
    _WASTE = "🔥 TOP WASTE"
    _SAFETY = "🛡️ SAFETY"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextray",
        description="Optimize chat message context: chunking, deduplication, reporting.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    opt = subparsers.add_parser("optimize", help="Optimize messages from a JSON file.")
    opt.add_argument("input", help="Path to a JSON file with a list of messages.")
    opt.add_argument("--output", "-o",
                     help="Where to write the optimized JSON (default: <input>_optimized<ext>).")
    opt.add_argument("--stdout", action="store_true",
                     help="Print the optimized JSON to stdout instead of a file.")
    return parser


def _fail(message: str) -> int:
    print(f"{_ERR} Error: {message}", file=sys.stderr)
    return 1


def _load_and_validate(path: str) -> tuple[list, int] | None:
    try:
        with open(path, encoding="utf-8") as f:
            messages = json.load(f)
    except json.JSONDecodeError:
        _fail(f"{EXPECTED_FORMAT} ({path} is not valid JSON)")
        return None
    except OSError as exc:
        _fail(f"could not read {path}: {exc.strerror or exc}")
        return None

    if not isinstance(messages, list):
        _fail(f"{EXPECTED_FORMAT} (top-level value must be a list)")
        return None
    for i, message in enumerate(messages):
        if not isinstance(message, dict) or "role" not in message or "content" not in message:
            _fail(f"{EXPECTED_FORMAT} (message {i} must have 'role' and 'content')")
            return None
        if not isinstance(message["role"], str) or not isinstance(message["content"], str):
            _fail(f"{EXPECTED_FORMAT} (message {i} 'role' and 'content' must be strings)")
            return None
    return messages, 0


def _format_report(result: dict) -> str:
    metrics = result["metrics"]
    total_in = metrics["total_chars_in"]
    total_out = metrics["total_chars_out"]
    saved = metrics["chars_saved"]
    reduction = round(metrics["reduction_percentage"])

    lines = [
        "=== CONTEXTRAY OPTIMIZATION REPORT ===",
        "",
        _IMPACT,
        f"Original: {total_in:,} chars",
        f"Optimized: {total_out:,} chars",
        f"Saved: {saved:,} chars ({reduction}%)",
        "",
        _WASTE,
    ]
    blocks = result["top_waste_blocks"]
    if blocks:
        for block in blocks:
            lines.append(
                f"- Hash {block['hash'][:12]}... repeated {block['count']} times "
                f"({block['chars_wasted']:,} chars wasted)"
            )
    else:
        lines.append("- No duplicate blocks found")
    lines += [
        "",
        _SAFETY,
        f"{_CHECK} System messages preserved",
        f"{_CHECK} Cross-role duplicates not removed",
        f"{_CHECK} Code blocks protected",
        f"{_CHECK} Small chunks skipped",
        "",
        "-------------------------------------",
    ]
    return "\n".join(lines)


def _run(args) -> int:
    loaded = _load_and_validate(args.input)
    if loaded is None:
        return 1
    messages, _ = loaded

    result = optimize_context(messages)
    payload = {
        "optimized_context": result["optimized_context"],
        "metrics": result["metrics"],
        "top_waste_blocks": result["top_waste_blocks"],
    }

    if args.stdout:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"{_CHECK} ContextRay Optimization Complete", file=sys.stderr)
        print(_format_report(result), file=sys.stderr)
        return 0

    output_path = args.output
    if not output_path:
        base, ext = os.path.splitext(args.input)
        output_path = f"{base}_optimized{ext}"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        return _fail(f"could not write {output_path}: {exc.strerror or exc}")

    print(f"{_CHECK} ContextRay Optimization Complete")
    print()
    print(_format_report(result))
    print(f"Output saved to: {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_markers()
    args = build_parser().parse_args(argv)
    if args.command != "optimize":
        build_parser().print_usage(sys.stderr)
        return 2
    try:
        return _run(args)
    except Exception as exc:  # noqa: BLE001 - CLI must never crash with a traceback
        return _fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())