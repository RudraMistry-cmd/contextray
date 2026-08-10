"""End-to-end stress test of the context optimizer pipeline
   (chunk_and_hash -> detect_duplicates -> optimize_chunks -> generate_metrics_and_report).

Covers:
  S1  - normal structured chat text (markdown, code blocks, paragraphs)
  S2A - 5.5k single-line word flood, duplicated across roles
  S2B - 2.6k run of one word, no whitespace anywhere (hard-cut path)
  S2C - messy mixed text: unicode, emoji, tabs, \r\n, double breaks
  S2D - code-block-only messages incl. a 4k-char fenced block
  S2E - edge cases: empty, whitespace-only, tiny duplicates
  H1  - HUGE structured document (~60k chars) with repeated boilerplate + copy message
  H2  - HUGE single-line flood (~60k chars, no paragraph breaks at all)
  H3  - HUGE code-heavy document (~60k chars, 30 fenced blocks > 1k each)
  H4  - 30k chars of one repeated letter (identical 1k chunks -> mass dedup)
  MEGA- 400k chars of seeded random text (no newlines) - fails if any shortcut
        on large inputs is taken, short samples always pass
  S3  - real-world context from a local Ollama model (optional, graceful fallback)

All input contexts are written to test_contexts.txt in the repo root.

Usage:  python tests/test_pipeline.py      (attempts local Ollama; falls back)
        python tests/test_pipeline.py --skip-ollama
"""

import hashlib
import json
import os
import random
import sys
import urllib.request

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

from contextray.chunking import (  # noqa: E402
    chunk_and_hash,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
)
from contextray.detection import detect_duplicates  # noqa: E402
from contextray.optimization import optimize_chunks  # noqa: E402
from contextray.reporting import generate_metrics_and_report  # noqa: E402

HERE = _THIS_DIR
CONTEXT_FILE = os.path.join(_REPO_ROOT, "test_contexts.txt")

_passed = 0
_failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}")


def sha256_hex(text):
    return hashlib.sha256(text.strip().encode()).hexdigest()


def run_pipeline(messages):
    chunks = chunk_and_hash(messages)
    marked = detect_duplicates(chunks)
    optimized = optimize_chunks(marked)
    report = generate_metrics_and_report(chunks, optimized)
    return chunks, marked, optimized, report


def message_ranges(chunks, messages):
    """(start, end) chunk-index range that belongs to each message."""
    ranges = []
    start = 0
    for msg in messages:
        acc = ""
        end = start
        for i in range(start, len(chunks)):
            acc += chunks[i]["text"]
            end = i + 1
            if len(acc) >= len(msg["content"]):
                break
        ranges.append((start, end))
        start = end
    return ranges


