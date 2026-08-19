"""ContextRay - character-level context optimizer for chat histories."""

from .core import optimize_context, optimize_text
from .errors import InvalidMessageError
from .segmentation import Segment, segment_text

__version__ = "0.3.0"

__all__ = [
    "optimize_context",
    "optimize_text",
    "segment_text",
    "Segment",
    "InvalidMessageError",
]