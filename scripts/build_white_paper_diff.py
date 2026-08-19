"""Generate ContextRay_White_Paper_Diff.pdf: v0.1.0 -> v0.3.0 change summary.

Compares the original v0.1 white paper (whose full text was extracted to
text before the v0.3 rebuild) with the current v0.3.0 paper. Reuses the
layout helpers from build_white_paper.py:

    python scripts/build_white_paper_diff.py
"""

import os

from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Spacer

from build_white_paper import (
    P,
    Paper,
    VERSION,
    _toc,
    bullets,
    table,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ContextRay_White_Paper_Diff.pdf")

OLD = "v0.1.0"
NEW = VERSION


def _story(toc_pages):
    story = [
        Spacer(1, 34),
        P("ContextRay \u2014 White Paper Change Summary", "Title"),
        P(f"{OLD}  \u2192  {NEW}", "Subtitle"),
        P("What changed between the two technical white papers: architecture, API contract, "
          "validation, verification, safety, limitations, and reference material. Built from "
          "the extracted text of the original v0.1 PDF and the current v0.3.0 codebase.", "Subtitle"),
        Spacer(1, 16),
        table(
            ["Property", OLD + " paper", NEW + " paper"],
            [
                ["Version", "0.1.0 (first public release)", f"{NEW} (structural segmentation layer)"],
                ["Pages", "14", "15"],
                ["Pipeline stages", "4 (chunk \u2192 detect \u2192 optimize \u2192 report)",
                 "5 + 4 (segmentation layer + core)"],
                ["Public entry points", "1 (optimize_context)", "2 (optimize_context + optimize_text)"],
                ["Return keys", "4", "5 (segments added)"],
                ["Test status", "191 checks \u2014 4 API + 187 pipeline",
                 "222 checks \u2014 18 API + 181 pipeline + 23 segmentation"],
            ],
            widths=[34 * mm, 56 * mm, 56 * mm],
        ),
        Spacer(1, 10),
        P("Provenance: the v0.1.0 PDF was replaced in the v0.3 rebuild, but its complete text "
          "had been extracted first (14 pages, all sections) and is the source for the "
          "\u201cBefore\u201d side throughout this document. \u201cAfter\u201d refers to the "
          "current ContextRay_" + "White_Paper.pdf. Word-level rewording is trimmed; this "
          "document lists semantic changes only.", "Thin"),
        PageBreak(),
    ]

    story += _toc(toc_pages)

    # ---- 1  at a glance ------------------------------------------------------
    story += [
        P("1  What Changed at a Glance", "H1"),
        table(
            ["Area", OLD, NEW],
            [
                ["Pipeline shape",
                 "Four stages; fences masked inside chunking; optimize_context() "
                 "orchestrates.",
                 "Structural Segmentation stage runs first (optimize_text() path): STRICT "
                 "segments masked then restored byte-for-byte; chunking fence masking kept."],
                ["Validation (Python API)",
                 "No documented Python-side error type; per-message checks existed but were "
                 "CLI-documented.",
                 "Fail-fast InvalidMessageError (ValueError subclass) naming message index "
                 "and exact key/type; 5-case table in Section 4."],
                ["Text input",
                 "CLI accepted a JSON message list only; anything else was rejected "
                 "with \u201cInvalid input format\u201d.",
                 "CLI auto-detects: JSON list \u2192 optimize_context(); any other text "
                 "\u2192 optimize_text(); --strict requires the JSON format."],
                ["Token estimates",
                 "Fixed chars \u00f7 4 heuristic, documented as approximate.",
                 "Heuristic stays; token_estimator callable replaces it everywhere; errors "
                 "re-wrapped with context."],
                ["Failure behavior",
                 "Pipeline errors propagate; CLI catch-all prints one-line error.",
                 "Segmentation failure degrades to a safe plain-text fallback "
                 "(segmentation_fallback=true) instead of failing."],
                ["Cost guards",
                 "Marker-length guard only (no negative reduction).",
                 "Plus: unfenced-Python scan firewall at 20,000 lines; CLI input size guard "
                 "--max-input-mb (default 50 MB)."],
                ["Verification",
                 "191 checks: test_core.py (4) + test_pipeline.py (187).",
                 "222 checks: + token_estimator/error cases, CLI text & JSON modes, SEGMENTS "
                 "section, --max-input-mb; new test_segmentation.py (23)."],
                ["Reference material",
                 "11 sections; appendix covers chunking constants and CLI facts.",
                 "Same skeleton; added segmentation rules table, three new constants, and "
                 "raw-text integration example."],
            ],
            widths=[26 * mm, 48 * mm, 58 * mm],
        ),
        PageBreak(),
    ]

    # ---- 2  section by section ------------------------------------------------
    story += [
        P("2  Section-by-Section Walkthrough", "H1"),

        P("1  The Concept", "H2"),
        P("<b>1.3 Design principles</b> \u2014 previously three principles (byte-safety, "
          "determinism, conservative removal); now five. Added: <b>structural protection</b> "
          "(segmentation layer recognizes code/JSON structurally and masks it) and "
          "<b>fail fast, fail safe</b> (InvalidMessageError on bad input; documented "
          "plain-text fallback if segmentation fails). Core concept paragraphs unchanged."),

        P("2  Architecture", "H2"),
        *bullets([
            "Stages: 4 \u2192 <b>segmentation layer + 4-stage core</b> (5 modules). Diagram "
            "gained stage [0] \u201cmask STRICT with length-preserving placeholders\u201d and "
            "stage [4] \u201crestore placeholders byte-for-byte\u201d.",
            "<b>New 2.1 \u201cStage 0 \u2014 Structural Segmentation\u201d</b>: detection-rule "
            "table (fenced code / fenced block / whole-line JSON / bare Python \u2265 3 lines "
            "/ text), STRICT vs FLEXIBLE, placeholder padding, duplicate-STRICT collapse, "
            "20,000-line firewall, fallback semantics.",
            "Old 2.1\u20132.4 renumbered to 2.2\u20132.5; chunking/detection/optimization text "
            "unchanged.",
            "2.5 Reporting: added the \u201cSegments:\u201d section inserted into "
            "optimize_text() reports, and the token note naming which estimator was used.",
        ]),

        P("3  Public API Contract", "H2"),
        *bullets([
            "3.1: one entry point \u2192 <b>two</b>: optimize_text(raw_text) added; both expose "
            "stable signatures with config + token_estimator kwargs; a plain str is now also "
            "accepted by optimize_context().",
            "Return contract: 4 keys \u2192 <b>5</b> \u2014 \u201csegments\u201d key "
            "(per-type counts/modes, optimize_text path only).",
            "metrics schema: 6 fields \u2192 <b>7</b> \u2014 segmentation_fallback added.",
            "New paragraph on token_estimator: replacement semantics, error wrapping, "
            "est_tokens_saved = in \u2212 out.",
            "3.2 CLI: usage gained <b>--strict</b> and <b>--max-input-mb FLOAT</b>; input "
            "description \u201cany text file\u201d; auto-detection paragraph; \u201cthree of "
            "the five result keys\u201d; terminal report layout now opens with the SEGMENTS "
            "block (text inputs).",
        ]),

        P("4  Input Validation & Error Handling", "H2"),
        *bullets([
            "Before: CLI-only bullet list (file exists \u2192 valid JSON \u2192 top-level list "
            "\u2192 dict shape \u2192 string values) + catch-all handler.",
            "After: same CLI list, but the <b>size guard runs first</b> (before reading), and "
            "each shape failure now names the offending message index.",
            "New: Python API fail-fast section \u2014 InvalidMessageError case table "
            "(content None, content list, missing keys, non-dict items, non-string values).",
        ]),

        P("5  Determinism & Verification", "H2"),
        *bullets([
            "191 \u2192 <b>222 checks</b>: 18 API (validation errors, token_estimator) + 181 "
            "pipeline (CLI text/JSON modes, SEGMENTS section, --max-input-mb) + 23 new "
            "segmentation checks.",
            "test_segmentation.py (new): segment contiguity and byte-exactness, fence/JSON/"
            "bare-Python rules, STRICT survival, exact metrics with masking, precedence, line "
            "guard, fallback flag, segments breakdown.",
        ]),

        P("6  Empirical Findings (A/B with llama3.2:3b)", "H2"),
        P("<b>No changes.</b> The three findings, the reviewer table, and the guidance are "
          "reproduced verbatim \u2014 v0.3 introduced no new model-facing behavior."),

        P("7  Safety Guarantees", "H2"),
        *bullets([
            "Kept: system messages preserved, cross-role duplicates never removed, no negative "
            "reductions, tiny chunks conservative.",
            "Added: <b>STRICT segments survive byte-exact</b>; <b>placeholders never leak</b> "
            "(collision-free per run); <b>guarded worst-case costs</b> (20,000-line scan "
            "firewall + --max-input-mb); <b>safe fallback</b> (segmentation_fallback=true, "
            "never a crash).",
        ]),

        P("8  Known Problems & Limitations", "H2"),
        *bullets([
            "\u201cCode-fence coverage is narrow\u201d rewritten as \u201cStructural coverage "
            "is finite\u201d: scope widened from fences only to fences + whole-line JSON + "
            "parseable bare Python (\u2265 3 lines); inline code and malformed fences still "
            "chunk like text.",
            "Three rows added: unfenced-Python scan capped at 20,000 lines; fallback loses "
            "STRICT protection (flagged in metrics/report); CLI rejects files over "
            "--max-input-mb.",
            "Unchanged rows: exact bytes only, marker bias, whitespace-sensitive hashing, tiny "
            "chunks, cross-role duplicates, token heuristic, config ignored.",
            "Open questions updated: machine-readable role stats, configurable marker "
            "wording, MIN/MAX chunk size knobs.",
        ]),

        P("9  Integration Guide", "H2"),
        *bullets([
            "Chat loop, agent flows, structured JSON content: unchanged.",
            "<b>New subsection \u201cRaw text and documents\u201d</b>: optimize_text() example "
            "with the segments key and byte-exact protection behavior.",
            "Golden rule now names both entry points (was: optimize_context is \u201cthe only "
            "documented public entry point\u201d).",
        ]),

        P("10  Appendix A \u2014 Worked Example", "H2"),
        *bullets([
            "sample_chat.json example and its report: unchanged (48 chars, 0%, tiny-chunk "
            "explanation).",
            "Realistic fixture report: gained the SEGMENTS block (code: 2 (protected), "
            "json: 1 (protected)) before IMPACT.",
        ]),

        P("11  Appendix B \u2014 Quick Reference", "H2"),
        *bullets([
            "<b>New table \u201cSegmentation decisions at a glance\u201d</b> (5 detection "
            "rules \u2192 segment type/mode).",
            "Pipeline decisions table: unchanged.",
            "Constants: added SEGMENT_PLACEHOLDER, MAX_LINES_FOR_PYTHON_SCAN, MAX_INPUT_MB; "
            "the original five kept verbatim.",
            "CLI facts: added auto-detection/--strict bullet and the size-guard bullet.",
            "Project facts: version 0.1.0 \u2192 0.3.0; tests 4+187 \u2192 18+181+23; entry "
            "points 1 \u2192 2.",
        ]),
        PageBreak(),
    ]

    # ---- 3  new + 4  unchanged + 5 corrections --------------------------------
    story += [
        P("3  Brand-New Content", "H1"),
        table(
            ["New item", "Where"],
            [
                ["segment_text() / Segment / mask_strict_segments() / restore_strict_segments()",
                 "2.1"],
                ["segments result key and SEGMENTS report section", "3.1, 3.2, 2.5"],
                ["InvalidMessageError validation contract", "4"],
                ["segmentation_fallback metric and fallback semantics", "3.1, 7, 8"],
                ["token_estimator kwarg", "3.1"],
                ["--strict and --max-input-mb CLI flags; text auto-detection", "3.2, 4"],
                ["20,000-line unfenced-Python firewall", "2.1, 7, 8, 11"],
                ["Raw text & documents integration subsection", "9"],
                ["Segmentation decisions reference table", "11"],
            ],
            widths=[88 * mm, 28 * mm],
        ),
        PageBreak(),

        P("4  What Did NOT Change", "H1"),
        *bullets([
            "Core dedup semantics: global + per-role lookup tables, KEPT / REMOVED / "
            "FLAGGED_ONLY, same-speaker-only removal, system always kept.",
            "Chunk size constants (MAX_CHUNK_SIZE 1000, MIN_CHUNK_SIZE 64) and "
            "whitespace-folded sha256 hashing.",
            "Marker text and the negative-reduction guard (33-char marker, chunk kept when "
            "the marker is \u2265 chunk length).",
            "Reporting arithmetic: waste = (count\u22121) \u00d7 length, top 5 blocks, per-role "
            "stats, safety notes.",
            "Empirical A/B findings and their guidance (Section 6).",
            "Worked example input and its 0%-savings lesson (Appendix A).",
            "CLI exit codes (0 / 1 / 2), default output naming, --stdout/--output behavior, "
            "Unicode\u2192ASCII marker fallback.",
            "Python \u2265 3.9, zero runtime dependencies, MIT license.",
        ]),
        PageBreak(),

        P("5  Stale Data Corrected", "H1"),
        table(
            ["Item", "Before (v0.1 paper)", "After (v0.3 paper)"],
            [
                ["Version", "0.1.0", "0.3.0"],
                ["Test status", "191 checks \u2014 4 API + 187 pipeline",
                 "222 checks \u2014 18 API + 181 pipeline + 23 segmentation"],
                ["Entry points", "\u201conly documented public entry point\u201d (singular)",
                 "two documented entry points"],
                ["Result keys written by the CLI", "\u201cthree of the four result keys\u201d",
                 "\u201cthree of the five result keys\u201d"],
                ["Limitation scope", "fences only", "fences + whole-line JSON + bare Python"],
                ["Generated-from note", "v0.1 codebase", "v0.3 codebase"],
            ],
            widths=[40 * mm, 34 * mm, 42 * mm],
        ),
        Spacer(1, 10),
        P("This change summary was generated from the extracted v0.1.0 PDF text and the "
          "v0.3.0 codebase. The current white paper can be regenerated at any time with "
          "python scripts/build_white_paper.py; this document with "
          "python scripts/build_white_paper_diff.py.", "Thin"),
    ]

    return story


def _build(toc_pages):
    doc = Paper(OUT, title="ContextRay White Paper Change Summary",
                author="ContextRay", subject=f"White paper diff {OLD} -> {NEW}")
    doc.build(_story(toc_pages))
    return doc


def main():
    import build_white_paper

    build_white_paper.HEADER = (
        "ContextRay \u2014 White Paper Change Summary  \u00b7  v0.1.0 \u2192 v0.3.0")
    pass1 = _build([])
    entries = list(pass1.toc_entries)
    if entries and entries[0][1] == "Contents":
        entries = entries[1:]
    pass2 = _build([(level, text, page) for level, text, page in entries])
    final = pass2.toc_entries[1:]
    if [e[:2] for e in final] != [e[:2] for e in entries]:
        raise RuntimeError("heading set changed between passes")
    mismatches = [(a, b) for a, b in zip(entries, final) if a[2] != b[2]]
    if mismatches:
        raise RuntimeError(f"page numbers shifted between passes: {mismatches[:3]}")
    print(f"wrote {OUT}  ({len(entries)} TOC entries, {pass2.page} pages)")


if __name__ == "__main__":
    main()