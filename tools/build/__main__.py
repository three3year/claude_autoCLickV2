"""`python tools/build [--dry-run]` 的進入點."""
import sys
from pathlib import Path

sys.path[0] = str(Path(__file__).resolve().parent.parent)

from build import main  # noqa: E402

sys.exit(main())
