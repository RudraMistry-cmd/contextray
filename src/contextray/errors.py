"""Package-level exceptions."""


class InvalidMessageError(ValueError):
    """A message dict is malformed: missing required keys or non-str content.

    Raised by ``chunk_and_hash`` with the offending message index and an
    explanation; the package intentionally fails fast instead of coercing.
    """