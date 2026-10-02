"""`python tools/video_to_flow scan|assemble ...` 的進入點 (見 cli.py)."""
import sys
from pathlib import Path

# 以目錄執行時 sys.path[0] 是本套件目錄: 換成 tools/, 套件內的模組名
# (plan、video…) 才不會被當成頂層模組匯入
sys.path[0] = str(Path(__file__).resolve().parent.parent)

from video_to_flow.cli import main  # noqa: E402

sys.exit(main())