def test_chunk_invariants(name, messages):
    print(f"\n=== {name} ===")
    chunks, marked, optimized, report = run_pipeline(messages)
    metrics = report["metrics"]

    check(f"{name}: ids are incremental",
          [c["id"] for c in chunks] == list(range(len(chunks))))
    check(f"{name}: hash matches sha256 of stripped text (None for tiny chunks)",
          all((c["hash"] == sha256_hex(c["text"])
               if len(c["text"]) >= MIN_CHUNK_SIZE
               else c["hash"] is None)
              for c in chunks))
    check(f"{name}: lengths match text",
          all(c["length"] == len(c["text"]) for c in chunks))
    check(f"{name}: no chunk exceeds {MAX_CHUNK_SIZE} unless it holds a code block",
          all(len(c["text"]) <= MAX_CHUNK_SIZE or "```" in c["text"] for c in chunks))

    ranges = message_ranges(chunks, messages)
    ok_reassembly = True
    for (start, end), msg in zip(ranges, messages):
        if "".join(c["text"] for c in chunks[start:end]) != msg["content"]:
            ok_reassembly = False
    if ranges and ranges[-1][1] != len(chunks):
        ok_reassembly = False
    check(f"{name}: chunked text reassembles to original (nothing modified)", ok_reassembly)

    def dedup_key(c):
        return c["hash"] if c["hash"] is not None else c["text"]

    role_kept = {}
    global_kept = set()
    first_id = {}
    ok_semantics = True
    for c in chunks:
        first_id.setdefault(dedup_key(c), c["id"])
    for c in marked:
        key = dedup_key(c)
        if c["action"] == "KEPT":
            role_kept.setdefault(c["role"], set()).add(key)
            global_kept.add(key)
        elif c["action"] == "REMOVED":
            if key not in role_kept.get(c["role"], set()):
                ok_semantics = False
        elif c["action"] == "FLAGGED_ONLY":
            if key not in global_kept:
                ok_semantics = False
        else:
            ok_semantics = False
        if c["action"] != "KEPT":
            if c["duplicate_of"] != first_id[key] or not isinstance(c["duplicate_of"], int):
                ok_semantics = False
        elif c["duplicate_of"] is not None:
            ok_semantics = False
    check(f"{name}: dedup semantics consistent (twin earlier, refs point to first kept)", ok_semantics)

    check(f"{name}: metrics formulas",
          metrics["total_chars_in"] == sum(c["length"] for c in chunks)
          and metrics["total_chars_out"] == sum(len(c["text"]) for c in optimized)
          and metrics["chars_saved"] == metrics["total_chars_in"] - metrics["total_chars_out"]
          and metrics["est_tokens_in"] == metrics["total_chars_in"] / 4
          and metrics["est_tokens_saved"] == metrics["chars_saved"] / 4
          and ((metrics["reduction_percentage"]
                == round(metrics["chars_saved"] / metrics["total_chars_in"] * 100, 2))
               if metrics["total_chars_in"] else metrics["reduction_percentage"] == 0.0))

    check(f"{name}: top waste sorted desc, capped at 5, only count>1",
          len(report["top_waste_blocks"]) <= 5
          and all(report["top_waste_blocks"][i]["chars_wasted"]
                  >= report["top_waste_blocks"][i + 1]["chars_wasted"]
                  for i in range(len(report["top_waste_blocks"]) - 1)))

    check(f"{name}: report has impact + tokens",
          "Impact:" in report["report"] and "Estimated tokens" in report["report"])
    check(f"{name}: report has safety notes",
          all(s in report["report"] for s in ["System messages preserved",
                                               "Cross-role duplicates not removed",
                                               "Code blocks protected"]))

    check(f"{name}: optimize keeps order/roles/ids",
          [c["id"] for c in optimized] == [c["id"] for c in chunks]
          and [c["role"] for c in optimized] == [c["role"] for c in chunks])

    ok_replacements = True
    for orig_c, opt_c in zip(chunks, optimized):
        if opt_c["action"] == "REMOVED":
            expected = f'[duplicate of chunk #{opt_c["duplicate_of"]} removed]'
            if opt_c["text"] != expected:
                ok_replacements = False
        elif opt_c["text"] != orig_c["text"]:
            ok_replacements = False
    check(f"{name}: REMOVED text replaced, others untouched", ok_replacements)

    check(f"{name}: deterministic across runs",
          run_pipeline(messages)[-1] == report)

    removed = sum(1 for c in marked if c["action"] == "REMOVED")
    flagged = sum(1 for c in marked if c["action"] == "FLAGGED_ONLY")
    kept = sum(1 for c in marked if c["action"] == "KEPT")
    m = report["metrics"]
    print(f"  summary: {len(messages)} messages -> {len(chunks)} chunks "
          f"(kept={kept}, removed={removed}, flagged={flagged}) | "
          f"{m['total_chars_in']:,} chars -> {m['total_chars_out']:,} chars "
          f"({m['reduction_percentage']}%)")
    return chunks, marked, optimized, report


def test_duplicate_actions(name, messages, msg_index, duplicate_type):
    """Every chunk of the given message must carry the expected action."""
    chunks, marked, _, _ = run_pipeline(messages)
    (start, end) = message_ranges(chunks, messages)[msg_index]
    expected = "REMOVED" if duplicate_type == "same_role" else "FLAGGED_ONLY"
    dup_chunks = marked[start:end]
    check(f"{name}: message[{msg_index}] chunks are all {expected}",
          len(dup_chunks) > 0 and all(c["action"] == expected for c in dup_chunks))


# --------------------------------------------------------------------------
#  BUILD CONTEXTS
# --------------------------------------------------------------------------

SYSTEM_PROMPT = ("You are CodeWise, a senior Python software engineer. Give concise, "
                 "actionable answers with runnable code examples.")

boilerplate = ("Note: this example is intentionally simplified for clarity. In production "
               "code you would add error handling, logging and tests. Always validate your "
               "assumptions against the actual runtime version you target.")

