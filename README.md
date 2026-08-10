# TokenLens

Character-level context optimizer for chat histories. Chunks messages with
markdown code-block protection, detects exact duplicates (per role and
globally), replaces removed duplicates with compact markers, and reports
per-role character/token savings.

- Deterministic: same messages always produce the same output
- Standard library only, no dependencies
- Code blocks (` ```...``` `) are protected, never split or altered

## Installation

```bash
pip install .
```

## Usage

```bash
tokenlens optimize input.json
tokenlens optimize input.json --output out.json
tokenlens optimize input.json --stdout
```

`input.json` is a list of messages:

```json
[
  {"role": "user", "content": "Explain lists vs tuples."},
  {"role": "assistant", "content": "A list is ordered and mutable..."}
]
```

## Python API

```python
from tokenlens import optimize_context

result = optimize_context(messages)

result["optimized_context"]  # deduplicated messages: [{"role": ..., "content": ...}]
result["metrics"]            # chars/tokens saved
result["top_waste_blocks"]   # worst duplicate blocks per role
result["report"]             # human-readable summary
```

## Tests

```bash
python tests/test_core.py
python tests/test_pipeline.py
```