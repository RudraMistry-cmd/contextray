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
| **Does** | protect code blocks, system messages, and small chunks |
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

### CLI

```bash
contextray optimize input.json            # writes input_optimized.json
contextray optimize input.json --output out.json
contextray optimize input.json --stdout   # print JSON to stdout
contextray optimize notes.txt             # plain text works too — auto-detected
```

The CLI **auto-detects** the input: a JSON message list is optimized as
structured chat; any other file (`.txt`, `.md`, logs, raw dumps) is optimized
as a single `"text"` message. Pass `--strict` to require the exact JSON
message-list format.

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

> Note: the Python API does *not* validate for you — malformed input raises
> natural Python errors (`KeyError`, `TypeError`, `json.JSONDecodeError`).
> Validate your data at the boundary. A bare `str` is accepted and treated
> as a single `"text"` message.

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
| `content: None` (tool-call-only assistant turns) | not a string → `TypeError` |
| `content` as a list of typed parts (image/text arrays) | not a string |
| top-level dict / string / number | not a list |
| missing `role` or `content` key | `KeyError` |
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

`optimize_context()` returns a dict with 4 keys:

| key | type | meaning |
|---|---|---|
| `optimized_context` | `list[dict]` | deduplicated messages (`role`/`content` only) |
| `metrics` | `dict` | impact numbers (see below) |
| `top_waste_blocks` | `list[dict]` | worst duplicate blocks, max 5, sorted by `chars_wasted` desc |
| `report` | `str` | full human-readable summary (incl. per-role stats) |

`metrics`:

```json
{
  "total_chars_in": 3566,
  "total_chars_out": 2759,
  "chars_saved": 807,
  "reduction_percentage": 22.6,
  "est_tokens_in": 891.5,
  "est_tokens_saved": 201.75
}
```

Token estimates use the English heuristic **chars ÷ 4** — approximate by
design.

`top_waste_blocks` entry: `{"hash", "role", "count", "chars_wasted"}`.

> Per-role redundancy stats exist but only inside the `report` string —
> they are not exposed as a separate key (V1).

---

## 🔬 How It Works — The Pipeline

```
chunk_and_hash  →  detect_duplicates  →  optimize_chunks  →  generate_metrics_and_report
```

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
- ✅ Small chunks (< 64 chars) handled conservatively
- ✅ No negative reductions (marker must be smaller than the chunk)

V1 limitations (be aware):

- ⚠️ Only **exact byte-level duplicates** — no similarity, no paraphrases
- ⚠️ Code-block protection covers standard triple-backtick fences only
  (inline `` `code` `` and malformed fences chunk like plain text)
- ⚠️ Token estimates are approximate (÷4 English heuristic)
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
usage: contextray optimize [-h] [--output OUTPUT] [--stdout] input

positional arguments:
  input                 Path to a JSON message list, or any text file.

options:
  -h, --help            show this help message and exit
  --output, -o OUTPUT  Where to write the optimized JSON
                       (default: <input>_optimized<ext>)
  --stdout              Print the optimized JSON to stdout instead of a file
```

Notes:

- Default output: `input_optimized.json` (same extension as input). Text
  inputs always become `<name>_optimized.json` — the result is JSON either way.
- The CLI writes 3 of the 4 result keys (`optimized_context`, `metrics`,
  `top_waste_blocks`) — the printable `report` is shown on the console only.
- Exit codes: `0` success, `1` error, `2` usage error.
- Validation errors are reported to stderr with `[ERROR]`/`❌`.

---

## ✅ Tests

Run the API test (no dependencies, plain `assert`):

```bash
python tests/test_core.py
```

Run the end-to-end stress pipeline (covers 60k+ char floods, code-heavy
documents, unicode, and optional real Ollama contexts):

```bash
python tests/test_pipeline.py                # uses local Ollama if present
python tests/test_pipeline.py --skip-ollama  # offline mode
```

Stress fixtures are written to `test_contexts.txt` in the repo root.

---

## 📜 License

MIT License. See `LICENSE`.