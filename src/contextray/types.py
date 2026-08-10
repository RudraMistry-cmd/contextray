"""Shared type aliases for clarity. Informational only - runtime behavior uses dicts."""

from typing import TypedDict, Union

Message = TypedDict("Message", {"role": str, "content": str})

Chunk = TypedDict(
    "Chunk",
    {
        "id": int,
        "role": str,
        "text": str,
        "length": int,
        "hash": Union[str, None],
        "action": str,
        "duplicate_of": Union[int, None],
    },
    total=False,
)

Config = dict