structured_heading = "## Lists vs Tuples vs Sets in Python"
structured_para1 = ("Python offers several built-in collection types. A list is an ordered, "
                    "mutable sequence that allows duplicates and supports append, insert and "
                    "slicing. A tuple is an immutable ordered sequence, useful as a key in "
                    "dictionaries or as a fixed contract. A set is unordered, deduplicates "
                    "automatically and gives O(1) membership tests, but its elements must be "
                    "hashable. Choosing the right one matters for both clarity and runtime "
                    "behaviour, especially when processing large collections. A common mistake "
                    "is using a list where a set would be faster: membership tests on a list "
                    "scan linearly, while a set hashes elements and stays fast even with "
                    "millions of entries. Mutation rules differ too: because lists are mutable "
                    "they are not hashable, so you cannot place a list inside a set or use it "
                    "as a dictionary key, while tuples avoid that limitation. Iteration is "
                    "fastest on lists and tuples, and sets trade iteration speed for lookup "
                    "speed, so pick whichever matches your hot operation.")
structured_code1 = ("```python\n"
                    "items = [1, 2, 2, 3]\n"
                    "items.append(4)\n"
                    "unique = list(dict.fromkeys(items))  # preserves order\n"
                    "lookup = set(unique)\n"
                    "print(3 in lookup)  # True, O(1)\n```")
structured_para3 = ("When you read rows from a database cursor you typically collect them "
                    "into a list of tuples. If you then need to deduplicate results across "
                    "pages, converting the list to a set is the fastest approach, provided "
                    "the rows are hashable. If order matters, fall back to a list with a "
                    "seen-set.")
big_code_block = "```python\n" + "".join(
    f"mapping[{i}] = {i * 7}  # entry number {i}\n" for i in range(40)) + "```"

scenario1_msgs = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "Explain the differences between lists, tuples and sets in Python with code."},
    {"role": "assistant", "content": "\n\n".join([
        structured_heading, structured_para1, structured_code1, boilerplate])},
    {"role": "user", "content": "Show how this applies when processing a result set from a database query."},
    {"role": "assistant", "content": "\n\n".join([
        structured_heading, structured_para3, big_code_block, boilerplate])},
    {"role": "user", "content": boilerplate},
    {"role": "assistant", "content": boilerplate},
]

lorem_line = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
              "incididunt ut labore et dolore magna aliqua ut enim ad minim veniam quis nostrud "
              "exercitation ullamco laboris nisi aliquip ex ea commodo consequat. ")
b1_text = lorem_line * 24

scenario2a_msgs = [
    {"role": "user", "content": b1_text},
    {"role": "user", "content": b1_text},
    {"role": "assistant", "content": b1_text},
]

scenario2b_msgs = [
    {"role": "user", "content": "x" * 2600},
]

messy = ("!!!RUSHED-NOTES!!!\n\n\n"
         "todo: call vendor re specs \t tomorrow\n"
         "```json\n{\"ok\": true, \"replies\": 42}\n```\n"
         "random( " * 300 + "x\n"
         "ä¸­æ–‡å†…å®¹ã€‚æ—¥æœ¬èªžãƒ†ã‚¹ãƒˆã€‚ã™ã”ã„ã€‚\n"
         "0" * 400 + "\n"
         "final line \r\n avec returns\r\n"
         "  spacing  \n\n  double break above\n"
         "Tab\tcauses\tcut\tpaths\there\t" * 30)

scenario2c_msgs = [
    {"role": "user", "content": messy},
    {"role": "assistant", "content": messy},
]

scenario2d_msgs = [
    {"role": "user", "content": "```python\nprint('hi')\n```"},
    {"role": "user", "content": "```\n" + "line of text\n" * 300 + "```"},
]

scenario2e_msgs = [
    {"role": "user", "content": ""},
    {"role": "user", "content": "   \n "},
    {"role": "assistant", "content": "ok"},
    {"role": "assistant", "content": "ok"},
    {"role": "user", "content": "ok"},
]

# --- HUGE contexts (short inputs always pass; these would catch shortcuts) ----

h1_parts = []
for i in range(60):
    h1_parts.append(f"## Section {i}: performance and memory")
    h1_parts.append(f"Paragraph {i}. When processing large data sets the dominant cost is "
                    "memory allocation, not the comparison itself. Batch your work, reuse "
                    "containers and profile before you optimize anything else in the hot loop.")
    h1_parts.append(boilerplate)
    h1_parts.append("```python\n" +
                    "".join(f"print(f'item {j} -> {j * i}')  # section {i} trace\n"
                            for j in range(20)) + "```")
