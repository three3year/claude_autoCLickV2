"""公開招募標籤辨識 (recruit-tags): 吃一張公開招募畫面截圖, 認出五個`標籤格`
各是哪個`招募標籤`, 再用`招募池`快照算出`保底組合` (詞彙見 app/CONTEXT.md「公開招募」)。

本輪只做可行性驗證: 不點擊、不截圖、不碰 app、不進打包版。與`影片轉流程`同紀律——
只用引擎公開 API (`make_library`、`Engine.register`、`Engine.query`、`load_config`),
不經 runner, 不是 app 的第二條辨識路徑。對外兩個入口::

    build_pool(gacha, character, server)
        gacha_table + character_table (已解析的 JSON) → 招募池快照
    recognize(image, pool, engine=None, client="tw", cells=None, render_settings=None)
        截圖 + 快照 → 五格辨識結果、嚴格通過與否、保底組合

命令列 (`python tools/recruit_tags fetch-pool|recognize ...`, 見 `cli.py`) 另外
負責抓上游資料表 (網路動作只在 CLI)。拒絕繼續時丟 `ToolError`, 訊息給人看。
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from .errors import ToolError  # noqa: E402
from .pool import build_pool, load_pool  # noqa: E402
from .recognize import recognize  # noqa: E402

__all__ = ["ToolError", "build_pool", "load_pool", "recognize"]
