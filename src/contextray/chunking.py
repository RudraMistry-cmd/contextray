import hashlib
import re

from .errors import InvalidMessageError

MAX_CHUNK_SIZE = 1000
MIN_CHUNK_SIZE = 64  # Prevents chunk explosion and negative reduction on tiny strings

# Code-block protection scope (V1): only standard triple-backtick fenced blocks
# (```...```). Inline code (``x``) and malformed/unbalanced fences are left as-is
# and chunked like ordinary text.


def chunk_and_hash(messages: list[dict]) -> list[dict]:
    _validate_messages(messages)
    chunks = []
    next_id = 0

    for message in messages:
        role = message["role"]
        masked, blocks = _protect_code_blocks(message["content"])

        for piece in _split_text(masked):
            text = _restore_blocks(piece, blocks)
            length = len(text)
            # Thin chunks are noise: skip the sha256 work entirely (hash = None)
            # Hashing decision (V1): deterministic over clever. text.strip() folds
            # leading/trailing whitespace ("hello" == "hello\n"), but inner spacing
            # stays significant ("hello world" != "hello  world").
            chunk_hash = None if length < MIN_CHUNK_SIZE else hashlib.sha256(text.strip().encode()).hexdigest()
            chunks.append(
                {
                    "id": next_id,
                    "role": role,
                    "text": text,
                    "length": length,
                    "hash": chunk_hash,
                }
            )
            next_id += 1

    return chunks


def _validate_messages(messages: list[dict]) -> None:
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise InvalidMessageError(
                f"message[{index}]: expected a dict with 'role' and 'content', "
                f"got {type(message).__name__}")
        if "role" not in message:
            raise InvalidMessageError(f"message[{index}]: missing required key 'role'")
        if "content" not in message:
            raise InvalidMessageError(f"message[{index}]: missing required key 'content'")
        if not isinstance(message["role"], str):
            raise InvalidMessageError(
                f"message[{index}]: 'role' is {message['role']!r}, expected str")
        content = message["content"]
        if not isinstance(content, str):
            if content is None:
                hint = ("tool-call-only turns are not supported "
                        "\u2014 see README Input Contract")
                described = "None"
            elif isinstance(content, list):
                hint = ("typed content blocks are not supported "
                        "\u2014 see README Input Contract")
                described = "a list"
            else:
                hint = "see README Input Contract"
                described = repr(content)
            raise InvalidMessageError(
                f"message[{index}]: 'content' is {described}, expected str ({hint})")


def _protect_code_blocks(text: str) -> tuple[str, list[tuple[str, str]]]:
    blocks = []

    def replace(match: re.Match) -> str:
        placeholder = f"__BLOCK_{len(blocks) + 1}__"
        blocks.append((placeholder, match.group(0)))
        return placeholder

    masked = re.sub(r"```.*?```", replace, text, flags=re.DOTALL)
    return masked, blocks


def _split_text(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_SIZE:
        return [text]

    pieces = []
    for paragraph in _split_keeping_delimiter(text, "\n\n"):
        if len(paragraph) <= MAX_CHUNK_SIZE:
            pieces.append(paragraph)
            continue
        for line in _split_keeping_delimiter(paragraph, "\n"):
            if len(line) <= MAX_CHUNK_SIZE:
                pieces.append(line)
                continue
            pieces.extend(_split_at_nearest_whitespace(line))
    return [p for p in pieces if p]


def _split_keeping_delimiter(text: str, delimiter: str) -> list[str]:
    pieces = []
    start = 0
    while True:
        end = text.find(delimiter, start)
        if end == -1:
            pieces.append(text[start:])
            break
        pieces.append(text[start : end + len(delimiter)])
        start = end + len(delimiter)
    return pieces


def _split_at_nearest_whitespace(text: str) -> list[str]:
    pieces = []
    start = 0
    while len(text) - start > MAX_CHUNK_SIZE:
        end = start + MAX_CHUNK_SIZE
        cut = max(text.rfind(" ", start, end), text.rfind("\t", start, end))
        if cut == -1:
            pieces.append(text[start:end])
            start = end
        else:
            pieces.append(text[start : cut + 1])
            start = cut + 1
    pieces.append(text[start:])
    return pieces


def _restore_blocks(piece: str, blocks: list[tuple[str, str]]) -> str:
    for placeholder, block in blocks:
        piece = piece.replace(placeholder, block)
    return piece