h1_doc = "\n\n".join(h1_parts)

scenario_h1_msgs = [
    {"role": "user", "content": h1_doc},
    {"role": "user", "content": h1_doc},
]

scenario_h2_msgs = [
    {"role": "user", "content": lorem_line * 260},
    {"role": "assistant", "content": lorem_line * 260},
]

h3_parts = []
for i in range(30):
    h3_parts.append(f"## Module {i}: implementation notes")
    h3_parts.append(f"Prose for module {i} describing the public API, the invariants the "
                    "implementation relies on, and the edge cases the tests cover.")
    h3_parts.append("```python\n" +
                    "".join(f"def handler_{i}_{j}(value):\n"
                            f"    result = value * {i} + {j}\n"
                            f"    return int(result)\n\n"
                            for j in range(60)) + "```")
h3_doc = "\n\n".join(h3_parts)

scenario_h3_msgs = [
    {"role": "user", "content": h3_doc},
]

scenario_h4_msgs = [
    {"role": "user", "content": "Q" * 30000},
]

rng = random.Random(42)
mega_text = "".join(rng.choice("abcde fghij") for _ in range(400_000))

scenario_mega_msgs = [
    {"role": "user", "content": mega_text},
]


# --------------------------------------------------------------------------
#  OLLAMA (optional, local models only)
# --------------------------------------------------------------------------

def ollama_available():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as resp:
            data = json.load(resp)
        names = sorted(m["name"] for m in data.get("models", []))
        return names[0] if names else None
    except Exception:
        return None


def ollama_generate(model, prompt, timeout=180):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    request = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        data = json.load(resp)
    return data.get("response", "").strip()


def load_ollama_contexts():
    if "--skip-ollama" in sys.argv:
        print("\nOllama skipped (--skip-ollama flag).")
        return None, None
    model = ollama_available()
    if not model:
        print("\nOllama not reachable (no local model on localhost:11434) "
              "- using built-in samples only.")
        return None, None
    print(f"\nFetching real-world context from local Ollama model: {model}")
    transcript_prompt = ("Write a realistic technical support chat between a user named Alex "
                         "and a support agent about a failing CI pipeline. Include many "
                         "back-and-forth turns, troubleshooting steps, one fenced code block "
                         "with a YAML config snippet, and a clear resolution at the end. "
                         "At least 900 words. Reply with only the transcript text.")
    note_prompt = ("Write a long messy personal note written by a tired developer: stream of "
                   "consciousness, typos, run-on sentences, mixed line breaks, occasional "
                   "fragments, scattered ideas about work tasks, no headings. At least 600 "
                   "words. Reply with only the note text.")
    try:
        transcript = ollama_generate(model, transcript_prompt)
        note = ollama_generate(model, note_prompt)
    except Exception as exc:
        print(f"Ollama generation failed ({exc}) - using built-in samples only.")
        return None, None
    if len(transcript) < 600 or len(note) < 400:
        print("Ollama output too short - using built-in samples only.")
        return None, None
    msgs = [
        {"role": "system", "content": "You are a senior support engineer analyzing conversation context."},
        {"role": "user", "content": transcript},
        {"role": "assistant", "content": note},
        {"role": "user", "content": transcript},
    ]
    return msgs, model


# --------------------------------------------------------------------------
#  CONTEXT FILE
# --------------------------------------------------------------------------

def write_context_file(scenarios, ollama_msgs, ollama_model):
    lines = [
        "CONTEXT SAMPLES USED BY test_pipeline.py",
        "Each section mirrors the exact input messages passed to the pipeline.",
        "",
    ]
    for name, messages in scenarios:
        lines.append(f"=== {name} ===")
        for i, msg in enumerate(messages):
            preview = msg["content"]
            if len(preview) > 4000:
                preview = preview[:4000] + f"\n... [truncated, total length {len(msg['content'])} chars]"
            lines.append(f"[{i}] role={msg['role']}  length={len(msg['content'])}")
            lines.append(preview)
            lines.append("---")
        lines.append("")
    if ollama_model and ollama_msgs:
        lines.append(f"=== SCENARIO 3: OLLAMA REAL-WORLD (model: {ollama_model}) ===")
        for i, msg in enumerate(ollama_msgs):
            lines.append(f"[{i}] role={msg['role']}  length={len(msg['content'])}")
            lines.append(msg["content"])
            lines.append("---")
        lines.append("")
    else:
        lines.append("=== SCENARIO 3: OLLAMA ===")
        lines.append("(no local Ollama model was available - built-in samples used instead)")
        lines.append("")
    with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nContext samples written to: {CONTEXT_FILE}")


