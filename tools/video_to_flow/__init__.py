"""影片轉流程 (video-to-flow): 把一段`示範影片`變成一份一般的流程存檔.

不是 app 功能, 也不進打包版: 由 Claude 依專案 skill `video-to-flow` 呼叫。
對外是掃描與組裝兩個入口 (外加給掃描用的學游標樣本), 中間由 Claude 判斷 (詞彙見 app/CONTEXT.md「影片轉流程」)::

    scan(video, out_dir, sample=None, frames=())
        示範影片 → 候選點擊清單 (candidates.json) + 每個候選前後數幀的縮圖
    learn_cursor(video, points, out_path)
        遊戲自繪游標 → 游標樣本 (給 scan 的 sample; 錄影程式畫不出點擊特效時用)
    assemble(plan, engine=None, fingerprint=None, report_path=None)
        轉換計畫 + 目標 profile → 自我驗證 → 流程存檔 + 交付報告

兩個入口都有命令列 (`python tools/video_to_flow scan|assemble ...`, 見
`cli.py`)。任何「計畫或輸入有問題、工具拒絕繼續」都丟 `ToolError`,
訊息是給人看的中文; 拒絕時 profile 一個檔案都不會多。

全程只讀影片與 profile 檔案: 不截圖、不動滑鼠鍵盤、不碰真實螢幕。
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "app", _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from .errors import ToolError  # noqa: E402
from .assemble import assemble  # noqa: E402
from .cursor import learn as learn_cursor  # noqa: E402
from .scan import scan  # noqa: E402

__all__ = ["ToolError", "assemble", "learn_cursor", "scan"]
