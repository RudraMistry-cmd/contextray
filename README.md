# ContextRay

Deterministic context optimization for LLMs.

Reduce token usage, remove redundancy, and improve reasoning quality — without breaking your prompts.

---

## 🚨 The Problem

LLM-based systems (agents, chatbots, workflows) accumulate massive context over time.

This leads to:

- 💸 High token costs
- 🐢 Slower responses
- 🧠 Worse reasoning (needle-in-a-haystack problem)

Most solutions try to "summarize" or "compress" context using ML.

That breaks:

- JSON
- code blocks
- structured prompts

---

## ✅ The Solution

ContextRay is a deterministic context optimizer.

It does NOT summarize.

It does NOT hallucinate.

It simply:

- removes duplicate content
- preserves structure
- keeps everything byte-safe

---

## 🔥 What It Does

Given a large LLM context, ContextRay:

- detects repeated chunks
- removes safe duplicates
- preserves critical instructions
- protects code blocks and structured data
- shows you exactly where tokens are being wasted

---

## ⚡ Example

### Input

```json
[
  {"role": "user", "content": "Explain recursion"},
  {"role": "assistant", "content": "Recursion is..."},
  {"role": "assistant", "content": "Recursion is..."}
]
```

A ready-to-run copy lives in `examples/sample_chat.json`.

### Run

```bash
contextray optimize input.json
```

### Output

```text
✔ ContextRay Optimization Complete

=== CONTEXTRAY OPTIMIZATION REPORT ===

📊 IMPACT
Original: 1200 chars
Optimized: 700 chars
Saved: 500 chars (42%)

🔥 TOP WASTE
- Hash a1b2c3d4e5f6... repeated 2 times (450 chars wasted)

🛡️ SAFETY
✓ System messages preserved
✓ Cross-role duplicates not removed
✓ Code blocks protected
✓ Small chunks skipped

-------------------------------------
Output saved to: input_optimized.json
```

---

## 🛡️ Safety Guarantees

- System messages are preserved
- Code blocks are protected
- Cross-role duplicates are NOT removed
- Small chunks are ignored
- No ML, no hallucination risk

---

## 📦 Installation

```bash
pip install .
```

or from PyPI once published:

```bash
pip install contextray
```

---

## 🚀 Usage

### CLI

```bash
contextray optimize input.json
```

Optional:

```bash
--output out.json     # custom output path (default: <input>_optimized<ext>)
--stdout              # print JSON to stdout instead of writing a file
```

### Python API

```python
from contextray import optimize_context

result = optimize_context(messages)

print(result["optimized_context"])
print(result["report"])
```

---

## 📈 Output Structure

```json
{
  "optimized_context": [{"role": "...", "content": "..."}],
  "metrics": {"total_chars_in": 0, "total_chars_out": 0, "chars_saved": 0, "reduction_percentage": 0.0},
  "top_waste_blocks": [],
  "report": "..."
}
```

---

## ⚠️ Limitations (V1)

- Only exact duplicate detection
- Basic code block detection
- Token estimation is approximate

---

## 📜 License

MIT License