# --------------------------------------------------------------------------
#  RUN
# --------------------------------------------------------------------------

def main():
    scenarios = [
        ("SCENARIO 1: STRUCTURED CHAT", scenario1_msgs),
        ("SCENARIO 2A: 5.5K SINGLE-LINE FLOOD x3 ROLES", scenario2a_msgs),
        ("SCENARIO 2B: 2.6K RUN, NO WHITESPACE", scenario2b_msgs),
        ("SCENARIO 2C: UNICODE / EMOJI / TABS / MIXED BREAKS", scenario2c_msgs),
        ("SCENARIO 2D: CODE-BLOCK-ONLY MESSAGES", scenario2d_msgs),
        ("SCENARIO 2E: EDGE CASES (EMPTY, WHITESPACE, TINY DUPS)", scenario2e_msgs),
        ("HUGE 1: 60K STRUCTURED DOC + COPY MESSAGE", scenario_h1_msgs),
        ("HUGE 2: 60K SINGLE-LINE FLOOD x2 ROLES", scenario_h2_msgs),
        ("HUGE 3: 60K CODE-HEAVY DOC (30 BLOCKS >1K)", scenario_h3_msgs),
        ("HUGE 4: 30K REPEATED LETTER (IDENTICAL 1K CHUNKS)", scenario_h4_msgs),
        ("MEGA: 400K SEEDED RANDOM, NO NEWLINES", scenario_mega_msgs),
    ]

    ollama_msgs, ollama_model = load_ollama_contexts()
    if ollama_msgs:
        scenarios.append(("SCENARIO 3: OLLAMA REAL-WORLD", ollama_msgs))

    write_context_file(scenarios, ollama_msgs, ollama_model)

    print("\n" + "=" * 70)
    print("PIPELINE TESTS")
    print("=" * 70)

    for name, messages in scenarios:
        chunks, marked, optimized, report = test_chunk_invariants(name, messages)

        if name.startswith("SCENARIO 1"):
            test_duplicate_actions(name, messages, 5, "cross_role")
            test_duplicate_actions(name, messages, 6, "same_role")
        elif name.startswith("SCENARIO 2A"):
            test_duplicate_actions(name, messages, 1, "same_role")
            test_duplicate_actions(name, messages, 2, "cross_role")
        elif name.startswith("SCENARIO 2B"):
            texts = [c["text"] for c in chunks]
            actions = [c["action"] for c in marked]
            check(f"{name}: 1000/1000/600 hard-cut chunks",
                  texts == ["x" * 1000, "x" * 1000, "x" * 600])
            check(f"{name}: identical 1k chunks -> second REMOVED",
                  actions == ["KEPT", "REMOVED", "KEPT"]
                  and marked[1]["duplicate_of"] == 0)
        elif name.startswith("SCENARIO 2C"):
            test_duplicate_actions(name, messages, 1, "cross_role")
        elif name.startswith("SCENARIO 2D"):
            check(f"{name}: code block survives as single >1k chunk",
                  any(len(c["text"]) > MAX_CHUNK_SIZE and "```" in c["text"] for c in chunks))
        elif name.startswith("SCENARIO 2E"):
            test_duplicate_actions(name, messages, 3, "same_role")
            test_duplicate_actions(name, messages, 4, "cross_role")
            tiny = [c for c in chunks if c["role"] == "assistant" and c["text"] == "ok"]
            check(f"{name}: OK/OK/OK visibility: 'ok' chunks carry no hash (hashing skipped)",
                  len(tiny) == 2 and all(c["hash"] is None for c in tiny))
            check(f"{name}: tiny duplicates still DETECTED (action REMOVED)",
                  all(c["action"] == "REMOVED" for c in marked if c["text"] == "ok" and c["role"] == "assistant" and c["id"] > tiny[0]["id"]))
            opt_ok = [c for c in optimized if c["text"] == "ok"]
            check(f"{name}: but tiny chunks are NOT replaced (thresholded optimization)",
                  len(opt_ok) == 3 and all(c["text"] == "ok"
                                           and c["action"] in ("KEPT", "FLAGGED_ONLY")
                                           for c in opt_ok))
            check(f"{name}: tiny waste visible in top blocks (role + count)",
                  any(b["hash"] == "ok" and b["role"] == "assistant" and b["count"] == 3
                      for b in report["top_waste_blocks"]))
            check(f"{name}: report shows tiny visibility line",
                  "[assistant] block ok" in report["report"]
                  and "repeated 3 times" in report["report"])
        elif name.startswith("HUGE 1"):
            test_duplicate_actions(name, messages, 1, "same_role")
        elif name.startswith("HUGE 2"):
            test_duplicate_actions(name, messages, 1, "cross_role")
        elif name.startswith("HUGE 3"):
            n_big = sum(1 for c in chunks if len(c["text"]) > MAX_CHUNK_SIZE)
            check(f"{name}: all 30 fenced blocks survived as oversized chunks",
                  n_big == 30)
        elif name.startswith("HUGE 4"):
            actions = [c["action"] for c in marked]
            check(f"{name}: 30 identical 1k chunks -> 1 kept, 29 removed",
                  len(chunks) == 30 and actions == ["KEPT"] + ["REMOVED"] * 29)
        elif name.startswith("MEGA"):
            check(f"{name}: handled 400k chars in reasonable chunk count",
                  250 <= len(chunks) <= 450)
        elif name.startswith("SCENARIO 3"):
            test_duplicate_actions(name, messages, 3, "same_role")

    empty = run_pipeline([])
    check("empty message list: zero metrics, no crash",
          empty[0] == [] and empty[3]["metrics"]["total_chars_in"] == 0
          and empty[3]["metrics"]["reduction_percentage"] == 0.0
          and "none" in empty[3]["report"])

    print("\n" + "=" * 70)
    print("WEAK-SPOT CHECKS (role visibility + per-role redundancy)")
    print("=" * 70)
    chunks, marked, _, report = run_pipeline(scenario1_msgs)
    blocks = report["top_waste_blocks"]

    check("waste blocks carry role field",
          all("role" in b and isinstance(b["role"], str) for b in blocks))
    check("role-first waste line format in report",
          all(f"[{b['role']}] block" in report["report"] for b in blocks))

    role_stats = report["role_stats"]
    roles = {s["role"]: s for s in role_stats}
    check("role_stats covers every role",
          {"system", "user", "assistant"} <= set(roles))
    check("role_stats sorted by redundancy desc (ties by role)",
          all(role_stats[i]["redundancy_percentage"] >= role_stats[i + 1]["redundancy_percentage"]
              for i in range(len(role_stats) - 1)))
    check("role formulas consistent with metrics",
          sum(s["chars_in"] for s in role_stats) == report["metrics"]["total_chars_in"]
          and sum(s["chars_saved"] for s in role_stats) == report["metrics"]["chars_saved"])
    check("duplicate-heavy role shows higher redundancy (assistant > user)",
          roles["assistant"]["redundancy_percentage"] > roles["user"]["redundancy_percentage"])
    check("system role shows 0% redundancy (always preserved)",
          roles["system"]["redundancy_percentage"] == 0.0
          and roles["system"]["chars_saved"] == 0)
    check("report contains per-role redundancy section",
          "Per-role redundancy:" in report["report"]
          and f"{roles['assistant']['redundancy_percentage']}% redundant" in report["report"])
    check("big chunks still hashed (no regression)",
          all(c["hash"] is not None for c in chunks if len(c["text"]) >= MIN_CHUNK_SIZE))

    print()

    print("\n" + "=" * 70)
    print("REDUCTION SUMMARY")
    print("=" * 70)
    print(f"{'scenario':<52}{'chars in':>12}{'saved':>10}{'%':>9}  {'removed':>8}{'flagged':>8}")
    for name, messages in scenarios:
        chunks, marked, _, report = run_pipeline(messages)
        metrics = report["metrics"]
        removed = sum(1 for c in marked if c["action"] == "REMOVED")
        flagged = sum(1 for c in marked if c["action"] == "FLAGGED_ONLY")
        print(f"{name[:52]:<52}{metrics['total_chars_in']:>12,}{metrics['chars_saved']:>10,}"
              f"{metrics['reduction_percentage']:>8.2f}%{removed:>8}{flagged:>8}")
    print()

    print("=" * 70)
    print(f"RESULT: {_passed} passed, {_failed} failed")
    if _failed:
        sys.exit(1)
    print("ALL PASSED")


if __name__ == "__main__":
    main()