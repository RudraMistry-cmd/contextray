"""Allow ``python -m tokenlens`` to behave like the ``tokenlens`` CLI."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())