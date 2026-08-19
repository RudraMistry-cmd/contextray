"""Regenerate ContextRay_White_Paper.pdf (repo root) with reportlab.

Mirrors the original v0.1 white paper layout (A4, Helvetica/Courier,
Property table, dotted-leader TOC, gray header/footer) updated to the
v0.3.0 feature set:

    python scripts/build_white_paper.py

The TOC is built in two passes: pass 1 records the page number of every
heading, pass 2 renders the TOC with real page numbers. Both passes use
identical flowable heights, so pagination never shifts between them.
"""

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ContextRay_White_Paper.pdf")

VERSION = "0.3.0"
HEADER = f"ContextRay \u2014 Technical White Paper  \u00b7  v{VERSION}"

PAGE_W, PAGE_H = A4
MARGIN = 19 * mm
TEXT_W = PAGE_W - 2 * MARGIN

DARK = colors.HexColor("#222222")
MID = colors.HexColor("#555555")
LIGHT_BG = colors.HexColor("#f0f0f0")
HEAD_BG = colors.HexColor("#e3e3e3")

# --------------------------------------------------------------------------
# styles


def _body(name="Body", size=9.5, leading=13.2, **kw):
    defaults = dict(alignment=TA_JUSTIFY, spaceAfter=5)
    defaults.update(kw)
    return ParagraphStyle(
        name,
        fontName="Helvetica",
        fontSize=size,
        leading=leading,
        textColor=DARK,
        **defaults,
    )


S = {
    "Title": ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=30,
                            leading=36, textColor=DARK, spaceAfter=10),
    "Subtitle": ParagraphStyle("Subtitle", fontName="Helvetica", fontSize=13.5,
                               leading=18, textColor=MID, spaceAfter=6),
    "VersionTag": ParagraphStyle("VersionTag", fontName="Helvetica-Bold", fontSize=10,
                                 leading=13, textColor=colors.HexColor("#666666"),
                                 spaceAfter=22),
    "H1": ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=14,
                         leading=18, textColor=DARK, spaceBefore=6, spaceAfter=8,
                         keepWithNext=1),
    "H2": ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11.5,
                         leading=15, textColor=DARK, spaceBefore=10, spaceAfter=5,
                         keepWithNext=1),
    "Body": _body(),
    "Thin": _body("Thin", size=8.5, leading=11.5),
    "Bullet": _body("Bullet", leftIndent=12, bulletIndent=2, spaceAfter=3),
    "Code": ParagraphStyle("Code", fontName="Courier", fontSize=8, leading=10.5,
                           textColor=DARK),
    "TableText": ParagraphStyle("TableText", fontName="Helvetica", fontSize=8.5,
                                leading=11, textColor=DARK),
    "TableHead": ParagraphStyle("TableHead", fontName="Helvetica-Bold", fontSize=8.5,
                                leading=11, textColor=DARK),
    "TableTextC": ParagraphStyle("TableTextC", fontName="Helvetica", fontSize=8,
                                 leading=10, textColor=DARK),
    "TableHeadC": ParagraphStyle("TableHeadC", fontName="Helvetica-Bold", fontSize=8,
                                 leading=10, textColor=DARK),
    "H2C": ParagraphStyle("H2C", fontName="Helvetica-Bold", fontSize=11,
                          leading=14, textColor=DARK, spaceBefore=6, spaceAfter=4,
                          keepWithNext=1),
    "BulletC": ParagraphStyle("BulletC", leftIndent=12, bulletIndent=2,
                              fontSize=9, leading=11.5, spaceAfter=1.5,
                              fontName="Helvetica", textColor=DARK),
}

E = dict  # escape helper alias


def P(text, style="Body"):
    return Paragraph(text, S[style])


def CODE(lines, box=True):
    flow = [Preformatted("\n".join(lines), S["Code"])]
    if box:
        return [
            Spacer(1, 4),
            _box(flow),
            Spacer(1, 6),
        ]
    return flow


def _box(flowables, bg=LIGHT_BG):
    inner = Table([[f] for f in flowables], colWidths=[TEXT_W - 10])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8c8c8")),
        ("LINEABOVE", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8c8c8")),
    ]))
    return inner


def table(headers, rows, widths=None, compact=False):
    head_style = "TableHeadC" if compact else "TableHead"
    text_style = "TableTextC" if compact else "TableText"
    data = [[Paragraph(h, S[head_style]) for h in headers]]
    for row in rows:
        data.append([Paragraph(c, S[text_style]) for c in row])
    t = Table(data, colWidths=widths, repeatRows=1)
    pad = 2 if compact else 3
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c0c0c0")),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
    ]))
    return t


def bullets(items, style="Bullet"):
    return [Paragraph(item, S[style], bulletText="\u2013") for item in items]


# --------------------------------------------------------------------------
# TOC (two-pass)


class TocLine(Flowable):
    """One TOC row: heading on the left, dotted leader, page number right."""

    def __init__(self, level, text, page):
        super().__init__()
        self.level = level
        self.text = text
        self.page = page
        self.width = TEXT_W
        self.height = 13

    def draw(self):
        c = self.canv
        c.saveState()
        indent = 10 * (self.level - 1)
        font = "Helvetica-Bold" if self.level == 1 else "Helvetica"
        size = 9.5 if self.level == 1 else 9
        c.setFont(font, size)
        c.setFillColor(DARK)
        c.drawString(indent, 0, self.text)
        if self.page:
            num_w = c.stringWidth(str(self.page), font, size)
            dots_from = indent + c.stringWidth(self.text, font, size) + 5
            dots_to = self.width - num_w - 4
            c.setStrokeColor(colors.HexColor("#999999"))
            c.setLineWidth(0.4)
            c.setDash(1, 2.2)
            c.line(dots_from, 2.2, dots_to, 2.2)
            c.setDash()
            c.drawRightString(self.width, 0, str(self.page))
        c.restoreState()


