import sys
from pathlib import Path

sys.path[0] = str(Path(__file__).resolve().parent.parent)

from flow_check import main  # noqa: E402

sys.exit(main())
