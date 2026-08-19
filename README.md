# ContextRay

Deterministic context optimization for LLMs.

Reduce token usage, remove redundant context, and improve reasoning quality —
without breaking your prompts, without ML, without hallucination risk.

---

## Table of Contents

- [The Problem](#-the-problem)
- [What ContextRay Is (and Is Not)](#-what-contextray-is-and-is-not)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Input Contract — What to Feed In](#-input-contract--what-to-feed-in)
- [Output Structure](#-output-structure)
- [How It Works — The Pipeline](#-how-it-works--the-pipeline)
- [Safety Guarantees & V1 Limitations](#-safety-guarantees--v1-limitations)
- [Integration Guides](#-integration-guides)
- [Known Behavior: Markers and LLMs](#-known-behavior-markers-and-llms)
- [Troubleshooting & FAQ](#-troubleshooting--faq)
- [CLI Reference](#-cli-reference)
- [Tests](#-tests)
- [License](#-license)

---

## 🚨 The Problem

LLM-based systems (agents, chatbots, workflows) accumulate massive context
over time. Every request re-sends the whole conversation history, so:

- 💸 High token costs (you pay per token *sent*)
- 🐢 Slower responses (larger prompt = slower prefill)
- 🧠 Worse reasoning (needle-in-a-haystack: old facts get buried under noise)

Most "solutions" summarize or compress with ML models. That destroys:

- JSON payloads
- code blocks
- structured system prompts

---

## ✅ What ContextRay Is (and Is Not)

| | |
|---|---|
| **Is** | a deterministic, character-level context optimizer |
| **Is** | byte-safe: it only ever *removes* text, never rewrites it |
| **Does** | detect exact duplicates → replace repeats with small markers |
| **Does** | protect code blocks, whole-line JSON, and bare Python (segmentation layer) |
| **Does** | protect system messages, and skip small chunks conservatively |
| **Is NOT** | an ML model, a summarizer, or a compressor |
| **Is NOT** | fuzzy/paraphrase-aware (V1: exact matches only) |

---

## 📦 Installation

```bash
pip install .          # from the repository root
# or, once published on PyPI:
pip install contextray
```

Requirements: Python >= 3.9. No runtime dependencies (stdlib only).

---

## 🚀 Quick Start

### Python API

```python
from contextray import optimize_context

messages = [
    {"role": "user", "content": "Explain recursion"},
    {"role": "assistant", "content": "Recursion is a function that calls itself..."},
    {"role": "assistant", "content": "Recursion is a function that calls itself..."},  # exact dup
]

result = optimize_context(messages)

optimized = result["optimized_context"]   # deduplicated message list, ready to send
print(result["metrics"])                  # impact numbers
print(result["report"])                   # human-readable summary
```

Raw text / documents get their own entry point — the segmentation layer
protects fenced code, JSON, and bare Python blocks before deduplication:

```python
from contextray import optimize_text

result = optimize_text(open("notes.md", encoding="utf-8").read())
print(result["segments"])   # {'code': {'count': 4, 'mode': 'protected'}, ...}
```

### CLI

```bash
contextray optimize input.json            # writes input_optimized.json
contextray optimize input.json --output out.json
contextray optimize input.json --stdout   # print JSON to stdout
contextray optimize notes.txt             # plain text works too — auto-detected
contextray optimize --strict input.json   # require the exact JSON message-list format
contextray optimize --max-input-mb 200 input.json   # raise the size guard (default 50 MB)
```

The CLI **auto-detects** the input: a JSON message list is optimized as
structured chat; any other file (`.txt`, `.md`, logs, raw dumps) is optimized
via `optimize_text()` — segmentation included, with a `SEGMENTS` section in
the console report. Pass `--strict` to require the exact JSON message-list
format.

---

## 📥 Input Contract — What to Feed In

This is the #1 source of integration errors. Read carefully.

### Exact format

A **list of dicts**, each with exactly two string keys:

```python
[
    {"role": "<str>", "content": "<str>"},
    ...
]
```

- `role`: the speaker id. Any string (`"user"`, `"assistant"`, `"system"`,
  `"tool"`, `"function"`, ...). Only `"system"` has special meaning
  (always preserved).
- `content`: the message text. **Must be a plain `str`.**

### Validation (CLI)

By default the CLI accepts **any text**. Auto-detection rules (deterministic):

- valid JSON **list of dicts** → treated as messages; each dict must have
  string `role` + `content`, else a clean `[ERROR]` explains the problem
- valid JSON **single message dict** (`{"role", "content"}`) → one message
- **anything else** (plain text, non-list JSON, broken JSON…) → optimized as
  one `"text"` message

With `--strict` the old behavior returns — anything that is not a JSON
message list is rejected with:

```
[ERROR] Invalid input format. Expected: [{'role': '...', 'content': '...'}]
```

> Note: the Python API intentionally fails fast — malformed input raises
> `InvalidMessageError` (a `ValueError` subclass) naming the offending
> message index, e.g.
> `InvalidMessageError: message[3]: 'content' is None, expected str (tool-call-only turns are not supported — see README Input Contract)`.
> No coercion happens (`None` is not auto-converted to `""`, block lists
> are not stringified) — validate your data at the boundary. A bare `str`
> is accepted and treated as a single `"text"` message.

### ✅ Yes — LLM responses work directly

A response from any chat API is already a dict with `role` and `content` —
**exactly** what ContextRay eats. Feed the whole history you would send the
model, get back the optimized history:

```python
optimized = optimize_context(messages)["optimized_context"]
# send `optimized` to the model instead of `messages`
```

### ❌ Things that will NOT work

| Input | Why it fails |
|---|---|
| `content: None` (tool-call-only assistant turns) | `InvalidMessageError: message[i]: 'content' is None, expected str (tool-call-only turns are not supported — see README Input Contract)` |
| `content` as a list of typed parts (image/text arrays) | `InvalidMessageError: message[i]: 'content' is a list, expected str (typed content blocks are not supported — see README Input Contract)` |
| top-level dict / string / number | not a list |
| missing `role` or `content` key | `InvalidMessageError: message[i]: missing required key 'role'` / `...'content'` |
| message is not a dict | `InvalidMessageError: message[i]: expected a dict with 'role' and 'content', got <type>` |
| dicts with extra keys `{"role", "content", "name", ...}` | **works** — extra keys are ignored |

### Where the messages come from (no extra work needed)

```python
# OpenAI SDK — already compatible
completion = client.chat.completions.create(model="gpt-4o", messages=messages)
msg = completion.choices[0].message
messages.append({"role": msg.role, "content": msg.content})

# Ollama HTTP API — already compatible
resp = requests.post("http://localhost:11434/api/chat", json={...}).json()
messages.append(resp["message"])   # {"role": "assistant", "content": "..."}

# Streaming — accumulate the text yourself
text = "".join(chunk["message"]["content"] for chunk in stream)
messages.append({"role": "assistant", "content": text})
```

**Golden rule:** whatever list you'd send to the model is what you feed to
`optimize_context`. The output is a drop-in replacement for that list.

---

## 📈 Output Structure

`optimize_context()` returns a dict with 4 keys; `optimize_text()` returns the
same 4 plus a 5th (`segments`):

| key | type | meaning |
|---|---|---|
| `optimized_context` | `list[dict]` | deduplicated messages (`role`/`content` only) |
| `metrics` | `dict` | impact numbers (see below) |
| `top_waste_blocks` | `list[dict]` | worst duplicate blocks, max 5, sorted by `chars_wasted` desc |
| `report` | `str` | full human-readable summary (incl. per-role stats) |
| `segments` | `dict` | **`optimize_text()` only** — per-type segmentation stats, e.g. `{"code": {"count": 4, "mode": "protected"}}` |

`metrics`:

```json
{
  "total_chars_in": 3566,
  "total_chars_out": 2759,
  "chars_saved": 807,
  "reduction_percentage": 22.6,
  "est_tokens_in": 891.5,
  "est_tokens_saved": 201.75,
  "segmentation_fallback": false
}
```

`segmentation_fallback` appears in the `optimize_text()` path: it is `true`
when the segmentation step itself failed and the pipeline ran over the raw
text instead (safe, but without STRICT protection — the report is prefixed
with a note).

Token estimates use the English heuristic **chars ÷ 4** — approximate by
design. Both `optimize_context()` and `optimize_text()` accept an optional
`token_estimator: Callable[[str], float]` kwarg; when provided it replaces
the chars/4 figure everywhere: it is called with the full original text and
the full optimized text, and `est_tokens_saved` is
`est_tokens_in - est_tokens_out`. If it raises, the error is re-raised with
context (`token_estimator raised on optimized text: <original error>`).

```python
# tiktoken is NOT a dependency of this package - this example is illustrative
# only. pip install tiktoken if you want to try it.
# import tiktoken
# enc = tiktoken.encoding_for_model("gpt-4o")
# result = optimize_context(messages, token_estimator=lambda t: len(enc.encode(t)))
```

`top_waste_blocks` entry: `{"hash", "role", "count", "chars_wasted"}`.

> Per-role redundancy stats exist but only inside the `report` string —
> they are not exposed as a separate key (V1).

---

## 🔬 How It Works — The Pipeline

```
segment_text (segmentation layer)            ← optimize_text() only
      ↓
chunk_and_hash  →  detect_duplicates  →  optimize_chunks  →  generate_metrics_and_report
```

### 0. Structural Segmentation (`segmentation.py`)

Before deduplication, `segment_text()` splits raw text into ordered,
contiguous, byte-exact segments. Each segment is either **STRICT** (masked
out of the pipeline, restored byte-for-byte afterwards) or **FLEXIBLE**
(deduplicated like ordinary text). The rules are purely structural — no NLP,
no guessing:

| type | detection rule | mode |
|---|---|---|
| `code` | ``` ```-fenced block with a language tag | STRICT |
| `block` | ``` ```-fenced block with no language tag | STRICT |
| `json` | whole lines forming a single parseable JSON value (verified with `json.loads`) | STRICT |
| `code` | ≥ 3 whole lines that parse as valid Python (verified with `ast.parse`) — covers pasted code without fences | STRICT |
| `text` | everything else | FLEXIBLE |

Masking replaces each STRICT segment with a `__SEG…` token padded to the
segment's exact length, so chunking behavior and metrics are unchanged, and
byte-identical STRICT segments collapse like any other duplicate (the
first occurrence is restored byte-for-byte). Guards:

- **Line-count firewall:** the unfenced-Python scan restarts from every
  candidate line (superlinear on fence-free prose), so inputs above
  **20,000 lines** skip it — fences and JSON still run. Configurable via
  `segment_text(..., max_lines_for_python_scan=...)` (`None` = unlimited).
- **Safe fallback:** if segmentation itself raises, `optimize_text()` runs
  the pipeline over the raw text and sets `metrics["segmentation_fallback"]`
  to `True` — you always get a result, never a crash.

### 1. Chunking (`chunking.py`)

- Messages are split into **chunks of ≤ 1000 chars** (`MAX_CHUNK_SIZE`),
  preferring `\n\n` paragraph breaks, then `\n` line breaks, then whitespace.
- **Fenced code blocks** (``` ``` ) are masked with placeholders first so
  they are never split; the real text is restored afterwards.
- Chunks **< 64 chars** (`MIN_CHUNK_SIZE`) get no sha256 hash — treated as
  noise, but still deduplicated by their raw text.
- Every chunk gets a `sha256` hash of `text.strip()` (leading/trailing
  whitespace is folded; inner spacing is significant).

### 2. Detection (`detection.py`)

Two lookup tables: `global_seen` and `role_seen`.

| situation | action |
|---|---|
| `system` role | **KEPT** — always preserved |
| same text, same role (seen before) | **REMOVED** |
| same text, different role | **FLAGGED_ONLY** — detected, kept for safety |
| first occurrence | **KEPT** (becomes the reference copy) |

Design principle: removal is always "safe" — a user message is never deleted
because an assistant once wrote the same text; only same-speaker repeats are
removed.

### 3. Optimization (`optimization.py`)

Removed chunks are replaced with:

```
[duplicate of chunk #N removed]
```

where `N` is the **chunk id of the first occurrence** (useful for
debugging!). Guard: if the 33-char marker would be *longer* than the chunk
itself, the chunk is kept instead (never make things worse).

### 4. Reporting (`reporting.py`)

- `wasted = (count - 1) × chunk_length`, top 5 blocks reported
- per-role redundancy %, sorted worst-first
- safety notes always appended

---

## 🛡️ Safety Guarantees & V1 Limitations

Guaranteed:

- ✅ System messages preserved (never touched)
- ✅ Cross-role duplicates NOT removed (only flagged)
- ✅ Code blocks protected (never split, never corrupted)
- ✅ STRICT segments survive **byte-exact** — fenced code, whole-line JSON,
  and parseable bare Python are masked before dedup and restored
  byte-for-byte even when duplicated (`optimize_text()` path)
- ✅ No negative reductions (marker must be smaller than the chunk)
- ✅ No crashes on bad inputs: `InvalidMessageError` naming the message
  index; CLI exits `1` with a one-line error, never a traceback
- ✅ Safe fallback: segmentation failure → plain-text pipeline with
  `segmentation_fallback: true` instead of an exception
- ✅ Bounded worst cases: unfenced-Python scan capped at 20,000 lines;
  CLI rejects inputs over `--max-input-mb` (default 50 MB)
- ✅ Small chunks (< 64 chars) handled conservatively

V1 limitations (be aware):

- ⚠️ Only **exact byte-level duplicates** — no similarity, no paraphrases
- ⚠️ Structural recognition covers standard triple-backtick fences,
  whole-line JSON, and bare Python (≥ 3 parseable lines); inline
  `` `code` `` and malformed fences chunk like plain text
- ⚠️ Above 20,000 lines the bare-Python scan is skipped (fences and JSON
  still protected) — raise/disable `max_lines_for_python_scan` if you need
  it on huge documents
- ⚠️ In fallback mode (`segmentation_fallback: true`) STRICT protection is
  lost; the result is still valid, just unprotected
- ⚠️ Token estimates are approximate (÷4 English heuristic, or your
  `token_estimator`)
- ⚠️ `config` kwarg is accepted but currently ignored (reserved for tuning)

---

## 🔌 Integration Guides

### Multi-turn chat loop (the standard use case)

```python
from contextray import optimize_context

history = [{"role": "system", "content": SYSTEM_PROMPT}]

while True:
    user_in = input("You: ")
    history.append({"role": "user", "content": user_in})

    history = optimize_context(history)["optimized_context"]   # dedup every round

    reply = call_model(history)                    # your LLM call
    history.append({"role": "assistant", "content": reply})
```

Optimizing **every round** keeps the growth logarithmic: only new content is
added, everything that repeats is collapsed.

### Agent / multi-agent flows

Each agent receives the full accumulated transcript. Optimize before every
agent call:

```python
def agent_turn(messages, handoff):
    to_send = messages + [{"role": "user", "content": handoff}]
    optimized = optimize_context(to_send)["optimized_context"]
    out = call_model(optimized)
    messages.append({"role": "assistant", "content": out})
    return out
```

### Structured data (JSON) inside messages

JSON content is plain text: first occurrence is kept verbatim; an exactly
repeated JSON block is collapsed like any duplicate. The reference copy in
the transcript stays untouched, so downstream parsers keep working as long
as they read the *first* occurrence.

### When NOT to use it

- When the transcript contains no same-role byte-duplicates
  (realistic natural dialogue: expect ~0% savings — see next section).
- When a downstream decision-maker must see every byte of a repeated block
  *in place* (see marker warning below).

---

## ⚠️ Known Behavior: Markers and LLMs

Empirical findings from an A/B test with `llama3.2:3b` (temp 0):

1. **Naturally written LLM conversations contain ~0% exact duplicates.**
   Models paraphrase — byte-identical repeats are rare. Real redundancy
   comes from the *runtime*: frameworks that re-inject state, replay
   completed turns, cache/retry messages. Those are where ContextRay pays
   off (measured 11.7% reduction per later call on a double-registered
   turn).

2. **The marker text can bias models.** In a controlled reviewer test:
   - transcript with the full duplicate → model **REJECTED** the code (5/5)
   - transcript with `[duplicate of chunk #4 removed]` → model **APPROVED**
     (5/5)
   - transcript with the duplicate silently removed → model **REJECTED**
     (5/5)
   - all runs fully deterministic.
   The model read the marker as *"cleanup already performed — code quality
   improved"* and drifted toward approval.

3. **The removal is safe; the marker string is the risk.** Silent removal
   behaved identically to the full text in the same test.

Practical guidance:

- For non-critical logging/archival: fine as-is.
- For agent pipelines where a subsequent agent makes go/no-go decisions on
  the transcript: consider a neutral marker wording (e.g. an elision
  statement) or a `--no-markers` style silent removal, and test with your
  own models — behavior varies by model family.

---

## 🐞 Troubleshooting & FAQ

**Q: What do I feed to `optimize_context`?**
A list of `{"role": str, "content": str}` dicts — exactly what you'd send to
the LLM. LLM responses are already in this shape; append them and optimize.

**Q: I got `KeyError: 'content'` / `TypeError`.**
A message dict is missing `content` (or it isn't a string). Tool-call-only
assistant turns return `content: None` in some APIs — filter them out first,
e.g. `m for m in messages if isinstance(m.get("content"), str)`.

**Q: It removed nothing. Why?**
(Diagnose in this order:)
1. Duplicates must be ≥ 64 chars — tiny repeats are skipped.
2. Duplicates must be same-role — cross-role repeats are only flagged.
3. Duplicates must be *byte-identical* — whitespace or quoting differences
   break the hash.
4. `system` messages are always preserved.
5. The content really is naturally-written: LLM text rarely repeats exactly.

**Q: How do I see *what* was flagged but not removed?**
`result["top_waste_blocks"]` lists the worst duplicate blocks. The `report`
includes "Cross-role duplicates detected (not removed for safety)".

**Q: What does `[duplicate of chunk #5 removed]` mean?**
The chunk's text was byte-identical to earlier chunk `#5` (the reference
copy, which is still in the transcript).

**Q: What is the `segments` key / `SEGMENTS` section?**
`optimize_text()` reports what the segmentation layer did per type:
`{"code": {"count": 4, "mode": "protected"}}` — `protected` means every
segment of that type was STRICT (masked and restored byte-exact),
`processed` means FLEXIBLE (deduplicated like text). The CLI prints the
same data as a `SEGMENTS` section in the console report for text inputs.

**Q: The CLI refused my file with a `--max-input-mb` error.**
Inputs over 50 MB are rejected to bound memory. Re-run with
`--max-input-mb 200` (or any size) or split the file — the error message
says both.

**Q: Does it ever *create* tokens?**
Only pathological micro-chunks could be replaced by a longer marker — that
case is explicitly guarded (chunk kept, stats recomputed) so output chars
never exceed input.

**Q: Why is my JSON inside a message broken after optimization?**
It shouldn't be — the first occurrence is untouched. If you're parsing a
*repeated* copy that was replaced, parse the first occurrence instead.
Malformed/partial JSON blocks are plain text to ContextRay, like any other
content.

**Q: Can I tune chunk sizes?**
Not yet (V1). `MIN_CHUNK_SIZE = 64` and `MAX_CHUNK_SIZE = 1000` are module
constants. `optimize_context(..., config=...)` accepts a dict but ignores
it — reserved for future knobs.

**Q: The CLI says "not valid JSON".**
Your input file isn't a JSON list. Check: top level must be `[ ... ]`,
messages must be `{"role": "...", "content": "..."}`.

**Q: My terminal shows `[OK]` instead of `✓` / `📊`.**
The CLI auto-falls back to ASCII on legacy consoles (cp1252 etc.). Run in
Windows Terminal / a UTF-8 terminal for the emoji form.

**Q: Does streaming mode need anything special?**
No — accumulate the streamed `content` chunks into a string, append as an
assistant message, optimize next round.

**Q: Benchmarking: is dedup byte-safe for embeddings/search?**
Removal preserves the first occurrence; hashes are sha256 of stripped text —
no transformation of kept content.

---

## 🖥️ CLI Reference

```
usage: contextray optimize [-h] [--output OUTPUT] [--stdout] [--strict]
                           [--max-input-mb MAX_INPUT_MB]
                           input

positional arguments:
  input                 Path to a JSON message list, or any text file.

options:
  -h, --help            show this help message and exit
  --output, -o OUTPUT  Where to write the optimized JSON
                       (default: <input>_optimized<ext>)
  --stdout              Print the optimized JSON to stdout instead of a file
  --strict              Require the exact JSON message-list format; no text
                        auto-detection
  --max-input-mb FLOAT  Reject input files larger than this many MB
                        (default: 50)
```

Notes:

- Default output: `input_optimized.json` (same extension as input). Text
  inputs always become `<name>_optimized.json` — the result is JSON either way.
- Text inputs run through `optimize_text()` — the console report gains a
  `SEGMENTS` section (per-type counts/modes) and the metrics include
  `segmentation_fallback`.
- The CLI writes 3 of the 5 result keys (`optimized_context`, `metrics`,
  `top_waste_blocks`) — the printable `report` is shown on the console only.
- Exit codes: `0` success, `1` error, `2` usage error.
- Validation errors are reported to stderr with `[ERROR]`/`❌`.
- `--max-input-mb` guards memory: an oversized file is refused with a
  message suggesting the fix (`(raise the limit or split the file)`).

---

## ✅ Tests

Three assert-based suites (no pytest required); 222 checks in total:

```bash
python tests/test_core.py             # 18 checks — API contract, validation errors, token_estimator
python tests/test_pipeline.py         # 181 checks — end-to-end stress pipeline (uses local Ollama if present)
python tests/test_pipeline.py --skip-ollama  # offline mode
python tests/test_segmentation.py     # 23 checks — segment rules, byte-exact protection, guards, fallback
```

The pipeline suite covers 60k+ char floods, code-heavy documents, unicode,
CLI text/JSON modes, the SEGMENTS section, and `--max-input-mb`. The
segmentation suite verifies fence/JSON/bare-Python rules, byte-exact
restoration, STRICT duplicate collapse, the line-count firewall, and the
fallback path. Stress fixtures are written to `test_contexts.txt` in the
repo root.

---

## 📜 License

MIT License. See `LICENSE`.