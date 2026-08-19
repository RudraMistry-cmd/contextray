"""Benchmark segment_text() on plain prose (worst case for the scanners).

Synthetic inputs with no fences, no valid JSON and no parseable Python -
the pathological case for _python_spans/_json_spans, which restart their
scan from every candidate line.

Usage:  python scripts/bench_segmentation.py [n1 n2 n3 ...]

Prints wall-clock time per size; nothing is written to disk.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from contextray import segment_text  # noqa: E402


def plain_text(line_count: int) -> str:
    return "\n".join(
        f"plain prose filler line number {i} with a few words" for i in range(line_count)
    ) + "\n"


def bench(lines: int) -> float:
    text = plain_text(lines)
    start = time.perf_counter()
    segment_text(text)
    return time.perf_counter() - start


def main() -> None:
    sizes = [int(a) for a in sys.argv[1:]] or [1_000, 10_000, 50_000]
    results = []
    for lines in sizes:
        elapsed = bench(lines)
        results.append((lines, elapsed))
        print(f"{lines:>8,} lines  {elapsed:8.3f}s  "
              f"({elapsed * 1e6 / lines:6.0f} us/line)")

    if len(results) >= 2:
        base_lines, base_time = results[0]
        print()
        print("scaling vs smallest input (linear would be ~1x per line multiple):")
        for lines, elapsed in results[1:]:
            ratio = elapsed / base_time
            line_ratio = lines / base_lines
            print(f"  {lines:>8,} lines: {ratio:6.2f}x time vs {line_ratio:5.1f}x lines "
                  f"-> {'SUPERLINEAR' if ratio > 1.3 * line_ratio else 'linear-ish'}")


if __name__ == "__main__":
    main()