class Paper(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, pagesize=A4,
                         leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=24 * mm, bottomMargin=22 * mm, **kw)
        frame = Frame(MARGIN, 22 * mm, TEXT_W, PAGE_H - 46 * mm, id="main",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=_header_footer)])
        self.toc_entries = []

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            name = getattr(flowable.style, "name", "")
            if name in ("H1", "H2", "H2C"):
                level = 1 if name == "H1" else 2
                self.toc_entries.append((level, flowable.getPlainText(),
                                         self.canv.getPageNumber()))


def _header_footer(canv, doc):
    canv.saveState()
    canv.setFont("Helvetica", 7.5)
    canv.setFillColor(MID)
    canv.drawString(MARGIN, PAGE_H - 13 * mm, HEADER)
    canv.drawRightString(PAGE_W - MARGIN, PAGE_H - 13 * mm, f"Page {canv.getPageNumber()}")
    canv.setStrokeColor(colors.HexColor("#c8c8c8"))
    canv.setLineWidth(0.4)
    canv.line(MARGIN, PAGE_H - 14 * mm, PAGE_W - MARGIN, PAGE_H - 14 * mm)
    canv.restoreState()


def _toc(entries):
    """entries: list of (level, text, page_or_None); page None in pass 1."""
    flow = [P("Contents", "H1"), Spacer(1, 6)]
    for level, text, page in entries:
        flow.append(TocLine(level, text, page))
    flow.append(PageBreak())
    return flow


# --------------------------------------------------------------------------
# content


