"""CLI: ``tokenlens optimize input.json [--output out.json] [--stdout]``."""

import argparse
import json
import os
import sys

from .core import optimize_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tokenlens",
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "optimize":
        build_parser().print_usage(sys.stderr)
        return 2

    with open(args.input, encoding="utf-8") as f:
        messages = json.load(f)
    if not isinstance(messages, list):
        print("Error: input JSON must be a list of message dicts.", file=sys.stderr)
        return 1
    for message in messages:
        if not isinstance(message, dict) or "role" not in message or "content" not in message:
            print("Error: Each message must have 'role' and 'content'.", file=sys.stderr)
            return 1

    result = optimize_context(messages)
    payload = {
        "optimized_context": result["optimized_context"],
        "metrics": result["metrics"],
        "top_waste_blocks": result["top_waste_blocks"],
    }

    if args.stdout:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(result["report"], file=sys.stderr)
    else:
        output_path = args.output
        if not output_path:
            base, ext = os.path.splitext(args.input)
            output_path = f"{base}_optimized{ext}"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(result["report"])
        print(f"TokenLens optimization complete: saved {result['metrics']['chars_saved']:,} chars "
              f"({result['metrics']['reduction_percentage']}% reduction)")
        print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())