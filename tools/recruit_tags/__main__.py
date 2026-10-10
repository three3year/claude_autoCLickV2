"""`python tools/recruit_tags fetch-pool|recognize ...` 的進入點 (見 cli.py)."""
import sys
from pathlib import Path

# 以目錄執行時 sys.path[0] 是本套件目錄: 換成 tools/, 套件內的模組名
# (pool、render…) 才不會被當成頂層模組匯入
sys.path[0] = str(Path(__file__).resolve().parent.parent)

from recruit_tags.cli import main  # noqa: E402

sys.exit(main())