def _story(toc_pages):
    story = []

    # ---- title page -------------------------------------------------------
    story += [
        Spacer(1, 40),
        P("ContextRay", "Title"),
        P("Deterministic Context Optimization for LLM Chat Histories", "Subtitle"),
        P(f"A technical white paper covering the concept, architecture, API contract, "
          f"empirical findings, and the known problems and limitations of "
          f"ContextRay v{VERSION}.", "Subtitle"),
        Spacer(1, 18),
        table(
            ["Property", "Value"],
            [
                ["Version", f"{VERSION} (structural segmentation layer)"],
                ["Package", "contextray \u2014 pip install contextray"],
                ["Repository", "github.com/RudraMistry-cmd/contextray"],
                ["License", "MIT"],
                ["Python support", "\u2265 3.9, standard library only (zero runtime dependencies)"],
                ["Test status", "222 checks \u2014 18 API + 181 pipeline + 23 segmentation, all passing"],
            ],
            widths=[26 * mm, None],
        ),
        PageBreak(),
    ]

    # ---- table of contents ------------------------------------------------
    story += _toc(toc_pages)

    # ---- 1  The Concept ----------------------------------------------------
    story += [
        P("1  The Concept", "H1"),
        P("ContextRay is a deterministic, character-level optimizer for LLM chat histories. "
          "It takes the exact message list an application would send to a model \u2014 a sequence "
          "of {'role': ..., 'content': ...} dictionaries \u2014 and returns a drop-in replacement "
          "list with byte-identical duplicates removed, plus precise impact metrics and a "
          "human-readable report. Nothing is summarized, paraphrased, or inferred; every "
          "transformation is a function of the input bytes alone."),
        P("The core insight is that in production LLM systems, most context bloat does not come "
          "from verbose prose. It comes from the runtime: frameworks that re-inject state, "
          "frameworks that replay completed turns, cache/retry mechanisms that append the same "
          "assistant payload twice, and agents that hand the same transcript forward at every "
          "step. This redundant traffic is byte-identical, and byte-identical content can be "
          "removed with zero information loss \u2014 deterministically and verifiably."),

        P("1.1  Why this problem matters", "H2"),
        *bullets([
            "<b>Cost.</b> Tokens are billed per character. Repeating content in every round "
            "multiplies cost linearly with conversation length.",
            "<b>Latency.</b> Model response time grows with context length; trimmed contexts "
            "respond faster.",
            "<b>Reasoning quality.</b> Long contexts degrade retrieval accuracy \u2014 the "
            "needle-in-a-haystack problem. Noise dilutes the signal a model attends to.",
            "<b>Debugging and auditability.</b> A byte-safe, deterministic transform can be "
            "reproduced offline, tested, and reasoned about; an ML summarizer cannot.",
        ]),

        P("1.2  What it deliberately is NOT", "H2"),
        P("ContextRay does not compress with embeddings, does not summarize, does not use a "
          "language model at any point, and cannot hallucinate. It operates on exact string "
          "equality only. This is a deliberate philosophical choice: the tool's guarantees are "
          "only as strong as the deterministic laws it is built on, and those laws hold "
          "everywhere, on every input, in every environment."),

        P("1.3  Design principles", "H2"),
        *bullets([
            "<b>Byte-safety first.</b> Removal only. Every transformation either keeps text "
            "verbatim or deletes an exact duplicate of it. No rewrite ever happens.",
            "<b>Deterministic everything.</b> Same input, same output, same hashes, same "
            "report \u2014 across runs, machines, and platforms.",
            "<b>Structural protection.</b> Code, JSON, and fenced blocks are recognized "
            "structurally (fences, parsers) and masked before the pipeline runs, so they can "
            "never be split or corrupted internally (Section 2.1).",
            "<b>Fail fast, fail safe.</b> Invalid input raises an error naming the offending "
            "message and field; if classification work itself fails, the pipeline degrades to a "
            "documented plain-text fallback instead of crashing (Section 4).",
            "<b>Conservative removal.</b> Only same-speaker byte-repeats are removed; "
            "everything else is reported, not touched.",
        ]),
        PageBreak(),
    ]

    # ---- 2  Architecture ---------------------------------------------------
    story += [
        P("2  Architecture", "H1"),
        P("The package is a segmentation layer plus a four-stage core. Every stage lives in its "
          "own module with a single public function, so the pipeline can be inspected, tested, "
          "and reused stage by stage."),
        *CODE([
            "segment_text        chunk_and_hash      detect_duplicates      optimize_chunks      generate_metrics_and_report",
            "(segmentation.py)   (chunking.py)        (detection.py)         (optimization.py)        (reporting.py)",
        ], box=False),
        Spacer(1, 2),
        *CODE([
            "raw text / messages",
            "   |",
            "   v",
            "[0] split into STRICT / FLEXIBLE segments; mask STRICT with length-preserving",
            "    placeholders (fenced code, whole-line JSON, parseable bare Python stay   ",
            "    byte-exact even if duplicated)",
            "   |",
            "   v",
            "[1] split into chunks <= 1000 chars, sha256-hash every chunk >= 64 chars",
            "   |",
            "   v",
            "[2] mark each chunk KEPT / REMOVED / FLAGGED_ONLY using global + per-role",
            "    lookup tables",
            "   |",
            "   v",
            "[3] replace REMOVED chunks with a short marker (guarded against negative",
            "    reduction)",
            "   |",
            "   v",
            "[4] restore placeholders byte-for-byte; compute metrics, top waste blocks,",
            "    per-role stats, human-readable report",
        ]),
        P("The orchestrators optimize_context() and optimize_text() in core.py wire the stages "
          "together and are the only documented public entry points. Their return contracts are "
          "fixed (Section 3); the internal chunk representation never leaks into them."),

        P("2.1  Stage 0 \u2014 Structural Segmentation (segmentation.py)", "H2"),
        P("Before deduplication runs, segment_text() splits the input into ordered, contiguous, "
          "byte-exact segments. Each segment is either STRICT (provably structural \u2014 masked "
          "out of the pipeline with a placeholder, restored byte-for-byte afterwards) or "
          "FLEXIBLE (deduplicated like ordinary text). The rules are purely structural \u2014 "
          "no NLP, no guessing:"),
        table(
            ["Type", "Detection rule", "Mode"],
            [
                ["code", "```-fenced block with a language tag on the opening fence", "STRICT"],
                ["block", "```-fenced block with no language tag", "STRICT"],
                ["json", "one or more whole lines that parse as a single JSON value "
                 "(verified with json.loads; fences take precedence)", "STRICT"],
                ["code", "at least 3 whole lines that parse as valid Python (verified with "
                 "ast.parse) \u2014 covers code pasted without fences", "STRICT"],
                ["text", "everything else", "FLEXIBLE"],
            ],
            widths=[16 * mm, 92 * mm, 24 * mm],
        ),
        Spacer(1, 4),
        P("Masking replaces each STRICT segment with a \u201c__SEG\u2026\u201d token padded with an "
          "invisible filler to the segment's exact original length, so the downstream chunking "
          "behavior and metrics are unchanged (masked length == original length). Byte-identical "
          "STRICT segments share one token, so duplicates among protected regions collapse like "
          "any other duplicate \u2014 and the reference copy is restored byte-for-byte."),
        P("The unfenced-Python scan restarts from every candidate line, which is superlinear on "
          "fence-free prose. A firewall caps the cost: inputs above 20,000 lines "
          "(max_lines_for_python_scan=20000) skip that scan entirely \u2014 fence and JSON "
          "detection, which are cheap and linear, still run. Pass None to scan at any size."),
        P("If segmentation itself raises for any reason, optimize_text() falls back to running "
          "the pipeline over the raw text (safe, but without STRICT protection): "
          "metrics[\"segmentation_fallback\"] is True and the report is prefixed with a note. "
          "Errors raised by the pipeline itself are never swallowed."),

        P("2.2  Stage 1 \u2014 Chunking (chunking.py)", "H2"),
        P("Messages are split into chunks with a hard ceiling of 1,000 characters "
          "(MAX_CHUNK_SIZE). Splitting prefers natural boundaries in this order: double-newline "
          "paragraph breaks, then single-newline line breaks, then the nearest whitespace. "
          "Delimiters are kept attached so text is never deleted."),
        P("Fenced code blocks (triple backticks) are masked with placeholders before splitting, "
          "so a fence is never cut in half; the real text is restored after chunking. Chunks "
          "shorter than 64 characters (MIN_CHUNK_SIZE) are treated as noise: they are not hashed "
          "(hash = None) and are deduplicated by their raw text instead. Every other chunk "
          "receives sha256(text.strip())."),
        table(
            ["Constant", "Value", "Effect"],
            [
                ["MAX_CHUNK_SIZE", "1000", "split ceiling: paragraphs \u2192 lines \u2192 whitespace"],
                ["MIN_CHUNK_SIZE", "64", "below this: hash = None, never replaced"],
                ["CODE_FENCE_REGEX", "```.*?``` (DOTALL)", "placeholder-masked before splitting"],
                ["DEDUP_KEY", "hash or raw text", "tiny chunks deduplicate by raw text"],
            ],
            widths=[34 * mm, 40 * mm, 58 * mm],
        ),

        P("2.3  Stage 2 \u2014 Duplicate detection (detection.py)", "H2"),
        P("Two lookup tables track what has been seen: a global one and a per-role one. Each "
          "chunk is classified:"),
        table(
            ["Situation", "Action", "Rationale"],
            [
                ["role == 'system'", "KEPT", "System prompts are instructions; never touched."],
                ["Same key, same role (repeated)", "REMOVED",
                 "Same speaker repeated itself verbatim \u2014 safe to elide."],
                ["Same key, different role", "FLAGGED_ONLY",
                 "Reported as waste, but kept: removing could drop content one speaker still needs."],
                ["First occurrence", "KEPT",
                 "Becomes the reference copy; records its id for the marker."],
            ],
            widths=[45 * mm, 24 * mm, 63 * mm],
        ),
        P("The removal rule is deliberately asymmetric: a user message is never deleted because "
          "an assistant once wrote identical text. Only same-speaker byte-repeats are removed."),

        P("2.4  Stage 3 \u2014 Optimization (optimization.py)", "H2"),
        P("Removed chunks are replaced with a 33-character marker "
          "[duplicate of chunk #N removed], where N is the chunk id of the reference copy "
          "\u2014 useful for debugging and auditing. A guard prevents negative reduction: if the "
          "marker would be as long as or longer than the chunk it replaces, the chunk is kept "
          "verbatim instead. Output characters therefore never exceed input characters."),
        P("Marker guard is the reason small chunks are never replaced: for a 60-character chunk "
          "the marker (33 chars) would fit, but for chunks below 64 chars the pipeline "
          "deliberately stays conservative and skips replacement entirely."),

        P("2.5  Stage 4 \u2014 Reporting (reporting.py)", "H2"),
        P("The final stage computes impact metrics and a human-readable report. Waste per block "
          "is (count \u2212 1) \u00d7 chunk_length; the worst five blocks are reported, sorted by "
          "chars wasted. Per-role redundancy percentages are computed and sorted worst-first. "
          "Safety notes are always appended, so every report documents what was NOT touched and "
          "why. A token note states which estimate was used \u2014 the default English heuristic "
          "(chars \u00f7 4) or a caller-provided token_estimator. In the optimize_text() path a "
          "\u201cSegments:\u201d section is inserted into the report listing each segment type "
          "with its count and mode (protected vs processed)."),
        PageBreak(),
    ]

    # ---- 3  Public API Contract ---------------------------------------------
    story += [
        P("3  Public API Contract", "H1"),
        P("3.1  Python API", "H2"),
        P("Two entry points cover both input shapes. optimize_context() takes the exact "
          "message list an application would send to a model; optimize_text() takes a plain "
          "string and pre-processes it with the segmentation layer first."),
        *CODE([
            "from contextray import optimize_context, optimize_text",
            "",
            "result = optimize_context(messages)          # messages: [{'role', 'content'}, ...]",
            'result = optimize_text(raw_text)             # raw_text: any str',
            "",
            "result[\"optimized_context\"]                 # drop-in message list (role/content dicts)",
            "result[\"metrics\"]                            # impact numbers",
            "result[\"top_waste_blocks\"]                  # worst 5 duplicate blocks",
            "result[\"report\"]                            # full human-readable summary",
            'result.get("segments")                       # per-type segmentation stats (text path only)',
        ]),
        P("The signatures optimize_context(messages, *, config=None, token_estimator=None, "
          "**kwargs) and optimize_text(text, *, config=None, token_estimator=None, **kwargs) "
          "are stable. config is accepted but currently ignored \u2014 it is reserved for future "
          "tuning knobs, and callers are not broken by its presence. A plain str passed to "
          "optimize_context() is treated as a single \u201ctext\u201d-role message."),
        table(
            ["Return key", "Type", "Meaning"],
            [
                ["optimized_context", "list[dict]", "Reconstructed messages, {'role': str, 'content': str} only \u2014 no chunk internals."],
                ["metrics", "dict", "Character and token impact numbers (below)."],
                ["top_waste_blocks", "list[dict]", "Worst duplicate blocks, max 5, sorted by chars_wasted desc."],
                ["report", "str", "Full printable summary incl. per-role stats and safety notes."],
                ["segments", "dict", "optimize_text() only: per-type counts and modes "
                 "(code/json/block/text), e.g. {\"code\": {\"count\": 4, \"mode\": \"protected\"}}."],
            ],
            widths=[40 * mm, 18 * mm, 74 * mm],
        ),
        P("metrics schema", "H2"),
        *CODE([
            '{',
            '  "total_chars_in": 3566,',
            '  "total_chars_out": 2759,',
            '  "chars_saved": 807,',
            '  "reduction_percentage": 22.6,',
            '  "est_tokens_in": 891.5,',
            '  "est_tokens_saved": 201.75,',
            '  "segmentation_fallback": false,   # optimize_text() path',
            '}',
        ]),
        P("Token estimates use the English heuristic characters \u00f7 4 \u2014 approximate by "
          "design (Section 8). Both functions accept an optional "
          "token_estimator: Callable[[str], float] keyword that replaces the heuristic: it is "
          "called with the full original text and the full optimized text, "
          "est_tokens_saved = est_tokens_in \u2212 est_tokens_out, and errors are re-raised "
          "with context (\u201ctoken_estimator raised on optimized text: \u2026\u201d)."),
        P("Each top_waste_blocks entry is {'hash', 'role', 'count', 'chars_wasted'}. "
          "Per-role redundancy stats exist but are exposed only inside the report string."),

        P("3.2  CLI", "H2"),
        *CODE([
            "usage: contextray optimize [-h] [--output OUTPUT] [--stdout] [--strict]",
            "                           [--max-input-mb MAX_INPUT_MB]",
            "                           input",
            "",
            "positional arguments:",
            "  input                 Path to a JSON message list, or any text file.",
            "",
            "options:",
            "  -h, --help            show this help message and exit",
            "  --output, -o OUTPUT   Where to write the optimized JSON",
            "                        (default: <input>_optimized<ext>)",
            "  --stdout              Print the optimized JSON to stdout instead of a file",
            "  --strict              Require the exact JSON message-list format; no",
            "                        text auto-detection",
            "  --max-input-mb FLOAT  Reject input files larger than this many MB",
            "                        (default: 50)",
        ]),
        P("The CLI auto-detects the input: a valid JSON message list is optimized as structured "
          "chat via optimize_context(); any other text (a .txt/.md file, logs, a raw dump) is "
          "optimized as a single \u201ctext\u201d message via optimize_text(), which runs the "
          "segmentation layer and prints a SEGMENTS section. Pass --strict to require the exact "
          "JSON message-list format."),
        P("The CLI writes three of the five result keys to the output file (optimized_context, "
          "metrics, top_waste_blocks); the printable report is rendered on the console. Exit "
          "codes: 0 success, 1 error, 2 usage error. Validation errors are reported to stderr "
          "with an [ERROR] / \u274c marker and never raise a traceback."),
        P("Terminal report layout", "H2"),
        *CODE([
            "=== CONTEXTRAY OPTIMIZATION REPORT ===",
            "SEGMENTS                                (text inputs only)",
            "- code: 4 (protected)",
            "- json: 1 (protected)",
            "- block: 1 (protected)",
            "- text: 6 (processed)",
            "",
            "IMPACT",
            "Original: 3029 chars",
            "Optimized: 1624 chars",
            "Saved: 1405 chars (46%)",
            "TOP WASTE",
            "- Hash 300b1660169c... repeated 2 times (990 chars wasted)",
            "- Hash b8a2b3980551... repeated 2 times (450 chars wasted)",
            "SAFETY",
            "[OK] System messages preserved",
            "[OK] Cross-role duplicates not removed",
            "[OK] Code blocks protected",
            "[OK] Small chunks skipped",
            "-------------------------------------",
            "Output saved to: input_optimized.json",
        ]),
        P("On Unicode terminals the section labels and markers render with glyphs "
          "(\ud83d\udcca IMPACT, \ud83d\udd25 TOP WASTE, \ud83d\udee1\ufe0f SAFETY, \u2714, "
          "\u274c); on legacy code pages (e.g. cp1252) the CLI falls back to ASCII "
          "automatically. In --stdout mode the payload goes to stdout and the report goes to "
          "stderr, so shell redirection stays clean (2&gt;/dev/null discards the report)."),
        PageBreak(),
    ]

    # ---- 4  Input Validation & Error Handling -------------------------------
    story += [
        P("4  Input Validation &amp; Error Handling", "H1"),
        P("Both APIs validate input strictly, in order, before any processing starts. The "
          "Python API fails fast with InvalidMessageError (a ValueError subclass) that names "
          "the offending message index and the exact problem \u2014 no coercion happens (None "
          "is not auto-converted to \"\", block lists are not stringified):"),
        table(
            ["Input problem", "Error (message index i)"],
            [
                ["'content' is None (tool-call-only turns)",
                 "InvalidMessageError: message[i]: 'content' is None, expected str"],
                ["'content' is a list of typed parts (image/text arrays)",
                 "InvalidMessageError: message[i]: 'content' is a list, expected str"],
                ["missing 'role' or 'content' key",
                 "InvalidMessageError: message[i]: missing required key 'role' / 'content'"],
                ["item is not a dict",
                 "InvalidMessageError: message[i]: expected a dict with 'role' and 'content'"],
                ["'role' or 'content' not a string",
                 "InvalidMessageError: message[i]: 'role' and 'content' must be strings"],
            ],
            widths=[58 * mm, 74 * mm],
        ),
        P("Validate your data at the boundary: a plain str is accepted (treated as a single "
          "\u201ctext\u201d message), dicts with extra keys are fine (extra keys are ignored), "
          "and everything else raises."),
        P("The CLI applies the same checks with JSON-friendly wording, in order:"),
        *bullets([
            "The file must exist and be readable, else: could not read &lt;path&gt;.",
            "The file size must not exceed --max-input-mb (default 50.0): "
            "\u201cinput file is 61.2MB, exceeds --max-input-mb limit of 50.0MB (raise the "
            "limit or split the file)\u201d.",
            "The file must be valid JSON, else the canonical message \u201cInvalid input "
            "format. Expected: [{'role': '...', 'content': '...'}]\u201d with a reason.",
            "The JSON must be a list at the top level.",
            "Every item must be a dict with string 'role' and 'content' keys.",
        ]),
        P("The entire CLI entry point is wrapped in a catch-all handler, so even unexpected "
          "runtime errors print \u201cError: &lt;message&gt;\u201d and exit 1 instead of a "
          "traceback."),
        PageBreak(),
    ]

    # ---- 5  Determinism & Verification --------------------------------------
    story += [
        P("5  Determinism &amp; Verification", "H1"),
        P("Every transformation is deterministic: sha256 hashing, ordered table lookups, marker "
          "generation, and report formatting are functions of the input bytes alone. The "
          "verification suite runs without any external dependencies (plain assert-based "
          "scripts, no pytest required):"),
        table(
            ["Suite", "Checks", "Covers"],
            [
                ["tests/test_core.py", "18",
                 "Public API contract: keys, message shape, determinism, no chunk leakage, "
                 "InvalidMessageError cases, token_estimator (default, custom, error wrapping)."],
                ["tests/test_pipeline.py", "181",
                 "Stage invariants, chunk sizes, role rules, unicode, code fences, 60k+ char "
                 "floods, MEGA scenarios, CLI text/json modes, SEGMENTS section, "
                 "--max-input-mb, optional real-Ollama contexts."],
                ["tests/test_segmentation.py", "23",
                 "Segments contiguous and byte-exact, fence/JSON/bare-Python rules, strict "
                 "bytes survive optimization, metrics exact with masking, duplicate STRICT "
                 "segments collapse, precedence rules, python-scan line guard, fallback, "
                 "segments breakdown."],
            ],
            widths=[34 * mm, 13 * mm, 85 * mm],
        ),
        P("222 checks in total, all passing. The pipeline suite writes its stress fixtures to "
          "test_contexts.txt (repo root) so every run is inspectable. A local Ollama is used "
          "when present and skipped with --skip-ollama in offline mode \u2014 the deterministic "
          "scenarios never require it."),
        PageBreak(),
    ]

    # ---- 6  Empirical Findings ----------------------------------------------
    story += [
        P("6  Empirical Findings (A/B with llama3.2:3b)", "H1"),
        P("A controlled study was run against a local llama3.2:3b at temperature 0 to measure "
          "where ContextRay actually pays off \u2014 and where it introduces risk. Three "
          "findings shaped the design:"),
        P("Finding 1 \u2014 Naturally written LLM dialogue contains ~0% exact duplicates", "H2"),
        P("Models paraphrase; byte-identical repeats are rare in natural dialogue. The realistic "
          "redundancy comes from the runtime \u2014 re-injected state, replayed turns, doubled "
          "cache/retry payloads. In one measured double-registered-turn scenario ContextRay "
          "achieved an 11.7% reduction on the later call. Expect ~0% savings on genuinely "
          "conversational transcripts (Section 8)."),
        P("Finding 2 \u2014 The marker text can bias models (documented risk)", "H2"),
        table(
            ["Transcript variant", "Reviewer verdict (5 runs)", "Determinism"],
            [
                ["Full duplicate present", "REJECTED 5/5", "Yes \u2014 temp 0, identical prompt"],
                ["[duplicate of chunk #4 removed] marker", "APPROVED 5/5",
                 "Yes \u2014 temp 0, identical prompt"],
                ["Duplicate silently removed", "REJECTED 5/5",
                 "Yes \u2014 temp 0, identical prompt"],
            ],
        ),
        P("The model read the marker as \u201ccleanup already performed \u2014 code quality "
          "improved\u201d and drifted toward approval. The removal itself is safe: silent "
          "removal scored identically to the full text. The marker string is the risk, not the "
          "deletion."),
        P("Finding 3 \u2014 Guidance derived from the test", "H2"),
        *bullets([
            "<b>Non-critical logging / archival:</b> the default marker is fine.",
            "<b>Agent pipelines</b> where a downstream agent makes go/no-go decisions on the "
            "transcript: consider a neutral elision wording or a silent-removal option, and "
            "re-test with the target model family.",
        ]),
        P("This is a behavior-observation document, not a guarantee. Marker bias varies by "
          "model family and prompt; the package ships the informative marker by default and "
          "documents the trade-off."),
        PageBreak(),
    ]

    # ---- 7  Safety Guarantees -----------------------------------------------
    story += [
        P("7  Safety Guarantees", "H1"),
        *bullets([
            "<b>System messages preserved.</b> The 'system' role is always KEPT \u2014 never "
            "touched by the pipeline.",
            "<b>Cross-role duplicates are never removed.</b> Same text in different roles is "
            "flagged and reported, never deleted.",
            "<b>STRICT segments survive byte-exact.</b> Fenced code, fenced blocks, whole-line "
            "JSON, and parseable bare Python are masked before deduplication and restored "
            "byte-for-byte afterwards \u2014 even when duplicated, only the first occurrence "
            "is kept and it is untouched.",
            "<b>No negative reductions.</b> A chunk is replaced by a marker only when the "
            "marker is strictly smaller; output characters never exceed input characters.",
            "<b>Tiny chunks are conservative.</b> Chunks below 64 chars are reported as waste "
            "but never replaced.",
            "<b>Placeholders never leak.</b> Masked text always restores to the original "
            "bytes; the placeholder prefix is chosen collision-free per run.",
            "<b>Guarded worst-case costs.</b> The unfenced-Python scan is skipped above 20,000 "
            "lines, and the CLI rejects oversized inputs (--max-input-mb, default 50 MB) "
            "instead of reading them.",
            "<b>Safe fallback.</b> If segmentation itself fails, optimize_text() runs the "
            "pipeline over the raw text and reports segmentation_fallback=True \u2014 the "
            "caller is never left without a result.",
        ]),
        PageBreak(),
    ]

    # ---- 8  Known Problems & Limitations ------------------------------------
    story += [
        P("8  Known Problems &amp; Limitations", "H1"),
        P("This section is written to be read. ContextRay makes explicit trade-offs; each is "
          "listed with its impact and the mitigation that exists today."),
        table(
            ["Limitation", "Impact", "Mitigation / status"],
            [
                ["Exact byte-level duplicates only",
                 "Semantic repeats, paraphrases, and near-duplicates are never removed \u2014 "
                 "savings ceiling is low on natural dialogue.",
                 "Documented expectation (~0% on conversational text); runtime redundancy is "
                 "the target use case."],
                ["Marker string can bias LLMs",
                 "A downstream model may read '[duplicate of chunk #N removed]' as a quality "
                 "signal and drift its verdict.",
                 "Empirically documented (Section 6); neutral wording or silent removal advised "
                 "for decision pipelines."],
                ["Structural coverage is finite",
                 "Only fenced blocks, whole-line JSON, and parseable bare Python (\u2265 3 "
                 "lines) are recognized; inline code (`x = 1`) and malformed fences chunk like "
                 "plain text.",
                 "Recognition is parser-verified (json.loads / ast.parse) \u2014 no guessing. "
                 "Unrecognized regions are never corrupted, worst case they deduplicate "
                 "like text."],
                ["Whitespace-sensitive hashing",
                 "text.strip() folds outer whitespace ('hello' == 'hello\\n') but inner "
                 "spacing stays significant ('a b' != 'a  b').",
                 "Conservative direction \u2014 false negatives over false positives."],
                ["Tiny chunks: flagged but never removable",
                 "Duplicates under 64 chars appear in top-waste reporting but are never "
                 "replaced.",
                 "Visibility without action; the marker-length guard makes removal unsafe for "
                 "micro-chunks."],
                ["Cross-role duplicates never removed",
                 "Same text in user and assistant turns stays in full \u2014 leaves savings on "
                 "the table.",
                 "Deliberate safety choice; reported as waste so users can decide manually."],
                ["Token estimates are a heuristic",
                 "chars \u00f7 4 is an English average; real tokenizer counts differ, "
                 "especially for code and non-English text.",
                 "Stated as estimates in the schema and report; a custom token_estimator "
                 "callable replaces the heuristic everywhere."],
                ["Unfenced-Python scan is capped",
                 "Inputs above 20,000 lines skip bare-Python detection, so large fence-free "
                 "documents lose that protection.",
                 "Fences and JSON still detected (linear cost); the threshold is configurable "
                 "(max_lines_for_python_scan, None = unlimited)."],
                ["Fallback loses STRICT protection",
                 "If segmentation raises, optimize_text() runs unprotected over the raw text.",
                 "Documented and flagged (segmentation_fallback=True + report prefix); output "
                 "is still valid, just not protected."],
                ["CLI rejects oversized files",
                 "Inputs above --max-input-mb (default 50 MB) are refused.",
                 "Raise the limit or split the file; the message says both."],
                ["config kwarg ignored",
                 "Chunk size limits and thresholds are not yet tunable at runtime.",
                 "Accepted for forward compatibility; module constants are the current knobs."],
            ],
            widths=[34 * mm, 57 * mm, 41 * mm],
        ),
        P("Open questions for the next releases:"),
        *bullets([
            "Should role stats, chunk sizes, and skipped-chunk counts enter the machine-readable "
            "contract?",
            "Should the marker text be configurable (a --no-markers / custom-wording option)?",
            "Should MIN/MAX chunk sizes become real config knobs now that the fallback path is "
            "exercised?",
        ]),
        PageBreak(),
    ]

    # ---- 9  Integration Guide ------------------------------------------------
    story += [
        P("9  Integration Guide", "H1"),
        P("Multi-turn chat loop (the standard use case)", "H2"),
        *CODE([
            "from contextray import optimize_context",
            "",
            "history = [{\"role\": \"system\", \"content\": SYSTEM_PROMPT}]",
            "while True:",
            "    user_in = input(\"You: \")",
            "    history.append({\"role\": \"user\", \"content\": user_in})",
            "    history = optimize_context(history)[\"optimized_context\"]",
            "    reply = call_model(history)",
            "    history.append({\"role\": \"assistant\", \"content\": reply})",
        ]),
        P("Optimizing every round keeps growth logarithmic: only genuinely new content is added "
          "while everything repeated is collapsed."),
        P("Raw text and documents", "H2"),
        *CODE([
            "from contextray import optimize_text",
            "",
            "notes = open(\"notes.md\", encoding=\"utf-8\").read()",
            "result = optimize_text(notes)       # segmentation runs first",
            "print(result[\"segments\"])          # {'code': {'count': 4, 'mode': 'protected'}, ...}",
            "optimized = \"\\n\".join(m[\"content\"] for m in result[\"optimized_context\"])",
        ]),
        P("Fenced code, JSON dumps, and pasted Python in the document are masked, deduplicated "
          "(if repeated), and restored byte-for-byte; the surrounding prose deduplicates like "
          "any chat message. The CLI takes the same path automatically for non-JSON files."),
        P("Agent / multi-agent flows", "H2"),
        *CODE([
            "def agent_turn(messages, handoff):",
            "    to_send = messages + [{\"role\": \"user\", \"content\": handoff}]",
            "    optimized = optimize_context(to_send)[\"optimized_context\"]",
            "    out = call_model(optimized)",
            "    messages.append({\"role\": \"assistant\", \"content\": out})",
            "    return out",
        ]),
        P("Structured data inside messages", "H2"),
        P("JSON content is plain text: the first occurrence is kept verbatim; an exactly "
          "repeated block is collapsed like any duplicate. Downstream parsers keep working as "
          "long as they read the first occurrence, which is untouched."),
        P("Golden rule", "H2"),
        P("Whatever list you would send to the model is what you feed to optimize_context(); "
          "whatever raw text you would paste is what you feed to optimize_text(). The output is "
          "a drop-in replacement \u2014 role and content strings only, in the original order. "
          "OpenAI, Ollama HTTP, and streaming payloads are all already compatible; streaming "
          "requires only that the caller accumulates the content parts into a string first."),
        PageBreak(),
    ]

    # ---- 10  Appendix A ------------------------------------------------------
    story += [
        P("10  Appendix A \u2014 Worked Example", "H1"),
        P("The shipped example examples/sample_chat.json:"),
        *CODE([
            "[",
            "  {\"role\": \"user\", \"content\": \"Explain recursion.\"},",
            "  {\"role\": \"assistant\", \"content\": \"Recursion is...\"},",
            "  {\"role\": \"assistant\", \"content\": \"Recursion is...\"}",
            "]",
        ]),
        P("Running contextray optimize examples/sample_chat.json yields:"),
        *CODE([
            "=== CONTEXTRAY OPTIMIZATION REPORT ===",
            "IMPACT",
            "Original: 48 chars",
            "Optimized: 48 chars",
            "Saved: 0 chars (0%)",
            "TOP WASTE",
            "- Hash Recursion is... repeated 2 times (15 chars wasted)",
            "SAFETY",
            "[OK] System messages preserved",
            "[OK] Cross-role duplicates not removed",
            "[OK] Code blocks protected",
            "[OK] Small chunks skipped",
            "-------------------------------------",
            "Output saved to: examples/sample_chat_optimized.json",
        ]),
        P("The duplicate is 15 chars \u2014 below MIN_CHUNK_SIZE (64) \u2014 so it is detected "
          "and reported as waste but deliberately not removed, exactly as the tiny-chunk "
          "limitation describes. This example is educational: it shows the reporting surface, "
          "not a realistic savings scenario."),
        P("Realistic scenario (development fixture)", "H2"),
        P("A fixture with repeated payloads, duplicated assistant turns, and code blocks:"),
        *CODE([
            "=== CONTEXTRAY OPTIMIZATION REPORT ===",
            "SEGMENTS",
            "- code: 2 (protected)",
            "- json: 1 (protected)",
            "IMPACT",
            "Original: 3029 chars",
            "Optimized: 1624 chars",
            "Saved: 1405 chars (46%)",
            "TOP WASTE",
            "- Hash 300b1660169c... repeated 2 times (990 chars wasted)",
            "- Hash b8a2b3980551... repeated 2 times (450 chars wasted)",
            "- Hash Sets use has... repeated 2 times (58 chars wasted)",
        ]),
        PageBreak(),
    ]

    # ---- 11  Appendix B ------------------------------------------------------
    story += [
        P("11  Appendix B \u2014 Quick Reference", "H1"),
        P("Segmentation decisions at a glance", "H2C"),
        table(
            ["Situation", "Segment"],
            [
                ["```-fenced block with a language tag", "code (STRICT)"],
                ["```-fenced block without a language tag", "block (STRICT)"],
                ["one or more whole lines forming a single parseable JSON value", "json (STRICT)"],
                ["\u2265 3 whole lines that parse as valid Python (inputs \u2264 20,000 lines)",
                 "code (STRICT)"],
                ["everything else", "text (FLEXIBLE)"],
            ],
            widths=[92 * mm, 40 * mm],
            compact=True,
        ),
        P("Pipeline decisions at a glance", "H2C"),
        table(
            ["Situation", "Result"],
            [
                ["system role", "always KEPT"],
                ["first occurrence of a key", "KEPT \u2014 becomes the reference copy"],
                ["same key again, same role", "REMOVED \u2014 replaced by marker"],
                ["same key again, different role", "FLAGGED_ONLY \u2014 kept, reported as waste"],
                ["chunk < 64 chars", "no hash; dedup by raw text; never replaced"],
                ["marker would be >= chunk length", "chunk kept verbatim (no negative reduction)"],
            ],
            widths=[92 * mm, 40 * mm],
            compact=True,
        ),
        P("Constants", "H2C"),
        *CODE([
            "MAX_CHUNK_SIZE            = 1000    # split ceiling (paragraphs -> lines -> whitespace)",
            "MIN_CHUNK_SIZE            = 64      # below this: hash = None, never removed",
            "CODE_FENCE_REGEX          = ```.*?```  (DOTALL)  # masked before splitting",
            "DEDUP_KEY                 = hash or raw text for tiny chunks",
            "MARKER                    = [duplicate of chunk #N removed]  (33 chars)",
            "TOKEN_HEURISTIC           = chars / 4   (or custom token_estimator)",
            "SEGMENT_PLACEHOLDER       = __SEG<N>__ + U+FEFF padding (length-preserving)",
            "MAX_LINES_FOR_PYTHON_SCAN = 20000   # unfenced-Python firewall (None = unlimited)",
            "MAX_INPUT_MB (CLI)        = 50.0    # input size guard",
        ]),
        P("CLI facts", "H2C"),
        *bullets([
            "Auto-detects input: JSON message list \u2192 optimize_context(); any other text "
            "\u2192 optimize_text() with a SEGMENTS section. --strict rejects text inputs.",
            "Default output name: &lt;input&gt;_optimized&lt;ext&gt; \u2014 same directory as "
            "the input; text inputs always become ..._optimized.json.",
            "Exit codes: 0 success / 1 error / 2 usage.",
            "--stdout writes pure JSON to stdout; header and report go to stderr.",
            "Emoji markers auto-fall back to ASCII on legacy consoles.",
        ], style="BulletC"),
        P("Project facts", "H2C"),
        *bullets([
            f"Package name contextray {VERSION}; MIT license; Python \u2265 3.9; zero runtime "
            "dependencies.",
            "Tests: 18 API + 181 pipeline + 23 segmentation checks, all passing (Section 5).",
            "Two public entry points: optimize_context() (chat) and optimize_text() (raw text "
            "with structural protection).",
            "This document was generated from the v0.3 codebase and README; figures reflect "
            "observed runs.",
        ], style="BulletC"),
    ]

    return story


# --------------------------------------------------------------------------
# two-pass build


def _build(toc_pages):
    doc = Paper(OUT, title="ContextRay Technical White Paper",
                author="ContextRay", subject=f"ContextRay v{VERSION} white paper")
    doc.build(_story(toc_pages))
    return doc


def main():
    pass1 = _build([])
    entries = list(pass1.toc_entries)  # (level, text, page) recorded during pass 1
    if entries[0][1] == "Contents":
        entries = entries[1:]  # TOC heading itself is captured by afterFlowable
    pass2 = _build([(level, text, page) for level, text, page in entries])
    final = pass2.toc_entries
    if [e[:2] for e in final[1:]] != [e[:2] for e in entries]:
        raise RuntimeError("heading set changed between passes")
    mismatches = [(a, b) for a, b in zip(entries, final[1:]) if a[2] != b[2]]
    if mismatches:
        raise RuntimeError(f"page numbers shifted between passes: {mismatches[:3]}")
    print(f"wrote {OUT}  ({len(entries)} TOC entries, {pass2.page} pages)")


if __name__ == "__main__":
    main()