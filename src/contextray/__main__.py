"""Allow ``python -m contextray`` to behave like the ``contextray`` CLI."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())